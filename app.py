import os
import re
import sys
import math
import time
import random
import subprocess
from functools import lru_cache
from urllib.parse import urlparse

from PySide6.QtCore import (
    Qt, QTimer, QThread, Signal, QPointF, QRectF, QLineF, QSize,
    QVariantAnimation, QEasingCurve, QPropertyAnimation,
)
from PySide6.QtGui import (
    QPainter, QPixmap, QColor, QRadialGradient, QLinearGradient, QBrush, QPen,
    QFont, QPolygonF, QPainterPath, QKeySequence, QShortcut, QCursor,
)
from PySide6.QtWidgets import (
    QApplication, QWidget, QMainWindow, QHBoxLayout, QVBoxLayout,
    QLabel, QLineEdit, QTextBrowser, QCheckBox, QMessageBox, QPushButton,
    QScrollArea, QFrame, QGraphicsOpacityEffect, QSizePolicy,
)

from cerebro import Cerebro
from oido import Grabadora, GrabadoraPC, transcribir, precargar
from boca import hablar
import ojos

AQUI = os.path.dirname(os.path.abspath(__file__))
RUTA_AVATAR = os.path.join(AQUI, "avatar.png")

COLORES = {
    "idle": QColor(57, 255, 20),
    "escuchando": QColor(0, 243, 255),
    "pensando": QColor(255, 0, 60),
    "respondiendo": QColor(255, 170, 0),
    "error": QColor(139, 0, 0),
}
ORO = QColor(255, 204, 0)

VEL_FONDO = {"idle": 0.45, "escuchando": 1.1, "pensando": 2.8, "respondiendo": 1.8, "error": 0.08}
VEL_ROT = {"idle": 0.6, "escuchando": 1.4, "pensando": 4.0, "respondiendo": 2.2, "error": 0.15}
VEL_PULSO = {"idle": 2.0, "escuchando": 5.0, "pensando": 8.0, "respondiendo": 4.0, "error": 10.0}
AMP_BASE = {"idle": 0.15, "escuchando": 0.2, "pensando": 0.35, "respondiendo": 0.7, "error": 0.05}

COLOR_AUTOR = {
    "niko": QColor(0, 243, 255),
    "nexus": QColor(0, 243, 255),
    "sage": QColor(255, 0, 60),
    "sistema": QColor(57, 255, 20),
}
FUENTES = ("Segoe UI", "Noto Sans", "DejaVu Sans")
FUENTES_MONO = ("Consolas", "DejaVu Sans Mono", "Monospace")
FPS_MS = 33

# ---------- Comandos tácticos embebidos en la respuesta ----------
RE_ACCION = re.compile(
    r'\[(?P<tipo>ABRIR|ENFOCAR|CERRAR|TECLA|PULSAR|BUSCAR):\s*(?P<arg>.*?)\]'
    r'|(?s:\[(?P<tipo_e>ESCRIBIR):\s*(?P<arg_e>.*?)\])'
    r'|\[(?P<tipo_c>CLICK):\s*(?P<x>\d+)\s*,\s*(?P<y>\d+)\]'
    r'|\[(?P<tipo_s>SCROLL):\s*(?P<cant>-?\d+)\]'
    r'|\[(?P<tipo_w>ESPERAR)(?::\s*(?P<seg>\d+(?:\.\d+)?))?\]'
    r'|\[(?P<tipo_x>CIRCULOS)\]',
    re.I,
)
RE_APAGAR = re.compile(r'\[APAGAR\]', re.I)
RE_LIMPIAR = re.compile(
    r'\[(?:ABRIR|ENFOCAR|CERRAR|TECLA|PULSAR|BUSCAR):\s*.*?\]'
    r'|(?s:\[ESCRIBIR:\s*.*?\])'
    r'|\[CLICK:\s*\d+\s*,\s*\d+\]'
    r'|\[SCROLL:\s*-?\d+\]'
    r'|\[ESPERAR(?::\s*\d+(?:\.\d+)?)?\]'
    r'|\[CIRCULOS\]|\[APAGAR\]',
    re.I,
)
RE_PARCIAL = re.compile(r'\[(?:ABRIR|ENFOCAR|CERRAR|TECLA|ESCRIBIR|PULSAR|BUSCAR|CLICK|SCROLL|ESPERAR|CIRCULOS|APAGAR)[^\]]*$', re.I)


def extraer_acciones(texto):
    """Devuelve las directivas EN EL ORDEN en que aparecen: [(tipo, argumento), ...]."""
    acciones = []
    for m in RE_ACCION.finditer(texto):
        if m.group("tipo"): acciones.append((m.group("tipo").lower(), m.group("arg").strip()))
        elif m.group("tipo_e"): acciones.append(("escribir", m.group("arg_e")))
        elif m.group("tipo_c"): acciones.append(("click", (m.group("x"), m.group("y"))))
        elif m.group("tipo_s"): acciones.append(("scroll", m.group("cant")))
        elif m.group("tipo_w"): acciones.append(("esperar", m.group("seg") or ""))
        elif m.group("tipo_x"): acciones.append(("circulos", ""))
    return acciones


RE_SEGURO = re.compile(r'[^\w.\- ]')


def limpiar(texto):
    return RE_LIMPIAR.sub('', texto).strip()


def limpiar_parcial(texto):
    return RE_PARCIAL.sub('', RE_LIMPIAR.sub('', texto)).strip()


# ---------- Utilidades gráficas ----------
def lerp_color(a, b, t):
    t = max(0.0, min(1.0, t))
    return QColor(
        int(a.red() + (b.red() - a.red()) * t),
        int(a.green() + (b.green() - a.green()) * t),
        int(a.blue() + (b.blue() - a.blue()) * t),
    )


def acercar(a, b, t):
    """Como lerp_color pero converge de verdad al destino (evita quedarse a 1-2 niveles)."""
    t = max(0.0, min(1.0, t))
    r = a.red() + (b.red() - a.red()) * t
    g = a.green() + (b.green() - a.green()) * t
    bl = a.blue() + (b.blue() - a.blue()) * t
    if abs(b.red() - r) < 3 and abs(b.green() - g) < 3 and abs(b.blue() - bl) < 3:
        return QColor(b)
    return QColor(int(r), int(g), int(bl))


def con_alpha(c, alpha):
    r = QColor(c)
    r.setAlpha(max(0, min(255, int(alpha))))
    return r


def paralelogramo(x, y, w, h, skew):
    return QPolygonF([
        QPointF(x + skew, y), QPointF(x + w, y),
        QPointF(x + w - skew, y + h), QPointF(x, y + h),
    ])


def cursor_norm(widget):
    w, h = max(1, widget.width()), max(1, widget.height())
    pos = widget.mapFromGlobal(QCursor.pos())
    nx = (pos.x() - w / 2) / (w / 2)
    ny = (pos.y() - h / 2) / (h / 2)
    return max(-1.0, min(1.0, nx)), max(-1.0, min(1.0, ny))


@lru_cache(maxsize=None)
def fuente(pt, espaciado=0, mono=False):
    f = QFont()
    f.setFamilies(list(FUENTES_MONO if mono else FUENTES))
    f.setPointSize(pt)
    f.setBold(True)
    f.setItalic(True)
    if espaciado:
        f.setLetterSpacing(QFont.AbsoluteSpacing, espaciado)
    return f


# Tablas trigonométricas precalculadas (anillos del avatar)
_NR, _NT = 56, 72
_C_R = [math.cos(i * 2 * math.pi / _NR) for i in range(_NR)]
_S_R = [math.sin(i * 2 * math.pi / _NR) for i in range(_NR)]
_C_T = [math.cos(i * 2 * math.pi / _NT) for i in range(_NT)]
_S_T = [math.sin(i * 2 * math.pi / _NT) for i in range(_NT)]

ESTILO = """
QMainWindow { background-color: #050608; }
QWidget {
    color: #ffffff;
    font-family: 'Segoe UI', 'Noto Sans', 'DejaVu Sans', sans-serif;
    font-style: italic;
}
QToolTip {
    background-color: #0a0c10; color: #39ff14; border: 1px solid #39ff14; padding: 4px;
}
QScrollBar:vertical { border: none; background: transparent; width: 8px; margin: 0px; }
QScrollBar::handle:vertical { background: #39ff14; min-height: 30px; border-radius: 0px; }
QScrollBar::handle:vertical:hover { background: #ffffff; }
QScrollBar::add-line:vertical, QScrollBar::sub-line:vertical { border: none; background: none; }
QScrollBar::add-page:vertical, QScrollBar::sub-page:vertical { background: none; }
QLineEdit {
    background-color: rgba(10, 12, 16, 240);
    border: 2px solid #39ff14;
    border-left: 8px solid #39ff14;
    border-radius: 0px;
    padding: 12px;
    color: #ffffff;
    font-size: 14px;
    font-style: italic;
}
QLineEdit:focus { border-color: #00f3ff; background-color: #0f1218; }
QLineEdit:disabled { border-color: #1a3440; color: #3a5560; }
QLabel#estado {
    color: #39ff14;
    font-weight: 900;
    font-size: 17px;
    letter-spacing: 5px;
    margin-top: 6px;
}
QLabel#telemetria { color: #7fa8b5; font-size: 11px; font-weight: bold; letter-spacing: 2px; }
QCheckBox { color: #39ff14; font-size: 12px; font-weight: bold; }
QCheckBox::indicator { border: 2px solid #39ff14; width: 12px; height: 12px; }
QCheckBox::indicator:checked { background-color: #39ff14; }
"""


