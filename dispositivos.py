"""Dispositivos que SAGE puede VER por Wi-Fi. Solo los que tú registras en sage_dispositivos.json.

Hoy: celulares / tablets / TV Android por «Depuración inalámbrica» (adb). SAGE saca una captura de su pantalla cuando
le dices algo como «mira mi celular», «qué tengo en el celular» o «sácame una captura de mi celular», y la analiza.
Solo LEE la pantalla (no toca ni escribe nada en el dispositivo). Las capturas se guardan en capturas_dispositivos/
(SAGE_GUARDAR_CAPTURAS=0 para no guardarlas).

Configuración (una sola vez), desde la carpeta de SAGE:
    python dispositivos.py ayuda
"""
import io
import os
import re
import sys
import json
import time
import atexit
import shlex
import shutil
import tempfile
import socket
import base64
import subprocess
import unicodedata

AQUI = os.path.dirname(os.path.abspath(__file__))
RUTA_CONFIG = os.path.join(AQUI, "sage_dispositivos.json")
DIR_CAPTURAS = os.path.join(AQUI, "capturas_dispositivos")
_PNG = b"\x89PNG\r\n\x1a\n"

AYUDA = """\
CÓMO ENLAZAR TU CELULAR ANDROID (una sola vez; PC y celular en la MISMA Wi-Fi)

1. En la PC: baja «SDK Platform-Tools» de Google (developer.android.com/tools/releases/platform-tools), descomprímelo y deja
   la carpeta «platform-tools» junto a app.py (o añade adb al PATH, o pon SAGE_ADB=C:\\ruta\\adb.exe en .env).
2. En el celular: Ajustes > Acerca del teléfono > toca 7 veces «Número de compilación». Luego Ajustes > Sistema >
   Opciones de desarrollador > activa «Depuración inalámbrica».
3. Emparejar: en «Depuración inalámbrica» pulsa «Vincular dispositivo con código de vinculación». Verás una IP:PUERTO y un código:
       python dispositivos.py emparejar IP:PUERTO CODIGO
4. Registrar: en la pantalla principal de «Depuración inalámbrica» aparece «Dirección IP y puerto» (otro puerto):
       python dispositivos.py agregar celular IP:PUERTO
   (El puerto cambia cada vez que reactivas la depuración o reinicias el celular. Usa «auto» en vez de IP:PUERTO
    y SAGE intentará encontrarlo sola:  python dispositivos.py agregar celular auto)
5. Probar:  python dispositivos.py capturar celular     y luego, a SAGE: «mira mi celular».

Si la vinculación falla, usa el cable UNA vez:  python dispositivos.py usb celular   (sin vinculación)
Si no conecta:  python dispositivos.py diagnostico   (te dice qué falla y cómo arreglarlo)

Otros comandos:  listar | conectar NOMBRE | quitar NOMBRE | alias NOMBRE palabra1,palabra2
"""


class ErrorDispositivo(Exception):
    """Mensaje pensado para mostrarse tal cual a Niko."""


# ---------------------------------------------------------------- configuración
def _norm(texto):
    t = unicodedata.normalize("NFD", str(texto).lower())
    return "".join(c for c in t if unicodedata.category(c) != "Mn")


def _leer():
    try:
        with open(RUTA_CONFIG, encoding="utf-8") as f:
            d = json.load(f)
        return d.get("dispositivos", {}) if isinstance(d, dict) else {}
    except Exception:
        return {}


def _escribir(dispositivos):
    with open(RUTA_CONFIG, "w", encoding="utf-8") as f:
        json.dump({"dispositivos": dispositivos}, f, ensure_ascii=False, indent=2)


def listar():
    """{nombre: {tipo, direccion, alias}} de los dispositivos registrados."""
    return _leer()


def registrar(nombre, direccion="auto", tipo="android", alias=None):
    d = _leer()
    previo = d.get(nombre, {})
    d[nombre] = {"tipo": tipo, "direccion": direccion, "alias": alias if alias is not None else previo.get("alias", [])}
    _escribir(d)


def quitar(nombre):
    d = _leer()
    if nombre not in d: return False
    del d[nombre]
    _escribir(d)
    return True


# ---------------------------------------------------------------- adb
def _buscar_adb():
    candidatos = [
        os.getenv("SAGE_ADB", ""), shutil.which("adb") or "",
        os.path.join(AQUI, "platform-tools", "adb.exe"), os.path.join(AQUI, "platform-tools", "adb"),
        os.path.join(os.getenv("LOCALAPPDATA", ""), "Android", "Sdk", "platform-tools", "adb.exe"),
    ]
    for c in candidatos:
        if c and os.path.isfile(c):
            return c
    raise ErrorDispositivo("No encuentro adb. Baja «SDK Platform-Tools» de Google y deja la carpeta platform-tools junto a app.py "
                           "(o pon SAGE_ADB=<ruta de adb> en .env). Pasos completos: python dispositivos.py ayuda")


