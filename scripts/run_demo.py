"""Fase 3, corrida de validación: 3 alertas x 3 corridas con Runner e InMemorySessionService.

No aprueba la confirmación: si el agente pide crear el caso, la corrida termina ahí
y se comprueba que case_drafts no ganó filas. Llama al modelo (Vertex AI).
Uso: .venv/bin/python scripts/run_demo.py [--alerts AL-2001,AL-2002] [--runs 1]
Las alertas sin entrada en FIGURES/EXPECTED omiten la verificación de cifras y la comparación.
"""
import argparse
import asyncio
import re
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from google.adk.runners import Runner  # noqa: E402
from google.adk.sessions import InMemorySessionService  # noqa: E402
from google.genai import types  # noqa: E402

from investigador_alertas import data_backend  # noqa: E402
from investigador_alertas.agent import root_agent  # noqa: E402

ALERTS = ["AL-1001", "AL-1002", "AL-1003"]
RUNS = 3
APP, USER = "run_demo", "analista"
CONFIRM_CALL = "adk_request_confirmation"

# Tipología esperada por alerta (códigos del Literal de create_case_draft).
EXPECTED = {"AL-1001": "falso_positivo", "AL-1002": "ingenieria_social_mula", "AL-1003": "toma_de_cuenta"}

# Cifras obligatorias por alerta (validaciones 3.2 a 3.4). Aceptan coma o punto decimal.
# Se buscan en todo lo que el agente produjo: texto + argumentos de create_case_draft.
FIGURES = {
    "AL-1001": [
        ("4 pagos", r"\b(4|cuatro)\b[^.\n]{0,40}(pagos|transferencias)|(pagos|transferencias)[^.\n]{0,40}\b(4|cuatro)\b"),
        ("1,33", r"\b1[.,]33\b"),
    ],
    "AL-1002": [
        ("15 remitentes", r"\b15\b"),
        ("5 con alerta", r"\b5\b[^\n]{0,80}alert|alert[^\n]{0,80}\b5\b"),
        ("60 % / 0,6", r"\b60\s?%|\b0[.,]60?\b(?!\d)"),
    ],
    "AL-1003": [
        ("dispositivo nuevo", r"dispositivo[^.\n]{0,60}nuevo|nuevo[^.\n]{0,60}dispositivo|D-C003-NEW|is_new\W+true"),
        ("25 min", r"\b25\b[^.\n]{0,30}min|before\W+25\b"),
        ("400 días", r"\b400\b[^.\n]{0,20}(d[ií]as|days)|age_days\W+400\b"),
    ],
}


def classify(text: str) -> str:
    """Código de tipología: argumento typology= de create_case_draft o línea 'Tipología: código'."""
    m = re.search(r"typology=(\w+)", text) or re.search(r"Tipolog[ií]a:\**\s*(\w+)", text)
    return m.group(1) if m else "?"


def missing_figures(alert_id: str, text: str) -> list[str]:
    return [name for name, rx in FIGURES.get(alert_id, []) if not re.search(rx, text, re.I)]


def draft_count() -> int:
    return data_backend.query("SELECT COUNT(*) AS n FROM case_drafts")[0]["n"]


async def run_once(alert_id: str, n: int) -> dict:
    service = InMemorySessionService()
    runner = Runner(app_name=APP, agent=root_agent, session_service=service)
    session = await service.create_session(app_name=APP, user_id=USER)
    msg = types.Content(role="user", parts=[types.Part(text=f"Investiga la alerta {alert_id}")])

    calls, confirmation, text = [], False, ""
    async for ev in runner.run_async(user_id=USER, session_id=session.id, new_message=msg):
        for fc in ev.get_function_calls():
            if fc.name == CONFIRM_CALL:
                confirmation = True
            else:
                calls.append(fc.name)
                if fc.name == "create_case_draft":  # lo que vería el analista al aprobar
                    text += "\n[create_case_draft] " + "; ".join(
                        f"{k}={v}" for k, v in (fc.args or {}).items()) + "\n"
        # El dictamen puede venir en el mismo evento que create_case_draft (no es "final").
        if ev.author == root_agent.name and ev.content and ev.content.parts:
            text += "".join(p.text or "" for p in ev.content.parts if p.text)
    return {"alert": alert_id, "run": n, "tools": calls, "confirmation": confirmation, "text": text}


