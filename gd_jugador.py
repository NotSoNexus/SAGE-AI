"""Jugador de reflejos de Geometry Dash: mira la pantalla a 60 FPS SIN usar el LLM (demasiado lento) y aprende entre intentos.

Visión en vivo:
- La captura SOLO existe mientras se juega (dentro de GDJugador.jugar): fuera de [JUGAR] SAGE no graba la pantalla.
- Motor de captura, por orden: dxcam (DXGI, GPU, 60+ FPS reales; `pip install dxcam`) > mss (`pip install mss`) > PIL (lento, ~20 FPS).
- Solo se captura una franja delante del cubo y el bucle se sincroniza con la pantalla (60 Hz). Mide sus FPS reales y los muestra en «SAGE ve en vivo».

Cómo juega:
- Calibra buscando el cubo por su color (verde lima por defecto; con otro icono: SAGE_GD_COLOR=r,g,b en .env). Su tamaño da la unidad «bloque».
- Cada fotograma busca píxeles OSCUROS (pinchos y bloques) cerca del suelo. Mide la velocidad real del scroll (sirve con portales de velocidad)
  y salta cuando el obstáculo está a punto de llegar (distancia de disparo escalada por la velocidad). Modo nave (F9 alterna cubo/nave).

Cómo aprende (Geometry Dash es determinista: el mismo nivel pide los mismos saltos en cada intento):
- Cada intento dura hasta que el cubo desaparece (muerte). Se guarda el tiempo vivido y CUÁNTOS SALTOS dio.
- Si el mejor intento murió tras N saltos, los sospechosos son los últimos (N-1, N y, con menos peso, N-2 y N-3): en cada intento nuevo SOLO se
  prueba un ajuste de disparo en uno o dos de ellos, y se conserva únicamente si el intento dura más (hill-climbing por salto).
- Lo aprendido se guarda en gd_aprendizaje.json para la próxima vez (compatible con los registros antiguos por tramos de tiempo).
- Se detiene con F8, al pasar SAGE_GD_MINUTOS (10) o si el cubo no vuelve a aparecer en 4 s (nivel completado, pausa o menú).

Ajustes en .env (opcionales): SAGE_GD_FPS=60, SAGE_GD_VISTA_FPS=30, SAGE_GD_TOQUE=0.07, SAGE_GD_OSCURO=55, SAGE_GD_COLOR=125,255,0
"""
import os
import sys
import json
import time
import random

import numpy as np

AQUI = os.path.dirname(os.path.abspath(__file__))
RUTA_APRENDIZAJE = os.path.join(AQUI, "gd_aprendizaje.json")


def _num(nombre, defecto, minimo, maximo, tipo=float):
    try:
        return max(minimo, min(maximo, tipo(os.getenv(nombre, defecto))))
    except Exception:
        return defecto


TRAMO = 0.4                                          # s por tramo de tiempo (registros antiguos)
DS = 2                                               # submuestreo del análisis (más rápido)
OSCURO = _num("SAGE_GD_OSCURO", 55, 0, 255, int)     # luminosidad (0-255) por debajo de la cual un píxel cuenta como obstáculo
FPS = _num("SAGE_GD_FPS", 60, 20, 144, int)          # fotogramas por segundo objetivo de la visión
VISTA_FPS = _num("SAGE_GD_VISTA_FPS", 30, 5, 60, int)  # fotogramas por segundo de la ventanita «SAGE ve en vivo»
TOQUE = _num("SAGE_GD_TOQUE", 0.07, 0.03, 0.3)       # segundos que se mantiene pulsado el espacio en cada salto
V1 = 10.39                                           # bloques por segundo a velocidad 1x del juego


def _color_jugador():
    try:
        r, g, b = (int(v) for v in os.getenv("SAGE_GD_COLOR", "125,255,0").split(","))
        return r, g, b
    except Exception:
        return 125, 255, 0


def _acotar(v, lo=-1.5, hi=1.5):
    return max(lo, min(hi, v))


class _Temporizador:
    """Pide a Windows un temporizador de 1 ms: sin esto time.sleep() tiene ~15 ms de grano y no se puede ir a 60 Hz."""
    def __enter__(self):
        if sys.platform == "win32":
            try:
                import ctypes
                ctypes.windll.winmm.timeBeginPeriod(1)
            except Exception:
                pass
        return self

    def __exit__(self, *_):
        if sys.platform == "win32":
            try:
                import ctypes
                ctypes.windll.winmm.timeEndPeriod(1)
            except Exception:
                pass


