"""Valores esperados de la Fase 2 del HANDBOOK.md ("ahora" = created_ts de cada alerta)."""
import json
import shutil

import pytest

from investigador_alertas import data_backend, tools

TOL = 0.05


@pytest.fixture(autouse=True, params=["sqlite", "bigquery"])
def backend(request, monkeypatch):
    monkeypatch.setenv("DATA_BACKEND", request.param)
    return request.param


@pytest.mark.parametrize("alert_id, customer, to_account, created, amount, score, reasons", [
    ("AL-1001", "C001", "X-RENT", "2026-11-02 11:01:00", 2_400_000, 0.64, ["AMOUNT_ABOVE_PROFILE"]),
    ("AL-1002", "C002", "M001", "2026-11-02 12:01:00", 4_500_000, 0.91,
     ["NEW_BENEFICIARY", "AMOUNT_ABOVE_PROFILE"]),
    ("AL-1003", "C003", "B001", "2026-11-02 13:16:00", 6_000_000, 0.88,
     ["NEW_BENEFICIARY", "AMOUNT_ABOVE_PROFILE"]),
])
def test_get_alert(alert_id, customer, to_account, created, amount, score, reasons):
    r = tools.get_alert(alert_id)
    assert r["status"] == "ok"
    assert r["customer_id"] == customer
    assert r["to_account"] == to_account
    assert r["created_ts"] == created
    assert r["amount_cop"] == amount
    assert r["engine_score"] == pytest.approx(score)
    assert r["reason_codes"] == reasons


@pytest.mark.parametrize("alert_id, count, median, ratio, prior_n, prior_median, prior_ratio", [
    ("AL-1001", 26, 139_000, 17.3, 4, 1_800_000, 1.33),
    ("AL-1002", 30, 141_500, 31.8, 0, None, None),
    ("AL-1003", 30, 94_000, 63.8, 0, None, None),
])
def test_analyze_behavior(alert_id, count, median, ratio, prior_n, prior_median, prior_ratio):
    r = tools.analyze_behavior(alert_id)
    assert r["status"] == "ok"
    assert r["transfers_90d_count"] == count
    assert r["median_amount_90d_cop"] == median
    assert r["amount_vs_median_ratio"] == pytest.approx(ratio, abs=TOL)
    assert r["prior_payments_to_beneficiary_count"] == prior_n
    assert r["prior_payments_median_cop"] == prior_median
    if prior_ratio is None:
        assert r["amount_vs_prior_payments_ratio"] is None
    else:
        assert r["amount_vs_prior_payments_ratio"] == pytest.approx(prior_ratio, abs=TOL)
    # La hora cae siempre dentro del rango habitual (8 a 21 h).
    assert r["within_usual_hours"] is True
    assert 8 <= r["usual_hour_min"] and r["usual_hour_max"] <= 21


@pytest.mark.parametrize("alert_id", ["AL-1001", "AL-1002"])
def test_session_devices_habitual(alert_id):
    r = tools.get_session_devices(alert_id)
    assert len(r["devices"]) == 1
    assert r["transfer_device_is_new"] is False
    assert r["contact_change_ts"] is None
    assert r["contact_change_minutes_before_transfer"] is None


def test_session_devices_account_takeover():
    r = tools.get_session_devices("AL-1003")
    assert r["transfer_device_id"] == "D-C003-NEW"
    assert r["transfer_device_is_new"] is True
    new = next(d for d in r["devices"] if d["device_id"] == "D-C003-NEW")
    assert new["first_seen"] == "2026-11-02 13:10:00"
    assert r["contact_change_ts"] == "2026-11-02 12:50:00"
    assert r["contact_change_minutes_before_transfer"] == 25


