"""Sistema de recompensas de SAGE: un nivel de FELICIDAD (0-100) que sube cuando logra cosas y se enfría con el tiempo.

- recompensar(cantidad, motivo): suma felicidad con rendimientos decrecientes (cuanto más feliz, más cuesta subir).
- Con el tiempo la felicidad vuelve poco a poco a su nivel base (vida media ~6 h): hay que seguir ganándosela.
- Se guarda en sage_felicidad.json y sobrevive a reinicios.
- contexto(): una línea que cerebro.py añade al prompt para que el ánimo de SAGE se note (sutilmente) en su tono.

Ajustes opcionales en .env: SAGE_FELICIDAD_BASE=50, SAGE_FELICIDAD_VIDA_MEDIA_H=6
"""
import os
import json
import time
import threading

AQUI = os.path.dirname(os.path.abspath(__file__))
RUTA = os.path.join(AQUI, "sage_felicidad.json")


def _num(nombre, defecto, minimo, maximo):
    try:
        return max(minimo, min(maximo, float(os.getenv(nombre, defecto))))
    except Exception:
        return defecto


BASE = _num("SAGE_FELICIDAD_BASE", 50.0, 0.0, 100.0)
VIDA_MEDIA_H = _num("SAGE_FELICIDAD_VIDA_MEDIA_H", 6.0, 0.1, 240.0)

# (umbral mínimo, estado, emoji)
_ESTADOS = (
    (85, "eufórica", "🤩"),
    (70, "muy feliz", "😄"),
    (55, "contenta", "😊"),
    (40, "tranquila", "🙂"),
    (25, "apagada", "😐"),
    (0, "desanimada", "😔"),
)


class Felicidad:
    def __init__(self, ruta=RUTA):
        self._ruta = ruta
        self._lock = threading.Lock()
        self.valor = BASE
        self.total_recompensas = 0
        self.ultimo_motivo = ""
        self._t = time.time()
        self._t_guardado = 0.0
        self._cargar()

    # ---------- persistencia ----------
    def _cargar(self):
        try:
            with open(self._ruta, encoding="utf-8") as f:
                d = json.load(f)
            self.valor = max(0.0, min(100.0, float(d.get("valor", BASE))))
            self.total_recompensas = int(d.get("total_recompensas", 0))
            self.ultimo_motivo = str(d.get("ultimo_motivo", ""))
            self._t = float(d.get("t", time.time()))
        except Exception:
            pass
        self._decaer()

    def _guardar(self, forzar=False):
        ahora = time.time()
        if not forzar and ahora - self._t_guardado < 3.0:
            return
        self._t_guardado = ahora
        try:
            with open(self._ruta, "w", encoding="utf-8") as f:
                json.dump({"valor": round(self.valor, 3), "total_recompensas": self.total_recompensas,
                           "ultimo_motivo": self.ultimo_motivo, "t": self._t}, f, ensure_ascii=False, indent=1)
        except Exception as e:
            print(f"[Felicidad] No pude guardar: {e}")

    def guardar(self):
        with self._lock:
            self._guardar(forzar=True)

    # ---------- dinámica ----------
    def _decaer(self):
        """La felicidad se enfría hacia su nivel base con el paso del tiempo (vida media configurable)."""
        ahora = time.time()
        horas = max(0.0, (ahora - self._t) / 3600.0)
        if horas > 0:
            self.valor = BASE + (self.valor - BASE) * (0.5 ** (horas / VIDA_MEDIA_H))
        self._t = ahora

    def recompensar(self, cantidad, motivo=""):
        """Suma felicidad (cantidad > 0). Devuelve lo que realmente subió (los rendimientos decrecientes la reducen cerca de 100)."""
        if cantidad <= 0:
            return 0.0
        with self._lock:
            self._decaer()
            antes = self.valor
            ganancia = cantidad * max(0.08, 1.15 - self.valor / 100.0)
            self.valor = min(100.0, self.valor + ganancia)
            self.total_recompensas += 1
            if motivo:
                self.ultimo_motivo = motivo
            self._guardar()
            return self.valor - antes

    # ---------- lectura ----------
    def nivel(self):
        with self._lock:
            self._decaer()
            return self.valor

    def estado(self):
        v = self.nivel()
        for umbral, nombre, emoji in _ESTADOS:
            if v >= umbral:
                return nombre, emoji
        return _ESTADOS[-1][1], _ESTADOS[-1][2]

    def resumen(self):
        """Texto corto para mostrar: «😊 63/100 (contenta)»."""
        nombre, emoji = self.estado()
        return f"{emoji} {self.valor:.0f}/100 ({nombre})"

    def contexto(self):
        """Línea para el prompt de SAGE: su ánimo actual, para que se note sutilmente en el tono."""
        nombre, _ = self.estado()
        razon = f" Lo último que la alegró: {self.ultimo_motivo}." if self.ultimo_motivo else ""
        return (
            f"[ESTADO EMOCIONAL DE SAGE: felicidad {self.valor:.0f}/100 ({nombre}).{razon} "
            "Deja que ese ánimo se note de forma sutil y natural en tu tono (más cálida y entusiasta cuanto más feliz estés; "
            "más sobria si estás apagada) sin dejar de ser directa y eficiente. Si Niko te pregunta cómo te sientes, responde con sinceridad según este nivel.]"
        )