def _adb(*args, timeout=15):
    cmd = [_buscar_adb(), *args]
    extra = {"creationflags": subprocess.CREATE_NO_WINDOW} if sys.platform == "win32" else {}
    env = dict(os.environ)
    env.setdefault("ADB_MDNS_OPENSCREEN", "1")  # descubrimiento mDNS integrado: «auto» funciona sin tener Bonjour instalado
    try:
        r = subprocess.run(cmd, capture_output=True, timeout=timeout, env=env, **extra)
    except subprocess.TimeoutExpired:
        raise ErrorDispositivo("adb tardó demasiado en responder. ¿El celular está en la misma Wi-Fi, con la pantalla encendida y la "
                               "depuración inalámbrica activada?")
    return r.returncode, r.stdout or b"", (r.stderr or b"").decode("utf-8", "replace")


def _txt(b):
    return (b or b"").decode("utf-8", "replace").strip()


def _conectados():
    """[(serial, estado)] según «adb devices»."""
    _, out, _ = _adb("devices", timeout=10)
    res = []
    for linea in _txt(out).splitlines()[1:]:
        partes = linea.split()
        if len(partes) >= 2: res.append((partes[0], partes[1]))
    return res


def _mdns():
    """IP:PUERTO de dispositivos que anuncian depuración inalámbrica en la red (adb mdns)."""
    try:
        _, out, _ = _adb("mdns", "services", timeout=8)
    except ErrorDispositivo:
        return []
    return [m.group(1) for l in _txt(out).splitlines() if "_adb-tls-connect" in l
            for m in [re.search(r"(\d{1,3}(?:\.\d{1,3}){3}:\d+)", l)] if m]


def _serial(dev):
    """Conecta con el dispositivo y devuelve el serial para «adb -s».
    Si la IP:PUERTO guardada ya no sirve (el puerto cambia al reactivar la depuración), lo busca solo por mDNS."""
    d = (dev.get("direccion") or "auto").strip()
    fallo = ""
    if d.lower() != "auto":
        _, out, err = _adb("connect", d, timeout=10)
        msg = (_txt(out) + " " + err).lower()
        if "connected to" in msg or "already connected" in msg:
            return d
        fallo = (_txt(out) or err).strip() or "sin respuesta"

    conectados = _conectados()
    for serial, estado in conectados:  # conexiones muertas de puertos anteriores: se cierran para que no estorben
        if estado == "offline":
            _adb("disconnect", serial, timeout=8)
    listos = [s for s, e in _conectados() if e == "device"]
    if not listos:
        for addr in _mdns():
            _, out, err = _adb("connect", addr, timeout=10)
            fallo = fallo or (_txt(out) or err.strip())
        conectados = _conectados()
        listos = [s for s, e in conectados if e == "device"]
        if not listos and any(e == "unauthorized" for _, e in conectados):
            raise ErrorDispositivo("El celular aún no autorizó esta PC: acepta el aviso «¿Permitir la depuración inalámbrica?» en su pantalla.")
    if listos:
        return listos[0]
    if fallo:
        raise ErrorDispositivo(f"No pude conectar con {d}: {fallo}. Casi siempre es que el puerto cambió o que falta emparejar. "
                               "Prueba: python dispositivos.py diagnostico")
    raise ErrorDispositivo("No veo ningún celular por Wi-Fi. Activa «Depuración inalámbrica» en el celular (misma red que la PC), "
                           "emparéjalo una vez y corre: python dispositivos.py diagnostico")


def configurar_usb(nombre):
    """Plan B sin vinculación: con el celular por USB una vez, lo pasa a modo Wi-Fi (puerto 5555) y lo registra.
    Dura hasta que se reinicie el celular; entonces repites este comando con el cable."""
    usb = [s for s, e in _conectados() if e == "device" and ":" not in s and "._adb" not in s]
    if not usb:
        raise ErrorDispositivo("No veo el celular por USB. Conéctalo con cable, activa «Depuración USB» en Opciones de desarrollador "
                               "y acepta en su pantalla el aviso «¿Permitir la depuración USB?» (marca «Permitir siempre»).")
    serial = usb[0]
    _, out, _ = _adb("-s", serial, "shell", "ip", "-f", "inet", "addr", "show", "wlan0", timeout=10)
    m = re.search(r"inet (\d{1,3}(?:\.\d{1,3}){3})", _txt(out))
    if not m:
        raise ErrorDispositivo("No pude leer la IP Wi-Fi del celular. ¿Está conectado a la misma Wi-Fi que la PC?")
    ip = m.group(1)
    _adb("-s", serial, "tcpip", "5555", timeout=10)
    time.sleep(2.5)
    _, out, err = _adb("connect", f"{ip}:5555", timeout=10)
    msg = (_txt(out) + " " + err).lower()
    if "connected to" not in msg and "already connected" not in msg:
        raise ErrorDispositivo(f"El celular pasó a modo Wi-Fi pero no pude conectar con {ip}:5555: {(_txt(out) or err).strip()}")
    registrar(nombre, f"{ip}:5555")
    return f"{ip}:5555"


