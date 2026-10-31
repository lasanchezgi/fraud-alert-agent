# Handbook – Agente investigador de alertas de fraude (GEAR)

Oct 30, 2026 · @Laura

Este handbook es el paso a paso para construir y presentar el agente antes del Lightning Pitch del Nov 3, 2026 a las 4:00 PM. Sigue las fases en orden, no avances una fase sin pasar sus validaciones y usa los puntos de inflexión para decidir cuándo recortar o activar el Plan B.

## Antes de empezar

Antes de abrir Claude Code, deja lista la carpeta del proyecto con su `CLAUDE.md` y una copia de este handbook. Con eso, cada fase arranca con un prompt corto.

- [ ] Descarga `generar_datos_sinteticos.py` desde la conversación del proyecto gcp\_gear donde se generó.
- [ ] Exporta este doc a Markdown y guárdalo como `HANDBOOK.md` en el repo. Claude Code no puede abrir el doc, pero sí leer ese archivo.
- [ ] Revisa que tengas Python 3.11 o superior (el generador se probó con 3.13) y `gcloud` instalado.
- [ ] Comenta el proyecto con tu líder: es personal y usa datos 100 % sintéticos. Hazlo antes del 3 nov.
- [ ] En Billing → Credits, revisa saldo, vencimiento y qué servicios cubren los créditos.

Estructura del repo:

```
fraud-alert-agent/
├── CLAUDE.md
├── HANDBOOK.md
├── generar_datos_sinteticos.py
├── datos_sinteticos/          ← lo crea el generador (CSV + SQLite)
├── investigador_alertas/      ← carpeta del agente (adk web la detecta)
│   ├── __init__.py            ← from . import agent
│   ├── agent.py               ← root_agent
│   ├── tools.py               ← las 6 herramientas
│   ├── data_backend.py        ← SQLite o BigQuery, misma interfaz
│   └── .env
├── tests/test_tools.py        ← valores esperados (Fase 2)
└── scripts/
    ├── load_bigquery.sh
    └── run_demo.py            ← corre las 3 alertas y registra la trayectoria
```

Contenido del `CLAUDE.md` (cópialo tal cual):

```markdown
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
```

Prompt de arranque para Claude Code:

> Lee CLAUDE.md y HANDBOOK.md. Crea la estructura de carpetas de la sección "Antes de empezar" y un venv. Instala google-adk, google-cloud-bigquery, python-dotenv y pytest. Corre generar\_datos\_sinteticos.py y confirma que imprime "Autoverificación OK". Dime la versión de google-adk instalada. Todavía no escribas herramientas.

## Ruta y compuertas

&#91;embedded content: ruta por día · 6 fases, 6 compuertas\]

Cada rombo es una compuerta con hora límite. Si llegas a ella sin cumplir su criterio, aplica la columna "Si no pasa" de Puntos de inflexión. Si G3 falla el sábado, el domingo empieza con el Plan B.

## Fase 0 — GCP listo

La meta es un proyecto personal con facturación, Vertex AI y BigQuery habilitados, y credenciales locales que funcionen. Calcula 30 a 45 minutos.

1. Verifica cuenta y proyecto, y habilita las APIs:

```bash
gcloud auth list                          # la activa (*) debe ser tu Gmail personal, no @udea.edu.co
gcloud auth login                         # solo si la activa no es la personal
gcloud config get-value project           # ¿es tu proyecto personal y no el de un lab?
export PROJECT_ID="<tu-proyecto>"
gcloud config set project $PROJECT_ID
gcloud billing projects describe $PROJECT_ID     # debe decir billingEnabled: true
gcloud services enable aiplatform.googleapis.com bigquery.googleapis.com
gcloud auth application-default login
gcloud auth application-default set-quota-project $PROJECT_ID
```

2. Crea un presupuesto en Billing → Budgets & alerts con alertas al 50, 90 y 100 %. Una alerta avisa, pero no corta el gasto. Calculo que esta demo cuesta unos pocos dólares; es una estimación mía, sin verificar.
3. Elige el modelo: en Vertex AI → Model Garden, el Gemini Flash más reciente. Los Gemini recientes responden en la región `global` y dan 404 en `us-central1` (verificado con `scripts/check_vertex.py`). Anota su nombre exacto.
4. Crea `investigador_alertas/.env`:

