"""Conocimiento de memoria de YouTube, X (Twitter), Google y Discord para SAGE.

- conocimiento_para(): guía completa (layout, atajos, URLs, protocolos) que cerebro.py inyecta cuando se habla del sitio.
- mapa_visual(): versión condensada que se le pasa al módulo de visión para que se oriente en la pantalla.

Las posiciones son aproximadas (pantalla 1920x1080, tema claro u oscuro, español o inglés): para hacer click en algo
SIEMPRE se usa [PULSAR: descripción visual], nunca coordenadas fijas.
"""
import re

from discord_conocimiento import CONOCIMIENTO_DISCORD

# =====================================================================
#  YOUTUBE
# =====================================================================
CONOCIMIENTO_YOUTUBE = """
=== CONOCIMIENTO DE YOUTUBE (de memoria, navegador de escritorio) ===

[DISTRIBUCIÓN DE LA INTERFAZ]
- BARRA SUPERIOR (fija): a la izquierda el menú hamburguesa (☰) y el logo de YouTube (clic = Inicio); en el CENTRO la caja de búsqueda con la lupa a su derecha (y el micrófono al lado); a la derecha el botón "Crear" (+ / cámara), la campana de notificaciones y tu avatar (menú de cuenta).
- MENÚ LATERAL IZQUIERDO: Inicio, Shorts, Suscripciones, y la sección "Tú": Historial, Playlists, Ver más tarde, Videos que me gustan, Tus videos; más abajo Explorar (Tendencias, Música, Juegos, Noticias...). Se oculta/muestra con el menú hamburguesa.
- INICIO: arriba una barra de "chips" de categorías (Todos, Música, Juegos...) y debajo una cuadrícula de miniaturas de videos (cada una con título, canal, vistas y fecha).
- RESULTADOS DE BÚSQUEDA: lista VERTICAL de videos (miniatura a la izquierda, título grande, canal, vistas, descripción corta). Arriba, el botón "Filtros" (fecha de subida, tipo, duración, características, orden). OJO: los primeros resultados pueden ser un ANUNCIO (marcado "Patrocinado"/"Anuncio") o un carrusel de Shorts; el "primer video" real es el primer resultado que NO es anuncio ni Short, salvo que Niko pida otra cosa.
- PÁGINA DE UN VIDEO: reproductor grande arriba a la izquierda. Debajo: título, nombre del canal con botón rojo/blanco "Suscribirse", botones Me gusta / No me gusta, Compartir, Guardar y "..." (más). Luego la descripción (clic en "...más" para expandirla) y MÁS ABAJO (hay que hacer scroll) los comentarios: arriba la caja "Añade un comentario...". La columna derecha tiene los videos recomendados / "A continuación".
- CONTROLES DEL REPRODUCTOR (barra inferior del video, aparece al pasar el ratón): reproducir/pausar, siguiente, volumen, tiempo, subtítulos (CC), engranaje de Ajustes (calidad, velocidad, subtítulos), modo cine, pantalla completa. Los anuncios muestran el botón "Saltar anuncio" abajo a la derecha del reproductor tras unos 5 s.
- PÁGINA DE UN CANAL: banner, avatar, nombre y @usuario, botón Suscribirse, y pestañas: Inicio, Videos, Shorts, En directo, Playlists, Comunidad/Publicaciones, Acerca de; con una lupa al final de las pestañas para buscar dentro del canal.

[ATAJOS DE TECLADO (con el foco en la página/reproductor, NO en una caja de texto)]
k o espacio = pausa/reproducir; j = retroceder 10 s; l = adelantar 10 s; flechas izquierda/derecha = ±5 s; flechas arriba/abajo = volumen; m = silenciar; f = pantalla completa; t = modo cine; c = subtítulos; i = minireproductor; 0-9 = saltar al 0%-90% del video; shift+n = siguiente video; shift+p = anterior; "<" y ">" = velocidad; "/" = ir a la caja de búsqueda; esc = salir de pantalla completa.

[URLS ÚTILES — la forma MÁS RÁPIDA Y FIABLE de buscar]
- Buscar: https://www.youtube.com/results?search_query=palabras+separadas+por+mas
- Solo videos (sin canales/listas): añadir &sp=EgIQAQ%3D%3D a la URL de búsqueda.
- Un canal: https://www.youtube.com/@usuario ; sus videos: https://www.youtube.com/@usuario/videos
- Historial: https://www.youtube.com/feed/history ; Ver más tarde: https://www.youtube.com/playlist?list=WL ; Suscripciones: https://www.youtube.com/feed/subscriptions
- Para buscar a un USUARIO/CANAL: https://www.youtube.com/results?search_query=nombre&sp=EgIQAg%3D%3D (filtro "Canal") y pulsar el primer resultado que tenga su nombre.

[PROTOCOLOS DE ACCIÓN]
* Buscar y reproducir el primer video:
  [ABRIR: https://www.youtube.com/results?search_query=gatos] [PULSAR: primer video de los resultados (que no sea anuncio ni Short)]
  (el ejecutor espera solo a que cargue; NO pongas enter ni coordenadas).
* Buscar desde la propia página: [PULSAR: caja de búsqueda de YouTube arriba al centro] [ESCRIBIR: texto] [TECLA: enter] [ESPERAR] [PULSAR: ...].
* Controlar el video ya abierto: [TECLA: k] (pausa/play), [TECLA: f] (pantalla completa), [TECLA: m] (silenciar), [TECLA: l] (adelantar 10 s), [TECLA: c] (subtítulos).
* Ir a los comentarios: [BUSCAR: sección de comentarios]. Escribir un comentario SOLO si Niko lo pide: [BUSCAR: sección de comentarios] [PULSAR: caja Añade un comentario] [ESCRIBIR: texto] [PULSAR: botón Comentar].
* Suscribirse / Me gusta: [PULSAR: botón Suscribirse debajo del video] / [PULSAR: botón Me gusta (pulgar arriba) debajo del video].
* Saltar anuncio: [PULSAR: botón Saltar anuncio abajo a la derecha del reproductor].
* Banner de cookies/consentimiento: el ejecutor lo detecta como obstáculo y lo cierra solo.

[SCROLL Y NAVEGACIÓN VERTICAL EN YOUTUBE]
- La rueda del mouse mueve la página con el cursor sobre casi cualquier zona (miniaturas, comentarios, columna de recomendados e incluso encima del reproductor, salvo en pantalla completa). El ejecutor lleva el cursor al centro de la pantalla y gira la rueda: [SCROLL: -600] = media pantalla hacia abajo, [SCROLL: -1200] = una pantalla, [SCROLL: -2400] = dos; con números POSITIVOS sube. Tras cada scroll espera a que la pantalla se asiente (scroll suave y miniaturas que cargan) y comprueba que la página se movió.
- INICIO y RESULTADOS: el feed es infinito, al bajar se cargan más videos. Tras un scroll largo encadena [ESPERAR: 1] antes de pulsar algo. No hay "final": para recorrer muchos videos encadena varios [SCROLL: -1200] o usa [BUSCAR: descripción] (hace scroll mirando la pantalla hasta encontrarlo).
- PÁGINA DE UN VIDEO: al bajar se pasa de reproductor a título/descripción y luego a los comentarios, que cargan al llegar (espera [ESPERAR: 1.5]). Para ir directo a ellos: [BUSCAR: sección de comentarios]. Para volver al reproductor: [SCROLL: 12000] (varias muescas seguidas).
- SHORTS (video vertical centrado, con me gusta / comentarios / compartir a su derecha): aquí NO se baja la página, se cambia de short. Siguiente = [TECLA: down], anterior = [TECLA: up] (la rueda también cambia de short si el cursor está sobre el video). El panel de comentarios de un Short tiene su propio scroll.
- PANTALLA COMPLETA / MODO CINE: en pantalla completa la página no se mueve. Sal primero con [TECLA: esc] y luego haz scroll.
- CUIDADO CON EL TECLADO: con el reproductor en foco, home = ir al inicio del video, end = saltar al final, espacio = pausar, flechas izq/der = ±5 s y flechas arriba/abajo = volumen. Para mover la PÁGINA no uses esas teclas: usa SCROLL (o [TECLA: pagedown] / [TECLA: pageup]).
- BARRA DE CATEGORÍAS (chips) del Inicio: se desplaza en horizontal; para ver más chips [PULSAR: flecha derecha ">" al final de la barra de categorías].
- Si el ejecutor informa que el scroll NO movió la página (pantalla completa, un Short, un diálogo abierto...), díselo a Niko con honestidad y propón la solución.

[CLIC DERECHO EN YOUTUBE]
- Clic derecho sobre el REPRODUCTOR abre el menú propio de YouTube: Bucle, Copiar URL del vídeo, Copiar URL del vídeo en este momento, Copiar código para insertar, Información de depuración, Solucionar problemas de reproducción y Estadísticas para nerds. Ejemplo: [PULSAR_DER: reproductor del video] [ESPERAR: 1] [PULSAR: opción Copiar URL del vídeo del menú]. (Normalmente, un segundo clic derecho sobre ese menú abre el menú normal del navegador.)
- Clic derecho sobre una MINIATURA, un título o un enlace: menú del navegador (Abrir en una pestaña nueva, Copiar dirección del enlace...). Ejemplo: [PULSAR_DER: primer video de los resultados (que no sea anuncio)] [ESPERAR: 1] [PULSAR: opción Copiar dirección del enlace].
- El menú contextual queda abierto tras el clic derecho: elige la opción que Niko pidió o ciérralo con [TECLA: esc]. Si no pidió ninguna opción, no elijas nada.

[REGLAS]
- No comentes, no te suscribas ni des like si Niko no lo pidió.
- Evita siempre anuncios ("Patrocinado") al elegir un video.
=== FIN DEL CONOCIMIENTO DE YOUTUBE ===
"""

