"""Spotify para SAGE por la Web API: reproduce canciones y PLAYLISTS por detrás, sin tocar el mouse, el teclado ni el foco de Niko.

Todo se hace con peticiones a la API de Spotify (play va al reproductor que ya tengas: PC, celular...). Lo único visible que puede pasar:
si Spotify de escritorio no está abierto, se lanza MINIMIZADO y sin activarse (SAGE_SPOTIFY_ABRIR=0 lo desactiva).

Requisitos: cuenta Spotify Premium (la exige la API), SPOTIPY_CLIENT_ID / SPOTIPY_CLIENT_SECRET en .env y `pip install spotipy`.
Autorización (UNA sola vez, en la terminal; así SAGE nunca abre el navegador por su cuenta mientras trabajas):
    python spotify_sage.py autorizar
Otros comandos de prueba:
    python spotify_sage.py playlists | playlist NOMBRE [aleatorio|orden] | cancion BUSQUEDA | dispositivos

.env opcional: SAGE_SPOTIFY_DISPOSITIVO=parte del nombre del dispositivo donde reproducir (por defecto: el activo, si no el PC, si no el primero).

Más pruebas:  python spotify_sage.py volumen subir|bajar|"subir 20"|40|silenciar
              python spotify_sage.py enplaylist "origami | amo a mi esposo"
"""
import os
import re
import sys
import time
import difflib
import functools
import subprocess
import unicodedata

from dotenv import load_dotenv

try:
    import spotipy
    from spotipy.oauth2 import SpotifyOAuth
    from spotipy.cache_handler import CacheFileHandler
except ImportError:   # el módulo se puede importar sin spotipy; el error sale al usarlo, con instrucciones
    spotipy = None

AQUI = os.path.dirname(os.path.abspath(__file__))
RUTA_CACHE = os.path.join(AQUI, ".spotify_cache")
SCOPES = ("user-modify-playback-state user-read-playback-state playlist-read-private "
          "playlist-read-collaborative user-library-read")


class ErrorSpotify(Exception):
    """Mensaje pensado para mostrarse tal cual a Niko."""


class SinControlVolumen(ErrorSpotify):
    """El dispositivo (algunos celulares, altavoces, TV) no deja que Spotify cambie su volumen."""


# ---------------------------------------------------------------- autenticación (sin navegador por sorpresa)
def _auth(interactivo=False):
    if spotipy is None:
        raise ErrorSpotify("Falta la librería de Spotify. En la terminal: pip install spotipy")
    load_dotenv(os.path.join(AQUI, ".env"), override=True)
    cid, secreto = os.getenv("SPOTIPY_CLIENT_ID"), os.getenv("SPOTIPY_CLIENT_SECRET")
    if not cid or not secreto:
        raise ErrorSpotify("Faltan SPOTIPY_CLIENT_ID y SPOTIPY_CLIENT_SECRET en el .env")

    class _SinNavegador(SpotifyOAuth):
        def get_auth_response(self, *a, **k):   # spotipy abriría el navegador o pediría texto en la terminal: aquí no
            raise ErrorSpotify("SAGE necesita permiso de Spotify (una sola vez). En la terminal: python spotify_sage.py autorizar")

    clase = SpotifyOAuth if interactivo else _SinNavegador
    return clase(client_id=cid, client_secret=secreto,
                 redirect_uri=os.getenv("SPOTIPY_REDIRECT_URI", "http://127.0.0.1:8888/callback"),
                 scope=SCOPES, cache_handler=CacheFileHandler(cache_path=RUTA_CACHE), open_browser=interactivo)


def cliente():
    """Cliente listo para usar. Si falta autorizar (o faltan permisos nuevos) lanza ErrorSpotify en vez de abrir nada."""
    auth = _auth(False)
    try:
        token = auth.validate_token(auth.cache_handler.get_cached_token())
    except ErrorSpotify:
        raise
    except Exception:
        token = None
    if not token:
        raise ErrorSpotify("SAGE necesita permiso de Spotify (una sola vez, incluye leer tus playlists). "
                           "En la terminal: python spotify_sage.py autorizar")
    return spotipy.Spotify(auth_manager=auth)