```
GOOGLE_GENAI_USE_VERTEXAI=TRUE
GOOGLE_CLOUD_PROJECT=<tu-proyecto>
GOOGLE_CLOUD_LOCATION=global
MODEL=<nombre exacto del modelo>
DATA_BACKEND=sqlite
BQ_DATASET=fraud_synth
```

Prompt para Claude Code:

> Escribe scripts/check\_vertex.py: que lea investigador\_alertas/.env y, con google-genai sobre Vertex AI, le pida al modelo MODEL una frase corta. Ejecútalo. Si falla, diagnostica la causa antes de cambiar nada (403 = permisos o API sin habilitar; 404 = nombre de modelo o región).

**Validaciones (compuerta G0)**

| # | Qué validar | Cómo | Resultado esperado |
| --- | --- | --- | --- |
| 0.1 | Cuenta activa | `gcloud auth list` | Tu Gmail personal, marcado con `*` |
| 0.2 | Facturación | `gcloud billing projects describe $PROJECT_ID` | `billingEnabled: true` |
| 0.3 | APIs | `gcloud services list --enabled \| grep -E "aiplatform\|bigquery"` | Aparecen las dos |
| 0.4 | Modelo responde | `python scripts/check_vertex.py` | Una frase, sin 403 ni 404 |
| 0.5 | Presupuesto | Consola de Billing | Alerta creada |

Si 0.4 sigue fallando después de 1 hora, aplica la compuerta G0 (sección Puntos de inflexión).

## Fase 1 — Datos sintéticos en BigQuery

La meta es tener las mismas 6 tablas en SQLite (respaldo local) y en BigQuery, con conteos idénticos. Calcula 30 minutos.

Usa esquemas explícitos en lugar de `--autodetect`: con DATETIME las fechas quedan sin zona horaria, igual que en SQLite. `case_drafts` se crea vacía con `bq mk` porque su CSV solo trae el encabezado. Estos comandos no los probé porque requieren tus credenciales.

```bash
python3 generar_datos_sinteticos.py            # debe imprimir "Autoverificación OK"
bq --location=US mk --dataset $PROJECT_ID:fraud_synth
L="bq load --replace --source_format=CSV --skip_leading_rows=1"
$L fraud_synth.customers    datos_sinteticos/customers.csv    customer_id:STRING,segment:STRING,city:STRING,signup_date:DATE
$L fraud_synth.accounts     datos_sinteticos/accounts.csv     account_id:STRING,customer_id:STRING,opened_date:DATE,key_created_date:DATE
$L fraud_synth.transactions datos_sinteticos/transactions.csv tx_id:STRING,ts:DATETIME,from_account:STRING,to_account:STRING,amount_cop:INT64,channel:STRING,status:STRING
$L fraud_synth.sessions     datos_sinteticos/sessions.csv     session_id:STRING,customer_id:STRING,ts:DATETIME,device_id:STRING,ip_country:STRING,contact_change_ts:DATETIME
$L fraud_synth.alerts       datos_sinteticos/alerts.csv       alert_id:STRING,tx_id:STRING,customer_id:STRING,created_ts:DATETIME,engine_score:FLOAT64,reason_codes:STRING,status:STRING
bq mk -t fraud_synth.case_drafts case_id:STRING,alert_id:STRING,created_ts:DATETIME,hypothesis:STRING,risk:STRING,recommendation:STRING,evidence_json:STRING,approved_by:STRING
```

BigQuery carga como NULL los campos vacíos del CSV, y SQLite los guarda como cadena vacía. Las herramientas deben tratar `''` y NULL igual (por ejemplo, `customer_id` de las cuentas externas).

Prompt para Claude Code:

> Convierte los comandos de la Fase 1 de HANDBOOK.md en scripts/load\_bigquery.sh, con set -e y verificando antes que gcloud auth list muestre mi Gmail personal y que el proyecto activo sea el de .env. Ejecútalo y luego corre las validaciones 1.1 a 1.5. Si algo no coincide, muéstrame la diferencia antes de corregir.

