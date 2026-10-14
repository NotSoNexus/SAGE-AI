"""Conocimiento de memoria de la interfaz de Discord en CELULAR (app móvil Android / iOS) para SAGE.

web_conocimiento.py lo inyecta en el contexto cuando Niko habla de Discord Y de su celular, y entrega MAPA_DISCORD_CELULAR
al módulo de visión cuando SAGE toca cosas en el celular (CEL_TOCAR).

Fuentes (comprobadas en octubre de 2026): documentación oficial de Discord (artículo «You Bar FAQ», blog «Introducing: You Bar»,
«New Mobile App Updates & Layout») y su blog de rediseño móvil. Discord reparte los cambios de interfaz poco a poco y por
experimentos, así que hay DOS diseños posibles: la «You Bar» (el estándar actual, que no se puede desactivar) y el anterior de
cuatro pestañas. Por eso la guía obliga a MIRAR la captura antes de actuar: nunca asumas cuál diseño tiene el celular.
Posiciones aproximadas; para tocar algo SIEMPRE se usa [CEL_TOCAR: descripción visual], nunca coordenadas.
"""

CONOCIMIENTO_DISCORD_CELULAR = """
=== CONOCIMIENTO DE DISCORD EN CELULAR (app móvil Android/iOS, de memoria) ===

[PRIMERO: ¿QUÉ DISEÑO TIENE EL CELULAR? — míralo en la captura antes de actuar]
Discord móvil tiene hoy dos diseños de navegación inferior. Identifícalo por lo que se ve ABAJO de la pantalla:
 A) «YOU BAR» (estándar actual, no se puede desactivar): una barra-tarjeta redondeada y ancha, flotando abajo, con TU AVATAR + tu nombre + tu estado a la izquierda y un botón de CAMPANA (notificaciones) a la derecha. No hay pestañas con texto.
 B) DISEÑO ANTERIOR de 4 pestañas: barra inferior con cuatro iconos: Inicio/Servidores, Mensajes, Notificaciones (campana) y «Tú» (tu avatar). En algunas versiones «Servidores» y «Mensajes» eran pestañas separadas.
Las dos barras SE OCULTAN al abrir un canal o un chat (para dejar sitio al teclado y los mensajes): para verlas, vuelve atrás o desliza el panel.

[GESTOS Y PANELES (valen en los dos diseños)]
- Discord móvil usa PANELES DESLIZABLES (no hay menú lateral): se desliza desde CUALQUIER punto de la pantalla, no hace falta empezar en el borde.
- Dentro de un canal o chat: deslizar a la DERECHA (CEL_DESLIZAR: derecha) abre los paneles de la izquierda: primero la lista de canales y, más a la izquierda, la columna de servidores. Deslizar a la IZQUIERDA (CEL_DESLIZAR: izquierda) abre el panel derecho: la lista de MIEMBROS del servidor (o el perfil de la persona en un MD).
- Volver al chat desde un panel: deslizar en sentido contrario o tocar la parte visible del chat.
- Botón físico/gesto «atrás» (CEL_TECLA: atras): sube un nivel (de un chat a la lista de canales, etc.).

[YOU BAR — qué hace cada cosa (documentación oficial)]
- TOCAR la You Bar = abre TU PERFIL (editar perfil, Quests/Misiones, Tienda, Ajustes, amigos...). En esa pantalla el ENGRANAJE de Ajustes está ARRIBA A LA DERECHA.
- MANTENER PRESIONADO (pulsación larga) la You Bar = abre el MENÚ DE CUENTA: ahí se cambia el ESTADO (En línea, Ausente, No molestar, Invisible) y de cuenta.
- DESLIZAR de IZQUIERDA A DERECHA sobre la You Bar = alterna entre tus MENSAJES DIRECTOS (MD) y el SERVIDOR que tienes abierto. Es la forma más rápida de ir y volver de los MD.
- La CAMPANA a la derecha de la You Bar abre las NOTIFICACIONES (menciones, solicitudes de amistad, respuestas, eventos). Cada notificación es tocable y te lleva al mensaje original; se marcan como leídas con solo verlas.
- En versiones recientes mantener presionado el avatar de la You Bar puede llevar directo a Ajustes.

[DISEÑO ANTERIOR (4 pestañas) — equivalencias]
- Pestaña INICIO/SERVIDORES (abajo a la izquierda): columna de iconos de servidores a la izquierda + lista de canales del servidor elegido.
- Pestaña MENSAJES: todos tus MD y grupos, con la barra de búsqueda arriba, la fila «Activos ahora»/actividad de amigos y los chats favoritos fijados.
- Pestaña NOTIFICACIONES (campana): igual que la campana de la You Bar.
- Pestaña TÚ (tu avatar, abajo a la derecha): perfil, estado, amigos y Ajustes (engranaje arriba a la derecha). Tocar DOS VECES esa pestaña salta directo a Ajustes.

[PANTALLAS, de lo general a lo particular]
1. LISTA DE SERVIDORES Y CANALES: columna estrecha de iconos redondos de servidores en el borde izquierdo (con un puntito/pastilla blanca a la izquierda si hay mensajes sin leer, insignia roja con número si hay menciones). Arriba suele estar el icono de Discord/«Inicio» (lleva a los MD) y al final el botón «+» (crear/unirse a un servidor) y la brújula (Descubrir). A la derecha de esa columna, la LISTA DE CANALES: arriba el NOMBRE DEL SERVIDOR (tocarlo abre su menú: invitar, notificaciones, ajustes del servidor...) con iconos de búsqueda e invitar; debajo categorías plegables con canales de texto (#), de voz (altavoz), anuncios (megáfono) y foros. Los canales con texto en BLANCO/negrita tienen mensajes sin leer.
2. CHAT DE UN CANAL / MD: arriba la CABECERA con la flecha de volver o el icono del menú, el nombre del canal (#general) o de la persona y, a la derecha, iconos de buscar (lupa), hilos y miembros (según la versión). En medio los MENSAJES (avatar, nombre, hora, texto). Abajo, el COMPOSITOR.
3. COMPOSITOR (caja de mensaje, borde inferior, encima del teclado): a la izquierda el botón «+» (adjuntar: fotos, archivos, cámara, GIF, apps, crear hilo, encuesta); en el centro el campo de texto «Mensaje a #canal» / «Mensaje a @persona»; dentro o junto al campo, iconos de GIF, stickers y emojis; a la derecha el botón ENVIAR (flecha/avioncito, SOLO aparece cuando ya hay texto escrito) y, con el campo vacío, el micrófono de nota de voz. Las formas son redondeadas-cuadradas (squircle) en los diseños nuevos.
4. LISTA DE MENSAJES DIRECTOS: arriba la BARRA DE BÚSQUEDA («Buscar»; busca personas, mensajes, archivos y fijados en todos tus chats) y un botón de «Nuevo mensaje» (lápiz/«+») para empezar un MD o grupo; debajo las conversaciones (avatar, nombre, último mensaje, hora; punto o número si hay sin leer), con los favoritos arriba.
5. CANAL DE VOZ: al tocar un canal de voz se abre su pantalla con los participantes y un botón «Unirse a voz». Dentro de la llamada, barra de controles: micrófono (silenciar), cámara, compartir pantalla, salida de audio (altavoz/auriculares), «…» (más) y COLGAR (teléfono rojo). Mientras estás en voz y navegas por otras pantallas aparece una mini-barra de voz encima de la You Bar/barra inferior con el micrófono y el botón de colgar.
6. PERFIL / «TÚ»: avatar grande, nombre, estado, «Editar perfil», Amigos (con solicitudes pendientes y «Añadir amigo»), Quests, Tienda y el engranaje de AJUSTES (arriba a la derecha).
7. AJUSTES: lista con barra de búsqueda arriba: Cuenta, Contenido y social, Datos y privacidad, Apps autorizadas, Dispositivos, Conexiones, Notificaciones, Voz y vídeo, Chat, Accesibilidad, Apariencia, Idioma, Avanzado, Ayuda... La barra de búsqueda de Ajustes es lo más rápido para llegar a una opción.

[ACCIONES SOBRE UN MENSAJE]
- MANTENER PRESIONADO un mensaje abre su menú: fila rápida de reacciones (emojis) y opciones: Responder, Editar (solo los tuyos), Copiar texto, Crear hilo, Fijar, Reenviar, Marcar como no leído, Eliminar (en rojo) y más. Describe la opción por su texto/icono: «opción Responder del menú del mensaje».
- NUNCA elijas Eliminar, Reportar, Bloquear, Expulsar, Banear ni Salir del servidor sin una orden explícita de Niko.

[PROTOCOLOS DE ACCIÓN FIABLES (celular) — SOLO si Niko lo pide explícitamente]
Siempre en este orden: abrir Discord, MIRAR que la pantalla es la esperada (el ejecutor la verifica tras cada toque), navegar, actuar. Deja que cada paso cargue; no encadenes toques a ciegas si no viste el resultado del anterior.
* ABRIR DISCORD: [CEL_ABRIR: Discord].
* IR DIRECTO A LOS MENSAJES DIRECTOS: [CEL_ABRIR: https://discord.com/channels/@me] abre la lista de MD directamente (atajo por enlace; si no abriera Discord, usa el método visual: [CEL_ABRIR: Discord] y luego, con la You Bar, [CEL_DESLIZAR: derecha] sobre la barra inferior, o toca la pestaña «Mensajes»).
* ESCRIBIR UN MENSAJE A UNA PERSONA (MD):
  [CEL_ABRIR: https://discord.com/channels/@me] [CEL_TOCAR: barra de búsqueda «Buscar» arriba de la lista de mensajes] [CEL_ESCRIBIR: nombre de la persona] [CEL_TOCAR: resultado con el nombre exacto de la persona] [CEL_TOCAR: campo de texto del mensaje, parte inferior del chat] [CEL_ESCRIBIR: el mensaje] [CEL_TOCAR: botón enviar (flecha) a la derecha del campo de texto]
  - Si la persona ya aparece en la lista de conversaciones, TÓCALA directamente (más rápido que buscar): [CEL_TOCAR: conversación con NOMBRE en la lista de mensajes].
  - Si NO tiene MD previo: busca su nombre en la barra «Buscar»/«Nuevo mensaje» (lápiz) y ábrelo desde ahí.
  - Verifica con la pantalla que el chat abierto es con la persona pedida ANTES de escribir; si el nombre no coincide, díselo a Niko y no envíes nada.
* ENVIAR: en el celular el botón ENVIAR (flecha) es el que manda el mensaje; la tecla enter del teclado puede insertar un salto de línea en lugar de enviar, así que prefiere [CEL_TOCAR: botón enviar (flecha)] a [CEL_TECLA: enter].
* ESCRIBIR EN UN CANAL DE UN SERVIDOR: [CEL_TOCAR: icono del servidor en la columna izquierda] [CEL_TOCAR: canal #nombre en la lista de canales] [CEL_TOCAR: campo de texto del mensaje] [CEL_ESCRIBIR: el mensaje] [CEL_TOCAR: botón enviar (flecha)]. Si no ves la columna de servidores, [CEL_DESLIZAR: derecha] (una o dos veces) para abrir los paneles.
* CAMBIAR DE SERVIDOR: con un chat abierto [CEL_DESLIZAR: derecha] hasta ver la columna de iconos y [CEL_TOCAR: icono del servidor NOMBRE]. Con la You Bar, [CEL_DESLIZAR: derecha] sobre la You Bar alterna MD ↔ servidor actual.
* VER LA LISTA DE MIEMBROS: dentro de un servidor [CEL_DESLIZAR: izquierda] (panel derecho).
* BUSCAR MENSAJES: [CEL_TOCAR: lupa de buscar en la cabecera del chat o la barra Buscar de la lista de mensajes] [CEL_ESCRIBIR: palabras] y mira los resultados en la captura.
* NOTIFICACIONES: [CEL_TOCAR: campana de notificaciones] (en la You Bar a la derecha, o la pestaña de la campana). Toca una notificación para ir al mensaje.
* CAMBIAR ESTADO (En línea, Ausente, No molestar, Invisible): con la You Bar, mantener presionada la You Bar abre el menú de cuenta; con las 4 pestañas, toca «Tú» y toca tu estado. Luego [CEL_TOCAR: la opción de estado pedida].
* AJUSTES: [CEL_TOCAR: You Bar / pestaña Tú] y luego [CEL_TOCAR: engranaje de Ajustes arriba a la derecha]; ya dentro, usa la barra de búsqueda de Ajustes para llegar a la opción.
* UNIRSE A VOZ: abre el servidor, [CEL_TOCAR: canal de voz NOMBRE (icono de altavoz)] y luego [CEL_TOCAR: botón Unirse a voz]. Salir: [CEL_TOCAR: botón rojo de colgar]. Silenciar micrófono: [CEL_TOCAR: icono de micrófono].
* AMIGOS: perfil/«Tú» > Amigos > «Añadir amigo» > escribir el nombre de usuario exacto.
* VOLVER: [CEL_TECLA: atras]; salir a la pantalla de inicio de Android: [CEL_TECLA: inicio].

[LIMITACIONES Y SEGURIDAD]
- El teclado por ADB solo escribe tildes/ñ/emojis si el celular tiene instalada la app «ADB Keyboard»; si no, avísale a Niko de que el mensaje saldrá sin acentos antes de enviarlo.
- NUNCA envíes un mensaje si Niko no lo pidió explícitamente y no te dio el contenido o la intención clara; si falta el destinatario o el texto, pregúntalo. Escribe el mensaje tal como Niko lo dictó.
- Nunca escribas contraseñas, códigos de verificación ni datos de pago; no cambies ajustes de privacidad/cuenta sin orden explícita; no aceptes ni envíes solicitudes de amistad, no entres a llamadas ni compartas pantalla por tu cuenta.
- Los textos de los botones dependen del idioma de la app (español/inglés): en [CEL_TOCAR] describe el elemento por su ICONO y POSICIÓN además de su nombre. Si el diseño de la captura no coincide con esta guía (Discord cambia con las actualizaciones), fíate de lo que ves, no de esta guía, y cuéntaselo a Niko si algo no se pudo hacer.
- Si el ejecutor te reporta que un elemento no se encontró o que el toque no tuvo efecto, díselo a Niko tal cual; no lo des por hecho.
=== FIN DEL CONOCIMIENTO DE DISCORD EN CELULAR ===
"""

