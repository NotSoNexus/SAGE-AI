"""Control de ventanas y programas de SAGE (Windows): minimizar, maximizar, modo ventana y cerrar programas.

Incluye la GUARDIA de seguridad (filtrar_acciones): independiente del modelo de IA, bloquea cualquier cierre o cambio de estado de ventana
que Niko no haya pedido con claridad (y sobre algo que Niko no haya nombrado). app.py la aplica a TODAS las acciones antes de ejecutarlas.

- cambiar_estado('minimizar' | 'maximizar' | 'ventana', objetivo): objetivo vacío = la ventana activa de Niko (nunca la de SAGE).
  «ventana» = modo ventana: saca la ventana de maximizada / minimizada / pantalla completa.
- cerrar_programa(nombre, forzar): cierra con cortesía (WM_CLOSE: el programa puede preguntar si guardar). Solo fuerza el cierre si Niko lo pidió
  o si el programa ya no tiene ventanas (típico de apps que se quedan en la bandeja, como Discord o Spotify).
- Nunca cierra SAGE, su terminal, el editor desde el que corre ni procesos del sistema.
"""
import csv
import io
import os
import re
import subprocess
import sys
import time
import unicodedata

SW_SHOWNORMAL, SW_MAXIMIZE, SW_MINIMIZE, SW_RESTORE = 1, 3, 6, 9
WM_CLOSE = 0x0010
_NOWIN = getattr(subprocess, "CREATE_NO_WINDOW", 0)

NAVEGADORES = frozenset({"opera", "opera_gx", "chrome", "msedge", "firefox", "brave", "vivaldi", "iexplore", "arc"})
# Nunca se cierran (SAGE depende de ellos o son del sistema)
PROTEGIDOS = frozenset({
    "explorer", "csrss", "winlogon", "dwm", "svchost", "system", "services", "lsass", "smss", "wininit", "fontdrvhost",
    "python", "pythonw", "py", "code", "cmd", "powershell", "pwsh", "conhost", "windowsterminal", "wt",
    "applicationframehost", "searchhost", "startmenuexperiencehost", "textinputhost", "shellexperiencehost",
})


# ---------------------------------------------------------------- texto
def norm(texto):
    t = unicodedata.normalize("NFD", str(texto).lower())
    return "".join(c for c in t if unicodedata.category(c) != "Mn")


def squash(texto):
    return re.sub(r"[^a-z0-9]", "", norm(texto))


_STOP = frozenset((
    "el la los las un una unos unas de del en al a y o que dice por favor mi tu su sus este esta esto ese esa eso esos esas "
    "ventana ventanas programa programas app apps aplicacion aplicaciones pestana pestanas tab tabs exe todo todos todas "
    "actual activa abierta abierto lo le me te se con para sin").split())
_GENERICOS = frozenset("actual activa esta este esto esa ese eso ventana programa app aplicacion pestana todo todas todos".split())
_SINONIMOS = {
    "navegador": {"opera", "chrome", "edge", "msedge", "firefox", "brave", "vivaldi"},
    "browser": {"opera", "chrome", "edge", "msedge", "firefox", "brave", "vivaldi"},
    "musica": {"spotify"},
    "chat": {"discord", "whatsapp", "telegram"},
}


def tokens(arg):
    return [t for t in re.findall(r"[a-z0-9]+", norm(arg)) if t not in _STOP and len(t) >= 2]


def _nombra(arg, texto_norm):
    """¿El argumento (lo que SAGE quiere tocar) es algo que Niko nombró? (con sinónimos como «navegador» → opera, chrome...)"""
    toks = tokens(arg)
    if not toks:
        return True                                          # sin nombre: se refiere a la ventana activa
    for t in toks:
        if t in texto_norm:
            return True
        for palabra, alias in _SINONIMOS.items():
            if palabra in texto_norm and t in alias:
                return True
    return False


