"""Comentarista de SAGE: mira tu pantalla de forma continua y opina EN TIEMPO REAL, como un streamer que ve contigo.

Cómo funciona (y qué NO es):
- Toma una captura cada ~1.5 s, pero solo la ANALIZA con el modelo cuando la pantalla cambió de verdad y pasó el intervalo mínimo
  (20 s normal, 10 s si detecta Geometry Dash u Outcome Memories; un cambio brusco, p. ej. morir o cambiar de mapa, adelanta el comentario).
  Son capturas periódicas (2 fotogramas con ~1 s de diferencia), no vídeo continuo.
- Al detectar Geometry Dash / Outcome Memories añade a su prompt el conocimiento de ese juego (gd_conocimiento / outcome_conocimiento).
- Un OJITO diminuto (abajo a la derecha, transparente al mouse y excluido de las capturas) parpadea cada vez que SAGE mira y brilla
  mientras analiza: si no parpadea, no está mirando.
- No mira cuando SAGE está ocupada (habla, escucha, ejecuta), cuando la ventana activa es la propia SAGE o una sensible
  (contraseñas, bancos, gestores de claves, incógnito...). Límite por hora para no gastar cuota de la API.
- Apagado por defecto: «sé mi comentarista» / Ctrl+Shift+C lo enciende; «deja de comentar» lo apaga. SAGE_COMENTARISTA=1 en .env lo enciende al arrancar.
- OUTCOME MEMORIES: lo reconoce SOLO (título de la ventana o el placeId de los registros de Roblox, ver outcome_deteccion.py) y entra en modo «stun»:
  muestrea la pantalla de forma continua (~cada 0.7 s) y cada ~4 s (o antes si hay un cambio brusco) manda al modelo 3 capturas que cubren TODO ese tramo,
  así un stun que ocurre entre dos análisis también se ve. Cuando hay un stun, SAGE reacciona al instante: frase corta en voz alta, rebote del avatar y felicidad.
  No es magia: depende de que el modelo reconozca el stun en las capturas, así que puede perderse alguno. SAGE_OUTCOME_AUTO=1 enciende el comentarista sola al detectar el juego.

Ajustes opcionales en .env: SAGE_COMENTARISTA_INTERVALO=20, SAGE_COMENTARISTA_INTERVALO_JUEGO=10, SAGE_COMENTARISTA_UMBRAL=0.02,
SAGE_COMENTARISTA_FRAMES=2, SAGE_COMENTARISTA_MAX_HORA=120, SAGE_COMENTARISTA_IGNORAR=palabra1,palabra2 (ventanas que nunca mira),
SAGE_OJO=0 (sin ojito), SAGE_OJO_TAM=16 (px), SAGE_OJO_OPACIDAD=0.45.
Modo Outcome: SAGE_COMENTARISTA_INTERVALO_OUTCOME=4, SAGE_COMENTARISTA_EVENTO_OUTCOME=0.10 (salto de cambio entre capturas que cuenta como «algo pasó»),
SAGE_COMENTARISTA_GAP_STUN=3 (s mínimos entre dos reacciones), SAGE_COMENTARISTA_FRAMES_OUTCOME=3, SAGE_COMENTARISTA_MAX_HORA_OUTCOME=360, SAGE_OUTCOME_AUTO=0/1.
"""
import os
import sys
import math
import random
import time
import threading
from collections import deque

from PySide6.QtCore import Qt, QThread, Signal, QTimer, QPointF
from PySide6.QtGui import QPainter, QColor, QPen, QPainterPath, QBrush
from PySide6.QtWidgets import QWidget, QApplication

import ojos
import outcome_deteccion

# Ventanas que SAGE nunca mira (se compara en minúsculas contra el título de la ventana activa)
_SENSIBLES = (
    "contraseña", "contrasena", "password", "passwd", "iniciar sesión", "iniciar sesion", "inicio de sesión", "sign in", "log in", "login",
    "banco", "bank", "paypal", "tarjeta de", "keepass", "bitwarden", "1password", "lastpass", "dashlane", "authenticator",
    "incógnito", "incognito", "inprivate", "metamask", "wallet", "cartera",
)


def _env_num(nombre, defecto, minimo, maximo):
    try:
        return max(minimo, min(maximo, float(os.getenv(nombre, defecto))))
    except ValueError:
        return defecto


