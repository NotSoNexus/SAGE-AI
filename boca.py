import os
os.environ.setdefault("PYGAME_HIDE_SUPPORT_PROMPT", "1")

import re
import time
import queue
import atexit
import asyncio
import shutil
import tempfile
import threading
import io
import uuid
import sys
import base64
import wave
import urllib.request
from xml.sax.saxutils import escape as _xml
import subprocess

import edge_tts
import pygame

from horas import hablar_horas

VOZ_SAGE = "es-MX-DaliaNeural"
VELOCIDAD_SAGE = "+25%"
# Se pueden cambiar desde .env sin tocar código: SAGE_VOZ y SAGE_VOZ_VELOCIDAD

try:
    pygame.mixer.init()
    pygame.mixer.set_reserved(1)          # el canal 0 es solo de la voz (el aviso usa otros)
    _canal = pygame.mixer.Channel(0)
    _MIXER_OK = True
except Exception as e:  # sin dispositivo de audio no debe romper la app
    _MIXER_OK = False
    _canal = None
    print(f"[SAGE AUDIO] Mixer no disponible: {e}")

_DIR_TEMP = tempfile.mkdtemp(prefix="sage_voz_")
atexit.register(shutil.rmtree, _DIR_TEMP, ignore_errors=True)

cola_texto = queue.Queue()               # frases pendientes de sintetizar
cola_audio = queue.Queue(maxsize=4)      # mp3 listos para reproducir (la siguiente se genera mientras suena la actual)

_lock = threading.Lock()
_pendientes = 0
_epoca = 0  # sube con cada callar(): descarta todo lo que venga de antes
_t_actividad = time.monotonic()  # último movimiento de la cola de voz (perro guardián contra contadores atascados)

_RE_CODIGO = re.compile(r"```.*?```", re.DOTALL)
_RE_DIRECTIVA = re.compile(r"\[(?:SEGURIDAD|AJUSTE|ABRIR_FONDO|RECORDAR|OLVIDAR|RECUERDO_MOVER|RECUERDOS_ORDENAR|MENSAJE|ABRIR|ENFOCAR|CERRAR|ESCRIBIR|TECLA|PULSAR_DER|PULSAR|BUSCAR|ATAJO|ARRASTRAR|DESCARGAR|DIBUJAR|TRAZO|JUGAR|CERRAR_PESTA[ÑN]A|MINIMIZAR|MAXIMIZAR|VENTANA|SEGUNDO_PLANO|PRIMER_PLANO|MULTIMEDIA|DISCORD|CLICK_DER|CLICK|SCROLL|ESPERAR|CIRCULOS|APAGAR_PC|APAGAR|TEMPORIZADOR|CEL_[A-Z]+|SPOTIFY_PLAYLIST|SPOTIFY_EN_PLAYLIST|SPOTIFY_VOLUMEN|SPOTIFY)\b[^\]]*\]", re.IGNORECASE)
_RE_URL = re.compile(r"https?://\S+")


# =====================================================================
#  LIMPIEZA Y DIVISIÓN DEL TEXTO
# =====================================================================
def limpiar_texto(texto):
    """Quita lo que no debe leerse en voz alta: código, directivas [ABRIR: ...], URLs y marcas markdown."""
    t = _RE_CODIGO.sub(" ", texto)
    t = _RE_DIRECTIVA.sub(" ", t)
    t = _RE_URL.sub(" ", t)
    t = re.sub(r"`([^`]*)`", r"\1", t)
    t = re.sub(r"[*_#>~|]+", " ", t)
    t = hablar_horas(t)   # «15:30» se dice «las tres y media de la tarde» (12 horas, natural)
    t = re.sub(r"^\s*[-•]\s+", "", t, flags=re.MULTILINE)
    t = re.sub(r"[ \t]+", " ", t)
    return t.strip()