# ---------------------------------------------------------------- guardia de seguridad
_RE_PIDE_CERRAR = re.compile(r"\b(cierr\w*|cerr\w*|mat(a|ar|alo|ala|alos|alas)\b|termin\w*|finaliz\w*|apag\w*|salir|sal de|salte de|quit\w*|elimin\w*|borr\w*|kill|close|exit)")
_RE_PIDE_MINIMIZAR = re.compile(r"\b(minimiz\w*|esconde\w*|escondel\w*|ocult\w*|escritorio|manda\w* a la barra|baja\w* la ventana)")
_RE_PIDE_MAXIMIZAR = re.compile(r"\b(maximiz\w*|agranda\w*|ampli\w*|pantalla completa|llena\w* la pantalla|a pantalla)")
_RE_PIDE_VENTANA = re.compile(r"\b(modo ventana|en ventana|ventana normal|ventaneado|restaur\w*|desmaximiz\w*|reduce\w*|reduc\w*|achic\w*|"
                              r"sal\w* de(?:l)? (?:modo )?pantalla completa|quit\w*\s+(?:la\s+)?pantalla completa|tamano normal|no maximizad\w*|ventana(?:r)?\b.*\bnormal)")
_RE_NEGACION = re.compile(r"\b(?:no|nunca|jamas|sin)\s+(?:(?:te|me|lo|la|los|las|se)\s+)?\w+")
_COMBOS_CERRAR = frozenset({"ctrl+w", "ctrl+f4", "alt+f4", "ctrl+shift+w", "ctrl+q"})
_COMBOS_VENTANA = frozenset({"win+down", "win+up", "win+left", "win+right", "win+m", "win+d", "win+shift+m", "f11", "alt+enter", "alt+space"})
_RE_PULSAR_CERRAR = re.compile(r"\b(cerrar|cierra|close|boton x|cruz|x de cerrar)\b")
_RE_PULSAR_VENTANA = re.compile(r"\b(minimizar|maximizar|restaurar|pantalla completa)\b")


def _combo(arg):
    c = re.sub(r"\s+", "", norm(arg))
    for viejo, nuevo in (("windows", "win"), ("super", "win"), ("control", "ctrl"), ("escape", "esc")):
        c = c.replace(viejo, nuevo)
    return c


def pide_ventana(p):
    return bool(_RE_PIDE_MINIMIZAR.search(p) or _RE_PIDE_MAXIMIZAR.search(p) or _RE_PIDE_VENTANA.search(p))


def filtrar_acciones(acciones, pedido, contexto=""):
    """Guardia: deja pasar solo lo que Niko pidió. `pedido` = su mensaje; `contexto` = el intercambio anterior (para «ciérralo»).
    Devuelve (acciones_permitidas, [descripción de lo bloqueado])."""
    p = norm(pedido)
    p_ctx = f"{p} {norm(contexto)}"
    pp = _RE_NEGACION.sub(" ", p)                      # «no cierres discord» NO es una orden de cerrar
    cerrar = bool(_RE_PIDE_CERRAR.search(pp))
    permisos = {"minimizar": bool(_RE_PIDE_MINIMIZAR.search(pp)), "maximizar": bool(_RE_PIDE_MAXIMIZAR.search(pp)),
                "ventana": bool(_RE_PIDE_VENTANA.search(pp))}
    ventana_ok = any(permisos.values())
    ok, bloqueadas = [], []
    for tipo, arg in acciones:
        a = arg if isinstance(arg, str) else ""
        motivo = None
        if tipo in ("cerrar", "cerrar_pestana"):
            if not cerrar:
                motivo = "no pediste cerrar nada"
            elif not _nombra(a.split("|")[-1] if tipo == "cerrar_pestana" else a, p_ctx):
                motivo = f"no mencionaste «{a.strip()}»"
        elif tipo in ("minimizar", "maximizar", "ventana"):
            if not permisos[tipo]:
                motivo = "no pediste ese cambio de ventana"
            elif not _nombra(a, p_ctx):
                motivo = f"no mencionaste «{a.strip()}»"
        elif tipo in ("tecla", "atajo"):
            c = _combo(a)
            if c in _COMBOS_CERRAR and not cerrar:
                motivo = f"{a.strip()} cerraría una ventana o pestaña y no lo pediste"
            elif c in _COMBOS_VENTANA and not ventana_ok:
                motivo = f"{a.strip()} cambiaría el estado de una ventana y no lo pediste"
        elif tipo in ("pulsar", "pulsar_der"):
            d = norm(a)
            if _RE_PULSAR_CERRAR.search(d) and not cerrar:
                motivo = "pulsaría un botón de cerrar y no lo pediste"
            elif _RE_PULSAR_VENTANA.search(d) and not ventana_ok:
                motivo = "cambiaría el estado de una ventana y no lo pediste"
        if motivo:
            bloqueadas.append(f"{tipo.upper()}: {a.strip()} ({motivo})")
        else:
            ok.append((tipo, arg))
    return ok, bloqueadas