def diagnostico():
    """Revisa paso a paso por qué no conecta y dice qué arreglar. Devuelve el texto."""
    L = []
    try:
        adb = _buscar_adb()
        L.append(f"✔ adb encontrado: {adb}")
    except ErrorDispositivo as e:
        return f"✖ {e}"
    try:
        _, out, _ = _adb("version", timeout=10)
        L.append("  " + _txt(out).splitlines()[0])
        _adb("start-server", timeout=20)
    except ErrorDispositivo as e:
        return "\n".join(L + [f"✖ {e}"])

    conectados = _conectados()
    L.append(f"• Dispositivos que adb ve ahora: {conectados or 'ninguno'}")
    for serial, estado in conectados:
        if estado == "unauthorized": L.append("  ✖ «unauthorized»: acepta el aviso de depuración en la pantalla del celular.")
        if estado == "offline": L.append("  ✖ «offline»: apaga y enciende «Depuración inalámbrica» en el celular y vuelve a correr esto.")

    _, out, err = _adb("mdns", "check", timeout=10)
    L.append(f"• mDNS: {(_txt(out) or err.strip() or '(sin respuesta)').splitlines()[0]}")
    servicios = _mdns()
    L.append(f"• Celulares anunciándose por mDNS: {servicios or 'ninguno'}")
    if not servicios:
        L.append("  (Si el celular está con la depuración activa y aquí sale «ninguno», tu router bloquea el descubrimiento: "
                 "usa IP:PUERTO fija, y revisa que no sea una red de invitados / con «aislamiento de clientes».)")

    # Limpieza y prueba real de conexión
    for serial, estado in conectados:
        if estado == "offline":
            _adb("disconnect", serial, timeout=8)
            L.append(f"• Cerré la conexión muerta {serial}")
    for addr in servicios:
        _, out, err = _adb("connect", addr, timeout=10)
        L.append(f"• Intento de conexión a {addr}: {(_txt(out) or err.strip() or '(sin respuesta)')}")
    despues = _conectados()
    L.append(f"• Estado final: {despues or 'ninguno'}")
    if any(e == "device" for _, e in despues):
        L.append("  ✔ Conectado. Prueba: python dispositivos.py capturar celular")
    elif any(e == "unauthorized" for _, e in despues):
        L.append("  ✖ Mira la pantalla del celular: acepta «¿Permitir la depuración inalámbrica?» (marca «Permitir siempre»).")
    else:
        L.append("  ✖ Sigue sin conectar. Si arriba dice «failed to authenticate» o «protocol fault», falta EMPAREJAR (o hay que reemparejar): "
                 "en el celular, Depuración inalámbrica > «Vincular dispositivo con código de vinculación» y corre "
                 "python dispositivos.py emparejar IP:PUERTO CODIGO (ese puerto es otro, solo vale mientras el diálogo está abierto).")

    registrados = _leer()
    if not registrados:
        L.append("✖ No hay dispositivos registrados: python dispositivos.py agregar celular auto")
    for nombre, dev in registrados.items():
        d = (dev.get("direccion") or "auto").strip()
        L.append(f"• «{nombre}» registrado con dirección: {d}")
        if d.lower() == "auto":
            continue
        try:
            ip, puerto = d.rsplit(":", 1)
            with socket.create_connection((ip, int(puerto)), timeout=4):
                L.append(f"  ✔ {d} responde en la red.")
        except Exception as e:
            L.append(f"  ✖ {d} NO responde ({e}). Causas típicas: el puerto cambió (míralo otra vez en Depuración inalámbrica, "
                     "o usa «auto»), la pantalla del celular está apagada, o PC y celular no están en la misma red.")
            if servicios:
                L.append(f"  → Pero el celular sí se anuncia en: {', '.join(servicios)}. Con «auto» SAGE lo usará solo: "
                         f"python dispositivos.py agregar {nombre} auto")
    L.append("• Recuerda: el puerto de «Vincular con código» (solo para emparejar) NO es el de «Dirección IP y puerto» (para conectar).")
    return "\n".join(L)


