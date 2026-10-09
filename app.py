import os
import sys
import math
import time
import random
import re

from PySide6.QtCore import (
    Qt, QTimer, QThread, Signal, QPointF, QRectF, QSize,
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
AMP_BASE = {"idle": 0.15, "escuchando": 0.2, "pensando": 0.35, "respondiendo": 0.7, "error": 0.05}

COLOR_AUTOR = {
    "niko": QColor(0, 243, 255),
    "nexus": QColor(0, 243, 255),
    "sage": QColor(255, 0, 60),
    "sistema": QColor(57, 255, 20),
}
FUENTES = ["Segoe UI", "Noto Sans", "DejaVu Sans"]

def lerp_color(a, b, t):
    t = max(0.0, min(1.0, t))
    return QColor(
        int(a.red() + (b.red() - a.red()) * t),
        int(a.green() + (b.green() - a.green()) * t),
        int(a.blue() + (b.blue() - a.blue()) * t),
    )

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

class Fondo(QWidget):
    def __init__(self):
        super().__init__()
        self.estado = "idle"
        self.color = QColor(COLORES["idle"])
        self.rayas = [self._raya(True) for _ in range(60)]
        self.anillos = [self._anillo(True) for _ in range(7)]
        self.suelo = 0.0
        self.t = 0.0
        self.impulso = 3.0          
        self.px = 0.0               
        self.py = 0.0
        self._ult = time.perf_counter()
        self.timer = QTimer(self)
        self.timer.timeout.connect(self._tick)
        self.timer.start(33)

    @staticmethod
    def _raya(inicial=False):
        return {
            "x": random.uniform(0.0, 1.2) if inicial else random.uniform(1.0, 1.3),
            "y": random.random(),
            "v": random.uniform(0.25, 1.1),
            "l": random.uniform(0.04, 0.22),
            "a": random.randint(25, 95),
            "w": random.choice((1, 1, 2)),
        }

    @staticmethod
    def _anillo(inicial=False):
        return {
            "x": random.uniform(0.0, 1.3) if inicial else random.uniform(1.05, 1.4),
            "y": random.uniform(0.10, 0.88),
            "s": random.uniform(14, 40),
            "v": random.uniform(0.18, 0.5),
            "fase": random.uniform(0, 6.28),
        }

    def set_estado(self, estado):
        if estado != self.estado:
            self.impulso = max(self.impulso, 1.4)   
        self.estado = estado

    def _tick(self):
        ahora = time.perf_counter()
        dt = min(0.1, ahora - self._ult)
        self._ult = ahora
        self.t += dt
        self.impulso *= max(0.0, 1.0 - dt * 2.0)
        vel = VEL_FONDO.get(self.estado, 0.5) * (1.0 + self.impulso * 1.2)

        nx, ny = cursor_norm(self)
        k = min(1.0, dt * 3)
        self.px += (nx - self.px) * k
        self.py += (ny - self.py) * k

        self.color = lerp_color(self.color, COLORES.get(self.estado, COLORES["idle"]), dt * 6)
        self.suelo = (self.suelo + dt * vel * 0.8) % 1.0
        for i, r in enumerate(self.rayas):
            r["x"] -= dt * r["v"] * vel
            if r["x"] + r["l"] < -0.05:
                self.rayas[i] = self._raya()
        for i, a in enumerate(self.anillos):
            a["x"] -= dt * a["v"] * vel * 0.6
            if a["x"] < -0.1:
                self.anillos[i] = self._anillo()
        self.update()

    def paintEvent(self, ev):
        p = QPainter(self)
        p.setRenderHint(QPainter.Antialiasing)
        w, h = self.width(), self.height()
        cx = w / 2 + self.px * w * 0.05
        c = self.color

        g = QLinearGradient(0, 0, 0, h)
        g.setColorAt(0.0, QColor(5, 6, 8))
        g.setColorAt(1.0, QColor(10, 14, 22))
        p.fillRect(self.rect(), g)

        p.setPen(Qt.NoPen)
        p.setBrush(con_alpha(c, 16))
        p.drawPolygon(QPolygonF([QPointF(w * 0.52, 0), QPointF(w * 0.74, 0), QPointF(w * 0.30, h), QPointF(w * 0.08, h)]))
        p.setBrush(con_alpha(c, 9))
        p.drawPolygon(QPolygonF([QPointF(w * 0.78, 0), QPointF(w * 0.84, 0), QPointF(w * 0.40, h), QPointF(w * 0.34, h)]))

        hor = h * 0.52 + self.py * h * 0.02
        n = 14
        for i in range(n):
            z = ((i + self.suelo) / n)
            y = hor + (h - hor) * (z ** 2.2)
            p.setPen(QPen(con_alpha(c, 12 + 40 * z), 1))
            p.drawLine(QPointF(0, y), QPointF(w, y))
        for k in range(-12, 13):
            xt = cx + k * w * 0.02
            xb = w / 2 + k * w * 0.12
            p.setPen(QPen(con_alpha(c, 24), 1))
            p.drawLine(QPointF(xt, hor), QPointF(xb, h))

        p.setBrush(Qt.NoBrush)
        for a in self.anillos:
            x = a["x"] * w - self.px * 26
            y = a["y"] * h - self.py * 14
            s = a["s"]
            rx = max(2.5, s * abs(math.cos(self.t * 2.4 + a["fase"])))
            p.setPen(QPen(con_alpha(ORO, 80), 3))
            p.drawEllipse(QPointF(x, y), rx, s)
            p.setPen(QPen(con_alpha(QColor(255, 255, 255), 50), 1))
            p.drawEllipse(QPointF(x, y), max(1.5, rx - 3), s - 3)

        claro = lerp_color(c, QColor(255, 255, 255), 0.45)
        estira = 1.0 + min(2.0, self.impulso) * 0.8
        for r in self.rayas:
            x0, y0 = r["x"] * w, r["y"] * h
            largo = r["l"] * w * estira
            pen = QPen(con_alpha(claro, r["a"]), r["w"])
            pen.setCapStyle(Qt.RoundCap)
            p.setPen(pen)
            p.drawLine(QPointF(x0, y0), QPointF(x0 + largo, y0 - largo * 0.10))

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
        self._ult = time.perf_counter()
        self.timer = QTimer(self)
        self.timer.timeout.connect(self._tick)
        self.timer.start(40)

    def set_estado(self, estado):
        self.estado = estado

    def set_modelo(self, modelo):
        if modelo: self.modelo = modelo

    def _tick(self):
        ahora = time.perf_counter()
        dt = ahora - self._ult
        self._ult = ahora
        self.t += dt
        self.color = lerp_color(self.color, COLORES.get(self.estado, COLORES["idle"]), min(1.0, dt * 7))
        self.update()

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

        f = QFont()
        f.setFamilies(FUENTES)
        f.setPointSize(24)
        f.setBold(True)
        f.setItalic(True)
        f.setLetterSpacing(QFont.AbsoluteSpacing, 8)
        p.setFont(f)
        p.setPen(con_alpha(c, 110))
        p.drawText(QRectF(29, 10, ancho, 38), Qt.AlignLeft | Qt.AlignVCenter, "SAGE")
        p.setPen(QColor(255, 255, 255))
        p.drawText(QRectF(26, 8, ancho, 38), Qt.AlignLeft | Qt.AlignVCenter, "SAGE")

        f2 = QFont()
        f2.setFamilies(FUENTES)
        f2.setPointSize(8)
        f2.setBold(True)
        f2.setItalic(True)
        f2.setLetterSpacing(QFont.AbsoluteSpacing, 3)
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
        f3 = QFont()
        f3.setFamilies(["Consolas", "DejaVu Sans Mono", "Monospace"])
        f3.setPointSize(15)
        f3.setBold(True)
        f3.setItalic(True)
        p.setFont(f3)
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
        self._ultimo = time.perf_counter()
        self.timer = QTimer(self)
        self.timer.timeout.connect(self._tick)
        self.timer.start(33)

    def set_estado(self, estado):
        if estado != self.estado: self.ondas.append(self.t)  
        self.estado = estado

    def recoger_anillo(self):
        self.pickups.append(self.t)

    def mousePressEvent(self, ev):
        self.rebote = 1.0
        self.ondas.append(self.t)
        super().mousePressEvent(ev)

    def _tick(self):
        ahora = time.perf_counter()
        dt = min(0.1, ahora - self._ultimo)
        self._ultimo = ahora
        self.t += dt
        self.rot += dt * VEL_ROT.get(self.estado, 1.0)
        self.color = lerp_color(self.color, COLORES.get(self.estado, COLORES["idle"]), min(1.0, dt * 8))
        self.ondas = [o for o in self.ondas if self.t - o < 0.9]
        self.pickups = [k for k in self.pickups if self.t - k < 1.2]
        self.rebote = max(0.0, self.rebote * (1.0 - dt * 3.5) - dt * 0.05)

        nx, ny = cursor_norm(self)
        k = min(1.0, dt * 6)
        self.mx += (nx - self.mx) * k
        self.my += (ny - self.my) * k
        self.update()

    def _escalado(self, lado):
        if self._cache[0] != lado:
            esc = self.pix.scaled(lado, lado, Qt.KeepAspectRatio, Qt.SmoothTransformation)
            self._cache = (lado, esc)
        return self._cache[1]

    def paintEvent(self, ev):
        p = QPainter(self)
        p.setRenderHint(QPainter.Antialiasing)
        p.setRenderHint(QPainter.SmoothPixmapTransform)

        w, h = self.width(), self.height()
        cx, cy = w / 2, h / 2
        radio = min(w, h) * 0.25
        color = self.color
        pulso = 0.5 + 0.5 * math.sin(self.t * {"idle": 2.0, "escuchando": 5.0, "pensando": 8.0, "respondiendo": 4.0, "error": 10.0}.get(self.estado, 2.0))

        r_halo = radio * (1.5 + 0.25 * pulso)
        g = QRadialGradient(QPointF(cx, cy), r_halo)
        g.setColorAt(0.0, con_alpha(color, 60 + 110 * pulso))
        g.setColorAt(1.0, con_alpha(color, 0))
        p.setPen(Qt.NoPen)
        p.setBrush(QBrush(g))
        p.drawEllipse(QPointF(cx, cy), r_halo, r_halo)

        amp = AMP_BASE.get(self.estado, 0.15)
        if self.estado == "escuchando": amp += self.nivel * 1.5
        amp = min(amp, 1.2)
        n = 56
        r0 = radio * 1.5
        pen = QPen(color)
        pen.setWidthF(3.0)
        pen.setCapStyle(Qt.FlatCap)
        for i in range(n):
            ang = i * 2 * math.pi / n + self.rot * 0.15
            ruido = 0.5 + 0.5 * math.sin(self.t * 7 + i * 0.9) * math.sin(self.t * 3.3 + i * 0.41)
            largo = 4 + amp * ruido * radio * 0.38
            pen.setColor(con_alpha(color, 90 + 130 * ruido))
            p.setPen(pen)
            ca, sa = math.cos(ang), math.sin(ang)
            p.drawLine(QPointF(cx + ca * r0, cy + sa * r0), QPointF(cx + ca * (r0 + largo), cy + sa * (r0 + largo)))

        p.setBrush(Qt.NoBrush)
        for o in self.ondas:
            k = (self.t - o) / 0.9
            pw = QPen(con_alpha(color, 200 * (1 - k)))
            pw.setWidthF(1 + 3 * (1 - k))
            p.setPen(pw)
            rr = radio * (1.0 + 0.9 * k)
            p.drawEllipse(QPointF(cx, cy), rr, rr)

        dy = math.sin(self.t * 3.0) * 8
        dx = random.uniform(-4, 4) if self.estado == "error" else 0.0
        if not self.pix.isNull():
            esc = self._escalado(int(radio * 2.1))
            sq = math.sin(self.t * 4.0) * (0.05 if self.estado in ("respondiendo", "pensando") else 0.025)
            sq += self.rebote * math.sin(self.t * 24.0) * 0.14
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

        pen = QPen(color)
        pen.setWidth(3)
        p.setPen(pen)
        p.setBrush(Qt.NoBrush)
        p.drawEllipse(QPointF(cx, cy), radio * 1.12, radio * 1.12)

        rt0, rt1 = radio * 1.2, radio * 1.27
        for i in range(72):
            ang = i * 2 * math.pi / 72 + self.rot * 0.5
            largo = rt1 + (radio * 0.05 if i % 6 == 0 else 0)
            pen2 = QPen(con_alpha(color, 200 if i % 6 == 0 else 110))
            pen2.setWidthF(2 if i % 6 == 0 else 1)
            p.setPen(pen2)
            ca, sa = math.cos(ang), math.sin(ang)
            p.drawLine(QPointF(cx + ca * rt0, cy + sa * rt0), QPointF(cx + ca * largo, cy + sa * largo))

        if self.estado == "pensando":
            pen = QPen(color)
            pen.setWidth(6)
            p.setPen(pen)
            rect = QRectF(cx - radio * 1.12, cy - radio * 1.12, radio * 2.24, radio * 2.24)
            inicio = int((self.t * 350) % 360) * 16
            p.drawArc(rect, inicio, 120 * 16)
            p.drawArc(rect, inicio + 180 * 16, 60 * 16)

        pen = QPen(color)
        pen.setWidth(2)
        pen.setStyle(Qt.DashLine)
        p.setPen(pen)
        rect_hud = QRectF(cx - radio * 1.38, cy - radio * 1.38, radio * 2.76, radio * 2.76)
        inicio_hud = int((-self.rot * 40) % 360) * 16
        p.drawArc(rect_hud, inicio_hud, 360 * 16)

        p.setPen(Qt.NoPen)
        p.setBrush(QColor(255, 255, 255))
        for i in range(3):
            ang = -self.rot * 1.2 + i * 2 * math.pi / 3
            ox, oy = cx + math.cos(ang) * radio * 1.38, cy + math.sin(ang) * radio * 1.38
            s = 6
            p.drawPolygon(QPolygonF([QPointF(ox, oy - s), QPointF(ox + s, oy), QPointF(ox, oy + s), QPointF(ox - s, oy)]))

        for pk in self.pickups:
            k = (self.t - pk) / 1.2
            ry = radio * 0.22
            rx = max(2.0, ry * abs(math.cos(k * 16)))
            yy = cy - radio * 1.55 - k * radio * 0.9
            alfa = 255 * (1 - k)
            p.setBrush(Qt.NoBrush)
            p.setPen(QPen(con_alpha(ORO, alfa), 4))
            p.drawEllipse(QPointF(cx, yy), rx, ry)
            f = QFont()
            f.setFamilies(FUENTES)
            f.setBold(True)
            f.setItalic(True)
            f.setPointSize(13)
            p.setFont(f)
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
            for i in range(5):
                k = 0.5 + 0.5 * math.sin(self._t * 9 - i * 0.8)
                alto = 6 + 18 * k
                x = 32 + i * 16
                base = h - 16
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
        self._ult = time.perf_counter()

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

        self.timer = QTimer(self)
        self.timer.timeout.connect(self._tick)
        self.timer.start(40)

    def _rango(self, _mn, mx):
        if self._pegado: self.scroll.verticalScrollBar().setValue(mx)

    def _movido(self, v):
        self._pegado = v >= self.scroll.verticalScrollBar().maximum() - 6

    def set_estado(self, estado):
        self.estado = estado

    def _tick(self):
        ahora = time.perf_counter()
        dt = ahora - self._ult
        self._ult = ahora
        self.t += dt
        self.fase = (self.fase + dt * VEL_ROT.get(self.estado, 1.0) * 0.18) % 1.0
        self.color = lerp_color(self.color, COLORES.get(self.estado, COLORES["idle"]), min(1.0, dt * 7))
        self.update()

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
        pen = QPen(QBrush(grad), 2)
        p.setPen(pen)
        p.drawLine(QPointF(max(12.0, x - 80), 1), QPointF(min(w - ch, x + 80), 1))

        if self._vacio():
            pulso = 0.5 + 0.5 * math.sin(self.t * 2.2)
            f = QFont()
            f.setFamilies(FUENTES)
            f.setPointSize(54)
            f.setBold(True)
            f.setItalic(True)
            f.setLetterSpacing(QFont.AbsoluteSpacing, 14)
            p.setFont(f)
            p.setPen(con_alpha(c, 18 + 14 * pulso))
            p.drawText(QRectF(0, h * 0.30, w, 90), Qt.AlignCenter, "SAGE")
            f2 = QFont()
            f2.setFamilies(FUENTES)
            f2.setPointSize(9)
            f2.setBold(True)
            f2.setItalic(True)
            f2.setLetterSpacing(QFont.AbsoluteSpacing, 5)
            p.setFont(f2)
            p.setPen(con_alpha(c, 90 + 120 * pulso))
            p.drawText(QRectF(0, h * 0.30 + 92, w, 24), Qt.AlignCenter, "ESPERANDO COMANDO")

class Ventana(QMainWindow):
    def __init__(self, cerebro):
        super().__init__()
        self.setWindowTitle("SAGE // EXTREME OS")
        self.resize(1150, 780)
        self.setMinimumSize(900, 640)

        self.cerebro = cerebro
        
        # Instanciamos ambos motores de captura (Micrófono y Loopback PC)
        self.grabadora_mic = Grabadora()
        self.grabadora_pc = GrabadoraPC()
        self.grabadora_actual = None
        self.grabando_tipo = None  # None, "mic", "pc"

        self._tareas = set()
        self._parcial = ""
        self._burbuja_sage = None
        self._estado = "idle"
        self._nivel = 0.0
        self._rings = 0

        self._timer_ui = QTimer(self)
        self._timer_ui.setSingleShot(True)
        self._timer_ui.setInterval(60)
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
        
        # Botón para Micrófono Físico
        self.btn_mic = BotonRiders("MICRÓFONO", COLORES["escuchando"])
        self.btn_mic.clicked.connect(self.toggle_mic)

        # Botón separado para el Audio de la PC (Discord / Juegos)
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

        self._timer_tel = QTimer(self)
        self._timer_tel.timeout.connect(self._tick_tel)
        self._timer_tel.start(50)

        self._set_estado("idle", "SISTEMA ONLINE")
        self.entrada.setFocus()

        calentar = Tarea(self._calentar)
        calentar.finished.connect(lambda t=calentar: self._tareas.discard(t))
        self._tareas.add(calentar)
        calentar.start()

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

    def _tick_tel(self):
        if self.grabando_tipo:
            nivel = getattr(self.grabadora_actual, "nivel", 0.0)
            destino = min(1.0, nivel * 7)
        else:
            destino = 0.0
        self._nivel += (destino - self._nivel) * 0.35
        self.avatar.nivel = self._nivel

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
        self.estado_lbl.setStyleSheet(f"color: {c};")
        self.entrada.setStyleSheet(f"border-color: {c};")

    def _agregar(self, autor, texto, markdown=False):
        return self.chat.agregar(autor, texto, markdown=markdown)

    def _pintar_parcial(self):
        import re
        if self._burbuja_sage is not None and self._parcial:
            txt = re.sub(r'\[ABRIR:\s*.*?\]', '', self._parcial, flags=re.IGNORECASE)
            txt = re.sub(r'\[ENFOCAR:\s*.*?\]', '', txt, flags=re.IGNORECASE)
            txt = re.sub(r'\[CERRAR:\s*.*?\]', '', txt, flags=re.IGNORECASE)
            txt = re.sub(r'\[APAGAR\]', '', txt, flags=re.IGNORECASE).strip()
            self._burbuja_sage.set_markdown(txt)

    def _respuesta_ok(self):
        import re
        import os
        import subprocess
        self._timer_ui.stop()
        final = self._parcial or "(sin respuesta)"
        
        comandos_abrir = re.findall(r'\[ABRIR:\s*(.*?)\]', final, flags=re.IGNORECASE)
        comandos_enfocar = re.findall(r'\[ENFOCAR:\s*(.*?)\]', final, flags=re.IGNORECASE)
        comandos_cerrar = re.findall(r'\[CERRAR:\s*(.*?)\]', final, flags=re.IGNORECASE)
        comando_apagar = re.search(r'\[APAGAR\]', final, flags=re.IGNORECASE)
        
        texto_limpio = re.sub(r'\[ABRIR:\s*.*?\]', '', final, flags=re.IGNORECASE)
        texto_limpio = re.sub(r'\[ENFOCAR:\s*.*?\]', '', texto_limpio, flags=re.IGNORECASE)
        texto_limpio = re.sub(r'\[CERRAR:\s*.*?\]', '', texto_limpio, flags=re.IGNORECASE)
        texto_limpio = re.sub(r'\[APAGAR\]', '', texto_limpio, flags=re.IGNORECASE).strip()

        if self._burbuja_sage is not None:
            self._burbuja_sage.set_markdown(texto_limpio)
        else:
            self._agregar("SAGE", texto_limpio, markdown=True)
            
        self._parcial = ""
        self._burbuja_sage = None

        self._rings += 1
        self.lbl_rings.setText(f"◎ RINGS {self._rings:03d}")
        self.avatar.recoger_anillo()

        m = getattr(self.cerebro, "_m", None) or {}
        if m.get("primero") is not None:
            self.lbl_lat.setText(f"LAT {m['primero']:.2f}s")
            
        for cmd in comandos_abrir:
            self._agregar("Sistema", f"⚡ Ejecutando anulación de sistema: {cmd}")
            try: os.startfile(cmd)
            except Exception as e: self._agregar("Sistema", f"⚠ Error al intentar abrir {cmd}: {e}")

        if comandos_enfocar:
            import ctypes
            def traer_al_frente(nombre):
                user32 = ctypes.windll.user32
                hwnds = []
                def callback(hwnd, lParam):
                    if user32.IsWindowVisible(hwnd):
                        length = user32.GetWindowTextLengthW(hwnd)
                        if length > 0:
                            buff = ctypes.create_unicode_buffer(length + 1)
                            user32.GetWindowTextW(hwnd, buff, length + 1)
                            if nombre.lower() in buff.value.lower():
                                hwnds.append(hwnd)
                    return True
                EnumWindowsProc = ctypes.WINFUNCTYPE(ctypes.c_bool, ctypes.POINTER(ctypes.c_int), ctypes.POINTER(ctypes.c_int))
                user32.EnumWindows(EnumWindowsProc(callback), 0)
                if hwnds:
                    hwnd = hwnds[0]
                    user32.ShowWindow(hwnd, 9)
                    user32.SetForegroundWindow(hwnd)
                    return True
                return False

            for app_name in comandos_enfocar:
                self._agregar("Sistema", f"🎯 Transfiriendo foco visual a: {app_name}")
                try:
                    nombre_limpio = app_name.lower().strip()
                    if "spotify" in nombre_limpio:
                        os.startfile("spotify:")
                        continue
                    elif "discord" in nombre_limpio:
                        os.startfile(os.path.join(os.getenv('LOCALAPPDATA'), 'Discord', 'Update.exe'), '--processStart Discord.exe')
                        continue
                    if not traer_al_frente(app_name):
                        self._agregar("Sistema", f"⚠ No se encontró ventana visible para: {app_name}")
                except Exception as e:
                    self._agregar("Sistema", f"⚠ Error al enfocar: {e}")

        for app_name in comandos_cerrar:
            nombre_proceso = app_name.lower().replace(".exe", "").replace('"', '').replace("'", "").strip()
            self._agregar("Sistema", f"💀 Ejecutando protocolo de terminación para: {nombre_proceso}")
            try:
                subprocess.run(f'powershell -Command "Stop-Process -Name \'*{nombre_proceso}*\' -Force -ErrorAction SilentlyContinue"', shell=True, creationflags=subprocess.CREATE_NO_WINDOW)
                subprocess.run(f'taskkill /F /IM "*{nombre_proceso}*.exe" /T', shell=True, creationflags=subprocess.CREATE_NO_WINDOW, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
            except Exception as e:
                self._agregar("Sistema", f"⚠ Error al intentar terminar {nombre_proceso}: {e}")

        self._listo()

        if texto_limpio and texto_limpio != "(sin respuesta)":
            tarea_voz = Tarea(hablar, texto_limpio)
            if comando_apagar:
                tarea_voz.finished.connect(self.close)
            self._lanzar(tarea_voz, lambda x: None, lambda e: print(f"Fallo de voz: {e}"))
        elif comando_apagar:
            QTimer.singleShot(1000, self.close)

    def _trozo(self, texto):
        if not self._parcial:
            self._set_estado("respondiendo", "TRANSMITIENDO...")
        self._parcial += texto
        if not self._timer_ui.isActive():
            self._timer_ui.start()

    def _atajo_mic(self):
        if self.grabando_tipo == "mic" or (not self.grabando_tipo and self.btn_mic.isEnabled()):
            self.toggle_mic()

    # --- CONTROL DE MICRÓFONO FÍSICO ---
    def toggle_mic(self):
        if self.grabando_tipo == "pc": 
            return # Ocupado capturando PC
        
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

    # --- CONTROL DE AUDIO PC / DISCORD (LOOPBACK) ---
    def toggle_pc(self):
        if self.grabando_tipo == "mic": 
            return # Ocupado con el micrófono
        
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

    def _lanzar(self, tarea, ok, fallo):
        tarea.ok.connect(ok)
        tarea.fallo.connect(fallo)
        tarea.finished.connect(lambda t=tarea: self._tareas.discard(t))
        self._tareas.add(tarea)
        tarea.start()

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
        
        self._set_estado("pensando", "ANALIZANDO INTENCIÓN...")
        
        t = Tarea(self.cerebro.analizar_intencion, texto)
        t.ok.connect(lambda res: self._ejecutar_con_intencion(res, texto))
        t.fallo.connect(self._respuesta_error)
        t.finished.connect(lambda t=t: self._tareas.discard(t))
        self._tareas.add(t)
        t.start()

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
                import subprocess
                objetivo = intencion.get("objetivo_proceso", "").strip()
                if objetivo:
                    cmd = f'powershell -Command "Get-Process *{objetivo}* -ErrorAction SilentlyContinue | Select-Object ProcessName, MainWindowTitle | ConvertTo-Csv -NoTypeInformation"'
                    info_procesos = subprocess.check_output(cmd, shell=True, text=True, stderr=subprocess.STDOUT, encoding='mbcs', errors='replace', creationflags=subprocess.CREATE_NO_WINDOW).strip()
                    if info_procesos:
                        texto_enriquecido += f"\n\n[SISTEMA: El proceso '{objetivo}' SI FUE DETECTADO en la RAM]:\n{info_procesos}"
                    else:
                        texto_enriquecido += f"\n\n[SISTEMA: El proceso '{objetivo}' NO ESTÁ EJECUTÁNDOSE.]"
                    self._agregar("Sistema", f"⚙️ Rastreo específico de '{objetivo}' completado.")
                else:
                    cmd = 'powershell -Command "Get-Process | Where-Object {$_.MainWindowTitle} | Select-Object ProcessName, MainWindowTitle | ConvertTo-Csv -NoTypeInformation"'
                    info_procesos = subprocess.check_output(cmd, shell=True, text=True, stderr=subprocess.STDOUT, encoding='mbcs', errors='replace', creationflags=subprocess.CREATE_NO_WINDOW).strip()
                    texto_enriquecido += f"\n\n[DATOS DE TELEMETRÍA - TODOS LOS PROCESOS ACTIVOS]:\n{info_procesos}"
                    self._agregar("Sistema", f"⚙️ Escaneo de subprocesos general completado.")
            except Exception as e:
                self._agregar("Sistema", f"⚠ Fallo de telemetría de Windows: {e}")

        self._set_estado("pensando", "CALCULANDO...")
        self._burbuja_sage = self.chat.agregar("SAGE", esperando=True)
        
        t = TareaStream(self.cerebro.procesar_stream, texto_enriquecido, imagen_a_enviar)
        t.trozo.connect(self._trozo)
        t.ok.connect(self._respuesta_ok)
        t.fallo.connect(self._respuesta_error)
        t.finished.connect(lambda t=t: self._tareas.discard(t))
        self._tareas.add(t)
        t.start()

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