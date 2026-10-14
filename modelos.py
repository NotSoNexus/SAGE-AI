"""Lista los modelos de Gemini disponibles para generateContent.

Uso:
    python modelos.py            # todos
    python modelos.py flash      # solo los que contengan "flash"
"""
import os
import sys

from dotenv import load_dotenv
from google import genai

AQUI = os.path.dirname(os.path.abspath(__file__))


def main():
    load_dotenv(os.path.join(AQUI, ".env"))
    api_key = os.getenv("GEMINI_API_KEYS")
    if not api_key:
        print("Falta GEMINI_API_KEYS en .env")
        return 1

    filtro = sys.argv[1].lower() if len(sys.argv) > 1 else ""
    en_uso = [m.strip() for m in os.getenv("GEMINI_MODEL", "").split(",") if m.strip()]

    try:
        client = genai.Client(api_key=api_key)
        modelos = list(client.models.list())
    except Exception as e:
        print(f"No se pudo consultar la API: {e}")
        return 1

    filas = []
    for m in modelos:
        if "generateContent" not in (getattr(m, "supported_actions", None) or []):
            continue
        nombre = (m.name or "").removeprefix("models/")
        if filtro and filtro not in nombre.lower():
            continue
        filas.append((
            nombre,
            getattr(m, "input_token_limit", None) or "-",
            getattr(m, "output_token_limit", None) or "-",
        ))
    filas.sort()

    if not filas:
        print("No hay modelos que coincidan.")
        return 0

    ancho = max(len(f[0]) for f in filas)
    print(f"Modelos disponibles para generateContent ({len(filas)}):\n")
    print(f"{'MODELO':<{ancho}}  {'ENTRADA':>10}  {'SALIDA':>8}")
    for nombre, entrada, salida in filas:
        marca = "  <- en uso (.env)" if nombre in en_uso else ""
        print(f"{nombre:<{ancho}}  {entrada:>10}  {salida:>8}{marca}")

    ausentes = [m for m in en_uso if m not in {f[0] for f in filas}]
    if ausentes:
        print(f"\nAviso: en tu .env hay modelos que no aparecen en la lista: {', '.join(ausentes)}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