# ---------------------------------------------------------------- captura
def capturar(nombre, guardar=True):
    """Captura la pantalla del dispositivo registrado. Devuelve (imagen PIL, ruta_guardada o ''). Lanza ErrorDispositivo."""
    dev = _leer().get(nombre)
    if dev is None:
        raise ErrorDispositivo(f"No tengo registrado ningún dispositivo llamado «{nombre}».")
    if dev.get("tipo", "android") != "android":
        raise ErrorDispositivo(f"El tipo de dispositivo «{dev.get('tipo')}» todavía no está soportado (solo Android).")

    serial = _sesion(nombre, dev)
    _, out, err = _adb("-s", serial, "exec-out", "screencap", "-p", timeout=25)
    if not out.startswith(_PNG):
        e = (err + " " + _txt(out)).lower()
        if "unauthorized" in e:
            raise ErrorDispositivo("El celular no autorizó esta PC: acepta el aviso «¿Permitir la depuración inalámbrica?» en su pantalla.")
        if "offline" in e or "not found" in e or "no devices" in e or "closed" in e:
            raise ErrorDispositivo("El celular se desconectó. Revisa que siga en la misma Wi-Fi y con la depuración inalámbrica activa.")
        raise ErrorDispositivo(f"adb no devolvió una captura válida: {(err or _txt(out))[:200] or 'respuesta vacía'}")

    from PIL import Image
    img = Image.open(io.BytesIO(out))
    img.load()
    if img.convert("L").getextrema()[1] < 6:
        raise ErrorDispositivo("La captura salió completamente negra: la pantalla del celular está apagada o bloqueada, o la app que muestra "
                               "protege su contenido. Enciéndelo y vuelve a pedirlo.")
    ruta = ""
    if guardar and os.getenv("SAGE_GUARDAR_CAPTURAS", "1").strip() != "0":
        try:
            os.makedirs(DIR_CAPTURAS, exist_ok=True)
            ruta = os.path.join(DIR_CAPTURAS, f"{re.sub(r'[^A-Za-z0-9_-]+', '_', nombre)}_{time.strftime('%Y%m%d_%H%M%S')}.png")
            with open(ruta, "wb") as f:
                f.write(out)
        except Exception as ex:
            print(f"[Dispositivos] No pude guardar la captura: {ex}")
            ruta = ""
    return img, ruta



# ---------------------------------------------------------------- control del celular (adb input)
_serial_cache = {}
_tam_cache = {}

_APPS = {
    "whatsapp": "com.whatsapp", "youtube": "com.google.android.youtube", "instagram": "com.instagram.android",
    "tiktok": "com.zhiliaoapp.musically", "spotify": "com.spotify.music", "chrome": "com.android.chrome",
    "telegram": "org.telegram.messenger", "discord": "com.discord", "facebook": "com.facebook.katana",
    "messenger": "com.facebook.orca", "twitter": "com.twitter.android", "x": "com.twitter.android",
    "netflix": "com.netflix.mediaclient", "maps": "com.google.android.apps.maps", "mapas": "com.google.android.apps.maps",
    "gmail": "com.google.android.gm", "play store": "com.android.vending", "tienda": "com.android.vending",
    "snapchat": "com.snapchat.android", "reddit": "com.reddit.frontpage", "twitch": "tv.twitch.android.app",
    "drive": "com.google.android.apps.docs", "fotos": "com.google.android.apps.photos", "google": "com.google.android.googlequicksearchbox",
    "calendario": "com.google.android.calendar", "reloj": "com.google.android.deskclock", "pinterest": "com.pinterest",
    "steam": "com.valvesoftware.android.steam.community", "roblox": "com.roblox.client", "minecraft": "com.mojang.minecraftpe",
}
_INTENTS = {  # nombre -> (acción, extra)
    "ajustes": "android.settings.SETTINGS", "configuracion": "android.settings.SETTINGS", "settings": "android.settings.SETTINGS",
    "wifi": "android.settings.WIFI_SETTINGS", "bluetooth": "android.settings.BLUETOOTH_SETTINGS",
    "camara": "android.media.action.STILL_IMAGE_CAMERA", "telefono": "android.intent.action.DIAL", "marcador": "android.intent.action.DIAL",
}
_TECLAS = {
    "atras": "KEYCODE_BACK", "volver": "KEYCODE_BACK", "inicio": "KEYCODE_HOME", "home": "KEYCODE_HOME",
    "recientes": "KEYCODE_APP_SWITCH", "enter": "KEYCODE_ENTER", "buscar": "KEYCODE_SEARCH", "borrar": "KEYCODE_DEL",
    "volumen_subir": "KEYCODE_VOLUME_UP", "subir_volumen": "KEYCODE_VOLUME_UP", "volumen_bajar": "KEYCODE_VOLUME_DOWN",
    "bajar_volumen": "KEYCODE_VOLUME_DOWN", "silencio": "KEYCODE_VOLUME_MUTE", "bloquear": "KEYCODE_SLEEP",
    "pausa": "KEYCODE_MEDIA_PLAY_PAUSE", "play": "KEYCODE_MEDIA_PLAY_PAUSE", "siguiente": "KEYCODE_MEDIA_NEXT",
    "anterior": "KEYCODE_MEDIA_PREVIOUS", "tab": "KEYCODE_TAB", "esc": "KEYCODE_ESCAPE",
}
_TECLAS_CMD = {
    "notificaciones": "cmd statusbar expand-notifications", "ajustes_rapidos": "cmd statusbar expand-settings",
    "cerrar_paneles": "cmd statusbar collapse",
}