# ---------------------------------------------------------------- API de Windows (todo lo que toca el sistema está aquí)
_W = None


def _w():
    global _W
    if _W is None:
        import ctypes
        from ctypes import wintypes
        u = ctypes.WinDLL("user32", use_last_error=True)      # instancias propias: no alteran los argtypes de otras partes de la app
        k = ctypes.WinDLL("kernel32", use_last_error=True)
        d = ctypes.WinDLL("dwmapi")
        H = wintypes.HWND
        u.ShowWindow.argtypes = [H, ctypes.c_int]
        for f in (u.IsIconic, u.IsZoomed, u.IsWindowVisible, u.SetForegroundWindow, u.GetWindowTextLengthW):
            f.argtypes = [H]
        u.GetForegroundWindow.restype = H
        u.GetWindowTextW.argtypes = [H, wintypes.LPWSTR, ctypes.c_int]
        u.GetWindowThreadProcessId.argtypes = [H, ctypes.POINTER(wintypes.DWORD)]
        u.GetWindowLongW.argtypes = [H, ctypes.c_int]
        u.GetWindow.argtypes = [H, wintypes.UINT]
        u.GetWindow.restype = H
        u.GetWindowRect.argtypes = [H, ctypes.POINTER(wintypes.RECT)]
        u.MonitorFromWindow.argtypes = [H, wintypes.DWORD]
        u.MonitorFromWindow.restype = wintypes.HANDLE
        u.PostMessageW.argtypes = [H, wintypes.UINT, wintypes.WPARAM, wintypes.LPARAM]
        k.OpenProcess.argtypes = [wintypes.DWORD, wintypes.BOOL, wintypes.DWORD]
        k.OpenProcess.restype = wintypes.HANDLE
        k.QueryFullProcessImageNameW.argtypes = [wintypes.HANDLE, wintypes.DWORD, wintypes.LPWSTR, ctypes.POINTER(wintypes.DWORD)]
        k.CloseHandle.argtypes = [wintypes.HANDLE]
        d.DwmGetWindowAttribute.argtypes = [H, wintypes.DWORD, ctypes.c_void_p, wintypes.DWORD]

        class MONITORINFO(ctypes.Structure):
            _fields_ = [("cbSize", wintypes.DWORD), ("rcMonitor", wintypes.RECT), ("rcWork", wintypes.RECT), ("dwFlags", wintypes.DWORD)]
        u.GetMonitorInfoW.argtypes = [wintypes.HANDLE, ctypes.POINTER(MONITORINFO)]
        _W = (u, k, d, MONITORINFO)
    return _W