# ---------- Hilos ----------
class Tarea(QThread):
    ok = Signal(object)
    fallo = Signal(str)

    def __init__(self, fn, *args):
        super().__init__()
        self.fn, self.args = fn, args

    def run(self):
        try: self.ok.emit(self.fn(*self.args))
        except Exception as e: self.fallo.emit(str(e))


class TareaStream(QThread):
    trozo = Signal(str)
    ok = Signal()
    fallo = Signal(str)

    def __init__(self, fn, *args):
        super().__init__()
        self.fn, self.args = fn, args

    def run(self):
        try:
            for t in self.fn(*self.args): self.trozo.emit(t)
            self.ok.emit()
        except Exception as e: self.fallo.emit(str(e))


def traer_al_frente(nombre):
    import ctypes
    user32 = ctypes.windll.user32
    hwnds = []

    def callback(hwnd, lParam):
        if user32.IsWindowVisible(hwnd):
            n = user32.GetWindowTextLengthW(hwnd)
            if n > 0:
                buff = ctypes.create_unicode_buffer(n + 1)
                user32.GetWindowTextW(hwnd, buff, n + 1)
                if nombre.lower() in buff.value.lower():
                    hwnds.append(hwnd)
        return True

    proc = ctypes.WINFUNCTYPE(ctypes.c_bool, ctypes.POINTER(ctypes.c_int), ctypes.POINTER(ctypes.c_int))
    user32.EnumWindows(proc(callback), 0)
    if hwnds:
        user32.ShowWindow(hwnds[0], 9)
        user32.SetForegroundWindow(hwnds[0])
        return True
    return False


