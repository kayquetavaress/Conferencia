import hashlib
import hmac
import os
import secrets
import sqlite3
from contextlib import contextmanager
from datetime import datetime
from pathlib import Path


INITIAL_MATERIALS = (
    ("4000000416", "COMPOSTO PÓ PVC BRANCO TUBO ESGOTO", "PVC"),
    ("4000000417", "COMPOSTO PÓ PVC MARROM TUBO SOLDÁVEL", "PVC"),
    ("4000002859", "COMPOSTO PÓ ROSCAVEL", "PVC"),
    ("4000000418", "COMPOSTO PÓ CORRUGADO LEVE", "PVC"),
    ("4000001792", "COMPOSTO PÓ CORRUGADO REFORÇADO", "PVC"),
    ("4000001331", "COMPOSTO MOÍDO PVC BRANCO", "PVC"),
    ("4000000628", "COMPOSTO PÓ PVC PRETO", "PVC"),
    ("4000001395", "COMPOSTO MOÍDO PVC TELHA", "PVC"),
    ("4000001330", "COMPOSTO MOÍDO PVC MARROM", "PVC"),
    ("4000001733", "COMPOSTO PÓ TELHA INCOLOR", "PVC"),
    ("4000001821", "COMPOSTO PÓ PVC BEGE TUBO R", "PVC"),
)
HASH_ITERATIONS = 310_000


def data_directory():
    base = os.environ.get("LOCALAPPDATA")
    if base:
        return Path(base) / "Fortlev" / "Inventario"
    return Path.home() / ".local" / "share" / "fortlev" / "inventario"


def default_database_path():
    return data_directory() / "inventario.db"


@contextmanager
def connect(db_path=None):
    path = Path(db_path) if db_path else default_database_path()
    path.parent.mkdir(parents=True, exist_ok=True)
    connection = sqlite3.connect(path, timeout=15)
    connection.row_factory = sqlite3.Row
    connection.execute("PRAGMA foreign_keys = ON")
    connection.execute("PRAGMA busy_timeout = 15000")
    try:
        with connection:
            yield connection
    finally:
        connection.close()


def initialize_database(db_path=None):
    with connect(db_path) as connection:
        connection.execute("PRAGMA journal_mode = WAL")
        connection.executescript(
            """
            CREATE TABLE IF NOT EXISTS materials (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                code TEXT NOT NULL UNIQUE,
                description TEXT NOT NULL,
                category TEXT NOT NULL,
                active INTEGER NOT NULL DEFAULT 1 CHECK (active IN (0, 1))
            );

            CREATE TABLE IF NOT EXISTS bags (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                material_code TEXT NOT NULL,
                label_id TEXT,
                material_description TEXT NOT NULL,
                category TEXT NOT NULL,
                weight TEXT NOT NULL,
                record_date TEXT NOT NULL,
                record_time TEXT NOT NULL,
                recorded_at TEXT NOT NULL
            );

            CREATE INDEX IF NOT EXISTS idx_bags_recorded_at
                ON bags(recorded_at);
            CREATE INDEX IF NOT EXISTS idx_bags_material_code
                ON bags(material_code);

            CREATE TABLE IF NOT EXISTS settings (
                key TEXT PRIMARY KEY,
                value TEXT NOT NULL
            );
            """
        )
        bag_columns = {
            row["name"] for row in connection.execute("PRAGMA table_info(bags)")
        }
        if "label_id" not in bag_columns:
            connection.execute("ALTER TABLE bags ADD COLUMN label_id TEXT")
        connection.execute(
            """
            CREATE UNIQUE INDEX IF NOT EXISTS idx_bags_label_id
            ON bags(UPPER(TRIM(label_id)))
            WHERE label_id IS NOT NULL AND TRIM(label_id) <> ''
            """
        )
        connection.executemany(
            """
            INSERT OR IGNORE INTO materials (code, description, category)
            VALUES (?, ?, ?)
            """,
            INITIAL_MATERIALS,
        )
        connection.execute(
            """
            UPDATE materials
            SET description = ?
            WHERE code = ? AND description = ?
            """,
            (
                "COMPOSTO PÓ PVC BEGE TUBO R",
                "4000001821",
                "COMPOSTO PÓ PVC BEGE TUBO SERIE R",
            ),
        )


