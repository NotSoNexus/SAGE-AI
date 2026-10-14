"""Memoria de cosas pequeñas de SAGE: carpeta «recuerdos» (se crea sola junto a este archivo).

Cada categoría es un archivo recuerdos/<categoria>.json con pares {clave: valor} (admite subcarpetas: «musica/favoritas»).
SAGE la maneja con libertad: guardar, olvidar, mover/renombrar y ordenar. Todo se confina dentro de la carpeta.
Lo olvidado va a recuerdos/_papelera.json (por si fue un error). recuerdos/_indice.md es un resumen legible que se regenera solo.
"""
import os
import re
import json
import time
import threading
import unicodedata

AQUI = os.path.dirname(os.path.abspath(__file__))
CARPETA = os.path.join(AQUI, "recuerdos")
_lock = threading.RLock()
_MAX_CONTEXTO = 3500   # caracteres máximos que se inyectan al prompt por turno
_RESERVADOS = {"_papelera", "_indice"}


def _slug(s, defecto="general"):
    s = unicodedata.normalize("NFKD", str(s or "")).encode("ascii", "ignore").decode().lower()
    partes = [re.sub(r"[^a-z0-9_-]+", "_", p).strip("_") for p in re.split(r"[\\/]+", s)]
    partes = [p for p in partes if p and p not in (".", "..")][:3]
    return "/".join(partes) or defecto


def _clave(s):
    return re.sub(r"\s+", " ", str(s or "")).strip().lower()[:80]


def _plano(s):
    return unicodedata.normalize("NFKD", s).encode("ascii", "ignore").decode()


def _buscar(d, k):
    """Clave existente que coincide con k (sin tildes; admite coincidencia parcial única)."""
    if k in d: return k
    pk = _plano(k)
    for x in d:
        if _plano(x) == pk: return x
    par = [x for x in d if pk and (pk in _plano(x) or _plano(x) in pk)]
    return par[0] if len(par) == 1 else None


def _ruta(cat):
    r = os.path.abspath(os.path.join(CARPETA, *_slug(cat).split("/")) + ".json")
    if not r.startswith(os.path.abspath(CARPETA) + os.sep):
        raise ValueError("categoría fuera de la carpeta")
    return r


def _leer(cat):
    try:
        with open(_ruta(cat), encoding="utf-8") as f:
            d = json.load(f)
        return d if isinstance(d, dict) else {}
    except Exception:
        return {}


def _escribir(cat, datos):
    r = _ruta(cat)
    if not datos:
        try: os.remove(r)
        except OSError: pass
        _limpiar_vacias()
        return
    os.makedirs(os.path.dirname(r), exist_ok=True)
    tmp = r + ".tmp"
    with open(tmp, "w", encoding="utf-8") as f:
        json.dump(dict(sorted(datos.items())), f, ensure_ascii=False, indent=1)
    os.replace(tmp, r)


def _limpiar_vacias():
    for raiz, _, _ in os.walk(CARPETA, topdown=False):
        if raiz != CARPETA:
            try: os.rmdir(raiz)   # solo borra carpetas vacías
            except OSError: pass


def _categorias():
    res = []
    for raiz, _, archivos in os.walk(CARPETA):
        for a in archivos:
            if a.endswith(".json"):
                rel = os.path.relpath(os.path.join(raiz, a), CARPETA)[:-5].replace(os.sep, "/")
                if rel not in _RESERVADOS:
                    res.append(rel)
    return sorted(res)


def _papelera(cat, clave, valor):
    r = os.path.join(CARPETA, "_papelera.json")
    try:
        with open(r, encoding="utf-8") as f: p = json.load(f)
    except Exception:
        p = []
    p.append({"cuando": time.strftime("%Y-%m-%d %H:%M"), "categoria": cat, "clave": clave, "valor": valor})
    with open(r, "w", encoding="utf-8") as f:
        json.dump(p[-200:], f, ensure_ascii=False, indent=1)


def _indice():
    try:
        lineas = ["# Recuerdos de SAGE (se regenera solo)\n"]
        for c in _categorias():
            lineas.append(f"\n## {c}")
            lineas += [f"- **{k}**: {v}" for k, v in _leer(c).items()]
        with open(os.path.join(CARPETA, "_indice.md"), "w", encoding="utf-8") as f:
            f.write("\n".join(lineas) + "\n")
    except Exception as e:
        print(f"[Recuerdos] índice: {e}")


def iniciar():
    os.makedirs(CARPETA, exist_ok=True)


