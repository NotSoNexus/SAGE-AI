"""Detección automática de Outcome Memories (Roblox) SIN mirar la pantalla y SIN gastar el modelo.

Cómo: el cliente de Roblox escribe en sus registros (%LOCALAPPDATA%\\Roblox\\logs) el «placeId» del juego al que te unes. SAGE solo lee
ese NÚMERO (nada de chats ni datos personales) y lo compara con el de Outcome Memories. También reconoce el título de la ventana.

  esta_jugando_outcome(titulo="") -> True (lo estás jugando) / False (Roblox cerrado u otro juego) / None (no se puede saber)

Prueba rápida:  python outcome_deteccion.py     (dice qué ve en tus registros de Roblox)
Ajustes opcionales en .env: SAGE_OUTCOME_ID=14608970270,otroPlaceId (más ids del juego si Outcome tuviera varios lugares)
"""
import glob
import os
import re
import time

ID_OUTCOME = "14608970270"       # roblox.com/games/14608970270
_FRESCO = 150.0                  # s: si el registro no se ha tocado en este tiempo, Roblox está cerrado
_CACHE_S = 6.0                   # el resultado se reutiliza unos segundos (la lectura es barata, pero se llama seguido)
_RE_LUGAR = re.compile(r"place[\s_]?id\W{0,4}(\d{6,})|\bplace\s+(\d{6,})\b", re.IGNORECASE)

_estado = {"ruta": None, "pos": 0, "lugar": None}
_cache = {"t": -1e9, "val": None}


def _ids():
    extra = {x.strip() for x in os.getenv("SAGE_OUTCOME_ID", "").split(",") if x.strip().isdigit()}
    return {ID_OUTCOME} | extra


def _carpetas():
    base = os.getenv("LOCALAPPDATA", "")
    if not base:
        return []
    c = [os.path.join(base, "Roblox", "logs")]
    c += glob.glob(os.path.join(base, "Packages", "ROBLOXCORPORATION.ROBLOX_*", "LocalState", "logs"))   # versión de Microsoft Store
    return [x for x in c if os.path.isdir(x)]


def _log_mas_nuevo():
    mejor, mt = None, 0.0
    for d in _carpetas():
        for r in glob.glob(os.path.join(d, "*.log")):
            try:
                t = os.path.getmtime(r)
            except OSError:
                continue
            if t > mt:
                mejor, mt = r, t
    return (mejor, time.time() - mt) if mejor else (None, None)


def lugar_actual():
    """(placeId del último juego al que se unió Roblox | None, antigüedad en s del registro | None)."""
    ruta, edad = _log_mas_nuevo()
    if ruta is None or edad > _FRESCO:
        return None, edad
    try:
        tam = os.path.getsize(ruta)
        if _estado["ruta"] != ruta or tam < _estado["pos"]:
            _estado.update(ruta=ruta, pos=0, lugar=None)        # archivo nuevo (otra sesión): se lee desde el principio
        with open(ruta, "rb") as f:
            f.seek(_estado["pos"])
            datos = f.read(8_000_000)
        _estado["pos"] += len(datos)
        for m in _RE_LUGAR.finditer(datos.decode("utf-8", "ignore")):
            _estado["lugar"] = m.group(1) or m.group(2)
    except OSError:
        return None, edad
    return _estado["lugar"], edad


def esta_jugando_outcome(titulo=""):
    """True: lo estás jugando · False: Roblox cerrado o en otro juego · None: no hay registros que lo digan."""
    if "outcome memories" in (titulo or "").lower():
        return True
    ahora = time.monotonic()
    if ahora - _cache["t"] < _CACHE_S:
        return _cache["val"]
    try:
        lugar, edad = lugar_actual()
        if edad is None:
            val = None                      # no hay registros de Roblox (no instalado / otro sistema)
        elif lugar is None:
            val = False if edad > _FRESCO else None   # cerrado, o abierto pero aún sin juego identificado
        else:
            val = lugar in _ids()
    except Exception:
        val = None
    _cache.update(t=ahora, val=val)
    return val


if __name__ == "__main__":
    lugar, edad = lugar_actual()
    print("Carpetas de registros de Roblox:", _carpetas() or "ninguna")
    if edad is None:
        print("No hay registros de Roblox.")
    else:
        print(f"Registro más reciente: hace {edad:.0f} s ({'Roblox abierto' if edad <= _FRESCO else 'Roblox cerrado'})")
        print("placeId del último juego:", lugar or "(no encontrado)")
    print("¿Estás jugando Outcome Memories?", {True: "SÍ", False: "NO", None: "no se puede saber"}[esta_jugando_outcome()])
