"""Datos 100 % sintéticos para el agente investigador de alertas (pitch GEAR).

Salida en ./datos_sinteticos/:
  - un CSV por tabla (listos para `bq load`)
  - fraude_sintetico.db (SQLite, respaldo local / Plan B)

Nada aquí proviene de un sistema, regla o dato real. Es un proyecto personal.

Tres alertas de demo, cada una con un camino de investigación distinto:
  AL-1001  Falso positivo: pago de arriendo habitual con monto algo mayor.
  AL-1002  Ingeniería social (APP) hacia una cuenta mula.
  AL-1003  Toma de cuenta: dispositivo nuevo + cambio de celular minutos antes.

Las herramientas deben usar como "ahora" el created_ts de la alerta, no el reloj real.
"""
import csv
import os
import random
import sqlite3
import statistics
from datetime import datetime, timedelta

random.seed(7)
NOW = datetime(2026, 11, 2, 14, 0, 0)  # "ahora" ficticio de la demo
OUT = "datos_sinteticos"
os.makedirs(OUT, exist_ok=True)


def f(d):
    return d.strftime("%Y-%m-%d %H:%M:%S")


def day(d):
    return d.strftime("%Y-%m-%d")


COLS = {
    "customers": ["customer_id", "segment", "city", "signup_date"],
    "accounts": ["account_id", "customer_id", "opened_date", "key_created_date"],
    "transactions": ["tx_id", "ts", "from_account", "to_account", "amount_cop", "channel", "status"],
    "sessions": ["session_id", "customer_id", "ts", "device_id", "ip_country", "contact_change_ts"],
    "alerts": ["alert_id", "tx_id", "customer_id", "created_ts", "engine_score", "reason_codes", "status"],
    "case_drafts": ["case_id", "alert_id", "created_ts", "hypothesis", "risk", "recommendation",
                    "evidence_json", "approved_by"],
}
T = {k: [] for k in COLS}
_n = {"tx": 0, "ses": 0, "al": 2000}


def tx(ts, src, dst, amt, channel="app"):
    _n["tx"] += 1
    tid = f"T{_n['tx']:05d}"
    T["transactions"].append([tid, f(ts), src, dst, int(amt), channel, "completed"])
    return tid


def ses(cid, ts, dev, country="CO", change=None):
    _n["ses"] += 1
    T["sessions"].append([f"S{_n['ses']:05d}", cid, f(ts), dev, country, f(change) if change else ""])


def alert(tid, cid, ts, score, reasons, aid=None):
    if aid is None:
        _n["al"] += 1
        aid = f"AL-{_n['al']}"
    T["alerts"].append([aid, tid, cid, f(ts), score, "|".join(reasons), "open"])
    return aid


def customer(cid, seg, city, signup):
    T["customers"].append([cid, seg, city, signup])
    T["accounts"].append([f"O-{cid}", cid, signup, ""])


def ext(aid, opened_days_ago, key_days_ago=None):
    """Cuenta externa (beneficiario). Sin cliente propio."""
    T["accounts"].append([
        aid, "", day(NOW - timedelta(days=opened_days_ago)),
        day(NOW - timedelta(days=key_days_ago)) if key_days_ago is not None else "",
    ])


POOL = [f"X{i:03d}" for i in range(1, 16)]
for a in POOL:
    ext(a, random.randint(300, 1500), random.randint(200, 290))


def history(cid, devices, n, median, days=60):
    """Historia normal: pocos beneficiarios favoritos, montos alrededor de `median`."""
    favs = random.sample(POOL, 3)
    for _ in range(n):
        ts = NOW - timedelta(days=random.uniform(1.0, days))
        ts = ts.replace(hour=random.randint(8, 21), minute=random.randint(0, 59), second=random.randint(0, 59))
        dst = random.choice(favs) if random.random() < 0.8 else random.choice(POOL)
        amt = max(20000, round(random.lognormvariate(0, 0.45) * median, -3))
        tx(ts, f"O-{cid}", dst, amt)
        ses(cid, ts - timedelta(minutes=2), random.choice(devices))