**Validaciones**

| # | Qué validar | Cómo | Resultado esperado |
| --- | --- | --- | --- |
| 1.1 | Dataset creado | `bq ls` | `fraud_synth`, ubicación US |
| 1.2 | Filas por tabla | `SELECT COUNT(*)` en cada tabla | customers 47 · accounts 65 · transactions 1.118 · sessions 1.114 · alerts 8 · case\_drafts 0 |
| 1.3 | Tipos | `bq show --schema fraud_synth.transactions` | `ts` es DATETIME |
| 1.4 | Consulta de control | `COUNT(DISTINCT from_account)` de transferencias con `to_account = 'M001'` entre `2026-11-01 12:01:00` y `2026-11-02 12:01:00` | 15 |
| 1.5 | Cuentas externas | `SELECT COUNT(*) FROM fraud_synth.accounts WHERE customer_id IS NULL` | 18 |

Si BigQuery no queda bien en 1 hora, sigue con SQLite y retoma BigQuery después de la Fase 2 (compuerta G2).

## Fase 2 — Las 6 herramientas

Las herramientas hacen todo el cálculo; el modelo solo razona sobre lo que devuelven. Esta fase cierra cuando `pytest` reproduce exactamente la tabla de valores esperados, primero en SQLite y después en BigQuery. Calcula 3 a 4 horas.

Reglas comunes a todas:

- Reciben `alert_id` y nada más (salvo `create_case_draft`). Así el modelo no puede pasar fechas o cuentas equivocadas.
- "Ahora" = `created_ts` de la alerta. Las ventanas son de 90 días para el comportamiento y de 24 horas para el beneficiario, ambas cerradas en ese instante.
- Devuelven un `dict` con `status` (`ok` o `error`) y campos con unidades en el nombre (`_cop`, `_days`, `_minutes`).
- El docstring le dice al modelo cuándo usarla y qué hipótesis ayuda a confirmar o descartar.

**Contratos**

| Herramienta | Devuelve | Ayuda a distinguir |
| --- | --- | --- |
| `get_alert` | Cliente, transacción, monto, beneficiario, score, códigos de razón, `created_ts` | Punto de partida |
| `analyze_behavior` | Transferencias en 90 días y su mediana (sin la de la alerta), monto vs. mediana, pagos previos a ese beneficiario y su mediana, monto vs. esa mediana, hora de la transferencia y rango horario habitual | Falso positivo vs. anomalía |
| `get_session_devices` | Dispositivos con número de sesiones, primera y última vez visto; si el dispositivo de la transferencia es nuevo (primera sesión en las 24 h previas); hora del cambio de contacto y minutos antes de la transferencia | Toma de cuenta vs. APP |
| `check_beneficiary` | Antigüedad de cuenta y de llave en días, remitentes distintos en 24 h, entradas y salidas en 24 h (con la transferencia de la alerta) y pass-through = salidas / entradas | APP / mula |
| `get_inbound_senders` | Remitentes del beneficiario en 24 h con su monto, y cuáles tienen otra alerta (sin contar la actual) | Red de mulas (segundo salto) |
| `create_case_draft` | `case_id` y estado; escribe en `case_drafts`. Recibe `alert_id`, hipótesis, riesgo, recomendación y evidencia | Única escritura, con confirmación (Fase 3) |

**Valores esperados** (calculados sobre el SQLite generado, con "ahora" = `created_ts` de cada alerta)

