"""Las 6 herramientas del investigador de alertas.

Reglas comunes: reciben alert_id (salvo create_case_draft), "ahora" = created_ts de la
alerta (nunca el reloj del sistema) y devuelven un dict con status "ok" o "error".
"""
import json
import statistics
from datetime import date, datetime, timedelta
from typing import Literal, get_args

from . import data_backend as db

Typology = Literal["toma_de_cuenta", "ingenieria_social_mula", "mula_receptora", "falso_positivo"]
Risk = Literal["bajo", "medio", "alto"]
TYPOLOGIES = get_args(Typology)
RISKS = get_args(Risk)

BEHAVIOR_WINDOW_DAYS = 90
BENEFICIARY_WINDOW_HOURS = 24
_FMT = "%Y-%m-%d %H:%M:%S"


# --- Utilidades ---------------------------------------------------------------

def _dt(v) -> datetime | None:
    """Normaliza texto de SQLite o datetime de BigQuery; '' y NULL -> None."""
    if v is None or v == "":
        return None
    if isinstance(v, datetime):
        return v
    return datetime.strptime(v, _FMT)


def _d(v) -> date | None:
    """Normaliza fechas (texto o date); '' y NULL -> None."""
    if v is None or v == "":
        return None
    if isinstance(v, datetime):
        return v.date()
    if isinstance(v, date):
        return v
    return date.fromisoformat(v)


def _s(v: datetime | None) -> str | None:
    return v.strftime(_FMT) if v else None


def _ratio(num, den) -> float | None:
    return round(num / den, 2) if den else None


def _error(message: str) -> dict:
    return {"status": "error", "message": message}


def _load_alert(alert_id: str) -> dict | None:
    """Alerta + su transferencia, con fechas normalizadas. None si no existe."""
    rows = db.query(
        """SELECT a.alert_id, a.customer_id, a.created_ts, a.engine_score, a.reason_codes,
                  t.tx_id, t.ts AS tx_ts, t.from_account, t.to_account, t.amount_cop
           FROM alerts a JOIN transactions t ON t.tx_id = a.tx_id
           WHERE a.alert_id = @alert_id""",
        {"alert_id": alert_id},
    )
    if not rows:
        return None
    r = rows[0]
    r["created_ts"] = _dt(r["created_ts"])
    r["tx_ts"] = _dt(r["tx_ts"])
    return r


def _not_found(alert_id: str) -> dict:
    return _error(f"Alerta '{alert_id}' no encontrada.")


# --- Herramientas -------------------------------------------------------------

def get_alert(alert_id: str) -> dict:
    """Punto de partida de toda investigación: devuelve los datos básicos de la alerta.

    Úsala primero. Entrega cliente, transferencia (cuenta origen, beneficiario, monto),
    score del motor, códigos de razón y created_ts, que es el "ahora" de las demás
    herramientas. No confirma ni descarta ninguna hipótesis por sí sola.

    Args:
        alert_id: Identificador de la alerta, por ejemplo "AL-1001".
    """
    a = _load_alert(alert_id)
    if a is None:
        return _not_found(alert_id)
    return {
        "status": "ok",
        "alert_id": a["alert_id"],
        "customer_id": a["customer_id"],
        "tx_id": a["tx_id"],
        "tx_ts": _s(a["tx_ts"]),
        "from_account": a["from_account"],
        "to_account": a["to_account"],
        "amount_cop": a["amount_cop"],
        "engine_score": a["engine_score"],
        "reason_codes": a["reason_codes"].split("|") if a["reason_codes"] else [],
        "created_ts": _s(a["created_ts"]),
    }


def analyze_behavior(alert_id: str) -> dict:
    """Compara la transferencia con el comportamiento del cliente en los últimos 90 días.

    Ayuda a distinguir falso positivo de anomalía: el monto solo no discrimina (puede ser
    alto frente a la mediana general y aun así normal), por eso también devuelve el
    historial de pagos previos al mismo beneficiario. Muchos pagos previos de monto
    similar apoyan "falso positivo"; cero pagos previos apoya "beneficiario nuevo".
    También compara la hora con el rango horario habitual del cliente.

    Args:
        alert_id: Identificador de la alerta, por ejemplo "AL-1001".
    """
    a = _load_alert(alert_id)
    if a is None:
        return _not_found(alert_id)
    start = a["created_ts"] - timedelta(days=BEHAVIOR_WINDOW_DAYS)
    rows = db.query(
        """SELECT t.ts, t.to_account, t.amount_cop
           FROM transactions t JOIN accounts ac ON ac.account_id = t.from_account
           WHERE ac.customer_id = @customer_id
             AND t.ts >= @start AND t.ts <= @now AND t.tx_id <> @tx_id""",
        {"customer_id": a["customer_id"], "start": start, "now": a["created_ts"],
         "tx_id": a["tx_id"]},
    )
    amounts = [r["amount_cop"] for r in rows]
    # Pagos previos al beneficiario: todo el historial hasta "ahora", no solo los 90 días.
    prior = [r["amount_cop"] for r in db.query(
        """SELECT t.amount_cop FROM transactions t JOIN accounts ac ON ac.account_id = t.from_account
           WHERE ac.customer_id = @customer_id AND t.to_account = @to_account
             AND t.ts <= @now AND t.tx_id <> @tx_id""",
        {"customer_id": a["customer_id"], "to_account": a["to_account"],
         "now": a["created_ts"], "tx_id": a["tx_id"]},
    )]
    hours = [_dt(r["ts"]).hour for r in rows]
    median_all = statistics.median(amounts) if amounts else None
    median_prior = statistics.median(prior) if prior else None
    tx_hour = a["tx_ts"].hour
    usual = (min(hours), max(hours)) if hours else (None, None)
    return {
        "status": "ok",
        "amount_cop": a["amount_cop"],
        "transfers_90d_count": len(amounts),
        "median_amount_90d_cop": median_all,
        "amount_vs_median_ratio": _ratio(a["amount_cop"], median_all),
        "prior_payments_to_beneficiary_count": len(prior),
        "prior_payments_median_cop": median_prior,
        "amount_vs_prior_payments_ratio": _ratio(a["amount_cop"], median_prior),
        "transfer_hour": tx_hour,
        "usual_hour_min": usual[0],
        "usual_hour_max": usual[1],
        "within_usual_hours": usual[0] is not None and usual[0] <= tx_hour <= usual[1],
    }


