import os
import re
import sys
import math
import time
import random
import subprocess
import unicodedata
import threading

import numpy as np
from functools import lru_cache
from urllib.parse import urlparse

from PySide6.QtCore import (
    Qt, QObject, QTimer, QThread, Signal, QPointF, QRectF, QRect, QLineF, QSize,
    QVariantAnimation, QEasingCurve, QPropertyAnimation,
)
from PySide6.QtGui import (
    QPainter, QPixmap, QColor, QRadialGradient, QLinearGradient, QBrush, QPen,
    QFont, QFontMetrics, QPolygonF, QPainterPath, QKeySequence, QShortcut, QCursor, QIcon, QImage, QAction,
)
from PySide6.QtWidgets import (
    QApplication, QWidget, QMainWindow, QHBoxLayout, QVBoxLayout,
    QLabel, QLineEdit, QTextBrowser, QCheckBox, QMessageBox, QPushButton,
    QScrollArea, QFrame, QGraphicsOpacityEffect, QSizePolicy, QSystemTrayIcon, QMenu,
)

from cerebro import Cerebro
from oido import Grabadora, GrabadoraPC, EscuchaContinua, fue_llamada, transcribir, precargar
from boca import hablar, esta_hablando, aviso
import ojos
import ventanas as vent
from web_conocimiento import mapa_visual
import dispositivos
import spotify_sage
import ajustes
import seguridad
import recuerdos
import comentarista

AQUI = os.path.dirname(os.path.abspath(__file__))
RUTA_AVATAR = os.path.join(AQUI, "avatar.png")
RUTA_ICONO = os.path.join(AQUI, "sage.ico")

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
    r'\[(?P<tipo>SEGURIDAD|AJUSTE|ABRIR_FONDO|RECORDAR|OLVIDAR|RECUERDO_MOVER|RECUERDOS_ORDENAR|ABRIR|ENFOCAR|CERRAR|TECLA|PULSAR_DER|PULSAR|BUSCAR|ATAJO|ARRASTRAR|DESCARGAR|DIBUJAR|TRAZO|JUGAR|CERRAR_PESTA[ÑN]A|MINIMIZAR|MAXIMIZAR|VENTANA|MULTIMEDIA|DISCORD|CEL_ABRIR|CEL_TOCAR|CEL_ESCRIBIR|CEL_DESLIZAR|CEL_TECLA|CEL_PANTALLA|SPOTIFY_PLAYLIST|SPOTIFY_EN_PLAYLIST|SPOTIFY_VOLUMEN|SPOTIFY):\s*(?P<arg>.*?)\]'
    r'|(?s:\[(?P<tipo_e>ESCRIBIR):\s*(?P<arg_e>.*?)\])'
    r'|(?s:\[(?P<tipo_f>ARCHIVO):\s*(?P<arg_f>.*?)\])'
    r'|\[(?P<tipo_c>CLICK):\s*(?P<x>\d+)\s*,\s*(?P<y>\d+)\]'
    r'|\[(?P<tipo_d>CLICK_DER)(?::\s*(?P<xd>\d+)\s*,\s*(?P<yd>\d+))?\]'
    r'|\[(?P<tipo_s>SCROLL):\s*(?P<cant>-?\d+)\]'
    r'|\[(?P<tipo_w>ESPERAR)(?::\s*(?P<seg>\d+(?:\.\d+)?))?\]'
    r'|\[(?P<tipo_t>TEMPORIZADOR):\s*(?P<seg_t>\d+)\s*,\s*(?P<msg_t>.*?)\]'
    r'|\[(?P<tipo_p>APAGAR_PC)(?::\s*(?P<arg_p>[^\]]*))?\]'
    r'|\[(?P<tipo_x>CIRCULOS)\]',
    re.I,
)
RE_APAGAR = re.compile(r'\[APAGAR\]', re.I)
RE_SEGUNDO_PLANO = re.compile(r'\[SEGUNDO_PLANO\]', re.I)
RE_PRIMER_PLANO = re.compile(r'\[PRIMER_PLANO\]', re.I)
RE_LIMPIAR = re.compile(
    r'\[(?:SEGURIDAD|AJUSTE|ABRIR_FONDO|RECORDAR|OLVIDAR|RECUERDO_MOVER|RECUERDOS_ORDENAR|ABRIR|ENFOCAR|CERRAR|TECLA|PULSAR_DER|PULSAR|BUSCAR|ATAJO|ARRASTRAR|DESCARGAR|DIBUJAR|TRAZO|JUGAR|CERRAR_PESTA[ÑN]A|MINIMIZAR|MAXIMIZAR|VENTANA|MULTIMEDIA|DISCORD|TEMPORIZADOR|CEL_ABRIR|CEL_TOCAR|CEL_ESCRIBIR|CEL_DESLIZAR|CEL_TECLA|CEL_PANTALLA|SPOTIFY_PLAYLIST|SPOTIFY_EN_PLAYLIST|SPOTIFY_VOLUMEN|SPOTIFY):\s*.*?\]'
    r'|(?s:\[ESCRIBIR:\s*.*?\])'
    r'|(?s:\[ARCHIVO:\s*.*?\])'
    r'|(?s:\[MENSAJE:\s*.*?\])'
    r'|\[CLICK:\s*\d+\s*,\s*\d+\]'
    r'|\[CLICK_DER(?::\s*\d+\s*,\s*\d+)?\]'
    r'|\[SCROLL:\s*-?\d+\]'
    r'|\[ESPERAR(?::\s*\d+(?:\.\d+)?)?\]'
    r'|\[CIRCULOS\]|\[APAGAR\]|\[SEGUNDO_PLANO\]|\[PRIMER_PLANO\]|\[APAGAR_PC(?::[^\]]*)?\]',
    re.I,
)
RE_PARCIAL = re.compile(r'\[(?:SEGURIDAD|AJUSTE|ABRIR_FONDO|RECORDAR|OLVIDAR|RECUERDO|RECUERDOS|ABRIR|ENFOCAR|CERRAR|TECLA|ESCRIBIR|ARCHIVO|MENSAJE|PULSAR|BUSCAR|ATAJO|ARRASTRAR|DESCARGAR|DIBUJAR|TRAZO|JUGAR|CERRAR_PESTA[ÑN]A|MINIMIZAR|MAXIMIZAR|VENTANA|MULTIMEDIA|DISCORD|CLICK|SCROLL|ESPERAR|CIRCULOS|APAGAR|SEGUNDO_PLANO|PRIMER_PLANO|TEMPORIZADOR|SPOTIFY|CEL_\w+)[^\]]*$', re.I)

def _terminar_ya(codigo=0):
    """Termina el proceso AHORA (os._exit): no espera a hilos de audio, Whisper, adb ni nada que quede en segundo plano."""
    try:
        sys.stdout.flush()
        sys.stderr.flush()
    except Exception:
        pass
    os._exit(int(codigo or 0))


def _salida_forzosa(segundos):
    """Temporizador de seguridad: si el cierre normal se cuelga, a los N segundos el proceso se termina a la fuerza."""
    t = threading.Timer(segundos, _terminar_ya)
    t.daemon = True
    t.start()


# Órdenes sobre la ventana de SAGE que se resuelven al instante, sin modelo (texto ya normalizado: minúsculas y sin tildes)
# Modo comentarista (SAGE mira la pantalla de forma continua y opina): se enciende/apaga al instante, sin modelo (texto ya sin tildes)
_RE_COM_OFF = re.compile(
    r"\b(?:deja(?:r)?\s+de\s+(?:comentar|vigilar|mirar\s+mi\s+pantalla)|(?:ya\s+)?no\s+(?:me\s+)?(?:comentes|vigiles)|para\s+de\s+comentar|basta\s+de\s+comentar|"
    r"(?:desactiva|apaga|quita|termina|cancela)\s+(?:el\s+)?(?:modo\s+)?comentarista|sin\s+comentarista)\b")
_RE_COM_ON = re.compile(
    r"\b(?:s[e]\s+(?:mi|el)\s+comentarista|(?:activa|enciende|pon|inicia|empieza|comienza)\s+(?:el\s+|tu\s+)?(?:modo\s+)?comentarista|"
    r"comenta\s+(?:lo\s+que|todo\s+lo\s+que|mi\s+pantalla|el\s+juego|mientras|en\s+vivo|en\s+tiempo\s+real)|"
    r"(?:mira|vigila|observa)\s+(?:mi\s+)?pantalla\s+(?:todo\s+el\s+tiempo|continuamente|sin\s+parar|en\s+tiempo\s+real|siempre)|"
    r"opina\s+(?:de|sobre)\s+lo\s+que\s+(?:pasa|veas|hago))")
_RE_ORDEN_APAGAR = re.compile(
    r"\bapaga\s?te\b|\bapaga\s+sage\b|\b(?:vete|ve|ponte|pon\s?te|anda|andate)\s+a\s+(?:descansar|dormir)\b"
    r"|\bcierra\s?te\s+(?:del\s+todo|por\s+completo)\b|\bcierra\s+sage\s+(?:del\s+todo|por\s+completo)\b"
    r"|^\W*(?:sage\W+)?a\s+descansar\W*$"
    # «apágate en segundo plano», «cierra el programa de sage en segundo plano», «termina tu proceso», «mátate»...
    r"|\b(?:apaga|termina|finaliza|mata)\s?(?:te)?\b[^.?!]{0,30}\b(?:programa|proceso|aplicacion|app|sage)\b[^.?!]{0,30}\b(?:segundo plano|background|bandeja)\b"
    r"|\bcierra\b[^.?!]{0,20}\b(?:programa|proceso|aplicacion)\b[^.?!]{0,30}\b(?:segundo plano|background|bandeja)\b"
    r"|\b(?:segundo plano|background|bandeja)\b[^.?!]{0,30}\b(?:apaga\s?te|cierra\s?te\s+(?:del\s+todo|por\s+completo)|termina\s?te|matate)\b"
    r"|\b(?:apaga\s?te|matate|termina\s?te)\b[^.?!]{0,30}\b(?:segundo plano|background|bandeja)\b"
    r"|\b(?:cierra|termina|finaliza|mata)\s+(?:por\s+completo\s+)?(?:tu|el)\s+(?:programa|proceso)\b")
_RE_ORDEN_SEGUNDO = re.compile(
    r"\b(?:pon\s?te|pasa\s?te|queda\s?te|manda\s?te|mete\s?te|retira\s?te|vete)\b[^.?!]{0,30}\b(?:segundo plano|bandeja|background)\b"
    r"|\b(?:oculta\s?te|esconde\s?te|minimiza\s?te)\b"
    r"|\b(?:pasa|pon|manda|ve|vete)\s+(?:a|en|al)\s+(?:el\s+)?(?:segundo plano|bandeja)\b"
    r"|\b(?:cierra|oculta|esconde|quita|minimiza)\s+tu\s+(?:ventana|interfaz|hud|pantalla)\b")
_RE_ORDEN_PRIMER = re.compile(
    r"\b(?:pon\s?te|pasa|pasa\s?te|vuelve|regresa|ven|sal)\b[^.?!]{0,25}\bprimer plano\b"
    r"|\b(?:muestra\s?te|asoma\s?te)\b"
    r"|\b(?:abre|muestra|saca|trae|ensena)\s+tu\s+(?:ventana|interfaz|hud|pantalla)\b"
    r"|^\W*(?:sage\W+)?(?:aparece|reaparece|vuelve|regresa|ven)\W*(?:sage)?\W*$")


def extraer_acciones(texto):
    """Devuelve las directivas EN EL ORDEN en que aparecen: [(tipo, argumento), ...]."""
    acciones = []
    for m in RE_ACCION.finditer(texto):
        if m.group("tipo"): acciones.append((m.group("tipo").lower().replace("ñ", "n"), m.group("arg").strip()))
        elif m.group("tipo_e"): acciones.append(("escribir", m.group("arg_e")))
        elif m.group("tipo_f"): acciones.append(("archivo", m.group("arg_f").strip()))  # <-- AÑADIR ESTO
        elif m.group("tipo_c"): acciones.append(("click", (m.group("x"), m.group("y"))))
        elif m.group("tipo_d"): acciones.append(("click_der", (m.group("xd"), m.group("yd"))))
        elif m.group("tipo_s"): acciones.append(("scroll", m.group("cant")))
        elif m.group("tipo_w"): acciones.append(("esperar", m.group("seg") or ""))
        elif m.group("tipo_t"): acciones.append(("temporizador", f"{m.group('seg_t')},{m.group('msg_t')}"))
        elif m.group("tipo_p"): acciones.append(("apagar_pc", (m.group("arg_p") or "").strip()))
        elif m.group("tipo_x"): acciones.append(("circulos", ""))
    return acciones


RE_SEGURO = re.compile(r'[^\w.\- ]')


def limpiar(texto):
    return RE_LIMPIAR.sub('', texto).strip()


def limpiar_parcial(texto):
    return RE_PARCIAL.sub('', RE_LIMPIAR.sub('', texto)).strip()


# ---------- Mensaje a toda la ventana ----------
# [MENSAJE: texto]  |  [MENSAJE: 10 | texto] (se cierra solo a los 10 s)  |  [MENSAJE: cerrar]
# No pasa por el Ejecutor (no usa mouse ni teclado): lo muestra la propia ventana de SAGE.
RE_MENSAJE = re.compile(r'(?s:\[\s*MENSAJE:\s*(.*?)\])', re.I)
_RE_MENSAJE_DUR = re.compile(r'^(\d{1,3}(?:[.,]\d+)?)\s*(?:s|seg|segs|segundos)?\s*\|\s*(.+)$', re.S | re.I)
_RE_MENSAJE_CERRAR = re.compile(r'^(?:cerrar|cierra|ocultar|oculta|quitar|quita|borrar|borra|esconder|esconde)\W*$', re.I)
MENSAJE_MAX = 600


def _limpiar_mensaje(texto):
    t = (texto or "").replace("\\n", "\n").strip()
    t = re.sub(r"\n{3,}", "\n\n", t)
    if len(t) >= 2 and (t[0], t[-1]) in {('"', '"'), ("'", "'"), ("«", "»"), ("“", "”")}:
        t = t[1:-1].strip()
    if len(t) > MENSAJE_MAX:
        t = t[:MENSAJE_MAX - 1].rstrip() + "…"
    return t


def extraer_mensajes(texto):
    """[MENSAJE: ...] de la respuesta del modelo, en orden: [("mostrar", texto, segundos|None) | ("cerrar", "", None)]."""
    res = []
    for m in RE_MENSAJE.finditer(texto or ""):
        cuerpo = m.group(1).strip()
        if not cuerpo:
            continue
        if _RE_MENSAJE_CERRAR.match(cuerpo):
            res.append(("cerrar", "", None))
            continue
        dur = None
        d = _RE_MENSAJE_DUR.match(cuerpo)
        if d:
            dur = min(120.0, max(2.0, float(d.group(1).replace(",", "."))))
            cuerpo = d.group(2)
        cuerpo = _limpiar_mensaje(cuerpo)
        if cuerpo:
            res.append(("mostrar", cuerpo, dur))
    return res


_P_SAGE = r"^\s*(?:oye\s+|hey\s+|ok\s+)?(?:sage[\s,:;.!¡]*)?(?:por\s+favor[\s,]*)?(?:ahora\s+)?"
_V_MOSTRAR = r"(?P<v>mu[eé]stra(?:me)?|ense[ñn]a(?:me)?|pon(?:me)?|saca(?:me)?|despliega|proyecta|escribe(?:me)?)"
_LOC = r"(?P<loc>en\s+(?:toda\s+)?(?:la\s+)?(?:ventana|pantalla)(?:\s+de\s+sage)?(?:\s+completa)?)"
_DICE = r"(?P<dice>(?:que\s+(?:dice|diga)|diciendo|dice)\b)"
_RE_ORDEN_1 = re.compile(_P_SAGE + _V_MOSTRAR + r"\s+(?:(?:el|un)\s+)?mensaje\s*(?:" + _LOC + r")?\s*(?:" + _DICE
                         + r")?\s*(?P<dos>[:\-–,])?\s*(?P<m>\S.*)$", re.I | re.S)
_RE_ORDEN_2 = re.compile(_P_SAGE + _V_MOSTRAR + r"\s+" + _LOC + r"(?:\s+(?:el|un)\s+mensaje)?\s*(?:" + _DICE + r"\s*[:\-–,]?\s*|[:\-–,]\s*|(?=[\"“«']))(?P<m>\S.*)$", re.I | re.S)
_RE_ORDEN_CERRAR = re.compile(_P_SAGE + r"(?:cierra|cerrar|quita|quitar|oculta|ocultar|borra|borrar|esconde|esconder)"
                              r"(?:\s+(?:el|ese|este|tu))?\s+mensaje(?:\s+(?:de|en)\s+(?:la\s+)?(?:ventana|pantalla))?[\s.!]*$", re.I)