def autorizar():
    """Autoriza a SAGE (abre el navegador UNA vez). ?salo desde la terminal, no desde la voz.
    Si el permiso guardado fue revocado (invalid_grant), borra el archivo de permisos y vuelve a pedirlo desde cero."""
    me = None
    for intento in (0, 1):
        auth = _auth(True)
        try:
            me = spotipy.Spotify(auth_manager=auth).current_user()
            break
        except Exception as e:
            revocado = "invalid_grant" in str(e).lower() or "revoked" in str(e).lower()
            if intento == 0 and revocado:
                print("El permiso guardado de Spotify ya no vale (fue revocado). Lo borro y te pido autorizar de nuevo...")
                try: os.remove(RUTA_CACHE)
                except OSError: pass
                continue
            raise
    return f"Autorizada con la cuenta <<{me.get('display_name') or me.get('id')}>>. Ya puedes pedirle playlists a SAGE."


def _traduce_errores(fn):
    @functools.wraps(fn)
    def envoltura(*a, **k):
        try:
            return fn(*a, **k)
        except ErrorSpotify:
            raise
        except Exception as e:
            if spotipy is not None and isinstance(e, spotipy.SpotifyException):
                razon = (getattr(e, "reason", None) or "").upper()
                texto = f"{getattr(e, 'msg', '')} {e}".lower()
                if "PREMIUM" in razon or "premium" in texto:
                    raise ErrorSpotify("Spotify solo deja que SAGE controle la reproducción con una cuenta Premium.") from e
                if e.http_status == 401:
                    raise ErrorSpotify("El permiso de Spotify caducó. En la terminal: python spotify_sage.py autorizar") from e
                if e.http_status == 429:
                    raise ErrorSpotify("Spotify limitó las peticiones por ahora (429). Prueba de nuevo en un minuto.") from e
                if e.http_status == 404:
                    raise ErrorSpotify("Spotify no encontró un reproductor activo. Abre Spotify en algún dispositivo e inténtalo otra vez.") from e
                if "VOLUME" in razon or "control device volume" in texto:
                    raise SinControlVolumen("Ese dispositivo no deja que Spotify controle su volumen (usa el del sistema o el del propio aparato).") from e
                if e.http_status == 403:
                    raise ErrorSpotify("Spotify rechazó la petición (403): faltan permisos o la cuenta no tiene acceso. "
                                       "Prueba: python spotify_sage.py autorizar") from e
                raise ErrorSpotify(f"Spotify respondió con un error ({e.http_status}): {getattr(e, 'msg', e)}") from e
            raise
    return envoltura


# ---------------------------------------------------------------- búsqueda por nombre aproximado
def _norm(texto):
    t = unicodedata.normalize("NFD", str(texto).lower())
    t = "".join(c for c in t if unicodedata.category(c) != "Mn")
    return re.sub(r"\s+", " ", re.sub(r"[^a-z0-9]+", " ", t)).strip()


_RUIDO = frozenset("playlist playlists lista listas de la el los las mi mis musica spotify en".split())


def _clave(texto):
    t = [w for w in _norm(texto).split() if w not in _RUIDO]
    return " ".join(t) or _norm(texto)


def puntaje(consulta, nombre):
    """0..1: qué tan bien encaja el nombre de una playlist con lo que pidió Niko."""
    a, b = _clave(consulta), _clave(nombre)
    if not a or not b:
        return 0.0
    ac, bc = a.replace(" ", ""), b.replace(" ", "")   # «lofi» ~ «Lo-Fi»
    if ac == bc:
        return 1.0
    if ac in bc or bc in ac:
        return 0.75 + 0.2 * min(len(ac), len(bc)) / max(len(ac), len(bc))
    ta, tb = set(a.split()), set(b.split())
    solape = len(ta & tb) / max(1, len(ta))
    return max(difflib.SequenceMatcher(None, a, b).ratio(), 0.8 * solape)


_RE_ENLACE = re.compile(r"(?:spotify:playlist:|open\.spotify\.com/(?:intl-[a-z]+/)?playlist/)([A-Za-z0-9]{10,})")
_RE_ME_GUSTA = re.compile(r"\b(me gustan?|favorit[ao]s?|liked|guardad[ao]s)\b")