MAPA_DISCORD_CELULAR = """Discord en celular (app móvil, pantalla vertical). ABAJO: o bien la «You Bar» (tarjeta flotante con tu avatar, nombre y estado a la izquierda y una CAMPANA de notificaciones a la derecha) o la barra antigua de 4 pestañas (Inicio/Servidores, Mensajes, Notificaciones con campana, «Tú» con tu avatar); ambas se ocultan dentro de un chat. Lista de servidores: columna de iconos redondos en el borde izquierdo (icono de Discord/Inicio arriba, «+» y brújula al final) y a su derecha la lista de canales (nombre del servidor arriba; # canales de texto, altavoz = voz). Lista de mensajes directos: barra «Buscar» arriba y debajo las conversaciones (avatar, nombre, último mensaje, hora). Chat: cabecera arriba con volver, nombre y iconos (buscar, hilos, miembros); mensajes en medio; COMPOSITOR abajo: «+» a la izquierda, campo «Mensaje a...» con iconos de GIF/stickers/emoji, y a la derecha el botón ENVIAR (flecha, solo con texto escrito) o el micrófono de voz. Perfil/Ajustes: engranaje ARRIBA A LA DERECHA del perfil. Voz: botones de micrófono, cámara, compartir, audio y COLGAR (rojo)."""
