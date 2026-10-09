import os
import numpy as np
import scipy.signal
import pyaudiowpatch as pyaudio

FS = 16000  # Whisper trabaja a 16 kHz mono
VOCABULARIO = "SAGE, Niko, Nexus, Sonic ReDust, Unreal Engine, Blender, blueprints, shaders, rigging, Fedora."


class Grabadora:
    """Graba de tu micrófono físico (modo normal)."""
    def __init__(self):
        self._frames = []
        self._stream = None
        self.nivel = 0.0

    def iniciar(self):
        import sounddevice as sd
        self._frames = []
        def callback(indata, frames, time, status):
            self._frames.append(indata.copy())
            self.nivel = float(np.sqrt(np.mean(indata ** 2)))
        self._stream = sd.InputStream(
            samplerate=FS, channels=1, dtype="float32", callback=callback
        )
        self._stream.start()

    def detener(self):
        if self._stream is not None:
            self._stream.stop()
            self._stream.close()
            self._stream = None
        self.nivel = 0.0
        if not self._frames:
            return np.zeros(0, dtype=np.float32)
        return np.concatenate(self._frames, axis=0).flatten()


class GrabadoraPC:
    """Graba todo el audio del sistema / Discord (Loopback) y lo resamplea a 16kHz."""
    def __init__(self):
        self._frames = []
        self._p = None
        self._stream = None
        self.nivel = 0.0
        self.native_rate = 44100  # Valor por defecto

    def iniciar(self):
        self._p = pyaudio.PyAudio()
        self._frames = []
        try:
            wasapi_info = self._p.get_host_api_info_by_type(pyaudio.paWASAPI)
            default_speakers = self._p.get_device_info_by_index(wasapi_info["defaultOutputDevice"])
            
            self.native_rate = int(default_speakers["defaultSampleRate"])

            loopback_device = None
            for loopback in self._p.get_loopback_device_info_generator():
                if default_speakers["name"] in loopback["name"]:
                    loopback_device = loopback
                    break
            if not loopback_device:
                loopback_devices = list(self._p.get_loopback_device_info_generator())
                if loopback_devices:
                    loopback_device = loopback_devices[0]

            if not loopback_device:
                raise Exception("No se encontró ningún dispositivo Loopback WASAPI activo.")

            def callback(in_data, frame_count, time_info, status):
                audio_data = np.frombuffer(in_data, dtype=np.float32)
                channels = loopback_device["maxInputChannels"]
                if channels > 1:
                    audio_data = audio_data.reshape(-1, channels).mean(axis=1)
                self._frames.append(audio_data.copy())
                self.nivel = float(np.sqrt(np.mean(audio_data ** 2)))
                return (None, pyaudio.paContinue)

            self._stream = self._p.open(
                format=pyaudio.paFloat32,
                channels=loopback_device["maxInputChannels"],
                rate=self.native_rate,
                input=True,
                input_device_index=loopback_device["index"],
                stream_callback=callback
            )
            self._stream.start_stream()
        except Exception as e:
            print(f"[Error de Loopback PC]: {e}")

    def detener(self):
        if self._stream is not None:
            self._stream.stop_stream()
            self._stream.close()
            self._stream = None
        if self._p is not None:
            self._p.terminate()
            self._p = None
            
        self.nivel = 0.0
        if not self._frames:
            return np.zeros(0, dtype=np.float32)
            
        audio_bruto = np.concatenate(self._frames, axis=0).flatten()
        
        # CONVERSIÓN CRÍTICA: Resamplear de la tasa nativa de la PC a 16kHz exactos para Whisper
        if self.native_rate != FS and audio_bruto.size > 0:
            num_output = int(len(audio_bruto) * FS / self.native_rate)
            audio_resampleado = scipy.signal.resample(audio_bruto, num_output)
            return audio_resampleado.astype(np.float32)
        
        return audio_bruto.astype(np.float32)


_modelo = None


def precargar():
    """Carga el modelo de Whisper en memoria."""
    global _modelo
    if _modelo is None:
        from faster_whisper import WhisperModel

        nombre = os.getenv("WHISPER_MODEL", "base")
        dispositivo = os.getenv("WHISPER_DEVICE", "cpu")
        tipo = "float16" if dispositivo == "cuda" else "int8"
        _modelo = WhisperModel(
            nombre, device=dispositivo, compute_type=tipo,
            cpu_threads=os.cpu_count() or 4,
        )
    return _modelo


def transcribir(audio):
    """Convierte audio (float32, 16 kHz) en texto."""
    if audio.size < FS * 0.3:
        return ""
    
    modelo = precargar()
    segmentos, _ = modelo.transcribe(
        audio,
        language="es",
        beam_size=1,
        temperature=0.0,
        condition_on_previous_text=False,
        without_timestamps=True,
        vad_filter=True,
        vad_parameters=dict(min_silence_duration_ms=300),
        initial_prompt=VOCABULARIO,
    )
    texto = " ".join(s.text.strip() for s in segmentos).strip()
    return texto