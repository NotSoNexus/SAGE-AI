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

VOCABULARIO = "SAGE, Niko, Wiwi, Outcome Memories, Frutiger Aero, Nexus, Cierra, Sonic ReDust, Godot, GDScript, Unreal Engine, Blender, Chill, blueprints, shaders, rigging, open world, play, enter, Discord, YouTube."

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
    if 2e-5 < pico < 0.3:
        audio = audio * min(40.0, 0.6 / pico)
    return audio.astype(np.float32, copy=False)


def _dispositivo_entrada():
    """MIC_DEVICE en .env (índice o nombre) para elegir micrófono; vacío = el predeterminado."""
    val = os.getenv("MIC_DEVICE", "").strip()
    if not val: return None
    try: return int(val)
    except ValueError: return val


def listar_entradas():
    """Los micrófonos que ve el sistema de audio, para diagnosticar: '1: Micrófono (Realtek) [MME]; ...'."""
    try:
        import sounddevice as sd
        dispositivos, apis = sd.query_devices(), sd.query_hostapis()
        return "; ".join(f"{i}: {d['name']} [{apis[d['hostapi']]['name']}]"
                         for i, d in enumerate(dispositivos) if d.get("max_input_channels", 0) > 0) or "(ninguno)"
    except Exception as e:
        return f"(no pude listarlos: {e})"


def candidatos_entrada(sd, excluir=()):
    """Micrófonos a probar, por orden: el de .env (MIC_DEVICE) o el predeterminado, y luego cualquier otra entrada
    (primero las de la misma API de audio que la predeterminada)."""
    cand = [_dispositivo_entrada()]
    try:
        dispositivos = sd.query_devices()
        pred = sd.default.device[0]
        host_def = dispositivos[pred]["hostapi"] if pred is not None and pred >= 0 else -1
        entradas = [(0 if d.get("hostapi") == host_def else 1, i) for i, d in enumerate(dispositivos) if d.get("max_input_channels", 0) > 0]
        cand += [i for _, i in sorted(entradas)]
    except Exception:
        pass
    vistos, res = set(), []
    for c in cand:
        if c not in vistos and c not in excluir:
            vistos.add(c)
            res.append(c)
    return res


def abrir_entrada(recibir, bloque_fs=None, excluir=()):
    """Abre el primer micrófono que funcione y llama a recibir(mono, tasa) con cada bloque (ya mezclado a mono).
    Prueba: el micrófono elegido/predeterminado y luego los demás; la tasa de 16 kHz y la nativa del dispositivo
    (muchos micrófonos de Windows no admiten 16 kHz); estéreo mezclado a mono (si el canal 0 está vacío no se pierde la voz).
    Devuelve (stream, dispositivo, nombre, tasa, es_alternativo)."""
    import sounddevice as sd  # import aquí para dar un error claro si falta

    ultimo, primero = None, True
    for dev in candidatos_entrada(sd, excluir):
        try:
            info = sd.query_devices(dev, "input")
        except Exception as e:
            ultimo, primero = e, False
            continue
        canales = max(1, min(2, int(info.get("max_input_channels", 1) or 1)))
        tasas = [FS]
        nativa = int(info.get("default_samplerate", 0) or 0)
        if nativa and nativa != FS: tasas.append(nativa)
        for tasa in tasas:
            for ch in ([canales] if canales == 1 else [canales, 1]):
                stream = None

                def cb(indata, frames, tiempo, status, tasa=tasa):
                    recibir(indata.mean(axis=1) if indata.shape[1] > 1 else indata[:, 0], tasa)

                try:
                    bloque = int(round(bloque_fs * tasa / FS)) if bloque_fs else 0
                    stream = sd.InputStream(samplerate=tasa, channels=ch, dtype="float32", blocksize=bloque, callback=cb, device=dev)
                    stream.start()
                    return stream, dev, str(info.get("name", dev)), tasa, not primero
                except Exception as e:
                    ultimo = e
                    if stream is not None:
                        try: stream.close()
                        except Exception: pass
        primero = False
    raise RuntimeError(f"No pude abrir ningún micrófono: {ultimo}")


