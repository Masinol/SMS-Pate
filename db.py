"""SMS Pate - tietokantakerros (SQLite).

Sisältää asiakasrekisterin (customers), ryhmät (groups) ja niiden
monta-moneen-liitostaulun (customer_groups). Myöhemmin tähän lisätään
myös lähetetyt viestit (messages) ja niiden toimitusstatus.
"""

import re
import sqlite3
from contextlib import contextmanager
from pathlib import Path

DATA_DIR = Path(__file__).parent / "data"
DB_PATH = DATA_DIR / "sms_pate.db"


@contextmanager
def get_conn():
    DATA_DIR.mkdir(exist_ok=True)
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON")
    try:
        yield conn
    finally:
        conn.close()


def init_db():
    with get_conn() as conn:
        conn.execute(
            """CREATE TABLE IF NOT EXISTS customers (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                name TEXT NOT NULL,
                phone TEXT NOT NULL UNIQUE,
                email TEXT,
                note TEXT,
                created_at TEXT DEFAULT (datetime('now'))
            )"""
        )
        conn.execute(
            """CREATE TABLE IF NOT EXISTS groups (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                name TEXT NOT NULL UNIQUE
            )"""
        )
        conn.execute(
            """CREATE TABLE IF NOT EXISTS customer_groups (
                customer_id INTEGER NOT NULL REFERENCES customers(id) ON DELETE CASCADE,
                group_id INTEGER NOT NULL REFERENCES groups(id) ON DELETE CASCADE,
                PRIMARY KEY (customer_id, group_id)
            )"""
        )
        conn.execute(
            """CREATE TABLE IF NOT EXISTS settings (
                key TEXT PRIMARY KEY,
                value TEXT
            )"""
        )
        conn.execute(
            """CREATE TABLE IF NOT EXISTS messages (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                body TEXT NOT NULL,
                group_names TEXT,
                recipient_count INTEGER NOT NULL DEFAULT 0,
                created_at TEXT DEFAULT (datetime('now'))
            )"""
        )
        conn.execute(
            """CREATE TABLE IF NOT EXISTS message_recipients (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                message_id INTEGER NOT NULL REFERENCES messages(id) ON DELETE CASCADE,
                customer_id INTEGER REFERENCES customers(id) ON DELETE SET NULL,
                name TEXT,
                phone TEXT NOT NULL,
                status TEXT NOT NULL DEFAULT 'odottaa',
                provider_message_id TEXT,
                error TEXT,
                updated_at TEXT DEFAULT (datetime('now'))
            )"""
        )
        conn.commit()


# ---------------------------------------------------------------------------
# Asetukset (mm. SMS-palvelun API-avain). Ei koskaan koodissa - vain tässä
# tietokannassa, jota muokataan Asetukset-sivun kautta.
# ---------------------------------------------------------------------------

def get_setting(key: str, default: str = "") -> str:
    with get_conn() as conn:
        row = conn.execute("SELECT value FROM settings WHERE key = ?", (key,)).fetchone()
        return row["value"] if row else default


def get_settings(keys: list[str]) -> dict:
    with get_conn() as conn:
        placeholders = ",".join("?" for _ in keys)
        rows = conn.execute(
            f"SELECT key, value FROM settings WHERE key IN ({placeholders})", keys
        ).fetchall()
        found = {r["key"]: r["value"] for r in rows}
        return {k: found.get(k, "") for k in keys}


def set_setting(key: str, value: str):
    with get_conn() as conn:
        conn.execute(
            "INSERT INTO settings (key, value) VALUES (?, ?) "
            "ON CONFLICT(key) DO UPDATE SET value = excluded.value",
            (key, value),
        )
        conn.commit()


# ---------------------------------------------------------------------------
# Puhelinnumeron normalisointi (suomalaiset numerot -> +358...)
# ---------------------------------------------------------------------------