def _mejor(consulta, items):
    puntuados = [(puntaje(consulta, p.get("name") or ""), p) for p in items if p and p.get("uri") and p.get("name")]
    return max(puntuados, key=lambda x: x[0]) if puntuados else (0.0, None)


def _mis_playlists(sp, tope=400):
    mias, res = [], sp.current_user_playlists(limit=50)
    while res and len(mias) < tope:
        mias += [p for p in (res.get("items") or []) if p]
        res = sp.next(res) if res.get("next") else None
    return mias


def _resolver_playlist(sp, consulta):
    """(uri, nombre, origen) de la playlist pedida: enlace > tus playlists > búsqueda en Spotify."""
    m = _RE_ENLACE.search(consulta)
    if m:
        return f"spotify:playlist:{m.group(1)}", "la playlist del enlace", "enlace"
    p, mejor = _mejor(consulta, _mis_playlists(sp))
    if mejor is not None and p >= 0.6:
        return mejor["uri"], mejor["name"], "tuya"
    res = sp.search(q=_clave(consulta) or consulta, type="playlist", limit=10)   # el máximo en modo desarrollo es 10
    p2, otro = _mejor(consulta, (res.get("playlists") or {}).get("items") or [])
    if otro is not None and p2 >= 0.3:
        dueno = (otro.get("owner") or {}).get("display_name") or ""
        return otro["uri"], otro["name"], ("de Spotify" if not dueno or dueno.lower() == "spotify" else f"encontrada en Spotify, de {dueno}")
    raise ErrorSpotify(f"No encontré ninguna playlist parecida a «{consulta}» ni entre las tuyas ni en Spotify.")


# ---------------------------------------------------------------- dispositivo (sin robar el foco)
def _abrir_spotify_minimizado():
    """Windows: lanza Spotify minimizado y SIN activarse, solo si no estaba abierto."""
    if sys.platform != "win32" or os.getenv("SAGE_SPOTIFY_ABRIR", "1").strip() == "0":
        return False
    exe = os.path.join(os.getenv("APPDATA", ""), "Spotify", "Spotify.exe")
    if not os.path.isfile(exe):
        return False
    try:
        info = subprocess.STARTUPINFO()
        info.dwFlags |= subprocess.STARTF_USESHOWWINDOW
        info.wShowWindow = 7   # SW_SHOWMINNOACTIVE: minimizada y sin quitarle el foco a lo que Niko está haciendo
        subprocess.Popen([exe, "--minimized"], startupinfo=info, close_fds=True)
        return True
    except Exception:
        return False


def _dispositivo(sp):
    devs = sp.devices().get("devices") or []
    if not devs and _abrir_spotify_minimizado():
        for _ in range(16):   # el reproductor tarda unos segundos en registrarse
            time.sleep(1.0)
            devs = sp.devices().get("devices") or []
            if devs:
                break
    if not devs:
        raise ErrorSpotify("No veo ningún reproductor de Spotify disponible. Abre Spotify (PC o celular) una vez y vuelve a pedírmelo.")
    pref = os.getenv("SAGE_SPOTIFY_DISPOSITIVO", "").strip().lower()
    if pref:
        for d in devs:
            if pref in (d.get("name") or "").lower():
                return d
    return (next((d for d in devs if d.get("is_active")), None)
            or next((d for d in devs if (d.get("type") or "").lower() == "computer"), None) or devs[0])


def _iniciar(sp, dev, **kw):
    try:
        sp.start_playback(device_id=dev["id"], **kw)
    except Exception as e:
        if spotipy is not None and isinstance(e, spotipy.SpotifyException) and e.http_status == 404:
            time.sleep(1.5)   # el dispositivo recién abierto aún no estaba listo
            sp.start_playback(device_id=dev["id"], **kw)
        else:
            raise


def _barajar(sp, dev, estado):
    if estado is None:
        return
    try:
        sp.shuffle(bool(estado), device_id=dev["id"])
    except Exception:
        pass