CITIES = ["Medellín", "Bogotá", "Cali", "Barranquilla"]

# --- Fondo: 30 clientes con comportamiento normal -------------------------------
for i in range(1, 31):
    cid = f"N{i:03d}"
    customer(cid, random.choice(["personas", "personas", "pyme"]), random.choice(CITIES),
             day(NOW - timedelta(days=random.randint(200, 2000))))
    devs = [f"D-{cid}-1"] + ([f"D-{cid}-2"] if random.random() < 0.3 else [])
    history(cid, devs, random.randint(20, 40), random.choice([80000, 120000, 200000, 350000]))

# --- Alerta A: falso positivo (arriendo habitual con monto mayor) ---------------
customer("C001", "personas", "Medellín", day(NOW - timedelta(days=900)))
ext("X-RENT", 900, 700)
history("C001", ["D-C001-1"], 25, 110000, days=100)
for d in (28, 58, 88, 118):
    ts = (NOW - timedelta(days=d)).replace(hour=9, minute=15, second=0)
    tx(ts, "O-C001", "X-RENT", 1800000)
    ses("C001", ts - timedelta(minutes=2), "D-C001-1")
ts = NOW - timedelta(hours=3)
t = tx(ts, "O-C001", "X-RENT", 2400000)
ses("C001", ts - timedelta(minutes=2), "D-C001-1")
alert(t, "C001", ts + timedelta(minutes=1), 0.64, ["AMOUNT_ABOVE_PROFILE"], aid="AL-1001")

# --- Alerta B: APP hacia cuenta mula --------------------------------------------
customer("C002", "personas", "Bogotá", day(NOW - timedelta(days=1200)))
history("C002", ["D-C002-1"], 30, 150000)
ext("M001", 3, 3)  # cuenta y llave de 3 días
for i in range(1, 15):
    cid = f"SN{i:02d}"
    customer(cid, "personas", random.choice(CITIES), day(NOW - timedelta(days=random.randint(200, 2000))))
    history(cid, [f"D-{cid}-1"], 10, 150000)
    ts = NOW - timedelta(hours=random.uniform(2, 23))
    t = tx(ts, f"O-{cid}", "M001", random.randrange(300000, 900001, 1000))
    ses(cid, ts - timedelta(minutes=2), f"D-{cid}-1")
    if i <= 5:  # 5 remitentes ya tienen su propia alerta abierta
        alert(t, cid, ts + timedelta(minutes=1), round(random.uniform(0.70, 0.86), 2), ["NEW_BENEFICIARY"])
for h in (20, 14, 8, 1):  # la mula reenvía casi todo lo recibido (pass-through)
    tx(NOW - timedelta(hours=h), "M001", random.choice(POOL), 2700000)
ts = NOW - timedelta(hours=2)
t = tx(ts, "O-C002", "M001", 4500000)
ses("C002", ts - timedelta(minutes=2), "D-C002-1")
alert(t, "C002", ts + timedelta(minutes=1), 0.91, ["NEW_BENEFICIARY", "AMOUNT_ABOVE_PROFILE"], aid="AL-1002")

# --- Alerta C: toma de cuenta ---------------------------------------------------
customer("C003", "personas", "Cali", day(NOW - timedelta(days=700)))
history("C003", ["D-C003-1"], 30, 100000)
ext("B001", 400, 380)  # beneficiario antiguo y poco concurrido: no es mula
for cid, h, amt in (("N005", 9, 150000), ("N006", 5, 220000)):
    ts = NOW - timedelta(hours=h)
    tx(ts, f"O-{cid}", "B001", amt)
    ses(cid, ts - timedelta(minutes=2), f"D-{cid}-1")