def por_defecto():
    """Nombre del primer dispositivo Android registrado (lo crea como «celular» si no hay ninguno)."""
    d = _leer()
    for n, v in d.items():
        if v.get("tipo", "android") == "android":
            return n
    registrar("celular", "auto")
    return "celular"


def _sesion(nombre, dev=None):
    """Serial del dispositivo, reutilizado entre acciones (evita reconectar en cada toque)."""
    serial = _serial_cache.get(nombre)
    if serial:
        return serial
    dev = dev or _leer().get(nombre)
    if dev is None:
        raise ErrorDispositivo(f"No tengo registrado ningún dispositivo llamado «{nombre}».")
    serial = _serial(dev)
    _serial_cache[nombre] = serial
    return serial


def _sh(nombre, comando, timeout=15):
    """Ejecuta un comando en el shell del celular. Reconecta una vez si la conexión se cayó. Devuelve el texto de salida."""
    for intento in range(2):
        serial = _sesion(nombre)
        rc, out, err = _adb("-s", serial, "shell", comando, timeout=timeout)
        txt = (_txt(out) + " " + err).strip()
        if rc != 0 and re.search(r"offline|not found|no devices|closed|unauthorized|device '", txt.lower()):
            _serial_cache.pop(nombre, None)
            if intento == 0:
                continue
            raise ErrorDispositivo("Perdí la conexión con el celular. Revisa la Wi-Fi y la depuración inalámbrica.")
        return txt
    return ""


def tamano(nombre, forzar=None):
    """(ancho, alto) de la pantalla en píxeles. Se puede forzar con el tamaño de la última captura (por si está girada)."""
    if forzar:
        _tam_cache[nombre] = tuple(forzar)
    if nombre not in _tam_cache:
        txt = _sh(nombre, "wm size")
        m = re.findall(r"(\d{3,5})x(\d{3,5})", txt)
        if not m:
            raise ErrorDispositivo("No pude leer el tamaño de la pantalla del celular.")
        w, h = m[-1]   # «Override size» si existe, si no «Physical size»
        _tam_cache[nombre] = (int(w), int(h))
    return _tam_cache[nombre]


def _instalados(nombre):
    txt = _sh(nombre, "pm list packages", timeout=20)
    return {l.split(":", 1)[1].strip() for l in txt.splitlines() if l.startswith("package:")}


def abrir_app(nombre, app):
    """Abre una app por nombre común («WhatsApp», «ajustes», «cámara») o por paquete. Devuelve un texto de resultado."""
    _sh(nombre, "input keyevent KEYCODE_WAKEUP")
    clave = _norm(app).strip()
    if clave in _INTENTS:
        txt = _sh(nombre, f"am start -a {_INTENTS[clave]}")
        if "error" in txt.lower() and "warning" not in txt.lower():
            raise ErrorDispositivo(f"No pude abrir «{app}»: {txt[:150]}")
        return f"Abrí «{app}»."

    instalados = None
    paquete = None
    if "." in clave and " " not in clave:
        paquete = clave
    elif clave in _APPS:
        instalados = _instalados(nombre)
        if _APPS[clave] in instalados:
            paquete = _APPS[clave]
    if paquete is None:
        instalados = instalados or _instalados(nombre)
        palabra = re.sub(r"[^a-z0-9]", "", clave)
        cand = sorted((p for p in instalados if palabra and palabra in re.sub(r"[^a-z0-9]", "", p.lower())), key=len)
        if not cand:
            raise ErrorDispositivo(f"No encontré ninguna app instalada llamada «{app}». "
                                   "Dime el nombre exacto o usa [CEL_TECLA: inicio] y búscala con [CEL_TOCAR: icono de {app}].")
        paquete = cand[0]
    txt = _sh(nombre, f"monkey -p {shlex.quote(paquete)} -c android.intent.category.LAUNCHER 1", timeout=20)
    if "no activities found" in txt.lower() or "aborted" in txt.lower():
        raise ErrorDispositivo(f"No pude lanzar «{app}» ({paquete}): {txt[:150]}")
    return f"Abrí «{app}» ({paquete})."