def _exe(pid, k):
    import ctypes
    from ctypes import wintypes
    h = k.OpenProcess(0x1000, False, pid)        # PROCESS_QUERY_LIMITED_INFORMATION
    if not h:
        return ""
    try:
        buf = ctypes.create_unicode_buffer(520)
        n = wintypes.DWORD(520)
        if k.QueryFullProcessImageNameW(h, 0, buf, ctypes.byref(n)):
            return os.path.splitext(os.path.basename(buf.value))[0].lower()
    finally:
        k.CloseHandle(h)
    return ""


def listar_ventanas():
    """Ventanas de aplicación visibles, de arriba abajo en el orden Z: [{hwnd, titulo, pid, exe, activa}]. Excluye las de SAGE."""
    import ctypes
    from ctypes import wintypes
    u, k, d, _ = _w()
    activa = u.GetForegroundWindow()
    res, exes = [], {}
    propio = os.getpid()
    proc = ctypes.WINFUNCTYPE(wintypes.BOOL, wintypes.HWND, wintypes.LPARAM)

    def cb(hwnd, _):
        try:
            if not u.IsWindowVisible(hwnd):
                return True
            n = u.GetWindowTextLengthW(hwnd)
            if n <= 0:
                return True
            ex = u.GetWindowLongW(hwnd, -20)                       # GWL_EXSTYLE
            if (ex & 0x80) and not (ex & 0x40000):                 # TOOLWINDOW sin APPWINDOW
                return True
            if u.GetWindow(hwnd, 4) and not (ex & 0x40000):        # tiene propietaria (diálogo auxiliar)
                return True
            oculta = ctypes.c_int(0)
            if d.DwmGetWindowAttribute(hwnd, 14, ctypes.byref(oculta), 4) == 0 and oculta.value:   # DWMWA_CLOAKED
                return True
            buf = ctypes.create_unicode_buffer(n + 1)
            u.GetWindowTextW(hwnd, buf, n + 1)
            if buf.value == "Program Manager":
                return True
            pid = wintypes.DWORD()
            u.GetWindowThreadProcessId(hwnd, ctypes.byref(pid))
            if pid.value == propio:
                return True
            if pid.value not in exes:
                exes[pid.value] = _exe(pid.value, k)
            res.append({"hwnd": hwnd, "titulo": buf.value, "pid": pid.value, "exe": exes[pid.value], "activa": hwnd == activa})
        except Exception:
            pass
        return True

    u.EnumWindows(proc(cb), 0)
    return res


def estado(hwnd):
    """'minimizada' | 'maximizada' | 'pantalla completa' (sin bordes, cubre el monitor) | 'normal'."""
    import ctypes
    from ctypes import wintypes
    u, _, _, MI = _w()
    if u.IsIconic(hwnd):
        return "minimizada"
    if u.IsZoomed(hwnd):
        return "maximizada"
    r = wintypes.RECT()
    u.GetWindowRect(hwnd, ctypes.byref(r))
    mi = MI()
    mi.cbSize = ctypes.sizeof(MI)
    mon = u.MonitorFromWindow(hwnd, 2)                             # MONITOR_DEFAULTTONEAREST
    if mon and u.GetMonitorInfoW(mon, ctypes.byref(mi)):
        m = mi.rcMonitor
        sin_barra = not (u.GetWindowLongW(hwnd, -16) & 0xC00000)   # sin WS_CAPTION
        if sin_barra and r.left <= m.left and r.top <= m.top and r.right >= m.right and r.bottom >= m.bottom:
            return "pantalla completa"
    return "normal"


def _show(hwnd, cmd):
    _w()[0].ShowWindow(hwnd, cmd)


def _al_frente(hwnd):
    try:
        _w()[0].SetForegroundWindow(hwnd)
    except Exception:
        pass


def _post_close(hwnd):
    _w()[0].PostMessageW(hwnd, WM_CLOSE, 0, 0)