def titulo_ventana_activa():
    """Título de la ventana en primer plano (solo Windows; en otros sistemas devuelve «» y no se filtra nada)."""
    if sys.platform != "win32":
        return ""
    try:
        import ctypes
        u = ctypes.windll.user32
        n = u.GetWindowTextLengthW(u.GetForegroundWindow())
        if n <= 0:
            return ""
        buf = ctypes.create_unicode_buffer(n + 1)
        u.GetWindowTextW(u.GetForegroundWindow(), buf, n + 1)
        return buf.value
    except Exception:
        return ""


_REACCIONES_STUN = ("¡Stun!", "¡Lo aturdiste!", "¡Buen stun!", "¡Eso, stun!", "¡Toma stun!", "¡Stun limpio!")
_MUESTREO_OUTCOME = 0.7   # s entre capturas en modo Outcome (barato: solo se guardan; al modelo van pocas)


class Comentarista(QThread):
    """Hilo de vigilancia. `ocupado()` (lo da la app) dice si SAGE está haciendo otra cosa: entonces no mira ni comenta.
    `ocupado_sin_voz()` es lo mismo pero ignorando su PROPIA voz de comentarista: en Outcome sigue mirando mientras habla para no perderse un stun."""
    comentario = Signal(str, str)   # (texto, juego detectado: "gd" / "outcome" / "")
    stun = Signal(str)              # reacción inmediata a un stun en Outcome Memories (texto corto)
    detectado = Signal(str)         # juego reconocido por primera vez ("outcome")
    auto = Signal(bool)             # SAGE_OUTCOME_AUTO: encender / apagar el comentarista porque empezó / terminó Outcome
    latido = Signal(str)            # "captura" | "analizando" | "ok" | "espera" | "pausa" | "off"

    def __init__(self, cerebro, ocupado, ocupado_sin_voz=None):
        super().__init__()
        self.cerebro = cerebro
        self._ocupado = ocupado
        self._ocupado_sin_voz = ocupado_sin_voz
        self._activo = threading.Event()
        self._parar = threading.Event()
        self.intervalo = _env_num("SAGE_COMENTARISTA_INTERVALO", 20.0, 5.0, 600.0)
        self.intervalo_juego = _env_num("SAGE_COMENTARISTA_INTERVALO_JUEGO", 10.0, 4.0, 600.0)
        self.umbral = _env_num("SAGE_COMENTARISTA_UMBRAL", 0.02, 0.002, 0.5)
        self.frames = int(_env_num("SAGE_COMENTARISTA_FRAMES", 2, 1, 3))
        self.max_hora = int(_env_num("SAGE_COMENTARISTA_MAX_HORA", 120, 5, 2000))
        # Modo Outcome Memories (stuns)
        self.intervalo_outcome = _env_num("SAGE_COMENTARISTA_INTERVALO_OUTCOME", 4.0, 2.0, 600.0)
        self.umbral_evento = _env_num("SAGE_COMENTARISTA_EVENTO_OUTCOME", 0.10, 0.02, 0.9)
        self.gap_stun = _env_num("SAGE_COMENTARISTA_GAP_STUN", 3.0, 1.0, 60.0)
        self.frames_outcome = int(_env_num("SAGE_COMENTARISTA_FRAMES_OUTCOME", 3, 1, 4))
        self.max_hora_outcome = int(_env_num("SAGE_COMENTARISTA_MAX_HORA_OUTCOME", 360, 20, 5000))
        self.auto_outcome = os.getenv("SAGE_OUTCOME_AUTO", "0").strip() == "1"
        extra = [p.strip().lower() for p in os.getenv("SAGE_COMENTARISTA_IGNORAR", "").split(",") if p.strip()]
        self._sensibles = _SENSIBLES + tuple(extra)
        self._juego = ""            # "gd" / "outcome" / "" (lo dice la detección local o el modelo)
        self._fijo = False          # True si «outcome» viene de la detección local (el modelo no lo desmiente)
        self._huella = None         # huella de la última pantalla analizada
        self._t_analisis = 0.0
        self._previos = []          # últimos comentarios (para no repetirse)
        self._llamadas = deque()    # marcas de tiempo de las llamadas al modelo (límite por hora)
        self._hasta = 0.0           # enfriamiento tras un error o un límite de cuota
        self._recientes = deque(maxlen=12)   # (t, imagen reducida) de las últimas capturas del modo Outcome
        self._difs = deque(maxlen=25)        # cambio entre capturas consecutivas (para detectar picos)
        self._ultima_huella = None
        self._t_blink = 0.0
        self._t_stun = -1e9
        self._auto_visto = False
        self._auto_encendido = False

    # ---------- control ----------
    @property
    def activo(self):
        return self._activo.is_set()

    def activar(self, on):
        if on:
            self._huella = None
            self._ultima_huella = None
            self._recientes.clear()
            self._difs.clear()
            self._t_analisis = time.monotonic() - self.intervalo + 4.0   # el primer comentario llega en ~4 s
            self._activo.set()
        else:
            self._activo.clear()
            self._auto_encendido = False
            self.latido.emit("off")

    def detener(self):
        self._parar.set()
        self._activo.set()   # despierta el bucle para que vea la orden de parar

    # ---------- bucle ----------
    def run(self):
        t_vig = 0.0
        while not self._parar.is_set():
            if not self._activo.is_set():
                if self.auto_outcome and time.monotonic() - t_vig > 10.0:   # apagado: solo comprueba (sin mirar la pantalla) si empezó Outcome
                    t_vig = time.monotonic()
                    try:
                        self._vigilar_auto()
                    except Exception as e:
                        print(f"[Comentarista] auto: {e}")
                self._activo.wait(0.5)
                continue
            try:
                espera = self._ciclo()
            except Exception as e:
                print(f"[Comentarista] {e}")
                espera = 5.0
            self._parar.wait(espera)

    def _vigilar_auto(self):
        det = outcome_deteccion.esta_jugando_outcome(titulo_ventana_activa())
        if det is True and not self._auto_visto:
            self._auto_visto = self._auto_encendido = True
            self.auto.emit(True)
        elif det is False:
            self._auto_visto = False

    def _es_sensible(self, titulo):
        bajo = titulo.lower()
        return any(p in bajo for p in self._sensibles)

    # ---------- reconocer el juego ----------
    def _detectar(self, titulo):
        """Outcome Memories sin gastar el modelo (título de la ventana o registros de Roblox). True / False / None."""
        det = outcome_deteccion.esta_jugando_outcome(titulo)
        if det is True:
            self._fijo = True
            self._poner_juego("outcome")
        elif det is False and self._fijo:        # dejó de jugarlo
            self._fijo = False
            if self._juego == "outcome":
                self._juego = ""
            if self._auto_encendido:             # el comentarista se encendió solo por Outcome: se apaga solo
                self._auto_encendido = self._auto_visto = False
                self.auto.emit(False)
        return det

    def _poner_juego(self, valor):
        nuevo = valor if valor in ("gd", "outcome") else ""
        if self._fijo:
            nuevo = "outcome"
        if nuevo != self._juego:
            self._juego = nuevo
            if nuevo == "outcome":
                self.detectado.emit("outcome")

    # ---------- un ciclo ----------
    def _ciclo(self):
        ahora = time.monotonic()
        if ahora < self._hasta:
            self.latido.emit("espera")
            return 2.0
        titulo = titulo_ventana_activa()
        if "SAGE //" in titulo:               # su propia ventana: comentaría sus propios comentarios en bucle
            self.latido.emit("espera")
            return 2.0
        if self._es_sensible(titulo):
            self._huella = self._ultima_huella = None
            self._recientes.clear()
            self.latido.emit("pausa")
            return 2.5

        self._detectar(titulo)
        en_outcome = self._juego == "outcome"
        busy = self._ocupado_sin_voz if (en_outcome and self._ocupado_sin_voz) else self._ocupado
        if busy():
            self.latido.emit("espera")
            return 1.5

        img = ojos.capturar()
        if img is None:
            return 3.0
        huella = ojos.huella(img)
        if en_outcome:
            return self._ciclo_outcome(ahora, titulo, img, huella, busy)
        return self._ciclo_general(ahora, titulo, img, huella)

    def _ciclo_general(self, ahora, titulo, img, huella):
        self.latido.emit("captura")           # el ojito parpadea: SAGE acaba de mirar
        cambio = ojos.diferencia(self._huella, huella) if self._huella is not None else 1.0
        desde = ahora - self._t_analisis
        interv = self.intervalo_juego if self._juego else self.intervalo
        evento = cambio > 0.40 and desde > 5.0   # cambio brusco (morir, nuevo mapa, otra app...): no esperar el intervalo
        if not evento:
            if cambio < self.umbral:
                return 1.5                      # nada nuevo en pantalla
            if desde < interv:
                return 1.0

        while self._llamadas and ahora - self._llamadas[0] > 3600:
            self._llamadas.popleft()
        if len(self._llamadas) >= self.max_hora:
            self.latido.emit("espera")
            return 10.0                         # tope por hora alcanzado

        frames = [img]
        if self.frames > 1:
            for _ in range(self.frames - 1):
                time.sleep(0.8)
                extra = ojos.capturar()
                if extra is not None:
                    frames.append(extra)

        self.latido.emit("analizando")
        self._llamadas.append(ahora)
        self._t_analisis = time.monotonic()
        self._huella = huella
        res = self.cerebro.comentar_pantalla(frames, titulo, self._juego, list(self._previos))
        if res is None:
            self._hasta = time.monotonic() + 30.0   # fallo o cuota: se calla un rato
            self.latido.emit("espera")
            return 5.0

        self._poner_juego(res["juego"])
        self.latido.emit("ok")
        texto = res["comentario"]
        if texto and self._activo.is_set() and not self._parar.is_set() and not self._ocupado():
            self._previos = (self._previos + [texto])[-5:]
            self.comentario.emit(texto, self._juego)
        return 1.0

    # ---------- modo Outcome Memories: reaccionar a los stuns ----------
    def _ciclo_outcome(self, ahora, titulo, img, huella, busy):
        # Muestreo continuo y barato: cada captura va a un búfer. Al modelo van pocas, pero cubren TODO el tramo desde el último análisis.
        peq = img.copy()
        peq.thumbnail((960, 960))
        d_cons = ojos.diferencia(self._ultima_huella, huella) if self._ultima_huella is not None else 0.0
        self._ultima_huella = huella
        self._recientes.append((ahora, peq))
        if ahora - self._t_blink > 3.0:
            self._t_blink = ahora
            self.latido.emit("captura")

        pico = False                           # cambio brusco entre capturas consecutivas (destello, golpe...)
        if len(self._difs) >= 8:
            mediana = sorted(self._difs)[len(self._difs) // 2]
            pico = d_cons > max(self.umbral_evento, 2.0 * mediana)
        self._difs.append(d_cons)

        desde = ahora - self._t_analisis
        evento = pico and desde >= max(self.gap_stun, 1.5)
        if not (desde >= self.intervalo_outcome or evento):
            return _MUESTREO_OUTCOME
        if not evento and self._huella is not None and ojos.diferencia(self._huella, huella) < self.umbral:
            return _MUESTREO_OUTCOME            # pantalla quieta (menú, pausa): nada que mirar

        while self._llamadas and ahora - self._llamadas[0] > 3600:
            self._llamadas.popleft()
        if len(self._llamadas) >= self.max_hora_outcome:
            self.latido.emit("espera")
            return 10.0

        marcos = [(t, im) for t, im in self._recientes if t > self._t_analisis - 0.1] or list(self._recientes)[-1:]
        n = self.frames_outcome
        if len(marcos) > n:                     # n capturas repartidas por todo el tramo (primera, intermedias, última)
            idx = sorted({round(k * (len(marcos) - 1) / (n - 1)) for k in range(n)}) if n > 1 else [len(marcos) - 1]
            marcos = [marcos[k] for k in idx]
        segundos = marcos[-1][0] - marcos[0][0]
        frames = [im for _, im in marcos]
        ultimo = self._recientes[-1]
        self._recientes.clear()                 # cada captura se usa una sola vez: así un mismo stun no se cuenta dos veces
        self._recientes.append(ultimo)

        self.latido.emit("analizando")
        self._llamadas.append(ahora)
        self._t_analisis = time.monotonic()
        self._huella = huella
        res = self.cerebro.comentar_pantalla(frames, titulo, self._juego, list(self._previos), segundos=segundos, evento=evento)
        if res is None:
            self._hasta = time.monotonic() + 30.0
            self.latido.emit("espera")
            return 5.0

        self._poner_juego(res["juego"])
        self.latido.emit("ok")
        texto = res["comentario"]
        vivo = self._activo.is_set() and not self._parar.is_set()
        if res.get("stun") and self._juego == "outcome":
            if vivo and not busy() and time.monotonic() - self._t_stun >= self.gap_stun:
                self._t_stun = time.monotonic()
                texto = texto or random.choice(_REACCIONES_STUN)
                self._previos = (self._previos + [texto])[-5:]
                self.stun.emit(texto)
        elif texto and vivo and not self._ocupado():
            self._previos = (self._previos + [texto])[-5:]
            self.comentario.emit(texto, self._juego)
        return _MUESTREO_OUTCOME


class OjoPantalla(QWidget):
    """El ojito: un ojo diminuto y casi transparente. Parpadea cada vez que SAGE mira la pantalla, brilla (naranja) mientras
    analiza, se pone gris si pausa por una ventana sensible o porque está ocupada. Transparente al mouse, sin foco y
    excluido de las capturas de SAGE (en Windows), así que ni estorba ni sale en lo que ella ve."""

    def __init__(self):
        super().__init__(None, Qt.WindowType.Tool | Qt.WindowType.FramelessWindowHint
                         | Qt.WindowType.WindowStaysOnTopHint | Qt.WindowType.WindowDoesNotAcceptFocus)
        self.setAttribute(Qt.WidgetAttribute.WA_ShowWithoutActivating)
        self.setAttribute(Qt.WidgetAttribute.WA_TransparentForMouseEvents)
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground)
        self._tam = int(_env_num("SAGE_OJO_TAM", 16, 10, 40))
        self._base = _env_num("SAGE_OJO_OPACIDAD", 0.45, 0.1, 1.0)
        self._activado = os.getenv("SAGE_OJO", "1").strip() != "0"
        self.setFixedSize(self._tam * 2, self._tam)
        self.setWindowOpacity(self._base)
        self.estado = "off"
        self.t = 0.0
        self._t_parpadeo = -10.0
        self._afinidad = False
        self._timer = QTimer(self)
        self._timer.timeout.connect(self._tick)

    # ---------- estado ----------
    def set_estado(self, estado):
        if estado == "captura":
            self._t_parpadeo = self.t          # parpadeo: la señal de «acabo de mirar»
            if self.estado == "analizando":
                return
        self.estado = estado
        if estado == "off":
            self.ocultar()
            return
        self.setWindowOpacity(min(1.0, self._base + 0.45) if estado == "analizando" else self._base)

    def mostrar(self):
        if not self._activado:
            return
        pantalla = QApplication.primaryScreen()
        if pantalla is None:
            return
        g = pantalla.availableGeometry()      # junto al puntito de SAGE, justo encima de la barra de tareas
        self.move(g.right() - self.width() - 56, g.bottom() - self.height() - 12)
        if not self.isVisible():
            self.show()
            self._timer.start(40)
            if sys.platform == "win32" and not self._afinidad:
                try:  # WDA_EXCLUDEFROMCAPTURE: no sale en las capturas de SAGE
                    import ctypes
                    ctypes.windll.user32.SetWindowDisplayAffinity(int(self.winId()), 0x11)
                    self._afinidad = True
                except Exception:
                    pass
        self.estado = "espera" if self.estado == "off" else self.estado

    def ocultar(self):
        if self.isVisible():
            self._timer.stop()
            self.hide()

    def _tick(self):
        self.t += 0.04
        self.update()

    # ---------- dibujo ----------
    def paintEvent(self, ev):
        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.Antialiasing)
        w, h = float(self.width()), float(self.height())
        cx, cy = w / 2, h / 2

        # Color y apertura según el estado
        if self.estado == "analizando":
            color = QColor(255, 170, 0)
            pulso = 0.5 + 0.5 * math.sin(self.t * 9)
        elif self.estado in ("pausa", "espera"):
            color = QColor(150, 160, 170)
            pulso = 0.0
        else:
            color = QColor(0, 243, 255)
            pulso = 0.5 + 0.5 * math.sin(self.t * 2)

        # Parpadeo: el párpado se cierra y abre en 0.22 s tras cada captura
        k = (self.t - self._t_parpadeo) / 0.22
        abierto = 1.0 if not (0.0 <= k <= 1.0) else abs(math.cos(k * math.pi))
        abierto = max(0.08, abierto)

        ancho, alto = w * 0.84, h * 0.46 * abierto
        ojo = QPainterPath()
        ojo.moveTo(cx - ancho / 2, cy)
        ojo.quadTo(cx, cy - alto * 1.9, cx + ancho / 2, cy)
        ojo.quadTo(cx, cy + alto * 1.9, cx - ancho / 2, cy)

        p.setPen(Qt.PenStyle.NoPen)
        p.setBrush(QColor(0, 0, 0, 90))      # base oscura: se ve sobre fondos claros y oscuros
        p.drawPath(ojo)
        pen = QPen(color)
        pen.setWidthF(max(1.2, h * 0.09))
        p.setPen(pen)
        p.setBrush(Qt.BrushStyle.NoBrush)
        p.drawPath(ojo)

        if abierto > 0.35:                    # iris + pupila
            r = h * 0.2 * (0.95 + 0.1 * pulso)
            p.setPen(Qt.PenStyle.NoPen)
            iris = QColor(color)
            iris.setAlpha(int(190 + 60 * pulso))
            p.setBrush(QBrush(iris))
            p.drawEllipse(QPointF(cx, cy), r, r)
            p.setBrush(QColor(0, 0, 0, 220))
            p.drawEllipse(QPointF(cx, cy), r * 0.45, r * 0.45)
