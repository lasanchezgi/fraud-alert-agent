#!/usr/bin/env bash
# Fase 1: carga las 6 tablas sintéticas a BigQuery (dataset fraud_synth, ubicación US).
set -e

cd "$(dirname "$0")/.."

# Cuenta de gcloud con la que se trabaja este proyecto (puede sobrescribirse con EXPECTED_ACCOUNT=...).
EXPECTED_ACCOUNT="${EXPECTED_ACCOUNT:-ludwiglawers@gmail.com}"

set -a
source investigador_alertas/.env
set +a
PROJECT_ID="$GOOGLE_CLOUD_PROJECT"
DATASET="${BQ_DATASET:-fraud_synth}"

# --- Verificaciones previas ---
ACTIVE_ACCOUNT="$(gcloud auth list --filter=status:ACTIVE --format='value(account)')"
if [ "$ACTIVE_ACCOUNT" != "$EXPECTED_ACCOUNT" ]; then
  echo "ERROR: cuenta activa de gcloud = '$ACTIVE_ACCOUNT', se esperaba '$EXPECTED_ACCOUNT'" >&2
  exit 1
fi

ACTIVE_PROJECT="$(gcloud config get-value project 2>/dev/null)"
if [ "$ACTIVE_PROJECT" != "$PROJECT_ID" ]; then
  echo "ERROR: proyecto activo de gcloud = '$ACTIVE_PROJECT', .env tiene '$PROJECT_ID'" >&2
  exit 1
fi
echo "OK: cuenta $ACTIVE_ACCOUNT, proyecto $PROJECT_ID"

# --- Datos ---
.venv/bin/python generar_datos_sinteticos.py | grep -q "Autoverificación OK"
echo "OK: Autoverificación OK"

# --- Dataset (idempotente) ---
if bq --project_id="$PROJECT_ID" show --dataset "$PROJECT_ID:$DATASET" >/dev/null 2>&1; then
  echo "Dataset $DATASET ya existe, se reutiliza"
else
  bq --location=US mk --dataset "$PROJECT_ID:$DATASET"
fi

# --- Tablas ---
L="bq --project_id=$PROJECT_ID load --replace --source_format=CSV --skip_leading_rows=1"
$L $DATASET.customers    datos_sinteticos/customers.csv    customer_id:STRING,segment:STRING,city:STRING,signup_date:DATE
$L $DATASET.accounts     datos_sinteticos/accounts.csv     account_id:STRING,customer_id:STRING,opened_date:DATE,key_created_date:DATE
$L $DATASET.transactions datos_sinteticos/transactions.csv tx_id:STRING,ts:DATETIME,from_account:STRING,to_account:STRING,amount_cop:INT64,channel:STRING,status:STRING
$L $DATASET.sessions     datos_sinteticos/sessions.csv     session_id:STRING,customer_id:STRING,ts:DATETIME,device_id:STRING,ip_country:STRING,contact_change_ts:DATETIME
$L $DATASET.alerts       datos_sinteticos/alerts.csv       alert_id:STRING,tx_id:STRING,customer_id:STRING,created_ts:DATETIME,engine_score:FLOAT64,reason_codes:STRING,status:STRING

# case_drafts se crea vacía (su CSV solo trae el encabezado); se omite si ya existe.
if bq --project_id="$PROJECT_ID" show "$PROJECT_ID:$DATASET.case_drafts" >/dev/null 2>&1; then
  echo "Tabla case_drafts ya existe, se reutiliza"
else
  bq --project_id="$PROJECT_ID" mk -t "$DATASET.case_drafts" case_id:STRING,alert_id:STRING,created_ts:DATETIME,hypothesis:STRING,risk:STRING,recommendation:STRING,evidence_json:STRING,approved_by:STRING
fi

echo "Carga completa"