| Señal | AL-1001 | AL-1002 | AL-1003 |
| --- | --- | --- | --- |
| Cliente → beneficiario | C001 → X-RENT | C002 → M001 | C003 → B001 |
| `created_ts` | 2026-11-02 11:01:00 | 2026-11-02 12:01:00 | 2026-11-02 13:16:00 |
| Monto (COP) | 2.400.000 | 4.500.000 | 6.000.000 |
| Score · razones | 0,64 · AMOUNT\_ABOVE\_PROFILE | 0,91 · NEW\_BENEFICIARY, AMOUNT\_ABOVE\_PROFILE | 0,88 · NEW\_BENEFICIARY, AMOUNT\_ABOVE\_PROFILE |
| Transferencias 90 d · mediana (COP) | 26 · 139.000 | 30 · 141.500 | 30 · 94.000 |
| Monto vs. mediana | 17,3x | 31,8x | 63,8x |
| Pagos previos al beneficiario | 4 de 1.800.000 → 1,33x | 0 | 0 |
| Dispositivo de la transferencia | Habitual (1 dispositivo) | Habitual (1 dispositivo) | Nuevo: D-C003-NEW, primera sesión 13:10 |
| Cambio de contacto | No | No | 12:50, 25 min antes de la transferencia (13:15) |
| Antigüedad cuenta · llave del beneficiario | 900 d · 700 d | 3 d · 3 d | 400 d · 380 d |
| Remitentes distintos en 24 h | 1 | 15 | 3 |
| Entradas · salidas 24 h (COP) | 2.400.000 · 0 | 13.444.000 · 8.100.000 (60 %) | 6.370.000 · 0 |
| Remitentes con otra alerta | 0 | 5 | 0 |
| Veredicto esperado | Falso positivo: cerrar | Mula por ingeniería social: escalar y sugerir bloqueo de llave | Toma de cuenta: escalar y contactar al cliente |

Dos cosas de esta tabla importan para el pitch:

1. **El monto no discrimina.** Las tres alertas superan 17 veces la mediana, y la hora cae siempre dentro del rango habitual (8 a 21 h). AL-1001 se cierra por los 4 pagos previos a ese beneficiario. Por eso `analyze_behavior` debe devolver el historial con el beneficiario y no solo la mediana general.
2. **El pass-through de M001 es 60 %, no 80 %.** El generador imprime 80 % porque mide todo el periodo e incluye una salida posterior a la alerta. Con "ahora" = `created_ts`, lo correcto es 60 %.

Prompt 1 para Claude Code (SQLite):

> Implementa investigador\_alertas/data\_backend.py (consultas parametrizadas sobre SQLite según DATA\_BACKEND) e investigador\_alertas/tools.py con las 6 herramientas de los contratos de la Fase 2 de HANDBOOK.md. create\_case\_draft escribe en case\_drafts. Escribe tests/test\_tools.py con todos los valores de la tabla "Valores esperados" (tolerancia 0,05 en los ratios). Corre pytest y muéstrame el resultado. Si un valor no coincide, explica por qué antes de tocar la tabla: la tabla manda.

Prompt 2 para Claude Code (BigQuery, después de G1):

> Añade a data\_backend.py la implementación BigQuery (google-cloud-bigquery, consultas parametrizadas sobre fraud\_synth, columnas DATETIME). Para create\_case\_draft usa INSERT con DML. Parametriza tests/test\_tools.py para correr con ambos backends y ejecútalo con DATA\_BACKEND=bigquery.

**Validaciones**

| # | Qué validar | Resultado esperado |
| --- | --- | --- |
| 2.1 | `pytest` con SQLite (compuerta G1) | Todo en verde |
| 2.2 | `pytest` con BigQuery (compuerta G2) | Mismos valores que SQLite |
| 2.3 | Alerta inexistente (`AL-9999`) | `status: error` con mensaje claro, sin excepción |
| 2.4 | `create_case_draft` con SQLite | Una fila nueva en `case_drafts`; bórrala después de la prueba |
| 2.5 | Ningún valor depende del reloj real | Los tests pasan igual sin importar el día en que los corras |

## Fase 3 — El agente en ADK

El agente es un solo `Agent` con las 6 herramientas. Esta fase cierra cuando resuelve las 3 alertas con el veredicto correcto en 3 de 3 corridas y nunca escribe un caso sin confirmación. Calcula 3 a 4 horas.

**Configuración**

- `name="investigador_alertas"` (identificador Python válido) y variable `root_agent`. Importa desde `google.adk.agents`.
- Modelo desde `MODEL` del `.env`. Temperatura baja (0 a 0,2) para que el veredicto sea estable.
- Si aparecen errores 429, usa `Gemini(model=..., retry_options=...)`, como en los labs.
- La aprobación humana es `FunctionTool(create_case_draft, require_confirmation=True)`. Verifiqué en google-adk 2.13.0 que el parámetro existe y que la interfaz de `adk web` incluye la solicitud de confirmación (`adk_request_confirmation`). El flujo completo no lo probé porque requiere llamar al modelo.