_CAM = None   # instancia de dxcam (una por proceso)
RUTA_CAPTURA = os.path.join(AQUI, "gd_captura.json")
RUTA_DEBUG = os.path.join(AQUI, "gd_debug.png")


def _motor_guardado():
    try:
        with open(RUTA_CAPTURA, encoding="utf-8") as f: return json.load(f).get("motor")
    except Exception:
        return None


def _guardar_motor(motor):
    try:
        with open(RUTA_CAPTURA, "w", encoding="utf-8") as f: json.dump({"motor": motor}, f)
    except Exception:
        pass


class _Pantalla:
    """Captura rápida de una región. Devuelve arrays RGB uint8 (alto, ancho, 3). None = la pantalla no cambió (solo dxcam).

    Prueba varios motores (dxcam > mss > PIL) y recuerda el que funcionó. SAGE_GD_CAPTURA=dxcam|mss|pil fuerza uno."""
    def __init__(self):
        self.cam = self.sct = None
        self.bgr = False        # True si el motor entrega los canales en orden BGR
        forzado = {"dxcam": "dxcam", "mss": "mss", "pil": "PIL"}.get(os.getenv("SAGE_GD_CAPTURA", "auto").strip().lower())
        orden = ["dxcam", "mss", "PIL"]
        pref = forzado or _motor_guardado()
        if pref in orden:
            orden.remove(pref); orden.insert(0, pref)
        self.motores = [m for m in orden if (not forzado or m == forzado) and self._abrir(m)] or ["PIL"]
        self.motor = self.motores[0]

    def _abrir(self, motor):
        global _CAM
        try:
            if motor == "dxcam":
                if sys.platform != "win32": return False
                if _CAM is None:
                    import dxcam
                    _CAM = dxcam.create(output_color="RGB")
                self.cam = _CAM
                return self.cam is not None
            if motor == "mss":
                import mss
                self.sct = mss.mss()
                return True
            return True
        except Exception:
            return False

    def siguiente(self):
        """Pasa al siguiente motor de captura; False si no quedan más."""
        i = self.motores.index(self.motor)
        if i + 1 >= len(self.motores): return False
        self.motor, self.bgr = self.motores[i + 1], False
        return True

    def tamano(self):
        if self.motor == "dxcam":
            return int(self.cam.width), int(self.cam.height)
        if self.motor == "mss":
            m = self.sct.monitors[1]
            return int(m["width"]), int(m["height"])
        from PIL import ImageGrab
        return ImageGrab.grab().size

    def grab(self, x0, y0, x1, y1):
        reg = (int(x0), int(y0), int(x1), int(y1))
        try:
            if self.motor == "dxcam":
                f = self.cam.grab(region=reg)   # dxcam espera al siguiente fotograma; None si la pantalla no cambió
            elif self.motor == "mss":
                m = self.sct.grab({"left": reg[0], "top": reg[1], "width": reg[2] - reg[0], "height": reg[3] - reg[1]})
                f = np.ascontiguousarray(np.asarray(m)[:, :, :3][:, :, ::-1])
            else:
                from PIL import ImageGrab
                f = np.asarray(ImageGrab.grab(bbox=reg).convert("RGB"))
        except Exception as e:
            print(f"[GD] la captura con {self.motor} falló: {e}")
            if self.siguiente(): return self.grab(*reg)
            raise
        if f is not None and self.bgr:
            f = np.ascontiguousarray(f[..., ::-1])
        return f


def _tecla_pulsada(vk):
    if sys.platform != "win32": return False
    try:
        import ctypes
        return bool(ctypes.windll.user32.GetAsyncKeyState(vk) & 0x8000)
    except Exception:
        return False


