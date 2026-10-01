import sqlite3
import json
import secrets
from datetime import datetime, timezone
from pathlib import Path

DB_PATH = Path(__file__).parent / "data" / "app.db"

SCHEMA = """
CREATE TABLE IF NOT EXISTS labs (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    name TEXT NOT NULL,
    contact_name TEXT,
    email TEXT,
    phone TEXT,
    address TEXT,
    owner_name TEXT,
    owner_address TEXT,
    owner_ssn TEXT,
    state TEXT,
    access_token TEXT UNIQUE,
    created_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS settings (
    id INTEGER PRIMARY KEY CHECK (id = 1),
    c_scanner REAL NOT NULL DEFAULT 7700,
    c_pc REAL NOT NULL DEFAULT 2200,
    c_cart REAL NOT NULL DEFAULT 350,
    c_ship REAL NOT NULL DEFAULT 200,
    c_train REAL NOT NULL DEFAULT 750,
    c_markup REAL NOT NULL DEFAULT 1500,
    lab_down_payment REAL NOT NULL DEFAULT 1270,
    lab_apr REAL NOT NULL DEFAULT 0.085,
    lab_term INTEGER NOT NULL DEFAULT 36,
    round_to REAL NOT NULL DEFAULT 5
);

CREATE TABLE IF NOT EXISTS proposals (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    lab_id INTEGER NOT NULL,
    token TEXT UNIQUE,
    client_practice_name TEXT,
    client_doctor_name TEXT,
    client_email TEXT,
    client_phone TEXT,
    client_address TEXT,
    inputs_json TEXT NOT NULL,
    results_json TEXT NOT NULL,
    status TEXT NOT NULL DEFAULT 'draft',
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL,
    FOREIGN KEY (lab_id) REFERENCES labs (id)
);
"""


def _new_token():
    return secrets.token_urlsafe(20)


def get_db():
    DB_PATH.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    conn.executescript(SCHEMA)
    # Defensive migration for databases created before tokens existed.
    existing_lab_cols = {r["name"] for r in conn.execute("PRAGMA table_info(labs)")}
    if "access_token" not in existing_lab_cols:
        conn.execute("ALTER TABLE labs ADD COLUMN access_token TEXT")
    existing_proposal_cols = {r["name"] for r in conn.execute("PRAGMA table_info(proposals)")}
    if "token" not in existing_proposal_cols:
        conn.execute("ALTER TABLE proposals ADD COLUMN token TEXT")
    for col in ("owner_name", "owner_address", "owner_ssn", "state"):
        if col not in existing_lab_cols:
            conn.execute(f"ALTER TABLE labs ADD COLUMN {col} TEXT")
    # Backfill any rows that predate the token columns.
    for row in conn.execute("SELECT id FROM labs WHERE access_token IS NULL"):
        conn.execute("UPDATE labs SET access_token = ? WHERE id = ?", (_new_token(), row["id"]))
    for row in conn.execute("SELECT id FROM proposals WHERE token IS NULL"):
        conn.execute("UPDATE proposals SET token = ? WHERE id = ?", (_new_token(), row["id"]))
    conn.execute("INSERT OR IGNORE INTO settings (id) VALUES (1)")
    conn.commit()
    return conn


def get_settings():
    conn = get_db()
    row = conn.execute("SELECT * FROM settings WHERE id = 1").fetchone()
    conn.close()
    d = dict(row)
    d["equipment_cost"] = d["c_scanner"] + d["c_pc"] + d["c_cart"] + d["c_ship"] + d["c_train"] + d["c_markup"]
    d["lab_financed"] = max(0.0, d["equipment_cost"] - d["lab_down_payment"])
    return d


def update_settings(data):
    conn = get_db()
    fields = ["c_scanner", "c_pc", "c_cart", "c_ship", "c_train", "c_markup",
              "lab_down_payment", "lab_apr", "lab_term", "round_to"]
    values = [data[f] for f in fields]
    conn.execute(
        f"UPDATE settings SET {', '.join(f + ' = ?' for f in fields)} WHERE id = 1",
        values,
    )
    conn.commit()
    conn.close()


def now():
    return datetime.now(timezone.utc).isoformat()