def _cortar_largo(pieza, maximo):
    res, actual = [], ""
    for palabra in pieza.split():
        if actual and len(actual) + 1 + len(palabra) > maximo:
            res.append(actual)
            actual = palabra
        else:
            actual = f"{actual} {palabra}".strip()
    if actual: res.append(actual)
    return res


def _dividir(texto, maximo=200):
    """Parte el texto en frases (para empezar a hablar antes) y junta las demasiado cortas."""
    trozos = []
    for pz in re.split(r"(?<=[.!?…:;])\s+|\n+", texto):
        pz = pz.strip()
        if not pz: continue
        trozos.extend(_cortar_largo(pz, maximo) if len(pz) > maximo else [pz])
    frases = []
    for pz in trozos:
        if frases and len(frases[-1]) < 24 and len(frases[-1]) + 1 + len(pz) <= maximo:
            frases[-1] += " " + pz
        else:
            frases.append(pz)
    return [f for f in frases if any(c.isalnum() for c in f)]


# =====================================================================
#  CONTADOR DE PENDIENTES
# =====================================================================
def _sumar(n):
    global _pendientes
    with _lock:
        _pendientes += n


def _restar(epoca):
    """Resta una frase pendiente SOLO si sigue siendo de la época actual (atómico con callar())."""
    global _pendientes, _t_actividad
    with _lock:
        if epoca == _epoca:
            _pendientes = max(0, _pendientes - 1)
        _t_actividad = time.monotonic()


def _latido():
    global _t_actividad
    _t_actividad = time.monotonic()


def _borrar(ruta):
    if not isinstance(ruta, str):
        return
    try: os.remove(ruta)
    except OSError: pass


# =====================================================================
#  HILOS: generador (edge-tts) y reproductor (pygame)
# =====================================================================
async def _sintetizar(frase, ruta):
    comunicador = edge_tts.Communicate(
        frase,
        os.getenv("SAGE_VOZ", VOZ_SAGE),
        rate=os.getenv("SAGE_VOZ_VELOCIDAD", VELOCIDAD_SAGE),
    )
    await asyncio.wait_for(comunicador.save(ruta), timeout=25)


_edge_malo_hasta = 0.0   # mientras dure, se usa directamente la voz de Windows (edge-tts falló)
_ultimo_aviso = ""


_MOTOR_FORZADO = os.getenv("SAGE_MOTOR", "").strip().lower() in ("piper", "azure", "windows")   # saltarse edge-tts
_t_actualizado = 0.0
_actualizado = False   # la auto-actualización de edge-tts se intenta una sola vez por ejecución


def _version_edge():
    try:
        from importlib.metadata import version
        return version("edge-tts")
    except Exception:
        return "?"


def _autoactualizar_edge():
    """Hilo: pip install -U edge-tts y recarga la librería sin reiniciar SAGE (los 403 suelen ser una versión vieja)."""
    global _edge_malo_hasta, edge_tts
    antes = _version_edge()
    try:
        r = subprocess.run([sys.executable, "-m", "pip", "install", "-U", "edge-tts", "--disable-pip-version-check", "-q"],
                           capture_output=True, timeout=300, creationflags=0x08000000 if sys.platform == "win32" else 0)
        for k in [k for k in sys.modules if k == "edge_tts" or k.startswith("edge_tts.")]:
            del sys.modules[k]
        import edge_tts as nuevo
        edge_tts = nuevo
        despues = _version_edge()
        if r.returncode == 0:
            print(f"[SAGE AUDIO] edge-tts {antes} -> {despues}. Reintento con la voz Dalia.")
            _edge_malo_hasta = 0.0
        else:
            print(f"[SAGE AUDIO] No pude actualizar edge-tts (instálalo tú: pip install -U edge-tts): {r.stderr.decode(errors='ignore')[-150:]}")
    except Exception as e:
        print(f"[SAGE AUDIO] No pude actualizar edge-tts: {e}")