class Memoria:
    """Lo aprendido de un nivel: distancia base de salto y ajustes por salto (y, de registros antiguos, por tramo de tiempo)."""
    def __init__(self, nivel):
        self.nivel = nivel
        self.d0, self.mejor_t, self.mejor_n, self.intentos = 2.4, 0.0, None, 0
        self.tramo, self.saltos = {}, {}
        try:
            with open(RUTA_APRENDIZAJE, encoding="utf-8") as f:
                d = json.load(f).get(nivel, {})
            self.d0 = float(d.get("d0", 2.4))
            self.mejor_t = float(d.get("mejor_t", 0.0))
            self.intentos = int(d.get("intentos", 0))
            self.tramo = {int(k): float(v) for k, v in d.get("tramo", {}).items()}
            self.saltos = {int(k): float(v) for k, v in d.get("saltos", {}).items()}
            mn = d.get("mejor_n")
            self.mejor_n = int(mn) if mn is not None else None
        except Exception:
            pass
        if self.mejor_t <= 0.0 and self.mejor_n is None:
            self.mejor_n = 0                       # nivel nuevo: no hay nada que calibrar
        self.d_prueba, self.p_tramo, self.p_saltos, self.n = self.d0, dict(self.tramo), dict(self.saltos), 0

    def nuevo_intento(self):
        self.n = 0
        self.p_tramo, self.p_saltos = dict(self.tramo), dict(self.saltos)
        if self.intentos < 6 and self.mejor_t < 3.0:     # primeros intentos: busca una distancia base razonable
            self.d_prueba = random.uniform(1.6, 3.2)
            return
        self.d_prueba = self.d0
        if self.mejor_n is None:                         # registro antiguo sin recuento de saltos: explora por tiempo hasta calibrarlo
            b = int(self.mejor_t / TRAMO)
            for k in range(max(0, b - 3), b + 1):
                if random.random() < 0.6:
                    self.p_tramo[k] = _acotar(self.p_tramo.get(k, 0.0) + random.gauss(0, 0.45))
            return
        # Sospechosos: el último salto del mejor intento (N-1), el siguiente (N) y, con menos peso, N-2 y N-3
        # (un salto mal sincronizado suele dejar al cubo mal colocado para los siguientes).
        n = self.mejor_n
        sosp = [(n, 2), (max(0, n - 1), 3), (max(0, n - 2), 2), (max(0, n - 3), 1)]
        ks, ws = [k for k, _ in sosp], [w for _, w in sosp]
        elegidos = {random.choices(ks, ws)[0]}
        if random.random() < 0.4:                        # a veces dos a la vez (restricciones acopladas)
            elegidos.add(random.choices(ks, ws)[0])
        for k in elegidos:
            self.p_saltos[k] = _acotar(self.p_saltos.get(k, 0.0) + random.choice((-1, 1)) * random.uniform(0.15, 1.0))

    def distancia(self, t):
        """Distancia de disparo (bloques a velocidad 1x) para el PRÓXIMO salto."""
        return self.d_prueba + self.p_tramo.get(int(t / TRAMO), 0.0) + self.p_saltos.get(self.n, 0.0)

    def saltar(self):
        self.n += 1

    def terminar(self, t):
        """Devuelve True si este intento mejoró el récord (y entonces adopta sus ajustes)."""
        self.intentos += 1
        mejora = t > self.mejor_t + 0.05
        if mejora:
            self.mejor_t, self.mejor_n = t, self.n
            self.d0, self.tramo, self.saltos = self.d_prueba, dict(self.p_tramo), dict(self.p_saltos)
        elif self.mejor_n is None and abs(t - self.mejor_t) < 1.5:
            self.mejor_n = self.n                        # calibra el recuento de saltos del registro antiguo
        self._guardar()
        return mejora

    def _guardar(self):
        try:
            try:
                with open(RUTA_APRENDIZAJE, encoding="utf-8") as f: todo = json.load(f)
            except Exception:
                todo = {}
            reg = {"d0": self.d0, "mejor_t": self.mejor_t, "intentos": self.intentos,
                   "tramo": {str(k): round(v, 3) for k, v in self.tramo.items()},
                   "saltos": {str(k): round(v, 3) for k, v in self.saltos.items()}}
            if self.mejor_n is not None: reg["mejor_n"] = self.mejor_n
            todo[self.nivel] = reg
            with open(RUTA_APRENDIZAJE, "w", encoding="utf-8") as f: json.dump(todo, f, ensure_ascii=False, indent=1)
        except Exception as e:
            print(f"[GD] No pude guardar el aprendizaje: {e}")


