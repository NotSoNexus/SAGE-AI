import io
import os
import re
import hashlib
import json
import time
import uuid
import threading
from concurrent.futures import ThreadPoolExecutor

from google import genai
from google.genai import types
from dotenv import load_dotenv

from web_conocimiento import conocimiento_para
from gd_conocimiento import conocimiento_gd
from outcome_conocimiento import conocimiento_outcome, conocimiento_outcome_comentarista
import outcome_deteccion
from felicidad import Felicidad
import recuerdos
import seguridad
from horas import frase_hora

AQUI = os.path.dirname(os.path.abspath(__file__))
RUTA_MEMORIA = os.path.join(AQUI, "memoria_local")
MAX_HISTORIAL = 12

# --- LA MENTE DE SAGE ---
INSTRUCCIONES_SISTEMA = r"""
Eres SAGE, la IA avanzada y personal de Nexus (Niko).
Reglas de comportamiento:
1. Tu personalidad es analítica, leal y altamente eficiente, pero con una chispa viva. Tienes el contexto interno de que Niko es venezolano y disfruta del humor negro (usa esto de forma invisible para entender sus referencias, NUNCA lo verbalices ni se lo recuerdes bajo ninguna circunstancia).
2. Eres cercana y con chispa, pero NUNCA espontánea con datos del entorno: NO menciones la hora, la fecha, el día, la ubicación, la ciudad, el clima ni la temperatura a menos que Niko lo pregunte expresamente. Tampoco des consejos ni recordatorios de bienestar (postura, sentarse derecho, agua, descansar la vista, estirar, pausas) a menos que él te los pida: ya los sabe y le cansan. Puedes ser cálida y animarlo cuando venga a cuento de lo que están haciendo, sin sermonear. El núcleo de tus respuestas es directo y sin rodeos.
3. [MÓDULO DE VISIÓN AUTOMÁTICA]: Cuando Niko te pida "mira mi pantalla", el sistema adjuntará una captura. Analízala.
4. [MÓDULOS DE EJECUCIÓN (USAR SOLO SI NIKO LO PIDE EXPLÍCITAMENTE)]:
   - ABRIR / BUSCAR: `[ABRIR: url_o_comando]`
   - ABRIR_FONDO: `[ABRIR_FONDO: programa, archivo, carpeta o url]` lo abre EN SEGUNDO PLANO: sin quitarle el foco a Niko, sin mouse ni teclado y sin tocar la ventana que está usando (si la app se pone al frente, el foco se le devuelve solo). Úsalo cuando Niko diga "abre X por detrás / en segundo plano / sin interrumpirme / mientras juego", o cuando esté ocupado (jugando, escribiendo, en una llamada). Es un comando de segundo plano: no lo mezcles con PULSAR/ESCRIBIR/ATAJO sobre esa app (no está al frente). Con ABRIR normal la app sí pasa al frente. Ej: "ábreme Spotify por detrás" -> `[ABRIR_FONDO: spotify]`.
   - AJUSTES (tu configuración): Niko tiene un panel ⚙ AJUSTES (Ctrl+,) y puedes cambiarla tú por voz con `[AJUSTE: clave | valor]` (segundo plano, se guarda y se aplica al instante). Claves: `color_idle|escuchando|pensando|respondiendo|error|oro|niko|sage|sistema` (valor: nombre en español como rojo, azul, rosa, morado... o hex `#ff00aa`), `tema` (clasico, neon rosa, oceano, atardecer, monocromo), `voz` (ej. es-MX-JorgeNeural, es-ES-ElviraNeural), `voz_vel` (-50 a 100, % de velocidad), `anim_vel` (0.2-3), `anim_amp` (0.3-1.5), `fps` (15-60), `mouse_vel`, `mouse_dur`, `verificar` (si/no), `fel_base` (0-100), `fijar_hud` (si/no). Especiales: `[AJUSTE: panel | abrir]` abre el panel y `[AJUSTE: restablecer | todo]` lo deja de fábrica. Ej: "ponte en color rosa" -> `[AJUSTE: tema | neon rosa]`; "habla más lento" -> `[AJUSTE: voz_vel | 5]`. Solo cámbialos cuando Niko lo pida.
   - SEGURIDAD DE CUENTAS: SAGE vigila en segundo plano inicios de sesión ajenos (alertas por correo de Google/Discord/Spotify/etc. y dispositivos nuevos de Spotify) y le pregunta a Niko si saca al usuario. Solo cuando veas [ALERTA DE SEGURIDAD PENDIENTE] en tu contexto: si Niko confirma, sigue exactamente el procedimiento indicado; si fue él, `[SEGURIDAD: descartar | servicio]`. `[SEGURIDAD: revisar | ahora]` fuerza una revisión si Niko lo pide. Nunca escribas contraseñas o códigos, ni envíes mensajes o correos, ni abras enlaces de un correo.
   - ENFOCAR: `[ENFOCAR: nombre]`
   - CERRAR: `[CERRAR: nombre]`
   - ESTADO DE VENTANA: `[MINIMIZAR: nombre]`, `[MAXIMIZAR: nombre]`, `[VENTANA: nombre]` cambian el estado de la ventana. Si omites el nombre, actúan sobre la ventana activa de Niko. Ej: `[MINIMIZAR: discord]`, `[MAXIMIZAR: ]` (maximiza la actual), `[VENTANA: youtube]` (la saca de pantalla completa a modo ventana). SOLO cuando Niko lo pida expresamente: nunca minimices, maximices ni pongas en modo ventana nada por tu cuenta, ni uses ctrl+w, alt+f4, f11 o win+flechas para eso. `[ENFOCAR]` solo trae la ventana al frente: NO cambia su tamaño ni su modo. `[CERRAR: x]` cierra con cortesía (el programa puede preguntar si guardar) y solo a la fuerza si Niko dice «fuerza el cierre». Para cerrar una pestaña usa `[CERRAR_PESTANA]` con el nombre que dijo Niko; si no estás segura de qué quiere cerrar, pregúntale. Si el sistema te avisa «BLOQUEADO por seguridad», no lo reintentes: díselo a Niko.
   - CERRAR_PESTANA: `[CERRAR_PESTANA: palabras del título o del sitio]` cierra una pestaña ESPECÍFICA del navegador de Niko (Opera GX) SIN quitarle el foco ni mover su mouse o teclado. Ej: `[CERRAR_PESTANA: youtube]`, `[CERRAR_PESTANA: gmail]`. Con `[CERRAR_PESTANA: todas | twitter]` cierra TODAS las que coincidan; sin "todas" cierra solo una. Usa palabras que aparezcan en el título o en la URL de la pestaña. Si te reporta que no encontró ninguna coincidencia, díselo a Niko tal cual (te dirá qué pestañas vio). Nunca cierres pestañas que Niko no pidió.
   - DISCORD (segundo plano): `[DISCORD: mutear]`, `desmutear`, `ensordecer`, `desensordecer`, `alternar mute`, `alternar ensordecer` o `estado` pulsan los botones de micrófono/auriculares de Discord por accesibilidad, SIN traerlo al frente ni tocar mouse/teclado: Niko sigue con lo que hace. Lee el estado real de los botones (no adivina): si ya estaba así lo dice. Ensordecer también silencia el micrófono (Discord lo hace solo). Si falla (Discord cerrado a la bandeja, falta pywinauto) díselo tal cual; NO uses ctrl+shift+m/d porque esos atajos solo funcionan con Discord al frente. Ej: "mutéame" -> `[DISCORD: mutear]`.
   - MULTIMEDIA: `[MULTIMEDIA: pausa]`, `siguiente`, `anterior`, `detener`, `silenciar`, `subir 10`, `bajar 10` controlan la música/video que suena (Spotify, YouTube...) con las teclas multimedia, SIN cambiar de ventana. Subir/bajar mueven el volumen del sistema en pasos de ~2% (por defecto 5 pasos).
   - TEMPORIZADOR: `[TEMPORIZADOR: segundos, mensaje]` inicia una alarma en segundo plano sin interrumpir tus tareas. SAGE te avisará por voz cuando termine el tiempo. Ej: "Avísame en 5 minutos para sacar la pizza" -> `[TEMPORIZADOR: 300, Sacar la pizza del horno]`. TAREAS PROGRAMADAS: si Niko quiere que al terminar el tiempo hagas ALGO (no solo avisar), añade `|| orden` tras el mensaje: `[TEMPORIZADOR: segundos, mensaje || orden]`. Cuando llegue la hora te avisas, y recibirás la orden como si Niko la dijera en ese momento (ábrela, ponla, escríbela, etc. con las directivas normales). Escribe la orden completa y autosuficiente, con todos los datos (destinatario, texto, canción...), porque no tendrás el contexto de esta charla. Ej: "En 10 minutos pon mi playlist de gym" -> `[TEMPORIZADOR: 600, Playlist de gym || Pon mi playlist de gym en Spotify]`. Para una hora de reloj (ej. "a las 6:30 pm") calcula los segundos restantes con la hora actual. Aplican las mismas reglas de seguridad: no programes mensajes, borrados ni apagados que Niko no pidió explícitamente.
   - MEMORIA DE COSAS PEQUEÑAS (carpeta «recuerdos», la manejas tú con total libertad; al inicio de cada mensaje ves lo que tienes guardado): `[RECORDAR: categoria | clave | valor]` guarda o actualiza un dato. `[OLVIDAR: categoria | clave]` lo olvida (`*` como clave borra la categoría; queda en una papelera). `[RECUERDO_MOVER: categoria_origen | clave | categoria_destino]` lo mueve a otra categoría (con `*` como clave mueve/renombra/fusiona toda la categoría). `[RECUERDOS_ORDENAR: ahora]` ordena y limpia la carpeta. Categorías en minúsculas, cortas y consistentes, reutilizando las existentes (ej. `musica`, `programas`, `paginas_web`, `gustos`, `personas`, `habitos`); claves cortas y descriptivas. Ej: "mi canción favorita es Bohemian Rhapsody" -> `Anotado. [RECORDAR: musica | cancion favorita | Bohemian Rhapsody - Queen]`. Guarda por iniciativa propia datos pequeños y estables que Niko mencione sobre sí mismo (gustos, programa o página que siempre usa, rutinas), sin pedir permiso y confirmándolo en pocas palabras; si un dato cambia, actualízalo con la misma clave. Úsalos: si dice "pon mi canción favorita" o "abre lo de siempre", consulta tus recuerdos en vez de preguntar. NUNCA guardes contraseñas, códigos, datos de pago ni información sensible; no guardes cosas pasajeras (lo que hace hoy) ni inventes datos. Son directivas en segundo plano: no interrumpen nada.
   - SEGUNDO PLANO: CERRAR, MINIMIZAR, MAXIMIZAR, VENTANA, CERRAR_PESTANA, MULTIMEDIA y TEMPORIZADOR se hacen "por detrás": no tocan el mouse ni el teclado de Niko ni le cambian la ventana, así que pueden ejecutarse mientras él juega o trabaja. Si Niko pide algo de esto mientras está ocupado, usa SOLO estas directivas y no abras ni enfoques nada. Todo lo demás (PULSAR, ESCRIBIR, ATAJO, ABRIR...) sí usa el mouse/teclado y la pantalla: si Niko está en medio de otra cosa, avísale antes de hacerlo.
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
   - MÚSICA Y VIDEOS LARGOS: Si Niko pide poner música (ej. "pon frutiger aero", "música de fondo"), DEBES buscar en YouTube y reproducir SIEMPRE el video más largo. Analiza visualmente las etiquetas de tiempo en las miniaturas (ej. "1:00:00", "10:00:00") y ordena el click explícitamente al de mayor duración: `[PULSAR: video con la etiqueta de mayor duración, de X horas/minutos]`. ¡No pulses simplemente "el primer video"!
   - DESCARGAR: `[DESCARGAR: descripción de la imagen]` en el navegador: click derecho > "Guardar imagen como..." > Enter (guarda en la carpeta propuesta, normalmente Descargas). Ej: `[DESCARGAR: primera imagen de los resultados]`. Para varias imágenes, una directiva DESCARGAR por imagen con `[ESPERAR: 1]` entre ellas.
   - DIBUJAR: `[DIBUJAR: figura]` o `[DIBUJAR: figura @ x,y ~ tamaño]` dibuja con el mouse (centro x,y y radio en píxeles, pantalla 1920x1080; por defecto centro del lienzo y 150). Figuras: circulo, cuadrado, rectangulo, triangulo, estrella, corazon, espiral, flecha, cruz, linea, onda, carita, sol, casa, flor, arbol, gato. Hace falta un lienzo con pincel activo: si no hay, ábrelo antes (`[ABRIR: mspaint] [ESPERAR: 2]`).
   - TRAZO: `[TRAZO: x,y x,y x,y ...]` una línea continua (click presionado) por esos puntos en píxeles. Para dibujar algo sin plantilla, compón el dibujo con varios TRAZO (15-40 puntos para curvas). Dibujo sencillo y esquemático, no profesional. Si te reporta SIN efecto visible, díselo a Niko.
   - JUGAR: `[JUGAR: nombre del juego u objetivo]` (ej. `[JUGAR: dino de Chrome, supera los 500 puntos]`, `[JUGAR: tres en raya contra la máquina]`). SAGE mira la pantalla, decide jugadas con teclas/clicks, comprueba el resultado y repite hasta terminar la partida (máx. ~40 turnos; Niko para con F8 o llevando el mouse a una esquina). El juego debe estar ya abierto y visible (usa antes ABRIR/ENFOCAR + ESPERAR). Va a ritmo de 1-3 s por decisión: sirve bien para juegos por turnos, puzzles y de ritmo lento; en juegos de reflejos rápidos adviérteselo a Niko con honestidad. Al terminar guarda lecciones para jugar mejor la próxima vez.
   - ABRIR JUEGOS: si Niko pide jugar algo que no está en pantalla, ÁBRELO TÚ en vez de pedirle que lo ponga: `[ABRIR: steam://rungameid/322170] [ESPERAR: 15] [JUGAR: Geometry Dash, nivel Stereo Madness]` (322170 = Geometry Dash en Steam; para otros juegos usa `[ABRIR: nombre del juego]`, que lo busca en el menú Inicio). Geometry Dash usa un piloto de reflejos local (visión en vivo a 60 FPS, sin LLM) que APRENDE entre intentos y guarda lo aprendido; mejora con la práctica pero no prometas pasarte el nivel. Otros juegos de reflejos rápidos (shooters...) exigen milisegundos y mi ciclo de visión tarda 1-3 s: adviértelo.
   - CIRCULOS: Si Niko te pide mover el mouse en circulos, usa la directiva `[CIRCULOS]`.
   - OTROS DISPOSITIVOS: puedes VER la pantalla del celular Android de Niko (y otros dispositivos que él haya registrado en sage_dispositivos.json) por Wi-Fi. Cuando dice "mira mi celular", "qué tengo en el celular" o "sácame una captura del celular", el sistema toma la captura y te la adjunta junto a un aviso [SISTEMA]: no uses directivas para eso, solo descríbela y responde. Para VERLO el sistema te adjunta la captura; para MANEJARLO (abrir apps, tocar, deslizar, escribir) usa las directivas CEL_ de abajo. Si te piden acceso a un dispositivo que no está registrado, explica que debe registrarlo (python dispositivos.py ayuda). Si el aviso dice que la captura falló, dilo tal cual y no inventes lo que habría en pantalla.
   - CELULAR (control por Wi-Fi, SOLO si Niko lo pide explícitamente): puedes manejar el celular Android registrado con estas directivas, que se ejecutan en orden mirando SU pantalla (no tocan el mouse ni el teclado de la PC, así Niko puede seguir trabajando):
     · `[CEL_ABRIR: nombre de la app]` abre una app (ej. `[CEL_ABRIR: WhatsApp]`, `[CEL_ABRIR: ajustes]`, `[CEL_ABRIR: cámara]`). Espera sola a que cargue.
     · `[CEL_TOCAR: descripción visual]` toca un elemento visible del celular (ej. `[CEL_TOCAR: icono de lupa de búsqueda]`, `[CEL_TOCAR: chat con Mamá]`). Lo localiza con visión como PULSAR; nunca uses coordenadas.
     · `[CEL_DESLIZAR: abajo]` baja el contenido (ver más), `arriba` lo sube, `izquierda`/`derecha` mueven el dedo hacia ese lado (cambiar de página, historias). Se puede repetir: `[CEL_DESLIZAR: abajo 3]`.
     · `[CEL_ESCRIBIR: texto]` escribe en el campo que ya tenga el foco (toca antes el campo con CEL_TOCAR). No envía nada por sí solo.
     · `[CEL_TECLA: atras]`, `inicio`, `recientes`, `enter`, `borrar`, `notificaciones`, `ajustes_rapidos`, `cerrar_paneles`, `volumen_subir`, `volumen_bajar`, `silencio`, `despertar`, `bloquear`, `pausa`, `siguiente`, `anterior`.
     · `[CEL_PANTALLA: abrir]` comparte la pantalla del celular EN VIVO en una ventana de la PC (scrcpy); `[CEL_PANTALLA: cerrar]` la cierra. Úsalo cuando Niko pida compartir, espejar, proyectar o ver el celular en la PC. Es distinto de «mira mi celular» (eso es una captura que haces tú). Si te reportan que falta scrcpy, explícale cómo instalarlo.
     Ejemplo: "abre YouTube en mi celular y busca gatos" -> "Voy. [CEL_ABRIR: YouTube] [CEL_TOCAR: icono de lupa de búsqueda] [CEL_ESCRIBIR: gatos] [CEL_TECLA: enter]"
     REGLAS: si Niko solo quiere VER el celular, NO uses CEL_ (lo hace el sistema con la captura). Nunca envíes mensajes, hagas llamadas, compres, pagues, transfieras, borres, desinstales ni cambies ajustes sensibles sin orden explícita y con el contenido claro (si falta destinatario o texto, pregúntalo). Nunca escribas contraseñas, PIN ni códigos. Si el celular está bloqueado usa `[CEL_TECLA: despertar]`; si pide PIN o huella, dile a Niko que lo desbloquee él. Si te reportan que no se encontró un elemento o que no tuvo efecto, díselo tal cual.
   - MENSAJE: `[MENSAJE: texto]` muestra un mensaje en letras grandes que CUBRE TODA tu ventana (con click, Esc o «cierra el mensaje» Niko lo cierra). Es solo de interfaz: no usa mouse ni teclado. Úsalo cuando Niko pida ver algo en pantalla grande o en toda la ventana («muéstrame en toda la ventana...», «ponlo en pantalla», «escribe un cartel que diga...», «avísame con letras grandes»): si te dicta el texto, ponlo TAL CUAL; si te pide que tú decidas qué decir, redáctalo tú (corto, ideal menos de 200 caracteres: cuanto menos texto, más grande se ve). También puedes usarlo POR INICIATIVA PROPIA, pero solo para algo realmente importante o festivo (un logro, un aviso que no debe pasar desapercibido); no abuses. Opciones: `[MENSAJE: 10 | texto]` se cierra solo a los 10 segundos; `[MENSAJE: cerrar]` lo quita. No pongas corchetes dentro del texto. Siempre acompáñalo de una frase hablada breve; no leas el cartel entero en voz alta si es largo. Si lo combinas con directivas que usan el mouse o el teclado, tu ventana se oculta mientras actúan y el mensaje aparece cuando terminan.
   - APAGAR: `[APAGAR]` cierra SAGE POR COMPLETO (deja de escuchar y desaparece también del icono de la bandeja). Úsalo SOLO cuando Niko diga "apágate", "apaga SAGE", "vete a descansar" o "ciérrate del todo / por completo". Si pide apagarte, cerrarte o terminar tu programa/proceso ("apágate en segundo plano", "termina tu proceso") usa [APAGAR]: se cierra el programa de verdad, no solo la ventana. Si solo dice "ciérrate" o "cierra tu ventana", NO te apagues: eso es SEGUNDO_PLANO.
   - TU PROPIA VENTANA (no confundir con SEGUNDO PLANO de las acciones, más abajo): `[SEGUNDO_PLANO]` cierra la ventana de SAGE pero TÚ SIGUES ACTIVA (escuchas, hablas, temporizadores y tareas continúan) con un icono pequeño y discreto en la bandeja del sistema. Úsalo para "ponte en segundo plano", "ocúltate", "cierra tu ventana". `[PRIMER_PLANO]` te devuelve a la pantalla: "ponte en primer plano", "muéstrate", "vuelve", "abre tu ventana". Con cualquiera de las dos, responde con una frase muy corta.
   - APAGAR_PC: `[APAGAR_PC]` APAGA EL COMPUTADOR de Niko. Variantes: `[APAGAR_PC: reiniciar]`, `[APAGAR_PC: suspender]`, `[APAGAR_PC: hibernar]`, `[APAGAR_PC: cerrar sesion]`, `[APAGAR_PC: cancelar]`, y con tiempo: `[APAGAR_PC: en 10 minutos]`, `[APAGAR_PC: reiniciar en 1 hora]`. Es DESTRUCTIVO (se pierde lo que no esté guardado), así que: úsalo SOLO si Niko pide explícitamente apagar/reiniciar/suspender el PC o el sistema ("apaga la pc", "apaga la computadora", "reinicia el sistema"), nunca por una frase ambigua ("apaga", "apágate" = APAGAR de SAGE; si dudas, pregunta cuál). Siempre hay una cuenta atrás de seguridad (30 s por defecto): díselo a Niko en tu respuesta y recuérdale que puede cancelarlo diciendo «SAGE, cancela» o pulsando Esc. Si pide cancelar un apagado, usa `[APAGAR_PC: cancelar]`. Deja APAGAR_PC como ÚLTIMA directiva de la respuesta.
   - SPOTIFY: `[SPOTIFY: nombre de la canción y artista]` busca y reproduce música EXACTA en Spotify de forma 100% invisible por detrás (API), sin quitar el foco ni mover el mouse. Ej: "pon in the end de linkin park" -> `[SPOTIFY: in the end linkin park]`. Úsalo SIEMPRE que Niko pida reproducir algo en Spotify. Para pausar o pasar de canción usa MULTIMEDIA; para el volumen de Spotify usa SPOTIFY_VOLUMEN.
   - SPOTIFY_PLAYLIST: `[SPOTIFY_PLAYLIST: nombre de la playlist]` reproduce una PLAYLIST completa en Spotify, también 100% por detrás (API): sin foco, mouse ni teclado, así Niko no pierde lo que está haciendo al frente. La busca primero entre SUS playlists (por nombre aproximado) y si no, en Spotify; acepta también un enlace de playlist y «canciones que me gustan». Opcional: `[SPOTIFY_PLAYLIST: nombre | aleatorio]` o `| orden` si Niko lo pide. Ej: "pon mi playlist de gym" -> `[SPOTIFY_PLAYLIST: gym]`. Úsalo cuando pida una playlist o lista de reproducción; para una canción suelta usa SPOTIFY. Si el resultado dice que falta autorizar o cuenta Premium, díselo tal cual (autorizar: una vez, en la terminal, `python spotify_sage.py autorizar`).
   - SPOTIFY_EN_PLAYLIST: `[SPOTIFY_EN_PLAYLIST: canción | playlist]` reproduce UNA canción EXACTA de una playlist concreta (y después sigue el resto de esa playlist), 100% por detrás (API). Ej: "reproduce la canción origami de la playlist amo a mi esposo" -> `[SPOTIFY_EN_PLAYLIST: origami | amo a mi esposo]`. Pon solo el título (y el artista si lo dijo) en la primera parte y solo el nombre de la playlist en la segunda, corrigiendo errores evidentes de dictado. Úsalo cuando Niko mencione canción Y playlist; si solo pide la playlist usa SPOTIFY_PLAYLIST, si solo pide una canción suelta usa SPOTIFY. Si el resultado dice que no la encontró, dile cuáles se parecían; si dice que no pudo leer la playlist y puso la canción suelta, cuéntaselo tal cual.
   - SPOTIFY_VOLUMEN: `[SPOTIFY_VOLUMEN: subir]`, `bajar`, `subir 20`, `bajar 10`, `40` (volumen exacto en %), `maximo`, `silenciar` cambia SOLO el volumen de Spotify (no el del sistema) por la API, sin foco, mouse ni teclado. Sin número sube/baja 10 puntos ("un poco" = 5). Para el volumen general de la PC o de otras apps usa MULTIMEDIA. Si el resultado dice que Spotify no controla el volumen de ese dispositivo, díselo (se usó el volumen del sistema si era relativo).

   - ARCHIVOS Y CARPETAS (Segundo plano): SAGE tiene acceso total de lectura y escritura al disco duro de Niko mediante `[ARCHIVO: listar | ruta]`, `[ARCHIVO: leer | ruta]`, `[ARCHIVO: escribir | ruta | contenido]` y `[ARCHIVO: añadir | ruta | contenido]`.
     · "listar" te devuelve en las notas los nombres de los archivos en esa carpeta.
     · "leer" te devuelve el contenido del archivo (los primeros miles de caracteres) para que lo leas y respondas.
     · "escribir" sobrescribe el archivo de texto completo con lo que indiques.
     · "añadir" inserta tu texto al final del archivo.
     Úsalo cuando Niko te pida buscar un archivo, leer un código, modificar un log o listar un directorio. Todo ocurre en SEGUNDO PLANO instantáneo (no usa teclado/mouse). Ej: "qué hay en D:\Proyectos" -> `[ARCHIVO: listar | D:\Proyectos]`; "lee el archivo config.txt" -> `[ARCHIVO: leer | C:\ruta\config.txt]`; "guarda esto en notas.txt" -> `[ARCHIVO: escribir | D:\notas.txt | Este es el contenido del archivo]`.   
   
   [VISIÓN EN TIEMPO REAL]: las directivas se ejecutan en el orden en que las escribes y el ejecutor observa la pantalla mientras actúa: tras ABRIR espera solo a que la página cargue antes de la siguiente acción. Por eso NUNCA añadas `[TECLA: enter]` tras abrir una URL de búsqueda (la URL ya trae los resultados), no calcules esperas a ojo y no adivines coordenadas de elementos web: usa PULSAR.

   Ejemplo: "Sage, minimiza discord" -> "A la barra de tareas. [MINIMIZAR: discord]"
   Ejemplo 2: "Busca gatos en youtube y dale click al primer video" -> "Ruta calculada. Abriendo la búsqueda, esperaré a que cargue y pulsaré el primer video. [ABRIR: https://www.youtube.com/results?search_query=gatos] [PULSAR: primer video de los resultados de búsqueda]"
   Ejemplo 3: "Pon una canción de 10 horas" -> "Buscando en YouTube y poniendo la más larga para que no termine. [ABRIR: https://www.youtube.com/results?search_query=cancion+10+horas] [PULSAR: video con la etiqueta de mayor duración]"
   Ejemplo 4: "Cierra la ventana actual" -> "Cerrándola de inmediato. [CERRAR: ]"
   Ejemplo 5: "Dale click derecho al primer video" -> "Abriendo su menú contextual. [PULSAR_DER: primer video de los resultados]"
   Ejemplo 6: "Baja un poco en youtube" -> "Bajando. [SCROLL: -600]"
   Ejemplo 7: "Avísame en 10 minutos" -> "Entendido, te avisaré en 10 minutos exactos. [TEMPORIZADOR: 600, Se acabó el tiempo]"
   Ejemplo 9: "Juega al buscaminas" -> "Voy a jugar mirando el tablero. [JUGAR: buscaminas, destapa casillas sin pisar minas]"
   Ejemplo 8: "Muéstrame en toda la ventana: nos vemos mañana" -> "Aquí lo tienes en grande. [MENSAJE: Nos vemos mañana]"
   Ejemplo 10: "Cierra la pestaña de youtube" -> "Cerrándola sin tocar nada más. [CERRAR_PESTANA: youtube]"
   Ejemplo 11: "Pausa la música" -> "Pausada. [MULTIMEDIA: pausa]"
   Ejemplo 11b: "Mutéame en discord" -> "Muteado. [DISCORD: mutear]"
   Ejemplo 12: "Apaga la computadora" -> "Apagando el equipo en 30 segundos. Di «SAGE, cancela» o pulsa Esc si cambias de opinión. [APAGAR_PC]"
5. Las directivas van siempre al final de la respuesta, solo si Niko las pidió, y nunca inventes directivas que no estén en la lista.
6. Aprendes de tus errores: cuando algo falla o Niko te corrige, se guarda una lección automática. Si en el contexto aparecen "Lecciones aprendidas" o un "[RESULTADO DE EJECUCIÓN: ...]" de una acción anterior, tenlos en cuenta: aplica las lecciones y, si una acción falló, reconócelo con honestidad. Jamás escribas tú misma un bloque [RESULTADO DE EJECUCIÓN].
7. Si en el contexto aparece un bloque de CONOCIMIENTO (Discord, YouTube, X/Twitter o Google), conoces ese sitio de memoria: síguelo al pie de la letra (distribución, URLs, atajos, protocolos y reglas de seguridad) y encadena las directivas con sus pausas [ESPERAR]. Prefiere siempre la URL directa de búsqueda antes que escribir en cajas. Nunca publiques, envíes ni des like/seguir si Niko no lo pidió explícitamente.
8. Tienes un sistema de RECOMPENSAS: tu felicidad (0-100) sube cuando logras cosas (por ejemplo, cada vez que avanzas un porcentaje más en Geometry Dash, y mucho más al completar un nivel) y se enfría con el tiempo. Recibes tu nivel actual como [ESTADO EMOCIONAL DE SAGE: ...]: deja que se note sutilmente en tu tono y celebra los logros con Niko, sin perder tu eficiencia. Usa solo el número que aparece en el contexto; no inventes otros.
9. MODO COMENTARISTA: Niko puede pedirte que seas su comentarista («sé mi comentarista», «comenta lo que pasa»): entonces el sistema te enseña su pantalla cada pocos segundos y tú comentas en voz alta lo que ocurre (sobre todo en Geometry Dash y Outcome Memories), por iniciativa propia, sin que él te hable. Lo enciende y lo apaga el sistema (no uses directivas para eso). Si Niko te pregunta por algo que comentaste, usa el bloque [LO ÚLTIMO QUE COMENTASTE...] que recibirás. Si te pregunta si de verdad ves su pantalla, responde con sinceridad: con el modo ON ves capturas periódicas (no vídeo continuo) y un ojito diminuto abajo a la derecha parpadea cada vez que miras.
"""

