"""Conocimiento de memoria sobre Geometry Dash para SAGE.

cerebro.py lo inyecta en el contexto cuando Niko habla de Geometry Dash, y gd_jugador.py / app.py lo usan al jugar.
"""
import re

NIVELES = (
    "stereo madness", "back on track", "polargeist", "dry out", "base after base", "cant let go", "jumper",
    "time machine", "cycles", "xstep", "clutterfunk", "theory of everything", "electroman adventures", "clubstep",
    "electrodynamix", "hexagon force", "blast processing", "theory of everything 2", "geometrical dominator",
    "deadlocked", "fingerdash", "dash",
)

CONOCIMIENTO_GD = """
=== CONOCIMIENTO DE GEOMETRY DASH (de memoria) ===
[QUÉ ES] Juego de plataformas de ritmo de RobTop. El personaje avanza SOLO a velocidad constante; el jugador solo controla UNA acción
(espacio / flecha arriba / click / W) con el timing justo, siguiendo la música. Tocar un pincho, sierra o el lado de un bloque = morir y reiniciar
el nivel desde el principio (o desde el último checkpoint en Modo Práctica). Steam: steam://rungameid/322170.

[MENÚ] Botón verde grande "Play" > carrusel de niveles (flechas izquierda/derecha) > "Play" del nivel. Esc = pausa (Resume, Practice Mode, Exit).
Modo Práctica: pone checkpoints (diamantes verdes); no cuenta como completar el nivel. Barra de progreso (%) opcional arriba. Al completar sale "Level Complete!".

[NIVELES OFICIALES, por orden] 1 Stereo Madness (fácil, el primero), 2 Back on Track, 3 Polargeist, 4 Dry Out, 5 Base After Base, 6 Can't Let Go,
7 Jumper, 8 Time Machine, 9 Cycles, 10 xStep, 11 Clutterfunk, 12 Theory of Everything, 13 Electroman Adventures, 14 Clubstep, 15 Electrodynamix,
16 Hexagon Force, 17 Blast Processing, 18 Theory of Everything 2, 19 Geometrical Dominator, 20 Deadlocked, 21 Fingerdash, 22 Dash.

[MODOS DE JUEGO — cada portal cambia el modo]
- CUBO (portal verde): un click = un salto. Mantener pulsado = vuelve a saltar al aterrizar. Es el modo base.
- NAVE (portal rosa): MANTENER pulsado = sube, SOLTAR = baja. Se controla con toques cortos para mantener la altura.
- BOLA (portal rojo): cada click invierte la gravedad (rueda por suelo o techo).
- OVNI/UFO (portal naranja): cada click da un saltito en el aire (se puede repetir en el aire).
- ONDA/WAVE (portal azul): mantener = sube en diagonal, soltar = baja en diagonal. Los pasillos son estrechos.
- ROBOT (portal blanco): mantener = salto más alto; ROBOT/ARAÑA: la araña (portal morado) se teletransporta al otro lado con cada click.
- Swing Copter (2.2): click invierte la dirección vertical.
Portales de gravedad: azul = gravedad normal, amarillo = gravedad invertida. Portales de tamaño: pequeño (mini) / normal. Portal de espejo, dual (dos jugadores a la vez).
Portales de VELOCIDAD: naranja = lento (0.5x), azul = normal (1x), verde = rápido (2x), rosa = más rápido (3x), rojo = el más rápido (4x).

[PADS Y ORBES — saltos especiales]
- Pad (en el suelo, se activa solo al pisarlo): amarillo = salto alto, rosa = salto bajo, rojo = salto muy alto, azul = invierte gravedad.
- Orbe (en el aire, hay que hacer click justo cuando lo tocas): amarillo = salto, rosa = salto pequeño, rojo = salto grande, azul = invierte gravedad,
  verde = invierte y salta, negro = baja de golpe, orbes con flecha = dash.
- Moneda secreta (amarilla) y llaves: coleccionables opcionales.

[PELIGROS] Pinchos (triángulos negros: el hitbox es MÁS PEQUEÑO que el dibujo), sierras giratorias, cuchillas, espinas en el suelo/techo, lados de bloques.
La parte de ARRIBA de un bloque es segura (se aterriza y se sigue); chocar de frente contra su lado mata. Bloques en el techo también matan en nave/onda.

[ESTRATEGIA]
- Cubo: salta un poco ANTES de que el pincho llegue (unos 2 bloques con velocidad 1x); a mayor velocidad hay que saltar antes en distancia.
- Pinchos dobles/triples: un salto largo los cubre; un click mantenido salva escaleras de bloques.
- Nave/onda: toques cortos y constantes; no mantener demasiado tiempo.
- Aprende el nivel por tramos: cada muerte indica el tramo difícil; repite ese tramo variando el momento del salto.
- Sigue el ritmo de la música: los obstáculos están colocados al compás.

[CÓMO APRENDE SAGE A JUGARLO] Geometry Dash exige reacciones en milisegundos, así que SAGE usa un jugador de reflejos local (gd_jugador.py) que mira
la pantalla EN VIVO A 60 FPS (solo mientras juega), detecta pinchos/bloques delante del cubo, mide la velocidad real del scroll y salta en el momento justo.
Geometry Dash es determinista: en cada intento guarda cuántos saltos dio antes de morir y, en el intento siguiente, prueba otro timing SOLO en los últimos saltos
(gd_aprendizaje.json); si el intento dura más, conserva el cambio. Mejora con los intentos, pero no es instantáneo ni infalible: no sabe usar orbes ni los modos
distintos del cubo y la nave (F9 alterna cubo/nave); los portales de gravedad y los saltos que exigen click en el aire quedan fuera de su alcance.
[RECOMPENSAS] SAGE tiene un nivel de felicidad (0-100, sage_felicidad.json) que sube al jugar: el % del nivel se estima por tiempo (tiempo vivo / duración del nivel;
la duración se mide sola al completarlo). Cada % que sube da una pequeña recompensa; superar su récord de progreso da más y celebra en voz alta en el 25, 50, 75 y 90 %;
completar un nivel da una recompensa grande. La felicidad se enfría con las horas, así que se la gana jugando.
=== FIN DEL CONOCIMIENTO DE GEOMETRY DASH ===
"""

_PISTAS = ("geometry dash", "geometrydash", "stereo madness", "robtop", "geometry")


def es_gd(texto):
    t = (texto or "").lower()
    return any(p in t for p in _PISTAS) or bool(re.search(r"\bgd\b", t))


def nivel_en(texto):
    """Nombre del nivel oficial mencionado en el texto (o 'generico')."""
    t = re.sub(r"[^a-z0-9 ]", "", (texto or "").lower().replace("'", ""))
    for n in sorted(NIVELES, key=len, reverse=True):
        if n in t:
            return n
    return "generico"


def conocimiento_gd(texto, previo=""):
    """Devuelve el bloque de conocimiento si se habla de Geometry Dash (ahora o en los últimos turnos)."""
    return CONOCIMIENTO_GD if es_gd(texto) or es_gd(previo) else ""
