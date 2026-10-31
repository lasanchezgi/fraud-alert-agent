"""Valida que el modelo de MODEL responde en Vertex AI (validación 0.4)."""
import os
import sys
from pathlib import Path

from dotenv import load_dotenv
from google import genai
from google.genai import errors, types

ENV_PATH = Path(__file__).resolve().parent.parent / "investigador_alertas" / ".env"
load_dotenv(ENV_PATH)

model = os.environ["MODEL"]
project = os.environ["GOOGLE_CLOUD_PROJECT"]
location = os.environ["GOOGLE_CLOUD_LOCATION"]
print(f"Proyecto: {project} | Región: {location} | Modelo: {model}")

client = genai.Client(vertexai=True, project=project, location=location)
try:
    response = client.models.generate_content(
        model=model,
        contents="Escribe una frase corta de saludo en español.",
        config=types.GenerateContentConfig(temperature=0.2),
    )
except errors.APIError as e:
    print(f"ERROR {e.code} ({e.status}): {e.message}")
    sys.exit(1)

print(f"Respuesta: {response.text.strip()}")
