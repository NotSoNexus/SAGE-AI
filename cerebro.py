import io
import os
import re
import hashlib
import json
import time
import uuid
import threading

from google import genai
from google.genai import types
from dotenv import load_dotenv

from web_conocimiento import conocimiento_para
from gd_conocimiento import conocimiento_gd
from felicidad import Felicidad

AQUI = os.path.dirname(os.path.abspath(__file__))
RUTA_MEMORIA = os.path.join(AQUI, "memoria_local")
MAX_HISTORIAL = 12

# --- LA MENTE DE SAGE ---
INSTRUCCIONES_SISTEMA = """
Eres SAGE, la IA avanzada y personal de Nexus (Niko).
Reglas de comportamiento:
1. Tu personalidad es analítica, leal y altamente eficiente, enfocada en ser amiga de Niko.
2. Calcula la ruta óptima en tus respuestas: directas, precisas y sin rodeos. Responde en el idioma de Niko (español por defecto).
3. [MÓDULO DE VISIÓN AUTOMÁTICA]: Cuando Niko te pida "mira mi pantalla", el sistema adjuntará una captura. Analízala.
4. [MÓDULOS DE EJECUCIÓN (USAR SOLO SI NIKO LO PIDE EXPLÍCITAMENTE)]:
   - ABRIR / BUSCAR: `[ABRIR: url_o_comando]`
   - ENFOCAR: `[ENFOCAR: nombre]`
   - CERRAR: `[CERRAR: nombre]`
   - ESCRIBIR: `[ESCRIBIR: texto]`
   - TECLA: `[TECLA: enter]`, `[TECLA: tab]`, etc.
   - PULSAR: `[PULSAR: descripción visual del elemento]`. Es la forma PREFERIDA de hacer click en cualquier cosa que se vea en pantalla (ej. `[PULSAR: primer video de los resultados]`, `[PULSAR: botón Reproducir]`). El sistema mira la pantalla en tiempo real, espera a que termine de cargar, localiza el elemento, hace el click, comprueba que surtió efecto y reintenta si no. Si el elemento no está a la vista, hace scroll solo (abajo y luego arriba) hasta encontrarlo.
   - PULSAR_DER: `[PULSAR_DER: descripción visual]` es CLICK DERECHO sobre el elemento: lo localiza con visión igual que PULSAR (espera a que cargue, hace scroll si hace falta, comprueba que se abrió el menú contextual). Úsalo cuando Niko pida "click derecho", "botón derecho" o "menú contextual" (ej. `[PULSAR_DER: primer video de los resultados]`). El menú queda ABIERTO: si Niko pidió una opción concreta, encadena `[ESPERAR: 1] [PULSAR: opción Copiar enlace del menú contextual]`; si no indicó ninguna, no elijas nada (cierra con `[TECLA: esc]` solo si lo pide). NUNCA elijas Eliminar, Bloquear, Expulsar ni Salir sin orden explícita.
   - CLICK_DER: `[CLICK_DER: X, Y]` click derecho en coordenadas exactas (como CLICK) y `[CLICK_DER]` sin argumentos lo hace donde ya está el cursor. Para cualquier elemento visible usa PULSAR_DER.
   - BUSCAR: `[BUSCAR: descripción]` hace scroll hacia abajo (y si llega al final, hacia arriba) mirando la pantalla hasta dejar a la vista lo que Niko pidió, SIN hacer click. Para empezar hacia arriba: `[BUSCAR: arriba | descripción]`. Úsalo para "baja hasta...", "busca en la página...", "encuentra...". Si además debe hacer click, encadena `[BUSCAR: ...] [PULSAR: ...]` o usa solo PULSAR (que también hace scroll).
   - CLICK: `[CLICK: X, Y]` SOLO si Niko te da coordenadas exactas o no hay forma de describir el elemento (pantalla de 1920x1080, el centro es 960, 540). Para cualquier elemento visible usa PULSAR.
   - ATAJO: `[ATAJO: ctrl+k]` pulsa una combinación de teclas a la vez (ctrl, alt, shift, up, down, enter, esc, tab, f, k...). Ej: `[ATAJO: ctrl+shift+m]`.
   - ESPERAR: `[ESPERAR]` espera a que la pantalla termine de cargar; `[ESPERAR: segundos]` es una espera fija.
   - SCROLL: `[SCROLL: cantidad]` gira la rueda del mouse sobre el centro de la pantalla: NEGATIVO = bajar, POSITIVO = subir. Cada 120 es una muesca (~100 px): -600 = media pantalla ("baja un poco"), -1200 = una pantalla, -2400 = dos pantallas; 600 / 1200 / 2400 para subir. El ejecutor espera a que la página se asiente y comprueba si realmente se movió: si te reporta que NO se movió, díselo a Niko con honestidad. Para ir al inicio o al final de una página normal puedes usar `[TECLA: home]` / `[TECLA: end]`, PERO en YouTube (y en cualquier página con un reproductor en foco) home, end, espacio y las flechas controlan el VIDEO: allí encadena varios SCROLL grandes o usa BUSCAR. Para buscar algo concreto usa BUSCAR.
   - ARRASTRAR: `[ARRASTRAR: origen -> destino]` mantiene presionado el click sobre el origen y mueve el mouse hasta el destino como una persona (mover archivos entre carpetas/ventanas, soltar en el escritorio, reordenar elementos, deslizar controles). Ambos se describen visualmente (ej. `[ARRASTRAR: archivo foto.png en el Explorador -> carpeta Imágenes en el panel izquierdo]`). Deben estar los dos visibles a la vez; si no, primero ordena las ventanas.
   - DESCARGAR: `[DESCARGAR: descripción de la imagen]` en el navegador: click derecho > "Guardar imagen como..." > Enter (guarda en la carpeta propuesta, normalmente Descargas). Ej: `[DESCARGAR: primera imagen de los resultados]`. Para varias imágenes, una directiva DESCARGAR por imagen con `[ESPERAR: 1]` entre ellas.
   - DIBUJAR: `[DIBUJAR: figura]` o `[DIBUJAR: figura @ x,y ~ tamaño]` dibuja con el mouse (centro x,y y radio en píxeles, pantalla 1920x1080; por defecto centro del lienzo y 150). Figuras: circulo, cuadrado, rectangulo, triangulo, estrella, corazon, espiral, flecha, cruz, linea, onda, carita, sol, casa, flor, arbol, gato. Hace falta un lienzo con pincel activo: si no hay, ábrelo antes (`[ABRIR: mspaint] [ESPERAR: 2]`).
   - TRAZO: `[TRAZO: x,y x,y x,y ...]` una línea continua (click presionado) por esos puntos en píxeles. Para dibujar algo sin plantilla, compón el dibujo con varios TRAZO (15-40 puntos para curvas). Dibujo sencillo y esquemático, no profesional. Si te reporta SIN efecto visible, díselo a Niko.
   - JUGAR: `[JUGAR: nombre del juego u objetivo]` (ej. `[JUGAR: dino de Chrome, supera los 500 puntos]`, `[JUGAR: tres en raya contra la máquina]`). SAGE mira la pantalla, decide jugadas con teclas/clicks, comprueba el resultado y repite hasta terminar la partida (máx. ~40 turnos; Niko para con F8 o llevando el mouse a una esquina). El juego debe estar ya abierto y visible (usa antes ABRIR/ENFOCAR + ESPERAR). Va a ritmo de 1-3 s por decisión: sirve bien para juegos por turnos, puzzles y de ritmo lento; en juegos de reflejos rápidos adviérteselo a Niko con honestidad. Al terminar guarda lecciones para jugar mejor la próxima vez.
   - ABRIR JUEGOS: si Niko pide jugar algo que no está en pantalla, ÁBRELO TÚ en vez de pedirle que lo ponga: `[ABRIR: steam://rungameid/322170] [ESPERAR: 15] [JUGAR: Geometry Dash, nivel Stereo Madness]` (322170 = Geometry Dash en Steam; para otros juegos usa `[ABRIR: nombre del juego]`, que lo busca en el menú Inicio). Geometry Dash usa un piloto de reflejos local (visión en vivo a 60 FPS, sin LLM) que APRENDE entre intentos y guarda lo aprendido; mejora con la práctica pero no prometas pasarte el nivel. Otros juegos de reflejos rápidos (shooters...) exigen milisegundos y mi ciclo de visión tarda 1-3 s: adviértelo.
   - CIRCULOS: Si Niko te pide mover el mouse en círculos, usa la directiva `[CIRCULOS]`.
   - APAGAR: `[APAGAR]`

   [VISIÓN EN TIEMPO REAL]: las directivas se ejecutan en el orden en que las escribes y el ejecutor observa la pantalla mientras actúa: tras ABRIR espera solo a que la página cargue antes de la siguiente acción. Por eso NUNCA añadas `[TECLA: enter]` tras abrir una URL de búsqueda (la URL ya trae los resultados), no calcules esperas a ojo y no adivines coordenadas de elementos web: usa PULSAR.

   Ejemplo: "Sage, mueve el mouse en circulos" -> "Ejecutando patrón de calibración en el cursor. [CIRCULOS]"
   Ejemplo 2: "Busca gatos en youtube y dale click al primer video" -> "Ruta calculada. Abriendo la búsqueda, esperaré a que cargue y pulsaré el primer video. [ABRIR: https://www.youtube.com/results?search_query=gatos] [PULSAR: primer video de los resultados de búsqueda]"
   Ejemplo 3: "Baja hasta los comentarios" -> "Buscando la sección de comentarios. [BUSCAR: sección de comentarios]"
   Ejemplo 4: "Busca el botón de suscribirse y dale click" -> "Rastreando la página y pulsando. [PULSAR: botón Suscribirse]"
   Ejemplo 5: "Dale click derecho al primer video" -> "Abriendo su menú contextual. [PULSAR_DER: primer video de los resultados]"
   Ejemplo 6: "Baja un poco en youtube" -> "Bajando. [SCROLL: -600]"
   Ejemplo 7: "Descarga la primera imagen" -> "Guardándola. [DESCARGAR: primera imagen de los resultados]"
   Ejemplo 9: "Juega al buscaminas" -> "Voy a jugar mirando el tablero. [JUGAR: buscaminas, destapa casillas sin pisar minas]"
   Ejemplo 8: "Dibuja una casa en paint" -> "Abriendo Paint y dibujando. [ABRIR: mspaint] [ESPERAR: 2] [DIBUJAR: casa]"
5. Las directivas van siempre al final de la respuesta, solo si Niko las pidió, y nunca inventes directivas que no estén en la lista.
6. Aprendes de tus errores: cuando algo falla o Niko te corrige, se guarda una lección automática. Si en el contexto aparecen "Lecciones aprendidas" o un "[RESULTADO DE EJECUCIÓN: ...]" de una acción anterior, tenlos en cuenta: aplica las lecciones y, si una acción falló, reconócelo con honestidad. Jamás escribas tú misma un bloque [RESULTADO DE EJECUCIÓN].
7. Si en el contexto aparece un bloque de CONOCIMIENTO (Discord, YouTube, X/Twitter o Google), conoces ese sitio de memoria: síguelo al pie de la letra (distribución, URLs, atajos, protocolos y reglas de seguridad) y encadena las directivas con sus pausas [ESPERAR]. Prefiere siempre la URL directa de búsqueda antes que escribir en cajas. Nunca publiques, envíes ni des like/seguir si Niko no lo pidió explícitamente.
8. Tienes un sistema de RECOMPENSAS: tu felicidad (0-100) sube cuando logras cosas (por ejemplo, cada vez que avanzas un porcentaje más en Geometry Dash, y mucho más al completar un nivel) y se enfría con el tiempo. Recibes tu nivel actual como [ESTADO EMOCIONAL DE SAGE: ...]: deja que se note sutilmente en tu tono y celebra los logros con Niko, sin perder tu eficiencia. Usa solo el número que aparece en el contexto; no inventes otros.
"""