def normalize_phone(raw: str) -> str | None:
    """Normalisoi puhelinnumeron muotoon +358xxxxxxxxx.

    Hyväksyy mm. muodot: 0401234567, 040 123 4567, +358401234567,
    00358401234567, 358401234567. Palauttaa None jos numero ei näytä
    validilta.
    """
    if not raw:
        return None
    digits = re.sub(r"[^\d+]", "", str(raw).strip())
    if not digits:
        return None

    if digits.startswith("00"):
        digits = "+" + digits[2:]
    elif digits.startswith("0"):
        digits = "+358" + digits[1:]
    elif digits.startswith("358"):
        digits = "+" + digits
    elif not digits.startswith("+"):
        # Ei tunnistettua etuliitettä - oletetaan suomalainen numero ilman nollaa
        digits = "+358" + digits

    if not re.fullmatch(r"\+\d{7,15}", digits):
        return None
    return digits


# ---------------------------------------------------------------------------
# Ryhmät
# ---------------------------------------------------------------------------

def list_groups():
    with get_conn() as conn:
        rows = conn.execute(
            """SELECT g.id, g.name, COUNT(cg.customer_id) AS customer_count
               FROM groups g
               LEFT JOIN customer_groups cg ON cg.group_id = g.id
               GROUP BY g.id, g.name
               ORDER BY g.name COLLATE NOCASE"""
        ).fetchall()
        return [dict(r) for r in rows]


def get_or_create_group(name: str) -> int:
    name = name.strip()
    with get_conn() as conn:
        row = conn.execute("SELECT id FROM groups WHERE name = ?", (name,)).fetchone()
        if row:
            return row["id"]
        cur = conn.execute("INSERT INTO groups (name) VALUES (?)", (name,))
        conn.commit()
        return cur.lastrowid


def delete_group(group_id: int):
    with get_conn() as conn:
        conn.execute("DELETE FROM groups WHERE id = ?", (group_id,))
        conn.commit()


# ---------------------------------------------------------------------------
# Asiakkaat
# ---------------------------------------------------------------------------

def list_customers(group_id: int | None = None):
    with get_conn() as conn:
        rows = conn.execute(
            """SELECT c.id, c.name, c.phone, c.email, c.note, c.created_at,
                      COALESCE(GROUP_CONCAT(g.name, ', '), '') AS groups
               FROM customers c
               LEFT JOIN customer_groups cg ON cg.customer_id = c.id
               LEFT JOIN groups g ON g.id = cg.group_id
               GROUP BY c.id
               ORDER BY c.name COLLATE NOCASE"""
        ).fetchall()
        customers = [dict(r) for r in rows]

    if group_id is not None:
        customers = [
            c for c in customers
            if any(g.strip() for g in c["groups"].split(",")) and _customer_in_group(c["id"], group_id)
        ]
    return customers


def _customer_in_group(customer_id: int, group_id: int) -> bool:
    with get_conn() as conn:
        row = conn.execute(
            "SELECT 1 FROM customer_groups WHERE customer_id = ? AND group_id = ?",
            (customer_id, group_id),
        ).fetchone()
        return row is not None


def get_customer(customer_id: int):
    with get_conn() as conn:
        row = conn.execute("SELECT * FROM customers WHERE id = ?", (customer_id,)).fetchone()
        if not row:
            return None
        group_rows = conn.execute(
            """SELECT g.id, g.name FROM groups g
               JOIN customer_groups cg ON cg.group_id = g.id
               WHERE cg.customer_id = ?""",
            (customer_id,),
        ).fetchall()
        data = dict(row)
        data["group_ids"] = [g["id"] for g in group_rows]
        data["group_names"] = [g["name"] for g in group_rows]
        return data


def add_customer(name: str, phone: str, email: str = "", note: str = "", group_ids=None) -> int:
    norm_phone = normalize_phone(phone)
    if not norm_phone:
        raise ValueError(f"Virheellinen puhelinnumero: {phone!r}")
    with get_conn() as conn:
        cur = conn.execute(
            "INSERT INTO customers (name, phone, email, note) VALUES (?, ?, ?, ?)",
            (name.strip(), norm_phone, email.strip(), note.strip()),
        )
        customer_id = cur.lastrowid
        for gid in group_ids or []:
            conn.execute(
                "INSERT OR IGNORE INTO customer_groups (customer_id, group_id) VALUES (?, ?)",
                (customer_id, gid),
            )
        conn.commit()
        return customer_id