**Instrucción** (estructura de 5 partes del path de ADK; ajústala, pero no le quites los límites):

```
IDENTIDAD: Eres un analista de fraude que investiga alertas de transferencias
inmediatas. Trabajas después del motor de reglas; no apruebas ni bloqueas pagos.

MISIÓN: Determinar la tipología más probable de la alerta (toma de cuenta,
ingeniería social hacia una mula, mula receptora o falso positivo) con evidencia
trazable.

MÉTODO:
1. Llama get_alert y plantea las hipótesis posibles.
2. Elige la siguiente herramienta según la hipótesis que más cambie tu
   conclusión. No llames herramientas que no la cambien.
3. Si el beneficiario parece una mula, revisa a sus otros remitentes.
4. Detente cuando la evidencia sea suficiente.

LÍMITES:
- Usa solo cifras que devolvieron las herramientas. No inventes datos.
- Para un falso positivo, recomienda cerrar y no crees caso.
- Si recomiendas escalar, presenta primero el dictamen y luego llama
  create_case_draft; el analista debe aprobarlo.

FORMATO DEL DICTAMEN:
Tipología · Riesgo (bajo/medio/alto) · Evidencia (viñetas: dato + herramienta)
· Hipótesis descartadas y por qué · Recomendación.
```

No agregues `if/else` en el código para enrutar por tipología. Si lo haces, el sistema pasa a ser un workflow y se cae el argumento del pitch. Si el camino no sale bien, ajusta la instrucción o los docstrings.

Prompt 1 para Claude Code (agente):

> Crea investigador\_alertas/agent.py y **init**.py siguiendo la Fase 3 de HANDBOOK.md: un solo Agent con las 6 herramientas, create\_case\_draft envuelta en FunctionTool(require\_confirmation=True) y la instrucción del handbook. Verifica que el módulo importa y que root\_agent lista las 6 herramientas, sin llamar al modelo. Luego dime cómo probarlo en adk web.

Prompt 2 para Claude Code (corrida de validación):

> Escribe scripts/run\_demo.py: con Runner e InMemorySessionService, corre AL-1001, AL-1002 y AL-1003 tres veces cada una ("Investiga la alerta AL-XXXX"). Por corrida registra la secuencia de herramientas llamadas, si se pidió confirmación y el texto final. No apruebes la confirmación. Imprime una tabla resumen y compárala con las validaciones 3.2 a 3.6.

Para probarlo a mano: desde la raíz del repo corre `adk web .`, elige `investigador_alertas` y escribe "Investiga la alerta AL-1002". En la pestaña de eventos revisas qué herramientas llamó y qué devolvieron.

**Validaciones (compuerta G3)**

| # | Qué validar | Resultado esperado |
| --- | --- | --- |
| 3.1 | `adk web .` | Lista `investigador_alertas` y responde |
| 3.2 | AL-1001 | Falso positivo; menciona los 4 pagos previos y el 1,33x; no llama `get_inbound_senders` ni `create_case_draft` |
| 3.3 | AL-1002 | Mula por ingeniería social; cita 15 remitentes, 5 con alerta y 60 % de pass-through; pide confirmación antes de crear el caso |
| 3.4 | AL-1003 | Toma de cuenta; cita el dispositivo nuevo y el cambio de contacto 25 min antes; descarta mula (3 remitentes, cuenta de 400 d) |
| 3.5 | Confirmación | Si la rechazas, no hay fila nueva en `case_drafts`; si la apruebas, hay exactamente una |
| 3.6 | Estabilidad | Mismo veredicto en 3 de 3 corridas por alerta |
| 3.7 | Sin cifras inventadas | Cada número del dictamen aparece en alguna respuesta de herramienta |

Si la confirmación no aparece en `adk web`, el plan B es exigir en código un parámetro `analyst_approval` que el agente debe pedirle al analista: sin él, la herramienta devuelve `error` y no escribe. Lo importante es que el control viva en el código y no solo en la instrucción.

