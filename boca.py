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
import uuid

import edge_tts
import pygame

VOZ_SAGE = "es-MX-DaliaNeural"
VELOCIDAD_SAGE = "+25%"
# Se pueden cambiar desde .env sin tocar código: SAGE_VOZ y SAGE_VOZ_VELOCIDAD

try:
    pygame.mixer.init()
    _MIXER_OK = True
except Exception as e:  # sin dispositivo de audio no debe romper la app
    _MIXER_OK = False
    print(f"[SAGE AUDIO] Mixer no disponible: {e}")

_DIR_TEMP = tempfile.mkdtemp(prefix="sage_voz_")
atexit.register(shutil.rmtree, _DIR_TEMP, ignore_errors=True)

cola_texto = queue.Queue()               # frases pendientes de sintetizar
cola_audio = queue.Queue(maxsize=3)      # mp3 listos para reproducir (la siguiente se genera mientras suena la actual)

_lock = threading.Lock()
_pendientes = 0
_epoca = 0  # sube con cada callar(): descarta todo lo que venga de antes

_RE_CODIGO = re.compile(r"```.*?```", re.DOTALL)
_RE_DIRECTIVA = re.compile(r"\[(?:ABRIR|ENFOCAR|CERRAR|ESCRIBIR|TECLA|PULSAR|BUSCAR|CLICK|SCROLL|ESPERAR|CIRCULOS|APAGAR)\b[^\]]*\]", re.IGNORECASE)
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


def _dividir(texto, maximo=260):
    """Parte el texto en frases (para empezar a hablar antes) y junta las demasiado cortas."""
    trozos = []
    for pz in re.split(r"(?<=[.!?…:;])\s+|\n+", texto):
        pz = pz.strip()
        if not pz: continue
        trozos.extend(_cortar_largo(pz, maximo) if len(pz) > maximo else [pz])
    frases = []
    for pz in trozos:
        if frases and len(frases[-1]) < 40 and len(frases[-1]) + 1 + len(pz) <= maximo:
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


def _restar():
    global _pendientes
    with _lock:
        _pendientes = max(0, _pendientes - 1)


def _borrar(ruta):
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


def _worker_generador():
    """Hilo con bucle de eventos persistente: convierte frases a mp3 sin bloquear la app."""
    loop = asyncio.new_event_loop()
    asyncio.set_event_loop(loop)
    while True:
        item = cola_texto.get()
        if item is None:
            break
        epoca, frase = item
        if epoca != _epoca:
            _restar()
            continue

        ruta = os.path.join(_DIR_TEMP, f"{uuid.uuid4().hex}.mp3")
        ok = False
        for _ in range(2):  # un reintento ante fallos de red
            try:
                loop.run_until_complete(_sintetizar(frase, ruta))
                ok = True
                break
            except Exception as e:
                print(f"[SAGE AUDIO ERROR]: {e}")
                _borrar(ruta)

        if ok and epoca == _epoca:
            cola_audio.put((epoca, ruta))
        else:
            _borrar(ruta)
            _restar()


def _worker_reproductor():
    while True:
        item = cola_audio.get()
        if item is None:
            break
        epoca, ruta = item
        try:
            if epoca == _epoca:
                pygame.mixer.music.load(ruta)
                pygame.mixer.music.play()
                while pygame.mixer.music.get_busy() and epoca == _epoca:
                    time.sleep(0.03)
        except Exception as e:
            print(f"[SAGE AUDIO ERROR]: {e}")
        finally:
            try: pygame.mixer.music.unload()
            except Exception: pass
            _borrar(ruta)
            _restar()


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
    epoca = _epoca
    _sumar(len(frases))
    for f in frases:
        cola_texto.put((epoca, f))


def esta_hablando():
    return _pendientes > 0


def _vaciar(cola, con_archivos):
    while True:
        try: item = cola.get_nowait()
        except queue.Empty: break
        if item is None: continue
        if con_archivos: _borrar(item[1])
        _restar()


def callar():
    """Interrumpe la voz al instante y descarta todo lo pendiente."""
    global _epoca
    _epoca += 1
    _vaciar(cola_texto, False)
    _vaciar(cola_audio, True)
    if _MIXER_OK:
        try: pygame.mixer.music.stop()
        except Exception: pass


def cerrar():
    callar()
    cola_texto.put(None)
    cola_audio.put(None)
