"""Conocimiento de memoria de la interfaz de Discord (escritorio, Windows) para SAGE.

cerebro.py lo inyecta en el contexto cuando Niko habla de Discord. Las posiciones son aproximadas
(pantalla 1920x1080): para hacer click en algo SIEMPRE se usa [PULSAR: descripción visual], nunca coordenadas fijas.
"""

CONOCIMIENTO_DISCORD = """
=== CONOCIMIENTO DE DISCORD (de memoria, escritorio Windows) ===

[DISTRIBUCIÓN DE LA INTERFAZ, de izquierda a derecha]
1. BARRA DE SERVIDORES (columna estrecha en el borde izquierdo):
   - Arriba del todo: logo de Discord (botón "Inicio"): lleva a Amigos y a los Mensajes Directos (MD).
   - Debajo: iconos redondos de cada servidor (los que tienen un puntito blanco a la izquierda tienen mensajes sin leer).
   - Al final: botón "+" (Añadir un servidor) y brújula (Descubrir servidores).
2. COLUMNA DE CANALES / MD (a la derecha de la barra de servidores):
   - Dentro de un servidor: arriba el NOMBRE DEL SERVIDOR (clic = menú: invitar gente, ajustes del servidor, crear canal, notificaciones...). Debajo, categorías con canales de texto (#) y canales de voz (icono de altavoz).
   - En Inicio: arriba una caja "Buscar o iniciar una conversación" (abre el Selector Rápido), luego Amigos, Nitro, Tienda y la lista "Mensajes directos".
   - Abajo de esta columna, esquina inferior izquierda: PANEL DE USUARIO con tu avatar y nombre (clic = cambiar estado: Conectado, Ausente, No molestar, Invisible), botón de micrófono (silenciar), botón de auriculares (ensordecer) y engranaje (Ajustes de usuario). Cuando estás en voz aparece encima el panel "Conexión de voz" con el botón de colgar (teléfono con X) para desconectarte.
3. ZONA CENTRAL (chat):
   - Cabecera con el nombre del canal o de la persona y, a la derecha, iconos: hilos, notificaciones, mensajes fijados, mostrar/ocultar lista de miembros (icono de personas), la caja "Buscar" (lupa), bandeja de entrada y ayuda.
   - En medio: los mensajes (pasa el ratón por encima de uno para ver: reaccionar, responder, reenviar y el menú "más" con tres puntos).
   - Abajo del todo: CAJA DE TEXTO "Enviar mensaje a #canal / @usuario". A la izquierda un botón "+" (adjuntar archivo, crear hilo, usar apps); a la derecha GIF, stickers y emojis.
4. COLUMNA DERECHA: lista de miembros del servidor (agrupados por rol y en línea / desconectados), o el perfil de la persona en un MD. Se muestra/oculta con el icono de personas de la cabecera.

[ATAJOS DE TECLADO ÚTILES — se ejecutan con [ATAJO: ...]]
- ctrl+k = SELECTOR RÁPIDO: la forma MÁS FIABLE de ir a cualquier persona, canal o servidor. Prefijos: @ = usuarios, # = canales de texto, ! = canales de voz, * = servidores.
- ctrl+f = buscar mensajes en el canal/MD/servidor actual (abre la caja Buscar de la cabecera). Filtros: from:usuario, mentions:usuario, has:link|image|file|video, in:canal, before:/after:/during: fecha.
- ctrl+, = Ajustes de usuario. ctrl+/ = lista de atajos.
- alt+up / alt+down = canal anterior / siguiente. ctrl+alt+up / ctrl+alt+down = servidor anterior / siguiente. alt+shift+up / alt+shift+down = canal anterior / siguiente con mensajes sin leer.
- esc = marcar el canal como leído. shift+esc = marcar todo el servidor como leído.
- ctrl+shift+m = silenciar/activar micrófono. ctrl+shift+d = ensordecer/activar auriculares.
- ctrl+e = abrir selector de emojis. ctrl+shift+u = subir un archivo.
- En la caja de texto: enter = ENVIAR el mensaje; shift+enter = salto de línea (NO uses saltos de línea al escribir mensajes); flecha arriba con la caja vacía = editar tu último mensaje; "/" = comandos de barra; "@nombre" = mención; ":nombre" = emoji.

[PROTOCOLOS DE ACCIÓN FIABLES]
Antes de cualquier acción, Discord debe estar abierto y al frente. Usa [ENFOCAR: discord] (lo abre si no estaba). Alternativa que abre Discord directamente en los MD: [ABRIR: discord://-/channels/@me].
Deja SIEMPRE pausas [ESPERAR: 1] o [ESPERAR: 1.5] entre pasos: los resultados del selector y los chats tardan en cargar.

* ESCRIBIR UN MENSAJE A UNA PERSONA (MD):
  [ENFOCAR: discord] [ATAJO: ctrl+k] [ESPERAR: 1] [ESCRIBIR: @nombre] [ESPERAR: 1.5] [TECLA: enter] [ESPERAR: 1.5] [ESCRIBIR: el mensaje] [TECLA: enter]
  - Al pulsar enter en el selector se abre el MD con el primer resultado y la caja de texto queda con el foco. Si no tiene el foco: [PULSAR: caja de texto para escribir el mensaje, parte inferior del chat].
  - Si hay varias personas con nombre parecido, escribe el nombre lo más exacto posible; el ejecutor verifica la pantalla al final y te dirá con quién quedó abierto el chat.
  - Si la persona no sale en el selector (no es amigo ni tiene MD previo): Inicio > Amigos > botón verde "Añadir amigo" (arriba a la derecha) > escribir su nombre de usuario > enter.

* ESCRIBIR EN UN CANAL DE UN SERVIDOR:
  [ENFOCAR: discord] [ATAJO: ctrl+k] [ESPERAR: 1] [ESCRIBIR: #nombre-del-canal] [ESPERAR: 1.5] [TECLA: enter] [ESPERAR: 1.5] [ESCRIBIR: el mensaje] [TECLA: enter]
  Para cambiar primero de servidor: [ATAJO: ctrl+k] [ESCRIBIR: *nombre del servidor] [TECLA: enter].

* BUSCAR UN USUARIO / UN CANAL SIN ENVIAR NADA: ctrl+k + el nombre con su prefijo, y NO pulses enter (o pulsa enter solo para abrirlo).

* BUSCAR MENSAJES: [ATAJO: ctrl+f] [ESPERAR: 1] [ESCRIBIR: from:usuario palabra] [TECLA: enter], y mira los resultados en la columna derecha.

* UNIRSE A VOZ: [PULSAR: nombre del canal de voz en la columna de canales (icono de altavoz)]. Salir: [PULSAR: botón de colgar (teléfono con X) en el panel Conexión de voz, abajo a la izquierda].

* CAMBIAR ESTADO: [PULSAR: avatar propio en el panel de usuario abajo a la izquierda] y luego [PULSAR: la opción de estado pedida].

* AJUSTES: [ATAJO: ctrl+,] o [PULSAR: engranaje de Ajustes de usuario, abajo a la izquierda]. Secciones en la barra izquierda de ajustes: Mi cuenta, Perfiles, Privacidad y seguridad, Apps autorizadas, Dispositivos, Conexiones, Notificaciones, Voz y vídeo, Teclas rápidas, Apariencia, Accesibilidad, Idioma, Avanzado. Los ajustes de un servidor están en el menú del nombre del servidor > Ajustes del servidor.

* ACCIONES SOBRE UN MENSAJE: pasa el ratón por el mensaje y usa [PULSAR: icono de responder del mensaje] o clic derecho sobre el mensaje para: Responder, Editar, Reenviar, Fijar, Copiar texto, Marcar como no leído, Eliminar.
* ACCIONES SOBRE UNA PERSONA: clic derecho sobre su nombre/avatar: Perfil, Mensaje, Llamar, Silenciar, Añadir amigo, Bloquear, Invitar al servidor.
* CLIC DERECHO (menú contextual): [PULSAR_DER: mensaje de <persona o texto>] [ESPERAR: 1] [PULSAR: opción Copiar texto del menú contextual]. Sobre una persona: [PULSAR_DER: nombre de la persona en la lista de miembros]; sobre un servidor: [PULSAR_DER: icono del servidor en la barra izquierda]. El menú queda abierto: elige solo la opción que Niko pidió o ciérralo con [TECLA: esc]. NUNCA elijas Eliminar mensaje, Bloquear, Expulsar, Banear ni Salir del servidor sin una orden explícita.

[REGLAS DE SEGURIDAD]
- NUNCA envíes un mensaje (enter en la caja de texto) si Niko no lo pidió explícitamente y no te dio el contenido o la intención clara del mensaje. Si te falta el destinatario o el texto, pregúntalo en vez de adivinar.
- Escribe el mensaje tal como Niko lo dictó, sin saltos de línea.
- Si el ejecutor te reporta que la persona o el canal abierto no coincide con el pedido, no lo des por hecho: dilo con honestidad.
- Los textos de los botones dependen del idioma de Discord (español/inglés): en [PULSAR] describe el elemento por su icono y posición además de su nombre.
=== FIN DEL CONOCIMIENTO DE DISCORD ===
"""
