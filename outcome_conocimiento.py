"""Conocimiento sobre Outcome Memories (juego fan de Roblox, «Sonic.EXE: Outcome Memories») para SAGE.

- conocimiento_outcome(): bloque COMPLETO, para cuando Niko habla del juego (cerebro.py).
- conocimiento_outcome_comentarista(): bloque COMPACTO + guía de comentarista, para el comentarista en vivo (se manda cada ~10 s: ahorra tokens).

Fuentes (octubre de 2026): The Unofficial Outcome Memories Wiki (Fandom bloquea la descarga directa: se usaron sus extractos de búsqueda),
Disasterpedia, Miraheze, NamuWiki, TV Tropes y la guía de AllThingsHow sobre v0.2 (actualizada 4-sep-2026, con fechas y cambios de parche).
El juego cambió mucho y su desarrollo se canceló: SAGE debe presentar las cifras como «según la wiki» y admitir que pueden estar desactualizadas.
"""
import re

CONOCIMIENTO_OUTCOME = """
=== CONOCIMIENTO DE OUTCOME MEMORIES (wiki no oficial + guías; puede estar desactualizado) ===
[QUÉ ES] Juego fan de Roblox de terror ASIMÉTRICO (1 Verdugo/Executioner contra varios Supervivientes), inspirado en «Sonic.EXE: The Disaster».
Personajes de SEGA/Sonic Team en un purgatorio/«vacío» que se reinicia sin fin (no están afiliados con SEGA). Hecho por Team Red Ring. Moneda: RINGS (anillos),
con los que se compran verdugos y cosméticos (el verdugo básico 2011X es gratis). Página oficial: https://www.roblox.com/games/14608970270

[ESTADO DEL JUEGO] Versión actual: V0.2 «No way back» (aniversario), lanzada el 13-dic-2025. Trajo 3 supervivientes, 3 verdugos, 2 mapas nuevos + Green Hill rehecho,
20 habilidades, 80 cosméticos y 40 emotes. Desarrollo PAUSADO el 12-ene-2026 (disputa con el desarrollador principal 1sobbe y problemas de comunicación) y CANCELADO
formalmente el 26-ene-2026; parte del equipo siguió hacia una última gran actualización, sin fecha confirmada. Existen recodes/recreaciones de fans. Si Niko pregunta
por el futuro del juego, di esto con prudencia y que puede haber novedades que no conozco.

[PARTIDA] Lobby: tablones en la pared (GAME RULES, changelog y «SERVER VERSION: V0.2»); se elige rol y personaje (el verdugo se sortea según tu «killer chance»).
El verdugo aparece lejos de los supervivientes. Los supervivientes ganan sobreviviendo hasta ~1:19-1:20: entonces aparece un ANILLO DE SALIDA (gran anillo verde) y escapan.
El verdugo gana ejecutando a todos. Si solo queda uno vivo: LMS (Last Man Standing / «Solo»), con música propia y bonos (p. ej. resistencia al daño); NO se activa si al
menos otro superviviente ya escapó. En LMS el verdugo puede entrar en Rage Mode. Los mapas rotan por partida y cambian el balance.
Servidores privados: el anfitrión sube/baja la probabilidad de verdugo, fija el personaje y elige mapa libremente.

[MAPAS] Green Hill (rehecho: spawns más juntos, así que el verdugo presiona antes al grupo), Angel Island (nuevo), Mystic Cave (nuevo). Pizzeria fue ELIMINADO por rendimiento.
Green Hill y Angel Island recortaron la hierba al 50 %; hay un ajuste «Fast Mode» que quita detalles del mapa. Solo en privados: TD Hills, TD YCR, OM Backrooms, Egg Room, Green Hill 5-1.

[MECÁNICAS] Vida: los supervivientes empiezan con 100 (Metal Sonic 175); casi todos caen en 3 golpes desde vida completa. Un superviviente caído (down) puede ser revivido por otros.
STUN: los supervivientes aturden al verdugo; tras un stun el verdugo tiene fotogramas de invulnerabilidad. «Terror Radius»: música/tensión que sube cuando el verdugo está cerca.
«Prioridad de superviviente» decide a quién golpea primero el verdugo. AGUA con sistema de OXÍGENO (ahogarse ya no es un temporizador fijo: se mide el tiempo sumergido; hay que salir
antes de que se vacíe). Estados nuevos: SANGRADO (Bleed) y ELECTRIZADO (Shocked). Ajuste «M1 turn»: al atacar tu personaje gira hacia donde apunta la cámara. La puntería de habilidades se reprogramó.
HUD: la barra de habilidades está ABAJO A LA DERECHA (ejemplos vistos: Laser Cannon, Glide, Switch).

[SUPERVIVIENTES EN ROTACIÓN] Sonic, Tails, Knuckles, Eggman, Amy, Cream, Metal Sonic, Blaze, Silver. SHADOW está fuera de rotación hasta terminar su rework. Solo en privados: sans, Baldi, Neo Metal Sonic, Fri sk, Clover (entre otros).
- SONIC: todoterreno de «golpear y huir», el más rápido. Dropdash (movilidad + stun), Peelout (huir y recoger aliados), esquiva pasiva.
- TAILS: francotirador a distancia con Laser Cannon; stun a distancia, fácil de acertar y de los más largos. Débil cuerpo a cuerpo; vuela.
- KNUCKLES: luchador de defensa; Counter (contra-ataque), puñetazo cargado, Glide; ideal para salvar aliados.
- EGGMAN: tanque/soporte; doble salto pasivo, Jetpack Boost, Energy Shield, apoya a Metal Sonic.
- AMY: cartas; su Moon Card recibió un REWORK importante en v0.2.
- CREAM: soporte (con Cheese); su curación ahora ESCALA con cuántos supervivientes cura a la vez (curar en masa rinde más que el toque individual).
- BLAZE: Burning Javelin; v0.2 subió el daño de su patada y ajustó Sol Flame.
- SILVER: psíquico; v0.2 le bajó la vida a 100 y modificó sus habilidades de vuelo y suspensión: su movilidad es su defensa.
- METAL SONIC: tanque/staller; Destructive Charge (embiste y aturde), Self Repair (se cura quieto), sensor del verdugo, mucha resistencia al daño (75 % en LMS); al llegar a 0 explota y muere (stun de 5 s). Una sola vida.

[VERDUGOS EN ROTACIÓN (EXEs)] 2011X (básico y gratis): invisibilidad con teletransporte a un superviviente cercano, agarre/estrangulamiento con minijuego (WASD), God's Trickery (clones), Rage Mode;
v0.2 ajustó su visibilidad (menor cooldown de salida). KOLOSSOS: bruto pesado que separa equipos: Charge que empala, Grab que atraviesa Counter/Energy Shield, postura defensiva inmune a stuns pero lentísima;
v0.2 mejoró su escalada y ahora puede trepar para salir del agua. TRIPWIRE: verdugo de minas y láseres (variantes: una con colocación de minas más rápida y más daño de láser, otra con más daño de M1).
FLEETWAY SUPER SONIC: su BURST ahora funciona con un MEDIDOR (hay que gestionarlo, no solo pulsar); láser y vuelo ajustados. Hay 2 verdugos más solo en privados.
Mencionados en la wiki como antiguos, planeados o en desarrollo (puede que no estén en rotación): No More Innocence (NMI), Manic Super Sonic, KING, Chara, Starved, Korin!X, EYX, END, IMPERFECT.
Los verdugos con stun-immunity o grabs son la pesadilla de Sonic, Metal Sonic y Tails.

[CONSEJOS GENERALES] Supervivientes: quédense cerca para reanimarse y repartir stuns; no gasten el stun en vano (fallar se castiga); usen el mapa (altura para Tails; vigilen los bordes con agua: el oxígeno corre);
en LMS busquen el anillo o aguanten con las resistencias. Verdugos: aíslen a un objetivo, castiguen stuns fallidos, guarden Rage Mode / Burst para cuando decida la partida.

[HONESTIDAD] Lo que sé viene de wikis y guías no oficiales y el juego cambió mucho: da las cifras como «según la wiki» y no inventes datos. Si Niko quiere jugarlo, solo puedes abrir Roblox/el juego;
SAGE NO sabe jugarlo sola (su piloto automático es solo de Geometry Dash).
=== FIN DEL CONOCIMIENTO DE OUTCOME MEMORIES ===
"""