class GDJugador:
    def __init__(self):
        self.color = _color_jugador()
        self.u = 0.0            # tamaño de un bloque en píxeles
        self.cx = 0.0           # x del cubo en pantalla
        self.base = 0.0         # y del suelo (parte baja del cubo apoyado)

    # ---------- detección ----------
    def _mascara(self, a):
        r, g, b = self.color
        a = a.astype(np.int16)
        return (np.abs(a[..., 0] - r) <= 45) & (np.abs(a[..., 1] - g) <= 45) & (np.abs(a[..., 2] - b) <= 55)

    def buscar_jugador(self, img):
        """(x0, y0, x1, y1, n_pixeles) del cubo en una captura completa, o None."""
        h, w = img.shape[:2]
        lo, hi = int(w * 0.08), int(w * 0.55)
        ys, xs = np.nonzero(self._mascara(img[:, lo:hi]))
        if ys.size < 120: return None
        xs = xs + lo
        x0, x1 = np.percentile(xs, [3, 97]); y0, y1 = np.percentile(ys, [3, 97])
        return float(x0), float(y0), float(x1), float(y1), int(ys.size)

    def hay_jugador(self, img):
        return self.buscar_jugador(img) is not None

    def calibrar(self, img):
        r = self.buscar_jugador(img)
        if not r: return False
        x0, y0, x1, y1, _ = r
        self.u = max(x1 - x0, y1 - y0) * 1.12
        self.cx, self.base = (x0 + x1) / 2, y1
        return self.u >= 12

    @staticmethod
    def _luminancia(trozo):
        """Luminosidad entera 0-255 (más rápida que en coma flotante)."""
        s = trozo.astype(np.uint16)
        return (s[..., 0] * 77 + s[..., 1] * 150 + s[..., 2] * 29) >> 8

    def analizar(self, banda, ox, oy, modo="cubo"):
        """banda: región capturada con origen (ox, oy) en pantalla. Devuelve dict con presente, base, cy, dist (en bloques) y huecos (nave)."""
        a = banda[::DS, ::DS]
        u = self.u / DS
        px = (self.cx - ox) / DS
        c0, c1 = max(0, int(px - 0.7 * u)), int(px + 0.7 * u)
        pm = self._mascara(a[:, c0:c1])
        presente = int(pm.sum()) >= 0.06 * u * u
        res = {"presente": presente, "base": None, "cy": None, "dist": None, "huecos": None}
        if not presente: return res
        filas = np.nonzero(pm.any(axis=1))[0]
        bottom, top = float(filas.max()), float(filas.min())
        res["base"], res["cy"] = bottom * DS + oy, (top + bottom) / 2 * DS + oy
        if modo == "cubo":
            ref = (self.base - oy) / DS                      # el suelo calibrado (más fiable que el cubo en el aire)
            r0, r1 = max(0, int(ref - 0.55 * u)), max(1, int(ref - 0.1 * u))
            ini = int(px + 0.8 * u)
            if ini < a.shape[1] and r1 > r0:
                col = (self._luminancia(a[r0:r1, ini:]) < OSCURO).mean(axis=0) > 0.45
                if col.any():
                    res["dist"] = (int(np.argmax(col)) + ini - px) / u
        else:  # nave: hueco libre en una franja delante del cubo
            s0, s1 = int(px + 2.0 * u), int(px + 2.7 * u)
            if s1 <= a.shape[1]:
                bloq = (self._luminancia(a[:, s0:s1]) < OSCURO).mean(axis=1) > 0.5
                libres, ini_run = [], None
                for i, b in enumerate(bloq):
                    if not b and ini_run is None: ini_run = i
                    if (b or i == len(bloq) - 1) and ini_run is not None:
                        fin = i if b else i + 1
                        if fin - ini_run >= 1.2 * u: libres.append(((ini_run + fin) / 2 * DS + oy))
                        ini_run = None
                res["huecos"] = libres
        return res

    def _preview(self, banda, ox, oy, r):
        """Lo que ve SAGE, reducido, con el cubo (cian) y el primer obstáculo (rojo) marcados."""
        p = banda[::3, ::3].copy()
        h, w = p.shape[:2]
        px = int((self.cx - ox) / 3)
        if 0 <= px < w - 2: p[:, px:px + 2] = (0, 243, 255)
        by = int((self.base - oy) / 3)
        if 0 <= by < h - 1: p[by:by + 1, :] = (0, 243, 255)
        if r.get("dist") is not None:
            xo = int((self.cx - ox + r["dist"] * self.u) / 3)
            if 0 <= xo < w - 3: p[:, xo:xo + 3] = (255, 0, 60)
        return p

    # ---------- bucle principal ----------
    def jugar(self, nivel, log, parar, minutos=None, vista=None):
        import pyautogui
        pyautogui.PAUSE = 0
        minutos = minutos if minutos is not None else float(os.getenv("SAGE_GD_MINUTOS", "10"))
        pant = _Pantalla()
        mem = Memoria(nivel)
        with _Temporizador():
            try:
                return self._partida(pyautogui, pant, mem, log, parar, minutos, vista)
            finally:
                try: pyautogui.keyUp("space", _pause=False)
                except Exception: pass

    @staticmethod
    def _res(motivo, mem, tiempos, fps=0.0):
        return {"motivo": motivo, "intentos": len(tiempos), "mejor": mem.mejor_t, "tiempos": tiempos, "fps": fps}

    def _partida(self, pyautogui, pant, mem, log, parar, minutos, vista):
        sw, sh = pant.tamano()
        log(f"👁 Visión en vivo ({pant.motor}, objetivo {FPS} FPS): buscando el cubo para calibrar...")
        if "dxcam" not in pant.motores:
            log("ℹ Sin dxcam la captura va más lenta que 60 FPS. Instálalo con: python -m pip install dxcam")

        t0 = t_motor = time.perf_counter()
        ok, diag = 0, False
        while time.perf_counter() - t0 < 35 and ok < 3:
            if parar(): return self._res("detenido por Niko", mem, [])
            img = pant.grab(0, 0, sw, sh)
            if img is not None:
                if self.calibrar(img):
                    ok += 1
                else:
                    ok = 0
                    if self.calibrar(img[..., ::-1]):        # el motor entrega BGR en vez de RGB
                        pant.bgr = not pant.bgr
                        log(f"🎨 {pant.motor} entrega los colores invertidos: lo corrijo.")
                        ok = 1
            if ok == 0 and time.perf_counter() - t_motor > 5.0:
                if img is not None:
                    media = float(img.mean())
                    desc = f"imagen {img.shape[1]}x{img.shape[0]}, brillo medio {media:.0f}/255" + (
                        " → pantalla NEGRA (¿juego a pantalla completa exclusiva u otro monitor?)" if media < 8 else "")
                    if not diag:
                        diag = True
                        try:
                            from PIL import Image
                            Image.fromarray(np.ascontiguousarray(img)).save(RUTA_DEBUG)
                            desc += " · guardé gd_debug.png con lo que ve SAGE"
                        except Exception:
                            pass
                else:
                    desc = "no entrega fotogramas"
                log(f"⚠ Con {pant.motor} no veo el cubo ({desc}).")
                if pant.siguiente():
                    log(f"🔄 Pruebo otro método de captura: {pant.motor}")
                    sw, sh = pant.tamano()
                    t_motor = time.perf_counter()
                else:
                    t_motor = float("inf")                    # no quedan métodos: sigo esperando sin repetir el aviso
            time.sleep(0.1)
        if ok < 3:
            return self._res("no encontré el cubo (mira gd_debug.png: ¿sale el juego? ¿no es verde lima? pon SAGE_GD_COLOR=r,g,b en .env)", mem, [])
        _guardar_motor(pant.motor)
        log(f"🎯 Calibrado con {pant.motor}: bloque ≈ {self.u:.0f}px. Aprendido de antes: {mem.intentos} intentos, récord {mem.mejor_t:.1f}s. F8 para parar, F9 cubo/nave.")

        bx0, bx1 = max(0, int(self.cx - 1.5 * self.u)), min(sw, int(self.cx + 9 * self.u))
        by0, by1 = max(0, int(self.base - 8 * self.u)), min(sh, int(self.base + 0.4 * self.u))
        modo, f9_antes = "cubo", False
        tiempos, t_fin = [], time.perf_counter() + minutos * 60
        mem.nuevo_intento()
        inicio = ultimo_visto = ultimo_salto = None
        soltar_en, mantenido, motivo = 0.0, False, ""
        ult_vista, periodo = 0.0, 1.0 / FPS
        proximo = time.perf_counter()
        cuenta, t_fps, fps, ms_an, mide = 0, proximo, 0.0, 0.0, 0
        dprev = tprev = None
        v_est = V1
        r = {"presente": False, "dist": None, "huecos": None}

        while True:
            ahora = time.perf_counter()
            if parar(): motivo = "detenido por Niko (F8)"; break
            if ahora > t_fin: motivo = f"tiempo máximo ({minutos:g} min)"; break
            f9 = _tecla_pulsada(0x78)
            if f9 and not f9_antes:
                modo = "nave" if modo == "cubo" else "cubo"
                log(f"🔁 Modo: {modo}")
            f9_antes = f9
            if soltar_en and ahora >= soltar_en:
                pyautogui.keyUp("space", _pause=False); soltar_en = 0.0

            banda = pant.grab(bx0, by0, bx1, by1)
            if banda is not None:
                ahora = time.perf_counter()
                ta = ahora
                r = self.analizar(banda, bx0, by0, modo)
                ms_an = 0.9 * ms_an + 0.1 * (time.perf_counter() - ta) * 1000

                cuenta += 1
                if ahora - t_fps >= 1.0:
                    fps, cuenta, t_fps, mide = cuenta / (ahora - t_fps), 0, ahora, mide + 1
                    if mide == 3:
                        log(f"📺 Visión en vivo: {fps:.0f} FPS reales ({pant.motor}), análisis {ms_an:.1f} ms por fotograma.")
                    elif mide > 3 and fps < 0.75 * FPS and mide % 10 == 0:
                        log(f"⚠ La visión va a {fps:.0f} FPS (objetivo {FPS}). Cierra programas pesados o baja los gráficos del juego.")

                if vista and ahora - ult_vista >= 1.0 / VISTA_FPS:
                    ult_vista = ahora
                    estado = (f" · obstáculo a {r['dist']:.1f} bloques" if r.get("dist") is not None
                              else (" · sin cubo" if not r["presente"] else " · vía libre"))
                    vista(self._preview(banda, bx0, by0, r),
                          f"{fps:.0f} FPS · {modo} · intento {mem.intentos + 1} · récord {mem.mejor_t:.1f}s" + estado)

                if r["presente"]:
                    if inicio is None:
                        inicio = ahora; mem.nuevo_intento(); v_est = V1; dprev = tprev = None
                    ultimo_visto = ahora
                    t = ahora - inicio
                    if modo == "cubo":
                        dist = r["dist"]
                        if dist is not None and dprev is not None and tprev is not None:   # velocidad real del scroll (portales de velocidad)
                            dt = ahora - tprev
                            if 0.004 < dt < 0.08:
                                inst = (dprev - dist) / dt
                                if 5.0 < inst < 25.0:
                                    v_est = _acotar(0.92 * v_est + 0.08 * inst, 6.0, 22.0)
                        dprev, tprev = dist, ahora
                        estable = r["base"] >= self.base - 0.18 * self.u     # apoyado en el suelo
                        if (estable and dist is not None and dist <= mem.distancia(t) * (v_est / V1)
                                and (ultimo_salto is None or ahora - ultimo_salto > 0.28)):
                            pyautogui.keyDown("space", _pause=False)
                            ultimo_salto, soltar_en = ahora, ahora + TOQUE
                            mem.saltar()
                    elif r["huecos"]:
                        objetivo = min(r["huecos"], key=lambda y: abs(y - r["cy"]))
                        if r["cy"] > objetivo + 0.15 * self.u and not mantenido:
                            pyautogui.keyDown("space", _pause=False); mantenido = True
                        elif r["cy"] < objetivo - 0.15 * self.u and mantenido:
                            pyautogui.keyUp("space", _pause=False); mantenido = False
            else:
                time.sleep(0.002)    # pantalla quieta: no hay fotograma nuevo

            # Vigilancia (también cuando la pantalla está quieta)
            ahora = time.perf_counter()
            if inicio is not None and ahora - ultimo_visto > 0.35:   # el cubo desapareció: murió
                if mantenido: pyautogui.keyUp("space", _pause=False); mantenido = False
                dur = ultimo_visto - inicio
                if dur >= 0.6:
                    saltos = mem.n
                    tiempos.append(dur)
                    mejora = mem.terminar(dur)
                    log(f"💥 Intento {mem.intentos}: {dur:.1f}s, {saltos} saltos" + (" ⭐ ¡nuevo récord!" if mejora else f" (récord {mem.mejor_t:.1f}s)"))
                inicio = None
            elif inicio is None and ultimo_visto is not None and ahora - ultimo_visto > 4.0:
                motivo = "el cubo no volvió a aparecer (nivel completado, pausa o menú)"; break
            elif inicio is None and ultimo_visto is None and ahora - t0 > 60:
                motivo = "no apareció el cubo"; break

            if pant.motor != "dxcam":     # dxcam ya espera al siguiente fotograma; con mss/PIL marcamos nosotros el ritmo
                proximo += periodo
                resto = proximo - time.perf_counter()
                if resto > 0: time.sleep(resto)
                else: proximo = time.perf_counter()

        return self._res(motivo, mem, tiempos, fps)