class _GrabadoraBase:
    def __init__(self):
        self._frames = []
        self._muestras = 0
        self._tasa = FS
        self.pico = 0.0   # volumen máximo de la última grabación (sin normalizar): 0 = el micrófono no envió nada
        self.nombre = ""
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
            self.pico = 0.0
            return np.zeros(0, dtype=np.float32)
        audio = np.concatenate(self._frames)
        self.pico = float(np.max(np.abs(audio))) if audio.size else 0.0
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
        self._cerrar()  # evita fugas si se llama dos veces seguidas
        self._reiniciar()
        try:
            self._stream, _, self.nombre, self._tasa, _ = abrir_entrada(self._acumular)
            print(f"[Micrófono] Grabando con: {self.nombre} ({self._tasa} Hz)")
        except Exception:
            self._cerrar()
            raise

    def detener(self):
        self._cerrar()
        return self._finalizar(self._tasa)


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

                # "small" = ~3x más rápido que "medium" con muy buena precisión en español. Para máxima precisión: WHISPER_MODEL=medium en .env
                nombre = os.getenv("WHISPER_MODEL", "small")
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
    """Convierte audio (float32, 16 kHz) en texto. beam: precisión/velocidad (por defecto WHISPER_BEAM, 2)."""
    audio = np.asarray(audio, dtype=np.float32)
    if audio.ndim > 1:
        audio = audio.mean(axis=1)
    if audio.size < FS * 0.3:  # menos de 0.3 s: no hay nada que transcribir
        return ""

    modelo = precargar()
    if beam is None:
        try: beam = max(1, int(os.getenv("WHISPER_BEAM", "2")))
        except ValueError: beam = 2

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
            # No cortar palabras a la mitad y dejar margen de 400 ms; umbral más bajo para no tirar voz suave
            vad_parameters=dict(threshold=0.35, min_silence_duration_ms=200, speech_pad_ms=250),
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
    Ajustes opcionales en .env: ESCUCHA_UMBRAL (volumen mínimo de voz, 0.002; el umbral real se adapta solo al ruido de
    fondo), MIC_DEVICE (micrófono concreto), ESCUCHA_DEBUG=1 (imprime el nivel del micrófono) y WHISPER_BEAM_ESCUCHA.
    """

    PRE_ROLL = 0.5         # s de audio previo al inicio de la voz (para no cortar la primera sílaba)
    FIN_SILENCIO = 0.55    # s de silencio que cierran una frase
    MIN_VOZ = 0.25         # s mínimos de voz para que valga la pena transcribir
    MAX_ENUNCIADO = 20.0   # s máximos por frase
    VENTANA_ORDEN = 10.0   # s que SAGE espera tu orden después de oír solo su nombre
    COOLDOWN = 0.5         # s de calma tras haber estado bloqueada (cola de la voz de SAGE, ecos)
    GRACIA_HABLA = 0.35    # s al empezar a hablar SAGE en los que solo se mide su eco (sin interrumpir)
    FACTOR_ECO = 2.2       # tu voz debe superar el eco medido de SAGE por este factor

    def __init__(self, al_llamado, bloqueado=None, al_error=None, al_aviso=None, interrumpible=None, al_interrumpir=None):
        self.interrumpible = interrumpible      # () -> True mientras SAGE está hablando y se la puede cortar
        self.al_interrumpir = al_interrumpir    # () -> se invoca (hilo de audio) cuando empiezas a hablar encima de ella
        try: self.umbral_interrupcion = float(os.getenv("SAGE_INTERRUMPIR_UMBRAL", "0.035"))
        except ValueError: self.umbral_interrupcion = 0.035
        try: self.min_interrupcion = max(0.1, float(os.getenv("SAGE_INTERRUMPIR_MS", "250")) / 1000.0)
        except ValueError: self.min_interrupcion = 0.25
        if os.getenv("SAGE_INTERRUMPIR", "1").strip() == "0": self.al_interrumpir = None
        self._eco = 0.0
        self._voz_encima = 0.0
        self._sage_hablaba = False
        self._t_habla = 0.0
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
        self._piso = 0.001
        try: self.umbral_min = float(os.getenv("ESCUCHA_UMBRAL", "0.002"))
        except ValueError: self.umbral_min = 0.002
        self._tasa = FS               # tasa real con la que se abrió el micrófono (si no admite 16 kHz se remuestrea)
        self._nombre_disp = ""
        self._ult_bloque = 0.0        # cuándo llegó el último bloque de audio (vigilancia del stream)
        self._t_abierto = 0.0
        self._max_rms = 0.0           # volumen máximo desde que se abrió (detecta un micrófono mudo)
        self._t_debug = 0.0
        self._debug = os.getenv("ESCUCHA_DEBUG", "").strip() == "1"
        try: self.beam = max(1, int(os.getenv("WHISPER_BEAM_ESCUCHA", "1")))
        except ValueError: self.beam = 1
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
        self._cerrar()
        self._reiniciar_vad()
        try:
            stream, dev, nombre, tasa, alterno = abrir_entrada(self._recibir, ESCUCHA_BLOQUE)
        except Exception:
            self._cerrar()
            raise
        self._stream, self._nombre_disp, self._tasa = stream, nombre, tasa
        self._ult_bloque = self._t_abierto = time.monotonic()
        self._max_rms = 0.0
        print(f"[Escucha] Micrófono en uso: {nombre} ({tasa} Hz)")
        if alterno:
            self._error(f"El micrófono predeterminado no se pudo abrir; uso «{nombre}». "
                        "Si no es el correcto, pon MIC_DEVICE=<nombre o número> en .env.")

    def _cerrar(self):
        if self._stream is not None:
            try:
                self._stream.stop()
                self._stream.close()
            except Exception:
                pass
            self._stream = None

    def _recibir(self, mono, tasa):
        try:
            self._ult_bloque = time.monotonic()
            if tasa != FS:
                mono = _remuestrear(np.array(mono, dtype=np.float32, copy=True), tasa)
            self._procesar_bloque(mono)
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
        if rms > self._max_rms: self._max_rms = rms

        if self.bloqueado():
            if self.al_interrumpir and self.interrumpible and self.interrumpible():
                if self._vigilar_interrupcion(mono, rms, ahora):
                    return
                # sigue bloqueada, pero conserva el pre-roll (self._pre) para no perder tus primeras sílabas
                self._hablando, self._buf, self._ruido_seg = False, [], 0.0
                self._bloqueado_hasta = ahora + self.COOLDOWN
                return
            self._sage_hablaba = False
            self._bloqueado_hasta = ahora + self.COOLDOWN
            self._reiniciar_vad()
            return
        self._sage_hablaba = False
        self._voz_encima = 0.0
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
        if self._total > 6.0:   # una "frase" tan larga suele ser ruido continuo: que el umbral suba y deje de dispararse
            self._piso += (rms - self._piso) * 0.004
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

    def _vigilar_interrupcion(self, mono, rms, ahora):
        """SAGE está hablando: si empiezas a hablar encima (sostenido, más fuerte que su propio eco) la corta
        y empieza a capturar tu frase con el pre-roll. Devuelve True si interrumpió."""
        self._pre.append(np.array(mono, dtype=np.float32, copy=True))
        dur = mono.size / FS
        if not self._sage_hablaba:                      # acaba de empezar a hablar: medir su eco antes de juzgar
            self._sage_hablaba, self._t_habla, self._eco, self._voz_encima = True, ahora, 0.0, 0.0
        if ahora - self._t_habla < self.GRACIA_HABLA:
            self._eco += (rms - self._eco) * 0.3
            return False
        umbral = max(self.umbral_interrupcion, self._eco * self.FACTOR_ECO)
        if rms <= umbral:
            self._eco += (rms - self._eco) * 0.03
            self._voz_encima = 0.0
            return False
        self._voz_encima += dur
        if self._voz_encima < self.min_interrupcion:
            return False

        n = int((self.min_interrupcion + 0.15) * FS / ESCUCHA_BLOQUE) + 1
        self._buf = list(self._pre)[-n:]
        self._hablando = True
        self._silencio = 0.0
        self._ruido_seg = 0.0
        self._total = sum(b.size for b in self._buf) / FS
        self._voz = self._voz_encima
        self._voz_encima = 0.0
        self._sage_hablaba = False
        self._bloqueado_hasta = 0.0
        print("[Escucha] Interrupción por voz: SAGE se calla.")
        try: self.al_interrumpir()
        except Exception as e: print(f"[Escucha] {e}")
        return True

    def _enviar(self, audio):
        try: self._cola.put_nowait(audio)
        except queue.Full: pass  # Whisper va atrasado: se descarta la frase más reciente

    def _vaciar_cola(self):
        while True:
            try: self._cola.get_nowait()
            except queue.Empty: break

    # ---------- transcripción y filtro por nombre ----------
    def _vigilar_micro(self):
        """Detecta un micrófono que se quedó mudo (desenchufado, cambio de dispositivo, permisos) y lo reabre."""
        try:
            if not self.activa or self._stream is None:
                return
            ahora = time.monotonic()
            if self._debug and ahora - self._t_debug > 2.0:
                self._t_debug = ahora
                print(f"[Escucha] «{self._nombre_disp}» nivel={self.nivel:.4f} máx={self._max_rms:.4f} "
                      f"ruido={self._piso:.4f} umbral={max(self.umbral_min, self._piso * 3.0):.4f}")
            if ahora - self._ult_bloque > 4.0:        # el stream dejó de entregar audio
                self._error("El micrófono dejó de enviar audio; lo reabro...")
                self._ult_bloque = ahora
                try: self._abrir()
                except Exception as e:
                    self.activa = False
                    self._error(f"No pude reabrir el micrófono: {e}")
            elif self._max_rms < 1e-5 and ahora - self._t_abierto > 8.0:    # abierto pero silencio digital absoluto
                self._t_abierto = ahora
                self._error(f"El micrófono «{self._nombre_disp}» solo entrega silencio absoluto. Revisa que no esté silenciado y que en Windows > "
                            "Configuración > Privacidad y seguridad > Micrófono estén activados «Acceso al micrófono» y «Permitir que las aplicaciones "
                            f"de escritorio accedan a tu micrófono». Para usar otro, pon MIC_DEVICE=<número o nombre> en .env. Entradas: {listar_entradas()}")
        except Exception as e:
            print(f"[Escucha] vigilancia: {e}")

    def _trabajar(self):
        while not self._parar.is_set():
            self._vigilar_micro()
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