class Ejecutor(QThread):
    """Ejecuta los comandos tácticos EN ORDEN mirando la pantalla en tiempo real:
    espera a que las páginas terminen de cargar, localiza los elementos con visión,
    verifica que cada click surtió efecto, reintenta y aprende de sus errores."""
    log = Signal(str)
    hud = Signal(bool)  # False = ocultar la HUD (para que no tape ni ensucie la captura), True = mostrarla

    MAX_INTENTOS = 4
    MAX_PASOS = 20  # máximo de pasos de búsqueda (mirar + scroll) por elemento

    def __init__(self, acciones, cerebro=None, objetivo=""):
        super().__init__()
        self.acciones = acciones
        self.cerebro = cerebro
        self.objetivo = objetivo
        self._pag = None
        self._espera = None       # None | "abrir" | "enfocar": hay que esperar a que la pantalla se calme
        self._dominio = ""
        self._notas = []
        self._vio_pantalla = False
        self._obstaculos = 0
        self._esperas_ult = 0

    # ---------- flujo principal ----------
    def run(self):
        ocultar = bool({t for t, _ in self.acciones} - {"cerrar"})
        if ocultar:
            self.hud.emit(False)
            time.sleep(0.6)
        try:
            self._ejecutar()
        except Exception as e:
            self.log.emit(f"⚠ Fallo inesperado del ejecutor: {e}")
        finally:
            if ocultar:
                self.hud.emit(True)

    def _ejecutar(self):
        log = self.log.emit
        if any(t in ("escribir", "tecla", "click", "pulsar", "scroll", "circulos") for t, _ in self.acciones):
            try:
                import pyautogui
                self._pag = pyautogui
            except Exception as e:
                log(f"⚠ pyautogui no disponible: {e}")

        for tipo, arg in self.acciones:
            try:
                getattr(self, f"_a_{tipo}")(arg)
            except Exception as e:
                log(f"⚠ Fallo en {tipo.upper()}: {e}")
                self._notas.append(f"{tipo.upper()} falló ({e})")

        if self._vio_pantalla and self.cerebro is not None:
            self._verificacion_final()
        if self.cerebro is not None and self._notas:
            self.cerebro.registrar_resultado(" | ".join(self._notas))

    # ---------- utilidades de visión ----------
    def _requiere_pag(self):
        if self._pag is None:
            self.log.emit("⚠ No puedo controlar teclado/mouse: pyautogui no disponible.")
            self._notas.append("no hay control de teclado/mouse")
        return self._pag

    def _esperar_pantalla(self):
        """Si se abrió/enfocó algo, mira la pantalla hasta que deje de cambiar (página cargada)."""
        modo, self._espera = self._espera, None
        if not modo: return
        self.log.emit("👁 Observando la pantalla hasta que termine de cargar...")
        ok, seg = ojos.esperar_estable(
            timeout=25.0 if modo == "abrir" else 8.0,
            minimo=1.0,
            requerir_cambio=(modo == "abrir"),
        )
        if ok:
            self.log.emit(f"👁 Pantalla estable tras {seg:.1f}s. Continúo.")
        else:
            self.log.emit(f"⏳ La pantalla seguía cambiando tras {seg:.0f}s; continúo igualmente.")

    def _confirmar(self, antes):
        """Tras un click: espera a que se asiente y comprueba que la pantalla realmente reaccionó."""
        time.sleep(0.9)
        ojos.esperar_estable(timeout=6.0, minimo=0.5, estables=2)
        return ojos.cambio(antes, ojos.capturar())

    def _aprender(self):
        if self.cerebro is None: return
        sitio = f" {self._dominio}" if self._dominio else " una página web"
        leccion = (
            f"Al abrir{sitio}, el contenido tarda en cargar: hacer click enseguida falla. "
            "Debo esperar a que la pantalla termine de cargar y localizar el elemento viéndolo en pantalla "
            "con [PULSAR: descripción] en lugar de usar coordenadas fijas."
        )
        if self.cerebro.guardar_leccion(leccion):
            self.log.emit("🧠 Error analizado. Lección registrada en mi memoria para no repetirlo.")

    def _verificacion_final(self):
        time.sleep(0.8)
        img = ojos.capturar()
        if img is None: return
        r = self.cerebro.verificar_resultado(img, self.objetivo)
        if not r: return
        marca = "✅" if r["cumplido"] else "⚠"
        self.log.emit(f"{marca} Verificación visual: {r['observacion']}")
        self._notas.append(f"verificación visual: {r['observacion']} (cumplido={'sí' if r['cumplido'] else 'no'})")

    # ---------- acciones ----------
    def _a_abrir(self, cmd):
        cmd = cmd.strip()
        self.log.emit(f"⚡ Ejecutando anulación de sistema: {cmd}")
        os.startfile(cmd)
        self._espera = "abrir"
        if cmd.lower().startswith(("http://", "https://")):
            self._dominio = urlparse(cmd).netloc.replace("www.", "")
        self._notas.append(f"abrí {cmd}")

    def _a_enfocar(self, app_name):
        self.log.emit(f"🎯 Transfiriendo foco visual a: {app_name}")
        n = app_name.lower().strip()
        if "spotify" in n:
            os.startfile("spotify:")
        elif "discord" in n:
            ruta = os.path.join(os.getenv('LOCALAPPDATA'), 'Discord', 'Update.exe')
            subprocess.Popen([ruta, '--processStart', 'Discord.exe'])
        elif not traer_al_frente(app_name):
            self.log.emit(f"⚠ No se encontró ventana visible para: {app_name}")
            self._notas.append(f"no encontré ventana de {app_name}")
            return
        if self._espera != "abrir":
            self._espera = "enfocar"
        self._notas.append(f"enfoqué {app_name}")

    def _a_escribir(self, txt):
        pag = self._requiere_pag()
        if not pag: return
        self._esperar_pantalla()
        self.log.emit("⌨️ Inyectando pulsaciones de teclado...")
        pag.write(txt, interval=0.015)
        self._notas.append("escribí texto")

    def _a_tecla(self, tecla):
        pag = self._requiere_pag()
        if not pag: return
        self._esperar_pantalla()
        self.log.emit(f"⌨️ Ejecutando comando de tecla: [{tecla.upper()}]")
        pag.press(tecla.lower().strip())
        self._notas.append(f"pulsé tecla {tecla}")

    def _a_esperar(self, seg):
        if seg:
            s = min(float(seg), 30.0)
            self.log.emit(f"⏳ Esperando {s:g}s...")
            time.sleep(s)
        else:
            if not self._espera: self._espera = "abrir"
            self._esperar_pantalla()

    def _a_click(self, coords):
        pag = self._requiere_pag()
        if not pag: return
        self._esperar_pantalla()
        x, y = int(coords[0]), int(coords[1])
        self._vio_pantalla = True
        for intento in (1, 2):
            antes = ojos.capturar()
            self.log.emit(f"🖱️ Desplazando cursor y ejecutando click en ({x}, {y})...")
            pag.moveTo(x, y, duration=0.6, tween=pag.easeInOutQuad)
            pag.click()
            if self._confirmar(antes):
                self.log.emit("✅ Click confirmado: la pantalla reaccionó.")
                self._notas.append(f"click en ({x}, {y}) confirmado")
                if intento > 1: self._aprender()
                return
            self.log.emit("⚠ La pantalla no reaccionó al click.")
            if intento == 1:
                self.log.emit("👁 Espero a que la pantalla termine de cargar y lo reintento...")
                ojos.esperar_estable(timeout=10.0, minimo=1.0)
        self._notas.append(f"click en ({x}, {y}) SIN efecto visible")

    def _desplazar(self, dir_, antes, muescas=5):
        """Scroll fiable: rueda del mouse en muescas pequeñas sobre el centro de la pantalla; si la pantalla no
        reacciona, recurre al teclado (RePág/AvPág). Devuelve la captura posterior. dir_: -1 abajo, 1 arriba."""
        pag = self._pag
        sw, sh = pag.size()
        pag.moveTo(sw // 2, sh // 2, duration=0.2)
        time.sleep(0.15)
        for _ in range(max(1, muescas)):
            pag.scroll(dir_ * 120)
            time.sleep(0.04)
        ojos.esperar_estable(timeout=6.0, minimo=0.6, estables=2)
        img = ojos.capturar()
        if img is not None and not ojos.cambio(antes, img, umbral=0.004):
            self.log.emit("⌨️ La rueda no movió la página; pruebo con el teclado...")
            pag.press("pagedown" if dir_ < 0 else "pageup")
            ojos.esperar_estable(timeout=6.0, minimo=0.6, estables=2)
            img = ojos.capturar()
        return img

    def _localizar_scrolleando(self, desc, direccion=-1, scroll=True):
        """Mira la pantalla y, si el elemento no está a la vista, hace scroll (abajo, y al llegar al final, arriba)
        hasta encontrarlo. direccion: -1 = empezar hacia abajo, 1 = empezar hacia arriba.
        Devuelve (captura, resultado) o (None, None) si no lo encontró."""
        pag, log = self._pag, self.log.emit
        sw, sh = pag.size()
        self._esperar_pantalla()
        self._esperas_ult = 0
        img = ojos.capturar()
        dir_, invertido, vista, espera_inicial, fallos = direccion, False, False, True, 0

        for _ in range(self.MAX_PASOS):
            if img is None:
                log("⚠ No pude capturar la pantalla.")
                return None, None

            if not vista:
                log(f"👁 Buscando «{desc}» en pantalla...")
                r = self.cerebro.localizar_elemento(img, desc)
                if r is None:
                    fallos += 1
                    if fallos >= 3:
                        log("⚠ El módulo de visión no responde.")
                        return None, None
                    time.sleep(1.5)
                    img = ojos.capturar()
                    continue

                if r["encontrado"] and (not r["cargando"] or self._esperas_ult >= 2):
                    return img, r

                if not r["encontrado"] and r["obstaculo"] and self._obstaculos < 2:
                    self._obstaculos += 1
                    log(f"🚧 Obstáculo detectado: {r['obstaculo']}. Lo despejo.")
                    pag.moveTo(int(r["ox"] * sw), int(r["oy"] * sh), duration=0.5, tween=pag.easeInOutQuad)
                    pag.click()
                    time.sleep(1.0)
                    img = ojos.capturar()
                    continue

                if (r["cargando"] and self._esperas_ult < 3) or espera_inicial:
                    if r["cargando"]: self._esperas_ult += 1
                    espera_inicial = False
                    log("⏳ La página sigue cargando; espero y vuelvo a mirar..." if r["cargando"]
                        else "⏳ Aún no lo veo; dejo que la pantalla se asiente y vuelvo a mirar...")
                    ojos.esperar_estable(timeout=10.0, minimo=1.0, estables=2)
                    img = ojos.capturar()
                    continue

                espera_inicial = False
                if r["encontrado"]:
                    return img, r

            vista = False
            if not scroll:
                return None, None

            # No está a la vista: desplazarse en la dirección actual y volver a mirar
            antes = img
            log(f"📜 No lo veo aquí; hago scroll hacia {'abajo' if dir_ < 0 else 'arriba'}...")
            img = self._desplazar(dir_, antes)
            if img is None:
                continue
            if not ojos.cambio(antes, img, umbral=0.004):
                if invertido:
                    log("📜 Recorrí la página en ambos sentidos y no lo encontré.")
                    return None, None
                invertido = True
                dir_ = -dir_
                log("📜 Llegué al extremo de la página; sigo buscando en sentido contrario...")
                vista = True  # esta captura ya fue analizada: no gastar otra consulta

        log("📜 Agoté los pasos de búsqueda sin encontrarlo.")
        return None, None

    def _a_buscar(self, arg):
        pag = self._requiere_pag()
        if not pag: return
        if self.cerebro is None:
            self.log.emit("⚠ Módulo de visión no disponible.")
            return
        direccion, desc = -1, arg.strip()
        if "|" in desc:
            pref, resto = desc.split("|", 1)
            pref = pref.strip().lower()
            if pref in ("arriba", "subir", "sube", "up"):
                direccion, desc = 1, resto.strip()
            elif pref in ("abajo", "bajar", "baja", "down"):
                direccion, desc = -1, resto.strip()
        self._vio_pantalla = True
        img, r = self._localizar_scrolleando(desc, direccion)
        if r is not None:
            self.log.emit(f"🎯 Encontrado: «{desc}». Queda a la vista en pantalla.")
            self._notas.append(f"encontré «{desc}» haciendo scroll y quedó a la vista")
        else:
            self.log.emit(f"❌ No encontré «{desc}» en la página.")
            self._notas.append(f"NO encontré «{desc}» tras recorrer la página")

    def _a_pulsar(self, desc):
        pag = self._requiere_pag()
        if not pag: return
        if self.cerebro is None:
            self.log.emit("⚠ Módulo de visión no disponible.")
            return
        desc = desc.strip()
        self._vio_pantalla = True
        sw, sh = pag.size()

        for intento in range(1, self.MAX_INTENTOS + 1):
            img, r = self._localizar_scrolleando(desc)
            if r is None:
                break
            x, y = int(r["x"] * sw), int(r["y"] * sh)
            self.log.emit(f"🖱️ Elemento localizado en ({x}, {y}). Ejecutando click...")
            pag.moveTo(x, y, duration=0.6, tween=pag.easeInOutQuad)
            pag.click()
            if self._confirmar(img):
                self.log.emit("✅ Click confirmado: la pantalla reaccionó.")
                self._notas.append(f"pulsé «{desc}» en ({x}, {y}) con éxito (intento {intento})")
                if intento > 1 or self._esperas_ult: self._aprender()
                return
            self.log.emit("⚠ La pantalla no reaccionó. Reevalúo y reintento...")

        self.log.emit(f"❌ No logré pulsar «{desc}».")
        self._notas.append(f"NO logré pulsar «{desc}»")

    def _a_scroll(self, cantidad):
        pag = self._requiere_pag()
        if not pag: return
        self._esperar_pantalla()
        self.log.emit("🖱️ Haciendo scroll en pantalla...")
        cant = int(cantidad)
        if cant != 0:
            sw, sh = pag.size()
            pag.moveTo(sw // 2, sh // 2, duration=0.2)
            time.sleep(0.15)
            antes = ojos.capturar()
            direccion = 1 if cant > 0 else -1
            for _ in range(max(1, round(abs(cant) / 120))):
                pag.scroll(direccion * 120)
                time.sleep(0.04)
            time.sleep(0.6)
            if antes is not None and not ojos.cambio(antes, ojos.capturar(), umbral=0.004):
                self.log.emit("⌨️ La rueda no movió la página; pruebo con el teclado...")
                for _ in range(max(1, round(abs(cant) / 600))):
                    pag.press("pageup" if cant > 0 else "pagedown")
                    time.sleep(0.2)
        time.sleep(0.4)
        self._notas.append(f"scroll {cantidad}")

    def _a_circulos(self, _arg=""):
        pag = self._requiere_pag()
        if not pag: return
        self._esperar_pantalla()
        self.log.emit("🖱️ Ejecutando maniobra de calibración (círculos)...")
        cx, cy = pag.position()
        r = 150
        for i in range(36):
            ang = math.radians(i * 10)
            pag.moveTo(cx + r * math.cos(ang), cy + r * math.sin(ang), duration=0.015)
        pag.moveTo(cx, cy, duration=0.2)
        self._notas.append("círculos con el mouse")

    def _a_cerrar(self, app_name):
        nombre = app_name.lower().replace(".exe", "").replace('"', '').replace("'", "").strip()
        nombre = RE_SEGURO.sub('', nombre).strip()
        if not nombre: return
        self.log.emit(f"💀 Ejecutando protocolo de terminación para: {nombre}")
        subprocess.run(
            f'powershell -Command "Stop-Process -Name \'*{nombre}*\' -Force -ErrorAction SilentlyContinue"',
            shell=True, creationflags=subprocess.CREATE_NO_WINDOW,
        )
        subprocess.run(
            f'taskkill /F /IM "*{nombre}*.exe" /T',
            shell=True, creationflags=subprocess.CREATE_NO_WINDOW,
            stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
        )
        self._notas.append(f"cerré {nombre}")


def powershell_csv(comando_ps):
    return subprocess.check_output(
        f'powershell -Command "{comando_ps}"',
        shell=True, text=True, stderr=subprocess.STDOUT,
        encoding='mbcs', errors='replace', creationflags=subprocess.CREATE_NO_WINDOW,
    ).strip()


# ---------- Widgets ----------
class Fondo(QWidget):
    def __init__(self):
        super().__init__()
        self.estado = "idle"
        self.color = QColor(COLORES["idle"])
        self.suelo = 0.0
        self.impulso = 3.0
        self.px = 0.0
        self.py = 0.0
        self._tam = None
        self._grad = None
        self._haz1 = None
        self._haz2 = None

    def set_estado(self, estado):
        if estado != self.estado:
            self.impulso = max(self.impulso, 1.4)
        self.estado = estado

    def tick(self, dt):
        self.impulso *= max(0.0, 1.0 - dt * 2.0)
        vel = VEL_FONDO.get(self.estado, 0.5) * (1.0 + self.impulso * 1.2)

        nx, ny = cursor_norm(self)
        k = min(1.0, dt * 3)
        self.px += (nx - self.px) * k
        self.py += (ny - self.py) * k

        self.color = acercar(self.color, COLORES.get(self.estado, COLORES["idle"]), dt * 6)
        self.suelo = (self.suelo + dt * vel * 0.8) % 1.0

    def _recalcular(self, w, h):
        self._tam = (w, h)
        g = QLinearGradient(0, 0, 0, h)
        g.setColorAt(0.0, QColor(5, 6, 8))
        g.setColorAt(1.0, QColor(10, 14, 22))
        self._grad = QBrush(g)
        self._haz1 = QPolygonF([QPointF(w * 0.52, 0), QPointF(w * 0.74, 0), QPointF(w * 0.30, h), QPointF(w * 0.08, h)])
        self._haz2 = QPolygonF([QPointF(w * 0.78, 0), QPointF(w * 0.84, 0), QPointF(w * 0.40, h), QPointF(w * 0.34, h)])

    def paintEvent(self, ev):
        p = QPainter(self)
        p.setRenderHint(QPainter.Antialiasing)
        w, h = self.width(), self.height()
        if self._tam != (w, h):
            self._recalcular(w, h)
        c = self.color
        cx = w / 2 + self.px * w * 0.05

        p.fillRect(self.rect(), self._grad)

        p.setPen(Qt.NoPen)
        p.setBrush(con_alpha(c, 16))
        p.drawPolygon(self._haz1)
        p.setBrush(con_alpha(c, 9))
        p.drawPolygon(self._haz2)

        hor = h * 0.52 + self.py * h * 0.02
        n = 14
        for i in range(n):
            z = (i + self.suelo) / n
            y = hor + (h - hor) * (z ** 2.2)
            p.setPen(QPen(con_alpha(c, 12 + 40 * z), 1))
            p.drawLine(QPointF(0, y), QPointF(w, y))

        p.setPen(QPen(con_alpha(c, 24), 1))
        p.drawLines([QLineF(cx + k * w * 0.02, hor, w / 2 + k * w * 0.12, h) for k in range(-12, 13)])

        if self.impulso > 0.05:
            p.fillRect(self.rect(), con_alpha(c, min(55, int(self.impulso * 20))))


class Cabecera(QWidget):
    def __init__(self, modelo=""):
        super().__init__()
        self.setFixedHeight(68)
        self.estado = "idle"
        self.color = QColor(COLORES["idle"])
        self.modelo = modelo
        self.t = 0.0

    def set_estado(self, estado):
        self.estado = estado

    def set_modelo(self, modelo):
        if modelo: self.modelo = modelo

    def tick(self, dt):
        self.t += dt
        self.color = acercar(self.color, COLORES.get(self.estado, COLORES["idle"]), dt * 7)

    def paintEvent(self, ev):
        p = QPainter(self)
        p.setRenderHint(QPainter.Antialiasing)
        w, h = self.width(), self.height()
        c = self.color
        skew = 26
        ancho = min(w * 0.55, 520)

        p.setBrush(QColor(10, 12, 16, 235))
        p.setPen(QPen(c, 2))
        p.drawPolygon(paralelogramo(0, 6, ancho, h - 12, skew))

        pulso = 0.5 + 0.5 * math.sin(self.t * 3)
        p.setPen(Qt.NoPen)
        p.setBrush(con_alpha(c, 150 + 70 * pulso))
        p.drawPolygon(paralelogramo(ancho + 10, 6, 16, h - 12, skew * 0.9))
        p.setBrush(con_alpha(c, 60 + 60 * (1 - pulso)))
        p.drawPolygon(paralelogramo(ancho + 32, 6, 8, h - 12, skew * 0.9))

        p.setFont(fuente(24, 8))
        p.setPen(con_alpha(c, 110))
        p.drawText(QRectF(29, 10, ancho, 38), Qt.AlignLeft | Qt.AlignVCenter, "SAGE")
        p.setPen(QColor(255, 255, 255))
        p.drawText(QRectF(26, 8, ancho, 38), Qt.AlignLeft | Qt.AlignVCenter, "SAGE")

        f2 = fuente(8, 3)
        p.setFont(f2)
        p.setPen(con_alpha(c, 230))
        p.drawText(QRectF(28, 44, ancho, 16), Qt.AlignLeft | Qt.AlignVCenter, "EXTREME OS // COPILOTO GAME DEV")

        x1, x2 = ancho + 60, w - 230
        if x2 > x1:
            pen = QPen(con_alpha(c, 150), 2)
            pen.setStyle(Qt.DashLine)
            pen.setDashOffset(-self.t * 18)
            p.setPen(pen)
            p.drawLine(QPointF(x1, h / 2), QPointF(x2, h / 2))

        pw = 210
        p.setBrush(QColor(10, 12, 16, 235))
        p.setPen(QPen(con_alpha(c, 170), 2))
        p.drawPolygon(paralelogramo(w - pw, 6, pw, h - 12, skew))
        p.setFont(fuente(15, 0, True))
        p.setPen(QColor(255, 255, 255))
        p.drawText(QRectF(w - pw + skew, 8, pw - skew - 12, 32), Qt.AlignRight | Qt.AlignVCenter, time.strftime("%H:%M:%S"))
        p.setFont(f2)
        p.setPen(con_alpha(c, 230))
        modelo = self.modelo if len(self.modelo) < 24 else self.modelo[:23] + "…"
        p.drawText(QRectF(w - pw + skew, 40, pw - skew - 12, 18), Qt.AlignRight | Qt.AlignVCenter, f"NÚCLEO {modelo.upper()}")


class BotonRiders(QPushButton):
    def __init__(self, texto, color=COLORES["idle"], compacto=False):
        super().__init__(texto)
        self.base = QColor(color)
        self.compacto = compacto
        self._h = 0.0
        self.setCursor(Qt.PointingHandCursor)
        self.setMinimumHeight(30 if compacto else 44)
        self.setFocusPolicy(Qt.NoFocus)
        self.anim = QVariantAnimation(self)
        self.anim.setDuration(180)
        self.anim.setEasingCurve(QEasingCurve.OutCubic)
        self.anim.valueChanged.connect(self._set_h)

    def _set_h(self, v):
        self._h = float(v)
        self.update()

    def _animar(self, destino):
        self.anim.stop()
        self.anim.setStartValue(self._h)
        self.anim.setEndValue(destino)
        self.anim.start()

    def enterEvent(self, ev):
        self._animar(1.0)
        super().enterEvent(ev)

    def leaveEvent(self, ev):
        self._animar(0.0)
        super().leaveEvent(ev)

    def sizeHint(self):
        fm = self.fontMetrics()
        extra = 36 if self.compacto else 60
        return QSize(fm.horizontalAdvance(self.text()) + len(self.text()) * 2 + extra, 30 if self.compacto else 44)

    def paintEvent(self, ev):
        p = QPainter(self)
        p.setRenderHint(QPainter.Antialiasing)
        w, h = self.width(), self.height()
        sk = min(14.0, h * 0.35)
        poly = QPolygonF([QPointF(sk, 1), QPointF(w - 1, 1), QPointF(w - 1 - sk, h - 1), QPointF(1, h - 1)])

        activo = self.isEnabled()
        col = QColor(self.base) if activo else QColor(58, 85, 96)
        if activo and self.isDown(): col = QColor(0, 243, 255)
        hv = self._h if activo else 0.0

        p.setBrush(lerp_color(QColor(5, 6, 8), col, hv))
        p.setPen(QPen(col, 2))
        p.drawPolygon(poly)

        if activo and hv > 0.01:
            path = QPainterPath()
            path.addPolygon(poly)
            p.setClipPath(path)
            x = -w * 0.3 + (w * 1.6) * hv
            p.setPen(Qt.NoPen)
            p.setBrush(QColor(255, 255, 255, 80))
            p.drawPolygon(QPolygonF([QPointF(x, 0), QPointF(x + 20, 0), QPointF(x + 20 - sk, h), QPointF(x - sk, h)]))
            p.setClipping(False)

        f = QFont(self.font())
        f.setBold(True)
        f.setItalic(True)
        f.setPointSizeF(9 if self.compacto else 10)
        f.setLetterSpacing(QFont.AbsoluteSpacing, 2)
        p.setFont(f)
        p.setPen(lerp_color(col, QColor(0, 0, 0), hv))
        p.drawText(QRectF(sk / 2, 0, w - sk, h), Qt.AlignCenter, self.text())


class Avatar(QWidget):
    def __init__(self, ruta_png):
        super().__init__()
        self.setMinimumSize(300, 300)
        self.setCursor(Qt.PointingHandCursor)
        self.pix = QPixmap(ruta_png) if os.path.exists(ruta_png) else QPixmap()
        self.estado = "idle"
        self.color = QColor(COLORES["idle"])
        self.nivel = 0.0
        self.t = 0.0
        self.rot = 0.0
        self.ondas = []
        self.pickups = []
        self.rebote = 0.0
        self.mx = 0.0
        self.my = 0.0
        self._cache = (None, None)

    def set_estado(self, estado):
        if estado != self.estado: self.ondas.append(self.t)
        self.estado = estado

    def recoger_anillo(self):
        self.pickups.append(self.t)

    def mousePressEvent(self, ev):
        self.rebote = 1.0
        self.ondas.append(self.t)
        super().mousePressEvent(ev)

    def tick(self, dt):
        self.t += dt
        self.rot += dt * VEL_ROT.get(self.estado, 1.0)
        self.color = acercar(self.color, COLORES.get(self.estado, COLORES["idle"]), dt * 8)
        if self.ondas: self.ondas = [o for o in self.ondas if self.t - o < 0.9]
        if self.pickups: self.pickups = [k for k in self.pickups if self.t - k < 1.2]
        self.rebote = max(0.0, self.rebote * (1.0 - dt * 3.5) - dt * 0.05)

        nx, ny = cursor_norm(self)
        k = min(1.0, dt * 6)
        self.mx += (nx - self.mx) * k
        self.my += (ny - self.my) * k

    def _escalado(self, lado):
        if self._cache[0] != lado:
            self._cache = (lado, self.pix.scaled(lado, lado, Qt.KeepAspectRatio, Qt.SmoothTransformation))
        return self._cache[1]

    def paintEvent(self, ev):
        p = QPainter(self)
        p.setRenderHint(QPainter.Antialiasing)
        p.setRenderHint(QPainter.SmoothPixmapTransform)

        w, h = self.width(), self.height()
        cx, cy = w / 2, h / 2
        radio = min(w, h) * 0.25
        color = self.color
        t = self.t
        pulso = 0.5 + 0.5 * math.sin(t * VEL_PULSO.get(self.estado, 2.0))

        # Halo
        r_halo = radio * (1.5 + 0.25 * pulso)
        g = QRadialGradient(QPointF(cx, cy), r_halo)
        g.setColorAt(0.0, con_alpha(color, 60 + 110 * pulso))
        g.setColorAt(1.0, con_alpha(color, 0))
        p.setPen(Qt.NoPen)
        p.setBrush(QBrush(g))
        p.drawEllipse(QPointF(cx, cy), r_halo, r_halo)

        # Espectro radial
        amp = AMP_BASE.get(self.estado, 0.15)
        if self.estado == "escuchando": amp += self.nivel * 1.5
        amp = min(amp, 1.2)
        r0 = radio * 1.5
        cb, sb = math.cos(self.rot * 0.15), math.sin(self.rot * 0.15)
        t7, t33 = t * 7, t * 3.3
        pen = QPen(color)
        pen.setWidthF(3.0)
        pen.setCapStyle(Qt.FlatCap)
        for i in range(_NR):
            ruido = 0.5 + 0.5 * math.sin(t7 + i * 0.9) * math.sin(t33 + i * 0.41)
            largo = 4 + amp * ruido * radio * 0.38
            pen.setColor(con_alpha(color, 90 + 130 * ruido))
            p.setPen(pen)
            ca = _C_R[i] * cb - _S_R[i] * sb
            sa = _S_R[i] * cb + _C_R[i] * sb
            p.drawLine(QPointF(cx + ca * r0, cy + sa * r0), QPointF(cx + ca * (r0 + largo), cy + sa * (r0 + largo)))

        # Ondas
        p.setBrush(Qt.NoBrush)
        for o in self.ondas:
            k = (t - o) / 0.9
            pw = QPen(con_alpha(color, 200 * (1 - k)))
            pw.setWidthF(1 + 3 * (1 - k))
            p.setPen(pw)
            rr = radio * (1.0 + 0.9 * k)
            p.drawEllipse(QPointF(cx, cy), rr, rr)

        # Imagen
        dy = math.sin(t * 3.0) * 8
        dx = random.uniform(-4, 4) if self.estado == "error" else 0.0
        if not self.pix.isNull():
            esc = self._escalado(int(radio * 2.1))
            sq = math.sin(t * 4.0) * (0.05 if self.estado in ("respondiendo", "pensando") else 0.025)
            sq += self.rebote * math.sin(t * 24.0) * 0.14
            p.save()
            p.translate(cx + dx + self.mx * radio * 0.10, cy + dy + self.my * radio * 0.06)
            p.rotate(self.mx * 5.0)
            p.scale(1 + sq, 1 - sq)
            p.drawPixmap(int(-esc.width() / 2), int(-esc.height() / 2), esc)
            p.restore()
        else:
            r = radio * 0.6 * (1 + 0.05 * pulso)
            p.setPen(Qt.NoPen)
            p.setBrush(QBrush(color))
            p.drawEllipse(QPointF(cx + dx, cy + dy), r, r)

        # Aro principal
        pen = QPen(color)
        pen.setWidth(3)
        p.setPen(pen)
        p.setBrush(Qt.NoBrush)
        p.drawEllipse(QPointF(cx, cy), radio * 1.12, radio * 1.12)

        # Marcas del aro (en dos lotes)
        rt0, rt1 = radio * 1.2, radio * 1.27
        cb, sb = math.cos(self.rot * 0.5), math.sin(self.rot * 0.5)
        mayores, menores = [], []
        for i in range(_NT):
            ca = _C_T[i] * cb - _S_T[i] * sb
            sa = _S_T[i] * cb + _C_T[i] * sb
            if i % 6 == 0:
                mayores.append(QLineF(cx + ca * rt0, cy + sa * rt0, cx + ca * (rt1 + radio * 0.05), cy + sa * (rt1 + radio * 0.05)))
            else:
                menores.append(QLineF(cx + ca * rt0, cy + sa * rt0, cx + ca * rt1, cy + sa * rt1))
        pen2 = QPen(con_alpha(color, 110))
        pen2.setWidthF(1)
        p.setPen(pen2)
        p.drawLines(menores)
        pen2 = QPen(con_alpha(color, 200))
        pen2.setWidthF(2)
        p.setPen(pen2)
        p.drawLines(mayores)

        if self.estado == "pensando":
            pen = QPen(color)
            pen.setWidth(6)
            p.setPen(pen)
            rect = QRectF(cx - radio * 1.12, cy - radio * 1.12, radio * 2.24, radio * 2.24)
            inicio = int((t * 350) % 360) * 16
            p.drawArc(rect, inicio, 120 * 16)
            p.drawArc(rect, inicio + 180 * 16, 60 * 16)

        pen = QPen(color)
        pen.setWidth(2)
        pen.setStyle(Qt.DashLine)
        p.setPen(pen)
        rect_hud = QRectF(cx - radio * 1.38, cy - radio * 1.38, radio * 2.76, radio * 2.76)
        p.drawArc(rect_hud, int((-self.rot * 40) % 360) * 16, 360 * 16)

        p.setPen(Qt.NoPen)
        p.setBrush(QColor(255, 255, 255))
        for i in range(3):
            ang = -self.rot * 1.2 + i * 2 * math.pi / 3
            ox, oy = cx + math.cos(ang) * radio * 1.38, cy + math.sin(ang) * radio * 1.38
            s = 6
            p.drawPolygon(QPolygonF([QPointF(ox, oy - s), QPointF(ox + s, oy), QPointF(ox, oy + s), QPointF(ox - s, oy)]))

        # Anillos recogidos (+1)
        if self.pickups:
            p.setFont(fuente(13))
            for pk in self.pickups:
                k = (t - pk) / 1.2
                ry = radio * 0.22
                rx = max(2.0, ry * abs(math.cos(k * 16)))
                yy = cy - radio * 1.55 - k * radio * 0.9
                alfa = 255 * (1 - k)
                p.setBrush(Qt.NoBrush)
                p.setPen(QPen(con_alpha(ORO, alfa), 4))
                p.drawEllipse(QPointF(cx, yy), rx, ry)
                p.setPen(con_alpha(ORO, alfa))
                p.drawText(QRectF(cx + ry + 8, yy - 14, 60, 28), Qt.AlignLeft | Qt.AlignVCenter, "+1")


class Cuerpo(QTextBrowser):
    def __init__(self):
        super().__init__()
        self.setFrameShape(QFrame.NoFrame)
        self.setVerticalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        self.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        self.setOpenExternalLinks(True)
        self.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Fixed)
        self.document().setDocumentMargin(0)
        self.setStyleSheet(
            "QTextBrowser { background: transparent; border: none; padding: 0px;"
            " color: #eaf7ff; font-size: 14px; font-style: normal;"
            " font-family: 'Segoe UI', 'Noto Sans', 'DejaVu Sans', sans-serif; }"
        )
        self.document().documentLayout().documentSizeChanged.connect(self._ajustar)

    def _ajustar(self, *_):
        alto = int(math.ceil(self.document().size().height())) + 2
        if alto != self.height(): self.setFixedHeight(alto)

    def resizeEvent(self, ev):
        super().resizeEvent(ev)
        self._ajustar()


class Burbuja(QWidget):
    def __init__(self, autor, texto="", markdown=False, esperando=False):
        super().__init__()
        clave = autor.lower()
        self.color = COLOR_AUTOR.get(clave, COLOR_AUTOR["sistema"])
        self.a_derecha = clave in ("niko", "nexus")
        self.esperando = esperando
        self._brillo = 0.0
        self._t = 0.0
        self._mostrada = False
        self.fila = None

        lay = QVBoxLayout(self)
        lay.setContentsMargins(26, 10, 26, 12)
        lay.setSpacing(4)

        self.tag = QLabel(f"▌{autor.upper()}")
        f = self.tag.font()
        f.setPointSize(8)
        f.setBold(True)
        f.setLetterSpacing(QFont.AbsoluteSpacing, 3)
        self.tag.setFont(f)
        self.tag.setStyleSheet(f"color: {self.color.name()}; background: transparent;")
        lay.addWidget(self.tag)

        self.cuerpo = Cuerpo()
        lay.addWidget(self.cuerpo)

        if texto:
            if markdown: self.cuerpo.setMarkdown(texto)
            else: self.cuerpo.setPlainText(texto)

        self._timer = QTimer(self)
        self._timer.setInterval(40)
        self._timer.timeout.connect(self._tick)
        if esperando:
            self.cuerpo.hide()
            self.setMinimumHeight(74)
            self._timer.start()

        self._anim = QVariantAnimation(self)
        self._anim.setDuration(700)
        self._anim.setStartValue(0.0)
        self._anim.setEndValue(1.0)
        self._anim.setEasingCurve(QEasingCurve.OutCubic)
        self._anim.valueChanged.connect(self._set_brillo)

    def _set_brillo(self, v):
        self._brillo = float(v)
        self.update()

    def _tick(self):
        self._t += 0.04
        self.update()

    def showEvent(self, ev):
        super().showEvent(ev)
        if not self._mostrada:
            self._mostrada = True
            self._anim.start()

    def fin_espera(self):
        if self.esperando:
            self.esperando = False
            self._timer.stop()
            self.setMinimumHeight(0)
            self.cuerpo.show()

    def set_markdown(self, texto):
        self.fin_espera()
        self.cuerpo.setMarkdown(texto)

    def paintEvent(self, ev):
        p = QPainter(self)
        p.setRenderHint(QPainter.Antialiasing)
        w, h = self.width(), self.height()
        sk = 12
        c = self.color
        poly = QPolygonF([QPointF(sk, 1), QPointF(w - 1, 1), QPointF(w - 1 - sk, h - 1), QPointF(1, h - 1)])

        p.setBrush(lerp_color(QColor(10, 12, 16), c, 0.07))
        p.setPen(QPen(con_alpha(c, 170), 2))
        p.drawPolygon(poly)

        p.setPen(Qt.NoPen)
        p.setBrush(c)
        if self.a_derecha:
            p.drawPolygon(QPolygonF([QPointF(w - 7, 1), QPointF(w - 1, 1), QPointF(w - 1 - sk, h - 1), QPointF(w - 7 - sk, h - 1)]))
        else:
            p.drawPolygon(QPolygonF([QPointF(sk, 1), QPointF(sk + 6, 1), QPointF(6, h - 1), QPointF(1, h - 1)]))

        if 0.0 < self._brillo < 1.0:
            path = QPainterPath()
            path.addPolygon(poly)
            p.setClipPath(path)
            x = -60 + (w + 120) * self._brillo
            p.setBrush(QColor(255, 255, 255, 70))
            p.drawPolygon(QPolygonF([QPointF(x, 0), QPointF(x + 28, 0), QPointF(x + 28 - sk, h), QPointF(x - sk, h)]))
            p.setClipping(False)

        if self.esperando:
            p.setPen(Qt.NoPen)
            base = h - 16
            for i in range(5):
                k = 0.5 + 0.5 * math.sin(self._t * 9 - i * 0.8)
                alto = 6 + 18 * k
                x = 32 + i * 16
                p.setBrush(con_alpha(c, 110 + 140 * k))
                p.drawPolygon(QPolygonF([
                    QPointF(x + 4, base - alto), QPointF(x + 11, base - alto),
                    QPointF(x + 7, base), QPointF(x, base),
                ]))


class Fila(QWidget):
    def __init__(self, burbuja, modo):
        super().__init__()
        lay = QHBoxLayout(self)
        lay.setContentsMargins(0, 0, 0, 0)
        lay.setSpacing(0)
        if modo == "der":
            lay.addStretch(1)
            lay.addWidget(burbuja, 7)
        elif modo == "izq":
            lay.addWidget(burbuja, 13)
            lay.addStretch(1)
        else:
            lay.addWidget(burbuja, 1)

        self._efecto = QGraphicsOpacityEffect(self)
        self._efecto.setOpacity(0.0)
        self.setGraphicsEffect(self._efecto)
        self._anim = QVariantAnimation(self)
        self._anim.setDuration(380)
        self._anim.setStartValue(0.0)
        self._anim.setEndValue(1.0)
        self._anim.setEasingCurve(QEasingCurve.OutCubic)
        self._anim.valueChanged.connect(self._paso)
        self._anim.finished.connect(self._fin)
        self._anim.start()

    def _paso(self, v):
        v = float(v)
        if self._efecto is not None: self._efecto.setOpacity(v)
        self.setContentsMargins(0, int(18 * (1.0 - v)), 0, 0)

    def _fin(self):
        self.setContentsMargins(0, 0, 0, 0)
        self._efecto = None
        self.setGraphicsEffect(None)


class PanelChat(QWidget):
    def __init__(self):
        super().__init__()
        self.estado = "idle"
        self.color = QColor(COLORES["idle"])
        self.t = 0.0
        self.fase = 0.0
        self._pegado = True

        raiz = QVBoxLayout(self)
        raiz.setContentsMargins(22, 14, 14, 18)

        self.scroll = QScrollArea()
        self.scroll.setWidgetResizable(True)
        self.scroll.setFrameShape(QFrame.NoFrame)
        self.scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        self.scroll.setStyleSheet("QScrollArea { background: transparent; border: none; }")
        self.scroll.viewport().setAutoFillBackground(False)

        self.cont = QWidget()
        self.cont.setObjectName("chatcont")
        self.lay = QVBoxLayout(self.cont)
        self.lay.setContentsMargins(0, 4, 8, 4)
        self.lay.setSpacing(12)
        self.lay.addStretch(1)
        self.scroll.setWidget(self.cont)
        self.cont.setAutoFillBackground(False)
        self.cont.setStyleSheet("#chatcont { background: transparent; }")
        raiz.addWidget(self.scroll)

        barra = self.scroll.verticalScrollBar()
        barra.rangeChanged.connect(self._rango)
        barra.valueChanged.connect(self._movido)

    def _rango(self, _mn, mx):
        if self._pegado: self.scroll.verticalScrollBar().setValue(mx)

    def _movido(self, v):
        self._pegado = v >= self.scroll.verticalScrollBar().maximum() - 6

    def set_estado(self, estado):
        self.estado = estado

    def tick(self, dt):
        self.t += dt
        self.fase = (self.fase + dt * VEL_ROT.get(self.estado, 1.0) * 0.18) % 1.0
        self.color = acercar(self.color, COLORES.get(self.estado, COLORES["idle"]), dt * 7)

    def agregar(self, autor, texto="", markdown=False, esperando=False):
        b = Burbuja(autor, texto, markdown, esperando)
        clave = autor.lower()
        modo = "der" if clave in ("niko", "nexus") else ("izq" if clave == "sage" else "centro")
        fila = Fila(b, modo)
        b.fila = fila
        self._pegado = True
        self.lay.insertWidget(self.lay.count() - 1, fila)
        return b

    def quitar(self, burbuja):
        if burbuja is not None and burbuja.fila is not None:
            burbuja.fila.setParent(None)
            burbuja.fila.deleteLater()
            burbuja.fila = None

    def _vacio(self):
        return self.lay.count() <= 1

    def paintEvent(self, ev):
        p = QPainter(self)
        p.setRenderHint(QPainter.Antialiasing)
        w, h = self.width(), self.height()
        c = self.color
        ch = 22

        marco = QPolygonF([
            QPointF(0, 0), QPointF(w - ch, 0), QPointF(w, ch),
            QPointF(w, h), QPointF(ch, h), QPointF(0, h - ch),
        ])
        p.setBrush(QColor(10, 12, 16, 215))
        p.setPen(QPen(con_alpha(c, 220), 2))
        p.drawPolygon(marco)

        p.setPen(Qt.NoPen)
        p.setBrush(c)
        p.drawPolygon(QPolygonF([QPointF(0, 0), QPointF(9, 0), QPointF(9, h - ch + 9), QPointF(0, h - ch)]))

        x = self.fase * (w + 160) - 80
        grad = QLinearGradient(x - 80, 0, x + 80, 0)
        grad.setColorAt(0.0, con_alpha(QColor(255, 255, 255), 0))
        grad.setColorAt(0.5, con_alpha(QColor(255, 255, 255), 190))
        grad.setColorAt(1.0, con_alpha(QColor(255, 255, 255), 0))
        p.setPen(QPen(QBrush(grad), 2))
        p.drawLine(QPointF(max(12.0, x - 80), 1), QPointF(min(w - ch, x + 80), 1))

        if self._vacio():
            pulso = 0.5 + 0.5 * math.sin(self.t * 2.2)
            p.setFont(fuente(54, 14))
            p.setPen(con_alpha(c, 18 + 14 * pulso))
            p.drawText(QRectF(0, h * 0.30, w, 90), Qt.AlignCenter, "SAGE")
            p.setFont(fuente(9, 5))
            p.setPen(con_alpha(c, 90 + 120 * pulso))
            p.drawText(QRectF(0, h * 0.30 + 92, w, 24), Qt.AlignCenter, "ESPERANDO COMANDO")


class Ventana(QMainWindow):
    def __init__(self, cerebro):
        super().__init__()
        self.setWindowTitle("SAGE // EXTREME OS")
        self.resize(1150, 780)
        self.setMinimumSize(900, 640)

        self.cerebro = cerebro

        self.grabadora_mic = Grabadora()
        self.grabadora_pc = GrabadoraPC()
        self.grabadora_actual = None
        self.grabando_tipo = None  # None, "mic", "pc"

        self._tareas = set()
        self._parcial = ""
        self._burbuja_sage = None
        self._estado = "idle"
        self._color_estado = None
        self._nivel = 0.0
        self._rings = 0
        self._texto_pend = ""
        self._pend = ("", False)

        self._timer_ui = QTimer(self)
        self._timer_ui.setSingleShot(True)
        self._timer_ui.setInterval(80)
        self._timer_ui.timeout.connect(self._pintar_parcial)

        self.fondo = Fondo()
        self.setCentralWidget(self.fondo)
        raiz = QVBoxLayout(self.fondo)
        raiz.setContentsMargins(26, 16, 26, 22)
        raiz.setSpacing(16)

        self.cabecera = Cabecera(getattr(cerebro, "modelo", ""))
        raiz.addWidget(self.cabecera)

        cuerpo = QHBoxLayout()
        cuerpo.setSpacing(25)
        raiz.addLayout(cuerpo, 1)

        izq = QVBoxLayout()
        self.avatar = Avatar(RUTA_AVATAR)
        self.estado_lbl = QLabel("SISTEMA ONLINE")
        self.estado_lbl.setObjectName("estado")
        self.estado_lbl.setAlignment(Qt.AlignCenter)

        tel = QHBoxLayout()
        self.lbl_rings = QLabel("◎ RINGS 000")
        self.lbl_rings.setObjectName("telemetria")
        self.lbl_lat = QLabel("LAT --")
        self.lbl_lat.setObjectName("telemetria")
        self.lbl_lat.setAlignment(Qt.AlignRight)
        tel.addWidget(self.lbl_rings)
        tel.addWidget(self.lbl_lat)

        self.chk_top = QCheckBox("FIJAR HUD")
        self.chk_top.toggled.connect(self._siempre_encima)

        izq.addWidget(self.avatar, 1)
        izq.addWidget(self.estado_lbl)
        izq.addSpacing(10)
        izq.addLayout(tel)
        izq.addWidget(self.chk_top)
        cuerpo.addLayout(izq, 2)

        der = QVBoxLayout()
        der.setSpacing(12)
        self.chat = PanelChat()
        der.addWidget(self.chat, 1)

        fila = QHBoxLayout()
        fila.setSpacing(8)
        self.entrada = QLineEdit()
        self.entrada.setPlaceholderText("Comando o enlace vocal... (Ctrl+M = Micrófono)")
        self.entrada.returnPressed.connect(self.enviar)

        self.btn_mic = BotonRiders("MICRÓFONO", COLORES["escuchando"])
        self.btn_mic.clicked.connect(self.toggle_mic)

        self.btn_pc = BotonRiders("AUDIO PC", QColor(0, 243, 255))
        self.btn_pc.clicked.connect(self.toggle_pc)

        self.btn_enviar = BotonRiders("EJECUTAR", COLORES["idle"])
        self.btn_enviar.clicked.connect(self.enviar)

        fila.addWidget(self.entrada, 1)
        fila.addWidget(self.btn_mic)
        fila.addWidget(self.btn_pc)
        fila.addWidget(self.btn_enviar)
        der.addLayout(fila)
        cuerpo.addLayout(der, 3)

        QShortcut(QKeySequence("Ctrl+M"), self, activated=self._atajo_mic)

        # Reloj único: anima todos los widgets y repinta la ventana una sola vez por fotograma
        self._ult = time.perf_counter()
        self._reloj = QTimer(self)
        self._reloj.timeout.connect(self._frame)
        self._reloj.start(FPS_MS)

        self._set_estado("idle", "SISTEMA ONLINE")
        self.entrada.setFocus()

        self._correr(Tarea(self._calentar))

        self.setWindowOpacity(0.0)
        self._fade = QPropertyAnimation(self, b"windowOpacity", self)
        self._fade.setDuration(500)
        self._fade.setStartValue(0.0)
        self._fade.setEndValue(1.0)
        self._fade.setEasingCurve(QEasingCurve.OutCubic)
        self._fade.start()

    def _calentar(self):
        try: self.cerebro.calentar()
        except Exception: pass
        try: precargar()
        except Exception: pass

    def _frame(self):
        ahora = time.perf_counter()
        dt = min(0.1, ahora - self._ult)
        self._ult = ahora
        if self.isMinimized() or not self.isVisible():
            return

        destino = min(1.0, getattr(self.grabadora_actual, "nivel", 0.0) * 7) if self.grabando_tipo else 0.0
        self._nivel += (destino - self._nivel) * min(1.0, dt * 8.6)
        self.avatar.nivel = self._nivel

        self.fondo.tick(dt)
        self.cabecera.tick(dt)
        self.avatar.tick(dt)
        self.chat.tick(dt)
        self.fondo.update()

    def _siempre_encima(self, activo):
        self.setWindowFlag(Qt.WindowStaysOnTopHint, activo)
        self.show()

    def _set_estado(self, estado, texto):
        self._estado = estado
        c = COLORES.get(estado, COLORES["idle"]).name()
        self.avatar.set_estado(estado)
        self.fondo.set_estado(estado)
        self.cabecera.set_estado(estado)
        self.chat.set_estado(estado)
        self.estado_lbl.setText(texto)
        if c != self._color_estado:
            self._color_estado = c
            self.estado_lbl.setStyleSheet(f"color: {c};")
            self.entrada.setStyleSheet(f"border-color: {c};")

    def _agregar(self, autor, texto, markdown=False):
        return self.chat.agregar(autor, texto, markdown=markdown)

    def _log_sistema(self, texto):
        self._agregar("Sistema", texto)

    def _pintar_parcial(self):
        if self._burbuja_sage is not None and self._parcial:
            self._burbuja_sage.set_markdown(limpiar_parcial(self._parcial))

    def _respuesta_ok(self):
        self._timer_ui.stop()
        final = self._parcial or "(sin respuesta)"

        acciones = extraer_acciones(final)
        apagar = bool(RE_APAGAR.search(final))
        limpio = limpiar(final)

        if self._burbuja_sage is not None:
            self._burbuja_sage.set_markdown(limpio)
        else:
            self._agregar("SAGE", limpio, markdown=True)

        self._parcial = ""
        self._burbuja_sage = None

        self._rings += 1
        self.lbl_rings.setText(f"◎ RINGS {self._rings:03d}")
        self.avatar.recoger_anillo()

        m = getattr(self.cerebro, "_m", None) or {}
        if m.get("primero") is not None:
            self.lbl_lat.setText(f"LAT {m['primero']:.2f}s")

        if acciones:
            # SAGE habla mientras actúa; la voz no espera a que termine la ejecución
            self._pend = ("", apagar)
            if limpio and limpio != "(sin respuesta)":
                self._lanzar(Tarea(hablar, limpio), lambda x: None, lambda e: print(f"Fallo de voz: {e}"))
            self._set_estado("pensando", "OBSERVANDO Y EJECUTANDO...")
            ej = Ejecutor(acciones, self.cerebro, self._texto_pend)
            ej.log.connect(self._log_sistema)
            ej.hud.connect(self._mostrar_hud)
            ej.finished.connect(self._fin_ejecucion)
            ej.finished.connect(lambda t=ej: self._tareas.discard(t))
            self._tareas.add(ej)
            ej.start()
        else:
            self._pend = (limpio, apagar)
            self._fin_ejecucion()

    def _mostrar_hud(self, visible):
        """El ejecutor oculta la HUD mientras mira la pantalla (su animación ensuciaría la detección de carga)."""
        if visible:
            self.show()
        else:
            self.hide()

    def _fin_ejecucion(self):
        limpio, apagar = self._pend
        self._listo()
        if limpio and limpio != "(sin respuesta)":
            voz = Tarea(hablar, limpio)
            if apagar:
                voz.finished.connect(self.close)
            self._lanzar(voz, lambda x: None, lambda e: print(f"Fallo de voz: {e}"))
        elif apagar:
            QTimer.singleShot(1000, self.close)

    def _respuesta_error(self, msg):
        self._timer_ui.stop()
        if self._burbuja_sage is not None:
            if self._parcial:
                self._burbuja_sage.set_markdown(limpiar(self._parcial) + "\n\n*(interrumpido)*")
            else:
                self.chat.quitar(self._burbuja_sage)
        self._parcial = ""
        self._burbuja_sage = None
        self._agregar("Sistema", f"Error crítico: {msg}")
        self._set_estado("error", "FALLO DE CONEXIÓN")
        QTimer.singleShot(1500, self._listo)

    def _trozo(self, texto):
        if not self._parcial:
            self._set_estado("respondiendo", "TRANSMITIENDO...")
        self._parcial += texto
        if not self._timer_ui.isActive():
            self._timer_ui.start()

    def _atajo_mic(self):
        if self.grabando_tipo == "mic" or (not self.grabando_tipo and self.btn_mic.isEnabled()):
            self.toggle_mic()

    # --- MICRÓFONO FÍSICO ---
    def toggle_mic(self):
        if self.grabando_tipo == "pc":
            return

        if self.grabando_tipo != "mic":
            self.grabadora_actual = self.grabadora_mic
            try: self.grabadora_actual.iniciar()
            except Exception as e:
                self._agregar("Sistema", f"No se pudo enlazar micrófono: {e}")
                return
            self.grabando_tipo = "mic"
            self.btn_mic.setText("DETENER MIC")
            self.btn_pc.setEnabled(False)
            self._bloquear(True)
            self._set_estado("escuchando", "ESCUCHANDO MIC...")
        else:
            audio = self.grabadora_actual.detener()
            self.grabando_tipo = None
            self.btn_mic.setText("MICRÓFONO")
            self.btn_pc.setEnabled(True)
            self.btn_mic.setEnabled(False)
            self._set_estado("pensando", "DECODIFICANDO...")
            self._lanzar(Tarea(transcribir, audio), self._transcripcion_ok, self._mic_error)

    # --- AUDIO PC / DISCORD (LOOPBACK) ---
    def toggle_pc(self):
        if self.grabando_tipo == "mic":
            return

        if self.grabando_tipo != "pc":
            self.grabadora_actual = self.grabadora_pc
            try: self.grabadora_actual.iniciar()
            except Exception as e:
                self._agregar("Sistema", f"No se pudo capturar audio de la PC: {e}")
                return
            self.grabando_tipo = "pc"
            self.btn_pc.setText("DETENER PC")
            self.btn_mic.setEnabled(False)
            self._bloquear(True)
            self._set_estado("escuchando", "CAPTURANDO AUDIO PC...")
        else:
            audio = self.grabadora_actual.detener()
            self.grabando_tipo = None
            self.btn_pc.setText("AUDIO PC")
            self.btn_mic.setEnabled(True)
            self.btn_pc.setEnabled(False)
            self._set_estado("pensando", "DECODIFICANDO PC...")
            self._lanzar(Tarea(transcribir, audio), self._transcripcion_ok, self._mic_error)

    def _transcripcion_ok(self, texto):
        if not texto:
            self._agregar("Sistema", "Señal vacía, reintente.")
            self._listo()
            return
        self._agregar("Niko", texto)
        self._pedir_respuesta(texto)

    def _mic_error(self, msg):
        self._agregar("Sistema", f"Fallo en decodificación: {msg}")
        self._set_estado("error", "ERROR DE AUDIO")
        QTimer.singleShot(1500, self._listo)

    def _bloquear(self, bloqueado):
        self.entrada.setEnabled(not bloqueado)
        self.btn_enviar.setEnabled(not bloqueado)

    def _listo(self):
        self._bloquear(False)
        self.btn_mic.setEnabled(True)
        self.btn_pc.setEnabled(True)
        self._set_estado("idle", "SISTEMA ONLINE")
        self.entrada.setFocus()

    def _correr(self, tarea, **senales):
        for nombre, slot in senales.items():
            getattr(tarea, nombre).connect(slot)
        tarea.finished.connect(lambda t=tarea: self._tareas.discard(t))
        self._tareas.add(tarea)
        tarea.start()

    def _lanzar(self, tarea, ok, fallo):
        self._correr(tarea, ok=ok, fallo=fallo)

    def enviar(self):
        if not self.entrada.isEnabled(): return
        texto = self.entrada.text().strip()
        if not texto: return
        self.entrada.clear()
        self._agregar("Niko", texto)
        self._pedir_respuesta(texto)

    def _pedir_respuesta(self, texto):
        self._bloquear(True)
        self.btn_mic.setEnabled(False)
        self.btn_pc.setEnabled(False)
        self._parcial = ""
        self._texto_pend = texto
        self._set_estado("pensando", "ANALIZANDO INTENCIÓN...")
        self._correr(
            Tarea(self.cerebro.analizar_intencion, texto),
            ok=self._intencion_lista, fallo=self._respuesta_error,
        )

    def _intencion_lista(self, intencion):
        self._ejecutar_con_intencion(intencion, self._texto_pend)

    def _ejecutar_con_intencion(self, intencion, texto):
        imagen_a_enviar = None
        texto_enriquecido = texto

        if intencion.get("ver_pantalla", False):
            self.hide()
            QApplication.processEvents()
            time.sleep(0.3)
            try:
                from PIL import ImageGrab
                imagen_a_enviar = ImageGrab.grab()
                self._agregar("Sistema", "📸 Escáner óptico autorizado y ejecutado.")
            except Exception as e:
                self._agregar("Sistema", f"⚠ Fallo de captura óptica: {e}")
            finally:
                self.show()

        if intencion.get("ver_procesos", False):
            try:
                objetivo = RE_SEGURO.sub('', intencion.get("objetivo_proceso", "")).strip()
                cols = "Select-Object ProcessName, MainWindowTitle | ConvertTo-Csv -NoTypeInformation"
                if objetivo:
                    info = powershell_csv(f"Get-Process *{objetivo}* -ErrorAction SilentlyContinue | {cols}")
                    if info:
                        texto_enriquecido += f"\n\n[SISTEMA: El proceso '{objetivo}' SI FUE DETECTADO en la RAM]:\n{info}"
                    else:
                        texto_enriquecido += f"\n\n[SISTEMA: El proceso '{objetivo}' NO ESTÁ EJECUTÁNDOSE.]"
                    self._agregar("Sistema", f"⚙️ Rastreo específico de '{objetivo}' completado.")
                else:
                    info = powershell_csv("Get-Process | Where-Object {$_.MainWindowTitle} | " + cols)
                    texto_enriquecido += f"\n\n[DATOS DE TELEMETRÍA - TODOS LOS PROCESOS ACTIVOS]:\n{info}"
                    self._agregar("Sistema", "⚙️ Escaneo de subprocesos general completado.")
            except Exception as e:
                self._agregar("Sistema", f"⚠ Fallo de telemetría de Windows: {e}")

        self._set_estado("pensando", "CALCULANDO...")
        self._burbuja_sage = self.chat.agregar("SAGE", esperando=True)

        self._correr(
            TareaStream(self.cerebro.procesar_stream, texto_enriquecido, imagen_a_enviar),
            trozo=self._trozo, ok=self._respuesta_ok, fallo=self._respuesta_error,
        )

    def closeEvent(self, ev):
        if self.grabando_tipo and self.grabadora_actual:
            self.grabadora_actual.detener()
        super().closeEvent(ev)


def main():
    app = QApplication(sys.argv)
    app.setStyleSheet(ESTILO)
    try: cerebro = Cerebro()
    except Exception as e:
        QMessageBox.critical(None, "Fallo Crítico de SAGE", str(e))
        return 1
    ventana = Ventana(cerebro)
    ventana.show()
    return app.exec()


if __name__ == "__main__":
    sys.exit(main())