def get_session_devices(alert_id: str) -> dict:
    """Revisa los dispositivos del cliente y si hubo un cambio de contacto reciente.

    Ayuda a distinguir toma de cuenta de otros casos: un dispositivo que aparece por
    primera vez en las 24 h previas, sumado a un cambio de contacto (teléfono o correo)
    pocos minutos antes de la transferencia, apoya "toma de cuenta". Dispositivo habitual
    y sin cambio de contacto la descartan.

    Args:
        alert_id: Identificador de la alerta, por ejemplo "AL-1001".
    """
    a = _load_alert(alert_id)
    if a is None:
        return _not_found(alert_id)
    sessions = db.query(
        """SELECT ts, device_id, contact_change_ts FROM sessions
           WHERE customer_id = @customer_id AND ts <= @now ORDER BY ts""",
        {"customer_id": a["customer_id"], "now": a["created_ts"]},
    )
    devices: dict[str, dict] = {}
    for s in sessions:
        ts = _dt(s["ts"])
        d = devices.setdefault(s["device_id"], {"device_id": s["device_id"], "sessions_count": 0,
                                                "first_seen": ts, "last_seen": ts})
        d["sessions_count"] += 1
        d["first_seen"] = min(d["first_seen"], ts)
        d["last_seen"] = max(d["last_seen"], ts)

    # Dispositivo de la transferencia = sesión más reciente hasta el instante de la transferencia.
    before_tx = [s for s in sessions if _dt(s["ts"]) <= a["tx_ts"]]
    tx_device = before_tx[-1]["device_id"] if before_tx else None
    is_new = (tx_device is not None and
              devices[tx_device]["first_seen"] >= a["created_ts"] - timedelta(hours=BENEFICIARY_WINDOW_HOURS))

    changes = [_dt(s["contact_change_ts"]) for s in sessions if _dt(s["contact_change_ts"])]
    change = max(changes) if changes else None
    return {
        "status": "ok",
        "devices": [{**d, "first_seen": _s(d["first_seen"]), "last_seen": _s(d["last_seen"])}
                    for d in devices.values()],
        "transfer_device_id": tx_device,
        "transfer_device_is_new": is_new,
        "contact_change_ts": _s(change),
        "contact_change_minutes_before_transfer":
            round((a["tx_ts"] - change).total_seconds() / 60) if change else None,
    }


def _window_flows(account: str, start: datetime, now: datetime) -> tuple[list[dict], list[dict]]:
    inbound = db.query(
        """SELECT tx_id, from_account, amount_cop FROM transactions
           WHERE to_account = @account AND ts >= @start AND ts <= @now""",
        {"account": account, "start": start, "now": now},
    )
    outbound = db.query(
        """SELECT tx_id, amount_cop FROM transactions
           WHERE from_account = @account AND ts >= @start AND ts <= @now""",
        {"account": account, "start": start, "now": now},
    )
    return inbound, outbound


def check_beneficiary(alert_id: str) -> dict:
    """Evalúa la cuenta beneficiaria: antigüedad y flujo de dinero en las últimas 24 h.

    Ayuda a distinguir APP / mula de otros casos: cuenta y llave recién creadas, muchos
    remitentes distintos y un pass-through alto (salidas / entradas, el dinero entra y sale
    rápido) apoyan "mula". Una cuenta antigua con pocos remitentes y sin salidas la descarta.

    Args:
        alert_id: Identificador de la alerta, por ejemplo "AL-1001".
    """
    a = _load_alert(alert_id)
    if a is None:
        return _not_found(alert_id)
    acc = db.query(
        "SELECT opened_date, key_created_date FROM accounts WHERE account_id = @account",
        {"account": a["to_account"]},
    )
    opened = _d(acc[0]["opened_date"]) if acc else None
    key_created = _d(acc[0]["key_created_date"]) if acc else None
    today = a["created_ts"].date()
    start = a["created_ts"] - timedelta(hours=BENEFICIARY_WINDOW_HOURS)
    inbound, outbound = _window_flows(a["to_account"], start, a["created_ts"])
    in_cop = sum(r["amount_cop"] for r in inbound)
    out_cop = sum(r["amount_cop"] for r in outbound)
    return {
        "status": "ok",
        "beneficiary_account": a["to_account"],
        "account_age_days": (today - opened).days if opened else None,
        "key_age_days": (today - key_created).days if key_created else None,
        "distinct_senders_24h": len({r["from_account"] for r in inbound}),
        "inbound_24h_cop": in_cop,
        "outbound_24h_cop": out_cop,
        "pass_through_ratio": _ratio(out_cop, in_cop),
    }