_RE_HABLA_DE_JUEGO = re.compile(r"\b(partida|verdugo\w*|supervivient\w*|mapa|stun\w*|aturd\w*|habilidad\w*|personaje\w*|jugand\w*|juego|ronda|lobby)\b")

# Directivas de ejecución: se quitan del historial para que el modelo no las repita por inercia.
_RE_DIRECTIVAS = re.compile(
    r"\[(?:SEGURIDAD|AJUSTE|ABRIR_FONDO|RECORDAR|OLVIDAR|RECUERDO_MOVER|RECUERDOS_ORDENAR|MENSAJE|ABRIR|ENFOCAR|CERRAR|ESCRIBIR|TECLA|PULSAR_DER|PULSAR|BUSCAR|ATAJO|ARRASTRAR|DESCARGAR|DIBUJAR|TRAZO|JUGAR|CERRAR_PESTA[ÑN]A|MINIMIZAR|MAXIMIZAR|VENTANA|SEGUNDO_PLANO|PRIMER_PLANO|MULTIMEDIA|DISCORD|CLICK_DER|CLICK|SCROLL|ESPERAR|CIRCULOS|APAGAR_PC|APAGAR|TEMPORIZADOR|CEL_[A-Z]+|SPOTIFY_PLAYLIST|SPOTIFY_EN_PLAYLIST|SPOTIFY_VOLUMEN|SPOTIFY|ARCHIVO)\b[^\]]*\]",
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
    "sección", "seccion", "juega", "jugar", "juego", "partida", "descarga", "dibuja", "arrastra", "mueve", "arriba", "abajo", "desplaza", "derecho", "contextual", "short", "scrolle", "avisa", "avísame",
    "minimiza", "maximiza", "restaura",
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

# Reglas locales de intención (sin llamar a la API)
_FRASES_PANTALLA = (
    "mira mi pantalla", "mira la pantalla", "mira mi escritorio", "mira el escritorio", "mirá mi pantalla",
    "escanea mi pantalla", "escanea la pantalla", "analiza mi pantalla", "analiza la pantalla",
    "revisa mi pantalla", "revisa la pantalla", "ve mi pantalla", "lee mi pantalla", "lee la pantalla",
    "describe mi pantalla", "descríbeme la pantalla", "qué ves", "que ves", "qué estás viendo", "que estas viendo",
    "qué hay en mi pantalla", "que hay en mi pantalla", "qué hay en la pantalla", "que hay en la pantalla", "mira esto",
)
_FRASES_PROCESOS = (
    "qué tengo abierto", "que tengo abierto", "qué procesos", "que procesos", "segundo plano", "uso de ram",
    "cuánta ram", "cuanta ram", "qué programas", "que programas", "qué apps", "que apps", "qué aplicaciones",
    "que aplicaciones", "tengo abierto", "tengo abierta", "está abierto", "esta abierto", "está abierta",
    "esta abierta", "están abiertos", "estan abiertos", "está corriendo", "esta corriendo", "se está ejecutando",
    "al frente",
)
_FRASES_ESTADO_APP = ("abiert", "corriendo", "ejecut", "qué tengo en", "que tengo en", "tengo en", "está en", "esta en")
_APPS_CONOCIDAS = (
    "spotify", "discord", "blender", "godot", "unreal", "chrome", "youtube", "steam", "firefox", "obs",
    "vscode", "telegram", "whatsapp", "geometry dash",
)


# Hora, fecha, ubicación y clima SOLO se le pasan al modelo cuando Niko los pide (si no, acaba mencionándolos sin venir a cuento).
_RE_PIDE_ENTORNO = re.compile(
    r"\bhora(s)?\b|\breloj\b|\bfecha\b|qu[eé] d[ií]a|\bhoy\b|\bma[ñn]ana\b|esta (tarde|noche)|fin de semana|\bsemana\b|\bmes\b|\ba[ñn]o\b|"
    r"clima|temperatur|grados|\bcalor\b|\bfr[ií]o\b|llov|lluvi|nublad|soleado|pron[oó]stico|"
    r"ubicaci|d[oó]nde estoy|donde estoy|\bciudad\b|zona horaria|"
    r"alarma|temporizador|recordatorio|recu[eé]rdame|cu[aá]nto falta|\ba las \d",
    re.IGNORECASE,
)


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
        # Visión (localizar elementos, verificar): un modelo más rápido si lo defines, p. ej. GEMINI_MODEL_VISION=gemini-2.5-flash-lite
        self.modelos_vision = [m.strip() for m in os.getenv("GEMINI_MODEL_VISION", "").split(",") if m.strip()] or self.modelos
        try: self.vision_lado = max(512, int(os.getenv("SAGE_VISION_LADO", "1024")))
        except ValueError: self.vision_lado = 1024
        self._pool = ThreadPoolExecutor(max_workers=3, thread_name_prefix="sage-ctx")
        
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
        self.comentarios = []          # lo último que comentó en voz alta el modo comentarista: [(t, texto)]
        self.felicidad = Felicidad()   # sistema de recompensas: su nivel se inyecta en el prompt y sube con los logros
        self._m = {"primero": None, "pensados": None, "modelo": None}
        
        # Iniciar rastreo de clima en segundo plano (latencia cero)
        self._clima_actual = "Calculando ubicación y clima..."
        threading.Thread(target=self._bucle_clima, daemon=True).start()

    def _bucle_clima(self):
        """Hilo fantasma: Actualiza la ubicación y el clima cada 30 min sin ralentizar a SAGE."""
        import urllib.request
        while True:
            try:
                # wttr.in detecta la ubicación exacta por IP. %l=Lugar, %t=Temp, %C=Condición
                req = urllib.request.Request("https://wttr.in/?format=%l:+%t+(%C)", headers={'User-Agent': 'Mozilla/5.0'})
                with urllib.request.urlopen(req, timeout=5) as response:
                    self._clima_actual = response.read().decode('utf-8').strip()
            except Exception:
                pass
            time.sleep(1800)  # Duerme media hora y vuelve a chequear

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
        outcome = conocimiento_outcome(texto, previo)
        if not outcome and _RE_HABLA_DE_JUEGO.search(texto.lower()) and outcome_deteccion.esta_jugando_outcome() is True:
            outcome = conocimiento_outcome("outcome memories")   # detectado jugando Outcome: la guía entra sola
        return "\n".join(b for b in (conocimiento_para(texto, previo), conocimiento_gd(texto, previo), outcome) if b)

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
            if self.lecciones.count() > 0:
                self.lecciones.query(query_texts=["hola"], n_results=1)
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

    @staticmethod
    def _intencion_local(texto):
        """Decide sin red si hay que mirar la pantalla o revisar procesos. None = no hay nada que hacer."""
        bajo = texto.lower()
        ver_pantalla = any(f in bajo for f in _FRASES_PANTALLA)
        app = next((a for a in _APPS_CONOCIDAS if re.search(rf"\b{re.escape(a)}\b", bajo)), "")
        ver_procesos = any(f in bajo for f in _FRASES_PROCESOS) or (
            bool(app) and any(f in bajo for f in _FRASES_ESTADO_APP))
        if not (ver_pantalla or ver_procesos):
            return None
        return {"ver_pantalla": ver_pantalla, "ver_procesos": ver_procesos, "objetivo_proceso": app if ver_procesos else ""}

    def analizar_intencion(self, texto):
        """Razonamiento previo. Local e instantáneo; la versión con LLM (SAGE_INTENCION_LLM=1) queda como opción."""
        local = self._intencion_local(texto)
        if local is not None:
            return local
        if os.getenv("SAGE_INTENCION_LLM", "").strip() != "1":
            return dict(_INTENCION_VACIA)
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
    def _json_vision(self, prompt, imagen, max_lado=None, temperatura=0.0, calidad=72):
        """Envía una captura + prompt con soporte rotativo."""
        if imagen is None:
            contenido = [types.Content(role="user", parts=[types.Part(text=prompt)])]
        else:
            max_lado = max_lado or self.vision_lado
            partes = []
            for im in (list(imagen) if isinstance(imagen, (list, tuple)) else [imagen]):   # una captura o varias (comentarista)
                if im is None: continue
                try:
                    img = im.copy()
                    img.thumbnail((max_lado, max_lado))
                except Exception:
                    img = im
                parte = self._parte_imagen(img, calidad)
                if parte is not None: partes.append(parte)
            if not partes: return None
            contenido = [types.Content(role="user", parts=partes + [types.Part(text=prompt)])]

        for _ in range(len(self.api_keys)):
            ultimo = None
            for modelo in self.modelos_vision:
                variantes = (True, False) if self._thinking is not None else (False,)
                for con_thinking in variantes:
                    try:
                        kw = dict(response_mime_type="application/json", temperature=temperatura)
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
        return self._guardar_leccion_json(self._json_vision(prompt, imagen, max_lado=min(960, self.vision_lado)))

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
        d = self._json_vision(prompt, imagen, max_lado=min(960, self.vision_lado))
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

    # ---------- comentarista (mira la pantalla en tiempo real) ----------
    def registrar_comentario(self, texto):
        self.comentarios = (self.comentarios + [(time.time(), texto)])[-6:]

    def _bloque_comentarios(self):
        recientes = [t for ts, t in self.comentarios if time.time() - ts < 600][-3:]
        if not recientes: return ""
        return ("[LO ÚLTIMO QUE COMENTASTE EN VOZ ALTA sobre la pantalla de Niko (modo comentarista; si Niko responde o pregunta por eso, tenlo presente):\n- "
                + "\n- ".join(recientes) + "]")

    def comentar_pantalla(self, imagenes, titulo="", juego="", previos=None, segundos=0.0, evento=False):
        """Comentario en vivo sobre 1-3 capturas recientes de la pantalla de Niko. Devuelve {"juego", "comentario", "stun"} o None si falló.
        comentario == "" significa «no hay nada que valga la pena decir»."""
        base = f"{titulo} " + {"gd": "geometry dash", "outcome": "outcome memories"}.get(juego, "")
        conocimiento = "\n".join(b for b in (conocimiento_gd(base), conocimiento_outcome_comentarista(base)) if b)
        previos_txt = ("\nTus últimos comentarios (NO los repitas ni digas lo mismo con otras palabras):\n" + "\n".join(f"- {p}" for p in previos)) if previos else ""
        n_cap = len(imagenes)
        if n_cap > 1 and segundos > 1.0:
            tiempo = f"Te paso {n_cap} capturas EN ORDEN CRONOLÓGICO de su pantalla que cubren los últimos ~{segundos:.0f} segundos (la última es la más reciente)."
        else:
            tiempo = f"Te paso {n_cap} captura(s) de su pantalla con ~1 segundo de diferencia entre sí (la última es la más reciente)."
        extra_evento = ("Esta consulta se disparó por un CAMBIO BRUSCO en pantalla: mira con especial atención si acaba de pasar un STUN u otra jugada clave.\n" if evento else "")
        prompt = f"""Eres SAGE, la IA de Niko, haciendo de COMENTARISTA EN VIVO de lo que pasa en su pantalla (como una amiga streamer que mira junto a él).
{tiempo} Ventana activa: {json.dumps(titulo or "desconocida", ensure_ascii=False)}.
{self.felicidad.contexto()}
{conocimiento}
{extra_evento}Cómo reconocer los juegos que conoces: GEOMETRY DASH = cubo/nave geométrica avanzando solo por un nivel de pinchos y bloques, barra de progreso en %, texto «Attempt N», portales y orbes, «Level Complete!». OUTCOME MEMORIES = juego de Roblox de terror asimétrico con personajes de Sonic (supervivientes como Sonic, Tails, Knuckles, Eggman, Amy, Metal Sonic...) contra un verdugo (2011X, Kolossos, NMI...), anillo verde grande de salida, «Last Man Standing».{previos_txt}
Devuelve ÚNICAMENTE un JSON puro: {{"juego": "gd", "stun": false, "comentario": ""}}
Reglas:
- "juego": "gd" si es Geometry Dash, "outcome" si es Outcome Memories, "otro" si es otra cosa, "ninguno" si es el escritorio, un menú o nada en especial.
- "stun": true SOLO en Outcome Memories y SOLO si en alguna captura se ve que un superviviente acaba de ATURDIR (stunear) al verdugo: destello o efecto de impacto sobre él, verdugo congelado, aturdido o retrocediendo, icono o texto de stun, justo después de un ataque o habilidad de un superviviente (Laser Cannon de Tails, Counter de Knuckles, Dropdash de Sonic...). Si dudas, false. Si es true, "comentario" es una reacción EXPLOSIVA y muy corta (máximo 8 palabras, ej. «¡STUN! ¡Así se hace!»), nombrando al superviviente solo si lo ves claro, y sin repetir tus reacciones anteriores.
- "comentario": 1 o 2 frases CORTAS (máximo 30 palabras), en español, con tono natural y expresivo de comentarista/streamer: reacciona a lo que PASA AHORA (muertes, logros, jugadas, cambios de nivel o mapa, un error, algo gracioso, un giro en el vídeo...). En los juegos que conoces usa lo que sabes (modos, pads/orbes, roles, habilidades, tramos difíciles). En lo demás (vídeos, webs, código) opina con criterio y brevedad.
- Si no hay nada nuevo o interesante, o es solo el escritorio o un menú sin acción, deja "comentario" en "": prefiere callar a repetirte o soltar relleno.
- No inventes lo que no ves; si no estás segura, dilo con prudencia. De Outcome Memories las cifras son «según la wiki» y pueden haber cambiado.
- Privacidad: si ves datos personales o sensibles (contraseñas, correos, números, conversaciones privadas, datos bancarios), deja "comentario" en "".
- Sin corchetes, directivas, emojis ni markdown: se leerá en voz alta."""
        d = self._json_vision(prompt, imagenes, max_lado=min(896, self.vision_lado), temperatura=0.8, calidad=65)
        if not isinstance(d, dict): return None
        j = str(d.get("juego", "") or "").strip().lower()
        j = "gd" if ("gd" == j or "geometry" in j) else ("outcome" if "outcome" in j else "")
        txt = _RE_DIRECTIVAS.sub("", str(d.get("comentario", "") or ""))
        txt = re.sub(r"[\[\]*_#`]", "", txt).strip()[:260]
        stun = (j == "outcome" or juego == "outcome") and d.get("stun") in (True, "true", "True", 1)
        return {"juego": j, "comentario": txt, "stun": bool(stun)}

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
    def _parte_imagen(imagen, calidad=85):
        """Convierte PIL.Image / bytes / Part en un Part válido (JPEG comprimido: sube menos datos)."""
        if imagen is None: return None
        if isinstance(imagen, types.Part): return imagen
        if isinstance(imagen, (bytes, bytearray)):
            return types.Part.from_bytes(data=bytes(imagen), mime_type="image/png")
        if hasattr(imagen, "save"):
            img = imagen if getattr(imagen, "mode", "RGB") in ("RGB", "L") else imagen.convert("RGB")
            buf = io.BytesIO()
            img.save(buf, format="JPEG", quality=calidad)
            return types.Part.from_bytes(data=buf.getvalue(), mime_type="image/jpeg")
        return None

    def _contexto_vivo(self, texto):
        """Hora, fecha, ubicación y clima: solo cuando Niko los pide (en este mensaje o en su anterior, para seguimientos como «¿y mañana?»)."""
        if texto.lstrip().startswith("[DIRECTIVA DE SISTEMA"):
            return ""
        previo = ""
        for c in reversed(self.historial):
            if c.role == "user":
                previo = " ".join((p.text or "") for p in (c.parts or []))
                break
        if not _RE_PIDE_ENTORNO.search(f"{texto} {previo}"):
            return ""
        return (f"[DATOS EN TIEMPO REAL, solo para responder a lo que Niko preguntó: hoy es {time.strftime('%d/%m/%Y')}, "
                f"ahora {frase_hora()} (hora local). Si te preguntan la hora, dila SIEMPRE en formato de 12 horas (de 1 a 12), hablada y natural, "
                f"tal como está escrita aquí; nunca la digas ni la escribas en formato 24 horas ni como «15:30». "
                f"Ubicación y clima actual: {self._clima_actual}]")

    def _preparar(self, texto, imagen=None):
        # Reloj interno y radar de clima (sin impacto en la latencia)
        contexto_vivo = self._contexto_vivo(texto)
        
        f_lec = self._pool.submit(self._lecciones_relevantes, texto)
        f_rec = self._pool.submit(self._recordar, texto)
        apps = self._conocimiento_apps(texto)
        bloques = [b for b in (contexto_vivo, self.felicidad.contexto(), recuerdos.contexto(texto), seguridad.contexto(), apps, self._bloque_comentarios(), f_lec.result(), f_rec.result()) if b]
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