def tocar(nombre, x, y):
    _sh(nombre, f"input tap {int(x)} {int(y)}")


def deslizar(nombre, direccion, tam=None, veces=1):
    """abajo/arriba = mueve el CONTENIDO (abajo = ver más); izquierda/derecha = el dedo va hacia ese lado."""
    w, h = tamano(nombre, tam)
    d = _norm(direccion).strip()
    rutas = {
        "abajo": (0.5 * w, 0.72 * h, 0.5 * w, 0.28 * h), "arriba": (0.5 * w, 0.28 * h, 0.5 * w, 0.72 * h),
        "izquierda": (0.82 * w, 0.5 * h, 0.18 * w, 0.5 * h), "derecha": (0.18 * w, 0.5 * h, 0.82 * w, 0.5 * h),
    }
    if d not in rutas:
        raise ErrorDispositivo(f"Dirección de deslizamiento no válida: «{direccion}» (usa abajo, arriba, izquierda o derecha).")
    x1, y1, x2, y2 = rutas[d]
    for _ in range(max(1, min(int(veces), 8))):
        _sh(nombre, f"input swipe {int(x1)} {int(y1)} {int(x2)} {int(y2)} 350")
        time.sleep(0.35)


def escribir(nombre, texto):
    """Escribe en el campo con el foco. Sin tildes/ñ salvo que esté instalada la app «ADB Keyboard». Devuelve un texto de resultado."""
    texto = " ".join(str(texto).split())
    if not texto:
        raise ErrorDispositivo("No hay texto que escribir.")
    nota = ""
    if not texto.isascii():
        if "com.android.adbkeyboard" in _instalados(nombre):
            _sh(nombre, "ime enable com.android.adbkeyboard/.AdbIME; ime set com.android.adbkeyboard/.AdbIME")
            b64 = base64.b64encode(texto.encode("utf-8")).decode()
            _sh(nombre, f"am broadcast -a ADB_INPUT_B64 --es msg {shlex.quote(b64)}")
            return f"Escribí «{texto}»."
        texto = "".join(c for c in unicodedata.normalize("NFD", texto) if unicodedata.category(c) != "Mn").encode("ascii", "ignore").decode()
        nota = " (sin tildes/ñ: instala «ADB Keyboard» en el celular para escribirlas)"
    _sh(nombre, f"input text {shlex.quote(texto.replace(' ', '%s'))}")
    return f"Escribí «{texto}»{nota}."


def tecla(nombre, que):
    k = _norm(que).strip().replace(" ", "_")
    if k in ("despertar", "desbloquear", "encender_pantalla"):
        _sh(nombre, "input keyevent KEYCODE_WAKEUP")
        _sh(nombre, "wm dismiss-keyguard")   # solo quita el bloqueo SIN PIN/huella; si lo tiene, lo desbloquea Niko
        return "Desperté la pantalla."
    if k in _TECLAS_CMD:
        _sh(nombre, _TECLAS_CMD[k])
        return f"Hecho: {que}."
    if k in _TECLAS:
        _sh(nombre, f"input keyevent {_TECLAS[k]}")
        return f"Pulsé «{que}»."
    raise ErrorDispositivo(f"No conozco la tecla «{que}». Opciones: {', '.join(sorted(set(_TECLAS) | set(_TECLAS_CMD) | {'despertar'}))}.")



# ---------------------------------------------------------------- compartir la pantalla del celular en la PC (scrcpy)
_espejos = {}   # nombre -> proceso de scrcpy


def _buscar_scrcpy():
    nombre = "scrcpy.exe" if sys.platform == "win32" else "scrcpy"
    candidatos = [os.getenv("SAGE_SCRCPY", ""), shutil.which("scrcpy") or "",
                  os.path.join(AQUI, "scrcpy", nombre), os.path.join(AQUI, nombre),
                  os.path.join(AQUI, "platform-tools", nombre)]
    for c in candidatos:
        if c and os.path.isfile(c):
            return c
    raise ErrorDispositivo("Para compartir la pantalla necesito scrcpy (gratis, de Genymobile). Bájalo de github.com/Genymobile/scrcpy/releases "
                           "(zip de Windows), descomprímelo en una carpeta «scrcpy» junto a app.py (o instálalo con: winget install scrcpy "
                           "o pon SAGE_SCRCPY=<ruta> en .env).")


