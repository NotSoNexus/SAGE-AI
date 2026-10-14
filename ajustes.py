"""Configuración de SAGE: colores, animación, voz, ratón, felicidad... Se guarda en sage_ajustes.json y se aplica en vivo.

- Gestor(app_module, ventana).aplicar()   -> vuelca los ajustes sobre las constantes de app.py
- Gestor.set_valor(clave, valor)          -> cambia un ajuste (lo usa la directiva [AJUSTE: clave | valor] por voz)
- Gestor.abrir_panel()                    -> ventana de configuración (botón ⚙, Ctrl+, o bandeja)
"""
import os
import json
from PySide6.QtCore import Qt
from PySide6.QtGui import QColor
from PySide6.QtWidgets import (QDialog, QVBoxLayout, QHBoxLayout, QTabWidget, QWidget, QLabel, QPushButton, QSlider,
                               QComboBox, QCheckBox, QColorDialog, QGridLayout, QApplication)

AQUI = os.path.dirname(os.path.abspath(__file__))
RUTA = os.path.join(AQUI, "sage_ajustes.json")

ESTADOS = ("idle", "escuchando", "pensando", "respondiendo", "error")
ETIQ_COLOR = {"idle": "En reposo / acento", "escuchando": "Escuchando", "pensando": "Pensando", "respondiendo": "Respondiendo",
              "error": "Error", "oro": "Llamado «SAGE» / destellos", "niko": "Tus mensajes", "sage": "Mensajes de SAGE", "sistema": "Mensajes del sistema"}
VOCES = ("es-MX-DaliaNeural", "es-MX-JorgeNeural", "es-ES-ElviraNeural", "es-ES-AlvaroNeural", "es-AR-ElenaNeural",
         "es-CO-SalomeNeural", "es-US-PalomaNeural", "es-CL-CatalinaNeural", "es-PE-CamilaNeural")

TEMAS = {
    "clasico": {},
    "frontiers": dict(idle="#19e3ff", escuchando="#7bffc4", pensando="#ff9a3c", respondiendo="#ffffff", error="#8b0000", oro="#ffd166"),
    "neon rosa": dict(idle="#ff2bd6", escuchando="#00f3ff", pensando="#ffe600", respondiendo="#ff7a00", error="#8b0000", oro="#ff9ad5"),
    "oceano": dict(idle="#00d4ff", escuchando="#7affc8", pensando="#3b82ff", respondiendo="#00ffa6", error="#8b0000", oro="#b6f0ff"),
    "atardecer": dict(idle="#ff8a3d", escuchando="#ffd23d", pensando="#ff3d6e", respondiendo="#ff5e3d", error="#7a0019", oro="#ffe29a"),
    "monocromo": dict(idle="#e6e6e6", escuchando="#ffffff", pensando="#9a9a9a", respondiendo="#cfcfcf", error="#555555", oro="#ffffff"),
}
NOMBRES_COLOR = {"rojo": "#ff0033", "azul": "#2979ff", "verde": "#39ff14", "rosa": "#ff2bd6", "morado": "#a020f0", "violeta": "#8a2be2",
                 "naranja": "#ff8a00", "amarillo": "#ffe600", "cian": "#00f3ff", "celeste": "#66ccff", "turquesa": "#00e5c8",
                 "blanco": "#ffffff", "negro": "#111111", "gris": "#9a9a9a", "dorado": "#ffcc00", "magenta": "#ff00ff", "lila": "#c8a2ff"}

# clave -> (mínimo, máximo) de los ajustes numéricos
RANGOS = {"anim_vel": (0.2, 3.0), "anim_amp": (0.3, 1.5), "fps": (15, 60), "voz_vel": (-50, 100),
          "mouse_dur": (0.02, 0.5), "mouse_vel": (1500, 20000), "fel_base": (0, 100), "fel_vida": (0.5, 72)}


def _hex(c):
    return QColor(c).name()


def _color(v):
    v = str(v).strip().lower()
    c = QColor(NOMBRES_COLOR.get(v, v))
    return c.name() if c.isValid() else None