## Fase 4 — Demo, video de respaldo y despliegue opcional

La demo del pitch es un video de 30 segundos, no una ejecución en vivo: el modelo puede tardar o fallar justo en tus 3 minutos. Si el video está listo, la demo en vivo pasa a ser un extra. Calcula 1 a 2 horas, más 2 si haces el despliegue.

**Qué grabar**

1. AL-1002 completa en `adk web`: la pregunta, las herramientas que va llamando, el dictamen, la solicitud de confirmación y el caso creado. Es la alerta que mejor muestra adaptación y aprobación humana.
2. AL-1001 en 5 segundos: el agente la cierra con 2 herramientas. Muestra que la mayoría de las alertas son ruido.
3. Capturas de la vista de eventos de AL-1002 y AL-1003 lado a lado para la diapositiva 2: dos alertas con caminos distintos.

Graba cada alerta completa (en Mac, `Cmd+Shift+5`) y luego recorta y acelera las esperas del modelo hasta 30 segundos. Agranda la letra del navegador para que se lea en pantalla compartida y cuida que no se vean tu correo ni la consola de facturación.

**Despliegue en Agent Runtime (opcional, compuerta G4)**

Hazlo solo si G3 pasó antes del domingo al mediodía, con un tope de 2 horas. Si no sale, el pitch no pierde nada: la arquitectura sigue siendo Gemini en Vertex AI con datos en BigQuery.

Prompt para Claude Code:

> Quiero desplegar investigador\_alertas en Agent Runtime con DATA\_BACKEND=bigquery. Primero revisa adk deploy agent\_engine --help en la versión instalada y dime qué parámetros necesito. Verifica antes cuenta y proyecto activos. Después del despliegue, identifica con qué cuenta de servicio corre el agente y dime qué roles de BigQuery le faltan para leer fraud\_synth e insertar en case\_drafts. No me des los roles a mí: van en esa cuenta de servicio.

En el Challenge Lab de Paint Agent el error fue justamente asignar los roles a tu propia cuenta en lugar de la cuenta de servicio. Después del pitch, borra el despliegue.

**Validaciones**

| # | Qué validar | Resultado esperado |
| --- | --- | --- |
| 4.1 | Video | 30 s o menos; se leen las herramientas, el dictamen y la confirmación |
| 4.2 | Respaldo del video | Una copia local y otra en Drive, y la diapositiva 4 enlaza la de Drive |
| 4.3 | Capturas de caminos | AL-1002 y AL-1003 muestran secuencias de herramientas distintas |
| 4.4 | Versión congelada | `git init`, commit y tag `pitch-v1` cuando G3 pase |
| 4.5 | Agent Runtime (opcional) | AL-1002 remoto da el mismo veredicto que en local |

## Fase 5 — Pitch

La rúbrica califica tres cosas: el problema, el criterio agéntico y el manejo del tiempo, no el código. El guion se escribe sobre la plantilla oficial de Google Slides, en 4 diapositivas, con una meta de 2:50 en el ensayo. Calcula 3 a 4 horas entre guion, diapositivas y ensayos.

**Guion (borrador para ajustar a tu voz)**

| Bloque | Tiempo | Diapositiva | Qué decir |
| --- | --- | --- | --- |
| 1. Problema | 45 s | Dos cifras y quién sufre el dolor | "Detrás de cada alerta de fraude hay un analista revisando perfil, dispositivos y a quién se le envió el dinero. Según Google Cloud, en monitoreo de lavado más del 95 % de las alertas son falsos positivos en la primera revisión. Y en Colombia hay menos margen: con Bre-B una transferencia se completa en máximo 20 segundos, y ya supera los 36 millones de usuarios." |
| 2. ¿Por qué un agente? | 45 s | Árbol de decisión + capturas de AL-1002 y AL-1003 | "El motor de reglas ya genera la alerta; eso es un if/else. Lo difícil viene después: cada alerta puede ser toma de cuenta, ingeniería social, mula o ruido, y cada hipótesis pide evidencia distinta. Un workflow consultaría todo, siempre a la misma profundidad. El agente decide qué mirar según lo que encuentra: estas dos alertas tomaron caminos distintos." |
| 3. Anatomía | 60 s | Modelo + Herramientas + Orquestación | Modelo: Gemini en Vertex AI. Herramientas: 6 consultas sobre BigQuery que calculan las cifras, para que el modelo razone pero no invente. Orquestación: ADK con bucle ReAct, que investiga solo pero necesita la aprobación del analista para su única acción, crear el caso. |
| 4. Demo y próximos pasos | 30 s | Video de 30 s | Video de AL-1002 (y AL-1001 cerrándose). Próximos pasos: servidor MCP de solo lectura, RAG sobre tipologías y evaluación con alertas etiquetadas. |