def _marcar_edge_malo():
    global _edge_malo_hasta, _actualizado, _t_actualizado
    _edge_malo_hasta = time.monotonic() + 300
    if _actualizado and time.monotonic() - _t_actualizado > 6 * 3600:
        _actualizado = False   # cada 6 h vuelve a buscar una versión nueva de edge-tts (Microsoft cambió su servicio el 10-oct-2026)   # a los 5 min se vuelve a intentar con edge-tts
    _preparar_piper()   # deja listo el motor local ilimitado mientras edge-tts siga fallando
    if not _actualizado and not getattr(sys, "frozen", False):
        _actualizado = True
        _t_actualizado = time.monotonic()
        print(f"[SAGE AUDIO] edge-tts {_version_edge()} falla: intento actualizarlo solo (mientras tanto, voz de Windows). "
              "Si sigue el 403, revisa que la hora del PC esté sincronizada.")
        threading.Thread(target=_autoactualizar_edge, daemon=True).start()


def _avisar_fallo_edge(e):
    global _ultimo_aviso
    msg = f"{type(e).__name__}: {e}"
    if msg != _ultimo_aviso:   # cada error distinto se muestra una sola vez
        _ultimo_aviso = msg
        pista = " -> actualiza con: pip install -U edge-tts" if any(x in msg for x in ("403", "Invalid response", "NoAudio", "WSServer", "Sec-MS")) else ""
        print(f"[SAGE AUDIO ERROR] edge-tts: {msg[:200]}{pista}. Uso la voz de Windows mientras tanto.")


_PS = """Add-Type -AssemblyName System.Speech
$s = New-Object System.Speech.Synthesis.SpeechSynthesizer
$nom = $null
if ($env:SAGE_TTS_VOZ) { $nom = $env:SAGE_TTS_VOZ }
else { $v = $s.GetInstalledVoices() | Where-Object { $_.Enabled -and $_.VoiceInfo.Culture.Name -like 'es*' } | Select-Object -First 1; if ($v) { $nom = $v.VoiceInfo.Name } }
if ($nom) { $s.SelectVoice($nom) }
$s.Rate = [int]$env:SAGE_TTS_RATE
$s.SetOutputToWaveFile($env:SAGE_TTS_OUT)
$s.Speak($env:SAGE_TTS_TEXTO)
$s.Dispose()"""


_voces_sapi = None   # nombres de las voces SAPI instaladas (se lee una sola vez)


def _voz_sapi():
    """Voz SAPI instalada que se llame como la de SAGE (p. ej. «Dalia» si instalaste la voz natural de Windows 11 + NaturalVoiceSAPIAdapter)."""
    global _voces_sapi
    if sys.platform != "win32":
        return None
    if _voces_sapi is None:
        _voces_sapi = []
        try:
            ps = "Add-Type -AssemblyName System.Speech; (New-Object System.Speech.Synthesis.SpeechSynthesizer).GetInstalledVoices() | ForEach-Object { $_.VoiceInfo.Name }"
            r = subprocess.run(["powershell", "-NoProfile", "-NonInteractive", "-Command", ps], capture_output=True, timeout=30, creationflags=0x08000000)
            _voces_sapi = [x.strip() for x in r.stdout.decode("utf-8", "ignore").splitlines() if x.strip()]
        except Exception:
            pass
    m = re.search(r"-([A-Za-z]+)Neural", os.getenv("SAGE_VOZ", VOZ_SAGE))
    if m:
        for n in _voces_sapi:
            if m.group(1).lower() in n.lower():
                return n
    return None


