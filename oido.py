import os
import re
import sys
import math
import queue
import time
import threading
import unicodedata
from collections import deque
from functools import lru_cache

import numpy as np

FS = 16000  # Whisper trabaja a 16 kHz mono
MAX_SEGUNDOS = 300  # tope de grabación para no llenar la RAM

VOCABULARIO = "SAGE, Niko, Wiwi, Nexus, Cierra, Sonic ReDust, Godot, GDScript, Unreal Engine, Blender, Chill, blueprints, shaders, rigging, open world, play, enter, Discord, YouTube."

# Frases fantasma típicas de Whisper cuando solo hay ruido o silencio
_ALUCINACIONES_EXACTAS = {"música", "musica", "subtítulos", "subtitulos", "gracias por ver", "suscríbete", "suscribete"}
_ALUCINACIONES_PARCIALES = (
    "amara.org", "subtítulos realizados por", "subtitulos realizados por",
    "subtítulos por la comunidad", "subtitulos por la comunidad",
    "no olvides suscribirte", "gracias por ver el video", "gracias por ver el vídeo",
)


# =====================================================================
#  UTILIDADES DE AUDIO
# =====================================================================
def _remuestrear(audio, origen, destino=FS):
    """Convierte a la tasa de Whisper. resample_poly es mucho más rápido y limpio que FFT resample."""
    if audio.size == 0 or origen == destino:
        return audio.astype(np.float32, copy=False)
    try:
        from scipy.signal import resample_poly
        g = math.gcd(int(origen), int(destino))
        return resample_poly(audio, int(destino) // g, int(origen) // g).astype(np.float32)
    except ImportError:
        n = int(len(audio) * destino / origen)
        x = np.linspace(0, len(audio) - 1, n)
        return np.interp(x, np.arange(len(audio)), audio).astype(np.float32)


def _normalizar(audio):
    """Sube el volumen de grabaciones muy bajas (máx. x8) para que el VAD y Whisper las detecten."""
    pico = float(np.max(np.abs(audio))) if audio.size else 0.0
    if 1e-4 < pico < 0.3:
        audio = audio * min(8.0, 0.6 / pico)
    return audio.astype(np.float32, copy=False)


def _dispositivo_entrada():
    """MIC_DEVICE en .env (índice o nombre) para elegir micrófono; vacío = el predeterminado."""
    val = os.getenv("MIC_DEVICE", "").strip()
    if not val: return None
    try: return int(val)
    except ValueError: return val


class _GrabadoraBase:
    def __init__(self):
        self._frames = []
        self._muestras = 0
        self._tasa = FS
        self.nivel = 0.0  # volumen RMS actual (0..~1), lo usa la UI para el visualizador

    def _reiniciar(self):
        self._frames = []
        self._muestras = 0
        self.nivel = 0.0

    def _acumular(self, mono, tasa):
        if mono.size == 0: return
        self.nivel = float(np.sqrt(np.mean(np.square(mono))))
        if self._muestras < tasa * MAX_SEGUNDOS:
            self._frames.append(np.array(mono, dtype=np.float32, copy=True))
            self._muestras += mono.size

    def _finalizar(self, tasa):
        self.nivel = 0.0
        if not self._frames:
            return np.zeros(0, dtype=np.float32)
        audio = np.concatenate(self._frames)
        self._frames = []
        self._muestras = 0
        return _normalizar(_remuestrear(audio, tasa))


# =====================================================================
#  GRABADORAS
# =====================================================================
class Grabadora(_GrabadoraBase):
    """Graba de tu micrófono físico (modo normal)."""

    def __init__(self):
        super().__init__()
        self._stream = None

    def _cerrar(self):
        if self._stream is not None:
            try:
                self._stream.stop()
                self._stream.close()
            except Exception:
                pass
            self._stream = None

    def iniciar(self):
        import sounddevice as sd  # import aquí para dar un error claro si falta

        self._cerrar()  # evita fugas si se llama dos veces seguidas
        self._reiniciar()

        def callback(indata, frames, tiempo, status):
            self._acumular(indata[:, 0], FS)

        try:
            self._stream = sd.InputStream(
                samplerate=FS, channels=1, dtype="float32",
                callback=callback, device=_dispositivo_entrada(),
            )
            self._stream.start()
        except Exception:
            self._cerrar()
            raise

    def detener(self):
        self._cerrar()
        return self._finalizar(FS)


def _buscar_loopback(p):
    try:
        return p.get_default_wasapi_loopback()
    except Exception:
        pass
    lista = list(p.get_loopback_device_info_generator())
    if not lista:
        raise RuntimeError("No se encontró ningún dispositivo Loopback WASAPI activo.")
    return lista[0]


class GrabadoraPC(_GrabadoraBase):
    """Graba todo el audio del sistema / Discord (Loopback WASAPI, solo Windows) y lo resamplea a 16 kHz."""

    def __init__(self):
        super().__init__()
        self._p = None
        self._stream = None
        self._tasa = 44100

    def _cerrar(self):
        if self._stream is not None:
            try:
                self._stream.stop_stream()
                self._stream.close()
            except Exception:
                pass
            self._stream = None
        if self._p is not None:
            try: self._p.terminate()
            except Exception: pass
            self._p = None

    def iniciar(self):
        if sys.platform != "win32":
            raise RuntimeError("La captura de audio del sistema (WASAPI loopback) solo está disponible en Windows.")
        import pyaudiowpatch as pyaudio  # lazy: no existe en Linux y rompía todo el módulo

        self._cerrar()
        self._reiniciar()
        p = pyaudio.PyAudio()
        try:
            dispositivo = _buscar_loopback(p)
            canales = max(1, int(dispositivo["maxInputChannels"]))
            self._tasa = int(dispositivo["defaultSampleRate"])

            def callback(in_data, frame_count, time_info, status):
                datos = np.frombuffer(in_data, dtype=np.float32)
                if canales > 1:
                    n = (datos.size // canales) * canales
                    datos = datos[:n].reshape(-1, canales).mean(axis=1)
                self._acumular(datos, self._tasa)
                return (None, pyaudio.paContinue)

            self._stream = p.open(
                format=pyaudio.paFloat32,
                channels=canales,
                rate=self._tasa,
                input=True,
                input_device_index=dispositivo["index"],
                frames_per_buffer=1024,
                stream_callback=callback,
            )
            self._p = p
            self._stream.start_stream()
        except Exception:
            self._cerrar()
            try: p.terminate()
            except Exception: pass
            raise  # antes se tragaba el error y la UI creía que estaba grabando

    def detener(self):
        self._cerrar()
        return self._finalizar(self._tasa)


# =====================================================================
#  LLAMADO POR NOMBRE: SAGE solo atiende cuando la llaman
# =====================================================================
# Formas en que Whisper suele escribir "SAGE" (dicho en inglés o en español). Ninguna es una palabra común del español.
# Si en la consola ves "[Escucha] Ignorado" con una forma nueva de escribirlo, añádela en .env: SAGE_NOMBRES=seich,saich
_VARIANTES_NOMBRE = frozenset({
    "sage", "sayge", "saige", "seige", "seyge", "sayj", "seij", "seyj", "seich", "seitch", "saich", "saitch",
    "seidch", "seig", "seyg", "saig", "sayg", "seish", "sech", "saje", "sague", "sahe",
})


def _tokens(texto):
    """Minúsculas, sin tildes ni signos: 'Sagé, ¡abre!' -> ['sage', 'abre']."""
    t = unicodedata.normalize("NFD", (texto or "").lower())
    t = "".join(c for c in t if unicodedata.category(c) != "Mn")
    return re.findall(r"[a-z]+", t)


@lru_cache(maxsize=8)
def _variantes(extra):
    var = set(_VARIANTES_NOMBRE)
    for v in extra.split(","):
        v = "".join(_tokens(v))
        if v: var.add(v)
    return frozenset(var)


_MULETILLAS = frozenset({"oye", "oiga", "hey", "ey", "eh", "hola", "ok", "okay", "okey", "vale", "mira", "buenas"})


def fue_llamada(texto):
    """True solo si el nombre de SAGE va AL PRINCIPIO ("Sage, abre YouTube", "oye sage, ..."): el nombre va antes de la orden.
    Un "sage" suelto en medio o al final de la frase no cuenta."""
    tokens = _tokens(texto)
    var = _variantes(os.getenv("SAGE_NOMBRES", ""))
    i = 0
    while i < len(tokens) and i < 2 and tokens[i] in _MULETILLAS:
        i += 1
    if i < len(tokens) and tokens[i] in var: return True
    if i + 1 < len(tokens) and tokens[i] + tokens[i + 1] in var: return True  # "sei" + "ch" -> "seich"
    return False


def solo_nombre(texto):
    """True si el texto es solo el llamado ("Sage", "oye sage"), sin ninguna orden detrás."""
    tokens = _tokens(texto)
    var = _variantes(os.getenv("SAGE_NOMBRES", ""))
    i = 0
    while i < len(tokens) and i < 2 and tokens[i] in _MULETILLAS:
        i += 1
    if i < len(tokens) and tokens[i] in var: i += 1
    elif i + 1 < len(tokens) and tokens[i] + tokens[i + 1] in var: i += 2
    else: return False
    return i >= len(tokens)


_VOCAB_TOKENS = frozenset(_tokens(VOCABULARIO))


def _es_eco_vocabulario(texto):
    """Con ruido, Whisper a veces 'alucina' el initial_prompt (la lista de vocabulario): eso nunca es una orden."""
    tk = _tokens(texto)
    return len(tk) >= 5 and sum(t in _VOCAB_TOKENS for t in tk) / len(tk) >= 0.85


# =====================================================================
#  WHISPER
# =====================================================================
_modelo = None
_lock_modelo = threading.Lock()
_lock_transcripcion = threading.Lock()


def precargar():
    """Carga el modelo de Whisper en memoria (thread-safe: el calentamiento y la primera transcripción no lo cargan dos veces)."""
    global _modelo
    if _modelo is None:
        with _lock_modelo:
            if _modelo is None:
                from faster_whisper import WhisperModel

                # "medium" = precisión casi humana. Si tu PC va lenta, WHISPER_MODEL=small en .env
                nombre = os.getenv("WHISPER_MODEL", "medium")
                dispositivo = os.getenv("WHISPER_DEVICE", "cpu")
                tipo = "float16" if dispositivo == "cuda" else "int8"
                _modelo = WhisperModel(
                    nombre, device=dispositivo, compute_type=tipo,
                    cpu_threads=os.cpu_count() or 4,
                )
    return _modelo


def _es_alucinacion(texto):
    bajo = texto.lower()
    plano = re.sub(r"[^\wáéíóúüñ ]", "", bajo).strip()
    return plano in _ALUCINACIONES_EXACTAS or any(p in bajo for p in _ALUCINACIONES_PARCIALES)


def transcribir(audio, beam=None):
    """Convierte audio (float32, 16 kHz) en texto. beam: precisión/velocidad (por defecto WHISPER_BEAM, 5)."""
    audio = np.asarray(audio, dtype=np.float32)
    if audio.ndim > 1:
        audio = audio.mean(axis=1)
    if audio.size < FS * 0.3:  # menos de 0.3 s: no hay nada que transcribir
        return ""

    modelo = precargar()
    if beam is None:
        try: beam = max(1, int(os.getenv("WHISPER_BEAM", "5")))
        except ValueError: beam = 5

    # Un solo hilo a la vez: la escucha por nombre y el micrófono manual comparten el mismo modelo.
    with _lock_transcripcion:
        segmentos, _ = modelo.transcribe(
            audio,
            language=os.getenv("WHISPER_LANG", "es") or None,  # WHISPER_LANG vacío = autodetección
            beam_size=beam,
            temperature=0.0,
            condition_on_previous_text=False,
            without_timestamps=True,
            vad_filter=True,
            # No cortar palabras a la mitad y dejar margen de 400 ms
            vad_parameters=dict(min_silence_duration_ms=300, speech_pad_ms=400),
            initial_prompt=VOCABULARIO,
        )
        # `segmentos` es un generador: se consume aquí dentro, con el candado puesto.
        partes = [s.text.strip() for s in segmentos if getattr(s, "no_speech_prob", 0.0) < 0.85]
    texto = " ".join(p for p in partes if p).strip()
    return "" if (_es_alucinacion(texto) or _es_eco_vocabulario(texto)) else texto


# =====================================================================
#  ESCUCHA CONTINUA: solo reacciona si oye "SAGE"
# =====================================================================
ESCUCHA_BLOQUE = 512  # muestras por bloque a 16 kHz (32 ms)


class EscuchaContinua:
    """Escucha el micrófono sin parar y SOLO avisa cuando oye el nombre de SAGE.

    - Detecta frases con un VAD por energía (umbral adaptativo al ruido de fondo).
    - Cada frase se transcribe con Whisper en un hilo aparte y se descarta salvo que contenga "SAGE".
    - bloqueado(): devuelve True mientras SAGE habla, piensa o se graba a mano; durante ese tiempo no se
      atiende nada (así no se escucha a sí misma ni se pisa con otra acción).
    - al_llamado(texto): se invoca desde un hilo con la frase completa cuando la llamaron.
    Ajustes opcionales en .env: ESCUCHA_UMBRAL (volumen mínimo de voz, 0.008) y WHISPER_BEAM_ESCUCHA (2).
    """

    PRE_ROLL = 0.5         # s de audio previo al inicio de la voz (para no cortar la primera sílaba)
    FIN_SILENCIO = 0.8     # s de silencio que cierran una frase
    MIN_VOZ = 0.25         # s mínimos de voz para que valga la pena transcribir
    MAX_ENUNCIADO = 20.0   # s máximos por frase
    VENTANA_ORDEN = 10.0   # s que SAGE espera tu orden después de oír solo su nombre
    COOLDOWN = 0.9         # s de calma tras haber estado bloqueada (cola de la voz de SAGE, ecos)

    def __init__(self, al_llamado, bloqueado=None, al_error=None, al_aviso=None):
        self.al_llamado = al_llamado
        self.al_aviso = al_aviso      # ruidito de «te escucho»
        self._armada_hasta = 0.0      # tras decir solo «SAGE», la siguiente frase es la orden (sin repetir el nombre)
        self.bloqueado = bloqueado or (lambda: False)
        self.al_error = al_error
        self.nivel = 0.0       # volumen RMS actual: la UI lo usa para animar al avatar
        self.activa = False
        self._stream = None
        self._cola = queue.Queue(maxsize=4)
        self._hilo = None
        self._parar = threading.Event()
        self._transcribir = transcribir  # sustituible en pruebas
        self._ult_error = 0.0
        self._bloqueado_hasta = 0.0
        self._piso = 0.003
        try: self.umbral_min = float(os.getenv("ESCUCHA_UMBRAL", "0.008"))
        except ValueError: self.umbral_min = 0.008
        try: self.beam = max(1, int(os.getenv("WHISPER_BEAM_ESCUCHA", "2")))
        except ValueError: self.beam = 2
        self._reiniciar_vad()

    # ---------- control ----------
    def iniciar(self):
        if self.activa:
            return
        self._abrir()
        self.activa = True
        self._parar.clear()
        if self._hilo is None or not self._hilo.is_alive():
            self._hilo = threading.Thread(target=self._trabajar, daemon=True)
            self._hilo.start()

    def detener(self):
        self.activa = False
        self._parar.set()
        self._cerrar()
        self._vaciar_cola()
        self.nivel = 0.0

    def suspender(self):
        """Cierra el micrófono sin desactivar la escucha (la grabación manual lo necesita libre)."""
        if self.activa:
            self._cerrar()
            self.nivel = 0.0

    def reanudar(self):
        if self.activa and self._stream is None:
            try:
                self._abrir()
            except Exception as e:
                self.activa = False
                self._error(f"No pude reabrir el micrófono: {e}")

    # ---------- micrófono ----------
    def _abrir(self):
        import sounddevice as sd  # import aquí para dar un error claro si falta

        self._cerrar()
        self._reiniciar_vad()
        try:
            self._stream = sd.InputStream(
                samplerate=FS, channels=1, dtype="float32", blocksize=ESCUCHA_BLOQUE,
                callback=self._callback, device=_dispositivo_entrada(),
            )
            self._stream.start()
        except Exception:
            self._cerrar()
            raise

    def _cerrar(self):
        if self._stream is not None:
            try:
                self._stream.stop()
                self._stream.close()
            except Exception:
                pass
            self._stream = None

    def _callback(self, indata, frames, tiempo, status):
        try:
            self._procesar_bloque(indata[:, 0])
        except Exception as e:  # una excepción aquí cerraría el stream de audio
            print(f"[Escucha] {e}")

    # ---------- detección de frases (VAD por energía) ----------
    def _reiniciar_vad(self):
        self._pre = deque(maxlen=max(1, int(self.PRE_ROLL * FS / ESCUCHA_BLOQUE) + 1))
        self._hablando = False
        self._buf = []
        self._silencio = 0.0
        self._total = 0.0
        self._voz = 0.0
        self._ruido_seg = 0.0

    def _procesar_bloque(self, mono, ahora=None):
        ahora = time.monotonic() if ahora is None else ahora
        rms = float(np.sqrt(np.mean(np.square(mono)))) if mono.size else 0.0
        self.nivel = rms

        if self.bloqueado():
            self._bloqueado_hasta = ahora + self.COOLDOWN
            self._reiniciar_vad()
            return
        if ahora < self._bloqueado_hasta:
            return

        dur = mono.size / FS
        bloque = np.array(mono, dtype=np.float32, copy=True)
        umbral = max(self.umbral_min, self._piso * 3.0)

        if not self._hablando:
            self._pre.append(bloque)
            if rms > umbral:
                self._ruido_seg += dur
                if self._ruido_seg >= 0.09:  # ~3 bloques seguidos: es voz, no un golpe
                    self._hablando = True
                    self._buf = list(self._pre)
                    self._silencio = 0.0
                    self._total = sum(b.size for b in self._buf) / FS
                    self._voz = self._ruido_seg
            else:
                self._ruido_seg = 0.0
                self._piso += (rms - self._piso) * 0.02  # sigue el ruido de fondo
            return

        self._buf.append(bloque)
        self._total += dur
        if rms > umbral * 0.7:
            self._silencio = 0.0
            self._voz += dur
        else:
            self._silencio += dur
        if self._silencio >= self.FIN_SILENCIO or self._total >= self.MAX_ENUNCIADO:
            audio = np.concatenate(self._buf)
            voz = self._voz
            self._reiniciar_vad()
            if voz >= self.MIN_VOZ:
                self._enviar(audio)

    def _enviar(self, audio):
        try: self._cola.put_nowait(audio)
        except queue.Full: pass  # Whisper va atrasado: se descarta la frase más reciente

    def _vaciar_cola(self):
        while True:
            try: self._cola.get_nowait()
            except queue.Empty: break

    # ---------- transcripción y filtro por nombre ----------
    def _trabajar(self):
        while not self._parar.is_set():
            try: audio = self._cola.get(timeout=0.3)
            except queue.Empty: continue
            if self.bloqueado():
                continue
            try:
                texto = self._transcribir(_normalizar(audio), beam=self.beam)
            except Exception as e:
                self._error(f"Transcripción fallida: {e}")
                continue
            if not texto or self.bloqueado():
                continue  # vacío, o SAGE empezó a hacer otra cosa mientras se transcribía
            ahora = time.monotonic()
            if ahora < self._armada_hasta:                  # ya me llamaste: esta frase es la orden
                self._armada_hasta = 0.0
                self._entregar(texto)
            elif fue_llamada(texto):
                if solo_nombre(texto):                      # solo «SAGE»: aviso y espero la orden
                    self._avisar()
                    self._armada_hasta = time.monotonic() + self.VENTANA_ORDEN
                    print("[Escucha] Llamada detectada: esperando la orden...")
                else:                                       # «SAGE, abre YouTube» en una sola frase
                    self._avisar()
                    self._entregar(texto)
            else:
                print(f"[Escucha] Ignorado (no dijiste SAGE): «{texto}»")

    def _avisar(self):
        if self.al_aviso:
            try: self.al_aviso()
            except Exception as e: print(f"[Escucha] {e}")
        self._bloqueado_hasta = time.monotonic() + 0.8   # que no se escuche a sí misma el ruidito

    def _entregar(self, texto):
        try: self.al_llamado(texto)
        except Exception as e: print(f"[Escucha] {e}")

    def _error(self, msg):
        ahora = time.monotonic()
        if ahora - self._ult_error < 30:  # no inundar el chat si falla en cada frase
            return
        self._ult_error = ahora
        if self.al_error:
            try: self.al_error(msg)
            except Exception: pass
        else:
            print(f"[Escucha] {msg}")