En el bloque 1 habla de "un banco" o "la industria", nunca de Bancolombia, y no muestres logos ni datos internos.

**Preguntas probables del jurado**

| Pregunta | Respuesta corta |
| --- | --- |
| ¿Por qué no basta un workflow? | Las consultas básicas sí caben en un workflow. El agente aporta dos cosas: interpreta combinaciones (dispositivo habitual + beneficiario nuevo apunta a ingeniería social, no a toma de cuenta) y decide cuándo profundizar (los otros remitentes, solo si parece mula). |
| ¿Y si el modelo alucina? | Las cifras las calculan las herramientas con SQL fijo, el dictamen cita de qué herramienta sale cada dato y la única escritura requiere aprobación humana en código. |
| ¿Por qué no decide en tiempo real? | Bre-B liquida en máximo 20 s y un bucle de razonamiento no cabe ahí. El agente trabaja después del motor: investiga, no autoriza pagos. |
| ¿Es un proyecto de tu banco? | No. Es un proyecto personal con datos 100 % sintéticos. |
| ¿Cómo lo medirías? | Con un set de alertas etiquetadas: acierto de tipología, herramientas por alerta, tiempo por alerta y falsos positivos cerrados correctamente. |
| ¿Cuánto cuesta o tarda? | Responde solo con lo que midas en `run_demo.py` (latencia y herramientas por alerta). Si no lo mediste, dilo y explica que el falso positivo se cierra con 2 consultas. |

**Validaciones (compuerta G5)**

| # | Qué validar | Resultado esperado |
| --- | --- | --- |
| 5.1 | Cifras de la diapositiva 1 | Abriste las dos fuentes (sección Fuentes) y el texto coincide |
| 5.2 | Diapositivas | 4 como máximo, en la plantilla oficial, sin marcas ni datos de Bancolombia |
| 5.3 | Tiempo | Tres ensayos seguidos en 2:50 o menos, con cronómetro |
| 5.4 | Preguntas | Puedes responder cada pregunta de la tabla en unos 20 s |
| 5.5 | Aval | Ya hablaste con tu líder |

## Puntos de inflexión

Cada compuerta tiene una hora límite. Si llegas a esa hora sin cumplir el criterio, aplica la columna "Si no pasa" en lugar de seguir insistiendo: el pitch se gana con un guion claro y ensayado, no con la arquitectura más completa.

| Compuerta | Límite | Criterio | Si pasa | Si no pasa |
| --- | --- | --- | --- | --- |
| G0 · GCP listo | 1 h después de empezar la Fase 0 | Validaciones 0.1 a 0.4 | Fase 1 | Usa Gemini con una clave de AI Studio (`GOOGLE_GENAI_USE_VERTEXAI=FALSE` y `GOOGLE_API_KEY`) y datos en SQLite. Vertex AI y BigQuery pasan a próximos pasos |
| G1 · Herramientas en SQLite | Sáb 31, 12:00 m | 2.1 en verde | Fase 3, y BigQuery en paralelo | No toques el agente hasta que pase. Si falta tiempo, fusiona `analyze_behavior` dentro de `get_alert` |
| G2 · BigQuery igual a SQLite | Sáb 31, 3:00 pm | 2.2 en verde | La demo usa BigQuery | La demo usa SQLite y el pitch presenta BigQuery como siguiente paso. No le dediques más de 1 h |
| G3 · Agente validado | Sáb 31, 10:00 pm | 3.2 a 3.6 | Graba el video y crea el tag `pitch-v1` | Con 2 de 3 alertas, la demo usa las que funcionan (AL-1002 es obligatoria). Con 0 o 1, Plan B: diagrama del flujo ReAct, contratos de herramientas y capturas, que es el nivel Intermedio de la rúbrica |
| G4 · Agent Runtime | Dom 1, 12:00 m | G3 pasó y tienes 2 h libres | Despliega (Fase 4) | Omítelo; no resta en la rúbrica |
| G5 · Congelado | Lun 2, 10:00 pm | 5.1 a 5.5 | El martes solo ensayas | Si el tiempo no baja de 2:50, recorta frases, no las cifras ni la demo |

