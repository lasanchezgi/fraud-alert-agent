
# Agente investigador de alertas de fraude (pitch GEAR, 3 nov 2026)

## Qué es

Proyecto personal para el Lightning Pitch de Academia GEAR. Agente en ADK (Python)
que investiga alertas sintéticas de transferencias inmediatas y propone un dictamen
con evidencia. Datos 100 % sintéticos: nunca uses datos, reglas, umbrales ni
sistemas reales de ningún banco.

## Decisiones de diseño (no las cambies sin preguntarme)

- Las herramientas reciben alert_id y calculan todo con SQL fijo y parametrizado.
  El LLM nunca escribe SQL.
- "Ahora" = created_ts de la alerta, nunca el reloj del sistema.
- DATA_BACKEND=sqlite|bigquery: misma interfaz y mismos resultados.
- create_case_draft es la única escritura: FunctionTool(..., require_confirmation=True).
- Modelo: Gemini en Vertex AI, temperatura baja.
- Sin herramientas built-in (google_search, VertexAiSearchTool) y sin sub-agentes.

## Validación

- pytest tests/test_tools.py debe pasar antes de tocar el agente.
  Los valores esperados están en HANDBOOK.md (Fase 2).
- Si regeneras los datos, recalcula los valores esperados.
- Verifica ejecutando y dime la versión de google-adk instalada.

## Forma de trabajo

Español, directo; comandos y nombres de API en inglés. Antes de cambiar un archivo,
explica el porqué y haz la edición mínima. No reescribas lo que ya funciona.