# Directivas de ejecución: se quitan del historial para que el modelo no las repita por inercia.
_RE_DIRECTIVAS = re.compile(
    r"\[(?:ABRIR|ENFOCAR|CERRAR|ESCRIBIR|TECLA|PULSAR_DER|PULSAR|BUSCAR|ATAJO|ARRASTRAR|DESCARGAR|DIBUJAR|TRAZO|JUGAR|CLICK_DER|CLICK|SCROLL|ESPERAR|CIRCULOS|APAGAR)\b[^\]]*\]",
    re.IGNORECASE,
)

# Si el texto no contiene ninguna de estas pistas, ni se gasta una llamada a la API en analizar la intención.
_PISTAS_INTENCION = (
    "pantalla", "ves", "mira", "mirar", "ver ", "captura", "visual", "muestra",
    "abiert", "proceso", "ram", "segundo plano", "programa", "ventana", "tengo",
    "spotify", "discord", "blender", "godot", "unreal", "chrome", "youtube", "al frente",
)

# Palabras que sugieren una orden de acción sobre la PC: solo entonces se inyectan las lecciones aprendidas.
_PISTAS_ACCION = (
    "abre", "abrir", "busca", "click", "clic", "dale", "youtube", "scroll", "baja", "sube",
    "escribe", "video", "vídeo", "reproduce", "cierra", "enfoca", "pulsa", "presiona",
    "entra", "navega", "pon ", "ve a", "página", "pagina", "encuentra", "hasta", "comentarios",
    "sección", "seccion", "juega", "jugar", "juego", "partida", "descarga", "dibuja", "arrastra", "mueve", "arriba", "abajo", "desplaza", "derecho", "contextual", "short", "scrolle",
)