def find_material(code, db_path=None):
    with connect(db_path) as connection:
        row = connection.execute(
            """
            SELECT id, code, description, category, active
            FROM materials WHERE code = ?
            """,
            (str(code).strip(),),
        ).fetchone()
    return dict(row) if row else None


def list_materials(db_path=None):
    with connect(db_path) as connection:
        rows = connection.execute(
            """
            SELECT id, code, description, category, active
            FROM materials ORDER BY code
            """
        ).fetchall()
    return [dict(row) for row in rows]


def save_material(code, description, category, active=True, material_id=None, db_path=None):
    code = str(code).strip()
    description = str(description).strip().upper()
    category = str(category).strip().upper()
    if not code or not description or not category:
        raise ValueError("Preencha o código, a descrição e a categoria.")

    with connect(db_path) as connection:
        if material_id is None:
            cursor = connection.execute(
                """
                INSERT INTO materials (code, description, category, active)
                VALUES (?, ?, ?, ?)
                """,
                (code, description, category, int(active)),
            )
            return cursor.lastrowid
        connection.execute(
            """
            UPDATE materials
            SET code = ?, description = ?, category = ?, active = ?
            WHERE id = ?
            """,
            (code, description, category, int(active), int(material_id)),
        )
        return int(material_id)


def set_material_active(material_id, active, db_path=None):
    with connect(db_path) as connection:
        cursor = connection.execute(
            "UPDATE materials SET active = ? WHERE id = ?",
            (int(active), int(material_id)),
        )
        if cursor.rowcount != 1:
            raise ValueError("O material selecionado não foi encontrado.")


def set_admin_password(password, db_path=None):
    if len(password) < 8:
        raise ValueError("A senha administrativa deve ter pelo menos 8 caracteres.")
    salt = secrets.token_bytes(16)
    password_hash = hashlib.pbkdf2_hmac(
        "sha256", password.encode("utf-8"), salt, HASH_ITERATIONS
    ).hex()
    with connect(db_path) as connection:
        connection.executemany(
            "INSERT OR REPLACE INTO settings (key, value) VALUES (?, ?)",
            (("admin_salt", salt.hex()), ("admin_hash", password_hash)),
        )


def has_admin_password(db_path=None):
    with connect(db_path) as connection:
        row = connection.execute(
            "SELECT value FROM settings WHERE key = 'admin_hash'"
        ).fetchone()
    return row is not None


def verify_admin_password(password, db_path=None):
    with connect(db_path) as connection:
        values = {
            row["key"]: row["value"]
            for row in connection.execute(
                """
                SELECT key, value FROM settings
                WHERE key IN ('admin_salt', 'admin_hash')
                """
            )
        }
    if "admin_salt" not in values or "admin_hash" not in values:
        return False
    actual = hashlib.pbkdf2_hmac(
        "sha256",
        str(password).encode("utf-8"),
        bytes.fromhex(values["admin_salt"]),
        HASH_ITERATIONS,
    ).hex()
    return hmac.compare_digest(actual, values["admin_hash"])