def _sintetizar_windows(frase, ruta):
    """Voz local de Windows (System.Speech) a un .wav. Devuelve True si el archivo quedó listo."""
    if sys.platform != "win32":
        return False
    try:
        pct = int(re.sub(r"[^0-9+-]", "", os.getenv("SAGE_VOZ_VELOCIDAD", VELOCIDAD_SAGE)) or 0)
    except ValueError:
        pct = 0
    env = {**os.environ, "SAGE_TTS_VOZ": _voz_sapi() or "", "SAGE_TTS_TEXTO": frase, "SAGE_TTS_OUT": ruta, "SAGE_TTS_RATE": str(max(-10, min(10, round(pct / 10))))}
    cod = base64.b64encode(_PS.encode("utf-16-le")).decode()
    try:
        subprocess.run(["powershell", "-NoProfile", "-NonInteractive", "-EncodedCommand", cod], env=env, timeout=30,
                       creationflags=0x08000000, stdin=subprocess.DEVNULL, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        return os.path.exists(ruta) and os.path.getsize(ruta) > 100
    except Exception as e:
        print(f"[SAGE AUDIO ERROR] voz de Windows: {e}")
        return False


# ---------------------------------------------------------------- motores alternativos
def _sintetizar_azure(frase, ruta):
    """Azure Speech (REST): la MISMA voz es-MX-DaliaNeural con tu propia clave (nivel gratis F0: ~500 000 caracteres/mes)."""
    clave, region = os.getenv("SAGE_AZURE_KEY", "").strip(), os.getenv("SAGE_AZURE_REGION", "").strip()
    if not (clave and region):
        return False
    voz = os.getenv("SAGE_VOZ", VOZ_SAGE)
    rate = os.getenv("SAGE_VOZ_VELOCIDAD", VELOCIDAD_SAGE)
    ssml = (f"<speak version='1.0' xml:lang='es-MX'><voice name='{voz}'><prosody rate='{rate}'>{_xml(frase)}</prosody></voice></speak>")
    req = urllib.request.Request(f"https://{region}.tts.speech.microsoft.com/cognitiveservices/v1", data=ssml.encode("utf-8"), method="POST",
                                 headers={"Ocp-Apim-Subscription-Key": clave, "Content-Type": "application/ssml+xml",
                                          "X-Microsoft-OutputFormat": "audio-24khz-48kbitrate-mono-mp3", "User-Agent": "SAGE"})
    try:
        with urllib.request.urlopen(req, timeout=20) as r, open(ruta, "wb") as f:
            f.write(r.read())
        return os.path.getsize(ruta) > 100
    except Exception as e:
        print(f"[SAGE AUDIO] Azure: {str(e)[:120]}")
        _borrar(ruta)
        return False


_PIPER_MODELO = os.getenv("SAGE_PIPER_VOZ", "es_MX-claude-high")
_PIPER_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "voces")
_piper = None            # PiperVoice cargada
_piper_estado = "nuevo"  # nuevo | preparando | listo | fallo
_piper_lock = threading.Lock()


def _piper_preparar_hilo():
    """Instala piper-tts y baja la voz (una vez, ~65 MB) en segundo plano. Después funciona SIN internet y sin límite."""
    global _piper, _piper_estado
    try:
        try:
            import piper  # noqa: F401
        except ImportError:
            print("[SAGE AUDIO] Instalando piper-tts (voz local ilimitada)...")
            subprocess.run([sys.executable, "-m", "pip", "install", "-U", "piper-tts", "--disable-pip-version-check", "-q"], check=True, timeout=600,
                           creationflags=0x08000000 if sys.platform == "win32" else 0)
        os.makedirs(_PIPER_DIR, exist_ok=True)
        onnx = os.path.join(_PIPER_DIR, _PIPER_MODELO + ".onnx")
        partes = _PIPER_MODELO.split("-")   # es_MX-claude-high -> es/es_MX/claude/high/
        base = f"https://huggingface.co/rhasspy/piper-voices/resolve/main/{partes[0].split('_')[0]}/{partes[0]}/{partes[1]}/{partes[2]}/{_PIPER_MODELO}.onnx"
        for url, dest in ((base, onnx), (base + ".json", onnx + ".json")):
            if not os.path.exists(dest) or os.path.getsize(dest) < 1000:
                print(f"[SAGE AUDIO] Descargando {os.path.basename(dest)}...")
                urllib.request.urlretrieve(url, dest + ".part")
                os.replace(dest + ".part", dest)
        from piper import PiperVoice
        _piper = PiperVoice.load(onnx)
        _piper_estado = "listo"
        _sintetizar_piper("hola")   # calienta el modelo: la primera frase real sale sin retraso
        print("[SAGE AUDIO] Voz local Piper lista (ilimitada, sin internet).")
    except Exception as e:
        _piper_estado = "fallo"
        print(f"[SAGE AUDIO] Piper no disponible: {str(e)[:150]}")