**Orden de recorte** si el tiempo aprieta (lo primero que se sacrifica va arriba):

1. Agent Runtime.
2. BigQuery (la demo queda sobre SQLite).
3. `analyze_behavior` como herramienta aparte.
4. AL-1001 y AL-1003 en el video.

El guion y los ensayos nunca se recortan.

## Riesgos conocidos

Casi todos estos problemas ya aparecieron en los labs o en la configuración de tu cuenta. Revisa esta tabla antes de pedirle a Claude Code que depure un error.

| Riesgo | Síntoma | Cómo evitarlo | Dónde apareció |
| --- | --- | --- | --- |
| Plantillas de estado con valor por defecto | `{clave?valor}` llega literal al prompt | Usa solo `{clave}` o `{clave?}`, o ninguna plantilla | Path de ADK (verificado en 2.12.0) |
| Orden de pasos no impuesto | El modelo se salta "primero verifica, luego actúa" | Los controles van en código (`require_confirmation`), no solo en la instrucción | Path de ADK |
| Herramientas built-in mezcladas con otras | Error 400 al llamar al modelo | No uses built-in; si hiciera falta, envuélvela en un `AgentTool` | Challenge Lab de Paint Agent |
| Nombre o punto de entrada inválido | `ValidationError`, o `adk web` no encuentra el agente | `name` sin guiones ni espacios, variable `root_agent`, `__init__.py` con `from . import agent` | Path de ADK |
| Roles en la cuenta equivocada | El agente desplegado no puede leer BigQuery | Los roles van en la cuenta de servicio del agente, no en la tuya | Challenge Lab de Paint Agent |
| `gcloud` con la cuenta de la UdeA | Facturación bloqueada | `gcloud auth list` antes de cada sesión | Configuración de tu cuenta GCP |
| Diferencia de versiones de ADK | Un parámetro del lab no existe o cambió | Los labs usaban 1.30.0 y local tendrás 2.x: anota la versión y revisa `--help` antes de copiar comandos | Path de despliegue |
| Cuota del modelo | Errores 429 durante la grabación | `retry_options` y grabar con tiempo, no el lunes en la noche | Labs de despliegue |
| Modelo no disponible en la región | Error 404 | Usa `GOOGLE_CLOUD_LOCATION=global` y revisa el nombre exacto en Model Garden | `scripts/check_vertex.py` |
| Datos regenerados | Los tests dejan de coincidir | El generador usa semilla fija (7). No lo modifiques después de G1 sin recalcular la tabla | — |

## Fuentes

Las cifras de la diapositiva 1 salen de la investigación de fraude e IA en banca (oct. 2026). No abrí estas páginas al escribir el handbook, así que ábrelas antes de usarlas (validación 5.1).

- [Google Cloud Launches AI-Powered Anti Money Laundering Product for Financial Institutions](https://www.googlecloudpresscorner.com/2023-06-21-Google-Cloud-Launches-AI-Powered-Anti-Money-Laundering-Product-for-Financial-Institutions) (21 jun. 2023): más del 95 % de las alertas son falsos positivos en la primera revisión.
- [Conozca Bre-B — Banco de la República](https://www.banrep.gov.co/es/bre-b/que-es): según la investigación, más de 36 millones de usuarios al 6 oct. 2026. El límite de 20 segundos sale del documento técnico de Bre-B del Banco de la República (feb. 2026), que la investigación cita.

Los valores esperados de la Fase 2 se calcularon sobre el SQLite que produce `generar_datos_sinteticos.py` (semilla 7). Lo de `require_confirmation` se verificó instalando google-adk 2.13.0.
