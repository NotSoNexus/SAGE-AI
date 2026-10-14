"""Hora hablada de forma natural en formato de 12 horas (1 a 12), para que SAGE la diga como una persona.

  frase_hora()            -> «son las tres y media de la tarde» / «es la una en punto de la tarde»
  hablar_horas(texto)     -> reemplaza «15:30», «a las 8:05 pm»... por su forma hablada (lo usa boca.py antes de sintetizar la voz)
"""
import re
import time

_UN = ("cero", "uno", "dos", "tres", "cuatro", "cinco", "seis", "siete", "ocho", "nueve", "diez", "once", "doce", "trece", "catorce",
       "quince", "dieciséis", "diecisiete", "dieciocho", "diecinueve", "veinte", "veintiuno", "veintidós", "veintitrés", "veinticuatro",
       "veinticinco", "veintiséis", "veintisiete", "veintiocho", "veintinueve")
_DEC = {3: "treinta", 4: "cuarenta", 5: "cincuenta"}


def _num(n):
    if n < 30:
        return _UN[n]
    d, u = divmod(n, 10)
    return _DEC[d] + (f" y {_UN[u]}" if u else "")


def _parte_del_dia(h, m):
    if h == 0 and m == 0:
        return "de la noche"          # las doce de la noche
    if h < 6:
        return "de la madrugada"
    if h < 12:
        return "de la mañana"
    if h == 12:
        return "del mediodía"
    if h < 20:
        return "de la tarde"
    return "de la noche"


def _hora12(h):
    return (h % 12) or 12


def _con_articulo(h12):
    return "la una" if h12 == 1 else f"las {_num(h12)}"


def hora_hablada(h, m):
    """(verbo, frase): ('son', 'las tres y media de la tarde'). Minutos 1-44 con «y», del 45 en adelante con «menos» (como se dice)."""
    parte = _parte_del_dia(h, m)
    if m == 0:
        mostrada, resto = _hora12(h), " en punto"
    elif m == 15:
        mostrada, resto = _hora12(h), " y cuarto"
    elif m == 30:
        mostrada, resto = _hora12(h), " y media"
    elif m >= 45:
        mostrada = _hora12(h + 1)
        falta = 60 - m
        resto = " menos cuarto" if m == 45 else (" menos un minuto" if falta == 1 else f" menos {_num(falta)}")
    else:
        mostrada, resto = _hora12(h), f" y {_num(m)}"
    verbo = "es" if mostrada == 1 else "son"
    return verbo, f"{_con_articulo(mostrada)}{resto} {parte}"


def frase_hora(t=None):
    """«son las tres y media de la tarde» con la hora local actual (o la de la estructura time dada)."""
    t = t or time.localtime()
    verbo, frase = hora_hablada(t.tm_hour, t.tm_min)
    return f"{verbo} {frase}"


# «15:30», «a las 8:05 pm», «la 1:10»: se reemplaza por la hora hablada (el artículo propio sustituye al que ya hubiera).
# Para no confundir duraciones o marcadores («dura 3:45», «va 2:10») solo se convierte si hay «la/las», am/pm, la palabra «hora» delante o es de 13 a 23 h.
_RE_HORA = re.compile(r"(?P<art>\b(?:las?)\s+)?(?<![\d:.,])(?P<h>\d{1,2}):(?P<m>[0-5]\d)(?::[0-5]\d)?(?![\d:])(?:\s*(?P<ap>[ap])\.?\s?m\b\.?)?", re.IGNORECASE)
_RE_ANTES_HORA = re.compile(r"hora\w*\s*(?:es|de|:)?\s*$", re.IGNORECASE)


def _sustituir(m):
    h, mi = int(m.group("h")), int(m.group("m"))
    marca = (m.group("ap") or "").lower()
    if marca:
        if not 1 <= h <= 12:
            return m.group(0)
        h = (h % 12) + (12 if marca == "p" else 0)
    else:
        if h > 23:
            return m.group(0)
        contexto = m.string[max(0, m.start() - 18):m.start()]
        if not (m.group("art") or h >= 13 or _RE_ANTES_HORA.search(contexto)):
            return m.group(0)
    return hora_hablada(h, mi)[1]


def hablar_horas(texto):
    return _RE_HORA.sub(_sustituir, texto)
