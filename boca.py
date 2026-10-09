import os
import asyncio
import threading
import queue
import uuid
import edge_tts
import pygame

pygame.mixer.init()
VOZ_SAGE = "es-MX-DaliaNeural"

cola_audio = queue.Queue()

def _worker_voz():
    """Hilo con bucle de eventos persistente para cero lag en la app."""
    loop = asyncio.new_event_loop()
    asyncio.set_event_loop(loop)

    while True:
        texto = cola_audio.get()
        if texto is None:
            break
        
        texto_limpio = texto.replace("*", "").replace("#", "").strip()
        if not texto_limpio:
            cola_audio.task_done()
            continue

        archivo_temp = f"sage_voice_{uuid.uuid4().hex}.mp3"
        
        async def generar_audio():
            comunicador = edge_tts.Communicate(texto_limpio, VOZ_SAGE, rate="+25%")
            await comunicador.save(archivo_temp)
        
        try:
            loop.run_until_complete(generar_audio())
            pygame.mixer.music.load(archivo_temp)
            pygame.mixer.music.play()
            while pygame.mixer.music.get_busy():
                pygame.time.Clock().tick(10)
        except Exception as e:
            print(f"[SAGE AUDIO ERROR]: {e}")
        finally:
            pygame.mixer.music.unload()
            if os.path.exists(archivo_temp):
                try: os.remove(archivo_temp)
                except: pass
        
        cola_audio.task_done()

hilo_voz = threading.Thread(target=_worker_voz, daemon=True)
hilo_voz.start()

def hablar(texto):
    if texto.strip():
        cola_audio.put(texto)

def esta_hablando():
    return not cola_audio.empty() or pygame.mixer.music.get_busy()