@pytest.mark.parametrize("alert_id, acct_age, key_age, senders, inbound, outbound, pass_through", [
    ("AL-1001", 900, 700, 1, 2_400_000, 0, 0.0),
    ("AL-1002", 3, 3, 15, 13_444_000, 8_100_000, 0.60),
    ("AL-1003", 400, 380, 3, 6_370_000, 0, 0.0),
])
def test_check_beneficiary(alert_id, acct_age, key_age, senders, inbound, outbound, pass_through):
    r = tools.check_beneficiary(alert_id)
    assert r["status"] == "ok"
    assert r["account_age_days"] == acct_age
    assert r["key_age_days"] == key_age
    assert r["distinct_senders_24h"] == senders
    assert r["inbound_24h_cop"] == inbound
    assert r["outbound_24h_cop"] == outbound
    assert r["pass_through_ratio"] == pytest.approx(pass_through, abs=TOL)


@pytest.mark.parametrize("alert_id, senders, with_alert", [
    ("AL-1001", 1, 0),
    ("AL-1002", 15, 5),
    ("AL-1003", 3, 0),
])
def test_get_inbound_senders(alert_id, senders, with_alert):
    r = tools.get_inbound_senders(alert_id)
    assert r["status"] == "ok"
    assert r["senders_count"] == senders
    assert r["senders_with_other_alert_count"] == with_alert
    assert sum(1 for s in r["senders"] if s["has_other_alert"]) == with_alert


@pytest.mark.parametrize("tool", [
    tools.get_alert, tools.analyze_behavior, tools.get_session_devices,
    tools.check_beneficiary, tools.get_inbound_senders,
])
def test_alert_not_found(tool):
    r = tool("AL-9999")
    assert r["status"] == "error"
    assert "AL-9999" in r["message"]


def test_create_case_draft_writes_one_row(backend, tmp_path, monkeypatch):
    if backend == "sqlite":  # copia temporal: no ensucia la base real
        copy = tmp_path / "copia.db"
        shutil.copy(data_backend._DEFAULT_SQLITE, copy)
        monkeypatch.setenv("SQLITE_PATH", str(copy))

    evidence = [{"dato": "4 pagos previos", "herramienta": "analyze_behavior"}]
    discarded = [{"hipotesis": "mula receptora", "motivo": "cuenta de 900 días"}]
    r = tools.create_case_draft("AL-1001", "falso_positivo", "bajo", evidence, discarded, "cerrar")
    try:
        assert r["status"] == "ok"
        rows = data_backend.query(
            "SELECT case_id, alert_id, hypothesis, risk, recommendation, evidence_json "
            "FROM case_drafts WHERE case_id = @case_id", {"case_id": r["case_id"]})
        assert len(rows) == 1
        row = rows[0]
        assert (row["alert_id"], row["hypothesis"], row["risk"], row["recommendation"]) == \
            ("AL-1001", "falso_positivo", "bajo", "cerrar")
        assert json.loads(row["evidence_json"]) == {
            "typology": "falso_positivo", "risk": "bajo", "evidence": evidence,
            "discarded_hypotheses": discarded, "recommendation": "cerrar"}
    finally:  # en BigQuery la tabla es la real: borra la fila de prueba
        data_backend.execute("DELETE FROM case_drafts WHERE case_id = @case_id",
                             {"case_id": r["case_id"]})

    assert tools.create_case_draft("AL-9999", "falso_positivo", "bajo", [], [], "x")["status"] == "error"


@pytest.mark.parametrize("typology, risk", [
    ("falso positivo", "bajo"),   # sin guion bajo: no es un código
    ("fraude", "bajo"),
    ("falso_positivo", "extremo"),
])
def test_create_case_draft_rejects_invalid_values(typology, risk):
    before = data_backend.query("SELECT COUNT(*) AS n FROM case_drafts")[0]["n"]
    r = tools.create_case_draft("AL-1001", typology, risk, [], [], "cerrar")
    assert r["status"] == "error"
    assert data_backend.query("SELECT COUNT(*) AS n FROM case_drafts")[0]["n"] == before