ts = NOW - timedelta(minutes=45)
t = tx(ts, "O-C003", "B001", 6000000)
ses("C003", ts - timedelta(minutes=5), "D-C003-NEW", change=ts - timedelta(minutes=25))
alert(t, "C003", ts + timedelta(minutes=1), 0.88, ["NEW_BENEFICIARY", "AMOUNT_ABOVE_PROFILE"], aid="AL-1003")

# --- Salida ---------------------------------------------------------------------
for name, rows in T.items():
    with open(os.path.join(OUT, f"{name}.csv"), "w", newline="", encoding="utf-8") as fh:
        w = csv.writer(fh)
        w.writerow(COLS[name])
        w.writerows(rows)

db = os.path.join(OUT, "fraude_sintetico.db")
if os.path.exists(db):
    os.remove(db)
con = sqlite3.connect(db)
for name, cols in COLS.items():
    con.execute(f"CREATE TABLE {name} ({', '.join(cols)})")
    if T[name]:
        con.executemany(f"INSERT INTO {name} VALUES ({', '.join('?' * len(cols))})", T[name])
con.commit()


# --- Autoverificación -----------------------------------------------------------
def one(sql, *p):
    return con.execute(sql, p).fetchone()[0]


since = f(NOW - timedelta(hours=24))
now_s = f(NOW)

assert one("SELECT max(ts) FROM transactions") <= now_s
assert one("SELECT max(ts) FROM sessions") <= now_s
assert one("SELECT max(created_ts) FROM alerts") <= now_s

# A: beneficiario habitual (4 pagos previos + el de la alerta) y un solo dispositivo
assert one("SELECT count(*) FROM transactions WHERE from_account='O-C001' AND to_account='X-RENT'") == 5
assert one("SELECT count(DISTINCT device_id) FROM sessions WHERE customer_id='C001'") == 1

# B: dispositivo habitual, beneficiario nuevo con muchos remitentes y alertas hermanas
assert one("SELECT count(DISTINCT device_id) FROM sessions WHERE customer_id='C002'") == 1
assert one("SELECT count(*) FROM transactions WHERE from_account='O-C002' AND to_account='M001'") == 1
assert one("SELECT count(DISTINCT from_account) FROM transactions WHERE to_account='M001' AND ts>=?", since) == 15
assert one("""SELECT count(*) FROM alerts a JOIN transactions t ON a.tx_id=t.tx_id
              WHERE t.to_account='M001' AND a.alert_id<>'AL-1002'""") == 5
inflow = one("SELECT sum(amount_cop) FROM transactions WHERE to_account='M001'")
outflow = one("SELECT sum(amount_cop) FROM transactions WHERE from_account='M001'")
ratio = outflow / inflow
assert 0.6 <= ratio <= 1.0

# C: dispositivo nuevo + cambio de contacto antes de la transferencia; beneficiario poco concurrido
assert one("SELECT count(*) FROM sessions WHERE customer_id='C003' AND device_id='D-C003-NEW'") == 1
assert one("SELECT count(*) FROM sessions WHERE customer_id='C003' AND device_id='D-C003-1'") > 0
assert one("SELECT contact_change_ts FROM sessions WHERE device_id='D-C003-NEW'") < \
    one("SELECT ts FROM transactions WHERE from_account='O-C003' AND to_account='B001'")
assert one("SELECT count(DISTINCT from_account) FROM transactions WHERE to_account='B001' AND ts>=?", since) == 3
assert one("SELECT count(*) FROM transactions WHERE from_account='O-C003' AND to_account='B001'") == 1

print("Autoverificación OK")
for cid in ("C001", "C002", "C003"):
    amts = [r[0] for r in con.execute("SELECT amount_cop FROM transactions WHERE from_account=?", (f"O-{cid}",))]
    print(f"{cid}: {len(amts)} transferencias, mediana {int(statistics.median(amts)):,} COP")
print(f"M001: entradas {inflow:,} / salidas {outflow:,} (pass-through {ratio:.0%})")
for name, rows in T.items():
    print(f"{name}: {len(rows)} filas")