# ---------------------------------------------------------------- API pública
@_traduce_errores
def reproducir_playlist(consulta, aleatorio=None):
    """Reproduce una playlist por nombre aproximado, enlace/URI o «canciones que me gustan». aleatorio: True / False / None (no tocar)."""
    consulta = (consulta or "").strip()
    if not consulta:
        raise ErrorSpotify("No me dijiste qué playlist poner.")
    sp = cliente()
    if _RE_ME_GUSTA.search(_norm(consulta)) and len(_norm(consulta).split()) <= 5:
        uris = []
        for desde in (0, 50):
            pag = sp.current_user_saved_tracks(limit=50, offset=desde)
            uris += [i["track"]["uri"] for i in (pag.get("items") or []) if i.get("track") and i["track"].get("uri")]
        if not uris:
            raise ErrorSpotify("No encontré canciones guardadas en tus «Me gusta».")
        dev = _dispositivo(sp)
        _barajar(sp, dev, aleatorio)
        _iniciar(sp, dev, uris=uris[:100])
        return f"Reproduciendo tus canciones que te gustan en {dev.get('name', 'Spotify')}."
    uri, nombre, origen = _resolver_playlist(sp, consulta)
    dev = _dispositivo(sp)
    _barajar(sp, dev, aleatorio)
    _iniciar(sp, dev, context_uri=uri)
    _barajar(sp, dev, aleatorio)
    modo = " en aleatorio" if aleatorio else (" en orden" if aleatorio is False else "")
    return f"Reproduciendo la playlist «{nombre}» ({origen}){modo} en {dev.get('name', 'Spotify')}."


@_traduce_errores
def reproducir_cancion(consulta):
    consulta = (consulta or "").strip()
    if not consulta:
        raise ErrorSpotify("No me dijiste qué canción poner.")
    sp = cliente()
    pistas = (sp.search(q=consulta, limit=5, type="track").get("tracks") or {}).get("items") or []
    pistas = [t for t in pistas if t and t.get("uri")]
    if not pistas:
        raise ErrorSpotify(f"No encontré la canción «{consulta}».")
    t = pistas[0]
    dev = _dispositivo(sp)
    _iniciar(sp, dev, uris=[t["uri"]])
    artista = ((t.get("artists") or [{}])[0]).get("name", "")
    return f"Reproduciendo «{t.get('name')}»{f' de {artista}' if artista else ''} en {dev.get('name', 'Spotify')}."


@_traduce_errores
def listar_playlists():
    return [p["name"] for p in _mis_playlists(cliente()) if p.get("name")]


@_traduce_errores
def listar_dispositivos():
    return [(d.get("name"), d.get("type"), bool(d.get("is_active"))) for d in cliente().devices().get("devices") or []]


# ---------------------------------------------------------------- volumen
def _elegir_dispositivo(devs):
    pref = os.getenv("SAGE_SPOTIFY_DISPOSITIVO", "").strip().lower()
    if pref:
        for d in devs:
            if pref in (d.get("name") or "").lower():
                return d
    return (next((d for d in devs if d.get("is_active")), None)
            or next((d for d in devs if (d.get("type") or "").lower() == "computer"), None) or devs[0])


def _interpretar_volumen(orden, actual):
    """«subir», «bajar 20», «un poco más bajo», «40», «al máximo», «silenciar» -> volumen final 0..100."""
    t = _norm(orden)
    m = re.search(r"\d{1,3}", t)
    n = int(m.group()) if m else None
    if re.search(r"\bsilenc|\bmute|sin sonido|\bmutea", t):
        return 0
    if re.search(r"\bmaxim|\bmax\b|a tope|al tope|al 100", t):
        return 100
    if re.search(r"\bminim|\bmin\b", t):
        return 5
    if re.search(r"\bmitad\b", t):
        return 50
    baja = re.search(r"\b(?:baj|disminu|reduc|menos|down)", t)
    sube = re.search(r"\b(?:sub|aument|mas|alz|up)", t)
    if baja or sube:
        paso = n if n is not None else (5 if re.search(r"poco|poquito|ligeramente|tantito", t) else 25 if re.search(r"mucho|bastante", t) else 10)
        return actual + (-paso if baja else paso)
    if n is not None:
        return n   # «pon el volumen a 30»: valor absoluto
    raise ErrorSpotify("No entendí qué hacer con el volumen: dime «sube», «baja», un número (por ejemplo 40) o «silencia».")