def interpretar_orden_mensaje(texto):
    """Órdenes de Niko que se resuelven sin gastar una llamada al modelo."""
    t = (texto or "").strip()
    if not t or t.startswith("["):
        return None
    if _RE_ORDEN_CERRAR.match(t):
        return ("cerrar", "", None)
    m = _RE_ORDEN_1.match(t)
    if m:
        v = m.group("v").lower()
        pista = bool(m.group("loc") or m.group("dice") or m.group("dos"))
        if pista and (m.group("loc") or not v.startswith("escribe")):
            msg = _limpiar_mensaje(m.group("m"))
            if msg:
                return ("mostrar", msg, None)
    m = _RE_ORDEN_2.match(t)
    if m:
        msg = _limpiar_mensaje(m.group("m"))
        if msg:
            return ("mostrar", msg, None)
    return None


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
    background-color: rgba(5, 10, 16, 235);
    border: 1px solid #39ff14;
    border-left: 5px solid #39ff14;
    border-radius: 0px;
    padding: 12px 14px;
    color: #ffffff;
    font-size: 14px;
    font-style: italic;
}
QLineEdit:focus { border-color: #00f3ff; background-color: #0f1218; }
QLineEdit:disabled { border-color: #1a3440; color: #3a5560; }
QLabel#estado {
    color: #39ff14;
    font-weight: 900;
    font-size: 14px;
    letter-spacing: 6px;
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
        if user32.IsIconic(hwnds[0]):
            user32.ShowWindow(hwnds[0], 9)   # solo si estaba minimizada; si estaba maximizada o a pantalla completa se respeta
        user32.SetForegroundWindow(hwnds[0])
        return True
    return False


# ---------- Segundo plano: acciones que NO tocan el mouse, el teclado ni la ventana activa de Niko ----------
ACCIONES_FONDO = frozenset({"cerrar", "minimizar", "maximizar", "ventana", "cerrar_pestana", "multimedia", "discord", "esperar", "temporizador", "seguridad", "ajuste", "abrir_fondo", "recordar", "olvidar", "recuerdo_mover", "recuerdos_ordenar", "apagar_pc", "spotify", "spotify_playlist", "spotify_en_playlist", "spotify_volumen",
                           "cel_abrir", "cel_tocar", "cel_escribir", "cel_deslizar", "cel_tecla", "cel_pantalla", "archivo"})


def es_segundo_plano(acciones):
    return bool(acciones) and all(t in ACCIONES_FONDO for t, _ in acciones)


def _norm(texto):
    t = unicodedata.normalize("NFD", str(texto).lower())
    return "".join(c for c in t if unicodedata.category(c) != "Mn")


_STOP_PESTANA = frozenset("pestana pestanas tab tabs ventana de del la el los las que dice llamada llamadas con en "
                          "navegador opera gx una un esa ese esas esos".split())


def parsear_pestana(arg):
    """'todas | youtube' -> (True, ['youtube']); 'la pestaña de gmail' -> (False, ['gmail'])."""
    texto, todas = _norm(arg), False
    if "|" in texto:
        pref, resto = texto.split("|", 1)
        if re.search(r"\btodas?\b|\btodos?\b", pref):
            todas, texto = True, resto
    elif re.match(r"^\s*(?:todas|todos)\b", texto):
        todas = True
    palabras = [p for p in re.findall(r"[\w.\-/]+", texto) if p not in _STOP_PESTANA and p not in ("todas", "todos")]
    return todas, palabras


def coincide(palabras, texto):
    t = _norm(texto)
    return bool(palabras) and all(p in t for p in palabras)


def _exe_de_pid(pid):
    import ctypes
    from ctypes import wintypes
    k = ctypes.windll.kernel32
    h = k.OpenProcess(0x1000, False, pid)  # PROCESS_QUERY_LIMITED_INFORMATION
    if not h: return ""
    try:
        buf, n = ctypes.create_unicode_buffer(1024), wintypes.DWORD(1024)
        return buf.value if k.QueryFullProcessImageNameW(h, 0, buf, ctypes.byref(n)) else ""
    finally:
        k.CloseHandle(h)


def _pestanas_cdp():
    """Pestañas vía depuración remota (Opera lanzado con --remote-debugging-port=9222). None si no está activa."""
    import json
    import urllib.request
    puerto = os.getenv("SAGE_OPERA_DEBUG_PORT", "9222")
    try:
        with urllib.request.urlopen(f"http://127.0.0.1:{puerto}/json/list", timeout=0.7) as r:
            datos = json.loads(r.read().decode("utf-8", "replace"))
    except Exception:
        return None
    return puerto, [d for d in datos if d.get("type") == "page" and d.get("id")]


def _pestanas_uia():
    """[(título, wrapper)] de las pestañas de todas las ventanas del navegador (UI Automation, sin tocar el foco)."""
    from pywinauto import Desktop
    from pywinauto.controls.uiawrapper import UIAWrapper
    exe_buscado = os.getenv("SAGE_NAVEGADOR_EXE", "opera").lower()
    res = []
    for w in Desktop(backend="uia").windows(class_name="Chrome_WidgetWin_1"):
        try:
            if exe_buscado not in os.path.basename(_exe_de_pid(w.process_id())).lower(): continue
            for info in w.element_info.descendants(control_type="TabItem"):
                res.append((info.name or "", UIAWrapper(info)))
        except Exception:
            continue
    return res


def _cerrar_tab_uia(wrap):
    """Pulsa (por UI Automation, sin mouse) el botón de cerrar que cuelga de la pestaña."""
    from pywinauto.controls.uiawrapper import UIAWrapper
    botones = wrap.element_info.descendants(control_type="Button")
    for b in botones:
        n = _norm(b.name or "")
        if "cerrar" in n or "close" in n or (len(botones) == 1 and not n):
            UIAWrapper(b).invoke()
            return True
    return False


def cerrar_pestanas_fondo(palabras, todas=False):
    """Cierra pestañas del navegador SIN mover el mouse ni cambiar la ventana activa."""
    cdp = _pestanas_cdp()
    if cdp is not None:
        import urllib.request
        puerto, paginas = cdp
        coinc = [p for p in paginas if coincide(palabras, f"{p.get('title', '')} {p.get('url', '')}")]
        if not coinc:
            return [], "no encontré ninguna pestaña con eso; abiertas: " + ", ".join((p.get("title") or "")[:30] for p in paginas[:8]), False
        cerradas = []
        for p in (coinc if todas else coinc[:1]):
            try:
                urllib.request.urlopen(f"http://127.0.0.1:{puerto}/json/close/{p['id']}", timeout=2).read()
                cerradas.append(p.get("title") or p.get("url") or "(sin título)")
            except Exception:
                pass
        return (cerradas, "", False) if cerradas else ([], "la depuración remota no pudo cerrarla", True)

    try:
        tabs = []
        for _ in range(3):   # la primera consulta despierta la accesibilidad de Chromium: puede salir vacía
            tabs = _pestanas_uia()
            if tabs: break
            time.sleep(0.7)
    except ImportError:
        return [], "falta instalar pywinauto (pip install pywinauto)", True
    except Exception as e:
        return [], f"UI Automation falló: {e}", True
    if not tabs:
        return [], "no pude leer las pestañas del navegador (¿está abierto o minimizado?)", True
    coinc = [(t, w) for t, w in tabs if coincide(palabras, t)]
    if not coinc:
        return [], "no encontré ninguna pestaña con eso; vi: " + ", ".join(t[:30] for t, _ in tabs[:8]), False
    cerradas = []
    for t, w in (coinc if todas else coinc[:1]):
        try:
            if _cerrar_tab_uia(w):
                cerradas.append(t or "(sin título)")
                time.sleep(0.15)
        except Exception:
            pass
    return (cerradas, "", False) if cerradas else ([], "no encontré el botón de cerrar de la pestaña", True)


_MEDIA_VK = {"playpause": 0xB3, "next": 0xB0, "prev": 0xB1, "stop": 0xB2, "mute": 0xAD, "down": 0xAE, "up": 0xAF}


def interpretar_multimedia(arg):
    """'subir 10' -> ('up', 10). Devuelve (clave, repeticiones) o (None, 1)."""
    t = _norm(arg)
    m = re.search(r"\d+", t)
    n = min(50, max(1, int(m.group()))) if m else None
    for clave, patron in (("mute", r"silenc|mute"), ("up", r"\b(?:sub|aument|mas volumen|up)"),
                          ("down", r"\b(?:baj|disminu|menos volumen|down)"), ("next", r"siguiente|next|salta|adelant"),
                          ("prev", r"anterior|previ|atras"), ("stop", r"deten|stop|parar"),
                          ("playpause", r"paus|play|reprod|reanud|contin")):
        if re.search(patron, t):
            return clave, n or (5 if clave in ("up", "down") else 1)
    return None, 1


def tecla_multimedia(clave, veces=1):
    """Pulsa una tecla multimedia global (no cambia de ventana)."""
    import ctypes
    if sys.platform != "win32": raise RuntimeError("solo Windows")
    vk = _MEDIA_VK[clave]
    for _ in range(veces):
        ctypes.windll.user32.keybd_event(vk, 0, 1, 0)   # KEYEVENTF_EXTENDEDKEY
        ctypes.windll.user32.keybd_event(vk, 0, 3, 0)   # + KEYEVENTF_KEYUP
        time.sleep(0.02)


# ---------- Energía del PC: apagar / reiniciar / suspender / hibernar / cerrar sesión (siempre con cuenta atrás cancelable) ----------
_ENERGIA = {"hasta": 0.0, "modo": "", "cancelado": False}


def _shutdown(*args):
    return subprocess.run(["shutdown", *args], capture_output=True, text=True, encoding="mbcs", errors="replace",
                          creationflags=subprocess.CREATE_NO_WINDOW)


def interpretar_energia(arg):
    """'reiniciar en 10 minutos' -> ('reiniciar', 600). Sin tiempo: SAGE_APAGADO_DEMORA (30 s por defecto, entre 5 y 600)."""
    t = _norm(arg)
    modo = "apagar"
    for patron, nombre in (("cancel", "cancelar"), ("abort", "cancelar"), ("reinici", "reiniciar"), ("restart", "reiniciar"),
                           ("reboot", "reiniciar"), ("hibern", "hibernar"), ("suspen", "suspender"), ("dormir", "suspender"),
                           ("sesion", "cerrar sesion"), ("logoff", "cerrar sesion"), ("logout", "cerrar sesion")):
        if patron in t:
            modo = nombre
            break
    try: demora = max(5, min(600, int(float(os.getenv("SAGE_APAGADO_DEMORA", "30")))))
    except ValueError: demora = 30
    m = re.search(r"(\d+)\s*(horas?|h|minutos?|mins?|m|segundos?|segs?|s)?\b", t)
    if m:
        unidad = (m.group(2) or "s")[0]
        demora = max(5, min(86400, int(m.group(1)) * (3600 if unidad == "h" else 60 if unidad == "m" else 1)))
    return modo, demora


def energia_pendiente():
    return not _ENERGIA["cancelado"] and time.time() < _ENERGIA["hasta"]


def programar_energia(modo, segundos):
    """Apagar/reiniciar usan el temporizador del propio Windows (sobrevive aunque SAGE se cierre). Los demás modos
    solo se registran: el Ejecutor espera la cuenta atrás y luego llama a ejecutar_energia_diferida()."""
    _ENERGIA.update(hasta=time.time() + segundos, modo=modo, cancelado=False)
    if modo in ("apagar", "reiniciar"):
        _shutdown("/a")  # limpia una programación anterior (si no, Windows rechaza la nueva con el error 1190)
        args = ["/s" if modo == "apagar" else "/r", "/t", str(segundos), "/c", "SAGE: di «SAGE, cancela» o ejecuta «shutdown /a» para cancelar."]
        if os.getenv("SAGE_APAGADO_FORZAR", "0").strip() == "1": args.append("/f")
        r = _shutdown(*args)
        if r.returncode != 0:
            _ENERGIA["hasta"] = 0.0
            return False, (r.stderr or r.stdout or f"código {r.returncode}").strip()
    return True, ""


def ejecutar_energia_diferida(modo):
    if modo == "hibernar": r = _shutdown("/h")
    elif modo == "cerrar sesion": r = _shutdown("/l")
    else: r = subprocess.run(["rundll32.exe", "powrprof.dll,SetSuspendState", "0,1,0"], capture_output=True, creationflags=subprocess.CREATE_NO_WINDOW)
    return r.returncode == 0, ((getattr(r, "stderr", "") or "").strip() if isinstance(getattr(r, "stderr", ""), str) else "")


def cancelar_energia():
    """Cancela el apagado/reinicio/suspensión programado. Devuelve True si había uno pendiente."""
    if not energia_pendiente():
        return False
    _ENERGIA["cancelado"] = True
    if _ENERGIA["modo"] in ("apagar", "reiniciar"):
        _shutdown("/a")
    _ENERGIA["hasta"] = 0.0
    return True


# Juegos que se abren por su URI de Steam (más fiable que buscar el .exe). Añade los tuyos aquí.
JUEGOS_LANZADOR = {
    "geometry dash": "steam://rungameid/322170",
    "geometrydash": "steam://rungameid/322170",
}

DURACION_MOUSE = float(os.getenv("SAGE_MOUSE_DURACION", "0.09"))   # tope de segundos por desplazamiento (antes 0.18)
VELOCIDAD_MOUSE = float(os.getenv("SAGE_MOUSE_VELOCIDAD", "9000"))  # px/s: los trayectos cortos son aún más rápidos
# SAGE_VERIFICAR=siempre fuerza la mirada final con visión tras cada ejecución; por defecto ("auto") solo se hace si algo falló
VERIFICAR_SIEMPRE = os.getenv("SAGE_VERIFICAR", "auto").strip().lower() == "siempre"


def mover_rapido(pag, x, y):
    """Lleva el cursor a (x, y) con una curva suave pero MUY rápida: la duración depende de la distancia
    (a 9000 px/s cruzar toda la pantalla tarda ~0.09 s) y los saltos cortos son instantáneos."""
    try:
        px, py = pag.position()
    except Exception:
        px, py = x, y
    dur = min(DURACION_MOUSE, math.hypot(x - px, y - py) / VELOCIDAD_MOUSE)
    if dur < 0.03:
        pag.moveTo(x, y, _pause=False)
    else:
        pag.moveTo(x, y, duration=dur, tween=pag.easeOutQuad)
UMBRAL_CLICK_DER = 0.004  # un menú contextual es pequeño: se confirma con un cambio de pantalla menor que el de un click normal


def escribir_unicode(texto, intervalo=0.003):
    """Escribe cualquier texto (tildes, ñ, ¿¡, emojis) con SendInput Unicode. pyautogui.write NO sabe escribir
    caracteres fuera de ASCII. Solo Windows. '\n' se envía como Enter y '\t' como Tab."""
    import ctypes
    from ctypes import wintypes

    if sys.platform != "win32":
        raise RuntimeError("escribir_unicode solo funciona en Windows")

    class MOUSEINPUT(ctypes.Structure):
        _fields_ = [("dx", wintypes.LONG), ("dy", wintypes.LONG), ("mouseData", wintypes.DWORD),
                    ("dwFlags", wintypes.DWORD), ("time", wintypes.DWORD), ("dwExtraInfo", ctypes.c_size_t)]

    class KEYBDINPUT(ctypes.Structure):
        _fields_ = [("wVk", wintypes.WORD), ("wScan", wintypes.WORD), ("dwFlags", wintypes.DWORD),
                    ("time", wintypes.DWORD), ("dwExtraInfo", ctypes.c_size_t)]

    class _U(ctypes.Union):
        _fields_ = [("mi", MOUSEINPUT), ("ki", KEYBDINPUT)]

    class INPUT(ctypes.Structure):
        _anonymous_ = ("u",)
        _fields_ = [("type", wintypes.DWORD), ("u", _U)]

    def enviar(vk, scan, flags):
        entrada = INPUT()
        entrada.type = 1  # INPUT_KEYBOARD
        entrada.ki = KEYBDINPUT(vk, scan, flags, 0, 0)
        ctypes.windll.user32.SendInput(1, ctypes.byref(entrada), ctypes.sizeof(INPUT))

    for ch in texto:
        if ch in ("\n", "\t"):
            vk = 0x0D if ch == "\n" else 0x09
            enviar(vk, 0, 0)
            enviar(vk, 0, 2)
        else:
            datos = ch.encode("utf-16-le")
            for i in range(0, len(datos), 2):
                unidad = int.from_bytes(datos[i:i + 2], "little")
                enviar(0, unidad, 0x0004)          # KEYEVENTF_UNICODE
                enviar(0, unidad, 0x0004 | 0x0002)  # + KEYEVENTF_KEYUP
        time.sleep(intervalo)


class Ejecutor(QThread):
    """Ejecuta los comandos tácticos EN ORDEN mirando la pantalla en tiempo real:
    espera a que las páginas terminen de cargar, localiza los elementos con visión,
    verifica que cada click surtió efecto, reintenta y aprende de sus errores."""
    log = Signal(str)
    vista = Signal(bytes, int, int, str)  # fotograma + texto para la ventanita «SAGE ve en vivo» (w=0 la cierra)
    hud = Signal(bool)  # False = ocultar la HUD (para que no tape ni ensucie la captura), True = mostrarla
    ajuste = Signal(str)   # cambios de configuración pedidos por voz (se aplican en el hilo de la interfaz)
    alarma = Signal(str)  # Señal para conectar temporizadores en segundo plano

    MAX_INTENTOS = 4
    MAX_PASOS = 20  # máximo de pasos de búsqueda (mirar + scroll) por elemento

    def __init__(self, acciones, cerebro=None, objetivo=""):
        super().__init__()
        self.acciones = acciones
        self.cerebro = cerebro
        self.objetivo = objetivo
        self.cancelado = False
        self._pag = None
        self._espera = None       # None | "abrir" | "enfocar": hay que esperar a que la pantalla se calme
        self._dominio = ""
        self._notas = []
        self._vio_pantalla = False
        self._obstaculos = 0
        self._esperas_ult = 0
        self._ya_espero = False   # ya se esperó a que la página cargara (evita una espera extra al buscar)
        self._ultimo_entorno = ""
        self._ult_vista = 0.0
        self.fondo = es_segundo_plano(acciones)   # solo acciones que no tocan mouse/teclado/ventana de Niko
        self._hud_oculto = False

    # ---------- flujo principal ----------
    def run(self):
        ocultar = not self.fondo
        self._hud_oculto = ocultar
        if ocultar:
            self.hud.emit(False)
            time.sleep(0.2)
        try:
            self._ejecutar()
        except Exception as e:
            self.log.emit(f"⚠ Fallo inesperado del ejecutor: {e}")
        finally:
            if not self.fondo: self.vista.emit(b"", 0, 0, "")   # una tarea de fondo no debe cerrar la ventanita de otra
            if ocultar:
                self.hud.emit(True)

    def _ejecutar(self):
        # ... (código anterior)
        self._aprender_de_fallos()
        if self.cerebro is not None and self._notas:
            self.cerebro.registrar_resultado(" | ".join(self._notas))
        log = self.log.emit
        if any(t in ("escribir", "tecla", "atajo", "buscar", "click", "click_der", "pulsar", "pulsar_der", "scroll", "circulos",
                                              "arrastrar", "descargar", "dibujar", "trazo", "jugar", "cerrar_pestana")
               for t, _ in self.acciones):
            try:
                import pyautogui
                pyautogui.PAUSE = 0.005          # por defecto pyautogui espera 0.1 s tras CADA acción
                pyautogui.MINIMUM_DURATION = 0.0  # por defecto movía al instante todo lo menor de 0.1 s...
                pyautogui.MINIMUM_SLEEP = 0.003   # ...y paraba 50 ms entre pasos: ahora los movimientos cortos salen fluidos
                self._pag = pyautogui
            except Exception as e:
                log(f"⚠ pyautogui no disponible: {e}")

        for tipo, arg in self.acciones:
            if getattr(self, "cancelado", False):
                log("🛑 Ejecución cancelada por el usuario.")
                break
            try:
                getattr(self, f"_a_{tipo}")(arg)
            except Exception as e:
                log(f"⚠ Fallo en {tipo.upper()}: {e}")
                self._notas.append(f"{tipo.upper()} falló ({e})")

        fallos = any(self._RE_FALLO.search(n) for n in self._notas)
        if self._vio_pantalla and self.cerebro is not None and not self.cancelado and (fallos or VERIFICAR_SIEMPRE):
            self._verificacion_final()   # una llamada de visión extra (1-3 s): solo si algo salió mal
        self._aprender_de_fallos()
        if self.cerebro is not None and self._notas:
            self.cerebro.registrar_resultado(" | ".join(self._notas))

    _RE_FALLO = re.compile(r"SIN efecto|NO logré|no encontré|falló|no pude|no hay control|sin plantilla|mal formado", re.I)

    def _a_archivo(self, arg):
        """[ARCHIVO: listar|leer|escribir|añadir | ruta | contenido] Módulo de manipulación local."""
        partes = [p.strip() for p in arg.split("|", 2)]
        if len(partes) < 2:
            self._notas.append("ARCHIVO mal formado: usa accion | ruta | contenido")
            return
            
        accion, ruta = partes[0].lower(), partes[1].strip('"').strip("'")
        
        if accion == "listar":
            try:
                elem = os.listdir(ruta)
                lista = ", ".join(elem[:150]) + ("..." if len(elem) > 150 else "")
                self._notas.append(f"Contenido de la carpeta '{ruta}': {lista}")
                self.log.emit(f"📂 Carpeta listada: {os.path.basename(ruta) or ruta}")
            except Exception as e:
                self._notas.append(f"Fallo al listar '{ruta}': {e}")
                self.log.emit(f"⚠ Fallo al listar: {e}")
                
        elif accion == "leer":
            try:
                with open(ruta, "r", encoding="utf-8", errors="replace") as f:
                    contenido = f.read(4000)  # Leemos hasta 4000 caracteres para no desbordar su contexto de memoria
                self._notas.append(f"Contenido del archivo '{ruta}':\n{contenido}")
                self.log.emit(f"📄 Archivo leído: {os.path.basename(ruta)}")
            except Exception as e:
                self._notas.append(f"Fallo al leer '{ruta}': {e}")
                self.log.emit(f"⚠ Fallo al leer: {e}")
                
        elif accion in ("escribir", "añadir") and len(partes) >= 3:
            try:
                modo = "w" if accion == "escribir" else "a"
                with open(ruta, modo, encoding="utf-8") as f:
                    f.write(("\n" if accion == "añadir" else "") + partes[2])
                self._notas.append(f"Éxito al {accion} en '{ruta}'")
                self.log.emit(f"💾 Archivo modificado: {os.path.basename(ruta)}")
            except Exception as e:
                self._notas.append(f"Fallo al {accion} en '{ruta}': {e}")
                self.log.emit(f"⚠ Fallo de escritura: {e}")
        else:
            self._notas.append(f"Faltan parámetros o acción desconocida para ARCHIVO: {accion}")

    def _spotify(self, etiqueta, fn, *args):
        """Spotify por la API: no mueve el mouse, no escribe y no cambia la ventana activa de Niko."""
        try:
            msg = fn(*args)
            self.log.emit(f"🎵 {msg}")
            self._notas.append(f"{etiqueta}: {msg}")
        except spotify_sage.ErrorSpotify as e:
            self.log.emit(f"⚠ Spotify: {e}")
            self._notas.append(f"{etiqueta} falló: {e}")
        except Exception as e:
            self.log.emit(f"⚠ Error inesperado en Spotify: {e}")
            self._notas.append(f"{etiqueta} falló: {e}")

    def _a_spotify(self, arg):
        """[SPOTIFY: canción y artista] Reproduce una canción por la API, en segundo plano real."""
        self._spotify("SPOTIFY", spotify_sage.reproducir_cancion, arg.strip())

    def _a_spotify_playlist(self, arg):
        """[SPOTIFY_PLAYLIST: nombre] o [SPOTIFY_PLAYLIST: nombre | aleatorio|orden] Reproduce una playlist por la API, en segundo plano real."""
        nombre, _, modo = arg.partition("|")
        aleatorio = {"aleatorio": True, "shuffle": True, "orden": False, "en orden": False}.get(modo.strip().lower())
        self._spotify("SPOTIFY_PLAYLIST", spotify_sage.reproducir_playlist, nombre.strip(), aleatorio)

    def _a_spotify_en_playlist(self, arg):
        """[SPOTIFY_EN_PLAYLIST: canción | playlist] Reproduce UNA canción concreta de una playlist (y la playlist sigue después), por la API."""
        cancion, _, playlist = arg.partition("|")
        if not cancion.strip() or not playlist.strip():
            self.log.emit("⚠ SPOTIFY_EN_PLAYLIST necesita «canción | playlist».")
            self._notas.append("SPOTIFY_EN_PLAYLIST mal formado: usa «canción | playlist»")
            return
        self._spotify("SPOTIFY_EN_PLAYLIST", spotify_sage.reproducir_cancion_de_playlist, cancion.strip(), playlist.strip())

    def _a_spotify_volumen(self, arg):
        """[SPOTIFY_VOLUMEN: subir|bajar|subir 20|40|maximo|silenciar] Cambia el volumen de Spotify por la API (sin tocar mouse ni teclado)."""
        try:
            msg = spotify_sage.cambiar_volumen(arg.strip())
            self.log.emit(f"🔊 {msg}")
            self._notas.append(f"SPOTIFY_VOLUMEN: {msg}")
        except spotify_sage.SinControlVolumen as e:
            # Ese dispositivo no deja que Spotify toque su volumen: respaldo con las teclas de volumen del sistema (solo relativo)
            clave, veces = interpretar_multimedia(arg)
            m = re.search(r"\d+", arg)
            if clave in ("up", "down", "mute"):
                tecla_multimedia(clave, 1 if clave == "mute" else max(1, round((int(m.group()) if m else 10) / 2)))   # cada pulsación ≈ 2 %
                msg = "Spotify no deja controlar el volumen de ese dispositivo; moví el volumen del SISTEMA con las teclas multimedia."
                self.log.emit(f"🔊 {msg}")
                self._notas.append(f"SPOTIFY_VOLUMEN: {msg}")
            else:
                self.log.emit(f"⚠ Spotify: {e}")
                self._notas.append(f"SPOTIFY_VOLUMEN falló: {e} Un valor exacto solo puedo ponerlo por la API de Spotify.")
        except spotify_sage.ErrorSpotify as e:
            self.log.emit(f"⚠ Spotify: {e}")
            self._notas.append(f"SPOTIFY_VOLUMEN falló: {e}")
        except Exception as e:
            self.log.emit(f"⚠ Error inesperado en Spotify: {e}")
            self._notas.append(f"SPOTIFY_VOLUMEN falló: {e}")

    def _aprender_de_fallos(self):
        """Si algo salió mal, destila una lección y la guarda para no repetir el error."""
        if self.cerebro is None or self.cancelado: return
        if self.acciones and all(t.startswith(("cel_", "spotify")) for t, _ in self.acciones): return   # las lecciones usan capturas de la PC
        fallos = [n for n in self._notas if self._RE_FALLO.search(n)]
        if not fallos: return
        try:
            self.log.emit("🧠 Analizando por qué falló...")
            if self.cerebro.analizar_fallo(self.objetivo, [f"{t}: {a}" for t, a in self.acciones], self._notas, ojos.capturar()):
                self.log.emit("🧠 Error analizado. Lección guardada en mi memoria.")
        except Exception as e:
            print(f"[Lecciones] {e}")

    def _ver(self, img, texto="", ancho=384, min_dt=0.1):
        """Manda a la ventanita «SAGE ve en vivo» lo que SAGE está mirando (por defecto máx. ~10 fps; el piloto de GD la regula él)."""
        ahora = time.perf_counter()
        if img is None or ahora - self._ult_vista < min_dt: return
        self._ult_vista = ahora
        try:
            if isinstance(img, np.ndarray):
                a = np.ascontiguousarray(img[:, :, :3])
            else:
                a = np.asarray(img.convert("RGB").resize((ancho, max(1, int(img.height * ancho / img.width)))))
            self.vista.emit(a.tobytes(), a.shape[1], a.shape[0], str(texto)[:140])
        except Exception:
            pass

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
        self._ya_espero = True
        self.log.emit("👁 Observando la pantalla hasta que termine de cargar...")
        ok, seg = ojos.esperar_estable(
            timeout=25.0 if modo == "abrir" else 8.0,
            minimo=0.5,
            requerir_cambio=(modo == "abrir"),
        )
        if ok:
            self.log.emit(f"👁 Pantalla estable tras {seg:.1f}s. Continúo.")
        else:
            self.log.emit(f"⏳ La pantalla seguía cambiando tras {seg:.0f}s; continúo igualmente.")

    def _confirmar(self, antes, umbral=None):
        """Tras un click: espera a que se asiente y comprueba que la pantalla realmente reaccionó."""
        time.sleep(0.12)
        ojos.esperar_estable(timeout=5.0, minimo=0.2, estables=2)
        return ojos.cambio(antes, ojos.capturar(), umbral or ojos.UMBRAL_CAMBIO)

    def _aprender(self):
        if self.cerebro is None or self.cancelado: return
        sitio = f" {self._dominio}" if self._dominio else " una página web"
        leccion = (
            f"Al abrir{sitio}, el contenido tarda en cargar: hacer click enseguida falla. "
            "Debo esperar a que la pantalla termine de cargar y localizar el elemento viéndolo en pantalla "
            "con [PULSAR: descripción] en lugar de usar coordenadas fijas."
        )
        if self.cerebro.guardar_leccion(leccion):
            self.log.emit("🧠 Error analizado. Lección registrada en mi memoria para no repetirlo.")

    def _verificacion_final(self):
        time.sleep(0.3)
        img = ojos.capturar()
        if img is None: return
        r = self.cerebro.verificar_resultado(img, self.objetivo)
        if not r: return
        marca = "✅" if r["cumplido"] else "⚠"
        self.log.emit(f"{marca} Verificación visual: {r['observacion']}")
        self._notas.append(f"verificación visual: {r['observacion']} (cumplido={'sí' if r['cumplido'] else 'no'})")

    # ---------- acciones ----------
    def _a_seguridad(self, arg):
        """[SEGURIDAD: descartar | servicio] da por resuelta una alerta; [SEGURIDAD: revisar | ahora] revisa ya."""
        p = [x.strip() for x in arg.split("|", 1)]
        msg = seguridad.revisar_ahora() if p[0].lower() == "revisar" else seguridad.descartar(p[1] if len(p) > 1 else "")
        self.log.emit(f"🛡️ {msg}")
        self._notas.append(msg)

    def _a_ajuste(self, arg):
        """[AJUSTE: clave | valor] Cambia un parámetro de la configuración de SAGE (se aplica en la interfaz)."""
        self.ajuste.emit(arg)
        self._notas.append(f"cambié el ajuste «{arg.strip()}»")

    def _a_abrir_fondo(self, cmd):
        """[ABRIR_FONDO: programa, archivo, carpeta o URL] Lo abre sin tomar el foco ni tocar mouse/teclado de Niko."""
        cmd = JUEGOS_LANZADOR.get(cmd.strip().lower(), cmd.strip())
        ok, msg = vent.abrir_en_segundo_plano(cmd)
        self.log.emit(("🫥 " if ok else "⚠ ") + msg[:1].upper() + msg[1:])
        self._notas.append(msg if ok else f"NO logré abrir {cmd} en segundo plano: {msg}")

    def _a_abrir(self, cmd):
        cmd = JUEGOS_LANZADOR.get(cmd.strip().lower(), cmd.strip())
        self.log.emit(f"⚡ Ejecutando anulación de sistema: {cmd}")
        try:
            os.startfile(cmd)
        except OSError:
            # No es una ruta/URL/comando conocido: lo busca en el menú Inicio como haría una persona
            try:
                import pyautogui
                self.log.emit(f"🔎 Buscando «{cmd}» en el menú Inicio...")
                pyautogui.press("win"); time.sleep(0.5)
                pyautogui.write(cmd, interval=0.01); time.sleep(1.0)
                pyautogui.press("enter")
            except Exception as e:
                self.log.emit(f"⚠ No pude abrir «{cmd}»: {e}")
                self._notas.append(f"NO logré abrir {cmd} ({e})")
                return
        self._espera = "abrir"
        self._ya_espero = False
        if cmd.lower().startswith(("http://", "https://")):
            self._dominio = urlparse(cmd).netloc.replace("www.", "")
        self._notas.append(f"abrí {cmd}")

    def _a_enfocar(self, app_name):
        self.log.emit(f"🎯 Transfiriendo foco visual a: {app_name}")
        n = app_name.lower().strip()
        if "spotify" in n:
            os.startfile("spotify:")
        elif "discord" in n:
            if not traer_al_frente("Discord"):
                ruta = os.path.join(os.getenv('LOCALAPPDATA'), 'Discord', 'Update.exe')
                subprocess.Popen([ruta, '--processStart', 'Discord.exe'])
                time.sleep(2.0)
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
        try:
            escribir_unicode(txt)
        except Exception as e:
            self.log.emit(f"⚠ Escritura Unicode no disponible ({e}); uso el método básico.")
            pag.write(txt, interval=0.015)
        self._notas.append("escribí texto")

    def _a_tecla(self, tecla):
        pag = self._requiere_pag()
        if not pag: return
        self._esperar_pantalla()
        self.log.emit(f"⌨️ Ejecutando comando de tecla: [{tecla.upper()}]")
        pag.press(tecla.lower().strip())
        self._notas.append(f"pulsé tecla {tecla}")

    def _a_atajo(self, combo):
        pag = self._requiere_pag()
        if not pag: return
        self._esperar_pantalla()
        alias = {"control": "ctrl", "escape": "esc", "arriba": "up", "abajo": "down", "izquierda": "left",
                 "derecha": "right", "intro": "enter", "return": "enter", "mayus": "shift", "windows": "win"}
        partes = [p.strip().lower() for p in re.split(r"[+\s]+", combo) if p.strip()]
        teclas = [alias.get(p, p) for p in partes]
        if not teclas:
            self.log.emit("⚠ Atajo vacío.")
            return
        self.log.emit(f"⌨️ Ejecutando atajo: [{'+'.join(teclas).upper()}]")
        pag.hotkey(*teclas)
        time.sleep(0.15)
        self._notas.append(f"atajo {'+'.join(teclas)}")

    # ---------- celular Android (adb por Wi-Fi) ----------
    def _cel(self):
        if getattr(self, "_cel_nombre", None) is None:
            self._cel_nombre = dispositivos.por_defecto()
        return self._cel_nombre

    def _cel_foto(self):
        img, _ = dispositivos.capturar(self._cel(), guardar=False)
        self._cel_tam = img.size
        self._ver(img, "Mirando tu celular...", min_dt=0.0)
        return img

    def _cel_esperar(self, timeout=8.0, minimo=0.8):
        """Mira el celular hasta que su pantalla deja de cambiar. Devuelve la última captura."""
        t0, prev, calma, ultima = time.perf_counter(), None, 0, None
        while not self.cancelado and time.perf_counter() - t0 < timeout:
            try:
                img = self._cel_foto()
            except dispositivos.ErrorDispositivo as e:
                if "negra" not in str(e): raise
                calma = 0; time.sleep(0.4); continue   # pantalla negra momentánea (app cargando)
            ultima = img
            if prev is not None:
                calma = calma + 1 if ojos.diferencia(prev, img) <= ojos.UMBRAL_ESTABLE else 0
            prev = img
            if calma >= 2 and time.perf_counter() - t0 >= minimo: break
        return ultima

    def _a_cel_abrir(self, arg):
        msg = dispositivos.abrir_app(self._cel(), arg)
        self.log.emit(f"📱 {msg}")
        self._notas.append(f"CEL_ABRIR {arg}: {msg}")
        self._cel_esperar(10.0)

    def _a_cel_tocar(self, arg):
        nombre, desc = self._cel(), arg.strip()
        for intento in range(3):
            if self.cancelado: return
            img = self._cel_esperar(6.0, minimo=0.0)
            if img is None: raise dispositivos.ErrorDispositivo("No pude ver la pantalla del celular.")
            r = self.cerebro.localizar_elemento(img, desc, contexto="Captura completa de la pantalla de un celular Android en vertical.")
            if r is None:
                self.log.emit("⚠ El módulo de visión no respondió; reintento..."); time.sleep(0.8); continue
            if r["cargando"]:
                self.log.emit("⏳ El celular sigue cargando..."); time.sleep(0.8); continue
            if r["encontrado"]:
                W, H = img.size
                dispositivos.tocar(nombre, r["x"] * W, r["y"] * H)
                self.log.emit(f"👆 Toqué en el celular: {desc}")
                time.sleep(0.5)
                despues = self._cel_foto()
                if ojos.cambio(img, despues, 0.004):
                    self._notas.append(f"CEL_TOCAR «{desc}»: hecho")
                else:
                    self._notas.append(f"CEL_TOCAR «{desc}»: tocado pero SIN efecto visible")
                    self.log.emit("⚠ Toqué, pero la pantalla del celular no cambió.")
                return
            if r["obstaculo"] and (r["ox"] or r["oy"]):
                W, H = img.size
                self.log.emit(f"🧹 Cierro un obstáculo: {r['obstaculo']}")
                dispositivos.tocar(nombre, r["ox"] * W, r["oy"] * H); time.sleep(0.8); continue
            if intento == 1:
                self.log.emit("🔎 No lo veo; deslizo hacia abajo para buscarlo...")
                dispositivos.deslizar(nombre, "abajo", getattr(self, "_cel_tam", None))
        self._notas.append(f"CEL_TOCAR «{desc}»: no encontré el elemento en el celular")
        self.log.emit(f"⚠ No encontré «{desc}» en la pantalla del celular.")

    def _a_cel_pantalla(self, arg):
        """[CEL_PANTALLA: abrir|cerrar] comparte la pantalla del celular en una ventana de la PC (scrcpy)."""
        if _norm(arg).split()[:1] and _norm(arg).split()[0] in ("cerrar", "apagar", "quitar", "detener", "parar"):
            msg = dispositivos.espejo_cerrar(self._cel())
        else:
            msg = dispositivos.espejo_abrir(self._cel())
        self.log.emit(f"🖥 {msg}")
        self._notas.append(f"CEL_PANTALLA {arg}: {msg}")

    def _a_cel_deslizar(self, arg):
        partes = arg.split()
        veces = int(partes[1]) if len(partes) > 1 and partes[1].isdigit() else 1
        dispositivos.deslizar(self._cel(), partes[0] if partes else "", getattr(self, "_cel_tam", None), veces)
        self.log.emit(f"👆 Deslicé el celular: {arg}")
        self._notas.append(f"CEL_DESLIZAR {arg}: hecho")

    def _a_cel_escribir(self, arg):
        msg = dispositivos.escribir(self._cel(), arg)
        self.log.emit(f"⌨ {msg}")
        self._notas.append(f"CEL_ESCRIBIR: {msg}")

    def _a_cel_tecla(self, arg):
        msg = dispositivos.tecla(self._cel(), arg)
        self.log.emit(f"📱 {msg}")
        self._notas.append(f"CEL_TECLA {arg}: {msg}")
        time.sleep(0.5)

    def _a_esperar(self, seg):
        if seg:
            s = min(float(seg), 30.0)
            self.log.emit(f"⏳ Esperando {s:g}s...")
            time.sleep(s)
        else:
            if not self._espera: self._espera = "abrir"
            self._esperar_pantalla()

    def _a_apagar_pc(self, arg):
        """[APAGAR_PC] / [APAGAR_PC: reiniciar|suspender|hibernar|cerrar sesion|cancelar|en 10 minutos]: con cuenta atrás cancelable."""
        if sys.platform != "win32":
            self.log.emit("⚠ APAGAR_PC solo funciona en Windows.")
            self._notas.append("APAGAR_PC no disponible: no es Windows")
            return
        modo, seg = interpretar_energia(arg)
        if modo == "cancelar":
            if cancelar_energia():
                self.log.emit("⏻ Apagado cancelado.")
                self._notas.append("cancelé el apagado/reinicio programado")
            else:
                self.log.emit("⏻ No había ningún apagado programado.")
                self._notas.append("no había ningún apagado programado que cancelar")
            return
        verbo = {"apagar": "Apagando el PC", "reiniciar": "Reiniciando el PC", "suspender": "Suspendiendo el PC",
                 "hibernar": "Hibernando el PC", "cerrar sesion": "Cerrando la sesión"}[modo]
        cuando = f"{seg // 60} min {seg % 60} s" if seg >= 60 and seg % 60 else (f"{seg // 60} min" if seg >= 60 else f"{seg} s")
        ok, err = programar_energia(modo, seg)
        if not ok:
            self.log.emit(f"❌ No pude programar la acción: {err}")
            self._notas.append(f"NO logré programar {modo} del PC: {err}")
            return
        self.log.emit(f"⏻ {verbo} en {cuando}. Di «SAGE, cancela» o pulsa Esc para cancelarlo.")
        if modo in ("suspender", "hibernar", "cerrar sesion"):
            while time.time() < _ENERGIA["hasta"] and not self.cancelado:
                time.sleep(0.25)
            if self.cancelado or _ENERGIA["cancelado"]:
                _ENERGIA["hasta"] = 0.0
                self.log.emit("⏻ Cancelado.")
                self._notas.append(f"{modo} del PC cancelado antes de tiempo")
                return
            ok, err = ejecutar_energia_diferida(modo)
            if not ok:
                self.log.emit(f"❌ No pude ejecutar {modo}: {err}")
                self._notas.append(f"NO logré {modo} el PC: {err or 'el sistema lo rechazó (¿hibernación desactivada?)'}")
                return
        self._notas.append(f"programé {modo} del PC en {cuando} (cancelable con Esc o diciendo «SAGE, cancela»)")

    def _a_recordar(self, arg):
        """[RECORDAR: categoria | clave | valor] Guarda un recuerdo en la carpeta «recuerdos»."""
        p = [x.strip() for x in arg.split("|", 2)]
        if len(p) == 2: p = ["general"] + p
        msg = recuerdos.guardar(*p) if len(p) == 3 else "RECORDAR mal formado: usa categoria | clave | valor"
        self.log.emit(f"🧠 {msg}")
        self._notas.append(msg)

    def _a_olvidar(self, arg):
        """[OLVIDAR: categoria | clave] (clave * = toda la categoría; va a la papelera)."""
        p = [x.strip() for x in arg.split("|", 1)]
        msg = recuerdos.olvidar(p[0], p[1] if len(p) > 1 else "*") if p[0] else "OLVIDAR mal formado: usa categoria | clave"
        self.log.emit(f"🧠 {msg}")
        self._notas.append(msg)

    def _a_recuerdo_mover(self, arg):
        """[RECUERDO_MOVER: categoria_origen | clave o * | categoria_destino] (mueve, renombra o fusiona)."""
        p = [x.strip() for x in arg.split("|", 2)]
        msg = recuerdos.mover(*p) if len(p) == 3 else "RECUERDO_MOVER mal formado: usa origen | clave o * | destino"
        self.log.emit(f"🧠 {msg}")
        self._notas.append(msg)

    def _a_recuerdos_ordenar(self, _arg=""):
        msg = recuerdos.ordenar()
        self.log.emit(f"🧠 {msg}")
        self._notas.append(msg)

    def _a_temporizador(self, arg):
        m = re.match(r"^(\d+)\s*,\s*(.+)$", arg.strip())
        if not m:
            self.log.emit("⚠ TEMPORIZADOR mal formado. Usa: segundos, mensaje")
            self._notas.append("TEMPORIZADOR mal formado")
            return

        segs = int(m.group(1))
        mensaje, _, tarea = m.group(2).partition("||")   # «aviso || orden a ejecutar al terminar» (la orden es opcional)
        mensaje, tarea = mensaje.strip(), tarea.strip()
        if not mensaje:
            mensaje = tarea
        self.log.emit(f"⏱️ Temporizador iniciado: {segs}s para «{mensaje}»" + (f" + tarea «{tarea}»." if tarea else "."))

        # Lanza un reloj asíncrono para no bloquear a SAGE
        t = threading.Timer(segs, lambda: self.alarma.emit(mensaje + "\x00" + tarea))
        t.daemon = True
        t.start()
        self._notas.append(f"inicié un temporizador de {segs}s para «{mensaje}»" + (f" que ejecutará la tarea «{tarea}»" if tarea else ""))

    def _a_click(self, coords):
        pag = self._requiere_pag()
        if not pag: return
        self._esperar_pantalla()
        x, y = int(coords[0]), int(coords[1])
        self._vio_pantalla = True
        for intento in (1, 2):
            if getattr(self, "cancelado", False): return
            antes = ojos.capturar()
            self.log.emit(f"🖱️ Desplazando cursor y ejecutando click en ({x}, {y})...")
            mover_rapido(pag, x, y)
            pag.click()
            if self._confirmar(antes):
                self.log.emit("✅ Click confirmado: la pantalla reaccionó.")
                self._notas.append(f"click en ({x}, {y}) confirmado")
                if intento > 1: self._aprender()
                return
            self.log.emit("⚠ La pantalla no reaccionó al click.")
            if intento == 1:
                self.log.emit("👁 Espero a que la pantalla termine de cargar y lo reintento...")
                ojos.esperar_estable(timeout=10.0, minimo=0.5)
        self._notas.append(f"click en ({x}, {y}) SIN efecto visible")

    def _desplazar(self, dir_, antes, muescas=5):
        """Scroll fiable: rueda del mouse en muescas pequeñas sobre el centro de la pantalla; si la pantalla no
        reacciona, recurre al teclado (RePág/AvPág). Devuelve la captura posterior. dir_: -1 abajo, 1 arriba."""
        pag = self._pag
        sw, sh = pag.size()
        mover_rapido(pag, sw // 2, sh // 2)
        time.sleep(0.05)
        for _ in range(max(1, muescas)):
            if getattr(self, "cancelado", False): return None
            pag.scroll(dir_ * 120)
            time.sleep(0.015)
        ojos.esperar_estable(timeout=6.0, minimo=0.2, estables=2)
        img = ojos.capturar()
        if img is not None and not ojos.cambio(antes, img, umbral=0.004):
            self.log.emit("⌨️ La rueda no movió la página; pruebo con el teclado...")
            pag.press("pagedown" if dir_ < 0 else "pageup")
            ojos.esperar_estable(timeout=6.0, minimo=0.2, estables=2)
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
        ctx = mapa_visual(f"{self._dominio} {desc} {self.objetivo}")
        img = ojos.capturar()
        dir_, invertido, vista, espera_inicial, fallos = direccion, False, False, not self._ya_espero, 0

        for _ in range(self.MAX_PASOS):
            if getattr(self, "cancelado", False): return None, None
            if img is None:
                log("⚠ No pude capturar la pantalla.")
                return None, None

            if not vista:
                log(f"👁 Buscando «{desc}» en pantalla...")
                r = self.cerebro.localizar_elemento(img, desc, ctx)
                if r is None:
                    fallos += 1
                    if fallos >= 3:
                        log("⚠ El módulo de visión no responde.")
                        return None, None
                    time.sleep(1.5)
                    img = ojos.capturar()
                    continue

                if r.get("entorno") and r["entorno"] != self._ultimo_entorno:
                    self._ultimo_entorno = r["entorno"]
                    log(f"🧭 Entorno detectado: {r['entorno']}")
                if r["encontrado"] and (not r["cargando"] or self._esperas_ult >= 2):
                    return img, r

                if not r["encontrado"] and r["obstaculo"] and self._obstaculos < 2:
                    self._obstaculos += 1
                    log(f"🚧 Obstáculo detectado: {r['obstaculo']}. Lo despejo.")
                    mover_rapido(pag, int(r["ox"] * sw), int(r["oy"] * sh))
                    pag.click()
                    time.sleep(0.4)
                    img = ojos.capturar()
                    continue

                if (r["cargando"] and self._esperas_ult < 3) or espera_inicial:
                    if r["cargando"]: self._esperas_ult += 1
                    espera_inicial = False
                    log("⏳ La página sigue cargando; espero y vuelvo a mirar..." if r["cargando"]
                        else "⏳ Aún no lo veo; dejo que la pantalla se asiente y vuelvo a mirar...")
                    ojos.esperar_estable(timeout=10.0, minimo=0.5, estables=2)
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
        self._pulsar(desc, "left")

    def _a_pulsar_der(self, desc):
        """CLICK DERECHO sobre un elemento localizado con visión: abre su menú contextual y lo deja abierto."""
        self._pulsar(desc, "right")

    def _pulsar(self, desc, boton="left"):
        pag = self._requiere_pag()
        if not pag: return
        if self.cerebro is None:
            self.log.emit("⚠ Módulo de visión no disponible.")
            return
        desc = desc.strip()
        der = boton == "right"
        medio = boton == "middle"
        verbo = "click derecho" if der else ("click central" if medio else "click")
        umbral = UMBRAL_CLICK_DER if (der or medio) else None
        intentos = 2 if der else (1 if medio else self.MAX_INTENTOS)   # un click central NUNCA se repite: cerraría otra pestaña
        self._vio_pantalla = True
        sw, sh = pag.size()

        for intento in range(1, intentos + 1):
            if getattr(self, "cancelado", False): return
            if der and intento > 1:
                pag.press("esc")  # cierra un menú que no se llegó a detectar: así no se alterna abrir/cerrar
                time.sleep(0.3)
            img, r = self._localizar_scrolleando(desc)
            if r is None:
                break
            x, y = int(r["x"] * sw), int(r["y"] * sh)
            self.log.emit(f"🖱️ Elemento localizado en ({x}, {y}). Ejecutando {verbo}...")
            mover_rapido(pag, x, y)
            pag.click(button=boton)
            if self._confirmar(img, umbral):
                if der:
                    self.log.emit("✅ Click derecho confirmado: se abrió el menú contextual.")
                    self._notas.append(f"click derecho sobre «{desc}» en ({x}, {y}) con éxito (intento {intento}); el menú contextual quedó abierto")
                elif medio:
                    self.log.emit("✅ Click central confirmado: la pestaña se cerró.")
                    self._notas.append(f"cerré «{desc}» con click central en ({x}, {y}) (la pantalla reaccionó)")
                else:
                    self.log.emit("✅ Click confirmado: la pantalla reaccionó.")
                    self._notas.append(f"pulsé «{desc}» en ({x}, {y}) con éxito (intento {intento})")
                if intento > 1 or self._esperas_ult: self._aprender()
                return
            self.log.emit("⚠ La pantalla no reaccionó. Reevalúo y reintento...")

        self.log.emit(f"❌ No logré hacer {verbo} sobre «{desc}».")
        self._notas.append(f"NO logré hacer {verbo} sobre «{desc}»")

    def _a_click_der(self, coords):
        """Click derecho en coordenadas exactas, o donde ya está el cursor si no se dieron."""
        pag = self._requiere_pag()
        if not pag: return
        self._esperar_pantalla()
        self._vio_pantalla = True
        x, y = coords
        antes = ojos.capturar()
        if x is not None and y is not None:
            x, y = int(x), int(y)
            self.log.emit(f"🖱️ Click derecho en ({x}, {y})...")
            mover_rapido(pag, x, y)
            donde = f"({x}, {y})"
        else:
            self.log.emit("🖱️ Click derecho en la posición actual del cursor...")
            donde = "la posición actual del cursor"
        pag.click(button="right")
        if self._confirmar(antes, UMBRAL_CLICK_DER):
            self.log.emit("✅ Click derecho confirmado: la pantalla reaccionó.")
            self._notas.append(f"click derecho en {donde} confirmado; el menú contextual quedó abierto")
        else:
            self.log.emit("⚠ La pantalla no reaccionó al click derecho.")
            self._notas.append(f"click derecho en {donde} SIN efecto visible")

    def _a_scroll(self, cantidad):
        pag = self._requiere_pag()
        if not pag: return
        self._esperar_pantalla()
        cant = int(cantidad)
        if cant == 0:
            return
        self.log.emit(f"🖱️ Haciendo scroll hacia {'arriba' if cant > 0 else 'abajo'} ({abs(cant)})...")
        sw, sh = pag.size()
        mover_rapido(pag, sw // 2, sh // 2)
        time.sleep(0.05)
        antes = ojos.capturar()
        direccion = 1 if cant > 0 else -1
        for _ in range(max(1, round(abs(cant) / 120))):
            if getattr(self, "cancelado", False): return
            pag.scroll(direccion * 120)
            time.sleep(0.015)
        # Espera a que acabe el scroll suave y a que carguen las miniaturas/comentarios nuevos (YouTube)
        ojos.esperar_estable(timeout=3.0, minimo=0.25, estables=2)
        movio = antes is None or ojos.cambio(antes, ojos.capturar(), umbral=0.004)
        if not movio:
            self.log.emit("⌨️ La rueda no movió la página; pruebo con el teclado...")
            for _ in range(max(1, round(abs(cant) / 600))):
                if getattr(self, "cancelado", False): return
                pag.press("pageup" if cant > 0 else "pagedown")
                time.sleep(0.2)
            ojos.esperar_estable(timeout=3.0, minimo=0.25, estables=2)
            movio = ojos.cambio(antes, ojos.capturar(), umbral=0.004)
        if movio:
            self._notas.append(f"scroll {cantidad} (la página se movió)")
        else:
            self.log.emit("⚠ La página no se movió.")
            self._notas.append(f"scroll {cantidad} SIN efecto visible (¿pantalla completa, un Short o un menú abierto?)")
        time.sleep(0.1)

    def _a_circulos(self, _arg=""):
        pag = self._requiere_pag()
        if not pag: return
        self._esperar_pantalla()
        self.log.emit("🖱️ Ejecutando maniobra de calibración (círculos)...")
        cx, cy = pag.position()
        r = 150
        for i in range(36):
            if getattr(self, "cancelado", False): return
            ang = math.radians(i * 10)
            pag.moveTo(cx + r * math.cos(ang), cy + r * math.sin(ang), duration=0.015)
        pag.moveTo(cx, cy, duration=0.2)
        self._notas.append("círculos con el mouse")

    # ---------- movimiento humano: arrastrar, descargar imágenes y dibujar ----------
    def _mover_humano(self, x0, y0, x1, y1, paso_s=0.003):
        """Mueve el cursor con curva de Bézier, velocidad variable y micro-temblor (el botón queda como esté)."""
        pag = self._pag
        dist = math.hypot(x1 - x0, y1 - y0)
        n = max(8, min(45, int(dist / 20)))
        nx, ny = -(y1 - y0) / (dist or 1), (x1 - x0) / (dist or 1)
        arco = random.uniform(-0.12, 0.12) * dist
        cx, cy = (x0 + x1) / 2 + nx * arco, (y0 + y1) / 2 + ny * arco
        for i in range(1, n + 1):
            if getattr(self, "cancelado", False): return
            t = i / n
            t = t * t * (3 - 2 * t)
            x = (1 - t) ** 2 * x0 + 2 * (1 - t) * t * cx + t ** 2 * x1
            y = (1 - t) ** 2 * y0 + 2 * (1 - t) * t * cy + t ** 2 * y1
            if i < n:
                x += random.uniform(-1.2, 1.2); y += random.uniform(-1.2, 1.2)
            pag.moveTo(x, y, _pause=False)
            time.sleep(paso_s * random.uniform(0.7, 1.4))

    def _arrastrar_xy(self, x0, y0, x1, y1):
        pag = self._pag
        px, py = pag.position()
        self._mover_humano(px, py, x0, y0)
        time.sleep(random.uniform(0.06, 0.12))
        pag.mouseDown(_pause=False)
        try:
            time.sleep(random.uniform(0.06, 0.12))
            self._mover_humano(x0, y0, x1, y1, paso_s=0.006)
            time.sleep(random.uniform(0.08, 0.16))
        finally:
            pag.mouseUp(_pause=False)

    def _a_arrastrar(self, arg):
        """[ARRASTRAR: origen -> destino]: localiza ambos con visión, mantiene el click y mueve el mouse como una persona."""
        pag = self._requiere_pag()
        if not pag: return
        if self.cerebro is None:
            self.log.emit("⚠ Módulo de visión no disponible."); return
        m = re.split(r"\s*(?:->|→|=>)\s*", arg, maxsplit=1)
        if len(m) != 2 or not m[0].strip() or not m[1].strip():
            self.log.emit("⚠ ARRASTRAR necesita «origen -> destino»."); self._notas.append("ARRASTRAR mal formado"); return
        origen, destino = m[0].strip(), m[1].strip()
        self._vio_pantalla = True
        sw, sh = pag.size()
        _, r0 = self._localizar_scrolleando(origen, scroll=False)
        if r0 is None:
            self._notas.append(f"ARRASTRAR: no encontré el origen «{origen}»"); return
        _, r1 = self._localizar_scrolleando(destino, scroll=False)
        if r1 is None:
            self._notas.append(f"ARRASTRAR: no encontré el destino «{destino}»"); return
        x0, y0, x1, y1 = int(r0["x"] * sw), int(r0["y"] * sh), int(r1["x"] * sw), int(r1["y"] * sh)
        antes = ojos.capturar()
        self.log.emit(f"🖱️ Arrastrando «{origen}» ({x0}, {y0}) → «{destino}» ({x1}, {y1})...")
        self._arrastrar_xy(x0, y0, x1, y1)
        if self._confirmar(antes):
            self.log.emit("✅ Arrastre confirmado: la pantalla reaccionó.")
            self._notas.append(f"arrastré «{origen}» a «{destino}» (la pantalla cambió)")
        else:
            self.log.emit("⚠ La pantalla no reaccionó al arrastre.")
            self._notas.append(f"arrastre «{origen}» -> «{destino}» SIN efecto visible")

    def _a_descargar(self, desc):
        """[DESCARGAR: imagen]: click derecho > Guardar imagen como... > Enter (carpeta propuesta)."""
        pag = self._requiere_pag()
        if not pag: return
        if self.cerebro is None:
            self.log.emit("⚠ Módulo de visión no disponible."); return
        desc = desc.strip()
        n0 = len(self._notas)
        self._pulsar(desc, "right")
        if not any("menú contextual quedó abierto" in n for n in self._notas[n0:]):
            self._notas.append(f"DESCARGAR: no pude abrir el menú de «{desc}»"); return
        time.sleep(0.3)
        self._pulsar("opción Guardar imagen como (Save image as) del menú contextual", "left")
        self.log.emit("👁 Esperando el diálogo de guardado...")
        ojos.esperar_estable(timeout=6.0, minimo=0.4, requerir_cambio=True, espera_sin_cambio=1.5)
        antes = ojos.capturar()
        pag.press("enter")
        time.sleep(0.4)
        if ojos.cambio(antes, ojos.capturar(), 0.004):
            self.log.emit("✅ Imagen guardada (el diálogo se cerró).")
            self._notas.append(f"descargué la imagen «{desc}» con Guardar imagen como (diálogo aceptado)")
        else:
            self.log.emit("⚠ No vi que el diálogo se cerrara.")
            self._notas.append(f"DESCARGAR «{desc}»: no pude confirmar que se guardara")

    # ---------- dibujo ----------
    def _trazo(self, puntos, paso_s=0.003):
        """Dibuja una polilínea (píxeles) con el botón presionado."""
        pag = self._pag
        sw, sh = pag.size()
        puntos = [(min(max(int(x), 2), sw - 3), min(max(int(y), 2), sh - 3)) for x, y in puntos]
        if len(puntos) < 2: return
        px, py = pag.position()
        self._mover_humano(px, py, *puntos[0])
        pag.mouseDown(_pause=False)
        try:
            time.sleep(0.05)
            for (xa, ya), (xb, yb) in zip(puntos, puntos[1:]):
                if getattr(self, "cancelado", False): break
                n = max(2, int(math.hypot(xb - xa, yb - ya) / 6))
                for i in range(1, n + 1):
                    t = i / n
                    pag.moveTo(xa + (xb - xa) * t + random.uniform(-.5, .5), ya + (yb - ya) * t + random.uniform(-.5, .5), _pause=False)
                    time.sleep(paso_s)
        finally:
            pag.mouseUp(_pause=False)
        time.sleep(0.08)

    @staticmethod
    def _figura(nombre, cx, cy, r):
        """Lista de trazos (listas de puntos) para una figura sencilla centrada en (cx, cy); None si no hay plantilla."""
        def arco(a0, a1, rr=None, k=40, ox=0, oy=0):
            rr = r if rr is None else rr
            return [(cx + ox + rr * math.cos(a0 + (a1 - a0) * i / k), cy + oy + rr * math.sin(a0 + (a1 - a0) * i / k)) for i in range(k + 1)]
        def c(a, rr=None):
            rr = r if rr is None else rr
            return (cx + rr * math.cos(a), cy + rr * math.sin(a))
        n = nombre.lower()
        full = 2 * math.pi
        if any(k in n for k in ("circulo", "círculo", "redondo")): return [arco(0, full, k=60)]
        if any(k in n for k in ("cuadrado", "caja")): return [[(cx - r, cy - r), (cx + r, cy - r), (cx + r, cy + r), (cx - r, cy + r), (cx - r, cy - r)]]
        if "rectangulo" in n or "rectángulo" in n: return [[(cx - r * 1.5, cy - r), (cx + r * 1.5, cy - r), (cx + r * 1.5, cy + r), (cx - r * 1.5, cy + r), (cx - r * 1.5, cy - r)]]
        if "triangulo" in n or "triángulo" in n: return [[(cx, cy - r), (cx + r, cy + r * .8), (cx - r, cy + r * .8), (cx, cy - r)]]
        if "estrella" in n: return [[c(-math.pi / 2 + i * 4 * math.pi / 5) for i in range(6)]]
        if "corazon" in n or "corazón" in n:
            return [[(cx + r * math.sin(t) ** 3, cy - r * (13 * math.cos(t) - 5 * math.cos(2 * t) - 2 * math.cos(3 * t) - math.cos(4 * t)) / 16)
                     for t in [i * full / 70 for i in range(71)]]]
        if "espiral" in n: return [[(cx + r * (a / 12) * math.cos(a), cy + r * (a / 12) * math.sin(a)) for a in [i * 0.2 for i in range(61)]]]
        if "flecha" in n: return [[(cx - r, cy), (cx + r, cy)], [(cx + r * .5, cy - r * .5), (cx + r, cy), (cx + r * .5, cy + r * .5)]]
        if "cruz" in n: return [[(cx - r, cy), (cx + r, cy)], [(cx, cy - r), (cx, cy + r)]]
        if "linea" in n or "línea" in n: return [[(cx - r, cy), (cx + r, cy)]]
        if "onda" in n: return [[(cx - r * 1.5 + i * r * 3 / 60, cy + r * .4 * math.sin(i * math.pi / 7.5)) for i in range(61)]]
        if "carita" in n or "cara" in n:
            return [arco(0, full, k=60), arco(0, full, r * .1, 14, -r * .35, -r * .3), arco(0, full, r * .1, 14, r * .35, -r * .3), arco(.2 * math.pi, .8 * math.pi, r * .55, 20)]
        if "sol" in n:
            t = [arco(0, full, r * .5, 40)]
            for i in range(8):
                a = i * math.pi / 4
                t.append([c(a, r * .7), c(a, r * 1.1)])
            return t
        if "casa" in n:
            return [[(cx - r, cy + r), (cx - r, cy), (cx + r, cy), (cx + r, cy + r), (cx - r, cy + r)],
                    [(cx - r * 1.2, cy), (cx, cy - r * .9), (cx + r * 1.2, cy)],
                    [(cx - r * .2, cy + r), (cx - r * .2, cy + r * .45), (cx + r * .25, cy + r * .45), (cx + r * .25, cy + r)]]
        if "flor" in n:
            t = [arco(0, full, r * .2, 20, 0, -r * .3)]
            for i in range(6):
                a = i * math.pi / 3
                t.append(arco(0, full, r * .28, 20, r * .5 * math.cos(a), -r * .3 + r * .5 * math.sin(a)))
            t.append([(cx, cy + r * .25), (cx, cy + r)])
            return t
        if "arbol" in n or "árbol" in n:
            return [[(cx - r * .12, cy + r), (cx - r * .12, cy + r * .2), (cx + r * .12, cy + r * .2), (cx + r * .12, cy + r)],
                    arco(0, full, r * .7, 50, 0, -r * .3)]
        if "gato" in n:
            return [arco(0, full, r * .8, 50),
                    [(cx - r * .7, cy - r * .35), (cx - r * .75, cy - r * 1.05), (cx - r * .2, cy - r * .72)],
                    [(cx + r * .7, cy - r * .35), (cx + r * .75, cy - r * 1.05), (cx + r * .2, cy - r * .72)],
                    arco(0, full, r * .07, 10, -r * .3, -r * .1), arco(0, full, r * .07, 10, r * .3, -r * .1),
                    [(cx - r * .08, cy + r * .1), (cx + r * .08, cy + r * .1), (cx, cy + r * .2), (cx - r * .08, cy + r * .1)],
                    [(cx - r * .9, cy + r * .1), (cx - r * .3, cy + r * .2)], [(cx + r * .9, cy + r * .1), (cx + r * .3, cy + r * .2)]]
        return None

    def _a_dibujar(self, arg):
        """[DIBUJAR: figura] o [DIBUJAR: figura @ x,y ~ tamaño]: dibuja con el mouse sobre un lienzo ya abierto."""
        pag = self._requiere_pag()
        if not pag: return
        self._esperar_pantalla()
        sw, sh = pag.size()
        m = re.match(r"^(?P<f>[^@~]+?)\s*(?:@\s*(?P<x>\d+)\s*,\s*(?P<y>\d+))?\s*(?:~\s*(?P<r>\d+))?\s*$", arg.strip())
        if not m:
            self.log.emit("⚠ DIBUJAR mal formado."); self._notas.append("DIBUJAR mal formado"); return
        nombre = m.group("f").strip()
        cx = int(m.group("x")) if m.group("x") else sw // 2
        cy = int(m.group("y")) if m.group("y") else int(sh * 0.55)
        r = int(m.group("r")) if m.group("r") else 150
        trazos = self._figura(nombre, cx, cy, r)
        if not trazos:
            self.log.emit(f"⚠ No tengo plantilla para «{nombre}».")
            self._notas.append(f"DIBUJAR «{nombre}»: sin plantilla (usa [TRAZO: x,y x,y ...] para dibujarlo a mano)"); return
        self._vio_pantalla = True
        antes = ojos.capturar()
        self.log.emit(f"✏️ Dibujando «{nombre}» en ({cx}, {cy})...")
        for t in trazos:
            if getattr(self, "cancelado", False): break
            self._trazo(t)
            time.sleep(0.1)
        if self._confirmar(antes, 0.002):
            self.log.emit("✅ Dibujo hecho: el lienzo cambió.")
            self._notas.append(f"dibujé «{nombre}» en ({cx}, {cy}) tamaño {r}; el lienzo cambió")
        else:
            self.log.emit("⚠ El lienzo no cambió; ¿hay un pincel activo?")
            self._notas.append(f"dibujo «{nombre}» SIN efecto visible (¿no hay lienzo o pincel activo?)")

    def _a_trazo(self, arg):
        """[TRAZO: x,y x,y ...]: línea continua por esos puntos (píxeles) con el click presionado."""
        pag = self._requiere_pag()
        if not pag: return
        self._esperar_pantalla()
        pts = [(int(a), int(b)) for a, b in re.findall(r"(-?\d+)\s*,\s*(-?\d+)", arg)]
        if len(pts) < 2:
            self.log.emit("⚠ TRAZO necesita al menos 2 puntos."); self._notas.append("TRAZO sin puntos suficientes"); return
        self._vio_pantalla = True
        self.log.emit(f"✏️ Trazando línea de {len(pts)} puntos...")
        self._trazo(pts)
        self._notas.append(f"trazo de {len(pts)} puntos dibujado")

    # ---------- juegos ----------
    def _a_jugar(self, arg):
        """[JUGAR: juego u objetivo]: Geometry Dash tiene piloto de reflejos propio; el resto usa el bucle de visión."""
        from gd_conocimiento import es_gd
        pag = self._requiere_pag()
        if not pag: return
        if self.cerebro is None:
            self.log.emit("⚠ Módulo de visión no disponible."); return
        self._esperar_pantalla()
        self._ver(ojos.capturar(), f"Mirando tu pantalla para jugar: {arg}")
        if es_gd(arg): self._jugar_gd(arg)
        else: self._a_jugar_generico(arg)

    # ---------- Geometry Dash: menús con visión + reflejos locales + aprendizaje ----------
    def _jugar_gd(self, juego):
        from gd_jugador import GDJugador, FPS
        from gd_conocimiento import nivel_en
        pag, log = self._pag, self.log.emit
        sw, sh = pag.size()
        nivel = nivel_en(juego)
        if sys.platform == "win32": traer_al_frente("Geometry Dash")
        jug = GDJugador()
        self._vio_pantalla = False

        # Fase 1: navegar los menús con visión hasta que el nivel esté en marcha (el cubo visible)
        previa, bitacora, hecho = ojos.capturar(), [], 0
        objetivo_menu = ("Geometry Dash: SOLO navega los menús (Play, elegir el nivel "
                         f"{'«' + nivel + '»' if nivel != 'generico' else 'que pidió Niko, por defecto Stereo Madness'}, Play del nivel) "
                         "hasta que el nivel esté EMPEZANDO con el cubo visible. En cuanto el cubo esté dentro del nivel pon fin=true y resultado='nivel iniciado'. "
                         "No pulses nada dentro del nivel.")
        for n in range(1, 13):
            if self._parar_pedido(): self._notas.append("GD: Niko me detuvo en los menús"); return
            img = previa if previa is not None else ojos.capturar()
            if img is not None and jug.hay_jugador(np.asarray(img.convert("RGB"))):
                hecho += 1
                if hecho >= 2: break
            else:
                hecho = 0
            self._ver(img, f"[menú {n}] buscando cómo llegar al nivel...")
            d = self.cerebro.decidir_jugada(img, objetivo_menu, bitacora[-6:], [])
            if d is None: time.sleep(1.0); previa = ojos.capturar(); continue
            log(f"🎮 [menú {n}] {d['razon']}")
            if d["fin"] and "iniciado" in d["resultado"].lower():
                time.sleep(1.5); break
            hechas = [self._jugada(a, sw, sh) for a in d["acciones"]]
            bitacora.append(f"{n}: {d['razon']} -> {', '.join(hechas)}")
            time.sleep(1.0)
            previa = ojos.capturar()

        # Fase 2: reflejos rápidos con aprendizaje
        log(f"⚡ Paso al piloto de reflejos (sin LLM, visión en vivo a {FPS} FPS).")
        res = jug.jugar(nivel, log, self._parar_pedido, vista=lambda img, txt="": self._ver(img, txt, min_dt=0.0),
                        felicidad=getattr(self.cerebro, "felicidad", None), hablar=hablar)
        tiempos = res["tiempos"]
        resumen = (f"{res['intentos']} intentos, mejor récord {res['mejor']:.1f}s (~{res['pct']:.0f}% del nivel)"
                   + (f", último {tiempos[-1]:.1f}s" if tiempos else "") + f"; fin: {res['motivo']}")
        log(f"🎮 Geometry Dash: {resumen}")
        fel = getattr(self.cerebro, "felicidad", None)
        if fel is not None:
            log(f"💖 Felicidad {fel.resumen()} · +{res['ganada']:.1f} ganados en esta sesión de juego")
            fel.guardar()
        completado = False
        if "no volvió a aparecer" in res["motivo"]:
            time.sleep(0.8)
            v = self.cerebro.verificar_resultado(ojos.capturar(), "¿La pantalla muestra el aviso de nivel completado (Level Complete)?")
            if v:
                completado = v["cumplido"]
                log(f"{'🏆' if completado else '⚠'} {v['observacion']}")
                if completado:
                    if tiempos and tiempos[-1] > 10:
                        GDJugador.registrar_completado(nivel, tiempos[-1])   # duración real del nivel: calibra el % de próximas partidas
                    if fel is not None:
                        gan = fel.recompensar(15, f"completar {nivel} en Geometry Dash")
                        fel.guardar()
                        log(f"🎉 ¡Nivel completado! +{gan:.0f} de felicidad → {fel.resumen()}")
                        try: hablar("¡Lo logramos! ¡Nivel completado!")
                        except Exception: pass
        self._notas.append(f"jugué Geometry Dash ({nivel}): {resumen}" + ("; ¡NIVEL COMPLETADO!" if completado else "")
                            + (f"; felicidad {fel.resumen()}" if fel is not None else ""))
        try:
            hist = [f"intento {i + 1}: {t:.1f}s" for i, t in enumerate(tiempos)] or ["sin intentos medidos"]
            if self.cerebro.reflexionar_juego(f"Geometry Dash {nivel}", hist, resumen):
                log("🧠 Lección de Geometry Dash guardada en mi memoria.")
        except Exception as e:
            print(f"[Lecciones] {e}")

    _TECLAS_PROHIBIDAS = frozenset({"win", "winleft", "winright", "alt", "altleft", "altright", "ctrl", "ctrlleft", "ctrlright",
                                    "sleep", "apps", "printscreen", "fn", "f4", "f8"})

    def _parar_pedido(self):
        """F8 pulsada = Niko quiere que SAGE deje de jugar (solo Windows), o interrupción desde la interfaz."""
        if self.cancelado: return True
        if sys.platform != "win32": return False
        try:
            import ctypes
            return bool(ctypes.windll.user32.GetAsyncKeyState(0x77) & 0x8000)
        except Exception:
            return False

    def _jugada(self, a, sw, sh):
        """Ejecuta una acción del juego; devuelve un resumen corto."""
        pag = self._pag
        t = str(a.get("t", "")).lower()
        def pt(v):
            return int(min(max(float(v[1]), 0), 1000) / 1000 * sw), int(min(max(float(v[0]), 0), 1000) / 1000 * sh)
        try:
            if t == "tecla":
                k = str(a.get("v", "")).lower().strip()
                if k in self._TECLAS_PROHIBIDAS or k not in pag.KEYBOARD_KEYS: return f"tecla «{k}» no permitida"
                mant = min(max(float(a.get("mant", 0.05) or 0.05), 0.02), 3.0)
                pag.keyDown(k, _pause=False)
                time.sleep(mant)
                pag.keyUp(k, _pause=False)
                return f"tecla {k} {mant:.2f}s"
            if t == "click":
                x, y = pt(a["punto"])
                pag.moveTo(x, y, duration=0.12, tween=pag.easeOutQuad)
                pag.click()
                return f"click ({x}, {y})"
            if t == "arrastrar":
                x0, y0 = pt(a["punto"]); x1, y1 = pt(a["punto2"])
                self._arrastrar_xy(x0, y0, x1, y1)
                return f"arrastre ({x0}, {y0})→({x1}, {y1})"
            if t == "esperar":
                s = min(max(float(a.get("s", 0.5) or 0.5), 0.05), 3.0)
                time.sleep(s)
                return f"espera {s:.1f}s"
        except Exception as e:
            return f"{t} falló ({e})"
        return f"acción «{t}» desconocida"

    def _a_jugar_generico(self, arg):
        """Juego cualquiera: bucle mirar → decidir → actuar → comprobar, hasta que termine la partida."""
        pag = self._requiere_pag()
        if not pag: return
        if self.cerebro is None:
            self.log.emit("⚠ Módulo de visión no disponible."); return
        juego = arg.strip() or "el juego que se ve en pantalla"
        self._esperar_pantalla()
        self._vio_pantalla = False   # la verificación final genérica no aplica a una partida
        sw, sh = pag.size()
        try: turnos = max(1, int(os.getenv("SAGE_JUEGO_TURNOS", "40")))
        except ValueError: turnos = 40
        lecciones = self.cerebro.lecciones_para(f"juego {juego}")
        if lecciones: self.log.emit(f"🧠 Aplico {len(lecciones)} lección(es) de partidas anteriores.")
        self.log.emit(f"🎮 A jugar: {juego} (F8 para parar).")
        bitacora, resultado, fallos, quietos = [], "", 0, 0
        previa = ojos.capturar()
        for n in range(1, turnos + 1):
            if self._parar_pedido():
                resultado = "Niko me detuvo"; break
            img = previa if previa is not None else ojos.capturar()
            self._ver(img, f"[{n}] pensando la jugada...")
            d = self.cerebro.decidir_jugada(img, juego, bitacora[-8:], lecciones)
            if d is None:
                fallos += 1
                if fallos >= 3:
                    resultado = "la visión falló 3 veces seguidas"; break
                time.sleep(1.0); previa = ojos.capturar(); continue
            fallos = 0
            self.log.emit(f"🎮 [{n}/{turnos}] {d['razon']}")
            self._ver(img, f"[{n}] {d['razon']}")
            hechas = [self._jugada(a, sw, sh) for a in d["acciones"]]
            if d["fin"]:
                resultado = d["resultado"] or "partida terminada"; bitacora.append(f"{n}: {d['razon']} -> FIN: {resultado}"); break
            time.sleep(0.25)
            ahora = ojos.capturar()
            self._ver(ahora, f"[{n}] resultado de: {', '.join(hechas)[:90]}")
            movio = ojos.cambio(img, ahora, 0.003)
            quietos = 0 if movio else quietos + 1
            bitacora.append(f"{n}: {d['razon']} -> {', '.join(hechas) or 'sin acciones'}" + ("" if movio else " (la pantalla NO cambió)"))
            if quietos >= 5:
                resultado = "la pantalla no reaccionaba a mis acciones (¿el juego no tiene el foco?)"; break
            previa = ahora
        else:
            resultado = f"se acabaron los {turnos} turnos sin terminar la partida"
        self.log.emit(f"🎮 Fin de la sesión: {resultado}")
        self._notas.append(f"jugué «{juego}» {len(bitacora)} turnos; resultado: {resultado}")
        try:
            if bitacora and self.cerebro.reflexionar_juego(juego, bitacora, resultado):
                self.log.emit("🧠 Lección de la partida guardada en mi memoria.")
        except Exception as e:
            print(f"[Lecciones] {e}")

    def _a_cerrar_pestana(self, arg):
        """[CERRAR_PESTANA: youtube]: cierra una pestaña concreta del navegador SIN tocar mouse, teclado ni foco."""
        todas, palabras = parsear_pestana(arg)
        if not palabras:
            self.log.emit("⚠ CERRAR_PESTANA necesita decir cuál (título o sitio).")
            self._notas.append("CERRAR_PESTANA mal formado")
            return
        desc = " ".join(palabras)
        self.log.emit(f"🗂️ Cerrando {'todas las pestañas' if todas else 'la pestaña'} «{desc}» en segundo plano...")
        cerradas, motivo, probar_vision = cerrar_pestanas_fondo(palabras, todas)
        if cerradas:
            self.log.emit("✅ Pestaña(s) cerrada(s): " + "; ".join(t[:50] for t in cerradas))
            self._notas.append(f"cerré {len(cerradas)} pestaña(s) de «{desc}» en segundo plano: " + "; ".join(t[:40] for t in cerradas))
            return
        if probar_vision and os.getenv("SAGE_PESTANAS_VISUAL", "1").strip() != "0" and self.cerebro is not None and self._requiere_pag():
            self._cerrar_pestana_visual(desc, motivo)
            return
        self.log.emit(f"❌ No pude cerrar «{desc}»: {motivo}")
        self._notas.append(f"NO logré cerrar la pestaña «{desc}»: {motivo}")

    def _cerrar_pestana_visual(self, desc, motivo):
        """Plan B: pone el navegador al frente, localiza la pestaña con visión y le hace click central; luego devuelve el foco."""
        import ctypes
        pag, tocar_hud = self._pag, not self._hud_oculto
        self.log.emit(f"🖱️ En segundo plano no pude ({motivo}). Pruebo con visión; usaré el mouse un instante.")
        previa = ctypes.windll.user32.GetForegroundWindow()
        if tocar_hud:
            self.hud.emit(False)
            time.sleep(0.2)
        try:
            if not traer_al_frente("Opera"):
                self.log.emit("❌ No encontré la ventana del navegador.")
                self._notas.append(f"NO logré cerrar la pestaña «{desc}»: no encontré la ventana de Opera")
                return
            time.sleep(0.4)
            ojos.esperar_estable(timeout=4.0, minimo=0.3)
            self._pulsar(f"pestaña «{desc}» en la barra de pestañas de Opera GX (arriba del todo, no el contenido de la página)", "middle")
        finally:
            if tocar_hud: self.hud.emit(True)
            try:
                if previa and ctypes.windll.user32.IsWindow(previa): ctypes.windll.user32.SetForegroundWindow(previa)
            except Exception:
                pass

    def _a_discord(self, arg):
        """[DISCORD: mutear|desmutear|ensordecer|desensordecer|alternar mute|alternar ensordecer|estado]: botones de Discord por UI Automation, sin cambiar la ventana activa."""
        from discord_voz import discord_voz_fondo
        self.log.emit(f"🎙️ Discord (segundo plano): {arg.strip()}")
        ok, msg = discord_voz_fondo(arg)
        self.log.emit(("✅ " if ok else "⚠ ") + msg)
        self._notas.append(f"Discord: {msg}" if ok else f"NO logré lo de Discord ({msg})")

    def _a_multimedia(self, arg):
        """[MULTIMEDIA: pausa|siguiente|anterior|detener|silenciar|subir N|bajar N]: teclas multimedia, sin cambiar de ventana."""
        clave, veces = interpretar_multimedia(arg)
        if clave is None:
            self.log.emit(f"⚠ MULTIMEDIA no entiende «{arg}».")
            self._notas.append(f"MULTIMEDIA «{arg}» no reconocido")
            return
        self.log.emit(f"🎵 Multimedia: {arg.strip()}")
        tecla_multimedia(clave, veces)
        self._notas.append(f"envié la tecla multimedia «{clave}»" + (f" x{veces}" if veces > 1 else ""))

    def _a_cerrar(self, app_name):
        """[CERRAR: programa]: cierre cortés (el programa puede preguntar si guardar); solo a la fuerza si Niko lo pidió."""
        nombre = RE_SEGURO.sub('', app_name.lower().replace(".exe", "")).strip()
        if not nombre: return
        forzar = bool(re.search(r"\b(fuerza|forzad\w*|a la fuerza|mata\w*|kill|no responde|congelad\w*|trabad\w*|colgad\w*)", vent.norm(self.objetivo)))
        self.log.emit(f"💀 Cerrando «{nombre}»" + (" a la fuerza..." if forzar else " con cortesía (puede preguntar si guardar)..."))
        ok, msg = vent.cerrar_programa(nombre, forzar)
        self.log.emit(("✅ " if ok else "⚠ ") + msg[:1].upper() + msg[1:])
        self._notas.append(msg if ok else f"NO logré cerrar {nombre}: {msg}")

    def _estado_ventana(self, modo, objetivo):
        ok, msg = vent.cambiar_estado(modo, objetivo)
        self.log.emit(("🪟 " if ok else "⚠ ") + msg[:1].upper() + msg[1:])
        self._notas.append(msg if ok else f"NO logré {modo} «{objetivo.strip() or 'la ventana activa'}»: {msg}")

    def _a_minimizar(self, arg):
        """[MINIMIZAR: programa]: lo manda a la barra de tareas (sin nombre = la ventana activa de Niko)."""
        self._estado_ventana("minimizar", arg)

    def _a_maximizar(self, arg):
        """[MAXIMIZAR: programa]: lo maximiza y lo trae al frente."""
        self._estado_ventana("maximizar", arg)

    def _a_ventana(self, arg):
        """[VENTANA: programa]: modo ventana (la saca de maximizada, minimizada o pantalla completa)."""
        self._estado_ventana("ventana", arg)

def powershell_csv(comando_ps):
    """Ejecuta PowerShell y devuelve su salida; si no hay resultados (código de salida 1) devuelve cadena vacía."""
    try:
        return subprocess.check_output(
            ["powershell", "-NoProfile", "-Command", comando_ps],
            text=True, stderr=subprocess.STDOUT,
            encoding='mbcs', errors='replace', creationflags=subprocess.CREATE_NO_WINDOW,
        ).strip()
    except subprocess.CalledProcessError:
        return ""


# ---------- Widgets ----------
class Fondo(QWidget):
    """Fondo limpio estilo HUD: degradado profundo, rejilla finísima, viñeta y marco con esquinas del color del estado."""
    def __init__(self):
        super().__init__()
        self.estado = "idle"
        self.color = QColor(COLORES["idle"])
        self.impulso = 0.0
        self._tam = None
        self._base = None

    def set_estado(self, estado):
        if estado != self.estado:
            self.impulso = 1.0
        self.estado = estado

    def tick(self, dt):
        self.impulso *= max(0.0, 1.0 - dt * 2.5)
        self.color = acercar(self.color, COLORES.get(self.estado, COLORES["idle"]), dt * 6)

    def _recalcular(self, w, h):
        self._tam = (w, h)
        pm = QPixmap(w, h)
        q = QPainter(pm)
        g = QLinearGradient(0, 0, 0, h)
        g.setColorAt(0.0, QColor(3, 6, 10))
        g.setColorAt(1.0, QColor(6, 15, 24))
        q.fillRect(pm.rect(), g)
        q.setPen(QPen(QColor(120, 200, 255, 9), 1))
        for x in range(0, w, 56): q.drawLine(x, 0, x, h)
        for y in range(0, h, 56): q.drawLine(0, y, w, y)
        rg = QRadialGradient(w / 2, h / 2, max(w, h) * 0.75)
        rg.setColorAt(0.55, QColor(0, 0, 0, 0))
        rg.setColorAt(1.0, QColor(0, 0, 0, 175))
        q.fillRect(pm.rect(), rg)
        q.setPen(QPen(QColor(150, 220, 255, 42), 1))   # regleta de marcas en los bordes laterales
        for n, y in enumerate(range(48, h - 48, 24)):
            largo = 22 if n % 5 == 0 else 12
            q.drawLine(8, y, 8 + largo, y)
            q.drawLine(w - 8, y, w - 8 - largo, y)
        q.end()
        self._base = pm

    def paintEvent(self, ev):
        p = QPainter(self)
        w, h = self.width(), self.height()
        if self._tam != (w, h):
            self._recalcular(w, h)
        p.drawPixmap(0, 0, self._base)
        c = self.color
        rg = QRadialGradient(w * 0.2, h * 0.5, h * 0.8)
        rg.setColorAt(0.0, con_alpha(c, 24 + 34 * self.impulso))
        rg.setColorAt(1.0, con_alpha(c, 0))
        p.fillRect(self.rect(), rg)

        p.setRenderHint(QPainter.Antialiasing)
        m, L = 12, 46
        p.setPen(QPen(con_alpha(c, 38 + 60 * self.impulso), 1))
        p.drawRect(m, m, w - 2 * m, h - 2 * m)
        p.setPen(QPen(con_alpha(c, 215), 2))
        for x, y, sx, sy in ((m, m, 1, 1), (w - m, m, -1, 1), (m, h - m, 1, -1), (w - m, h - m, -1, -1)):
            p.drawLine(QPointF(x, y), QPointF(x + sx * L, y))
            p.drawLine(QPointF(x, y), QPointF(x, y + sy * L))


def biselado(x, y, w, h, ch):
    """Placa con las esquinas superior derecha e inferior izquierda cortadas."""
    return QPolygonF([QPointF(x, y), QPointF(x + w - ch, y), QPointF(x + w, y + ch),
                      QPointF(x + w, y + h), QPointF(x + ch, y + h), QPointF(x, y + h - ch)])


class PlacaHUD(QWidget):
    """Panel biselado con pestaña de título; toma el color del estado de SAGE."""
    def __init__(self, titulo):
        super().__init__()
        self.titulo = titulo
        self.estado = "idle"
        self.color = QColor(COLORES["idle"])

    def set_estado(self, estado):
        self.estado = estado

    def tick(self, dt):
        self.color = acercar(self.color, COLORES.get(self.estado, COLORES["idle"]), dt * 7)

    def paintEvent(self, ev):
        p = QPainter(self)
        p.setRenderHint(QPainter.Antialiasing)
        w, h = self.width(), self.height()
        c = self.color
        p.setBrush(QColor(7, 12, 18, 205))
        p.setPen(QPen(con_alpha(c, 130), 1.5))
        p.drawPolygon(biselado(1, 1, w - 2, h - 2, 22))
        p.setPen(Qt.NoPen)
        p.setBrush(c)
        p.drawPolygon(QPolygonF([QPointF(1, 1), QPointF(5, 1), QPointF(5, h - 22), QPointF(1, h - 24)]))
        f = fuente(8, 4)
        p.setFont(f)
        tw = QFontMetrics(f).horizontalAdvance(self.titulo) + len(self.titulo) * 4 + 30
        p.setBrush(con_alpha(c, 38))
        p.drawPolygon(QPolygonF([QPointF(14, 1), QPointF(14 + tw, 1), QPointF(14 + tw - 12, 24), QPointF(14, 24)]))
        p.setPen(con_alpha(c, 240))
        p.drawText(QRectF(24, 1, tw, 23), Qt.AlignLeft | Qt.AlignVCenter, self.titulo)
        p.setPen(QPen(con_alpha(c, 70), 1))
        p.drawLine(QPointF(14 + tw + 6, 12), QPointF(w - 40, 12))


class TelemetriaHUD(QWidget):
    """Lectura de datos reales de SAGE (escucha, voz, ánimo, núcleo) en filas finas."""
    def __init__(self):
        super().__init__()
        self.datos = []
        self.color = QColor(COLORES["idle"])
        self.setFixedHeight(4 * 28 + 10)

    def poner(self, datos, color):
        self.datos, self.color = datos, color
        self.update()

    def paintEvent(self, ev):
        p = QPainter(self)
        p.setRenderHint(QPainter.Antialiasing)
        w = self.width()
        c = self.color
        fe, fv = fuente(7, 3), fuente(9, 1)
        for n, (etiqueta, valor, frac) in enumerate(self.datos):
            y = 4 + n * 28
            p.setFont(fe)
            p.setPen(con_alpha(c, 170))
            p.drawText(QRectF(0, y, w * 0.4, 20), Qt.AlignLeft | Qt.AlignVCenter, etiqueta)
            p.setFont(fv)
            p.setPen(QColor(255, 255, 255))
            p.drawText(QRectF(w * 0.35, y, w * 0.65, 20), Qt.AlignRight | Qt.AlignVCenter, valor)
            p.setPen(QPen(con_alpha(c, 55), 1))
            p.drawLine(QPointF(0, y + 24), QPointF(w, y + 24))
            if frac is not None:
                p.setPen(QPen(c, 2))
                p.drawLine(QPointF(0, y + 24), QPointF(w * max(0.0, min(1.0, frac)), y + 24))


class Cabecera(QWidget):
    def __init__(self, modelo=""):
        super().__init__()
        self.setFixedHeight(72)
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
        ancho = min(w * 0.42, 460)

        p.setBrush(QColor(7, 12, 18, 225))
        p.setPen(QPen(con_alpha(c, 170), 1.5))
        p.drawPolygon(biselado(2, 6, ancho, h - 12, 20))
        p.setPen(Qt.NoPen)
        p.setBrush(c)
        p.drawPolygon(QPolygonF([QPointF(2, 6), QPointF(8, 6), QPointF(8, h - 26), QPointF(2, h - 26 + 6)]))

        p.setFont(fuente(24, 10))
        p.setPen(con_alpha(c, 90))
        p.drawText(QRectF(31, 10, ancho, 38), Qt.AlignLeft | Qt.AlignVCenter, "SAGE")
        p.setPen(QColor(255, 255, 255))
        p.drawText(QRectF(28, 8, ancho, 38), Qt.AlignLeft | Qt.AlignVCenter, "SAGE")
        p.setFont(fuente(8, 4))
        p.setPen(con_alpha(c, 235))
        p.drawText(QRectF(30, 46, ancho, 16), Qt.AlignLeft | Qt.AlignVCenter, "EXTREME OS  //  COPILOTO GAME DEV")

        pw = 230
        x1, x2 = ancho + 34, w - pw - 34
        if x2 > x1:
            y = h / 2
            p.setPen(QPen(con_alpha(c, 80), 1))
            p.drawLine(QPointF(x1, y), QPointF(x2, y))
            for k in range(int((x2 - x1) // 26) + 1):
                xx = x1 + k * 26
                p.drawLine(QPointF(xx, y - (6 if k % 4 == 0 else 3)), QPointF(xx, y + (6 if k % 4 == 0 else 3)))
            p.setPen(Qt.NoPen)
            p.setBrush(con_alpha(c, 200))
            for xx in (x1, x2):
                p.drawPolygon(QPolygonF([QPointF(xx - 5, y), QPointF(xx, y - 5), QPointF(xx + 5, y), QPointF(xx, y + 5)]))

        p.setBrush(QColor(7, 12, 18, 225))
        p.setPen(QPen(con_alpha(c, 170), 1.5))
        p.drawPolygon(biselado(w - pw - 2, 6, pw, h - 12, 20))
        p.setFont(fuente(16, 2, True))
        p.setPen(QColor(255, 255, 255))
        p.drawText(QRectF(w - pw + 18, 8, pw - 40, 32), Qt.AlignRight | Qt.AlignVCenter, time.strftime("%H:%M:%S"))
        p.setFont(fuente(8, 3))
        p.setPen(con_alpha(c, 235))
        modelo = self.modelo if len(self.modelo) < 22 else self.modelo[:21] + "…"
        p.drawText(QRectF(w - pw + 18, 40, pw - 40, 18), Qt.AlignRight | Qt.AlignVCenter, f"NÚCLEO {modelo.upper()}")


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
        if activo and self.isDown(): col = QColor(COLORES["escuchando"])
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
        self.vigilando = False  # escucha por nombre activa: el espectro reacciona a la voz aunque esté en reposo
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
        if self.estado == "escuchando" or (self.vigilando and self.estado == "idle"): amp += self.nivel * 1.5
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
        self._clave = clave
        self.color = COLOR_AUTOR.get(clave, COLOR_AUTOR["sistema"])
        self.a_derecha = clave in ("niko", "nexus")
        self.esperando = esperando
        self._brillo = 0.0
        self._t = 0.0
        self._mostrada = False
        self.fila = None

        lay = QVBoxLayout(self)
        lay.setContentsMargins(28, 11, 28, 13)
        lay.setSpacing(5)

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
        ch = 12
        if self.a_derecha:   # tus mensajes: cortes arriba-izquierda y abajo-derecha
            poly = QPolygonF([QPointF(1 + ch, 1), QPointF(w - 1, 1), QPointF(w - 1, h - 1 - ch),
                              QPointF(w - 1 - ch, h - 1), QPointF(1, h - 1), QPointF(1, 1 + ch)])
        else:                # mensajes de SAGE / sistema: cortes arriba-derecha y abajo-izquierda
            poly = biselado(1, 1, w - 2, h - 2, ch)

        p.setBrush(lerp_color(QColor(7, 12, 18), c, 0.06))
        p.setPen(QPen(con_alpha(c, 140), 1.2))
        p.drawPolygon(poly)

        p.setPen(QPen(c, 3))
        if self.a_derecha:
            p.drawLine(QPointF(w - 1.5, 2), QPointF(w - 1.5, h - 2 - ch))
        else:
            p.drawLine(QPointF(1.5, 2 + ch), QPointF(1.5, h - 2))

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


def _recolorear_burbuja(self):
    """Aplica el color actual del autor (los mensajes ya escritos también cambian al tocar los ajustes)."""
    c = COLOR_AUTOR.get(self._clave, COLOR_AUTOR["sistema"])
    if c.rgb() != self.color.rgb():
        self.color = QColor(c)
        self.tag.setStyleSheet(f"color: {c.name()}; background: transparent;")
        self.update()


Burbuja.recolorear = _recolorear_burbuja


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
        raiz.setContentsMargins(22, 36, 14, 18)

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
        p.drawPolygon(QPolygonF([QPointF(0, 0), QPointF(5, 0), QPointF(5, h - ch + 5), QPointF(0, h - ch)]))
        f = fuente(8, 4)
        p.setFont(f)
        titulo = "COMUNICACIONES"
        tw = QFontMetrics(f).horizontalAdvance(titulo) + len(titulo) * 4 + 30
        p.setBrush(con_alpha(c, 38))
        p.drawPolygon(QPolygonF([QPointF(14, 0), QPointF(14 + tw, 0), QPointF(14 + tw - 12, 24), QPointF(14, 24)]))
        p.setPen(con_alpha(c, 240))
        p.drawText(QRectF(24, 0, tw, 24), Qt.AlignLeft | Qt.AlignVCenter, titulo)
        p.setPen(QPen(con_alpha(c, 70), 1))
        p.drawLine(QPointF(14 + tw + 6, 12), QPointF(w - ch - 14, 12))

        if self._vacio():
            pulso = 0.5 + 0.5 * math.sin(self.t * 2.2)
            p.setFont(fuente(54, 14))
            p.setPen(con_alpha(c, 18 + 14 * pulso))
            p.drawText(QRectF(0, h * 0.30, w, 90), Qt.AlignCenter, "SAGE")
            p.setFont(fuente(9, 5))
            p.setPen(con_alpha(c, 90 + 120 * pulso))
            p.drawText(QRectF(0, h * 0.30 + 92, w, 24), Qt.AlignCenter, "ESPERANDO COMANDO")


class VistaVivo(QWidget):
    """Ventanita flotante con lo que SAGE está viendo mientras juega (transparente al mouse y excluida de las capturas en Windows)."""
    def __init__(self):
        super().__init__(None, Qt.WindowType.Tool | Qt.WindowType.FramelessWindowHint
                         | Qt.WindowType.WindowStaysOnTopHint | Qt.WindowType.WindowDoesNotAcceptFocus)
        self.setAttribute(Qt.WidgetAttribute.WA_ShowWithoutActivating)
        self.setAttribute(Qt.WidgetAttribute.WA_TransparentForMouseEvents)
        self.resize(400, 292)
        self._img, self._texto = None, ""

    def poner(self, datos, w, h, texto):
        if w <= 0 or h <= 0:
            self.hide(); return
        self._img = QImage(datos, w, h, 3 * w, QImage.Format.Format_RGB888).copy()
        self._texto = texto
        if not self.isVisible():
            g = QApplication.primaryScreen().availableGeometry()
            self.move(g.right() - self.width() - 12, g.top() + 12)
            self.show()
            if sys.platform == "win32":
                try:  # WDA_EXCLUDEFROMCAPTURE: esta ventana no sale en las capturas de SAGE
                    import ctypes
                    ctypes.windll.user32.SetWindowDisplayAffinity(int(self.winId()), 0x11)
                except Exception:
                    pass
        self.update()

    def paintEvent(self, ev):
        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.Antialiasing)
        p.setPen(QPen(COLORES["sage"], 2)); p.setBrush(QColor(8, 10, 18, 235))
        p.drawRoundedRect(QRectF(1, 1, self.width() - 2, self.height() - 2), 8, 8)
        p.setBrush(COLORES["sage"]); p.setPen(Qt.PenStyle.NoPen); p.drawEllipse(QPointF(16, 15), 4, 4)
        p.setPen(QColor(235, 235, 245)); p.setFont(fuente(8, 2))
        p.drawText(QRectF(28, 6, 340, 18), Qt.AlignmentFlag.AlignVCenter, "SAGE VE EN VIVO")
        zona = QRectF(8, 28, self.width() - 16, 216)
        if self._img is not None:
            sc = self._img.scaled(int(zona.width()), int(zona.height()), Qt.AspectRatioMode.KeepAspectRatio, Qt.TransformationMode.FastTransformation)
            p.drawImage(int(zona.x() + (zona.width() - sc.width()) / 2), int(zona.y() + (zona.height() - sc.height()) / 2), sc)
        p.setPen(QColor(170, 230, 240)); p.setFont(fuente(8))
        p.drawText(QRectF(10, 248, self.width() - 20, 40), Qt.AlignmentFlag.AlignLeft | Qt.TextFlag.TextWordWrap, self._texto)


class IndicadorSage(QWidget):
    """Puntito casi invisible abajo a la derecha de la pantalla: avisa de que SAGE sigue activa mientras su ventana no se ve.
    Transparente al mouse, sin foco, excluido de las capturas de SAGE y con poca opacidad (se aviva un poco mientras trabaja).
    Ajustes en .env: SAGE_INDICADOR=0 (apagarlo), SAGE_INDICADOR_TAM=20 (px), SAGE_INDICADOR_OPACIDAD=0.4, SAGE_INDICADOR_SIEMPRE=1 (verlo siempre)."""

    def __init__(self):
        super().__init__(None, Qt.WindowType.Tool | Qt.WindowType.FramelessWindowHint
                         | Qt.WindowType.WindowStaysOnTopHint | Qt.WindowType.WindowDoesNotAcceptFocus)
        self.setAttribute(Qt.WidgetAttribute.WA_ShowWithoutActivating)
        self.setAttribute(Qt.WidgetAttribute.WA_TransparentForMouseEvents)
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground)
        try: self._tam = max(12, min(48, int(os.getenv("SAGE_INDICADOR_TAM", "20"))))
        except ValueError: self._tam = 20
        try: self._base = max(0.1, min(1.0, float(os.getenv("SAGE_INDICADOR_OPACIDAD", "0.4"))))
        except ValueError: self._base = 0.4
        self.setFixedSize(self._tam, self._tam)
        self.setWindowOpacity(self._base)
        self.estado, self.t, self._afinidad = "idle", 0.0, False
        self._timer = QTimer(self)
        self._timer.timeout.connect(self._tick)

    def set_estado(self, estado):
        self.estado = estado
        self.setWindowOpacity(self._base if estado == "idle" else min(1.0, self._base + 0.4))

    def mostrar(self):
        pantalla = QApplication.primaryScreen()
        if pantalla is None:
            return
        g = pantalla.availableGeometry()   # justo encima de la barra de tareas
        self.move(g.right() - self._tam - 14, g.bottom() - self._tam - 12)
        if not self.isVisible():
            self.show()
            self._timer.start(66)
            if sys.platform == "win32" and not self._afinidad:
                try:  # WDA_EXCLUDEFROMCAPTURE: no sale en las capturas de pantalla de SAGE
                    import ctypes
                    ctypes.windll.user32.SetWindowDisplayAffinity(int(self.winId()), 0x11)
                    self._afinidad = True
                except Exception:
                    pass

    def ocultar(self):
        if self.isVisible():
            self._timer.stop()
            self.hide()

    def _tick(self):
        self.t += 0.066
        self.update()

    def paintEvent(self, ev):
        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.Antialiasing)
        s = float(self._tam)
        centro = QPointF(s / 2, s / 2)
        color = QColor(COLORES.get(self.estado, COLORES["idle"]))
        pulso = 0.5 + 0.5 * math.sin(self.t * VEL_PULSO.get(self.estado, 2.0) * 0.5)
        p.setPen(Qt.PenStyle.NoPen)
        p.setBrush(QColor(0, 0, 0, 70))   # base oscura: se distingue sobre fondos claros y oscuros
        p.drawEllipse(centro, s * 0.46, s * 0.46)
        halo = QRadialGradient(centro, s * 0.5)
        c0, c1 = QColor(color), QColor(color)
        c0.setAlpha(int(40 + 60 * pulso)); c1.setAlpha(0)
        halo.setColorAt(0.0, c0); halo.setColorAt(1.0, c1)
        p.setBrush(QBrush(halo))
        p.drawEllipse(centro, s * 0.5, s * 0.5)
        anillo = QColor(color); anillo.setAlpha(190)
        pen = QPen(anillo); pen.setWidthF(max(1.2, s * 0.07))
        p.setPen(pen); p.setBrush(Qt.BrushStyle.NoBrush)
        p.drawEllipse(centro, s * 0.30, s * 0.30)
        punto = QColor(color); punto.setAlpha(int(200 + 55 * pulso))
        p.setPen(Qt.PenStyle.NoPen); p.setBrush(punto)
        r = s * 0.11 * (0.9 + 0.2 * pulso)
        p.drawEllipse(centro, r, r)


class MensajeCompleto(QWidget):
    """Mensaje a TODA la ventana de SAGE (estilo Sonic Riders): fondo oscuro con franjas en movimiento y el texto lo más grande
    que quepa. Se cierra con click, con Esc, solo (si trae segundos) o con «cierra el mensaje». Lo anima el reloj de Ventana (tick)."""
    ENTRADA, SALIDA = 0.38, 0.25

    def __init__(self, parent):
        super().__init__(parent)
        self.setCursor(Qt.CursorShape.PointingHandCursor)
        self._texto, self._autor = "", "SAGE"
        self._t = self._sal = 0.0
        self._saliendo = False
        self._cierra_en = None
        self._fit = None
        self.hide()

    def activo(self):
        return self.isVisible() and not self._saliendo

    def mostrar(self, texto, autor="SAGE", segundos=None):
        self._texto, self._autor = texto, autor
        self._t = self._sal = 0.0
        self._saliendo = False
        self._cierra_en = segundos
        self._fit = None
        p = self.parentWidget()
        if p is not None:
            self.setGeometry(p.rect())
        self.show()
        self.raise_()
        self.update()

    def ocultar(self):
        if self.isVisible() and not self._saliendo:
            self._saliendo, self._sal = True, 0.0

    def tick(self, dt):
        if not self.isVisible():
            return
        self._t += dt
        if self._saliendo:
            self._sal += dt
            if self._sal >= self.SALIDA:
                self._saliendo = False
                self.hide()
                return
        elif self._cierra_en is not None and self._t >= self._cierra_en:
            self.ocultar()
        self.update()

    def mousePressEvent(self, ev):
        self.ocultar()

    def _alfa(self):
        if self._saliendo:
            return max(0.0, 1.0 - self._sal / self.SALIDA)
        return min(1.0, self._t / self.ENTRADA)

    def _tamano(self, area):
        """Mayor tamaño de letra con el que el mensaje entra entero en el área."""
        clave = (self._texto, int(area.width()), int(area.height()))
        if self._fit is not None and self._fit[0] == clave:
            return self._fit[1]
        elegido = 12
        flags = Qt.AlignmentFlag.AlignCenter | Qt.TextFlag.TextWordWrap
        for pt in range(96, 11, -4):
            r = QFontMetrics(fuente(pt)).boundingRect(QRect(0, 0, int(area.width()), 100000), flags, self._texto)
            if r.height() <= area.height() and r.width() <= area.width():
                elegido = pt
                break
        self._fit = (clave, elegido)
        return elegido

    def paintEvent(self, ev):
        w, h = self.width(), self.height()
        a = self._alfa()
        e = a if self._saliendo else 1.0 - (1.0 - a) ** 3
        acento = COLORES["sage"] if self._autor.upper() == "SAGE" else COLORES["escuchando"]
        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.Antialiasing)
        p.fillRect(self.rect(), QColor(4, 6, 10, int(242 * a)))

        # franjas diagonales que corren (velocidad de Sonic Riders)
        p.setPen(Qt.PenStyle.NoPen)
        p.setBrush(con_alpha(acento, 24 * a))
        paso, ancho, inc = 150, 52, h * 0.35
        x = -inc - paso + (self._t * 110) % paso
        while x < w + inc:
            p.drawPolygon(QPolygonF([QPointF(x, 0), QPointF(x + ancho, 0), QPointF(x + ancho - inc, h), QPointF(x - inc, h)]))
            x += paso

        # barras de acento arriba y abajo que entran deslizando
        p.setBrush(con_alpha(acento, 255 * a))
        p.drawPolygon(paralelogramo(26, 20, max(0.0, (w - 52) * e), 5, 5))
        p.drawPolygon(paralelogramo(w - 26 - max(0.0, (w - 52) * e), h - 25, max(0.0, (w - 52) * e), 5, 5))

        # etiqueta «MENSAJE · autor»
        etiqueta = f"MENSAJE · {self._autor.upper()}"
        p.setFont(fuente(10, 3))
        ew = QFontMetrics(fuente(10, 3)).horizontalAdvance(etiqueta) + 44
        p.setBrush(con_alpha(acento, 235 * a))
        p.drawPolygon(paralelogramo(30 - (1.0 - e) * 60, 38, ew, 32, 12))
        p.setPen(con_alpha(QColor(255, 255, 255), 255 * a))
        p.drawText(QRectF(30 - (1.0 - e) * 60, 38, ew, 32), Qt.AlignmentFlag.AlignCenter, etiqueta)

        # texto principal, lo más grande que quepa
        area = QRectF(w * 0.08, 96, w * 0.84, max(40.0, h - 96 - 80))
        flags = Qt.AlignmentFlag.AlignCenter | Qt.TextFlag.TextWordWrap
        p.setFont(fuente(self._tamano(area)))
        dy = (1.0 - e) * 36
        sombra = QRectF(area.x() + 4, area.y() + 4 + dy, area.width(), area.height())
        p.setPen(con_alpha(acento, 170 * a))
        p.drawText(sombra, flags, self._texto)
        p.setPen(con_alpha(QColor(255, 255, 255), 255 * a))
        p.drawText(QRectF(area.x(), area.y() + dy, area.width(), area.height()), flags, self._texto)

        # pie: cómo cerrarlo (y cuenta atrás si se cierra solo)
        p.setFont(fuente(8, 2))
        p.setPen(con_alpha(QColor(150, 175, 190), 230 * a))
        p.drawText(QRectF(30, h - 52, w - 60, 20), Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter, "CLICK O ESC PARA CERRAR")
        if self._cierra_en and not self._saliendo:
            resto = max(0.0, 1.0 - self._t / self._cierra_en)
            p.setPen(Qt.PenStyle.NoPen)
            p.setBrush(con_alpha(acento, 255 * a))
            p.drawRect(QRectF(0, h - 4, w * resto, 4))


class PuenteEscucha(QObject):
    """Pasa al hilo de la interfaz lo que ocurre en los hilos de la escucha por nombre."""
    llamado = Signal(str)
    fallo = Signal(str)


ajustes.Gestor(sys.modules[__name__]).aplicar()   # colores, voz, velocidades... guardados en sage_ajustes.json


class Ventana(QMainWindow):
    alerta_seg = Signal(object)   # alertas de seguridad (vienen de otro hilo)

    def __init__(self, cerebro):
        super().__init__()
        self.cerebro = cerebro
        self.setWindowTitle("SAGE // EXTREME OS")
        self.resize(1150, 780)
        self.setMinimumSize(900, 640)

        self.grabadora_mic = Grabadora()
        self.grabadora_pc = GrabadoraPC()
        self.grabadora_actual = None
        self.grabando_tipo = None  # None, "mic", "pc"

        self._tareas = set()
        self._mensajes_pend = []   # [MENSAJE: ...] de la respuesta en curso: se muestran cuando termina de actuar
        self._parcial = ""
        self._hablado_txt = ""
        self._burbuja_sage = None
        self._estado = "idle"
        self._color_estado = None
        self._nivel = 0.0
        self._texto_pend = ""
        self._pend = ("", False)

        # Escucha por nombre: solo reacciona cuando oye "SAGE" (botón LLAMADO o Ctrl+L)
        self._ptt_exige_nombre = os.getenv("SAGE_LLAMADO_MIC", "0").strip() == "1"
        self.puente = PuenteEscucha()
        self.puente.llamado.connect(self._llamado_voz)
        self.puente.fallo.connect(self._escucha_fallo)
        self._interrumpida_voz = False
        self.escucha = EscuchaContinua(self.puente.llamado.emit, self._escucha_bloqueada, self.puente.fallo.emit, aviso,
                                       interrumpible=esta_hablando, al_interrumpir=self._interrumpida_por_voz)

        self._timer_ui = QTimer(self)
        self._timer_ui.setSingleShot(True)
        self._timer_ui.setInterval(80)
        self._timer_ui.timeout.connect(self._pintar_parcial)

        self.fondo = Fondo()
        self.setCentralWidget(self.fondo)
        raiz = QVBoxLayout(self.fondo)
        raiz.setContentsMargins(34, 26, 34, 30)
        raiz.setSpacing(18)

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
        self.lbl_lat = QLabel("LAT --")
        self.lbl_lat.setObjectName("telemetria")
        self.lbl_lat.setAlignment(Qt.AlignRight)
        tel.addWidget(self.lbl_lat)

        self.btn_escucha = BotonRiders("LLAMADO «SAGE»: OFF", ORO, compacto=True)
        self.btn_escucha.setToolTip("Escucha el micrófono sin parar y solo responde cuando dices «SAGE» (Ctrl+L)")
        self.btn_escucha.clicked.connect(self.toggle_escucha)

        self.btn_com = BotonRiders("COMENTARISTA: OFF", COLORES["escuchando"], compacto=True)
        self.btn_com.setToolTip("SAGE mira tu pantalla cada pocos segundos y comenta en voz alta lo que pasa (Ctrl+Shift+C). Un ojito sutil parpadea cuando mira.")
        self.btn_com.clicked.connect(self.toggle_comentarista)

        self.chk_top = QCheckBox("FIJAR HUD")
        self.chk_top.toggled.connect(self._siempre_encima)

        izq.addWidget(self.avatar, 1)
        izq.addWidget(self.estado_lbl)
        izq.addSpacing(10)
        self.telem = TelemetriaHUD()
        izq.addWidget(self.telem)
        izq.addLayout(tel)
        izq.addWidget(self.btn_escucha)
        izq.addWidget(self.btn_com)
        izq.addSpacing(4)
        izq.addWidget(self.chk_top)
        self.btn_ajustes = BotonRiders("⚙ AJUSTES", ORO, compacto=True)
        self.btn_ajustes.setToolTip("Colores, animación, voz y comportamiento de SAGE (Ctrl+,)")
        self.btn_ajustes.clicked.connect(lambda: self._ajustes.abrir_panel())
        izq.addWidget(self.btn_ajustes)
        self.placa = PlacaHUD("NÚCLEO")
        izq.setContentsMargins(24, 38, 24, 22)
        self.placa.setLayout(izq)
        cuerpo.addWidget(self.placa, 2)

        der = QVBoxLayout()
        der.setSpacing(12)
        self.chat = PanelChat()
        der.addWidget(self.chat, 1)

        fila = QHBoxLayout()
        fila.setSpacing(8)
        self.entrada = QLineEdit()
        self.entrada.setPlaceholderText("Comando... (Ctrl+M mic · Ctrl+L llamado SAGE)")
        self.entrada.returnPressed.connect(self.enviar)

        self.btn_mic = BotonRiders("MICRÓFONO", COLORES["escuchando"])
        self.btn_mic.clicked.connect(self.toggle_mic)

        self.btn_pc = BotonRiders("AUDIO PC", COLORES["escuchando"])
        self.btn_pc.clicked.connect(self.toggle_pc)

        self.btn_enviar = BotonRiders("EJECUTAR", COLORES["idle"])
        self.btn_enviar.clicked.connect(self.enviar)

        fila.addWidget(self.entrada, 1)
        fila.addWidget(self.btn_mic)
        fila.addWidget(self.btn_pc)
        fila.addWidget(self.btn_enviar)
        self.placa_cmd = PlacaHUD("COMANDO")
        fila.setContentsMargins(22, 38, 22, 18)
        self.placa_cmd.setLayout(fila)
        der.addWidget(self.placa_cmd)
        cuerpo.addLayout(der, 3)

        self.mensaje = MensajeCompleto(self)

        QShortcut(QKeySequence("Ctrl+M"), self, activated=self._atajo_mic)
        QShortcut(QKeySequence("Ctrl+L"), self, activated=self.toggle_escucha)
        QShortcut(QKeySequence("Ctrl+Shift+C"), self, activated=self.toggle_comentarista)
        self._ajustes = ajustes.Gestor(sys.modules[__name__], self)
        QShortcut(QKeySequence("Ctrl+,"), self, activated=self._ajustes.abrir_panel)
        QShortcut(QKeySequence("Esc"), self, activated=self._esc)
        QShortcut(QKeySequence("F11"), self, activated=self._alternar_pantalla)
        self._max = True   # arranca maximizada (F11 alterna maximizada / normal)

        # Reloj único: anima todos los widgets y repinta la ventana una sola vez por fotograma
        self._ult = time.perf_counter()
        self._reloj = QTimer(self)
        self._reloj.timeout.connect(self._frame)
        self._reloj.start(FPS_MS)

        self._set_estado("idle", self._texto_idle())
        self.entrada.setFocus()

        # NUEVAS VARIABLES DE CONTROL CONVERSACIONAL
        self._origen_comando = "texto"
        self._estaba_hablando = False
        self._ultimo_intercambio = time.perf_counter()
        self._minutos_silencio = 5.0  # Minutos de inactividad antes de que SAGE te hable sola

        self._correr(Tarea(self._calentar))
        self._salir = False            # True solo cuando Niko apaga SAGE de verdad
        self._segundo_plano = False    # True = ventana cerrada, SAGE sigue activa en la bandeja
        self._plano_pend = None
        self._crear_bandeja()
        self.alerta_seg.connect(self._alerta_seguridad)
        self._cajas_seg = []
        seguridad.iniciar(self.alerta_seg.emit)   # vigila inicios de sesión ajenos (correo + Spotify)
        self._ajustes.aplicar()   # botones, fps y «fijar HUD» según lo guardado
        self._indicador = IndicadorSage()   # puntito sutil abajo a la derecha mientras la ventana no se ve
        self._timer_ind = QTimer(self)
        self._timer_ind.timeout.connect(self._actualizar_indicador)
        self._timer_ind.start(600)

        # Modo comentarista: mira la pantalla de forma continua y opina en tiempo real (apagado hasta que Niko lo pide)
        self._comentarista = comentarista.Comentarista(self.cerebro, self._comentarista_ocupado, lambda: self._comentarista_ocupado(True))
        self._ojo = comentarista.OjoPantalla()
        self._comentarista.comentario.connect(self._comentario)
        self._comentarista.stun.connect(self._reaccion_stun)
        self._comentarista.detectado.connect(self._juego_detectado)
        self._comentarista.auto.connect(self._auto_comentarista)
        self._comentarista.latido.connect(self._ojo.set_estado)
        self._comentarista.start()
        if os.getenv("SAGE_COMENTARISTA", "0").strip() == "1":
            QTimer.singleShot(2500, lambda: self.set_comentarista(True))
        
        # ACTIVAR ESCUCHA POR NOMBRE SIEMPRE POR DEFECTO
        QTimer.singleShot(1500, self.toggle_escucha)

        self.setWindowOpacity(0.0)
        self._fade = QPropertyAnimation(self, b"windowOpacity", self)
        self._fade.setDuration(500)
        self._fade.setStartValue(0.0)
        self._fade.setEndValue(1.0)
        self._fade.setEasingCurve(QEasingCurve.OutCubic)
        self._fade.start()

    def resizeEvent(self, ev):
        super().resizeEvent(ev)
        if hasattr(self, "mensaje"):
            self.mensaje.setGeometry(self.rect())

    def _esc(self):
        """Esc: si hay un mensaje a pantalla completa lo cierra; si no, es el freno de emergencia de siempre."""
        if self.mensaje.activo():
            self.mensaje.ocultar()
            return
        self.interrumpir()

    def _mostrar_mensajes_pend(self):
        pend, self._mensajes_pend = self._mensajes_pend, []
        for accion, texto, segundos in pend:
            if accion == "cerrar":
                self.mensaje.ocultar()
            else:
                self.mensaje.mostrar(texto, "SAGE", segundos)

    def _orden_mensaje_local(self, texto):
        """«Muestra el mensaje: ...» / «cierra el mensaje»: Niko lo pide directo y se hace al instante, sin modelo. True si lo resolvió."""
        orden = interpretar_orden_mensaje(texto)
        if orden is None:
            return False
        accion, msg, segundos = orden
        if accion == "cerrar":
            if not self.mensaje.activo():
                return False   # no hay ningún mensaje abierto: que lo entienda el modelo
            self.mensaje.ocultar()
            self._agregar("Sistema", "🖥 Mensaje cerrado.")
        else:
            self.mensaje.mostrar(msg, "NIKO", segundos)
            self._agregar("Sistema", "🖥 Mensaje a toda la ventana (click o Esc para cerrarlo).")
        self._ultimo_intercambio = time.perf_counter()
        return True

    # ---------- Segundo plano / bandeja del sistema ----------
    def _ajuste_por_voz(self, arg):
        ok, msg = self._ajustes.set_valor(arg)
        self._log_sistema(("⚙️ " if ok else "⚠ ") + msg)

    def _crear_bandeja(self):
        """Icono pequeño y discreto en la bandeja del sistema (abajo a la derecha): indica que SAGE sigue activa aunque su ventana esté cerrada."""
        self._bandeja = None
        if not QSystemTrayIcon.isSystemTrayAvailable():
            return
        icono = QIcon(RUTA_ICONO) if os.path.exists(RUTA_ICONO) else self._icono_punto()
        b = QSystemTrayIcon(icono, self)
        b.setToolTip("SAGE · activa")
        menu = QMenu()
        self._acciones_bandeja = []
        for texto, fn in (("Mostrar SAGE", self.primer_plano), ("Ajustes", lambda: (self.primer_plano(), self._ajustes.abrir_panel())), ("Segundo plano", self.segundo_plano), (None, None), ("Apagar SAGE", self.apagar_total)):
            if texto is None:
                menu.addSeparator()
                continue
            act = QAction(texto, menu)
            act.triggered.connect(lambda _=False, f=fn: f())
            menu.addAction(act)
            self._acciones_bandeja.append(act)
        b.setContextMenu(menu)
        b.activated.connect(self._bandeja_click)
        b.show()
        self._bandeja, self._menu_bandeja = b, menu

    @staticmethod
    def _icono_punto():
        pm = QPixmap(32, 32)
        pm.fill(Qt.GlobalColor.transparent)
        p = QPainter(pm)
        p.setRenderHint(QPainter.RenderHint.Antialiasing)
        c = QColor(COLORES["idle"])
        c.setAlpha(210)
        p.setPen(Qt.PenStyle.NoPen)
        p.setBrush(c)
        p.drawEllipse(QPointF(16, 16), 6, 6)
        p.end()
        return QIcon(pm)

    def _actualizar_indicador(self):
        """Muestra el puntito abajo a la derecha mientras la ventana de SAGE no se ve (segundo plano o minimizada)."""
        ind = getattr(self, "_indicador", None)
        if ind is None:
            return
        if self._salir or os.getenv("SAGE_INDICADOR", "1").strip() == "0":
            ind.ocultar()
            return
        visible = self.isVisible() and not self.isMinimized()
        if visible and os.getenv("SAGE_INDICADOR_SIEMPRE", "0").strip() != "1":
            ind.ocultar()
        else:
            ind.mostrar()

    def _bandeja_click(self, motivo):
        if motivo in (QSystemTrayIcon.ActivationReason.Trigger, QSystemTrayIcon.ActivationReason.DoubleClick):
            self.primer_plano()

    def segundo_plano(self):
        """Cierra la ventana pero SAGE sigue activa (escucha, voz, temporizadores, tareas). Se vuelve con «ponte en primer plano» o con el icono de la bandeja."""
        if getattr(self, "_bandeja", None) is None:   # sin bandeja no habría forma de volver: solo se minimiza
            self.showMinimized()
            return
        self._segundo_plano = True
        self.hide()
        self._bandeja.setToolTip("SAGE · en segundo plano")
        self._actualizar_indicador()

    def _actualizar_telemetria(self):
        try: animo = float(self.cerebro.felicidad.nivel())
        except Exception: animo = None
        modelo = str(getattr(self.cerebro, "modelo", "") or "--").upper()
        esc = getattr(self, "escucha", None)
        self.telem.poner([
            ("ESCUCHA", "ACTIVA" if (esc is not None and esc.activa) else "APAGADA", None),
            ("VOZ", "HABLANDO" if esta_hablando() else "EN ESPERA", None),
            ("ÁNIMO", f"{animo:.0f} / 100" if animo is not None else "--", None if animo is None else animo / 100.0),
            ("NÚCLEO", modelo if len(modelo) < 20 else modelo[:19] + "…", None),
        ], self.avatar.color)

    def _alternar_pantalla(self):
        self._max = not self.isMaximized()
        self.showMaximized() if self._max else self.showNormal()

    def primer_plano(self):
        """Devuelve la ventana de SAGE al frente."""
        self._segundo_plano = False
        if self.isMinimized():
            self.showMaximized() if getattr(self, "_max", True) else self.showNormal()
        else:
            self.show()
        self.raise_()
        self.activateWindow()
        self._traer_ventana_al_frente()
        if getattr(self, "_bandeja", None) is not None:
            self._bandeja.setToolTip("SAGE · activa")
        self.entrada.setFocus()
        self._actualizar_indicador()

    def _traer_ventana_al_frente(self):
        """Windows no deja que una app tome el foco sin que el usuario la toque (p. ej. al pedirlo por voz): se acopla al hilo de la ventana activa un instante."""
        if sys.platform != "win32": return
        try:
            import ctypes
            u = ctypes.windll.user32
            hwnd = int(self.winId())
            t_fg = u.GetWindowThreadProcessId(u.GetForegroundWindow(), None)
            t_me = ctypes.windll.kernel32.GetCurrentThreadId()
            acoplar = bool(t_fg) and t_fg != t_me
            if acoplar: u.AttachThreadInput(t_me, t_fg, True)
            u.SetForegroundWindow(hwnd)
            if acoplar: u.AttachThreadInput(t_me, t_fg, False)
        except Exception:
            pass

    def apagar_total(self):
        """Apaga SAGE por completo (deja de escuchar y quita su icono de la bandeja). Solo con «apágate» / «vete a descansar» o desde el menú de la bandeja."""
        self._salir = True
        _salida_forzosa(3.5)   # red de seguridad: pase lo que pase al cerrar, el proceso muere en unos segundos
        self.close()

    def _cerrar_recursos(self):
        """Libera todo lo que SAGE abrió antes de terminar el proceso (cada paso protegido: uno que falle no impide los demás)."""
        for t in list(getattr(self, "_tareas", ())):       # tareas en marcha: que paren en cuanto puedan
            try: t.cancelado = True
            except Exception: pass
        pasos = (
            lambda: self._timer_ui.stop(),
            lambda: self._bandeja.hide() if getattr(self, "_bandeja", None) is not None else None,   # sin icono fantasma en la bandeja
            lambda: self._vista.close() if hasattr(self, "_vista") else None,
            lambda: self._timer_ind.stop() if hasattr(self, "_timer_ind") else None,
            lambda: self._indicador.close() if hasattr(self, "_indicador") else None,
            lambda: self._comentarista.detener() if hasattr(self, "_comentarista") else None,   # deja de mirar la pantalla
            lambda: self._ojo.close() if hasattr(self, "_ojo") else None,
            lambda: self.escucha.detener(),
            lambda: self.grabadora_actual.detener() if self.grabando_tipo and self.grabadora_actual else None,
            lambda: __import__("boca").cerrar(),            # corta la voz y detiene sus hilos de audio
            lambda: dispositivos.espejo_cerrar(),           # pantalla compartida del celular (scrcpy)
            lambda: getattr(self.cerebro, "felicidad", None) and self.cerebro.felicidad.guardar(),
        )
        for paso in pasos:
            try: paso()
            except Exception as e: print(f"[Cierre] {e}")

    def _contexto_previo(self):
        """Texto del intercambio anterior (para entender «ciérralo»)."""
        try:
            return " ".join((p.text or "") for c in self.cerebro.historial[-4:-2] for p in (c.parts or []))
        except Exception:
            return ""

    def _orden_ventana_local(self, texto):
        """«Ponte en segundo plano» / «ponte en primer plano» / «apágate» / «vete a descansar»: se resuelven al instante, sin modelo. True si las resolvió."""
        t = vent.norm(texto)
        if _RE_ORDEN_APAGAR.search(t):
            accion, frase, nota = "apagar", "Hasta luego, Niko. Me voy a descansar.", "⏻ Apagando SAGE por completo."
        elif _RE_ORDEN_SEGUNDO.search(t):
            accion, frase, nota = "segundo", "Aquí sigo, en segundo plano.", "🌙 Paso a segundo plano: sigo activa y escuchando. Dime «ponte en primer plano» o usa el icono de la bandeja."
        elif _RE_ORDEN_PRIMER.search(t):
            accion, frase, nota = "primer", "Aquí estoy.", "☀ De vuelta en primer plano."
        else:
            return False
        self._ultimo_intercambio = time.perf_counter()
        self._agregar("Sistema", nota)
        self._pend = (frase, accion == "apagar")
        self._plano_pend = accion if accion in ("segundo", "primer") else None
        self._fin_ejecucion()
        return True

    # ---------- Modo comentarista ----------
    def set_comentarista(self, on):
        self._comentarista.activar(on)
        if on: self._ojo.mostrar()
        else: self._ojo.ocultar()
        self.btn_com.setText("COMENTARISTA: ON" if on else "COMENTARISTA: OFF")

    def toggle_comentarista(self):
        on = not self._comentarista.activo
        self.set_comentarista(on)
        self._agregar("Sistema", "👁 Modo comentarista ENCENDIDO: SAGE mira tu pantalla cada pocos segundos y comenta lo que pasa (el ojito de abajo a la derecha parpadea cuando mira)."
                      if on else "👁 Modo comentarista APAGADO: SAGE ya no mira tu pantalla.")

    def _orden_comentarista_local(self, texto):
        """«Sé mi comentarista» / «deja de comentar»: se resuelve al instante, sin modelo. True si lo resolvió."""
        t = vent.norm(texto)
        if _RE_COM_OFF.search(t):
            on, frase, nota = False, "De acuerdo, dejo de mirar tu pantalla.", "👁 Modo comentarista APAGADO: SAGE ya no mira tu pantalla."
        elif _RE_COM_ON.search(t):
            on = True
            frase = "Listo, Niko. Soy tu comentarista: miro tu pantalla y te cuento lo que pase. Verás un ojito pequeño cuando esté mirando."
            nota = "👁 Modo comentarista ENCENDIDO: SAGE mira tu pantalla cada pocos segundos y comenta (ojito abajo a la derecha). Dime «deja de comentar» para apagarlo."
        else:
            return False
        self.set_comentarista(on)
        self._ultimo_intercambio = time.perf_counter()
        self._agregar("Sistema", nota)
        self._pend = (frase, False)
        self._fin_ejecucion()
        return True

    def _comentarista_ocupado(self, ignorar_voz_propia=False):
        """(Desde el hilo del comentarista) True si SAGE está haciendo otra cosa: entonces ni mira ni comenta.
        ignorar_voz_propia: en Outcome sigue mirando mientras habla SU comentario (para no perderse un stun)."""
        try:
            hablando = esta_hablando() and not (ignorar_voz_propia and getattr(self, "_origen_comando", "") == "comentarista")
            if self._estado != "idle" or hablando or self.grabando_tipo or self.mensaje.activo():
                return True
            if any(isinstance(t, Ejecutor) and t.isRunning() for t in list(self._tareas)):
                return True
            esc = getattr(self, "escucha", None)
            if esc is not None and getattr(esc, "_armada_hasta", 0) > time.monotonic():
                return True   # acaba de hablarte y espera tu respuesta: no la pises
        except Exception:
            return True
        return False

    def _reaccion_stun(self, texto):
        """Outcome Memories: Niko (o un superviviente) acaba de hacer un STUN. SAGE reacciona al instante: voz corta, rebote del avatar y un poco de felicidad."""
        if not texto or not self._comentarista.activo:
            return
        self._origen_comando = "comentarista"
        try:
            from boca import callar
            callar()   # el stun manda: corta el comentario anterior si seguía hablando
        except Exception:
            pass
        self._agregar("SAGE", "⚡ " + texto)
        self.cerebro.registrar_comentario(texto)
        self._ultimo_intercambio = time.perf_counter()
        try:   # reacción visible: el avatar rebota y lanza una onda
            self.avatar.rebote = 1.0
            self.avatar.ondas.append(self.avatar.t)
        except Exception:
            pass
        try:
            self.cerebro.felicidad.recompensar(0.5, "un stun en Outcome Memories")
        except Exception:
            pass
        self._lanzar(Tarea(hablar, texto), lambda x: None, lambda e: print(f"Fallo de voz: {e}"))

    def _juego_detectado(self, juego):
        if juego == "outcome":
            self._agregar("Sistema", "🎮 Detecté Outcome Memories: reacciono a cada stun.")

    def _auto_comentarista(self, on):
        """SAGE_OUTCOME_AUTO=1: el comentarista se enciende solo al empezar Outcome Memories y se apaga al cerrarlo."""
        if on == self._comentarista.activo:
            return
        self.set_comentarista(on)
        self._agregar("Sistema", "🎮 Empezó Outcome Memories: modo comentarista ENCENDIDO automáticamente (dime «deja de comentar» para apagarlo)."
                      if on else "🎮 Outcome Memories se cerró: modo comentarista apagado.")

    def _comentario(self, texto, juego):
        if not texto or not self._comentarista.activo:
            return
        self._origen_comando = "comentarista"   # que al terminar de hablar no suene la campanita de «te escucho»
        self._agregar("SAGE", "👁 " + texto)
        self.cerebro.registrar_comentario(texto)
        self._ultimo_intercambio = time.perf_counter()   # comentar no cuenta como silencio roto
        self._lanzar(Tarea(hablar, texto), lambda x: None, lambda e: print(f"Fallo de voz: {e}"))

    def interrumpir(self):
        """Freno de emergencia: detiene la voz y cancela la ejecución de tareas del mouse."""
        try:
            from boca import callar
            callar()  # Corta el audio inmediatamente
        except Exception as e:
            print(f"[Interrumpir] no pude cortar la voz: {e}")

        for t in list(self._tareas):
            if hasattr(t, "cancelado"):
                t.cancelado = True

        self._parcial = ""
        self._pend = ("", False)
        self._mensajes_pend = []
        self._timer_ui.stop()

        if self._burbuja_sage:
            self._burbuja_sage.set_markdown(self._burbuja_sage.cuerpo.toPlainText() + "\n\n*(Interrumpida)*")
            self._burbuja_sage = None

        if cancelar_energia():
            self._agregar("Sistema", "⏻ Apagado/reinicio programado: CANCELADO.")
        self._agregar("Sistema", "🛑 SAGE ha sido interrumpida por Niko.")
        self._listo()

    def _calentar(self):
        try: self.cerebro.calentar()
        except Exception: pass
        try: precargar()
        except Exception: pass

    def _frame(self):
        ahora = time.perf_counter()
        dt = min(0.1, ahora - self._ult)
        self._ult = ahora

        self._actualizar_estado_visual()

        # --- MODO CONVERSACIONAL AUTOMÁTICO (INCLUSO MINIMIZADA) ---
        hablando = esta_hablando()
        if self._estaba_hablando and not hablando:
            # Acaba de terminar de hablar. Si la orden fue por voz (o iniciativa), abrimos ventana de respuesta.
            if getattr(self, "_origen_comando", "") in ("mic", "sage", "silencio") and getattr(self, "escucha", None) and self.escucha.activa:
                import time as base_time
                self.escucha._armada_hasta = base_time.monotonic() + 8.0
                if not self._interrumpida_voz:
                    aviso() # Suena la campanita suave indicando que te está escuchando
            self._interrumpida_voz = False
        self._estaba_hablando = hablando

        # --- INICIATIVA PROACTIVA (ROMPER EL SILENCIO) ---
        if self._estado == "idle" and getattr(self, "escucha", None) and self.escucha.activa and not self.grabando_tipo:
            if (ahora - self._ultimo_intercambio) > (self._minutos_silencio * 60):
                self._ultimo_intercambio = ahora
                self._origen_comando = "silencio"
                comando_fantasma = "[DIRECTIVA DE SISTEMA: Ha pasado un buen rato de inactividad. Rompe el silencio con algo breve y natural: pregúntale a Niko qué está haciendo o comparte un pensamiento aleatorio. PROHIBIDO hablar de la hora, la fecha, el clima, la temperatura, la ubicación, la postura, el agua, estirarse o descansar. Sé breve, conversacional, y NUNCA menciones que recibiste esta directiva.]"
                self._pedir_respuesta(comando_fantasma)
        # -----------------------------------------------------------

        if self.isMinimized() or not self.isVisible():
            return

        if self.grabando_tipo:
            destino = min(1.0, getattr(self.grabadora_actual, "nivel", 0.0) * 7)
        elif self.escucha.activa and self._estado == "idle":
            destino = min(1.0, self.escucha.nivel * 7)
        else:
            destino = 0.0
        self._nivel += (destino - self._nivel) * min(1.0, dt * 8.6)
        self.avatar.nivel = self._nivel

        self.fondo.tick(dt)
        self.cabecera.tick(dt)
        self.avatar.tick(dt)
        self.chat.tick(dt)
        self.placa.tick(dt)
        self.placa_cmd.tick(dt)
        self._t_telem = getattr(self, "_t_telem", 0.0) + dt
        if self._t_telem > 0.5:
            self._t_telem = 0.0
            self._actualizar_telemetria()
        self.mensaje.tick(dt)  # CRUCIAL: Sin esto el mensaje a pantalla completa nunca sube su alfa de 0.0
        self.fondo.update()

    def _siempre_encima(self, activo):
        self.setWindowFlag(Qt.WindowStaysOnTopHint, activo)
        self.show()

    def _pintar_estado(self, estado):
        self._estado_pintado = estado
        self.avatar.set_estado(estado)
        self.fondo.set_estado(estado)
        if getattr(self, "_indicador", None) is not None: self._indicador.set_estado(estado)
        self.cabecera.set_estado(estado)
        self.chat.set_estado(estado)
        self.placa.set_estado(estado)
        self.placa_cmd.set_estado(estado)

    def _actualizar_estado_visual(self):
        """En reposo con el llamado por nombre activo, SAGE se ve «escuchando» (color de escuchando) cuando está armada o oye tu voz."""
        estado = self._estado
        if estado == "idle":
            esc = getattr(self, "escucha", None)
            try:
                armada = esc is not None and esc.activa and time.monotonic() < getattr(esc, "_armada_hasta", 0)
                if armada or (esc is not None and esc.activa and self.avatar.nivel > 0.12):
                    estado = "escuchando"
            except Exception:
                pass
        if estado != getattr(self, "_estado_pintado", None):
            self._pintar_estado(estado)
        c = COLORES.get(estado, COLORES["idle"]).name()
        if c != self._color_estado:
            self._color_estado = c
            self.estado_lbl.setStyleSheet(f"color: {c};")
            self.entrada.setStyleSheet(f"border-color: {c};")

    def _set_estado(self, estado, texto):
        self._estado = estado
        c = COLORES.get(estado, COLORES["idle"]).name()
        self._pintar_estado(estado)
        self.estado_lbl.setText(texto)
        if c != self._color_estado:
            self._color_estado = c
            self.estado_lbl.setStyleSheet(f"color: {c};")
            self.entrada.setStyleSheet(f"border-color: {c};")

    def _agregar(self, autor, texto, markdown=False):
        return self.chat.agregar(autor, texto, markdown=markdown)

    def _alerta_seguridad(self, a):
        """Alerta de inicio de sesión ajeno: avisa, habla y pregunta si saca a ese usuario (Sí / Fui yo / Ahora no)."""
        if "_log" in a:
            self._log_sistema("🛡️ " + a["_log"]); return
        serv, det = a["servicio"], (a.get("detalle") or "").strip()
        falso = a.get("verificado") is False
        self._agregar("Sistema", f"🛡️ ALERTA DE SEGURIDAD · {serv}: {a['asunto']}" + (f"\n{det}" if det else "") +
                      ("\n⚠️ Correo SIN VERIFICAR (posible phishing): no abras sus enlaces." if falso else ""))
        aviso()
        self._lanzar(Tarea(hablar, f"Niko, alerta de seguridad en {serv}. " + ("Ojo, el aviso parece falso. " if falso else "") +
                           "¿Quieres que saque a ese usuario de tu cuenta?"), lambda x: None, lambda e: None)
        caja = QMessageBox(self)
        caja.setWindowTitle(f"SAGE · Seguridad de {serv}")
        caja.setIcon(QMessageBox.Icon.Warning)
        caja.setText(f"{serv}: {a['asunto']}" + (f"\n\n{det}" if det else "") +
                     ("\n\n⚠️ Correo SIN VERIFICAR: puede ser phishing." if falso else "") + "\n\n¿Saco a ese usuario de tu cuenta?")
        si = caja.addButton("Sí, sácalo", QMessageBox.ButtonRole.AcceptRole)
        yo = caja.addButton("Fui yo", QMessageBox.ButtonRole.DestructiveRole)
        caja.addButton("Ahora no", QMessageBox.ButtonRole.RejectRole)
        caja.setWindowModality(Qt.WindowModality.NonModal)

        def respuesta(b, a=a):
            self._cajas_seg = [c for c in self._cajas_seg if c is not caja]
            if b is si:
                t = seguridad.resolver(a["id"], "expulsar")
                if t: self._ejecutar_tarea_programada(t)
            elif b is yo:
                seguridad.resolver(a["id"], "fui_yo")
                self._log_sistema(f"🛡️ Entendido, {serv} marcado como tuyo.")
            else:
                seguridad.resolver(a["id"], "postergar")
        caja.buttonClicked.connect(respuesta)
        self._cajas_seg.append(caja)
        caja.show(); caja.raise_()

    def _log_sistema(self, texto):
        self._agregar("Sistema", texto)

    def _pintar_parcial(self):
        if self._burbuja_sage is not None and self._parcial:
            self._burbuja_sage.set_markdown(limpiar_parcial(self._parcial))

    def _respuesta_ok(self):
        self._timer_ui.stop()
        final = self._parcial or "(sin respuesta)"

        acciones = extraer_acciones(final)
        acciones, bloqueadas = vent.filtrar_acciones(acciones, self._texto_pend, self._contexto_previo())   # nada de cerrar/cambiar ventanas sin que Niko lo pida
        for b in bloqueadas:
            self._agregar("Sistema", f"🛡 Bloqueé {b}")
        if bloqueadas:
            try: self.cerebro.registrar_resultado("BLOQUEADO por seguridad (Niko no lo pidió): " + " | ".join(bloqueadas))
            except Exception: pass
        self._plano_pend = "segundo" if RE_SEGUNDO_PLANO.search(final) else ("primer" if RE_PRIMER_PLANO.search(final) else None)
        self._mensajes_pend = extraer_mensajes(final)
        apagar = bool(RE_APAGAR.search(final))
        limpio = limpiar(final)
        hablado, self._hablado_txt = self._hablado_txt, ""
        voz = limpio[len(hablado):].strip() if limpio.startswith(hablado) else ("" if hablado else limpio)   # lo que aún no se ha dicho

        if self._burbuja_sage is not None:
            self._burbuja_sage.set_markdown(limpio)
        else:
            self._agregar("SAGE", limpio, markdown=True)

        self._parcial = ""
        self._burbuja_sage = None


        m = getattr(self.cerebro, "_m", None) or {}
        if m.get("primero") is not None:
            self.lbl_lat.setText(f"LAT {m['primero']:.2f}s")

        if acciones and es_segundo_plano(acciones) and not apagar:
            # Segundo plano: no oculta la HUD, no bloquea la interfaz ni toca el mouse/teclado de Niko; sigue trabajando
            ej = Ejecutor(acciones, self.cerebro, self._texto_pend)
            ej.log.connect(self._log_sistema)
            ej.alarma.connect(self._sonar_alarma)
            ej.ajuste.connect(self._ajuste_por_voz)
            ej.finished.connect(lambda t=ej: self._tareas.discard(t))
            self._tareas.add(ej)
            self._pend = (voz, False)
            ej.start()
            self._fin_ejecucion()   # habla y deja la interfaz libre YA
        elif acciones:
            # SAGE habla mientras actúa; la voz no espera a que termine la ejecución
            self._pend = ("", apagar)
            if voz and voz != "(sin respuesta)":
                self._lanzar(Tarea(hablar, voz), lambda x: None, lambda e: print(f"Fallo de voz: {e}"))
            self._set_estado("pensando", "OBSERVANDO Y EJECUTANDO...")
            ej = Ejecutor(acciones, self.cerebro, self._texto_pend)
            ej.log.connect(self._log_sistema)
            ej.hud.connect(self._mostrar_hud)
            ej.alarma.connect(self._sonar_alarma)
            ej.ajuste.connect(self._ajuste_por_voz)
            if not hasattr(self, "_vista"): self._vista = VistaVivo()
            ej.vista.connect(self._vista.poner)
            ej.finished.connect(self._fin_ejecucion)
            ej.finished.connect(lambda t=ej: self._tareas.discard(t))
            self._tareas.add(ej)
            ej.start()
        else:
            self._pend = (voz, apagar)
            self._fin_ejecucion()

    def _mostrar_hud(self, visible):
        """El ejecutor oculta la HUD mientras mira la pantalla (su animación ensuciaría la detección de carga)."""
        if visible:
            if not self._segundo_plano: self.show()
        else:
            self.hide()

    def _sonar_alarma(self, payload):
        """Se detona cuando el hilo asíncrono del temporizador llega a cero. Si trae tarea, la ejecuta como si Niko la pidiera."""
        mensaje, _, tarea = payload.partition("\x00")
        aviso()  # Hace sonar la campanilla del sistema
        self._agregar("Sistema", f"⏰ ALARMA COMPLETADA: {mensaje}")
        if tarea:
            texto_voz = f"Niko, es la hora programada. Voy con: {mensaje}"
        else:
            texto_voz = f"¡Niko, el temporizador ha terminado! Recuerda: {mensaje}"
        self._lanzar(Tarea(hablar, texto_voz), lambda x: None, lambda e: print(f"Fallo en voz de alarma: {e}"))
        if tarea:
            self._ejecutar_tarea_programada(tarea)

    def _ejecutar_tarea_programada(self, tarea, intentos=0):
        """Espera a que SAGE esté libre (no pensando ni hablando) y entonces procesa la orden programada."""
        if (not self.entrada.isEnabled() or esta_hablando()) and intentos < 300:   # reintenta hasta ~5 min
            QTimer.singleShot(1000, lambda: self._ejecutar_tarea_programada(tarea, intentos + 1))
            return
        self._origen_comando = "texto"
        self._agregar("Niko", f"⏰ (tarea programada) {tarea}")
        self._pedir_respuesta(tarea)

    def _fin_ejecucion(self):
        self._mostrar_mensajes_pend()   # ya terminó de actuar: la ventana está a la vista
        limpio, apagar = self._pend
        plano, self._plano_pend = self._plano_pend, None
        self._listo()
        if plano == "primer":
            self.primer_plano()
        hay_voz = bool(limpio and limpio != "(sin respuesta)") or esta_hablando()
        if hay_voz:
            self._lanzar(Tarea(hablar, limpio), lambda x: None, lambda e: print(f"Fallo de voz: {e}"))
        despues = self.apagar_total if apagar else (self.segundo_plano if plano == "segundo" else None)
        if despues is not None:   # se despide primero y después se oculta / apaga
            QTimer.singleShot(500 if hay_voz else 0, lambda: self._tras_voz(despues))

    def _tras_voz(self, fn, intentos=0):
        """Ejecuta fn cuando SAGE termine de hablar (máx. ~12 s)."""
        if esta_hablando() and intentos < 60:
            QTimer.singleShot(200, lambda: self._tras_voz(fn, intentos + 1))
        else:
            fn()

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

    def _hablar_incremental(self):
        """Lee en voz alta cada frase COMPLETA apenas se genera (sin esperar a que termine la respuesta)."""
        p = self._parcial
        k = p.rfind("[")
        if k != -1 and "]" not in p[k:]:
            p = p[:k]                      # directiva a medias: no se lee
        corte = 0
        for m in re.finditer(r"[.!?…]+[\"')\]]*\s|\n", p):
            corte = m.end()
        if corte <= 0:
            return
        pref = limpiar(p[:corte])
        previo = self._hablado_txt
        if not pref.startswith(previo):
            return
        nuevo = pref[len(previo):].strip()
        if len(nuevo) < 2:
            return
        self._hablado_txt = pref
        try: hablar(nuevo)
        except Exception as e: print(f"Fallo de voz: {e}")

    def _trozo(self, texto):
        if not self._parcial:
            self._hablado_txt = ""
            self._set_estado("respondiendo", "TRANSMITIENDO...")
        self._parcial += texto
        self._hablar_incremental()
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
            self.escucha.suspender()  # el micrófono lo usa la grabación manual; la escucha por nombre se reanuda al terminar
            try: self.grabadora_actual.iniciar()
            except Exception as e:
                self.escucha.reanudar()
                self._agregar("Sistema", f"No se pudo enlazar micrófono: {e}")
                return
            self.grabando_tipo = "mic"
            self.btn_mic.setText("DETENER MIC")
            self.btn_pc.setEnabled(False)
            self._bloquear(True)
            self._set_estado("escuchando", "ESCUCHANDO MIC...")
        else:
            audio = self._detener_grabacion()
            self.grabando_tipo = None
            self.btn_mic.setText("MICRÓFONO")
            self.btn_pc.setEnabled(True)
            self.btn_mic.setEnabled(False)
            self._set_estado("pensando", "DECODIFICANDO...")
            self._lanzar(Tarea(transcribir, audio), self._transcripcion_mic_ok, self._mic_error)

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
            audio = self._detener_grabacion()
            self.grabando_tipo = None
            self.btn_pc.setText("AUDIO PC")
            self.btn_mic.setEnabled(True)
            self.btn_pc.setEnabled(False)
            self._set_estado("pensando", "DECODIFICANDO PC...")
            self._lanzar(Tarea(transcribir, audio), self._transcripcion_ok, self._mic_error)

    def _transcripcion_mic_ok(self, texto):
        self._origen_comando = "mic"
        self._transcripcion_ok(texto, self._ptt_exige_nombre)

    def _detener_grabacion(self):
        """Detiene la grabadora actual y guarda su volumen máximo para explicar por qué salió vacía si hace falta."""
        g = self.grabadora_actual
        audio = g.detener()
        self._info_audio = (getattr(g, "pico", None), "el audio del PC" if g is self.grabadora_pc else f"«{getattr(g, 'nombre', '') or 'micrófono predeterminado'}»")
        return audio

    def _msg_senal_vacia(self):
        pico, nombre = getattr(self, "_info_audio", (None, ""))
        if pico is None:
            return "Señal vacía, reintente."
        if pico < 1e-4:
            return (f"Señal vacía: {nombre} no envió nada de audio (nivel {pico:.5f}). Revisa que no esté silenciado y que en Windows > Configuración > "
                    "Privacidad y seguridad > Micrófono estén activados «Acceso al micrófono» y «Permitir que las aplicaciones de escritorio accedan a tu "
                    f"micrófono». Para usar otro, pon MIC_DEVICE=<número o nombre> en .env. Entradas: {listar_entradas()}")
        if pico < 0.01:
            return f"Señal muy débil de {nombre} (nivel {pico:.4f}): sube el volumen del micrófono en Windows o acércate, y reintenta."
        return f"Se grabó audio de {nombre} (nivel {pico:.3f}) pero no entendí palabras. Habla un poco más cerca y reintenta."

    def _transcripcion_ok(self, texto, exigir_nombre=False):
        if not texto:
            self._agregar("Sistema", self._msg_senal_vacia())
            self._listo()
            return
        if exigir_nombre and not fue_llamada(texto):
            print(f"[Escucha] Ignorado (di SAGE al principio): «{texto}»")
            self._listo()
            return
        if exigir_nombre:
            aviso()
        self._agregar("Niko", texto)
        self._pedir_respuesta(texto)

    # --- LLAMADO POR NOMBRE ("SAGE") ---
    def _texto_idle(self):
        return "ESPERANDO «SAGE»" if self.escucha.activa else "SISTEMA ONLINE"

    def _escucha_bloqueada(self):
        """Bloquea mientras se graba a mano o SAGE habla (no se oye a sí misma). Al hablar, la escucha solo vigila
        si empiezas a hablar encima (interrupción por voz); mientras ejecuta sí oye, para poder decirle «SAGE, para»."""
        return bool(self.grabando_tipo) or esta_hablando()

    def _interrumpida_por_voz(self):
        """(Hilo de audio) Niko empezó a hablar mientras SAGE hablaba: corta la voz al instante."""
        self._interrumpida_voz = True
        try:
            from boca import callar
            callar()
        except Exception as e:
            print(f"[Interrumpir] no pude cortar la voz: {e}")

    def _sincronizar_escucha(self):
        activa = self.escucha.activa
        self.avatar.vigilando = activa
        self.btn_escucha.setText("LLAMADO «SAGE»: ON" if activa else "LLAMADO «SAGE»: OFF")
        self.btn_escucha.base = QColor(COLORES["idle"] if activa else ORO)
        self.btn_escucha.update()
        if self._estado == "idle":
            self.estado_lbl.setText(self._texto_idle())

    def toggle_escucha(self):
        if self.escucha.activa:
            self.escucha.detener()
        else:
            try: self.escucha.iniciar()
            except Exception as e:
                self._agregar("Sistema", f"No se pudo activar la escucha por nombre: {e}")
                return
        self._sincronizar_escucha()

    def _escucha_fallo(self, msg):
        self._agregar("Sistema", f"Escucha por nombre: {msg}")
        self._sincronizar_escucha()

    def _llamado_voz(self, texto):
        """Alguien dijo «SAGE ...» con la escucha activa (llega ya en el hilo de la interfaz)."""
        if self.grabando_tipo:
            return
        if energia_pendiente() and re.search(r"cancel|abort|no (?:te )?apag|no lo (?:hag|apag)|det[eé]n|alto\b|espera", texto.lower()):
            self._agregar("Niko", texto)
            self.interrumpir()   # corta la voz y cancela el apagado programado
            self._lanzar(Tarea(hablar, "Cancelado. No apago nada."), lambda x: None, lambda e: print(f"Fallo de voz: {e}"))
            return
        if self._estado != "idle" or esta_hablando():
            # Si está ocupada o hablando, SOLO escucha para interrumpir, ignorando comandos nuevos para evitar bucles.
            bajo = texto.lower()
            if any(w in bajo for w in ("para", "detente", "cancela", "cállate", "callate", "alto", "espera", "ya", "silencio")):
                self.interrumpir()
            return
        self._origen_comando = "sage"
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
        self._set_estado("idle", self._texto_idle())
        self.entrada.setFocus()
        self.escucha.reanudar()
        self._ultimo_intercambio = time.perf_counter()

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
        self._origen_comando = "texto"
        self._agregar("Niko", texto)
        self._pedir_respuesta(texto)

    def _pedir_respuesta(self, texto):
        if self._orden_mensaje_local(texto) or self._orden_ventana_local(texto) or self._orden_comentarista_local(texto):
            return
        self._ultimo_intercambio = time.perf_counter()
        self._bloquear(True)
        self.btn_mic.setEnabled(False)
        self.btn_pc.setEnabled(False)
        self._parcial = ""
        self._texto_pend = texto
        self._set_estado("pensando", "ANALIZANDO INTENCIÓN...")
        self._correr(
            Tarea(self._analizar, texto),
            ok=self._intencion_lista, fallo=self._respuesta_error,
        )

    def _analizar(self, texto):
        """(En un hilo) intención + telemetría de procesos. PowerShell tarda ~1 s y antes congelaba la ventana."""
        intencion = self.cerebro.analizar_intencion(texto)
        extra, aviso = "", ""
        if intencion.get("ver_procesos", False):
            try:
                objetivo = RE_SEGURO.sub('', intencion.get("objetivo_proceso", "")).replace(" ", "").strip()  # "geometry dash" -> GeometryDash
                cols = "Select-Object ProcessName, MainWindowTitle | ConvertTo-Csv -NoTypeInformation"
                if objetivo:
                    info = powershell_csv(f"Get-Process *{objetivo}* -ErrorAction SilentlyContinue | {cols}")
                    if info:
                        extra = f"\n\n[SISTEMA: El proceso '{objetivo}' SI FUE DETECTADO en la RAM]:\n{info}"
                    else:
                        extra = f"\n\n[SISTEMA: El proceso '{objetivo}' NO ESTÁ EJECUTÁNDOSE.]"
                    aviso = f"⚙️ Rastreo específico de '{objetivo}' completado."
                else:
                    info = powershell_csv("Get-Process | Where-Object {$_.MainWindowTitle} | " + cols)
                    extra = f"\n\n[DATOS DE TELEMETRÍA - TODOS LOS PROCESOS ACTIVOS]:\n{info}"
                    aviso = "⚙️ Escaneo de subprocesos general completado."
            except Exception as e:
                aviso = f"⚠ Fallo de telemetría de Windows: {e}"
        # Otro dispositivo registrado (celular Android por Wi-Fi): «mira mi celular», «sácame una captura del celular»...
        try:
            disp = dispositivos.mencionado(texto)
        except Exception:
            disp = None
        if disp:
            intencion = dict(intencion)
            intencion["ver_pantalla"] = False   # se mira el dispositivo, no el monitor de la PC
            try:
                img, ruta = dispositivos.capturar(disp)
                ruta = dispositivos.abrir(img, ruta) or ruta   # abre la captura en la PC para que la veas
                intencion["_imagen_dispositivo"] = img
                aviso = f"📱 Captura de «{disp}» tomada por Wi-Fi" + (f" y guardada en {ruta}" if ruta else "") + "."
                extra += (f"\n\n[SISTEMA: Te adjunto la captura de pantalla de «{disp}» (dispositivo Android de Niko, tomada ahora mismo por Wi-Fi)"
                          + (f", guardada en {ruta}" if ruta else "") + ". Es la pantalla de ESE dispositivo, no la de la PC. Descríbela / responde sobre ella; "
                          "no puedes tocar ni escribir en él, solo verlo.]")
            except Exception as e:
                aviso = f"⚠ No pude ver «{disp}»: {e}"
                extra += (f"\n\n[SISTEMA: Intenté capturar «{disp}» y FALLÓ: {e} Díselo a Niko con honestidad y explícale en una frase "
                          "qué debe revisar; no inventes lo que habría en su pantalla.]")
        return intencion, extra, aviso

    def _intencion_lista(self, res):
        intencion, extra, aviso = res
        self._ejecutar_con_intencion(intencion, self._texto_pend, extra, aviso)

    def _ejecutar_con_intencion(self, intencion, texto, extra="", aviso=""):
        imagen_a_enviar = intencion.get("_imagen_dispositivo")   # captura de otro dispositivo (si se pidió)
        texto_enriquecido = texto + extra
        if aviso:
            self._agregar("Sistema", aviso)

        if intencion.get("ver_pantalla", False) and imagen_a_enviar is None:
            self.hide()
            QApplication.processEvents()
            time.sleep(0.15)
            try:
                imagen_a_enviar = ojos.capturar()
                if imagen_a_enviar is None:
                    raise RuntimeError("no se pudo capturar la pantalla")
                self._agregar("Sistema", "📸 Escáner óptico autorizado y ejecutado.")
            except Exception as e:
                self._agregar("Sistema", f"⚠ Fallo de captura óptica: {e}")
            finally:
                if not self._segundo_plano: self.show()

        self._set_estado("pensando", "CALCULANDO...")
        self._burbuja_sage = self.chat.agregar("SAGE", esperando=True)

        self._correr(
            TareaStream(self.cerebro.procesar_stream, texto_enriquecido, imagen_a_enviar),
            trozo=self._trozo, ok=self._respuesta_ok, fallo=self._respuesta_error,
        )

    def closeEvent(self, ev):
        if not self._salir and getattr(self, "_bandeja", None) is not None and not QApplication.instance().isSavingSession():
            ev.ignore()          # la X (o alt+F4) solo cierra la ventana: SAGE sigue activa en segundo plano
            self.segundo_plano()
            return
        # --- salida real: se libera todo y el PROCESO TERMINA (no se queda vivo en segundo plano) ---
        self._salir = True
        _salida_forzosa(3.5)
        self._cerrar_recursos()
        super().closeEvent(ev)
        QTimer.singleShot(0, QApplication.quit)


def main():
    if sys.platform == "win32":
        try:  # sin esto Windows agrupa la ventana bajo python.exe y muestra su icono en la barra de tareas
            import ctypes
            ctypes.windll.shell32.SetCurrentProcessExplicitAppUserModelID("nexus.sage.asistente")
        except Exception:
            pass
    app = QApplication(sys.argv)
    app.setQuitOnLastWindowClosed(False)   # cerrar la ventana no apaga SAGE: sigue en la bandeja
    if os.path.exists(RUTA_ICONO):
        app.setWindowIcon(QIcon(RUTA_ICONO))
    app.setStyleSheet(ESTILO)
    try: cerebro = Cerebro()
    except Exception as e:
        QMessageBox.critical(None, "Fallo Crítico de SAGE", str(e))
        return 1
    ventana = Ventana(cerebro)
    if os.path.exists(RUTA_ICONO):
        ventana.setWindowIcon(QIcon(RUTA_ICONO))
    ventana.showMaximized()   # SAGE arranca con la ventana maximizada
    codigo = app.exec()
    if getattr(ventana, "_salir", False):
        _terminar_ya(codigo)   # apagado de verdad: sin esperar a ningún hilo de fondo
    return codigo


if __name__ == "__main__":
    sys.exit(main())