def _preparar_piper():
    global _piper_estado
    with _piper_lock:
        if _piper_estado != "nuevo":
            return
        _piper_estado = "preparando"
    threading.Thread(target=_piper_preparar_hilo, daemon=True).start()


def _sintetizar_piper(frase):
    """Piper local: devuelve el WAV en memoria (bytes), sin tocar el disco."""
    if _piper_estado != "listo" or _piper is None:
        return None
    try:
        try:
            from piper import SynthesisConfig
            pct = int(re.sub(r"[^0-9+-]", "", os.getenv("SAGE_VOZ_VELOCIDAD", VELOCIDAD_SAGE)) or 0)
            cfg = SynthesisConfig(length_scale=max(0.4, min(2.0, 100.0 / (100 + pct))))
        except Exception:
            cfg = None
        buf = io.BytesIO()
        with wave.open(buf, "wb") as wf:
            if hasattr(_piper, "synthesize_wav"):
                _piper.synthesize_wav(frase, wf, syn_config=cfg) if cfg else _piper.synthesize_wav(frase, wf)
            else:
                _piper.synthesize(frase, wf)
        data = buf.getvalue()
        return data if len(data) > 100 else None
    except Exception as e:
        print(f"[SAGE AUDIO] Piper: {str(e)[:120]}")
        return None


_MOTOR = os.getenv("SAGE_MOTOR", "piper").strip().lower()   # piper (por defecto) | edge | azure | windows
if _MOTOR in ("piper", "azure"):
    _preparar_piper()   # carga y calienta Piper desde el arranque


def _generar(frase, epoca, loop):
    """Audio de una frase con el primer motor que funcione. Devuelve bytes (WAV en memoria), una ruta de archivo o None."""
    orden = {"edge": ("edge", "piper", "azure", "windows"), "azure": ("azure", "piper", "windows"), "windows": ("windows",)}.get(
        _MOTOR, ("piper", "azure", "edge", "windows"))
    base = os.path.join(_DIR_TEMP, uuid.uuid4().hex)
    for m in orden:
        if epoca != _epoca:
            return None
        if m == "piper":
            d = _sintetizar_piper(frase)
            if d: return d
        elif m == "azure":
            if _sintetizar_azure(frase, base + ".mp3"): return base + ".mp3"
        elif m == "edge":
            if time.monotonic() < _edge_malo_hasta:
                continue
            for _ in range(2):
                try:
                    loop.run_until_complete(_sintetizar(frase, base + ".mp3"))
                    return base + ".mp3"
                except Exception as e:
                    _avisar_fallo_edge(e)
                    _borrar(base + ".mp3")
            _marcar_edge_malo()
        elif m == "windows":
            if _sintetizar_windows(frase, base + ".wav"): return base + ".wav"
    return None


def _worker_generador():
    """Hilo: convierte frases en audio (en memoria) mientras suena la anterior."""
    loop = asyncio.new_event_loop()
    asyncio.set_event_loop(loop)
    while True:
        item = cola_texto.get()
        if item is None:
            break
        epoca, frase = item
        if epoca != _epoca:
            continue  # callar() ya puso el contador a cero
        audio = _generar(frase, epoca, loop)
        if audio is not None and epoca == _epoca:
            cola_audio.put((epoca, audio))
        else:
            _borrar(audio)
            _restar(epoca)


