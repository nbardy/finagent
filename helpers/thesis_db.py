from __future__ import annotations

import hashlib
import sqlite3
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


REPO_ROOT = Path(__file__).resolve().parents[1]
DEFAULT_DB_PATH = REPO_ROOT / "config" / "thesis_registry.db"
MIN_REASON_LENGTH = 24


@dataclass(frozen=True)
class ThesisRecord:
    thesis_id: str
    symbol: str
    sec_type: str
    expiry: str
    strike: float
    right: str
    strategy: str
    intent: str
    reason: str
    order_ref: str
    status: str
    created_at: str
    updated_at: str
    source_file: str | None


def _utc_now() -> datetime:
    return datetime.now(timezone.utc)


def _timestamp(now: datetime | None = None) -> str:
    current = now or _utc_now()
    return current.isoformat(timespec="seconds")


def _connect(db_path: str | Path | None = None) -> sqlite3.Connection:
    path = Path(db_path) if db_path else DEFAULT_DB_PATH
    path.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(path)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON")
    return conn


def ensure_schema(db_path: str | Path | None = None) -> Path:
    path = Path(db_path) if db_path else DEFAULT_DB_PATH
    with _connect(path) as conn:
        conn.executescript(
            """
            CREATE TABLE IF NOT EXISTS theses (
                thesis_id TEXT PRIMARY KEY,
                symbol TEXT NOT NULL,
                sec_type TEXT NOT NULL,
                expiry TEXT NOT NULL DEFAULT '',
                strike REAL NOT NULL DEFAULT 0,
                right TEXT NOT NULL DEFAULT '',
                strategy TEXT NOT NULL DEFAULT '',
                intent TEXT NOT NULL DEFAULT '',
                reason TEXT NOT NULL,
                order_ref TEXT NOT NULL,
                status TEXT NOT NULL DEFAULT 'active',
                created_at TEXT NOT NULL,
                updated_at TEXT NOT NULL,
                source_file TEXT
            );

            CREATE TABLE IF NOT EXISTS order_events (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                thesis_id TEXT NOT NULL,
                order_ref TEXT NOT NULL,
                perm_id INTEGER,
                order_id INTEGER,
                symbol TEXT NOT NULL,
                sec_type TEXT NOT NULL,
                expiry TEXT NOT NULL DEFAULT '',
                strike REAL NOT NULL DEFAULT 0,
                right TEXT NOT NULL DEFAULT '',
                action TEXT NOT NULL DEFAULT '',
                quantity INTEGER NOT NULL DEFAULT 0,
                submitted_at TEXT NOT NULL,
                source_file TEXT,
                FOREIGN KEY (thesis_id) REFERENCES theses(thesis_id)
            );

            CREATE INDEX IF NOT EXISTS idx_theses_instrument
                ON theses(symbol, sec_type, expiry, strike, right, updated_at DESC);

            CREATE INDEX IF NOT EXISTS idx_order_events_perm_id
                ON order_events(perm_id);

            CREATE INDEX IF NOT EXISTS idx_order_events_order_ref
                ON order_events(order_ref);

            CREATE INDEX IF NOT EXISTS idx_order_events_instrument
                ON order_events(symbol, sec_type, expiry, strike, right, submitted_at DESC);
            """
        )
    return path


def normalize_reason(reason: str) -> str:
    normalized = " ".join(reason.strip().split())
    if len(normalized) < MIN_REASON_LENGTH:
        raise ValueError(
            f"Trade rationale must be at least {MIN_REASON_LENGTH} characters of descriptive text."
        )
    return normalized


def normalize_instrument(
    *,
    symbol: str,
    sec_type: str,
    expiry: str = "",
    strike: float = 0.0,
    right: str = "",
) -> dict[str, Any]:
    return {
        "symbol": symbol.strip().upper(),
        "sec_type": sec_type.strip().upper(),
        "expiry": expiry.strip(),
        "strike": float(strike or 0.0),
        "right": right.strip().upper(),
    }


def make_thesis_id(
    *,
    symbol: str,
    sec_type: str,
    reason: str,
    now: datetime | None = None,
) -> str:
    current = now or _utc_now()
    digest = hashlib.sha1(f"{symbol}|{sec_type}|{reason}".encode("utf-8")).hexdigest()[:8]
    return f"th-{current.strftime('%Y%m%d-%H%M%S')}-{symbol.lower()}-{digest}"


def build_order_ref(thesis_id: str, symbol: str, base_order_ref: str | None = None) -> str:
    suffix = thesis_id.split("-")[-1]
    symbol_part = symbol.strip().upper()[:6]
    if base_order_ref:
        base = base_order_ref.strip().replace(" ", "_")
        return f"{base}|th:{symbol_part}:{suffix}"[:40]
    return f"th:{symbol_part}:{suffix}"[:40]