def get_inbound_senders(alert_id: str) -> dict:
    """Lista quién envió dinero al beneficiario en las últimas 24 h y si esos remitentes
    tienen otras alertas.

    Ayuda a confirmar o descartar una red de mulas (segundo salto): varios remitentes del
    mismo beneficiario con alertas propias apoyan un esquema coordinado; ninguno con otra
    alerta apoya un caso aislado. No cuenta la alerta que se está investigando.

    Úsala solo si check_beneficiary sugiere que el beneficiario es una mula (cuenta
    nueva, muchos remitentes distintos o pass-through alto).

    Args:
        alert_id: Identificador de la alerta, por ejemplo "AL-1001".
    """
    a = _load_alert(alert_id)
    if a is None:
        return _not_found(alert_id)
    start = a["created_ts"] - timedelta(hours=BENEFICIARY_WINDOW_HOURS)
    inbound, _ = _window_flows(a["to_account"], start, a["created_ts"])
    other = db.query(
        """SELECT DISTINCT t.from_account FROM alerts al JOIN transactions t ON t.tx_id = al.tx_id
           WHERE al.alert_id <> @alert_id AND al.created_ts <= @now""",
        {"alert_id": alert_id, "now": a["created_ts"]},
    )
    with_alert = {r["from_account"] for r in other}
    totals: dict[str, int] = {}
    for r in inbound:
        totals[r["from_account"]] = totals.get(r["from_account"], 0) + r["amount_cop"]
    senders = [{"from_account": acct, "amount_cop": amt, "has_other_alert": acct in with_alert}
               for acct, amt in sorted(totals.items())]
    return {
        "status": "ok",
        "beneficiary_account": a["to_account"],
        "senders": senders,
        "senders_count": len(senders),
        "senders_with_other_alert_count": sum(s["has_other_alert"] for s in senders),
    }


def create_case_draft(alert_id: str, typology: Typology, risk: Risk, evidence: list[dict],
                      discarded_hypotheses: list[dict], recommendation: str) -> dict:
    """Guarda un borrador de caso con el dictamen. Es la única herramienta que escribe.

    Úsala solo al final, cuando ya reuniste la evidencia, y solo tras la confirmación
    humana. No aprueba el caso: el borrador queda pendiente de revisión.

    Args:
        alert_id: Identificador de la alerta investigada.
        typology: Código de la tipología ganadora: toma_de_cuenta, ingenieria_social_mula,
            mula_receptora o falso_positivo.
        risk: Nivel de riesgo: bajo, medio o alto.
        evidence: Lista de evidencias; cada una es {"dato": "...", "herramienta": "..."}
            con una cifra devuelta por una herramienta y el nombre de esa herramienta.
        discarded_hypotheses: Lista de hipótesis descartadas; cada una es
            {"hipotesis": "...", "motivo": "..."}.
        recommendation: Acción recomendada (por ejemplo cerrar, escalar, bloquear llave).
    """
    a = _load_alert(alert_id)
    if a is None:
        return _not_found(alert_id)
    if typology not in TYPOLOGIES:
        return _error(f"typology inválida: {typology!r}. Valores permitidos: {', '.join(TYPOLOGIES)}")
    if risk not in RISKS:
        return _error(f"risk inválido: {risk!r}. Valores permitidos: {', '.join(RISKS)}")
    n = db.query("SELECT COUNT(*) AS n FROM case_drafts WHERE alert_id = @alert_id",
                 {"alert_id": alert_id})[0]["n"]
    case_id = f"CD-{alert_id}-{n + 1}"
    db.execute(
        """INSERT INTO case_drafts (case_id, alert_id, created_ts, hypothesis, risk,
                                    recommendation, evidence_json, approved_by)
           VALUES (@case_id, @alert_id, @created_ts, @hypothesis, @risk,
                   @recommendation, @evidence_json, NULL)""",
        {"case_id": case_id, "alert_id": alert_id, "created_ts": a["created_ts"],
         "hypothesis": typology, "risk": risk, "recommendation": recommendation,
         "evidence_json": json.dumps(
             {"typology": typology, "risk": risk, "evidence": evidence,
              "discarded_hypotheses": discarded_hypotheses, "recommendation": recommendation},
             ensure_ascii=False)},
    )
    return {"status": "ok", "case_id": case_id, "case_status": "draft"}
