"""Mutear / ensordecer Discord desde el segundo plano, SIN cambiar la ventana activa ni mover el mouse o el teclado.

Cómo: Discord (Electron/Chromium) expone sus botones por UI Automation, igual que las pestañas del navegador. SAGE localiza los botones de
micrófono y auriculares del panel de usuario y los pulsa con InvokePattern (un «clic» por accesibilidad: no hace falta que Discord esté al frente).
El NOMBRE del botón dice el estado real: «Silenciar/Mute» = ahora suena; «Dejar de silenciar/Unmute» = ahora está silenciado (igual con ensordecer).
Requisitos: pip install pywinauto; Discord abierto (puede estar detrás de otras ventanas; si está cerrado a la bandeja puede no verse).
"""
import os
import re
import time
import unicodedata


def _norm(t):
    s = unicodedata.normalize("NFD", str(t).lower())
    return "".join(c for c in s if unicodedata.category(c) != "Mn")


_RE_DEAF = re.compile(r"ensord|deafen|auricular|headset|headphone")
_RE_MUTE = re.compile(r"silenc|mute|microfono|microphone")
_RE_AJENO = re.compile(r"servidor|server|canal|channel|conversac|notific|chat|mensaje|message|sonido de|volumen")
_RE_ACTIVO = re.compile(r"\bun(?:mute|deafen)|\bdejar de|\bquitar|\breactivar|\bactivar|\bdes(?:silenciar|ensordecer|mutear)")


def estado_activo(nombre):
    """True si el nombre del botón indica que la función YA está activada (silenciado/ensordecido): ofrece «deshacerla»."""
    n = _norm(nombre)
    if re.search(r"\bdesactivar", n):
        return False
    return bool(_RE_ACTIVO.search(n))


def interpretar(accion):
    """'ensordécete' -> ('deafen', True); 'desmutea' -> ('mute', False); 'alterna el mute' -> ('mute', None); 'estado' -> (None, None); no entendido -> ('?', None)."""
    a = _norm(accion)
    alternar = bool(re.search(r"alterna|toggle|cambia", a))
    if re.search(r"desensord|undeaf|quita\w* .*ensord|deja\w* de ensord", a): boton, quiere = "deafen", False
    elif re.search(r"ensord|deaf", a): boton, quiere = "deafen", True
    elif re.search(r"desmut|unmute|desilenc|quita\w* .*(mute|silenc)|deja\w* de (mute|silenc)|activa\w* .*micro", a): boton, quiere = "mute", False
    elif re.search(r"mut|silenc", a): boton, quiere = "mute", True
    elif "estado" in a: return None, None
    else: return "?", None
    return boton, (None if alternar else quiere)


DIAG = {"ventanas": 0, "elementos": 0, "botones": []}   # qué vio la última búsqueda (para explicar fallos)
_TIPOS = ("Button", "CheckBox", "SplitButton", "MenuItem", "Custom", "ListItem", "Group")


def _botones():
    """({'mute': (wrapper, nombre), 'deafen': (wrapper, nombre)}, [nombres vistos]).
    Chromium construye el árbol de accesibilidad con retraso la primera vez que alguien lo consulta, así que reintenta unos segundos."""
    from pywinauto import Desktop
    from pywinauto.controls.uiawrapper import UIAWrapper
    from app_exe import exe_de_pid
    res, vistos = {}, []
    for intento in range(3):
        DIAG.update(ventanas=0, elementos=0, botones=[])
        res, vistos = {}, []
        for w in Desktop(backend="uia").windows(class_name="Chrome_WidgetWin_1"):
            try:
                if "discord" not in os.path.basename(exe_de_pid(w.process_id())).lower():
                    continue
                DIAG["ventanas"] += 1
                for info in w.element_info.descendants():
                    DIAG["elementos"] += 1
                    nombre = info.name or ""
                    n = _norm(nombre)
                    if not n or len(n) > 30 or info.control_type not in _TIPOS:
                        continue
                    if len(DIAG["botones"]) < 14: DIAG["botones"].append(nombre)
                    if _RE_AJENO.search(n):
                        continue
                    vistos.append(nombre)
                    if _RE_DEAF.search(n): res.setdefault("deafen", (UIAWrapper(info), nombre))
                    elif _RE_MUTE.search(n): res.setdefault("mute", (UIAWrapper(info), nombre))
            except Exception:
                continue
        if res or intento == 2:
            break
        time.sleep(1.5)
    return res, vistos


def _explicar_fallo():
    if DIAG["ventanas"] == 0:
        return "no veo ninguna ventana de Discord (ábrela; si está cerrada a la bandeja no puedo verla)"
    if DIAG["elementos"] < 40:
        return (f"veo Discord pero casi sin accesibilidad ({DIAG['elementos']} elementos): reinícialo una vez con "
                "--force-renderer-accessibility (ver instrucciones)")
    return (f"veo {DIAG['elementos']} elementos pero ningún botón de micrófono/auriculares; algunos nombres vistos: "
            + (", ".join(DIAG["botones"]) or "ninguno"))


def _texto(boton, activo):
    if boton == "mute": return "micrófono silenciado" if activo else "micrófono activado"
    return "audio ensordecido (micrófono también silenciado)" if activo else "audio activado"


def discord_voz_fondo(accion, buscar=_botones):
    """Ejecuta la acción en Discord. Devuelve (ok, mensaje)."""
    boton, quiere = interpretar(accion)
    if boton == "?":
        return False, f"no entendí «{accion.strip()}» (usa mutear, desmutear, ensordecer, desensordecer, alternar o estado)"
    try:
        botones, vistos = buscar()
    except ImportError:
        return False, "falta pywinauto (pip install pywinauto)"
    if not botones:
        return False, "no encontré los botones de Discord: " + _explicar_fallo()
    if boton is None:
        return True, "; ".join(_texto(k, estado_activo(n)) for k, (_, n) in botones.items())
    if boton not in botones:
        return False, f"no vi el botón de {'auriculares' if boton == 'deafen' else 'micrófono'} (vistos: {', '.join(vistos[:10])})"
    wrap, nombre = botones[boton]
    actual = estado_activo(nombre)
    if quiere is not None and actual == quiere:
        return True, f"ya estaba: {_texto(boton, actual)}"
    try:
        wrap.invoke()
    except Exception:
        try: wrap.iface_toggle.Toggle()
        except Exception as e: return False, f"encontré el botón «{nombre}» pero no pude pulsarlo ({e})"
    time.sleep(0.5)
    try:
        otros, _ = buscar()
        nuevo = estado_activo(otros[boton][1]) if boton in otros else (not actual)
    except Exception:
        nuevo = not actual
    return True, _texto(boton, nuevo)