MAPA_YOUTUBE = """YouTube: barra superior fija (menú ☰ y logo a la izquierda, caja de búsqueda con lupa en el centro, Crear/campana/avatar a la derecha). Menú lateral izquierdo (Inicio, Shorts, Suscripciones, Tú). En Inicio: chips de categorías arriba y cuadrícula de miniaturas. En resultados: lista vertical de videos (el primero puede ser anuncio "Patrocinado" o carrusel de Shorts; ignóralos). En un video: reproductor arriba-izquierda, debajo título, canal + botón Suscribirse, Me gusta, Compartir, Guardar; comentarios más abajo; recomendados en la columna derecha; "Saltar anuncio" abajo-derecha del reproductor. Shorts: video vertical centrado con me gusta / comentarios / compartir a su derecha (se cambia de short con las flechas arriba/abajo). Un clic derecho sobre el reproductor abre el menú propio de YouTube (Bucle, Copiar URL del vídeo, Estadísticas para nerds...)."""

# =====================================================================
#  X / TWITTER
# =====================================================================
CONOCIMIENTO_TWITTER = """
=== CONOCIMIENTO DE X / TWITTER (de memoria, navegador de escritorio, https://x.com) ===
Hay que tener la sesión iniciada. Si aparece la pantalla de "Iniciar sesión", díselo a Niko: no introduzcas credenciales por tu cuenta.

[DISTRIBUCIÓN DE LA INTERFAZ, de izquierda a derecha]
1. MENÚ LATERAL IZQUIERDO: logo X (Inicio), Inicio, Explorar, Notificaciones, Mensajes, Grok, Listas, Marcadores, Comunidades, Premium, Perfil, "Más", y el botón azul grande "Postear" / "Post". Abajo del todo, tu cuenta (avatar + @usuario).
2. COLUMNA CENTRAL (timeline): arriba las pestañas "Para ti" y "Siguiendo"; debajo el COMPOSER ("¿Qué está pasando?" / "What's happening?") con botón azul "Postear" a su derecha; luego los posts. Cada post tiene abajo una barra de acciones: Responder, Repostear, Me gusta, Vistas, Guardar/Marcador y Compartir.
3. COLUMNA DERECHA: arriba la CAJA DE BÚSQUEDA ("Buscar"), luego "Suscríbete a Premium", "Qué está pasando" (tendencias) y "A quién seguir".
- PERFIL DE UN USUARIO: banner, avatar, nombre y @usuario, botones "Seguir" (y sobre mensaje/campana/"..."), y pestañas: Posts, Respuestas, Destacados, Multimedia, Me gusta.
- MENSAJES: a la izquierda la lista de conversaciones con un icono de sobre con "+" (nuevo mensaje) y una lupa para buscar; a la derecha la conversación abierta con la caja "Escribe un mensaje" abajo.

[ATAJOS DE TECLADO (con el foco en la página, no en una caja de texto)]
n = nuevo post; "/" = ir a la búsqueda; j / k = siguiente / anterior post; l = me gusta; r = responder; t = repostear; b = guardar; enter = abrir el post; g luego h = Inicio; g luego p = perfil; g luego n = notificaciones; g luego m = mensajes; "?" = ver todos los atajos. En el composer: ctrl+enter = PUBLICAR el post.

[URLS ÚTILES — la forma MÁS RÁPIDA Y FIABLE]
- Buscar posts: https://x.com/search?q=palabras&src=typed_query ; más recientes: añadir &f=live ; PERSONAS: añadir &f=user ; con imágenes/video: &f=media
- Perfil de un usuario: https://x.com/usuario (sin la @)
- Escribir un post: https://x.com/compose/post (abre el composer con el foco en la caja) ; con texto ya escrito: https://x.com/intent/post?text=texto+con+mas
- Mensajes: https://x.com/messages ; nuevo mensaje: https://x.com/messages/compose
- Notificaciones: https://x.com/notifications ; Marcadores: https://x.com/i/bookmarks
- Operadores de búsqueda: from:usuario, to:usuario, @usuario, "frase exacta", palabra1 OR palabra2, -excluir, since:AAAA-MM-DD, until:AAAA-MM-DD, min_faves:100, filter:media, filter:links, lang:es.

[PROTOCOLOS DE ACCIÓN]
* Buscar un USUARIO y entrar a su perfil:
  [ABRIR: https://x.com/search?q=nombre&f=user] [PULSAR: primer perfil de la lista de personas]  (si Niko ya sabe el @, directo: [ABRIR: https://x.com/usuario]).
* Buscar posts de un tema: [ABRIR: https://x.com/search?q=tema&f=live] y luego [PULSAR: ...] o [BUSCAR: ...] sobre lo que pida.
* ESCRIBIR / PUBLICAR un post: [ABRIR: https://x.com/compose/post] [ESPERAR] [ESCRIBIR: texto del post] [ATAJO: ctrl+enter]   (máx. 280 caracteres en cuentas gratuitas; si falla ctrl+enter: [PULSAR: botón azul Postear del composer]).
* ENVIAR UN MENSAJE DIRECTO (MD):
  [ABRIR: https://x.com/messages/compose] [ESPERAR] [ESCRIBIR: usuario] [ESPERAR: 1.5] [PULSAR: primer resultado de persona en la lista] [PULSAR: botón Siguiente] [ESPERAR: 1] [ESCRIBIR: mensaje] [TECLA: enter]
  Alternativa si ya hay conversación: [ABRIR: https://x.com/messages] [PULSAR: la conversación con esa persona] [PULSAR: caja Escribe un mensaje abajo] [ESCRIBIR: mensaje] [TECLA: enter].
  (Algunas cuentas no aceptan MD de desconocidos: si no aparece la opción, díselo a Niko.)
* RESPONDER a un post: [PULSAR: icono de responder (burbuja) del post] [ESCRIBIR: texto] [ATAJO: ctrl+enter].
* Me gusta / Repostear / Guardar: [PULSAR: icono de corazón del post] / [PULSAR: icono de repostear del post] / [PULSAR: icono de marcador del post].
* Seguir a alguien: abre su perfil y [PULSAR: botón Seguir del perfil].
* Más posts en el timeline: [SCROLL: -600] o [BUSCAR: lo que pida].

[REGLAS]
- NUNCA publiques, respondas, envíes un MD, sigas o des like si Niko no lo pidió explícitamente con el contenido claro. Si falta el texto o el destinatario, pregúntalo.
- Escribe el texto tal como Niko lo dictó.
=== FIN DEL CONOCIMIENTO DE X ===
"""