def procesos():
    """[(pid, nombre en minúsculas sin .exe)] de todos los procesos (tasklist)."""
    out = subprocess.check_output(["tasklist", "/FO", "CSV", "/NH"], text=True, encoding="mbcs", errors="replace", creationflags=_NOWIN)
    filas = []
    for f in csv.reader(io.StringIO(out)):
        if len(f) >= 2 and f[1].strip().isdigit():
            filas.append((int(f[1]), re.sub(r"\.exe$", "", f[0].strip().lower())))
    return filas


def _matar(pid):
    subprocess.run(["taskkill", "/F", "/T", "/PID", str(pid)], creationflags=_NOWIN, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)


# ---------------------------------------------------------------- buscar ventanas
def buscar_ventana(objetivo, ventanas=None, excluir_navegador_por_titulo=False):
    """Ventana que mejor encaja con `objetivo` (nombre del programa o parte del título). Vacío/genérico = la ventana activa de Niko."""
    vs = ventanas if ventanas is not None else listar_ventanas()
    if not vs:
        return None
    toks = tokens(objetivo)
    if not toks or all(t in _GENERICOS for t in toks):
        return next((w for w in vs if w["activa"]), vs[0])
    sq = "".join(toks)
    mejor, mejor_p = None, 0
    for w in vs:
        exe, tit = squash(w["exe"]), norm(w["titulo"])
        if sq == exe or any(t == exe for t in toks):
            p = 3
        elif len(sq) >= 3 and (sq in exe or any(len(t) >= 3 and t in exe for t in toks)):
            p = 2
        elif all(t in tit for t in toks):
            p = 1
            if excluir_navegador_por_titulo and w["exe"] in NAVEGADORES:
                p = 0                                                # «youtube» es una pestaña, no el navegador entero
        else:
            p = 0
        if p > mejor_p:
            mejor, mejor_p = w, p
    return mejor


# ---------------------------------------------------------------- minimizar / maximizar / modo ventana
def cambiar_estado(modo, objetivo=""):
    """modo: 'minimizar' | 'maximizar' | 'ventana'. Devuelve (ok, mensaje)."""
    w = buscar_ventana(objetivo)
    if w is None:
        return False, f"no encontré ninguna ventana de «{objetivo.strip() or 'la ventana activa'}»"
    h, nombre, st = w["hwnd"], (w["titulo"][:50] or w["exe"]), estado(w["hwnd"])

    if modo == "minimizar":
        if st == "minimizada":
            return True, f"«{nombre}» ya estaba minimizada"
        _show(h, SW_MINIMIZE)
        return True, f"minimicé «{nombre}»"

    if modo == "maximizar":
        if st == "maximizada":
            _al_frente(h)
            return True, f"«{nombre}» ya estaba maximizada"
        if st == "pantalla completa":
            return True, f"«{nombre}» ya está en pantalla completa"
        if st == "minimizada":
            _show(h, SW_RESTORE)
        _show(h, SW_MAXIMIZE)
        _al_frente(h)
        return True, f"maximicé «{nombre}»"

    if modo == "ventana":
        if st == "normal":
            return True, f"«{nombre}» ya estaba en modo ventana"
        if st in ("minimizada", "maximizada"):
            _show(h, SW_SHOWNORMAL)
            if estado(h) == "maximizada":
                _show(h, SW_RESTORE)
            _al_frente(h)
            return True, f"puse «{nombre}» en modo ventana"
        # Pantalla completa sin bordes: Windows no la quita por API; cada programa tiene su tecla (F11 en navegadores y reproductores, alt+enter en juegos)
        tecla = "f11" if w["exe"] in NAVEGADORES or w["exe"] in ("vlc", "mpv", "mpc-hc64", "spotify") else "alt+enter"
        try:
            import pyautogui
            _al_frente(h)
            time.sleep(0.4)
            pyautogui.hotkey(*tecla.split("+"))
            time.sleep(0.9)
        except Exception as e:
            return False, f"«{nombre}» está en pantalla completa y no pude pulsar {tecla}: {e}"
        if estado(h) == "pantalla completa":
            return False, f"«{nombre}» sigue en pantalla completa tras pulsar {tecla}; dime qué tecla usa ese programa para salir"
        return True, f"saqué «{nombre}» de pantalla completa con {tecla}"

    return False, f"modo de ventana desconocido: {modo}"