def insert_bag(material, weight, moment, label_id, db_path=None):
    label_id = str(label_id or "").strip().upper()
    if not label_id:
        raise ValueError("ID DA ETIQUETA OBRIGATÓRIO.")
    try:
        with connect(db_path) as connection:
            cursor = connection.execute(
                """
                INSERT INTO bags (
                    material_code, label_id, material_description, category, weight,
                    record_date, record_time, recorded_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    material["code"],
                    label_id,
                    material["description"],
                    material["category"],
                    str(weight),
                    moment.strftime("%Y-%m-%d"),
                    moment.strftime("%H:%M:%S"),
                    moment.isoformat(timespec="seconds"),
                ),
            )
            bag_id = cursor.lastrowid
    except sqlite3.IntegrityError as error:
        if label_id_is_registered(label_id, db_path):
            raise ValueError(
                f"ETIQUETA JÁ REGISTRADA. ID: {label_id}."
            ) from error
        raise
    return int(bag_id)


def label_id_is_registered(label_id, db_path=None):
    normalized_id = str(label_id or "").strip().upper()
    if not normalized_id:
        return False
    with connect(db_path) as connection:
        row = connection.execute(
            """
            SELECT 1 FROM bags
            WHERE UPPER(TRIM(label_id)) = ?
            LIMIT 1
            """,
            (normalized_id,),
        ).fetchone()
    return row is not None


def query_bags(start_date=None, end_date=None, search="", db_path=None):
    clauses = []
    parameters = []
    if start_date:
        clauses.append("record_date >= ?")
        parameters.append(start_date)
    if end_date:
        clauses.append("record_date <= ?")
        parameters.append(end_date)
    if search:
        clauses.append(
            "(material_code LIKE ? OR material_description LIKE ? OR label_id LIKE ?)"
        )
        pattern = "%" + search.strip() + "%"
        parameters.extend((pattern, pattern, pattern))
    where = (" WHERE " + " AND ".join(clauses)) if clauses else ""
    with connect(db_path) as connection:
        rows = connection.execute(
            """
            SELECT id, material_code, label_id, material_description, category,
                   weight, record_date, record_time, recorded_at
            FROM bags
            """
            + where
            + " ORDER BY recorded_at DESC, id DESC",
            parameters,
        ).fetchall()
    return [dict(row) for row in rows]


def delete_bag(bag_id, db_path=None):
    try:
        bag_id = int(bag_id)
    except (TypeError, ValueError) as error:
        raise ValueError("Selecione um número de registro válido.") from error
    if bag_id <= 0:
        raise ValueError("Selecione um número de registro válido.")

    with connect(db_path) as connection:
        cursor = connection.execute("DELETE FROM bags WHERE id = ?", (bag_id,))
        if cursor.rowcount != 1:
            raise ValueError("O registro selecionado não foi encontrado.")


def create_backup(destination, db_path=None):
    source_path = Path(db_path) if db_path else default_database_path()
    destination = Path(destination)
    destination.parent.mkdir(parents=True, exist_ok=True)
    with connect(source_path) as source:
        target = sqlite3.connect(destination)
        try:
            source.backup(target)
        finally:
            target.close()
    return destination


def restore_backup(source_path, db_path=None):
    source_path = Path(source_path).resolve()
    target_path = Path(db_path).resolve() if db_path else default_database_path().resolve()
    if source_path == target_path:
        raise ValueError("Selecione um arquivo de backup diferente do banco atual.")
    if not source_path.is_file():
        raise FileNotFoundError(f"Arquivo de backup não encontrado: {source_path}")

    source = sqlite3.connect(source_path, timeout=15)
    try:
        integrity = source.execute("PRAGMA integrity_check").fetchone()[0]
        if integrity != "ok":
            raise sqlite3.DatabaseError(f"O backup não passou na verificação: {integrity}")
        tables = {
            row[0]
            for row in source.execute(
                "SELECT name FROM sqlite_master WHERE type = 'table'"
            )
        }
        if not {"materials", "bags", "settings"}.issubset(tables):
            raise sqlite3.DatabaseError("O arquivo não é um backup válido do INVENTÁRIO.")

        had_target = target_path.exists()
        safety_copy = None
        if had_target:
            safety_directory = target_path.parent / "backups"
            safety_name = f"antes_restauracao_{datetime.now().strftime('%Y%m%d_%H%M%S')}.db"
            safety_copy = safety_directory / safety_name
            create_backup(safety_copy, target_path)

        with connect(target_path) as target:
            source.backup(target)
    finally:
        source.close()
    return safety_copy