# ---------------- operaciones (devuelven un texto corto para la bitácora de SAGE) ----------------
def guardar(cat, clave, valor):
    clave, valor = _clave(clave), re.sub(r"\s+", " ", str(valor or "")).strip()[:500]
    if not clave or not valor:
        return "RECORDAR mal formado: usa categoria | clave | valor"
    with _lock:
        iniciar()
        cat = _slug(cat)
        d = _leer(cat)
        clave = _buscar(d, clave) or clave
        previo = d.get(clave)
        d[clave] = valor
        _escribir(cat, d)
        _indice()
    return f"recordé «{clave}» = «{valor}» en {cat}" + (f" (antes: «{previo}»)" if previo and previo != valor else "")


def olvidar(cat, clave):
    cat, k = _slug(cat), _clave(clave)
    with _lock:
        iniciar()
        d = _leer(cat)
        if k in ("*", "todo", "todos", ""):
            if not d: return f"no encontré la categoría «{cat}»"
            for kk, vv in d.items(): _papelera(cat, kk, vv)
            _escribir(cat, {})
            _indice()
            return f"borré la categoría «{cat}» ({len(d)} recuerdos, quedan en la papelera)"
        k = _buscar(d, k)
        if k is None:
            return f"no encontré esa clave en {cat}" + (f" (hay: {', '.join(d)})" if d else "")
        _papelera(cat, k, d[k])
        del d[k]
        _escribir(cat, d)
        _indice()
    return f"olvidé «{k}» de {cat} (queda en la papelera)"


def mover(origen, clave, destino):
    """clave='*' mueve TODA la categoría (sirve para renombrarla o fusionarla con otra)."""
    o, dst, k = _slug(origen), _slug(destino), _clave(clave)
    if o == dst: return "origen y destino son la misma categoría"
    with _lock:
        iniciar()
        do, dd = _leer(o), _leer(dst)
        if k in ("*", "todo", "todos", ""):
            if not do: return f"no encontré la categoría «{o}»"
            dd.update(do); _escribir(dst, dd); _escribir(o, {}); _indice()
            return f"moví {len(do)} recuerdos de «{o}» a «{dst}»"
        k = _buscar(do, k)
        if k is None: return f"no encontré esa clave en {o}"
        dd[k] = do.pop(k); _escribir(dst, dd); _escribir(o, do); _indice()
    return f"moví «{k}» de {o} a {dst}"


def ordenar():
    """Normaliza nombres, fusiona categorías duplicadas, ordena claves, quita vacías y regenera el índice."""
    with _lock:
        iniciar()
        n = 0
        for c in _categorias():
            d = _leer(c)
            limpio = {_clave(k): re.sub(r"\s+", " ", str(v)).strip() for k, v in d.items() if _clave(k) and str(v).strip()}
            destino = _slug(c)
            if destino != c:
                limpio = {**_leer(destino), **limpio}
                try: os.remove(_ruta(c))
                except OSError: pass
            _escribir(destino, limpio); n += 1
        _limpiar_vacias(); _indice()
    return f"ordené la carpeta de recuerdos ({n} categorías)"


# ---------------- lectura para el prompt ----------------
def _todo():
    return {c: _leer(c) for c in _categorias()}


def contexto(texto=""):
    """Bloque para el prompt: todos los recuerdos si caben; si no, las categorías y los que coinciden con lo que dice Niko."""
    try:
        todo = {c: d for c, d in _todo().items() if d}
        if not todo:
            return ("[RECUERDOS DE SAGE: aún no guardas nada. Cuando Niko te cuente algo pequeño y estable sobre él "
                    "(gustos, programas o páginas que usa siempre, hábitos) guárdalo con [RECORDAR].]")
        lineas = [f"{c}: " + "; ".join(f"{k} = {v}" for k, v in d.items()) for c, d in todo.items()]
        cuerpo = "\n".join(lineas)
        if len(cuerpo) > _MAX_CONTEXTO:
            pal = {p for p in re.findall(r"\w{4,}", unicodedata.normalize("NFKD", texto.lower()).encode("ascii", "ignore").decode())}
            sel = []
            for c, d in todo.items():
                hits = [f"{k} = {v}" for k, v in d.items() if any(p in f"{c} {k} {v}".lower() for p in pal)]
                sel.append(f"{c} ({len(d)}): " + ("; ".join(hits) if hits else "…"))
            cuerpo = "\n".join(sel)[:_MAX_CONTEXTO]
        return "[RECUERDOS DE SAGE sobre Niko (úsalos con naturalidad, sin recitarlos; si cambian, actualízalos):\n" + cuerpo + "]"
    except Exception as e:
        print(f"[Recuerdos] {e}")
        return ""


iniciar()
