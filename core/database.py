"""SQLite 데이터베이스 — 스키마, 연결 관리, 쿼리 헬퍼."""

import sqlite3
import json
from contextlib import contextmanager
from pathlib import Path

from config import DB_PATH, DATA_DIR

# ────────────────────────────────────────
# 연결 관리
# ────────────────────────────────────────

def get_connection() -> sqlite3.Connection:
    """WAL 모드, row_factory 설정된 SQLite 연결 반환."""
    DATA_DIR.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(str(DB_PATH), check_same_thread=False)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA journal_mode=WAL")
    conn.execute("PRAGMA foreign_keys=ON")
    return conn


@contextmanager
def transaction(conn: sqlite3.Connection | None = None):
    """트랜잭션 컨텍스트 매니저. conn이 없으면 새로 생성."""
    own = conn is None
    if own:
        conn = get_connection()
    try:
        yield conn
        conn.commit()
    except Exception:
        conn.rollback()
        raise
    finally:
        if own:
            conn.close()


# ────────────────────────────────────────
# 스키마 생성
# ────────────────────────────────────────

_SCHEMA_SQL = """
CREATE TABLE IF NOT EXISTS uploaded_files (
    id              INTEGER PRIMARY KEY AUTOINCREMENT,
    filename        TEXT NOT NULL,
    file_hash       TEXT NOT NULL UNIQUE,
    year_month      TEXT NOT NULL,
    sheet_name_data TEXT NOT NULL,
    sheet_name_cost TEXT,
    total_cost      REAL,
    row_count       INTEGER NOT NULL,
    uploaded_at     TEXT DEFAULT (datetime('now','localtime'))
);

CREATE TABLE IF NOT EXISTS column_mappings (
    id              INTEGER PRIMARY KEY AUTOINCREMENT,
    mapping_name    TEXT NOT NULL DEFAULT 'default',
    column_key      TEXT NOT NULL,
    excel_column    TEXT NOT NULL,
    sheet_type      TEXT NOT NULL DEFAULT 'data',
    created_at      TEXT DEFAULT (datetime('now','localtime')),
    updated_at      TEXT DEFAULT (datetime('now','localtime')),
    UNIQUE(mapping_name, column_key)
);

CREATE TABLE IF NOT EXISTS repair_cases (
    id                  INTEGER PRIMARY KEY AUTOINCREMENT,
    file_id             INTEGER NOT NULL REFERENCES uploaded_files(id),
    row_number          INTEGER NOT NULL,
    year_month          TEXT NOT NULL,
    product_group       TEXT,
    product             TEXT,
    action_notes        TEXT,
    request_details     TEXT,
    judgment_type       TEXT,
    amount              REAL,
    extra_data          TEXT,
    created_at          TEXT DEFAULT (datetime('now','localtime'))
);
CREATE INDEX IF NOT EXISTS idx_cases_yearmonth ON repair_cases(year_month);
CREATE INDEX IF NOT EXISTS idx_cases_product   ON repair_cases(product_group);
CREATE INDEX IF NOT EXISTS idx_cases_judgment  ON repair_cases(judgment_type);

CREATE TABLE IF NOT EXISTS tag_dictionary (
    id              INTEGER PRIMARY KEY AUTOINCREMENT,
    standard_tag    TEXT NOT NULL UNIQUE,
    category        TEXT,
    is_active       INTEGER NOT NULL DEFAULT 1,
    created_at      TEXT DEFAULT (datetime('now','localtime')),
    updated_at      TEXT DEFAULT (datetime('now','localtime'))
);

CREATE TABLE IF NOT EXISTS tag_synonyms (
    id              INTEGER PRIMARY KEY AUTOINCREMENT,
    synonym         TEXT NOT NULL UNIQUE,
    tag_id          INTEGER NOT NULL REFERENCES tag_dictionary(id),
    created_at      TEXT DEFAULT (datetime('now','localtime'))
);

CREATE TABLE IF NOT EXISTS case_tags (
    id              INTEGER PRIMARY KEY AUTOINCREMENT,
    case_id         INTEGER NOT NULL REFERENCES repair_cases(id),
    tag_id          INTEGER NOT NULL REFERENCES tag_dictionary(id),
    source          TEXT NOT NULL,
    confidence      REAL,
    ai_raw_text     TEXT,
    is_final        INTEGER NOT NULL DEFAULT 0,
    created_at      TEXT DEFAULT (datetime('now','localtime')),
    confirmed_at    TEXT,
    UNIQUE(case_id, tag_id)
);
CREATE INDEX IF NOT EXISTS idx_casetags_case  ON case_tags(case_id);
CREATE INDEX IF NOT EXISTS idx_casetags_final ON case_tags(is_final);

CREATE TABLE IF NOT EXISTS tag_edit_history (
    id              INTEGER PRIMARY KEY AUTOINCREMENT,
    case_id         INTEGER NOT NULL REFERENCES repair_cases(id),
    old_tag_id      INTEGER REFERENCES tag_dictionary(id),
    new_tag_id      INTEGER NOT NULL REFERENCES tag_dictionary(id),
    action          TEXT NOT NULL,
    edited_at       TEXT DEFAULT (datetime('now','localtime'))
);

CREATE TABLE IF NOT EXISTS monthly_snapshots (
    id              INTEGER PRIMARY KEY AUTOINCREMENT,
    year_month      TEXT NOT NULL,
    snapshot_type   TEXT NOT NULL,
    data_json       TEXT NOT NULL,
    total_cost      REAL,
    total_cases     INTEGER,
    computed_at     TEXT DEFAULT (datetime('now','localtime')),
    UNIQUE(year_month, snapshot_type)
);

CREATE TABLE IF NOT EXISTS new_tag_candidates (
    id              INTEGER PRIMARY KEY AUTOINCREMENT,
    proposed_text   TEXT NOT NULL,
    similar_tag_id  INTEGER REFERENCES tag_dictionary(id),
    similarity_score REAL,
    case_id         INTEGER REFERENCES repair_cases(id),
    status          TEXT NOT NULL DEFAULT 'pending',
    created_at      TEXT DEFAULT (datetime('now','localtime')),
    resolved_at     TEXT
);
"""


