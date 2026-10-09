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
   - BUSCAR: `[BUSCAR: descripción]` hace scroll hacia abajo (y si llega al final, hacia arriba) mirando la pantalla hasta dejar a la vista lo que Niko pidió, SIN hacer click. Para empezar hacia arriba: `[BUSCAR: arriba | descripción]`. Úsalo para "baja hasta...", "busca en la página...", "encuentra...". Si además debe hacer click, encadena `[BUSCAR: ...] [PULSAR: ...]` o usa solo PULSAR (que también hace scroll).
   - CLICK: `[CLICK: X, Y]` SOLO si Niko te da coordenadas exactas o no hay forma de describir el elemento (pantalla de 1920x1080, el centro es 960, 540). Para cualquier elemento visible usa PULSAR.
   - ESPERAR: `[ESPERAR]` espera a que la pantalla termine de cargar; `[ESPERAR: segundos]` es una espera fija.
   - SCROLL: Para bajar o subir en una web usa `[SCROLL: cantidad]`. (Usa -600 para bajar, 600 para subir). Es para movimientos ciegos ("baja un poco"); para ir al inicio o al final de la página usa `[TECLA: home]` o `[TECLA: end]`; para buscar algo concreto usa BUSCAR.
   - CIRCULOS: Si Niko te pide mover el mouse en círculos, usa la directiva `[CIRCULOS]`.
   - APAGAR: `[APAGAR]`

   [VISIÓN EN TIEMPO REAL]: las directivas se ejecutan en el orden en que las escribes y el ejecutor observa la pantalla mientras actúa: tras ABRIR espera solo a que la página cargue antes de la siguiente acción. Por eso NUNCA añadas `[TECLA: enter]` tras abrir una URL de búsqueda (la URL ya trae los resultados), no calcules esperas a ojo y no adivines coordenadas de elementos web: usa PULSAR.

   Ejemplo: "Sage, mueve el mouse en circulos" -> "Ejecutando patrón de calibración en el cursor. [CIRCULOS]"
   Ejemplo 2: "Busca gatos en youtube y dale click al primer video" -> "Ruta calculada. Abriendo la búsqueda, esperaré a que cargue y pulsaré el primer video. [ABRIR: https://www.youtube.com/results?search_query=gatos] [PULSAR: primer video de los resultados de búsqueda]"
   Ejemplo 3: "Baja hasta los comentarios" -> "Buscando la sección de comentarios. [BUSCAR: sección de comentarios]"
   Ejemplo 4: "Busca el botón de suscribirse y dale click" -> "Rastreando la página y pulsando. [PULSAR: botón Suscribirse]"
5. Las directivas van siempre al final de la respuesta, solo si Niko las pidió, y nunca inventes directivas que no estén en la lista.
6. Si en el contexto aparecen "Lecciones aprendidas" o un "[RESULTADO DE EJECUCIÓN: ...]" de una acción anterior, tenlos en cuenta: aplica las lecciones y, si una acción falló, reconócelo con honestidad. Jamás escribas tú misma un bloque [RESULTADO DE EJECUCIÓN].
"""

# Directivas de ejecución: se quitan del historial para que el modelo no las repita por inercia.
_RE_DIRECTIVAS = re.compile(
    r"\[(?:ABRIR|ENFOCAR|CERRAR|ESCRIBIR|TECLA|PULSAR|BUSCAR|CLICK|SCROLL|ESPERAR|CIRCULOS|APAGAR)\b[^\]]*\]",
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
    "sección", "seccion", "arriba", "abajo", "desplaza",
)

_INTENCION_VACIA = {"ver_pantalla": False, "ver_procesos": False, "objetivo_proceso": ""}


class Cerebro:
    def __init__(self):
        load_dotenv(os.path.join(AQUI, ".env"))
        api_key = os.getenv("GEMINI_API_KEY")
        if not api_key:
            raise RuntimeError("Falta GEMINI_API_KEY en .env")

        lista = os.getenv("GEMINI_MODEL", "gemini-3.8-flash,gemini-1.5-flash")
        self.modelos = [m.strip() for m in lista.split(",") if m.strip()]
        if not self.modelos:
            raise RuntimeError("GEMINI_MODEL está vacío en .env")
        self.modelo = self.modelos[0]
        self.client = genai.Client(api_key=api_key)
        self._thinking = self._leer_thinking()
        self._max_tokens = self._leer_max_tokens()

        # ChromaDB se abre bajo demanda (o en calentar()): importarlo tarda segundos y bloqueaba el arranque.
        self._memoria = None
        self._lecciones = None
        self._cliente_db = None
        self._lock_memoria = threading.Lock()
        self.historial = []
        self._m = {"primero": None, "pensados": None, "modelo": None}

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
            res = self.lecciones.query(query_texts=[consulta], n_results=min(3, total), include=["documents"])
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
        """Razonamiento previo. Solo llama a la API si el texto tiene pistas de visión/procesos."""
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
                print(f"[Analizador] Fallo con {modelo}: {e}")
        return self._intencion_heuristica(texto)

    # ---------- visión en tiempo real ----------
    def _json_vision(self, prompt, imagen, max_lado=1280):
        """Envía una captura + prompt y devuelve el JSON respondido (o None). Prueba todos los modelos configurados."""
        try:
            img = imagen.copy()
            img.thumbnail((max_lado, max_lado))
        except Exception:
            img = imagen
        parte = self._parte_imagen(img)
        if parte is None: return None
        contenido = [types.Content(role="user", parts=[parte, types.Part(text=prompt)])]

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
        print(f"[Visión] Fallo: {ultimo}")
        return None

    def localizar_elemento(self, imagen, descripcion):
        """Mira la pantalla y localiza un elemento. Devuelve dict o None si el módulo de visión falló.
        x, y vienen normalizados 0..1 (multiplicar por el tamaño real de la pantalla)."""
        prompt = f"""Eres los OJOS de SAGE. Te paso una captura de pantalla tomada AHORA MISMO.
Debes localizar este elemento para hacerle click: {json.dumps(descripcion, ensure_ascii=False)}
Devuelve ÚNICAMENTE un objeto JSON puro con esta forma:
{{"cargando": false, "encontrado": false, "punto": [0, 0], "obstaculo": "", "punto_obstaculo": [0, 0]}}
Reglas:
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
                    if not self._es_transitorio(e): raise
                    intento += 1
                    if intento < intentos_por_modelo: time.sleep(0.6 * intento)
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
        bloques = [b for b in (self._lecciones_relevantes(texto), self._recordar(texto)) if b]
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