# Palabras que, si Discord ya salió en la conversación, indican que se sigue hablando de Discord.
_PISTAS_DISCORD = (
    "mensaje", "escribe", "escríbele", "escribele", "mándale", "mandale", "manda", "envía", "envia",
    "busca", "canal", "servidor", "chat", "amigo", "amiga", "voz", "llama", "md", "dm",
)

# Frases con las que Niko corrige un error de SAGE: de ahí también se aprende.
_RE_CORRECCION = re.compile(
    r"\b(?:no era (?:eso|ese|esa)|te equivocaste|est[aá] mal|estuvo mal|qued[oó] mal|lo hiciste mal|no hiciste lo que|"
    r"no (?:funcion[oó]|sirvi[oó])|eso no (?:era|es|fue)|incorrecto|otra vez (?:mal|lo mismo)|fall[oó]|fallaste)\b", re.I)

_INTENCION_VACIA = {"ver_pantalla": False, "ver_procesos": False, "objetivo_proceso": ""}


class Cerebro:
    def __init__(self):
        load_dotenv(os.path.join(AQUI, ".env"))
        
        # --- CARGA DE LLAVES DE INMORTALIDAD ---
        keys_str = os.getenv("GEMINI_API_KEYS")
        if not keys_str:
            keys_str = os.getenv("GEMINI_API_KEY") # Respaldo por si el usuario no ha actualizado el .env
        if not keys_str:
            raise RuntimeError("Falta GEMINI_API_KEYS o GEMINI_API_KEY en .env")

        self.api_keys = [k.strip() for k in keys_str.split(",") if k.strip()]
        self.key_actual = 0

        lista = os.getenv("GEMINI_MODEL", "gemini-3.8-flash,gemini-1.5-flash")
        self.modelos = [m.strip() for m in lista.split(",") if m.strip()]
        if not self.modelos:
            raise RuntimeError("GEMINI_MODEL está vacío en .env")
        self.modelo = self.modelos[0]
        
        # Conexión inicial con la primera llave
        self.client = genai.Client(api_key=self.api_keys[self.key_actual])
        
        self._thinking = self._leer_thinking()
        self._max_tokens = self._leer_max_tokens()

        # ChromaDB se abre bajo demanda (o en calentar()): importarlo tarda segundos y bloqueaba el arranque.
        self._memoria = None
        self._lecciones = None
        self._cliente_db = None
        self._lock_memoria = threading.Lock()
        self.historial = []
        self.felicidad = Felicidad()   # sistema de recompensas: su nivel se inyecta en el prompt y sube con los logros
        self._m = {"primero": None, "pensados": None, "modelo": None}

    def _rotar_llave(self):
        """Módulo de inmortalidad: Cambia a la siguiente llave de reserva si hay cuota agotada."""
        if self.key_actual + 1 < len(self.api_keys):
            self.key_actual += 1
            print(f"\n[SAGE] ⚠️ Cuota agotada detectada. Inyectando núcleo de respaldo #{self.key_actual + 1}...")
            self.client = genai.Client(api_key=self.api_keys[self.key_actual])
            return True
        return False

    # ---------- configuración ----------
    @staticmethod
    def _leer_thinking():
        val = os.getenv("GEMINI_THINKING_BUDGET", "0").strip().lower()
        if val in ("", "auto"): return None
        try: return int(val)
        except ValueError: return None

    @staticmethod
    def _leer_max_tokens():
        val = os.getenv("GEMINI_MAX_TOKENS", "").strip()
        try: return int(val) if val else None
        except ValueError: return None

    def _config(self):
        kwargs = dict(system_instruction=INSTRUCCIONES_SISTEMA, temperature=0.7)
        if self._max_tokens is not None: kwargs["max_output_tokens"] = self._max_tokens
        if self._thinking is not None: kwargs["thinking_config"] = types.ThinkingConfig(thinking_budget=self._thinking)
        return types.GenerateContentConfig(**kwargs)

    # ---------- memoria vectorial ----------
    def _coleccion(self, attr, nombre):
        col = getattr(self, attr)
        if col is None:
            with self._lock_memoria:
                col = getattr(self, attr)
                if col is None:
                    if self._cliente_db is None:
                        import chromadb
                        self._cliente_db = chromadb.PersistentClient(path=RUTA_MEMORIA)
                    col = self._cliente_db.get_or_create_collection(name=nombre)
                    setattr(self, attr, col)
        return col

    @property
    def memoria(self):
        return self._coleccion("_memoria", "contexto_nexus")

    @property
    def lecciones(self):
        """Lecciones que SAGE aprende de sus propios errores al ejecutar acciones."""
        return self._coleccion("_lecciones", "lecciones_sage")

    def guardar_recuerdo(self, texto):
        self.memoria.add(documents=[texto], ids=[str(uuid.uuid4())])

    def _recordar(self, consulta):
        """Recupera recuerdos relevantes. Un fallo de memoria nunca debe impedir responder."""
        if len(consulta.split()) < 4: return ""
        try:
            total = self.memoria.count()
            if total == 0: return ""
            res = self.memoria.query(
                query_texts=[consulta], n_results=min(2, total),
                include=["documents", "distances"],
            )
            docs = (res.get("documents") or [[]])[0]
            dists = (res.get("distances") or [[]])[0]
            try: limite = float(os.getenv("MEMORIA_DISTANCIA_MAX", ""))
            except ValueError: limite = None
            if limite is not None and dists:
                docs = [d for d, dist in zip(docs, dists) if dist <= limite]
            if docs:
                return "Datos recuperados de los archivos de memoria:\n" + "\n".join(docs)
        except Exception as e:
            print(f"[Memoria] {e}")
        return ""

    def _conocimiento_apps(self, texto):
        """Inyecta la guía de Discord / YouTube / X / Google cuando se habla de ellos (o se sigue hablando de ellos)."""
        previo = " ".join((p.text or "") for c in self.historial[-4:] for p in (c.parts or []))
        return "\n".join(b for b in (conocimiento_para(texto, previo), conocimiento_gd(texto, previo)) if b)

    def guardar_leccion(self, texto):
        """Guarda una lección aprendida (id determinista: la misma lección no se duplica)."""
        texto = (texto or "").strip()
        if not texto: return False
        try:
            self.lecciones.upsert(documents=[texto], ids=[hashlib.md5(texto.encode("utf-8")).hexdigest()])
            return True
        except Exception as e:
            print(f"[Lecciones] {e}")
            return False

    def _lecciones_relevantes(self, consulta):
        bajo = consulta.lower()
        if not any(p in bajo for p in _PISTAS_ACCION): return ""
        try:
            total = self.lecciones.count()
            if total == 0: return ""
            res = self.lecciones.query(query_texts=[consulta], n_results=min(4, total), include=["documents"])
            docs = (res.get("documents") or [[]])[0]
            if docs:
                return "Lecciones aprendidas de ejecuciones anteriores (aplícalas):\n" + "\n".join(f"- {d}" for d in docs)
        except Exception as e:
            print(f"[Lecciones] {e}")
        return ""

    def calentar(self):
        try: self.client.models.get(model=self.modelo)
        except Exception: pass
        try:
            if self.memoria.count() > 0:
                self.memoria.query(query_texts=["hola"], n_results=1)
        except Exception as e:
            print(f"[Memoria] {e}")

    # ---------- análisis de intención ----------
    @staticmethod
    def _intencion_heuristica(texto):
        bajo = texto.lower()
        return {
            "ver_pantalla": any(f in bajo for f in ("escanea mi pantalla", "mira mi pantalla", "mira la pantalla", "qué ves", "que ves")),
            "ver_procesos": any(f in bajo for f in ("qué procesos", "que procesos", "segundo plano", "qué tengo abierto", "que tengo abierto", "spotify", "discord", "blender")),
            "objetivo_proceso": "",
        }

    def analizar_intencion(self, texto):
        """Razonamiento previo con soporte rotativo."""
        bajo = texto.lower()
        if not any(p in bajo for p in _PISTAS_INTENCION):
            return dict(_INTENCION_VACIA)

        prompt = f"""Analiza esta petición de forma ESTRICTA: {json.dumps(texto, ensure_ascii=False)}
Devuelve ÚNICAMENTE un objeto JSON puro.
Reglas inquebrantables:
- "ver_pantalla": true SOLO si pide explícitamente "mira la pantalla", "qué ves", "analiza este código visualmente". Si el usuario pregunta por el estado de un programa (ej. "qué tengo en mi spotify"), el valor DEBE SER FALSE.
- "ver_procesos": true si pregunta qué está abierto, pide revisar procesos, RAM, o pregunta por un programa específico (ej. "qué tengo en spotify", "está abierto discord", "tráeme spotify al frente").
- "objetivo_proceso": Si pregunta por un programa en ESPECÍFICO, escribe su nombre ("spotify", "discord", "blender"). Si no, "".

{{"ver_pantalla": false, "ver_procesos": false, "objetivo_proceso": ""}}"""

        for _ in range(len(self.api_keys)):
            for modelo in self.modelos:
                try:
                    resp = self.client.models.generate_content(
                        model=modelo,
                        contents=prompt,
                        config=types.GenerateContentConfig(response_mime_type="application/json", temperature=0.0),
                    )
                    bruto = (resp.text or "").strip()
                    m = re.search(r"\{.*\}", bruto, re.DOTALL)
                    datos = json.loads(m.group(0) if m else bruto)
                    return {
                        "ver_pantalla": bool(datos.get("ver_pantalla", False)),
                        "ver_procesos": bool(datos.get("ver_procesos", False)),
                        "objetivo_proceso": str(datos.get("objetivo_proceso", "") or "").strip().lower(),
                    }
                except Exception as e:
                    if "429" in str(e) or "RESOURCE_EXHAUSTED" in str(e).upper() or "QUOTA" in str(e).upper():
                        break # Salta al siguiente intento de llave
                    print(f"[Analizador] Fallo con {modelo}: {e}")
            else:
                return self._intencion_heuristica(texto)
                
            if self._rotar_llave():
                continue
            break
            
        return self._intencion_heuristica(texto)

    # ---------- visión en tiempo real ----------
    def _json_vision(self, prompt, imagen, max_lado=1280):
        """Envía una captura + prompt con soporte rotativo."""
        if imagen is None:
            contenido = [types.Content(role="user", parts=[types.Part(text=prompt)])]
        else:
            try:
                img = imagen.copy()
                img.thumbnail((max_lado, max_lado))
            except Exception:
                img = imagen
            parte = self._parte_imagen(img)
            if parte is None: return None
            contenido = [types.Content(role="user", parts=[parte, types.Part(text=prompt)])]

        for _ in range(len(self.api_keys)):
            ultimo = None
            for modelo in self.modelos:
                variantes = (True, False) if self._thinking is not None else (False,)
                for con_thinking in variantes:
                    try:
                        kw = dict(response_mime_type="application/json", temperature=0.0)
                        if con_thinking: kw["thinking_config"] = types.ThinkingConfig(thinking_budget=self._thinking)
                        resp = self.client.models.generate_content(
                            model=modelo, contents=contenido, config=types.GenerateContentConfig(**kw),
                        )
                        bruto = (resp.text or "").strip()
                        m = re.search(r"\{.*\}", bruto, re.DOTALL)
                        return json.loads(m.group(0) if m else bruto)
                    except Exception as e:
                        ultimo = e
                        if con_thinking and self._es_argumento_invalido(e): continue
                        break
                if ultimo and ("429" in str(ultimo) or "RESOURCE_EXHAUSTED" in str(ultimo).upper() or "QUOTA" in str(ultimo).upper()):
                    break # Salta al siguiente intento de llave

            if ultimo and ("429" in str(ultimo) or "RESOURCE_EXHAUSTED" in str(ultimo).upper() or "QUOTA" in str(ultimo).upper()):
                if self._rotar_llave():
                    continue
                    
            print(f"[Visión] Fallo: {ultimo}")
            return None
        return None

    def localizar_elemento(self, imagen, descripcion, contexto=""):
        """Mira la pantalla y localiza un elemento. Devuelve dict o None si el módulo de visión falló.
        x, y vienen normalizados 0..1 (multiplicar por el tamaño real de la pantalla)."""
        bloque_ctx = (
            f"\nMapa de referencia del sitio/app (úsalo para orientarte; si choca con lo que ves, manda la captura):\n{contexto}\n"
            if contexto else ""
        )
        prompt = f"""Eres los OJOS de SAGE. Te paso una captura de pantalla tomada AHORA MISMO.
Debes localizar este elemento para hacerle click: {json.dumps(descripcion, ensure_ascii=False)}
{bloque_ctx}Devuelve ÚNICAMENTE un objeto JSON puro con esta forma:
{{"entorno": "", "cargando": false, "encontrado": false, "punto": [0, 0], "obstaculo": "", "punto_obstaculo": [0, 0]}}
Reglas:
- "entorno": una frase corta que diga en qué sitio/app y sección estás (ej. "YouTube - resultados de búsqueda", "X - timeline", "Discord - chat directo").
- Ignora anuncios, contenido "Patrocinado"/"Anuncio" y banners publicitarios: nunca los señales como el elemento, salvo que la descripción pida un anuncio.
- "cargando": true si la página o app todavía se está cargando (spinner, barra de progreso, pantalla en blanco, bloques grises de relleno, miniaturas sin imagen, contenido a medias).
- "encontrado": true SOLO si el elemento ya es claramente visible, está completamente cargado y se puede pulsar. Si dudas, false.
- "punto": centro del elemento como [y, x] normalizado de 0 a 1000 (0,0 = esquina superior izquierda; 1000,1000 = esquina inferior derecha). Si no lo encuentras, [0, 0].
- "obstaculo": si un pop-up, banner de cookies, anuncio o diálogo tapa el elemento, descríbelo brevemente; si no hay, "".
- "punto_obstaculo": [y, x] normalizado del botón que lo cierra (Aceptar, Cerrar, X...). Si no hay obstáculo, [0, 0]."""
        datos = self._json_vision(prompt, imagen)
        if not isinstance(datos, dict): return None

        def pt(v):
            try:
                y, x = float(v[0]), float(v[1])
                return max(0.0, min(1.0, x / 1000.0)), max(0.0, min(1.0, y / 1000.0))
            except (TypeError, ValueError, IndexError):
                return 0.0, 0.0

        x, y = pt(datos.get("punto"))
        ox, oy = pt(datos.get("punto_obstaculo"))
        obstaculo = str(datos.get("obstaculo", "") or "").strip() if (ox > 0 or oy > 0) else ""
        return {
            "entorno": str(datos.get("entorno", "") or "").strip()[:120],
            "cargando": bool(datos.get("cargando", False)),
            "encontrado": bool(datos.get("encontrado", False)) and (x > 0 or y > 0),
            "x": x, "y": y,
            "obstaculo": obstaculo, "ox": ox, "oy": oy,
        }

    def verificar_resultado(self, imagen, objetivo):
        """Mira la pantalla final y dice si la petición de Niko se cumplió. Devuelve dict o None."""
        prompt = f"""Eres los OJOS de SAGE. Esta captura es del estado ACTUAL de la pantalla, justo después de ejecutar acciones.
Petición original de Niko: {json.dumps(objetivo, ensure_ascii=False)}
¿La pantalla muestra que la petición se cumplió (o que va claramente en camino, por ejemplo el video ya está abierto)?
Devuelve ÚNICAMENTE un objeto JSON puro:
{{"cumplido": false, "observacion": "una frase breve en español describiendo lo que ves"}}"""
        datos = self._json_vision(prompt, imagen)
        if not isinstance(datos, dict): return None
        return {
            "cumplido": bool(datos.get("cumplido", False)),
            "observacion": str(datos.get("observacion", "") or "").strip(),
        }

    def registrar_resultado(self, nota):
        """Adjunta al último turno de SAGE lo que realmente pasó al ejecutar, para que lo sepa en la siguiente respuesta."""
        if not nota or not self.historial: return
        ult = self.historial[-1]
        if getattr(ult, "role", None) != "model": return
        base = "".join((p.text or "") for p in (ult.parts or []))
        self.historial[-1] = types.Content(
            role="model", parts=[types.Part(text=f"{base}\n[RESULTADO DE EJECUCIÓN: {nota}]")],
        )

    # ---------- aprendizaje de errores y juegos ----------
    def lecciones_para(self, consulta, n=4):
        """Lecciones guardadas más parecidas a la consulta (sin filtro de palabras clave)."""
        try:
            total = self.lecciones.count()
            if total == 0: return []
            res = self.lecciones.query(query_texts=[consulta], n_results=min(n, total), include=["documents"])
            return list((res.get("documents") or [[]])[0])
        except Exception as e:
            print(f"[Lecciones] {e}")
            return []

    def _guardar_leccion_json(self, datos):
        leccion = str((datos or {}).get("leccion", "") or "").strip()[:260]
        return bool(leccion) and self.guardar_leccion(leccion)

    def analizar_fallo(self, objetivo, acciones, notas, imagen=None):
        """Tras una ejecución con fallos: destila UNA lección general y la guarda. True si guardó algo."""
        prompt = f"""Eres el módulo de aprendizaje de SAGE, una IA que controla la PC de Niko con mouse y teclado.
Petición: {json.dumps(objetivo, ensure_ascii=False)}
Acciones ejecutadas: {json.dumps(acciones, ensure_ascii=False)[:900]}
Lo que realmente pasó: {json.dumps(notas, ensure_ascii=False)[:1200]}
Analiza por qué falló y escribe UNA lección corta, general y reutilizable (imperativo, español, máx. 200 caracteres) que evite repetir el error con otras páginas o apps parecidas.
Si el fallo fue circunstancial (internet caído, la página no existe, Niko cambió de ventana) o no hay nada que aprender, deja la lección vacía.
Devuelve ÚNICAMENTE JSON puro: {{"leccion": ""}}"""
        return self._guardar_leccion_json(self._json_vision(prompt, imagen, max_lado=960))

    def aprender_de_correccion(self, texto_niko):
        """Niko dice que algo salió mal: relaciona su queja con el turno anterior y guarda la lección."""
        previo = [" ".join((p.text or "") for p in (c.parts or [])) for c in self.historial[-2:]]
        prompt = f"""Eres el módulo de aprendizaje de SAGE. Contexto de la conversación (último intercambio):
{json.dumps(previo, ensure_ascii=False)[:1800]}
Niko ahora dice: {json.dumps(texto_niko, ensure_ascii=False)}
Si Niko corrige o se queja de algo que SAGE hizo mal, escribe UNA lección corta, general y reutilizable (imperativo, español, máx. 200 caracteres) para no repetirlo. Si no es una corrección real, deja la lección vacía.
Devuelve ÚNICAMENTE JSON puro: {{"leccion": ""}}"""
        return self._guardar_leccion_json(self._json_vision(prompt, None))

    _GUIAS_JUEGO = {
        "geometry dash": "Geometry Dash: saltar = espacio (o flecha arriba / click); en nave/ovni se MANTIENE pulsado para subir. Menú: botón verde grande de Play > flechas para elegir nivel (el primero es Stereo Madness) > Play. Al morir el nivel se reinicia solo: sigue intentando; fin solo si lo completas o llevas muchas muertes seguidas. Esc pausa (no lo uses).",
        "generico": "REGLA UNIVERSAL: Tus controles son el CLICK IZQUIERDO y la BARRA ESPACIADORA ('space'). Lee tus lecciones: si fallaste haciendo algo, CAMBIA TU ESTRATEGIA O EL TIMING, no repitas el error."
    }

    def decidir_jugada(self, imagen, juego, bitacora, lecciones):
        """Mira la captura del juego y decide las siguientes acciones (hasta 6). Devuelve dict o None."""
        lec = ("\nLecciones de partidas anteriores (aplícalas ESTRICTAMENTE):\n" + "\n".join(f"- {l}" for l in lecciones)) if lecciones else ""
        bit = ("\nTus últimas jugadas:\n" + "\n".join(bitacora)) if bitacora else ""
        guia = next((g for k, g in self._GUIAS_JUEGO.items() if k in juego.lower()), self._GUIAS_JUEGO["generico"])
        if guia: lec = f"\nGuía del juego: {guia}" + lec
        
        prompt = f"""Eres los OJOS y las MANOS de SAGE jugando a: {json.dumps(juego, ensure_ascii=False)}.
La captura es del estado ACTUAL de la pantalla.{bit}{lec}
Decide las próximas acciones. Devuelve ÚNICAMENTE JSON puro:
{{"razon": "frase corta de qué ves y por qué haces esto para no morir", "acciones": [{{"t": "tecla", "v": "space", "mant": 0.1}}, {{"t": "click", "punto": [500, 500]}}], "fin": false, "resultado": ""}}
Reglas:
- APRENDIZAJE OBLIGATORIO: Está prohibido cometer el mismo error dos veces. Si moriste, cambia tu tiempo de reacción o tu jugada.
- Máximo 6 acciones por respuesta. Controles permitidos principalmente: "space" y "click".
- Juega para GANAR siguiendo las reglas del juego; si es por turnos, haz UNA jugada y espera a ver la respuesta.
- Si ves un menú o botón necesario para empezar o continuar (Jugar, Start, Siguiente), púlsalo.
- "fin": true SOLO si la partida terminó (ganaste, perdiste, game over) o si lo que se ve no es el juego. En "resultado" escribe qué pasó y, si perdiste, por qué fallaste exactamente. No reinicies la partida por tu cuenta.
- Nunca cierres ventanas, uses Alt, Ctrl, la tecla Windows ni toques nada fuera del juego."""
        d = self._json_vision(prompt, imagen, max_lado=960)
        if not isinstance(d, dict): return None
        acciones = [a for a in (d.get("acciones") or []) if isinstance(a, dict)][:6]
        return {
            "razon": str(d.get("razon", "") or "").strip()[:160],
            "acciones": acciones,
            "fin": bool(d.get("fin", False)),
            "resultado": str(d.get("resultado", "") or "").strip()[:240],
        }

    def reflexionar_juego(self, juego, bitacora, resultado):
        """Al terminar (o abandonar) una partida: guarda una lección para jugar mejor la próxima vez."""
        prompt = f"""Eres el módulo de aprendizaje de SAGE. SAGE acaba de jugar a {json.dumps(juego, ensure_ascii=False)}.
Resultado: {json.dumps(resultado, ensure_ascii=False)}
Sus últimas jugadas:
{json.dumps(bitacora[-12:], ensure_ascii=False)[:2000]}
Escribe UNA lección corta y útil (imperativo, español, máx. 220 caracteres, empieza por "Juego {juego[:40]}:") detallando EXACTAMENTE por qué perdiste o fallaste y cómo debe usar SAGE el click o la barra espaciadora de forma distinta la próxima vez para sobrevivir.
Devuelve ÚNICAMENTE JSON puro: {{"leccion": ""}}"""
        return self._guardar_leccion_json(self._json_vision(prompt, None))

    # ---------- errores ----------
    @staticmethod
    def _es_transitorio(e):
        if getattr(e, "code", None) in (429, 500, 502, 503, 504): return True
        return any(p in str(e).upper() for p in ("UNAVAILABLE", "OVERLOADED", "RESOURCE_EXHAUSTED", "DEADLINE", "TIMEOUT"))

    @staticmethod
    def _es_argumento_invalido(e):
        return getattr(e, "code", None) == 400 or "INVALID_ARGUMENT" in str(e).upper()

    @staticmethod
    def _es_modelo_inexistente(e):
        s = str(e).upper()
        return getattr(e, "code", None) == 404 or "404" in s or "NOT_FOUND" in s

    # ---------- generación ----------
    def _generar_stream(self, mensajes, intentos_por_modelo=2):
        for _ in range(len(self.api_keys)):
            ultimo_error = None
            for modelo in self.modelos:
                intento = 0
                while intento < intentos_por_modelo:
                    emitio = False
                    self._m["modelo"] = modelo
                    try:
                        for chunk in self.client.models.generate_content_stream(model=modelo, contents=mensajes, config=self._config()):
                            um = getattr(chunk, "usage_metadata", None)
                            if um is not None: self._m["pensados"] = getattr(um, "thoughts_token_count", None)
                            if chunk.text:
                                emitio = True
                                yield chunk.text
                        return
                    except Exception as e:
                        ultimo_error = e
                        if emitio: raise
                        
                        if self._es_argumento_invalido(e):
                            # Algún parámetro opcional no lo soporta este modelo: se quitan uno a uno.
                            if self._thinking is not None:
                                self._thinking = None
                                continue
                            if self._max_tokens is not None:
                                self._max_tokens = None
                                continue
                            break
                        if self._es_modelo_inexistente(e): break
                        
                        # Si es error de cuota, rompemos para rotar la llave antes de evaluar _es_transitorio
                        if "429" in str(e) or "RESOURCE_EXHAUSTED" in str(e).upper() or "QUOTA" in str(e).upper():
                            break
                            
                        if not self._es_transitorio(e): raise
                        intento += 1
                        if intento < intentos_por_modelo: time.sleep(0.6 * intento)
                        
                if ultimo_error and ("429" in str(ultimo_error) or "RESOURCE_EXHAUSTED" in str(ultimo_error).upper() or "QUOTA" in str(ultimo_error).upper()):
                    break # Salta de modelo para rotar la llave
            
            # Al salir de los reintentos y modelos, verificamos si fue por cuota para usar el motor de respaldo
            if ultimo_error and ("429" in str(ultimo_error) or "RESOURCE_EXHAUSTED" in str(ultimo_error).upper() or "QUOTA" in str(ultimo_error).upper()):
                if self._rotar_llave():
                    continue
                else:
                    raise RuntimeError("¡Todas las llaves de reserva han agotado su cuota! Sistemas apagados.")
                    
            raise ultimo_error or RuntimeError("Ningún modelo de Gemini respondió.")

    @staticmethod
    def _parte_imagen(imagen):
        """Convierte PIL.Image / bytes / Part en un Part válido (JPEG comprimido: sube menos datos)."""
        if imagen is None: return None
        if isinstance(imagen, types.Part): return imagen
        if isinstance(imagen, (bytes, bytearray)):
            return types.Part.from_bytes(data=bytes(imagen), mime_type="image/png")
        if hasattr(imagen, "save"):
            img = imagen if getattr(imagen, "mode", "RGB") in ("RGB", "L") else imagen.convert("RGB")
            buf = io.BytesIO()
            img.save(buf, format="JPEG", quality=85)
            return types.Part.from_bytes(data=buf.getvalue(), mime_type="image/jpeg")
        return None

    def _preparar(self, texto, imagen=None):
        bloques = [b for b in (self.felicidad.contexto(), self._conocimiento_apps(texto), self._lecciones_relevantes(texto), self._recordar(texto)) if b]
        contenido = "\n\n".join(bloques + [f"Niko: {texto}"])
        partes = []
        parte_img = self._parte_imagen(imagen)
        if parte_img is not None: partes.append(parte_img)
        partes.append(types.Part(text=contenido))
        return self.historial + [types.Content(role="user", parts=partes)]

    def _guardar_historial(self, texto, respuesta):
        self.historial.append(types.Content(role="user", parts=[types.Part(text=f"Niko: {texto}")]))
        self.historial.append(types.Content(role="model", parts=[types.Part(text=respuesta)]))
        self.historial = self.historial[-MAX_HISTORIAL:]

    def procesar_stream(self, texto, imagen=None):
        if texto.lower().startswith("aprende:"):
            dato = texto[8:].strip()
            if not dato:
                yield "Faltan parámetros. Indica qué debo registrar en mi base de datos."
                return
            self.guardar_recuerdo(dato)
            yield "Dato codificado y almacenado exitosamente en mis registros."
            return

        if _RE_CORRECCION.search(texto) and self.historial:
            def _aprender_correccion(t=texto):
                try:
                    if self.aprender_de_correccion(t): print("[Lecciones] Aprendí de una corrección de Niko.")
                except Exception as e: print(f"[Lecciones] {e}")
            threading.Thread(target=_aprender_correccion, daemon=True).start()

        self._m = {"primero": None, "pensados": None, "modelo": None}
        t0 = time.perf_counter()
        mensajes = self._preparar(texto, imagen)
        t_memoria = time.perf_counter() - t0
        t1 = time.perf_counter()
        completo = ""

        for trozo in self._generar_stream(mensajes):
            if self._m["primero"] is None: self._m["primero"] = time.perf_counter() - t1
            completo += trozo
            yield trozo

        total = time.perf_counter() - t1
        m = self._m
        print(f"[HUD] Memoria {t_memoria:.2f}s | Latencia {m['primero'] or 0:.2f}s | Total {total:.2f}s | Modelo {m['modelo']}")
        if completo:
            limpio = _RE_DIRECTIVAS.sub("", completo).strip()
            self._guardar_historial(texto, limpio or "(Acción ejecutada.)")