# ---------------------------------------------------------------- cerrar programas
def _vivos(pids):
    try:
        return {pid for pid, _ in procesos() if pid in pids}
    except Exception:
        return set(pids)


def cerrar_programa(nombre, forzar=False, esperar=4.0):
    """Cierra un programa con cortesía. Devuelve (ok, mensaje)."""
    sq = squash(nombre)
    if len(sq) < 3:
        return False, f"«{nombre}» es demasiado corto o ambiguo para cerrarlo con seguridad"
    prohibidos = {os.getpid(), os.getppid()}

    cand = {}
    for pid, n in procesos():
        if sq in squash(n) and pid not in prohibidos:
            cand[pid] = n
    protegidos = sorted({n for n in cand.values() if n in PROTEGIDOS})
    cand = {p: n for p, n in cand.items() if n not in PROTEGIDOS}
    ventanas = listar_ventanas()

    por_titulo = False
    if not cand:
        w = buscar_ventana(nombre, ventanas, excluir_navegador_por_titulo=True)
        if w is not None and tokens(nombre) and all(t in norm(w["titulo"]) for t in tokens(nombre)):
            por_titulo = True
            ventanas = [w]
            if w["exe"] not in PROTEGIDOS and w["pid"] not in prohibidos:
                cand = {w["pid"]: w["exe"]}
        elif protegidos:
            return False, f"no cierro «{', '.join(protegidos)}»: SAGE depende de él o es parte del sistema"
        else:
            hay_nav = buscar_ventana(nombre, ventanas) is not None
            if hay_nav:
                return False, f"«{nombre}» parece una pestaña o sitio dentro del navegador, no un programa: para eso se usa CERRAR_PESTANA"
            return False, f"no encontré ningún programa llamado «{nombre}»"

    pids = set(cand)
    mias = [w for w in ventanas if w["pid"] in pids] if not por_titulo else ventanas
    for w in mias:                                           # 1) cierre cortés: el programa decide si pregunta por guardar
        try:
            _post_close(w["hwnd"])
        except Exception:
            pass
    fin = time.time() + esperar
    vivos = set(pids)
    while vivos and time.time() < fin:
        time.sleep(0.5)
        vivos = _vivos(pids) if pids else set()
    if por_titulo and not pids:
        return True, f"cerré la ventana «{(mias[0]['titulo'] if mias else nombre)[:50]}»"

    if vivos:
        con_ventana = {w["pid"] for w in listar_ventanas() if w["pid"] in vivos}
        a_matar = vivos if forzar else (vivos - con_ventana)  # sin ventana = vive en la bandeja: se cierra del todo
        for pid in a_matar:                                  # 2) solo si sigue vivo
            _matar(pid)
        quedan = vivos - a_matar
        if quedan:
            return False, (f"«{nombre}» no se cerró: sigue con ventana abierta (quizá pregunta si guardar cambios). "
                           "No lo forcé; dime «fuerza el cierre» si quieres cerrarlo a la fuerza")
    nombres = ", ".join(sorted(set(cand.values())))
    return True, f"cerré {nombres}"


# ---------------------------------------------------------------- abrir programas SIN robar el primer plano
def _hilo_input():
    import ctypes
    from ctypes import wintypes
    class LII(ctypes.Structure):
        _fields_ = [("cbSize", wintypes.UINT), ("dwTime", wintypes.DWORD)]
    li = LII(); li.cbSize = ctypes.sizeof(LII)
    ctypes.windll.user32.GetLastInputInfo(ctypes.byref(li))
    return li.dwTime