def upsert_thesis(
    *,
    symbol: str,
    sec_type: str,
    reason: str,
    strategy: str = "",
    intent: str = "",
    expiry: str = "",
    strike: float = 0.0,
    right: str = "",
    thesis_id: str | None = None,
    base_order_ref: str | None = None,
    source_file: str | None = None,
    db_path: str | Path | None = None,
) -> ThesisRecord:
    ensure_schema(db_path)
    instrument = normalize_instrument(
        symbol=symbol,
        sec_type=sec_type,
        expiry=expiry,
        strike=strike,
        right=right,
    )
    normalized_reason = normalize_reason(reason)
    now_text = _timestamp()
    final_thesis_id = thesis_id or make_thesis_id(
        symbol=instrument["symbol"],
        sec_type=instrument["sec_type"],
        reason=normalized_reason,
    )
    order_ref = build_order_ref(final_thesis_id, instrument["symbol"], base_order_ref)

    with _connect(db_path) as conn:
        conn.execute(
            """
            INSERT INTO theses (
                thesis_id, symbol, sec_type, expiry, strike, right,
                strategy, intent, reason, order_ref, status,
                created_at, updated_at, source_file
            )
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, 'active', ?, ?, ?)
            ON CONFLICT(thesis_id) DO UPDATE SET
                strategy=excluded.strategy,
                intent=excluded.intent,
                reason=excluded.reason,
                order_ref=excluded.order_ref,
                updated_at=excluded.updated_at,
                source_file=excluded.source_file
            """,
            (
                final_thesis_id,
                instrument["symbol"],
                instrument["sec_type"],
                instrument["expiry"],
                instrument["strike"],
                instrument["right"],
                strategy,
                intent,
                normalized_reason,
                order_ref,
                now_text,
                now_text,
                source_file,
            ),
        )
        row = conn.execute(
            "SELECT * FROM theses WHERE thesis_id = ?",
            (final_thesis_id,),
        ).fetchone()
    return ThesisRecord(**dict(row))


def record_order_event(
    *,
    thesis_id: str,
    order_ref: str,
    symbol: str,
    sec_type: str,
    action: str,
    quantity: int,
    expiry: str = "",
    strike: float = 0.0,
    right: str = "",
    perm_id: int | None = None,
    order_id: int | None = None,
    source_file: str | None = None,
    db_path: str | Path | None = None,
) -> None:
    ensure_schema(db_path)
    instrument = normalize_instrument(
        symbol=symbol,
        sec_type=sec_type,
        expiry=expiry,
        strike=strike,
        right=right,
    )
    with _connect(db_path) as conn:
        conn.execute(
            """
            INSERT INTO order_events (
                thesis_id, order_ref, perm_id, order_id,
                symbol, sec_type, expiry, strike, right,
                action, quantity, submitted_at, source_file
            )
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                thesis_id,
                order_ref,
                perm_id,
                order_id,
                instrument["symbol"],
                instrument["sec_type"],
                instrument["expiry"],
                instrument["strike"],
                instrument["right"],
                action,
                quantity,
                _timestamp(),
                source_file,
            ),
        )


def _row_to_dict(row: sqlite3.Row | None) -> dict[str, Any] | None:
    return dict(row) if row is not None else None


def find_thesis_for_order(
    *,
    perm_id: int | None = None,
    order_ref: str | None = None,
    symbol: str,
    sec_type: str,
    expiry: str = "",
    strike: float = 0.0,
    right: str = "",
    db_path: str | Path | None = None,
) -> dict[str, Any] | None:
    ensure_schema(db_path)
    instrument = normalize_instrument(
        symbol=symbol,
        sec_type=sec_type,
        expiry=expiry,
        strike=strike,
        right=right,
    )
    with _connect(db_path) as conn:
        if perm_id:
            row = conn.execute(
                """
                SELECT t.*
                FROM order_events oe
                JOIN theses t ON t.thesis_id = oe.thesis_id
                WHERE oe.perm_id = ?
                ORDER BY oe.id DESC
                LIMIT 1
                """,
                (perm_id,),
            ).fetchone()
            if row is not None:
                return _row_to_dict(row)

        if order_ref:
            row = conn.execute(
                """
                SELECT t.*
                FROM theses t
                WHERE t.order_ref = ?
                ORDER BY t.updated_at DESC
                LIMIT 1
                """,
                (order_ref,),
            ).fetchone()
            if row is not None:
                return _row_to_dict(row)

        row = conn.execute(
            """
            SELECT *
            FROM theses
            WHERE symbol = ?
              AND sec_type = ?
              AND expiry = ?
              AND strike = ?
              AND right = ?
              AND status = 'active'
            ORDER BY updated_at DESC
            LIMIT 1
            """,
            (
                instrument["symbol"],
                instrument["sec_type"],
                instrument["expiry"],
                instrument["strike"],
                instrument["right"],
            ),
        ).fetchone()
        return _row_to_dict(row)


def find_thesis_for_position(
    *,
    symbol: str,
    sec_type: str,
    expiry: str = "",
    strike: float = 0.0,
    right: str = "",
    db_path: str | Path | None = None,
) -> dict[str, Any] | None:
    return find_thesis_for_order(
        symbol=symbol,
        sec_type=sec_type,
        expiry=expiry,
        strike=strike,
        right=right,
        db_path=db_path,
    )
