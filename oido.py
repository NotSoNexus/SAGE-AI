import os
import re
import sys
import math
import threading

import numpy as np

FS = 16000  # Whisper trabaja a 16 kHz mono
MAX_SEGUNDOS = 300  # tope de grabación para no llenar la RAM

VOCABULARIO = "SAGE, Niko, Wiwi, Nexus, Sonic ReDust, Godot, GDScript, Unreal Engine, Blender, Chill, blueprints, shaders, rigging, open world, play, enter, Discord, YouTube."

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
#  WHISPER
# =====================================================================
_modelo = None
_lock_modelo = threading.Lock()


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


def transcribir(audio):
    """Convierte audio (float32, 16 kHz) en texto."""
    audio = np.asarray(audio, dtype=np.float32)
    if audio.ndim > 1:
        audio = audio.mean(axis=1)
    if audio.size < FS * 0.3:  # menos de 0.3 s: no hay nada que transcribir
        return ""

    modelo = precargar()
    try: beam = max(1, int(os.getenv("WHISPER_BEAM", "5")))
    except ValueError: beam = 5

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
    partes = [s.text.strip() for s in segmentos if getattr(s, "no_speech_prob", 0.0) < 0.85]
    texto = " ".join(p for p in partes if p).strip()
    return "" if _es_alucinacion(texto) else texto