CONOCIMIENTO_OUTCOME_COMENTARISTA = """
=== OUTCOME MEMORIES PARA COMENTAR EN VIVO (según wikis no oficiales; el juego cambió y su desarrollo se canceló en ene-2026) ===
[CÓMO RECONOCERLO] Roblox, terror asimétrico con personajes de Sonic: 1 verdugo contra supervivientes. Pistas: barra de habilidades ABAJO A LA DERECHA (Laser Cannon, Glide, Switch...), cronómetro de ronda,
música que sube cuando el verdugo está cerca (Terror Radius), anillo verde GRANDE de salida (aparece hacia 1:19), música de «Last Man Standing», agarre con minijuego, lobby con tablones (GAME RULES, SERVER VERSION: V0.2).
[ELENCO ACTUAL] Supervivientes: Sonic (rápido, Dropdash), Tails (Laser Cannon a distancia), Knuckles (Counter, Glide), Eggman (escudo, jetpack), Amy (Moon Card), Cream (cura más cuantos más cura), Metal Sonic (tanque, 175 vida, explota al morir),
Blaze (patada, Sol Flame), Silver (100 vida, vuelo/suspensión). Shadow está fuera de rotación. Verdugos: 2011X (invisible + teletransporte, agarre, Rage), Kolossos (bruto, Charge, trepa y sale del agua), Tripwire (minas y láseres), Fleetway Super Sonic (Burst con medidor, láser, vuelo).
[MAPAS] Green Hill (spawns juntos), Angel Island, Mystic Cave. Agua con medidor de oxígeno; estados Sangrado y Electrizado.
[REGLAS] Supervivientes ganan aguantando hasta el anillo; el verdugo gana ejecutando a todos. Caen en 3 golpes (100 de vida); un caído se puede revivir. Stun al verdugo = jugada clave (falla = castigo). LMS = queda uno vivo (no se activa si otro ya escapó).
[QUÉ COMENTAR] Cada STUN acertado: reacciona AL INSTANTE con una exclamación corta («¡STUN!»). Además: stuns fallados, caídas, revives, persecuciones, agarres, el anillo apareciendo, escapes justos, wipe del equipo, LMS, Rage/Burst, ahogos, buenos usos de mapa. Nombra personaje, verdugo o mapa SOLO si lo ves claro; no asumas el rol de Niko, dedúcelo de lo que ves.
No inventes cifras ni cooldowns: di «según la wiki» si dudas.
=== FIN OUTCOME (COMENTARISTA) ===
"""

_PISTAS = ("outcome memories", "outcomememories", "sonic.exe", "sonic exe", "the disaster", "2011x", "kolossos", "no more innocence",
           "yaomr", "fleetway", "mystic cave", "angel island")


def es_outcome(texto):
    t = (texto or "").lower()
    return any(p in t for p in _PISTAS) or bool(re.search(r"\b(?:om|exe)\b.*\b(?:roblox|supervivient\w*|verdugo\w*)\b", t))


def conocimiento_outcome(texto, previo=""):
    """Bloque completo si se habla de Outcome Memories (ahora o en los últimos turnos)."""
    return CONOCIMIENTO_OUTCOME if es_outcome(texto) or es_outcome(previo) else ""


def conocimiento_outcome_comentarista(texto, previo=""):
    """Bloque compacto para el comentarista en vivo."""
    return CONOCIMIENTO_OUTCOME_COMENTARISTA if es_outcome(texto) or es_outcome(previo) else ""
