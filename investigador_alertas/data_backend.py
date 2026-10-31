"""Acceso a datos con consultas parametrizadas (@nombre). Backend según DATA_BACKEND.

Las herramientas escriben SQL fijo y solo pasan parámetros; el LLM nunca escribe SQL.
Fechas: se pasan como datetime y se devuelven tal como las entrega cada backend
(texto en SQLite, datetime/date en BigQuery); tools.py las normaliza.
"""
import os
import sqlite3
from datetime import datetime
from pathlib import Path

from dotenv import load_dotenv

_ROOT = Path(__file__).resolve().parent.parent
load_dotenv(_ROOT / "investigador_alertas" / ".env")

_DEFAULT_SQLITE = _ROOT / "datos_sinteticos" / "fraude_sintetico.db"


def _backend() -> str:
    return os.environ.get("DATA_BACKEND", "sqlite").lower()


def _sqlite_params(params: dict) -> dict:
    return {k: v.strftime("%Y-%m-%d %H:%M:%S") if isinstance(v, datetime) else v
            for k, v in params.items()}


def _sqlite(sql: str, params: dict, write: bool) -> list[dict]:
    path = os.environ.get("SQLITE_PATH", str(_DEFAULT_SQLITE))
    con = sqlite3.connect(path)
    con.row_factory = sqlite3.Row
    try:
        rows = con.execute(sql, _sqlite_params(params)).fetchall()
        if write:
            con.commit()
        return [dict(r) for r in rows]
    finally:
        con.close()


_bq_client = None


def _bq_type(v) -> str:
    if isinstance(v, datetime):
        return "DATETIME"
    if isinstance(v, bool):
        return "BOOL"
    if isinstance(v, int):
        return "INT64"
    if isinstance(v, float):
        return "FLOAT64"
    return "STRING"


def _bigquery(sql: str, params: dict) -> list[dict]:
    """Consulta parametrizada sobre el dataset BQ_DATASET (tablas sin prefijo)."""
    global _bq_client
    from google.cloud import bigquery

    project = os.environ["GOOGLE_CLOUD_PROJECT"]
    dataset = os.environ.get("BQ_DATASET", "fraud_synth")
    if _bq_client is None:
        _bq_client = bigquery.Client(project=project, location=os.environ.get("BQ_LOCATION", "US"))
    config = bigquery.QueryJobConfig(
        default_dataset=f"{project}.{dataset}",
        query_parameters=[bigquery.ScalarQueryParameter(k, _bq_type(v), v)
                          for k, v in params.items()],
    )
    return [dict(r.items()) for r in _bq_client.query(sql, job_config=config).result()]


def query(sql: str, params: dict | None = None) -> list[dict]:
    """Ejecuta un SELECT parametrizado y devuelve una lista de dicts."""
    if _backend() == "sqlite":
        return _sqlite(sql, params or {}, write=False)
    if _backend() == "bigquery":
        return _bigquery(sql, params or {})
    raise ValueError(f"DATA_BACKEND desconocido: {_backend()!r}")


def execute(sql: str, params: dict | None = None) -> None:
    """Ejecuta un INSERT/DELETE parametrizado (DML; INSERT lo usa create_case_draft)."""
    if _backend() == "sqlite":
        _sqlite(sql, params or {}, write=True)
        return
    if _backend() == "bigquery":
        _bigquery(sql, params or {})  # DML: el job termina en result()
        return
    raise ValueError(f"DATA_BACKEND desconocido: {_backend()!r}")
