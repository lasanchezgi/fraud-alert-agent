"""Verificación remota del despliegue en Agent Runtime: AL-1001 completa y AL-1002 hasta la confirmación.

No aprueba nada: AL-1002 se detiene en cuanto aparece adk_request_confirmation, así que
case_drafts no gana filas. Llama al modelo y a BigQuery desde la nube.
Uso: .venv/bin/python scripts/remote_check.py [resource_name]
(por defecto lee deployment_resource_name.txt)
"""
import asyncio
import json
import re
import sys
from pathlib import Path

import agentplatform

ROOT = Path(__file__).resolve().parent.parent
PROJECT, REGION = "adk-deploy-laura-16499", "us-central1"
CONFIRM_CALL = "adk_request_confirmation"
USER = "analista"


async def run(remote, alert_id: str) -> dict:
    session = await remote.async_create_session(user_id=USER)
    sid = session["id"] if isinstance(session, dict) else session.id
    tools, text, confirm, create_args, errors = [], "", False, None, []
    async for ev in remote.async_stream_query(
            user_id=USER, session_id=sid, message=f"Investiga la alerta {alert_id}"):
        if ev.get("error_code") or ev.get("error_message"):
            errors.append(f"{ev.get('error_code')}: {ev.get('error_message')}")
        for part in (ev.get("content") or {}).get("parts") or []:
            fc, fr = part.get("function_call"), part.get("function_response")
            if fc:
                if fc["name"] == CONFIRM_CALL:
                    confirm = True
                else:
                    tools.append(fc["name"])
                    if fc["name"] == "create_case_draft":
                        create_args = fc.get("args")
            if fr and fr.get("name") != CONFIRM_CALL and "error" in json.dumps(fr.get("response"), default=str).lower()[:200]:
                errors.append(f"{fr['name']}: {json.dumps(fr.get('response'), default=str)[:200]}")
            if part.get("text") and ev.get("author") == "investigador_alertas":
                text += part["text"]
        if confirm:  # AL-1002: se corta en la solicitud, sin aprobar
            break
    return {"alert": alert_id, "tools": tools, "confirm": confirm, "text": text,
            "create_args": create_args, "errors": errors}


def verdict(r: dict) -> str:
    if r["create_args"]:
        return str(r["create_args"].get("typology", "?"))
    m = re.search(r"Tipolog[ií]a:\**\s*(\w+)", r["text"])
    return m.group(1) if m else "?"


async def main() -> None:
    name = sys.argv[1] if len(sys.argv) > 1 else (ROOT / "deployment_resource_name.txt").read_text().strip()
    client = agentplatform.Client(project=PROJECT, location=REGION)
    remote = client.runtimes.get(name=name)
    # (alerta, veredicto esperado, ¿debe pedir confirmación?)
    expected = [("AL-1001", "falso_positivo", False), ("AL-1002", "ingenieria_social_mula", True)]
    ok_all = True
    for alert, want, want_confirm in expected:
        r = await run(remote, alert)
        v = verdict(r)
        ok = v == want and r["confirm"] == want_confirm and not r["errors"]
        ok_all &= ok
        print(f"\n===== {alert} (remoto) =====")
        print("herramientas:", " > ".join(r["tools"]) or "(ninguna)")
        print("confirmación solicitada:", r["confirm"], f"(esperado {want_confirm})")
        print("veredicto:", v, f"(esperado {want})")
        if r["create_args"]:
            print("argumentos de create_case_draft:", json.dumps(r["create_args"], ensure_ascii=False, indent=1))
        if r["errors"]:
            print("ERRORES:", *r["errors"], sep="\n  ")
        if r["text"]:
            print(r["text"])
        print(f"-> {'OK' if ok else 'REVISAR'}")
    print("\nRESULTADO GLOBAL:", "OK" if ok_all else "REVISAR")
    sys.exit(0 if ok_all else 1)


if __name__ == "__main__":
    asyncio.run(main())