def init_db(conn: sqlite3.Connection | None = None):
    """모든 테이블 생성 (존재하지 않을 때만)."""
    with transaction(conn) as c:
        c.executescript(_SCHEMA_SQL)


# ────────────────────────────────────────
# 파일 메타 관련
# ────────────────────────────────────────

def file_exists(conn: sqlite3.Connection, file_hash: str) -> bool:
    row = conn.execute(
        "SELECT 1 FROM uploaded_files WHERE file_hash = ?", (file_hash,)
    ).fetchone()
    return row is not None


def insert_file_record(conn: sqlite3.Connection, **kwargs) -> int:
    cur = conn.execute(
        """INSERT INTO uploaded_files
           (filename, file_hash, year_month, sheet_name_data, sheet_name_cost, total_cost, row_count)
           VALUES (:filename, :file_hash, :year_month, :sheet_name_data, :sheet_name_cost, :total_cost, :row_count)""",
        kwargs,
    )
    return cur.lastrowid


# ────────────────────────────────────────
# 케이스 관련
# ────────────────────────────────────────

def insert_cases_bulk(conn: sqlite3.Connection, file_id: int, cases: list[dict]):
    rows = []
    for c in cases:
        extra = {k: v for k, v in c.items()
                 if k not in ("row_number", "year_month", "product_group", "product",
                              "action_notes", "request_details", "judgment_type", "amount")}
        rows.append((
            file_id,
            c["row_number"],
            c["year_month"],
            c.get("product_group"),
            c.get("product"),
            c.get("action_notes"),
            c.get("request_details"),
            c.get("judgment_type"),
            c.get("amount"),
            json.dumps(extra, ensure_ascii=False) if extra else None,
        ))
    conn.executemany(
        """INSERT INTO repair_cases
           (file_id, row_number, year_month, product_group, product,
            action_notes, request_details, judgment_type, amount, extra_data)
           VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
        rows,
    )


def get_cases_by_month(conn: sqlite3.Connection, year_month: str) -> list[dict]:
    rows = conn.execute(
        "SELECT * FROM repair_cases WHERE year_month = ? ORDER BY row_number",
        (year_month,),
    ).fetchall()
    return [dict(r) for r in rows]


def get_untagged_cases(conn: sqlite3.Connection, year_month: str) -> list[dict]:
    rows = conn.execute(
        """SELECT rc.* FROM repair_cases rc
           WHERE rc.year_month = ?
             AND rc.id NOT IN (
                 SELECT case_id FROM case_tags WHERE is_final = 1
             )
           ORDER BY rc.row_number""",
        (year_month,),
    ).fetchall()
    return [dict(r) for r in rows]


def get_uploaded_months(conn: sqlite3.Connection) -> list[str]:
    rows = conn.execute(
        "SELECT DISTINCT year_month FROM uploaded_files ORDER BY year_month DESC"
    ).fetchall()
    return [r["year_month"] for r in rows]


# ────────────────────────────────────────
# 컬럼 매핑
# ────────────────────────────────────────

def save_column_mapping(conn: sqlite3.Connection, mapping: dict[str, str],
                        mapping_name: str = "default"):
    for key, col in mapping.items():
        conn.execute(
            """INSERT INTO column_mappings (mapping_name, column_key, excel_column)
               VALUES (?, ?, ?)
               ON CONFLICT(mapping_name, column_key)
               DO UPDATE SET excel_column = excluded.excel_column,
                             updated_at = datetime('now','localtime')""",
            (mapping_name, key, col),
        )


def load_column_mapping(conn: sqlite3.Connection,
                        mapping_name: str = "default") -> dict[str, str]:
    rows = conn.execute(
        "SELECT column_key, excel_column FROM column_mappings WHERE mapping_name = ?",
        (mapping_name,),
    ).fetchall()
    return {r["column_key"]: r["excel_column"] for r in rows}


# ────────────────────────────────────────
# 태그 사전
# ────────────────────────────────────────

def get_all_tags(conn: sqlite3.Connection, active_only: bool = True) -> list[dict]:
    sql = "SELECT * FROM tag_dictionary"
    if active_only:
        sql += " WHERE is_active = 1"
    sql += " ORDER BY standard_tag"
    return [dict(r) for r in conn.execute(sql).fetchall()]


def add_tag(conn: sqlite3.Connection, standard_tag: str, category: str | None = None) -> int:
    cur = conn.execute(
        "INSERT INTO tag_dictionary (standard_tag, category) VALUES (?, ?)",
        (standard_tag, category),
    )
    return cur.lastrowid


def add_synonym(conn: sqlite3.Connection, synonym: str, tag_id: int):
    conn.execute(
        "INSERT OR IGNORE INTO tag_synonyms (synonym, tag_id) VALUES (?, ?)",
        (synonym, tag_id),
    )


def get_synonyms(conn: sqlite3.Connection, tag_id: int) -> list[str]:
    rows = conn.execute(
        "SELECT synonym FROM tag_synonyms WHERE tag_id = ?", (tag_id,)
    ).fetchall()
    return [r["synonym"] for r in rows]


def get_all_synonyms(conn: sqlite3.Connection) -> dict[str, int]:
    rows = conn.execute("SELECT synonym, tag_id FROM tag_synonyms").fetchall()
    return {r["synonym"]: r["tag_id"] for r in rows}


# ────────────────────────────────────────
# 케이스 태그
# ────────────────────────────────────────

def upsert_case_tag(conn: sqlite3.Connection, case_id: int, tag_id: int,
                    source: str, confidence: float | None = None,
                    ai_raw_text: str | None = None, is_final: bool = False):
    conn.execute(
        """INSERT INTO case_tags (case_id, tag_id, source, confidence, ai_raw_text, is_final)
           VALUES (?, ?, ?, ?, ?, ?)
           ON CONFLICT(case_id, tag_id)
           DO UPDATE SET source = excluded.source,
                         confidence = excluded.confidence,
                         ai_raw_text = excluded.ai_raw_text,
                         is_final = excluded.is_final,
                         confirmed_at = CASE WHEN excluded.is_final = 1
                                             THEN datetime('now','localtime')
                                             ELSE confirmed_at END""",
        (case_id, tag_id, source, confidence, ai_raw_text, int(is_final)),
    )


def get_case_tags(conn: sqlite3.Connection, case_id: int) -> list[dict]:
    rows = conn.execute(
        """SELECT ct.*, td.standard_tag, td.category
           FROM case_tags ct
           JOIN tag_dictionary td ON ct.tag_id = td.id
           WHERE ct.case_id = ?
           ORDER BY ct.confidence DESC""",
        (case_id,),
    ).fetchall()
    return [dict(r) for r in rows]


def get_tagged_cases_by_month(conn: sqlite3.Connection, year_month: str) -> list[dict]:
    rows = conn.execute(
        """SELECT rc.*, ct.tag_id, td.standard_tag, td.category,
                  ct.confidence, ct.source, ct.is_final
           FROM repair_cases rc
           JOIN case_tags ct ON rc.id = ct.case_id
           JOIN tag_dictionary td ON ct.tag_id = td.id
           WHERE rc.year_month = ?
           ORDER BY rc.row_number""",
        (year_month,),
    ).fetchall()
    return [dict(r) for r in rows]


# ────────────────────────────────────────
# 스냅샷
# ────────────────────────────────────────

def save_snapshot(conn: sqlite3.Connection, year_month: str,
                  snapshot_type: str, data: dict,
                  total_cost: float | None = None, total_cases: int | None = None):
    conn.execute(
        """INSERT INTO monthly_snapshots (year_month, snapshot_type, data_json, total_cost, total_cases)
           VALUES (?, ?, ?, ?, ?)
           ON CONFLICT(year_month, snapshot_type)
           DO UPDATE SET data_json = excluded.data_json,
                         total_cost = excluded.total_cost,
                         total_cases = excluded.total_cases,
                         computed_at = datetime('now','localtime')""",
        (year_month, snapshot_type, json.dumps(data, ensure_ascii=False), total_cost, total_cases),
    )


def load_snapshot(conn: sqlite3.Connection, year_month: str,
                  snapshot_type: str) -> dict | None:
    row = conn.execute(
        "SELECT data_json FROM monthly_snapshots WHERE year_month = ? AND snapshot_type = ?",
        (year_month, snapshot_type),
    ).fetchone()
    if row:
        return json.loads(row["data_json"])
    return None


# ────────────────────────────────────────
# 신규 태그 후보
# ────────────────────────────────────────

def add_new_tag_candidate(conn: sqlite3.Connection, proposed_text: str,
                          case_id: int | None = None,
                          similar_tag_id: int | None = None,
                          similarity_score: float | None = None):
    conn.execute(
        """INSERT INTO new_tag_candidates
           (proposed_text, case_id, similar_tag_id, similarity_score)
           VALUES (?, ?, ?, ?)""",
        (proposed_text, case_id, similar_tag_id, similarity_score),
    )


def get_pending_candidates(conn: sqlite3.Connection) -> list[dict]:
    rows = conn.execute(
        """SELECT ntc.*, td.standard_tag AS similar_tag_name
           FROM new_tag_candidates ntc
           LEFT JOIN tag_dictionary td ON ntc.similar_tag_id = td.id
           WHERE ntc.status = 'pending'
           ORDER BY ntc.created_at DESC"""
    ).fetchall()
    return [dict(r) for r in rows]


# ────────────────────────────────────────
# 편집 이력
# ────────────────────────────────────────

def record_edit(conn: sqlite3.Connection, case_id: int,
                new_tag_id: int, action: str,
                old_tag_id: int | None = None):
    conn.execute(
        """INSERT INTO tag_edit_history (case_id, old_tag_id, new_tag_id, action)
           VALUES (?, ?, ?, ?)""",
        (case_id, old_tag_id, new_tag_id, action),
    )