MAPA_TWITTER = """X/Twitter: menú lateral izquierdo (logo X, Inicio, Explorar, Notificaciones, Mensajes, Listas, Perfil, Más, botón azul grande Postear). Columna central: pestañas Para ti/Siguiendo, composer "¿Qué está pasando?" con botón azul Postear, y posts con barra de acciones inferior (responder, repostear, me gusta, vistas, guardar, compartir). Columna derecha: caja Buscar arriba, tendencias, a quién seguir. Perfil: banner, avatar, botón Seguir, pestañas Posts/Respuestas/Multimedia/Me gusta. Mensajes: lista de chats a la izquierda (sobre con + = nuevo mensaje) y conversación a la derecha con caja de texto abajo. Ignora los posts marcados "Anuncio"."""

# =====================================================================
#  GOOGLE
# =====================================================================
CONOCIMIENTO_GOOGLE = """
=== CONOCIMIENTO DE GOOGLE (de memoria, navegador de escritorio) ===

[DISTRIBUCIÓN DE LA INTERFAZ]
- PÁGINA PRINCIPAL (google.com): arriba a la derecha los enlaces Gmail e Imágenes, el icono de aplicaciones (cuadrícula de 9 puntos) y tu avatar (o "Iniciar sesión"). En el CENTRO: logo de Google, la CAJA DE BÚSQUEDA con lupa a la izquierda y, a la derecha, micrófono (voz) y cámara (Google Lens); debajo dos botones: "Buscar con Google" y "Voy a tener suerte". Es habitual un banner de cookies ("Aceptar todo" / "Rechazar todo") en la primera visita.
- PÁGINA DE RESULTADOS: arriba la caja de búsqueda (con el texto escrito) y a la derecha avatar/apps. Debajo, las PESTAÑAS: Todo, Imágenes, Videos, Noticias, Mapas, Libros, Vuelos, Finanzas, "Más", y el botón "Herramientas" (fecha, idioma...). Después: a veces un bloque "Vista creada con IA" (resumen), anuncios marcados "Patrocinado" (arriba y abajo: IGNÓRALOS), y los RESULTADOS ORGÁNICOS: cada uno con el sitio y su URL en gris pequeño, el TÍTULO grande en azul (es el enlace que se pulsa) y debajo un fragmento. Puede haber "Otras preguntas de los usuarios", videos, imágenes y noticias intercalados. Al final de la página: la paginación "Más resultados" / números 1 2 3 ... "Siguiente".
- RESPUESTAS RÁPIDAS: arriba de los resultados aparecen directamente calculadora, conversor, clima, traductor, definiciones, resultados deportivos, etc. (no hace falta abrir ningún resultado).
- GOOGLE IMÁGENES: cuadrícula de miniaturas; al pulsar una se abre un panel lateral con la imagen grande y el botón "Visitar".
- GOOGLE MAPS: caja "Buscar en Google Maps" arriba a la izquierda, mapa a la derecha, resultados en lista a la izquierda con botones Cómo llegar / Guardar / Compartir.

[URLS ÚTILES — la forma MÁS RÁPIDA Y FIABLE]
- Buscar: https://www.google.com/search?q=palabras+separadas+por+mas
- Imágenes: añadir &tbm=isch ; Videos: &tbm=vid ; Noticias: &tbm=nws ; Libros: &tbm=bks
- Mapas: https://www.google.com/maps/search/lugar ; ruta: https://www.google.com/maps/dir/origen/destino
- Traductor: https://translate.google.com/?sl=auto&tl=es&text=texto&op=translate
- Gmail: https://mail.google.com ; escribir un correo ya rellenado: https://mail.google.com/mail/?view=cm&fs=1&to=correo@dominio.com&su=asunto&body=texto
- Drive: https://drive.google.com ; Calendario: https://calendar.google.com ; Docs: https://docs.google.com
- Operadores de búsqueda: "frase exacta", site:dominio.com, filetype:pdf, -excluir, palabra1 OR palabra2, intitle:palabra, inurl:palabra, define:palabra, after:AAAA-MM-DD, before:AAAA-MM-DD.

[BUSCAR PERSONAS / USUARIOS]
Google no tiene "usuarios": se busca a la persona por nombre y se acota con operadores, p. ej. "nombre apellido" site:linkedin.com/in , "nombre" site:x.com , "nombre" site:instagram.com , "nombre" site:youtube.com. Para ver redes de alguien, mira los títulos de los resultados que contengan su nombre.

[ATAJOS DE TECLADO]
"/" = enfocar la caja de búsqueda (en la página de resultados); ctrl+l = barra de direcciones del navegador; ctrl+t = nueva pestaña; ctrl+w = cerrar pestaña; ctrl+tab = siguiente pestaña; alt+left = atrás; f5 = recargar. En Gmail (con atajos activados): c = redactar, ctrl+enter = ENVIAR.

[PROTOCOLOS DE ACCIÓN]
* Buscar algo: [ABRIR: https://www.google.com/search?q=texto+a+buscar]  (NO añadas enter; la URL ya trae los resultados).
* Abrir el primer resultado real: [ABRIR: https://www.google.com/search?q=texto] [PULSAR: título azul del primer resultado orgánico (no anuncio, no resumen de IA)].
* Buscar escribiendo en la caja de la página abierta: [PULSAR: caja de búsqueda de Google] [ESCRIBIR: texto] [TECLA: enter] [ESPERAR].
* Cambiar a imágenes/noticias/mapas: [PULSAR: pestaña Imágenes debajo de la caja de búsqueda] (o la URL con &tbm=).
* Siguiente página de resultados: [BUSCAR: botón Siguiente al final de los resultados] [PULSAR: botón Siguiente].
* Escribir un correo: [ABRIR: https://mail.google.com/mail/?view=cm&fs=1&to=...&su=...&body=...] [ESPERAR] y, SOLO si Niko pidió enviarlo, [ATAJO: ctrl+enter]. Si el correo no estaba completo, no lo envíes: pregunta.
* Banner de cookies: el ejecutor lo detecta como obstáculo y lo despeja solo.

[REGLAS]
- Nunca pulses anuncios ("Patrocinado") ni el resumen de IA como si fuera un resultado, salvo que Niko lo pida.
- No envíes correos ni mensajes sin una orden explícita y con el contenido claro.
=== FIN DEL CONOCIMIENTO DE GOOGLE ===
"""