def espejo_abrir(nombre):
    """Abre en la PC una ventana con la pantalla del celular en vivo (se puede manejar con el mouse). Devuelve un texto."""
    p = _espejos.get(nombre)
    if p is not None and p.poll() is None:
        return "La pantalla del celular ya está abierta en la PC."
    exe = _buscar_scrcpy()
    serial = _sesion(nombre)
    _sh(nombre, "input keyevent KEYCODE_WAKEUP")
    env = dict(os.environ)
    env["ADB"] = _buscar_adb()   # mismo adb que SAGE: evita que scrcpy reinicie el servidor y tumbe la conexión
    extra_args = shlex.split(os.getenv("SAGE_SCRCPY_ARGS", ""), posix=(sys.platform != "win32"))
    cmd = [exe, "--serial", serial, "--window-title", f"SAGE · {nombre}", "--max-size", os.getenv("SAGE_ESPEJO_TAMANO", "1280"), *extra_args]
    log = os.path.join(tempfile.gettempdir(), "sage_scrcpy.log")
    kw = {"creationflags": subprocess.CREATE_NO_WINDOW} if sys.platform == "win32" else {}
    with open(log, "w", encoding="utf-8", errors="replace") as f:
        p = subprocess.Popen(cmd, env=env, stdout=f, stderr=subprocess.STDOUT, cwd=os.path.dirname(exe) or None, **kw)
    time.sleep(2.5)
    if p.poll() is not None:
        try:
            cola = open(log, encoding="utf-8", errors="replace").read().strip().splitlines()[-4:]
        except Exception:
            cola = []
        raise ErrorDispositivo("scrcpy se cerró al arrancar: " + (" | ".join(cola) or f"código {p.returncode}") +
                               ". Revisa que el celular siga conectado y desbloqueado.")
    _espejos[nombre] = p
    return "Abrí la pantalla del celular en una ventana de la PC."


def espejo_cerrar(nombre=None):
    """Cierra la ventana compartida (de un dispositivo o de todos)."""
    cerrados = 0
    for n in ([nombre] if nombre else list(_espejos)):
        p = _espejos.pop(n, None)
        if p is not None and p.poll() is None:
            p.terminate()
            cerrados += 1
    return "Cerré la pantalla compartida." if cerrados else "No había ninguna pantalla compartida abierta."


atexit.register(lambda: espejo_cerrar())


# ---------------------------------------------------------------- ¿se refiere a un dispositivo?
_ALIAS_ANDROID = ("celular", "telefono", "movil", "cel", "smartphone", "android", "phone", "tablet", "tableta")
_INTENCION = re.compile(r"\b(mira|mirar|miras|revisa|revisar|muestra|muestrame|mostrar|ensename|ver|ves|captura|capturar|screenshot|"
                        r"pantalla|vistazo|saca|sacame|toma|tomame|que hay|que tengo|que sale|que dice|como esta|notificaciones)\b")


_ACCION = re.compile(r"\b(abre|abrir|abri|entra|entrar|escribe|escribir|manda|envia|enviar|toca|tocar|desliza|deslizar|pon|poner|busca|buscar|"
                     r"ve a|ir a|navega|reproduce|baja|sube|desbloquea|vuelve|regresa|cierra|comparte|compartir|comparteme|espeja|espejo|"
                     r"proyecta|transmite|duplica|refleja|mirror|cast)\b")
_SOLO_VER = re.compile(r"\b(captura|capturas|screenshot)\b")


def mencionado(texto):
    """Nombre del dispositivo registrado al que Niko se refiere pidiendo MIRAR algo («mira mi celular»), o None.
    Si aún no hay ninguno registrado y habla de su celular, registra «celular» (auto) para que la captura se intente
    y, si falla, SAGE explique el motivo en vez de ignorar la petición."""
    t = _norm(texto)
    if not _INTENCION.search(t):
        return None
    if _ACCION.search(t) and not _SOLO_VER.search(t):
        return None   # pide ACCIONAR («abre WhatsApp en mi celular»): lo hacen las directivas CEL_, no la captura
    registrados = _leer()
    if not registrados:
        if any(re.search(rf"\b{re.escape(a)}\b", t) for a in _ALIAS_ANDROID):
            registrar("celular", "auto")
            registrados = _leer()
        else:
            return None
    for nombre, dev in registrados.items():
        alias = {_norm(nombre)} | {_norm(a) for a in dev.get("alias", [])}
        if dev.get("tipo", "android") == "android":
            alias |= set(_ALIAS_ANDROID)
        if any(a and re.search(rf"\b{re.escape(a)}\b", t) for a in alias):
            return nombre
    return None