def create_lab(name, contact_name="", email="", phone="", address="",
                owner_name="", owner_address="", owner_ssn="", state=""):
    conn = get_db()
    token = _new_token()
    cur = conn.execute(
        """INSERT INTO labs
           (name, contact_name, email, phone, address, owner_name, owner_address, owner_ssn, state, access_token, created_at)
           VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
        (name, contact_name, email, phone, address, owner_name, owner_address, owner_ssn, state, token, now()),
    )
    conn.commit()
    lab_id = cur.lastrowid
    conn.close()
    return lab_id


def list_labs():
    """All labs -- admin use only. Never render this to a public/unauthenticated page."""
    conn = get_db()
    rows = conn.execute("SELECT * FROM labs ORDER BY name COLLATE NOCASE").fetchall()
    conn.close()
    return [dict(r) for r in rows]


def get_lab(lab_id):
    conn = get_db()
    row = conn.execute("SELECT * FROM labs WHERE id = ?", (lab_id,)).fetchone()
    conn.close()
    return dict(row) if row else None


def get_lab_by_token(token):
    if not token:
        return None
    conn = get_db()
    row = conn.execute("SELECT * FROM labs WHERE access_token = ?", (token,)).fetchone()
    conn.close()
    return dict(row) if row else None


def create_proposal(lab_id, client, inputs, results):
    conn = get_db()
    ts = now()
    token = _new_token()
    cur = conn.execute(
        """INSERT INTO proposals
           (lab_id, token, client_practice_name, client_doctor_name, client_email,
            client_phone, client_address, inputs_json, results_json,
            status, created_at, updated_at)
           VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, 'draft', ?, ?)""",
        (
            lab_id,
            token,
            client.get("practice_name", ""),
            client.get("doctor_name", ""),
            client.get("email", ""),
            client.get("phone", ""),
            client.get("address", ""),
            json.dumps(inputs),
            json.dumps(results),
            ts,
            ts,
        ),
    )
    conn.commit()
    pid = cur.lastrowid
    conn.close()
    return pid


def _row_to_proposal(row):
    d = dict(row)
    d["inputs"] = json.loads(d.pop("inputs_json"))
    d["results"] = json.loads(d.pop("results_json"))
    return d


def get_proposal(proposal_id):
    conn = get_db()
    row = conn.execute("SELECT * FROM proposals WHERE id = ?", (proposal_id,)).fetchone()
    conn.close()
    if not row:
        return None
    return _row_to_proposal(row)


def get_proposal_by_token(token):
    if not token:
        return None
    conn = get_db()
    row = conn.execute("SELECT * FROM proposals WHERE token = ?", (token,)).fetchone()
    conn.close()
    if not row:
        return None
    return _row_to_proposal(row)


def list_proposals(lab_id=None):
    """All proposals (optionally filtered to one lab) -- admin use only."""
    conn = get_db()
    if lab_id:
        rows = conn.execute(
            """SELECT p.*, l.name AS lab_name FROM proposals p
               JOIN labs l ON l.id = p.lab_id
               WHERE p.lab_id = ? ORDER BY p.created_at DESC""",
            (lab_id,),
        ).fetchall()
    else:
        rows = conn.execute(
            """SELECT p.*, l.name AS lab_name FROM proposals p
               JOIN labs l ON l.id = p.lab_id
               ORDER BY p.created_at DESC"""
        ).fetchall()
    conn.close()
    out = []
    for r in rows:
        d = dict(r)
        d["results"] = json.loads(d.pop("results_json"))
        d.pop("inputs_json", None)
        out.append(d)
    return out


def update_proposal(proposal_id, client, inputs, results):
    """Overwrite an existing proposal in place -- same id, same token, same
    link -- so editing a proposal never creates a stray duplicate."""
    conn = get_db()
    conn.execute(
        """UPDATE proposals SET
             client_practice_name = ?, client_doctor_name = ?, client_email = ?,
             client_phone = ?, client_address = ?, inputs_json = ?, results_json = ?,
             updated_at = ?
           WHERE id = ?""",
        (
            client.get("practice_name", ""),
            client.get("doctor_name", ""),
            client.get("email", ""),
            client.get("phone", ""),
            client.get("address", ""),
            json.dumps(inputs),
            json.dumps(results),
            now(),
            proposal_id,
        ),
    )
    conn.commit()
    conn.close()


def update_status(proposal_id, status):
    conn = get_db()
    conn.execute(
        "UPDATE proposals SET status = ?, updated_at = ? WHERE id = ?",
        (status, now(), proposal_id),
    )
    conn.commit()
    conn.close()