MAPA_GOOGLE = """Google: página principal con logo y caja de búsqueda al centro (lupa, micrófono y cámara), botones "Buscar con Google"/"Voy a tener suerte" debajo, y arriba a la derecha Gmail, Imágenes, apps (9 puntos) y avatar. Resultados: caja de búsqueda arriba; pestañas Todo/Imágenes/Videos/Noticias/Mapas/Más y botón Herramientas; luego posible bloque "Vista creada con IA" y anuncios "Patrocinado" (ignóralos); resultados orgánicos con URL en gris y TÍTULO azul grande (ese es el enlace); abajo la paginación "Siguiente". Banner de cookies al principio ("Aceptar todo"/"Rechazar todo"). Gmail: lista de correos al centro, botón Redactar arriba a la izquierda, carpetas en la columna izquierda."""

MAPA_DISCORD = """Discord: barra de servidores en el borde izquierdo (logo de Discord = Inicio arriba, iconos redondos de servidores, "+" al final); columna de canales/MD junto a ella (en Inicio: caja "Buscar o iniciar una conversación", Amigos, lista de Mensajes directos); panel de usuario abajo a la izquierda (avatar, micrófono, auriculares, engranaje de ajustes; encima, "Conexión de voz" con botón de colgar si estás en voz); zona central de chat con cabecera (nombre, iconos de hilos/notificaciones/fijados/miembros y caja Buscar a la derecha), mensajes y CAJA DE TEXTO abajo ("Enviar mensaje a..."); lista de miembros o perfil en la columna derecha."""

