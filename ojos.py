"""Ojos de SAGE: captura de pantalla y detección de cambios / estabilidad en tiempo real.

Se usa para que SAGE sepa cuándo una página terminó de cargar (la pantalla deja de cambiar)
y para confirmar que una acción (click, escritura...) realmente tuvo efecto.
"""
import time

import numpy as np

_ANCHO, _ALTO = 128, 72      # miniatura con la que se compara (rápida y tolerante al ruido)
_DELTA_PIXEL = 20            # cuánto debe variar un píxel (0-255) para contarse como "cambiado"
UMBRAL_ESTABLE = 0.003       # fracción de píxeles cambiados por debajo de la cual la pantalla está "quieta"
UMBRAL_CAMBIO = 0.010        # fracción mínima para considerar que una acción cambió la pantalla


def capturar():
    """Captura la pantalla principal como imagen PIL (o None si falla)."""
    try:
        from PIL import ImageGrab
        return ImageGrab.grab()
    except Exception as e:
        print(f"[Ojos] Fallo de captura: {e}")
        return None


def huella(img):
    """Miniatura en escala de grises para comparar pantallas barato."""
    if img is None:
        return None
    if isinstance(img, np.ndarray):
        return img
    try:
        return np.asarray(img.convert("L").resize((_ANCHO, _ALTO)), dtype=np.int16)
    except Exception:
        return None


def diferencia(a, b):
    """Fracción (0..1) de la pantalla que cambió entre dos capturas."""
    ha, hb = huella(a), huella(b)
    if ha is None or hb is None or ha.shape != hb.shape:
        return 0.0
    return float(np.mean(np.abs(ha - hb) > _DELTA_PIXEL))


def cambio(antes, despues, umbral=UMBRAL_CAMBIO):
    return diferencia(antes, despues) > umbral


def esperar_estable(timeout=20.0, intervalo=0.5, estables=3, minimo=1.0,
                    requerir_cambio=False, espera_sin_cambio=4.0, umbral=UMBRAL_ESTABLE):
    """Bloquea hasta que la pantalla deja de cambiar (p. ej. una página terminó de cargar).

    - estables: cuántas comparaciones seguidas deben salir "quietas" (estables * intervalo = calma mínima).
    - requerir_cambio: tras abrir algo, espera a VER que la pantalla cambió y luego se calmó;
      si nunca cambia, acepta la calma pasados `espera_sin_cambio` segundos.
    Devuelve (estable: bool, segundos_esperados: float).
    """
    t0 = time.perf_counter()
    prev = huella(capturar())
    if prev is None:
        time.sleep(minimo)
        return True, time.perf_counter() - t0

    vio_cambio = False
    calma = 0
    while True:
        time.sleep(intervalo)
        act = huella(capturar())
        if act is not None:
            if diferencia(prev, act) > umbral:
                vio_cambio = True
                calma = 0
            else:
                calma += 1
            prev = act
        else:
            calma += 1

        t = time.perf_counter() - t0
        if calma >= estables and t >= minimo:
            if vio_cambio or not requerir_cambio or t >= espera_sin_cambio:
                return True, t
        if t >= timeout:
            return False, t