@_traduce_errores
def cambiar_volumen(orden):
    """Sube/baja/pone el volumen de Spotify en el dispositivo que está sonando (por la API, sin tocar nada visible)."""
    sp = cliente()
    devs = sp.devices().get("devices") or []
    if not devs:
        raise ErrorSpotify("No veo ningún reproductor de Spotify abierto. Abre Spotify (PC o celular) y vuelve a pedírmelo.")
    dev = _elegir_dispositivo(devs)
    actual = dev.get("volume_percent")
    antes = 50 if actual is None else int(actual)
    nuevo = max(0, min(100, int(_interpretar_volumen(orden, antes))))
    nombre = dev.get("name", "Spotify")
    if actual is not None and nuevo == antes:
        return f"El volumen de Spotify en {nombre} ya está en {antes}%."
    sp.volume(nuevo, device_id=dev["id"])
    return f"Volumen de Spotify en {nombre}: {'?' if actual is None else f'{antes}%'} → {nuevo}%."


# ---------------------------------------------------------------- una canción EXACTA de una playlist
_RE_SUFIJO = re.compile(r"\s*[\(\[].*?[\)\]]|\s+-\s+.*$")
_RUIDO_CANCION = frozenset("de del la el los las cancion tema pista musica".split())


def _titulo_base(nombre):
    return _RE_SUFIJO.sub("", nombre).strip() or nombre


def puntaje_cancion(consulta, nombre, artistas=()):
    """0..1: qué tan bien encaja una canción con lo que pidió Niko (título, con o sin artista; tolera «- Remastered», «(feat. ...)»)."""
    q = _norm(consulta)
    if not q:
        return 0.0
    completo, base = _norm(nombre), _norm(_titulo_base(nombre))
    if q in (completo, base):
        return 1.0
    palabras = [w for w in q.split() if w not in _RUIDO_CANCION]
    disponibles = set(base.split()) | set(completo.split()) | set(_norm(" ".join(artistas)).split())
    if palabras and all(w in disponibles for w in palabras):
        return 0.85 + 0.1 * (len(palabras) / max(1, len(base.split())) if len(palabras) <= len(base.split()) else 0)
    return max(difflib.SequenceMatcher(None, q, base).ratio(), 0.9 * puntaje(consulta, nombre))


def _pistas_de_playlist(sp, pid, tope=1000):
    """[(uri, nombre, [artistas])]. Prueba el endpoint clásico y el nuevo /items (Spotify lo está renombrando)."""
    pistas, offset = [], 0
    while offset < tope:
        try:
            pag = sp.playlist_items(pid, limit=100, offset=offset, additional_types=("track",))
        except Exception as e1:
            if spotipy is not None and isinstance(e1, spotipy.SpotifyException) and e1.http_status in (400, 403, 404):
                try:
                    pag = sp._get(f"playlists/{pid}/items", limit=100, offset=offset)
                except Exception:
                    raise e1
            else:
                raise
        items = pag.get("items") or []
        for it in items:
            t = it.get("track") or it.get("item") or {}
            if t.get("uri") and not t.get("is_local") and t.get("type", "track") == "track":
                pistas.append((t["uri"], t.get("name") or "", [a.get("name", "") for a in t.get("artists") or []]))
        if not pag.get("next") or not items:
            break
        offset += 100
    return pistas


def _mejor_cancion(consulta, pistas):
    """(puntaje, índice) de la mejor coincidencia y lista de parecidas por si no llega al mínimo."""
    puntuadas = sorted(((puntaje_cancion(consulta, n, a), i) for i, (_, n, a) in enumerate(pistas)), key=lambda x: (-x[0], x[1]))
    return puntuadas