class Gestor:
    def __init__(self, mod, ventana=None):
        self.mod, self.ventana, self._dlg = mod, ventana, None
        if not hasattr(mod, "_AJ_BASE"):   # copia de los valores originales de app.py (para «restablecer» y como base de los multiplicadores)
            mod._AJ_BASE = {
                "colores": {**{k: _hex(mod.COLORES[k]) for k in ESTADOS}, "oro": _hex(mod.ORO)},
                "autor": {k: _hex(mod.COLOR_AUTOR[k]) for k in ("niko", "sage", "sistema")},
                "vel": {n: dict(getattr(mod, n)) for n in ("VEL_FONDO", "VEL_ROT", "VEL_PULSO", "AMP_BASE")},
                "estilo": mod.ESTILO, "fps": round(1000 / mod.FPS_MS), "mouse_dur": mod.DURACION_MOUSE,
                "mouse_vel": mod.VELOCIDAD_MOUSE, "verificar": bool(mod.VERIFICAR_SIEMPRE),
                "voz": os.getenv("SAGE_VOZ", "es-MX-DaliaNeural"),
                "voz_vel": int(str(os.getenv("SAGE_VOZ_VELOCIDAD", "+25%")).replace("%", "").replace("+", "") or 25),
            }
        b = mod._AJ_BASE
        self.defaults = {"colores": dict(b["colores"]), "autor": dict(b["autor"]), "anim_vel": 1.0, "anim_amp": 1.0, "fps": b["fps"],
                         "voz": b["voz"], "voz_vel": b["voz_vel"], "mouse_dur": b["mouse_dur"], "mouse_vel": b["mouse_vel"],
                         "verificar": b["verificar"], "fel_base": 50.0, "fel_vida": 6.0, "fijar_hud": False}
        self.cfg = json.loads(json.dumps(self.defaults))
        try:
            with open(RUTA, encoding="utf-8") as f:
                d = json.load(f)
            for k, v in d.items():
                if isinstance(v, dict) and isinstance(self.cfg.get(k), dict): self.cfg[k].update(v)
                elif k in self.cfg: self.cfg[k] = v
        except Exception:
            pass

    # ---------- guardar / aplicar ----------
    def guardar(self):
        try:
            with open(RUTA, "w", encoding="utf-8") as f:
                json.dump(self.cfg, f, ensure_ascii=False, indent=1)
        except Exception as e:
            print(f"[Ajustes] No pude guardar: {e}")

    def aplicar(self):
        m, c = self.mod, self.cfg
        for k, v in c["colores"].items():
            if k == "oro": m.ORO = QColor(v)
            elif k in m.COLORES: m.COLORES[k] = QColor(v)
        for k, v in c["autor"].items():
            m.COLOR_AUTOR[k] = QColor(v)
        m.COLOR_AUTOR["nexus"] = QColor(c["autor"]["niko"])
        m.COLORES["sage"] = QColor(c["autor"]["sage"])   # app.py lo usa en algunos rótulos
        for n, mult in (("VEL_FONDO", c["anim_vel"]), ("VEL_ROT", c["anim_vel"]), ("VEL_PULSO", c["anim_vel"]), ("AMP_BASE", c["anim_amp"])):
            d, base = getattr(m, n), m._AJ_BASE["vel"][n]
            for k in d: d[k] = base[k] * mult
        m.FPS_MS = max(10, int(1000 / max(1, c["fps"])))
        m.DURACION_MOUSE, m.VELOCIDAD_MOUSE, m.VERIFICAR_SIEMPRE = float(c["mouse_dur"]), float(c["mouse_vel"]), bool(c["verificar"])
        os.environ["SAGE_VOZ"] = c["voz"]
        os.environ["SAGE_VOZ_VELOCIDAD"] = f"{int(c['voz_vel']):+d}%"
        try:
            import felicidad
            felicidad.BASE, felicidad.VIDA_MEDIA_H = float(c["fel_base"]), float(c["fel_vida"])
        except Exception:
            pass
        acento, foco = c["colores"]["idle"], c["colores"]["escuchando"]
        m.ESTILO = m._AJ_BASE["estilo"].replace("#39ff14", "@A@").replace("#00f3ff", "@F@").replace("@A@", acento).replace("@F@", foco)
        app = QApplication.instance()
        if app is not None and self.ventana is not None:
            app.setStyleSheet(m.ESTILO)
        v = self.ventana
        if v is not None:
            try:
                v._reloj.setInterval(m.FPS_MS)
                v.btn_mic.base, v.btn_pc.base, v.btn_enviar.base = QColor(foco), QColor(foco), QColor(acento)
                v._sincronizar_escucha()
                if v.chk_top.isChecked() != bool(c["fijar_hud"]): v.chk_top.setChecked(bool(c["fijar_hud"]))
                for b in (v.btn_mic, v.btn_pc, v.btn_enviar, v.btn_ajustes): b.update()
                v.btn_ajustes.base = QColor(m.ORO)
                v._color_estado = None   # fuerza a repintar la etiqueta de estado y el borde con el color nuevo
                v._actualizar_estado_visual()
                for w in QApplication.instance().allWidgets():
                    if hasattr(w, "recolorear"): w.recolorear()   # mensajes ya escritos

            except Exception as e:
                print(f"[Ajustes] {e}")

    # ---------- cambios ----------
    def poner(self, clave, valor):
        """Cambia un ajuste con validación. clave: color_<estado|oro|niko|sage|sistema>, tema, o el nombre de un ajuste. Devuelve (ok, msg)."""
        c, k = self.cfg, str(clave).strip().lower().replace(" ", "_")
        try:
            if k.startswith("color_") and k[6:] in ETIQ_COLOR:
                h = _color(valor)
                if not h: return False, f"no reconozco el color «{valor}»"
                destino = "autor" if k[6:] in ("niko", "sage", "sistema") else "colores"
                c[destino][k[6:]] = h
            elif k == "tema":
                t = str(valor).strip().lower().replace("é", "e").replace("á", "a")
                if t not in TEMAS: return False, f"tema desconocido (hay: {', '.join(TEMAS)})"
                c["colores"] = {**self.defaults["colores"], **TEMAS[t]}
                cc = c["colores"]
                c["autor"] = dict(self.defaults["autor"]) if t == "clasico" else {"niko": cc["escuchando"], "sage": cc["pensando"], "sistema": cc["idle"]}
            elif k in RANGOS:
                lo, hi = RANGOS[k]
                c[k] = max(lo, min(hi, float(str(valor).replace("%", "").replace(",", "."))))
                if k in ("fps", "voz_vel", "mouse_vel"): c[k] = int(c[k])
            elif k == "voz":
                if str(valor) not in VOCES and not str(valor).startswith("es-"): return False, "voz no válida (ej. es-MX-DaliaNeural)"
                c["voz"] = str(valor)
            elif k in ("verificar", "fijar_hud"):
                c[k] = str(valor).strip().lower() in ("1", "true", "si", "sí", "on", "activar", "activado", "siempre")
            else:
                return False, f"ajuste desconocido «{clave}»"
        except ValueError:
            return False, f"valor no válido para {clave}: «{valor}»"
        self.guardar(); self.aplicar()
        return True, f"ajuste {k} = {valor}"

    def set_valor(self, arg):
        """Para la directiva [AJUSTE: clave | valor]. «panel» abre la ventana de configuración."""
        p = [x.strip() for x in str(arg).split("|", 1)]
        if p[0].lower() in ("panel", "abrir", "abrir panel", "ajustes"):
            self.abrir_panel(); return True, "abrí el panel de configuración"
        if p[0].lower() in ("restablecer", "reset", "defecto"):
            self.restablecer(); return True, "restablecí todos los ajustes"
        if len(p) < 2: return False, "AJUSTE mal formado: usa clave | valor"
        return self.poner(p[0], p[1])

    def restablecer(self):
        self.cfg = json.loads(json.dumps(self.defaults))
        self.guardar(); self.aplicar()
        if self._dlg is not None: self._dlg.refrescar()

    # ---------- panel ----------
    def abrir_panel(self):
        if self._dlg is None or not self._dlg.isVisible():
            self._dlg = PanelAjustes(self)
        self._dlg.show(); self._dlg.raise_(); self._dlg.activateWindow()