def update_customer(customer_id: int, name: str, phone: str, email: str, note: str, group_ids=None):
    norm_phone = normalize_phone(phone)
    if not norm_phone:
        raise ValueError(f"Virheellinen puhelinnumero: {phone!r}")
    with get_conn() as conn:
        conn.execute(
            "UPDATE customers SET name = ?, phone = ?, email = ?, note = ? WHERE id = ?",
            (name.strip(), norm_phone, email.strip(), note.strip(), customer_id),
        )
        conn.execute("DELETE FROM customer_groups WHERE customer_id = ?", (customer_id,))
        for gid in group_ids or []:
            conn.execute(
                "INSERT OR IGNORE INTO customer_groups (customer_id, group_id) VALUES (?, ?)",
                (customer_id, gid),
            )
        conn.commit()


def delete_customer(customer_id: int):
    with get_conn() as conn:
        conn.execute("DELETE FROM customers WHERE id = ?", (customer_id,))
        conn.commit()


# ---------------------------------------------------------------------------
# CSV-tuonti
# ---------------------------------------------------------------------------

# Tunnistetaan sarakeotsikot joustavasti (pieni/iso kirjain, muutama synonyymi)
COLUMN_ALIASES = {
    "name": ["nimi", "name"],
    "phone": ["puhelin", "puhelinnumero", "phone", "matkapuhelin"],
    "email": ["sahkoposti", "sähköposti", "email", "email-osoite"],
    "note": ["muistiinpano", "note", "lisatieto", "lisätieto"],
    "groups": ["ryhmat", "ryhmät", "ryhma", "ryhmä", "groups", "tagit"],
}


def _detect_columns(columns):
    lower_map = {str(c).strip().lower(): c for c in columns}
    mapping = {}
    for field, aliases in COLUMN_ALIASES.items():
        for alias in aliases:
            if alias in lower_map:
                mapping[field] = lower_map[alias]
                break
    return mapping


def import_customers_from_dataframe(df):
    """Tuo asiakkaat pandas DataFrame:sta.

    Palauttaa dictin: {"added": n, "updated": n, "errors": [(rivi, syy), ...]}
    """
    mapping = _detect_columns(df.columns)
    if "name" not in mapping or "phone" not in mapping:
        raise ValueError(
            "CSV:stä ei löytynyt pakollisia sarakkeita 'Nimi' ja 'Puhelin'. "
            f"Löydetyt sarakkeet: {list(df.columns)}"
        )

    added = 0
    updated = 0
    errors = []

    with get_conn() as conn:
        existing = {
            r["phone"]: r["id"]
            for r in conn.execute("SELECT id, phone FROM customers").fetchall()
        }

        for idx, row in df.iterrows():
            line_no = idx + 2  # otsikkorivi + 1-indeksointi
            name = str(row.get(mapping.get("name"), "")).strip()
            phone_raw = row.get(mapping.get("phone"), "")
            email = str(row.get(mapping.get("email"), "") or "").strip() if "email" in mapping else ""
            note = str(row.get(mapping.get("note"), "") or "").strip() if "note" in mapping else ""
            groups_raw = str(row.get(mapping.get("groups"), "") or "").strip() if "groups" in mapping else ""

            if not name or not str(phone_raw).strip():
                errors.append((line_no, "Nimi tai puhelin puuttuu"))
                continue

            phone = normalize_phone(phone_raw)
            if not phone:
                errors.append((line_no, f"Virheellinen puhelinnumero: {phone_raw!r}"))
                continue

            group_names = [g.strip() for g in re.split(r"[,/;]", groups_raw) if g.strip()]
            group_ids = [get_or_create_group(g) for g in group_names]

            if phone in existing:
                conn.execute(
                    "UPDATE customers SET name = ?, email = ?, note = ? WHERE id = ?",
                    (name, email, note, existing[phone]),
                )
                conn.execute("DELETE FROM customer_groups WHERE customer_id = ?", (existing[phone],))
                for gid in group_ids:
                    conn.execute(
                        "INSERT OR IGNORE INTO customer_groups (customer_id, group_id) VALUES (?, ?)",
                        (existing[phone], gid),
                    )
                updated += 1
            else:
                cur = conn.execute(
                    "INSERT INTO customers (name, phone, email, note) VALUES (?, ?, ?, ?)",
                    (name, phone, email, note),
                )
                new_id = cur.lastrowid
                existing[phone] = new_id
                for gid in group_ids:
                    conn.execute(
                        "INSERT OR IGNORE INTO customer_groups (customer_id, group_id) VALUES (?, ?)",
                        (new_id, gid),
                    )
                added += 1

        conn.commit()

    return {"added": added, "updated": updated, "errors": errors}