@_traduce_errores
def reproducir_cancion_de_playlist(cancion, playlist):
    """Reproduce UNA canción concreta de una playlist (por nombre aproximado de ambas) y la playlist sigue después de ella."""
    cancion, playlist = (cancion or "").strip(), (playlist or "").strip()
    if not cancion or not playlist:
        raise ErrorSpotify("Necesito el nombre de la canción y el de la playlist.")
    sp = cliente()

    me_gusta = bool(_RE_ME_GUSTA.search(_norm(playlist))) and len(_norm(playlist).split()) <= 5
    if me_gusta:
        uri, nombre_pl, origen = None, "tus canciones que te gustan", "tuya"
        pistas = []
        for desde in range(0, 500, 50):
            pag = sp.current_user_saved_tracks(limit=50, offset=desde)
            for i in pag.get("items") or []:
                t = i.get("track") or {}
                if t.get("uri"):
                    pistas.append((t["uri"], t.get("name") or "", [a.get("name", "") for a in t.get("artists") or []]))
            if not pag.get("next"):
                break
    else:
        uri, nombre_pl, origen = _resolver_playlist(sp, playlist)
        try:
            pistas = _pistas_de_playlist(sp, uri.split(":")[-1])
        except Exception as e:
            # Spotify no deja leer esa playlist con esta app: se avisa con claridad y se reproduce la canción suelta
            res = sp.search(q=cancion, type="track", limit=5)
            sueltas = [t for t in (res.get("tracks") or {}).get("items") or [] if t and t.get("uri")]
            if not sueltas:
                raise ErrorSpotify(f"No pude leer las canciones de «{nombre_pl}» ({e}) ni encontré «{cancion}» por su cuenta.")
            t = sueltas[0]
            dev = _dispositivo(sp)
            _iniciar(sp, dev, uris=[t["uri"]])
            artista = ((t.get("artists") or [{}])[0]).get("name", "")
            return (f"No pude leer las canciones de «{nombre_pl}» (Spotify no me deja con esta app), así que puse «{t.get('name')}»"
                    f"{f' de {artista}' if artista else ''} suelta, SIN confirmar que esté en esa playlist.")

    if not pistas:
        raise ErrorSpotify(f"La playlist «{nombre_pl}» no tiene canciones que yo pueda reproducir.")
    ranking = _mejor_cancion(cancion, pistas)
    mejor, idx = ranking[0]
    if mejor < 0.6:
        parecidas = [f"«{pistas[i][1]}»" for p, i in ranking[:3] if p >= 0.3]
        raise ErrorSpotify(f"No encontré «{cancion}» en la playlist «{nombre_pl}»."
                           + (f" Lo más parecido es: {', '.join(parecidas)}." if parecidas else ""))

    uri_pista, titulo, artistas = pistas[idx]
    dev = _dispositivo(sp)
    if me_gusta:
        _iniciar(sp, dev, uris=[p[0] for p in pistas[idx:idx + 100]])
    else:
        _iniciar(sp, dev, context_uri=uri, offset={"uri": uri_pista})
    quien = f" de {artistas[0]}" if artistas else ""
    return f"Reproduciendo «{titulo}»{quien} de la playlist «{nombre_pl}» ({origen}) en {dev.get('name', 'Spotify')}; después sigue el resto de la playlist."


# ---------------------------------------------------------------- línea de comandos
def _cli(argv):
    cmd = argv[1].lower() if len(argv) > 1 else "ayuda"
    try:
        if cmd == "autorizar":
            print(autorizar())
        elif cmd == "playlists":
            nombres = listar_playlists()
            print("\n".join(f"- {n}" for n in nombres) or "No tienes playlists.")
        elif cmd == "dispositivos":
            for n, t, a in listar_dispositivos():
                print(f"- {n} ({t}){'  <- activo' if a else ''}")
        elif cmd == "playlist" and len(argv) > 2:
            resto = argv[2:]
            alea = {"aleatorio": True, "orden": False}.get(resto[-1].lower()) if len(resto) > 1 else None
            print(reproducir_playlist(" ".join(resto[:-1] if alea is not None else resto), alea))
        elif cmd == "cancion" and len(argv) > 2:
            print(reproducir_cancion(" ".join(argv[2:])))
        elif cmd == "volumen" and len(argv) > 2:
            print(cambiar_volumen(" ".join(argv[2:])))
        elif cmd == "enplaylist" and len(argv) > 2 and "|" in " ".join(argv[2:]):
            c, _, p = " ".join(argv[2:]).partition("|")
            print(reproducir_cancion_de_playlist(c, p))
        else:
            print(__doc__)
    except ErrorSpotify as e:
        print(f"✖ {e}")
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(_cli(sys.argv))