def _worker_reproductor():
    while True:
        item = cola_audio.get()
        if item is None:
            break
        epoca, audio = item
        try:
            if epoca == _epoca:
                snd = pygame.mixer.Sound(file=io.BytesIO(audio)) if isinstance(audio, (bytes, bytearray)) else pygame.mixer.Sound(audio)
                _canal.play(snd)
                while _canal.get_busy() and epoca == _epoca:
                    _latido()
                    time.sleep(0.01)
        except Exception as e:
            print(f"[SAGE AUDIO ERROR]: {e}")
        finally:
            _borrar(audio)
            _restar(epoca)


if _MIXER_OK:
    threading.Thread(target=_worker_generador, daemon=True).start()
    threading.Thread(target=_worker_reproductor, daemon=True).start()


# =====================================================================
#  API PÚBLICA
# =====================================================================
def hablar(texto):
    if not _MIXER_OK or not texto or not texto.strip():
        return
    frases = _dividir(limpiar_texto(texto))
    if not frases:
        return
    global _pendientes, _t_actividad
    with _lock:   # leer la época y sumar pendientes es atómico respecto a callar(): sin contadores huérfanos
        epoca = _epoca
        _pendientes += len(frases)
        _t_actividad = time.monotonic()
        for f in frases:
            cola_texto.put((epoca, f))


def esta_hablando():
    global _pendientes
    if _pendientes > 0 and time.monotonic() - _t_actividad > 75:
        with _lock:   # nada se movió en 75 s (más que dos síntesis agotadas): el contador quedó atascado y bloquearía el micrófono
            _pendientes = 0
    return _pendientes > 0


def _vaciar(cola, con_archivos):
    while True:
        try: item = cola.get_nowait()
        except queue.Empty: break
        if item is None: continue
        if con_archivos: _borrar(item[1])


def callar():
    """Interrumpe la voz al instante y descarta todo lo pendiente."""
    global _epoca, _pendientes
    with _lock:
        _epoca += 1
        _pendientes = 0   # esta_hablando() pasa a False YA, sin esperar a que terminen las síntesis en curso
    _vaciar(cola_texto, False)
    _vaciar(cola_audio, True)
    if _MIXER_OK:
        try: _canal.stop()
        except Exception: pass


def cerrar():
    callar()
    cola_texto.put(None)
    cola_audio.put(None)


# =====================================================================
#  SONIDO DE "TE ESCUCHO" (campanita suave generada por código, sin archivos)
# =====================================================================
_sonido_aviso = None


def _crear_aviso():
    import numpy as np
    init = pygame.mixer.get_init()
    if not init:
        return None
    tasa, _, canales = init
    def nota(f, dur, vol):
        t = np.linspace(0, dur, int(tasa * dur), endpoint=False)
        env = np.minimum(1, t / 0.01) * np.exp(-t * 14)           # ataque suave y caída rápida
        return vol * env * (np.sin(2 * np.pi * f * t) + 0.25 * np.sin(2 * np.pi * 2 * f * t))
    gap = np.zeros(int(tasa * 0.05))
    onda = np.concatenate([nota(880, 0.16, 0.5), gap, nota(1318, 0.24, 0.5)])
    onda = (onda / max(1e-6, np.abs(onda).max()) * 0.35 * 32767).astype(np.int16)
    if canales == 2:
        onda = np.column_stack([onda, onda])
    return pygame.sndarray.make_sound(np.ascontiguousarray(onda))


def aviso():
    """Ruidito suave: 'te escuché, dime'. No bloquea ni interfiere con la voz."""
    global _sonido_aviso
    if not _MIXER_OK:
        return
    try:
        if _sonido_aviso is None:
            _sonido_aviso = _crear_aviso()
        if _sonido_aviso is not None:
            _sonido_aviso.play()
    except Exception as e:
        print(f"[SAGE AUDIO] Aviso no disponible: {e}")
