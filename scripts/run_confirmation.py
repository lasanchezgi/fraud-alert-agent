"""Fase 3, validación 3.5 y límites nuevos: responde a la confirmación (rechazar / aprobar).

Corre sobre una COPIA temporal de SQLite (no toca la base real ni BigQuery).
Uso: .venv/bin/python scripts/run_confirmation.py
"""
import asyncio
import os
import shutil
import sys
import tempfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from google.adk.runners import Runner  # noqa: E402
from google.adk.sessions import InMemorySessionService  # noqa: E402
from google.genai import types  # noqa: E402

from investigador_alertas import data_backend  # noqa: E402
from investigador_alertas.agent import root_agent  # noqa: E402

APP, USER = "run_confirmation", "analista"
CONFIRM_CALL = "adk_request_confirmation"


def rows() -> list[dict]:
    return data_backend.query("SELECT case_id, alert_id, hypothesis, risk, approved_by FROM case_drafts")


async def run(alert_id: str, confirmed: bool) -> dict:
    service = InMemorySessionService()
    runner = Runner(app_name=APP, agent=root_agent, session_service=service)
    session = await service.create_session(app_name=APP, user_id=USER)
    msg = types.Content(role="user", parts=[types.Part(text=f"Investiga la alerta {alert_id}")])

    before = len(rows())
    calls, confirm_id = [], None
    async for ev in runner.run_async(user_id=USER, session_id=session.id, new_message=msg):
        for fc in ev.get_function_calls():
            if fc.name == CONFIRM_CALL:
                confirm_id = fc.id
            else:
                calls.append(fc.name)
    if confirm_id is None:
        return {"asked": False, "calls": calls, "text": "", "new_rows": len(rows()) - before}

    reply = types.Content(role="user", parts=[types.Part(function_response=types.FunctionResponse(
        id=confirm_id, name=CONFIRM_CALL, response={"confirmed": confirmed}))])
    text, after_calls = "", []
    async for ev in runner.run_async(user_id=USER, session_id=session.id, new_message=reply):
        for fc in ev.get_function_calls():
            after_calls.append(fc.name)
        if ev.author == root_agent.name and ev.content and ev.content.parts:
            text += "".join(p.text or "" for p in ev.content.parts if p.text)
    return {"asked": True, "calls": calls, "after_calls": after_calls, "text": text,
            "new_rows": len(rows()) - before}


async def main() -> None:
    # (alerta, confirmed, filas nuevas esperadas): aprobar AL-1002, rechazar AL-1003.
    cases = [("AL-1002", True, 1), ("AL-1003", False, 0)]
    with tempfile.TemporaryDirectory() as tmp:
        copy = Path(tmp) / "copia.db"
        shutil.copy(data_backend._DEFAULT_SQLITE, copy)
        os.environ["DATA_BACKEND"], os.environ["SQLITE_PATH"] = "sqlite", str(copy)

        for alert, confirmed, want_rows in cases:
            label = "APROBAR" if confirmed else "RECHAZAR"
            r = await run(alert, confirmed)
            print(f"\n===== {alert} · {label} =====")
            print("pidió confirmación:", r["asked"])
            print("llamadas tras la respuesta:", r.get("after_calls"))
            print("filas nuevas en case_drafts:", r["new_rows"], f"(esperado {want_rows})")
            print(r["text"])
            ok = r["asked"] and r["new_rows"] == want_rows
            if confirmed:  # el dictamen completo debe quedar escrito en texto
                ok = ok and len(r["text"]) > 200 and "tipolog" in r["text"].lower()
            else:          # no debe reintentar la herramienta
                ok = ok and "create_case_draft" not in r["after_calls"]
            print(f"-> {'OK' if ok else 'REVISAR'}")
        print("\nfilas en la copia:", rows())


if __name__ == "__main__":
    asyncio.run(main())