def abrir(img, ruta=""):
    """Abre la captura en el visor de imágenes de la PC (SAGE_ABRIR_CAPTURA=0 lo desactiva). Devuelve la ruta usada."""
    if os.getenv("SAGE_ABRIR_CAPTURA", "1").strip() == "0":
        return ruta
    try:
        if not ruta or not os.path.isfile(ruta):
            import tempfile
            ruta = os.path.join(tempfile.gettempdir(), f"sage_captura_{time.strftime('%Y%m%d_%H%M%S')}.png")
            img.save(ruta)
        if sys.platform == "win32":
            os.startfile(ruta)
        elif sys.platform == "darwin":
            subprocess.Popen(["open", ruta])
        else:
            subprocess.Popen(["xdg-open", ruta])
    except Exception as e:
        print(f"[Dispositivos] No pude abrir la captura: {e}")
    return ruta


# ---------------------------------------------------------------- línea de comandos
def _cli(argv):
    cmd = argv[1].lower() if len(argv) > 1 else "ayuda"
    try:
        if cmd == "listar":
            d = _leer()
            if not d: print("No hay dispositivos registrados. Mira: python dispositivos.py ayuda")
            for n, v in d.items(): print(f"- {n}: {v.get('tipo', 'android')} @ {v.get('direccion', 'auto')}  alias: {', '.join(v.get('alias', [])) or '-'}")
        elif cmd == "agregar" and len(argv) >= 3:
            registrar(argv[2], argv[3] if len(argv) > 3 else "auto")
            print(f"Registrado «{argv[2]}». Prueba: python dispositivos.py capturar {argv[2]}")
        elif cmd == "quitar" and len(argv) >= 3:
            print("Quitado." if quitar(argv[2]) else "No existe.")
        elif cmd == "alias" and len(argv) >= 4:
            d = _leer()
            if argv[2] not in d: print("No existe ese dispositivo."); return 1
            registrar(argv[2], d[argv[2]].get("direccion", "auto"), d[argv[2]].get("tipo", "android"), [a.strip() for a in argv[3].split(",") if a.strip()])
            print("Alias guardados.")
        elif cmd == "emparejar" and len(argv) >= 4:
            _, out, err = _adb("pair", argv[2], argv[3], timeout=30)
            print(_txt(out) or err.strip() or "(sin respuesta)")
        elif cmd in ("diagnostico", "diagnóstico", "diag"):
            print(diagnostico())
        elif cmd == "probar":
            frase = " ".join(argv[2:]) or "mira mi celular"
            nombre = mencionado(frase)
            print(f"Frase: «{frase}» -> dispositivo detectado: {nombre or 'NINGUNO'}")
            if nombre:
                img, ruta = capturar(nombre)
                print(f"Captura OK: {img.size[0]}x{img.size[1]}" + (f" -> {ruta}" if ruta else ""))
                abrir(img, ruta)
        elif cmd == "cel" and len(argv) >= 3:   # python dispositivos.py cel abrir whatsapp | tocar 500 900 | deslizar abajo | tecla inicio | escribir hola
            n = por_defecto(); a = argv[2].lower(); r = " ".join(argv[3:])
            if a == "abrir": print(abrir_app(n, r))
            elif a == "tocar": x, y = argv[3:5]; tocar(n, x, y); print("Toqué.")
            elif a == "deslizar": deslizar(n, argv[3]); print("Deslicé.")
            elif a == "escribir": print(escribir(n, r))
            elif a == "tecla": print(tecla(n, r))
            else: print("Uso: cel abrir|tocar|deslizar|escribir|tecla ...")
        elif cmd == "espejo":   # python dispositivos.py espejo [abrir|cerrar]  (abrir deja el proceso vivo mientras no pulses Enter)
            n = por_defecto()
            if len(argv) > 2 and argv[2].lower() in ("cerrar", "apagar"): print(espejo_cerrar(n))
            else:
                print(espejo_abrir(n)); input("Pulsa Enter para cerrar la ventana... "); print(espejo_cerrar(n))
        elif cmd == "usb" and len(argv) >= 3:
            d = configurar_usb(argv[2])
            print(f"Listo: «{argv[2]}» registrado en {d}. Ya puedes quitar el cable. Prueba: python dispositivos.py capturar {argv[2]}")
        elif cmd == "reiniciar":
            _adb("disconnect", timeout=8)
            _adb("kill-server", timeout=10)
            _adb("start-server", timeout=20)
            print("adb reiniciado y conexiones cerradas.")
        elif cmd == "conectar" and len(argv) >= 3:
            dev = _leer().get(argv[2])
            if dev is None: print("No existe ese dispositivo."); return 1
            print(f"Conectado: {_serial(dev)}")
        elif cmd == "capturar" and len(argv) >= 3:
            img, ruta = capturar(argv[2])
            print(f"Captura OK: {img.size[0]}x{img.size[1]}" + (f" -> {ruta}" if ruta else ""))
        else:
            print(AYUDA)
    except ErrorDispositivo as e:
        print(f"✖ {e}")
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(_cli(sys.argv))