# ---------------------------------------------------------------------------
# Viestit ja viestihistoria
# ---------------------------------------------------------------------------

def create_message(body: str, group_names: str, recipients: list[dict]) -> int:
    """Luo uusi viesti ja sen vastaanottajarivit.

    recipients: lista dictejä {"customer_id", "name", "phone"}
    Palauttaa luodun viestin id:n.
    """
    with get_conn() as conn:
        cur = conn.execute(
            "INSERT INTO messages (body, group_names, recipient_count) VALUES (?, ?, ?)",
            (body, group_names, len(recipients)),
        )
        message_id = cur.lastrowid
        for r in recipients:
            conn.execute(
                """INSERT INTO message_recipients
                   (message_id, customer_id, name, phone, status)
                   VALUES (?, ?, ?, ?, 'odottaa')""",
                (message_id, r.get("customer_id"), r.get("name"), r.get("phone")),
            )
        conn.commit()
        return message_id


def update_recipient_status(recipient_id: int, status: str, provider_message_id: str = None, error: str = None):
    with get_conn() as conn:
        conn.execute(
            """UPDATE message_recipients
               SET status = ?, provider_message_id = COALESCE(?, provider_message_id),
                   error = ?, updated_at = datetime('now')
               WHERE id = ?""",
            (status, provider_message_id, error, recipient_id),
        )
        conn.commit()


def get_message_recipients(message_id: int):
    with get_conn() as conn:
        rows = conn.execute(
            "SELECT * FROM message_recipients WHERE message_id = ? ORDER BY name COLLATE NOCASE",
            (message_id,),
        ).fetchall()
        return [dict(r) for r in rows]


def list_messages():
    with get_conn() as conn:
        rows = conn.execute(
            """SELECT m.id, m.body, m.group_names, m.recipient_count, m.created_at,
                      SUM(CASE WHEN mr.status = 'lahetetty' THEN 1 ELSE 0 END) AS n_lahetetty,
                      SUM(CASE WHEN mr.status = 'toimitettu' THEN 1 ELSE 0 END) AS n_toimitettu,
                      SUM(CASE WHEN mr.status = 'virhe' THEN 1 ELSE 0 END) AS n_virhe,
                      SUM(CASE WHEN mr.status = 'odottaa' THEN 1 ELSE 0 END) AS n_odottaa
               FROM messages m
               LEFT JOIN message_recipients mr ON mr.message_id = m.id
               GROUP BY m.id
               ORDER BY m.created_at DESC"""
        ).fetchall()
        return [dict(r) for r in rows]


def get_stats() -> dict:
    """Yhteenveto lähetyksistä etusivua varten."""
    with get_conn() as conn:
        n_messages = conn.execute("SELECT COUNT(*) AS c FROM messages").fetchone()["c"]
        row = conn.execute(
            """SELECT
                   COUNT(*) AS n_recipients,
                   SUM(CASE WHEN status = 'toimitettu' THEN 1 ELSE 0 END) AS toimitettu,
                   SUM(CASE WHEN status = 'virhe' THEN 1 ELSE 0 END) AS virhe,
                   SUM(CASE WHEN status IN ('lahetetty', 'odottaa') THEN 1 ELSE 0 END) AS kesken
               FROM message_recipients"""
        ).fetchone()
        return {
            "n_messages": n_messages,
            "n_recipients": row["n_recipients"] or 0,
            "toimitettu": row["toimitettu"] or 0,
            "virhe": row["virhe"] or 0,
            "kesken": row["kesken"] or 0,
        }