class PanelAjustes(QDialog):
    def __init__(self, g):
        super().__init__(g.ventana)
        self.g = g
        self.setWindowTitle("SAGE · Configuración")
        self.setMinimumWidth(460)
        self._swatches, self._ctrl = {}, {}
        lay = QVBoxLayout(self)
        tabs = QTabWidget(); lay.addWidget(tabs)
        tabs.addTab(self._tab_colores(), "Colores")
        tabs.addTab(self._tab_animacion(), "Animación")
        tabs.addTab(self._tab_voz(), "Voz")
        tabs.addTab(self._tab_comportamiento(), "Comportamiento")
        fila = QHBoxLayout()
        b1, b2 = QPushButton("Restablecer todo"), QPushButton("Cerrar")
        b1.clicked.connect(g.restablecer); b2.clicked.connect(self.close)
        fila.addWidget(b1); fila.addStretch(1); fila.addWidget(b2); lay.addLayout(fila)

    # --- helpers ---
    def _slider(self, grid, fila, texto, clave, factor=1, sufijo="", tras=None):
        lo, hi = RANGOS[clave]
        s = QSlider(Qt.Orientation.Horizontal); s.setRange(int(lo * factor), int(hi * factor))
        lbl = QLabel()
        def actualizar(v):
            lbl.setText(f"{v / factor:g}{sufijo}")
        def cambio(v):
            actualizar(v)
            val = v / factor
            self.g.cfg[clave] = int(val) if factor == 1 else val
            self.g.guardar(); self.g.aplicar()
        s.setValue(int(self.g.cfg[clave] * factor)); actualizar(s.value()); s.valueChanged.connect(cambio)
        grid.addWidget(QLabel(texto), fila, 0); grid.addWidget(s, fila, 1); grid.addWidget(lbl, fila, 2)
        self._ctrl[clave] = (s, factor, actualizar)

    def _check(self, grid, fila, texto, clave):
        c = QCheckBox(texto); c.setChecked(bool(self.g.cfg[clave]))
        c.toggled.connect(lambda v: (self.g.cfg.__setitem__(clave, v), self.g.guardar(), self.g.aplicar()))
        grid.addWidget(c, fila, 0, 1, 3); self._ctrl[clave] = (c, None, None)

    def _tab_colores(self):
        w = QWidget(); lay = QVBoxLayout(w)
        fila = QHBoxLayout(); fila.addWidget(QLabel("Tema:"))
        for t in TEMAS:
            b = QPushButton(t.capitalize()); b.clicked.connect(lambda _=False, t=t: (self.g.poner("tema", t), self.refrescar()))
            fila.addWidget(b)
        lay.addLayout(fila)
        grid = QGridLayout()
        for i, k in enumerate(ETIQ_COLOR):
            b = QPushButton(); b.setFixedSize(70, 26); b.clicked.connect(lambda _=False, k=k: self._elegir(k))
            self._swatches[k] = b
            grid.addWidget(QLabel(ETIQ_COLOR[k]), i, 0); grid.addWidget(b, i, 1)
        lay.addLayout(grid); lay.addStretch(1)
        self._pintar()
        return w

    def _tab_animacion(self):
        w = QWidget(); grid = QGridLayout(w)
        self._slider(grid, 0, "Velocidad de animación", "anim_vel", 10, "×")
        self._slider(grid, 1, "Intensidad de las ondas", "anim_amp", 10, "×")
        self._slider(grid, 2, "Fotogramas por segundo", "fps", 1, " fps")
        grid.setRowStretch(3, 1)
        return w

    def _tab_voz(self):
        w = QWidget(); grid = QGridLayout(w)
        cb = QComboBox(); cb.addItems(VOCES)
        if self.g.cfg["voz"] not in VOCES: cb.addItem(self.g.cfg["voz"])
        cb.setCurrentText(self.g.cfg["voz"])
        cb.currentTextChanged.connect(lambda t: (self.g.cfg.__setitem__("voz", t), self.g.guardar(), self.g.aplicar()))
        grid.addWidget(QLabel("Voz"), 0, 0); grid.addWidget(cb, 0, 1, 1, 2); self._ctrl["voz"] = (cb, None, None)
        self._slider(grid, 1, "Velocidad al hablar", "voz_vel", 1, " %")
        prueba = QPushButton("Probar voz")
        def probar():
            from boca import hablar, callar
            callar(); hablar("Hola Niko, así suena mi voz con esta configuración.")
        prueba.clicked.connect(probar); grid.addWidget(prueba, 2, 0, 1, 3); grid.setRowStretch(3, 1)
        return w

    def _tab_comportamiento(self):
        w = QWidget(); grid = QGridLayout(w)
        self._slider(grid, 0, "Velocidad del mouse (px/s)", "mouse_vel", 1)
        self._slider(grid, 1, "Duración máx. por movimiento (s)", "mouse_dur", 100, " s")
        self._slider(grid, 2, "Felicidad base", "fel_base", 1)
        self._slider(grid, 3, "Vida media de la felicidad (h)", "fel_vida", 10, " h")
        self._check(grid, 4, "Verificar siempre con la pantalla tras actuar (más lento, más seguro)", "verificar")
        self._check(grid, 5, "Mantener la HUD siempre encima", "fijar_hud")
        grid.setRowStretch(6, 1)
        return w

    # --- colores ---
    def _valor_color(self, k):
        return self.g.cfg["autor" if k in ("niko", "sage", "sistema") else "colores"][k]

    def _pintar(self):
        for k, b in self._swatches.items():
            b.setStyleSheet(f"background-color: {self._valor_color(k)}; border: 2px solid #ffffff;")

    def _elegir(self, k):
        c = QColorDialog.getColor(QColor(self._valor_color(k)), self, ETIQ_COLOR[k])
        if c.isValid():
            self.g.poner(f"color_{k}", c.name()); self._pintar()

    def refrescar(self):
        """Vuelve a mostrar los valores actuales (tras un tema o «restablecer»)."""
        self._pintar()
        for k, (w, f, act) in self._ctrl.items():
            w.blockSignals(True)
            v = self.g.cfg[k]
            if isinstance(w, QSlider): w.setValue(int(v * f)); act(w.value())
            elif isinstance(w, QCheckBox): w.setChecked(bool(v))
            elif isinstance(w, QComboBox): w.setCurrentText(str(v))
            w.blockSignals(False)