# =====================================================================
#  SELECCIÓN
# =====================================================================
# clave -> (patrón que lo detecta, guía completa, mapa visual condensado)
SITIOS = {
    "discord": (re.compile(r"discord"), CONOCIMIENTO_DISCORD, MAPA_DISCORD),
    "youtube": (re.compile(r"youtube|youtu\.be|\byt\b"), CONOCIMIENTO_YOUTUBE, MAPA_YOUTUBE),
    "x": (
        re.compile(r"twitter|\btuit|\btweet|\bx\.com\b|\ben x\b|\bred social x\b|\bpost(ear|ea)? en x\b|\bdm (de|en) x\b"),
        CONOCIMIENTO_TWITTER, MAPA_TWITTER,
    ),
    "google": (re.compile(r"google|gmail|googlea"), CONOCIMIENTO_GOOGLE, MAPA_GOOGLE),
}

# Si el sitio salió hace poco en la conversación, estas palabras indican que se sigue hablando de él.
_SEGUIR = (
    "mensaje", "escribe", "escríbele", "escribele", "mándale", "mandale", "manda", "envía", "envia",
    "busca", "canal", "servidor", "chat", "amig", "voz", "llama", "usuario", "perfil", "video", "vídeo",
    "comenta", "publica", "twitea", "tuitea", "dale", "abre", "siguiente", "primero", "resultado",
    "suscrib", "sigue", "like", "me gusta", "baja", "sube", "post", "correo", "imagen", "noticia",
)


def conocimiento_para(texto, previo=""):
    """Devuelve la(s) guía(s) relevantes para esta petición ("" si no se habla de ninguno de los sitios)."""
    bajo = (texto or "").lower()
    ant = (previo or "").lower()
    directos = [k for k, (pat, _, _) in SITIOS.items() if pat.search(bajo)]
    if directos:
        return "\n".join(SITIOS[k][1] for k in directos[:2])
    if any(p in bajo for p in _SEGUIR):
        previos = [k for k, (pat, _, _) in SITIOS.items() if pat.search(ant)]
        if previos:
            return SITIOS[previos[-1]][1]
    return ""


def mapa_visual(texto):
    """Mapa condensado del/los sitios detectados en `texto` (dominio + descripción + objetivo) para el módulo de visión."""
    bajo = (texto or "").lower()
    claves = [k for k, (pat, _, _) in SITIOS.items() if pat.search(bajo)]
    return "\n\n".join(SITIOS[k][2] for k in claves[:2])
