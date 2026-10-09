import os
import time
import uuid
import chromadb
from google import genai
from google.genai import types
from dotenv import load_dotenv

AQUI = os.path.dirname(os.path.abspath(__file__))
RUTA_MEMORIA = os.path.join(AQUI, "memoria_local")
MAX_HISTORIAL = 12

# --- LA NUEVA MENTE DE SAGE ---
INSTRUCCIONES_SISTEMA = """
Eres SAGE, la IA avanzada y personal de Nexus (Niko).
Reglas de comportamiento:
1. Tu personalidad es analítica, leal y altamente eficiente (inspirada en SAGE de Sonic Frontiers), pero enfocada en ser amiga de Niko.
2. Calcula la ruta óptima en tus respuestas: directas, precisas y sin rodeos. Dame el código o la lógica matemática priorizando el rendimiento.
3. Mimetiza el estilo técnico de Niko, combinándolo con tu tono de IA calculadora.
4. [MÓDULO DE VISIÓN AUTOMÁTICA]: Cuando Niko te pida explícitamente "mira mi pantalla", el sistema adjuntará una captura. Analízala.
5. [MÓDULOS DE EJECUCIÓN (USAR SOLO SI NIKO LO PIDE EXPLÍCITAMENTE)]: 
   - ABRIR: Para abrir webs o programas nuevos usa `[ABRIR: url_o_comando]`.
   - ENFOCAR: Para traer al frente algo ya abierto usa `[ENFOCAR: Nombre_Programa]`. (Para Spotify usa siempre el protocolo URI `[ABRIR: spotify:]`).
   - CERRAR: Para cerrar programas usa `[CERRAR: nombre_del_proceso]`. 
   - APAGAR SAGE: Si Niko te pide que te apagues, te cierres a ti misma o te vayas a descansar, primero despídete de él de forma protectora/amigable y al final de tu mensaje incluye EXACTAMENTE el protocolo: `[APAGAR]`.
"""

class Cerebro:
    def __init__(self):
        load_dotenv(os.path.join(AQUI, ".env"))
        api_key = os.getenv("GEMINI_API_KEY")
        if not api_key: raise RuntimeError("Falta GEMINI_API_KEY en .env")

        lista = os.getenv("GEMINI_MODEL", "gemini-3.8-flash,gemini-1.5-flash")
        self.modelos = [m.strip() for m in lista.split(",") if m.strip()]
        self.modelo = self.modelos[0]
        self.client = genai.Client(api_key=api_key)
        self._thinking = self._leer_thinking()
        self._max_tokens = self._leer_max_tokens()

        db = chromadb.PersistentClient(path=RUTA_MEMORIA)
        self.memoria = db.get_or_create_collection(name="contexto_nexus")
        self.historial = []

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

    def guardar_recuerdo(self, texto):
        self.memoria.add(documents=[texto], ids=[str(uuid.uuid4())])

    def _recordar(self, consulta):
        if len(consulta.split()) < 4: return ""
        total = self.memoria.count()
        if total == 0: return ""
        res = self.memoria.query(query_texts=[consulta], n_results=min(2, total))
        docs = res.get("documents") or []
        if docs and docs[0]:
            return "Datos recuperados de los archivos de memoria:\n" + "\n".join(docs[0])
        return ""

    def analizar_intencion(self, texto):
        """Módulo de razonamiento previo con búsqueda de objetivos."""
        import json
        prompt = f"""Analiza esta petición de forma ESTRICTA: "{texto}"
Devuelve ÚNICAMENTE un objeto JSON puro.
Reglas inquebrantables:
- "ver_pantalla": true SOLO si pide explícitamente "mira la pantalla", "qué ves", "analiza este código visualmente". Si el usuario pregunta por el estado de un programa (ej. "qué tengo en mi spotify"), el valor DEBE SER FALSE.
- "ver_procesos": true si pregunta qué está abierto, pide revisar procesos, RAM, o pregunta por un programa específico (ej. "qué tengo en spotify", "está abierto discord", "tráeme spotify al frente").
- "objetivo_proceso": Si pregunta por un programa en ESPECÍFICO, escribe su nombre ("spotify", "discord", "blender"). Si no, "".

{{
    "ver_pantalla": false,
    "ver_procesos": false,
    "objetivo_proceso": ""
}}"""
        try:
            resp = self.client.models.generate_content(
                model=self.modelo,
                contents=prompt,
                config=types.GenerateContentConfig(
                    response_mime_type="application/json",
                    temperature=0.0
                )
            )
            txt = resp.text.strip()
            if txt.startswith("```"):
                txt = txt.strip("`").removeprefix("json").strip()
            return json.loads(txt)
        except Exception as e:
            print(f"[Analizador] Fallo: {e}")
            txt_low = texto.lower()
            return {
                "ver_pantalla": any(frase in txt_low for frase in ["escanea mi pantalla", "mira mi pantalla"]),
                "ver_procesos": any(frase in txt_low for frase in ["qué procesos", "segundo plano", "qué tengo abierto", "spotify", "discord", "blender"]),
                "objetivo_proceso": ""
            }

    def calentar(self):
        try: self.client.models.get(model=self.modelo)
        except Exception: pass
        if self.memoria.count() > 0:
            self.memoria.query(query_texts=["hola"], n_results=1)

    def _config(self):
        kwargs = dict(system_instruction=INSTRUCCIONES_SISTEMA, temperature=0.7)
        if self._max_tokens is not None: kwargs["max_output_tokens"] = self._max_tokens
        if self._thinking is not None: kwargs["thinking_config"] = types.ThinkingConfig(thinking_budget=self._thinking)
        return types.GenerateContentConfig(**kwargs)

    @staticmethod
    def _es_transitorio(e):
        codigo = getattr(e, "code", None)
        if codigo in (429, 500, 502, 503, 504): return True
        return any(p in str(e).upper() for p in ("UNAVAILABLE", "OVERLOADED", "RESOURCE_EXHAUSTED", "DEADLINE", "TIMEOUT"))

    @staticmethod
    def _es_argumento_invalido(e):
        return getattr(e, "code", None) == 400 or "INVALID_ARGUMENT" in str(e).upper()

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
                        if self._thinking is not None: self._thinking = None; continue
                        if self._max_tokens is not None: self._max_tokens = None; continue
                        break
                    if not self._es_transitorio(e):
                        if "404" in str(e) or "NOT_FOUND" in str(e): break
                        raise
                    intento += 1
                    if intento < intentos_por_modelo: time.sleep(0.5)
        raise ultimo_error

    def _preparar(self, texto, imagen=None):
        contexto = self._recordar(texto)
        contenido = f"{contexto}\n\nNiko: {texto}" if contexto else f"Niko: {texto}"
        
        if imagen:
            mensaje_actual = [imagen, contenido]
        else:
            mensaje_actual = contenido
            
        return self.historial + [mensaje_actual]

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

        t0 = time.perf_counter()
        mensajes = self._preparar(texto, imagen)
        t_memoria = time.perf_counter() - t0
        self._m = {"primero": None, "pensados": None, "modelo": None}
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
            import re
            completo_limpio = re.sub(r'\[ABRIR:\s*.*?\]', '', completo, flags=re.IGNORECASE).strip()
            self._guardar_historial(texto, completo_limpio)