async def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--alerts", default=",".join(ALERTS), help="lista separada por comas")
    ap.add_argument("--runs", type=int, default=RUNS)
    args = ap.parse_args()
    alerts = [a.strip() for a in args.alerts.split(",") if a.strip()]
    before = draft_count()
    results = []
    for alert in alerts:
        for n in range(1, args.runs + 1):
            try:
                r = await run_once(alert, n)
            except Exception as e:  # p. ej. 429 o permisos: se registra y se sigue
                r = {"alert": alert, "run": n, "tools": [], "confirmation": False,
                     "text": f"ERROR: {type(e).__name__}: {e}"}
            r["verdict"] = classify(r["text"])
            r["missing"] = missing_figures(alert, r["text"])
            results.append(r)
            print(f"\n===== {alert} corrida {n} =====")
            print("herramientas:", " > ".join(r["tools"]) or "(ninguna)")
            print("confirmación solicitada:", r["confirmation"])
            print(r["text"])

    after = draft_count()
    print("\n\n===== RESUMEN =====")
    print(f"{'alerta':8} {'#':>1}  {'veredicto':22} {'conf.':5} {'cifras':7} herramientas")
    for r in results:
        total = len(FIGURES.get(r["alert"], []))
        figs = f"{total - len(r['missing'])}/{total}"
        print(f"{r['alert']:8} {r['run']:>1}  {r['verdict']:22} {str(r['confirmation']):5} {figs:7} "
              + " > ".join(r["tools"]))

    print("\n===== COMPARACIÓN CON LAS VALIDACIONES =====")
    for alert in alerts:
        if alert not in EXPECTED:
            continue
        rs = [r for r in results if r["alert"] == alert]
        verdicts = {r["verdict"] for r in rs}
        n_inb = sum("get_inbound_senders" in r["tools"] for r in rs)
        asked = [r["confirmation"] for r in rs]
        ok_verdict = verdicts == {EXPECTED[alert]}
        if alert == "AL-1001":   # 3.2
            extra = n_inb == 0 and not any(asked) and all(
                r["text"].lstrip().startswith("Tipología: falso_positivo") for r in rs)
            detail = "sin get_inbound_senders ni confirmación; empieza con 'Tipología: falso_positivo'"
        elif alert == "AL-1002":  # 3.3
            extra = n_inb == len(rs) and all(asked)
            detail = "get_inbound_senders en 3 de 3 y confirmación en todas"
        else:                     # 3.4
            extra = n_inb <= 1 and all("get_session_devices" in r["tools"] for r in rs)
            detail = "get_inbound_senders en 1 corrida como máximo y usa get_session_devices"
        figs_ok = all(not r["missing"] for r in rs)
        print(f"{alert}: veredicto {sorted(verdicts)} esperado {EXPECTED[alert]} -> "
              f"{'OK' if ok_verdict else 'REVISAR'} | {detail} -> {'OK' if extra else 'REVISAR'}")
        print(f"   llamadas a get_inbound_senders: {n_inb} de {len(rs)}")
        print(f"   cifras obligatorias -> {'OK' if figs_ok else 'REVISAR'}"
              + "".join(f" | corrida {r['run']} falta: {', '.join(r['missing'])}" for r in rs if r["missing"]))
        print(f"   3.6 estabilidad: {'OK' if len(verdicts) == 1 else 'REVISAR'}")
    print(f"3.5 case_drafts: {before} filas antes, {after} después -> "
          f"{'OK (sin filas nuevas al no aprobar)' if before == after else 'REVISAR'}")
    print("Nota: sin aprobar, AL-1002 y AL-1003 no producen dictamen en texto; veredicto y cifras "
          "salen de los argumentos de create_case_draft. 3.7 sigue sin automatizar.")


if __name__ == "__main__":
    asyncio.run(main())