def _devolver_foco(hwnd):
    """Devuelve el foco a hwnd (con AttachThreadInput: no simula teclas, así que no molesta a la app que Niko está usando)."""
    import ctypes
    from ctypes import wintypes
    u = ctypes.WinDLL("user32", use_last_error=True)
    H = wintypes.HWND
    u.GetForegroundWindow.restype = H
    for f in (u.IsWindow, u.IsIconic, u.SetForegroundWindow):
        f.argtypes = [H]
    u.ShowWindow.argtypes = [H, ctypes.c_int]
    u.GetWindowThreadProcessId.argtypes = [H, ctypes.POINTER(wintypes.DWORD)]
    u.AttachThreadInput.argtypes = [wintypes.DWORD, wintypes.DWORD, wintypes.BOOL]
    if not u.IsWindow(hwnd):
        return
    if u.IsIconic(hwnd):
        u.ShowWindow(hwnd, 9)   # SW_RESTORE: solo si Niko la tenía minimizada
    actual = u.GetForegroundWindow()
    t_act = u.GetWindowThreadProcessId(actual, None) if actual else 0
    t_yo = ctypes.windll.kernel32.GetCurrentThreadId()
    unido = bool(t_act and t_act != t_yo and u.AttachThreadInput(t_yo, t_act, True))
    try:
        u.SetForegroundWindow(hwnd)
    finally:
        if unido:
            u.AttachThreadInput(t_yo, t_act, False)


def abrir_en_segundo_plano(cmd, vigilar=8.0):
    """Abre un programa, archivo, carpeta o URL sin que su ventana tome el foco: arranca minimizado-sin-activar y, si aun así
    la app se pone al frente, devuelve el foco a lo que Niko estaba haciendo. Devuelve (ok, mensaje)."""
    import ctypes
    import threading
    from ctypes import wintypes
    if sys.platform != "win32":
        return False, "solo disponible en Windows"
    cmd = (cmd or "").strip()
    if not cmd:
        return False, "no indicaste qué abrir"
    u = ctypes.WinDLL("user32")
    u.GetForegroundWindow.restype = wintypes.HWND
    original = u.GetForegroundWindow()
    previas = {v["hwnd"] for v in listar_ventanas()}
    input0 = _hilo_input()

    sh = ctypes.WinDLL("shell32")
    sh.ShellExecuteW.argtypes = [wintypes.HWND, wintypes.LPCWSTR, wintypes.LPCWSTR, wintypes.LPCWSTR, wintypes.LPCWSTR, ctypes.c_int]
    sh.ShellExecuteW.restype = ctypes.c_void_p
    # SW_SHOWMINNOACTIVE (7): ventana minimizada y sin activar. Para una URL o un documento la abre su programa predeterminado.
    r = sh.ShellExecuteW(None, "open", cmd, None, None, 7) or 0
    if r <= 32:
        try:   # comando con argumentos («notepad archivo.txt», «code .»): se lanza sin consola ni foco
            si = subprocess.STARTUPINFO()
            si.dwFlags |= subprocess.STARTF_USESHOWWINDOW
            si.wShowWindow = 7
            subprocess.Popen(cmd, shell=True, startupinfo=si, creationflags=0x08000000,   # CREATE_NO_WINDOW
                             stdin=subprocess.DEVNULL, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        except Exception as e:
            return False, f"no pude abrir «{cmd}» en segundo plano ({e})"

    if original:
        def vigia():
            fin = time.time() + vigilar
            while time.time() < fin:
                time.sleep(0.15)
                try:
                    ahora = u.GetForegroundWindow()
                    if ahora and ahora != original:
                        # Foco robado por la app nueva (ventana que no existía), o Niko no tocó nada: se lo devuelve.
                        if ahora not in previas or _hilo_input() == input0:
                            _devolver_foco(original)
                except Exception:
                    return
        threading.Thread(target=vigia, daemon=True).start()
    return True, f"abrí «{cmd}» en segundo plano (sin quitarte el foco)"
