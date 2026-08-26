"""SQLite 저장소.

폴링할 때마다 같은 물건이 계속 딸려 온다. 이미 본 것인지 판정해서 **처음 본
것만** 알림 큐에 넣는 게 이 계층의 핵심이다. 판정 기준은 `Listing.dedupe_key`.

가격이 바뀐 경우(유찰로 최저가가 내려간 경우)는 새 물건은 아니지만 알릴
가치가 있어서, 값이 달라지면 다시 알림 대상으로 올린다.
"""

from __future__ import annotations

import json
import sqlite3
from dataclasses import asdict
from datetime import datetime, timezone
from pathlib import Path

from .models import FilterProfile, Listing, PropertyType, Source

SCHEMA = """
CREATE TABLE IF NOT EXISTS listings (
    dedupe_key      TEXT PRIMARY KEY,
    source          TEXT NOT NULL,
    payload         TEXT NOT NULL,
    effective_price INTEGER,
    first_seen_at   TEXT NOT NULL,
    last_seen_at    TEXT NOT NULL,
    notified_at     TEXT
);
CREATE INDEX IF NOT EXISTS idx_listings_source ON listings(source);
CREATE INDEX IF NOT EXISTS idx_listings_seen ON listings(first_seen_at DESC);
CREATE INDEX IF NOT EXISTS idx_listings_notified ON listings(notified_at);

CREATE TABLE IF NOT EXISTS filters (
    id      INTEGER PRIMARY KEY AUTOINCREMENT,
    payload TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS settings (
    key   TEXT PRIMARY KEY,
    value TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS listing_details (
    dedupe_key  TEXT PRIMARY KEY,
    payload     TEXT NOT NULL,
    fetched_at  TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS poll_log (
    id         INTEGER PRIMARY KEY AUTOINCREMENT,
    source     TEXT NOT NULL,
    started_at TEXT NOT NULL,
    ok         INTEGER NOT NULL,
    fetched    INTEGER NOT NULL DEFAULT 0,
    new_count  INTEGER NOT NULL DEFAULT 0,
    error      TEXT
);
"""


def _now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


class Store:
    def __init__(self, path: Path) -> None:
        self.path = path
        self.path.parent.mkdir(parents=True, exist_ok=True)
        with self._connect() as conn:
            conn.executescript(SCHEMA)

    def _connect(self) -> sqlite3.Connection:
        conn = sqlite3.connect(self.path, timeout=15)
        conn.row_factory = sqlite3.Row
        conn.execute("PRAGMA journal_mode=WAL")
        return conn

    # ---------- 물건 ----------

    def upsert(self, listing: Listing) -> bool:
        """저장하고 '알릴 만한 변화가 있었는지'를 돌려준다.

        처음 보는 물건이거나, 이미 아는 물건인데 유효가격이 내려갔으면 True.
        """
        payload = json.dumps(listing.to_dict(), ensure_ascii=False)
        price = listing.effective_price_krw
        now = _now()

        with self._connect() as conn:
            row = conn.execute(
                "SELECT effective_price, first_seen_at FROM listings WHERE dedupe_key = ?",
                (listing.dedupe_key,),
            ).fetchone()

            if row is None:
                conn.execute(
                    "INSERT INTO listings"
                    " (dedupe_key, source, payload, effective_price, first_seen_at, last_seen_at)"
                    " VALUES (?, ?, ?, ?, ?, ?)",
                    (listing.dedupe_key, listing.source.value, payload, price, now, now),
                )
                return True

            price_dropped = (
                price is not None
                and row["effective_price"] is not None
                and price < row["effective_price"]
            )
            conn.execute(
                "UPDATE listings SET payload = ?, effective_price = ?, last_seen_at = ?"
                + (", notified_at = NULL" if price_dropped else "")
                + " WHERE dedupe_key = ?",
                (payload, price, now, listing.dedupe_key),
            )
            return price_dropped

    def pending_notifications(self, limit: int = 50) -> list[dict]:
        """아직 알리지 않은 물건."""
        with self._connect() as conn:
            rows = conn.execute(
                "SELECT dedupe_key, payload FROM listings"
                " WHERE notified_at IS NULL ORDER BY first_seen_at DESC LIMIT ?",
                (limit,),
            ).fetchall()
        return [{"dedupe_key": r["dedupe_key"], **json.loads(r["payload"])} for r in rows]

    def mark_notified(self, dedupe_keys: list[str]) -> None:
        if not dedupe_keys:
            return
        now = _now()
        with self._connect() as conn:
            conn.executemany(
                "UPDATE listings SET notified_at = ? WHERE dedupe_key = ?",
                [(now, key) for key in dedupe_keys],
            )

    def listings(
        self,
        source: str | None = None,
        limit: int = 100,
        offset: int = 0,
    ) -> list[dict]:
        query = "SELECT payload, first_seen_at, notified_at FROM listings"
        params: list = []
        if source:
            query += " WHERE source = ?"
            params.append(source)
        query += " ORDER BY first_seen_at DESC LIMIT ? OFFSET ?"
        params += [limit, offset]

        with self._connect() as conn:
            rows = conn.execute(query, params).fetchall()
        return [
            {
                **json.loads(r["payload"]),
                "first_seen_at": r["first_seen_at"],
                "notified": r["notified_at"] is not None,
            }
            for r in rows
        ]

    def count(self) -> dict[str, int]:
        with self._connect() as conn:
            rows = conn.execute(
                "SELECT source, COUNT(*) AS n FROM listings GROUP BY source"
            ).fetchall()
        return {r["source"]: r["n"] for r in rows}

    def prune(self, keep_days: int = 90) -> int:
        """오래된 물건을 지운다. 작은 서버라 무한정 쌓아두지 않는다."""
        with self._connect() as conn:
            cursor = conn.execute(
                "DELETE FROM listings WHERE last_seen_at < datetime('now', ?)",
                (f"-{keep_days} days",),
            )
            return cursor.rowcount

    def drop_stale(self, source: str, hours: int = 36) -> int:
        """이번 수집에 안 잡힌 물건을 지운다.

        온비드는 '입찰진행중'만 조회하므로, 물건이 목록에서 사라졌다는 건
        마감됐다는 뜻이다. last_seen_at 이 갱신되지 않은 것을 걷어낸다.
        **수집이 성공한 직후에만 부를 것** - 실패한 폴링 뒤에 부르면
        멀쩡한 물건을 전부 지운다.
        """
        with self._connect() as conn:
            cursor = conn.execute(
                "DELETE FROM listings WHERE source = ?"
                " AND last_seen_at < datetime('now', ?)",
                (source, f"-{hours} hours"),
            )
            return cursor.rowcount

    # ---------- 물건 상세 ----------

    def get_detail(self, dedupe_key: str, max_age_days: int = 7) -> dict | None:
        """캐시된 상세. 오래되면 없는 것으로 친다.

        상세 API 는 일일 1,000회뿐이라 매번 부르면 안 되고, 그렇다고 영원히
        캐시하면 유찰로 최저가가 내려간 것을 놓친다.
        """
        with self._connect() as conn:
            row = conn.execute(
                "SELECT payload FROM listing_details"
                " WHERE dedupe_key = ? AND fetched_at > datetime('now', ?)",
                (dedupe_key, f"-{max_age_days} days"),
            ).fetchone()
        return json.loads(row["payload"]) if row else None

    def save_detail(self, dedupe_key: str, detail: dict) -> None:
        with self._connect() as conn:
            conn.execute(
                "INSERT INTO listing_details (dedupe_key, payload, fetched_at)"
                " VALUES (?, ?, ?)"
                " ON CONFLICT(dedupe_key) DO UPDATE SET"
                " payload = excluded.payload, fetched_at = excluded.fetched_at",
                (dedupe_key, json.dumps(detail, ensure_ascii=False), _now()),
            )

    def find_listing(self, dedupe_key: str) -> dict | None:
        with self._connect() as conn:
            row = conn.execute(
                "SELECT payload FROM listings WHERE dedupe_key = ?", (dedupe_key,)
            ).fetchone()
        return json.loads(row["payload"]) if row else None

    # ---------- 필터 ----------

    def save_filter(self, profile: FilterProfile) -> FilterProfile:
        payload = json.dumps(asdict(profile), ensure_ascii=False)
        with self._connect() as conn:
            if profile.id is None:
                cursor = conn.execute("INSERT INTO filters (payload) VALUES (?)", (payload,))
                profile.id = cursor.lastrowid
                conn.execute(
                    "UPDATE filters SET payload = ? WHERE id = ?",
                    (json.dumps(asdict(profile), ensure_ascii=False), profile.id),
                )
            else:
                conn.execute(
                    "UPDATE filters SET payload = ? WHERE id = ?", (payload, profile.id)
                )
        return profile

    def filters(self) -> list[FilterProfile]:
        with self._connect() as conn:
            rows = conn.execute("SELECT id, payload FROM filters ORDER BY id").fetchall()
        result = []
        for row in rows:
            data = json.loads(row["payload"])
            data["id"] = row["id"]
            result.append(FilterProfile(**data))
        return result

    def delete_filter(self, filter_id: int) -> bool:
        with self._connect() as conn:
            cursor = conn.execute("DELETE FROM filters WHERE id = ?", (filter_id,))
            return cursor.rowcount > 0

    # ---------- 설정 (차주 프로필 등) ----------

    def set_setting(self, key: str, value: dict) -> None:
        with self._connect() as conn:
            conn.execute(
                "INSERT INTO settings (key, value) VALUES (?, ?)"
                " ON CONFLICT(key) DO UPDATE SET value = excluded.value",
                (key, json.dumps(value, ensure_ascii=False)),
            )

    def get_setting(self, key: str) -> dict | None:
        with self._connect() as conn:
            row = conn.execute("SELECT value FROM settings WHERE key = ?", (key,)).fetchone()
        return json.loads(row["value"]) if row else None

    # ---------- 폴링 기록 ----------

    def log_poll(
        self,
        source: str,
        ok: bool,
        fetched: int = 0,
        new_count: int = 0,
        error: str | None = None,
    ) -> None:
        with self._connect() as conn:
            conn.execute(
                "INSERT INTO poll_log (source, started_at, ok, fetched, new_count, error)"
                " VALUES (?, ?, ?, ?, ?, ?)",
                (source, _now(), 1 if ok else 0, fetched, new_count, error),
            )
            # 기록이 무한히 쌓이지 않게 소스별 최근 200건만 남긴다.
            conn.execute(
                "DELETE FROM poll_log WHERE source = ? AND id NOT IN"
                " (SELECT id FROM poll_log WHERE source = ? ORDER BY id DESC LIMIT 200)",
                (source, source),
            )

    def poll_status(self) -> list[dict]:
        """소스별 마지막 폴링 결과. 조용히 죽은 어댑터를 찾는 용도."""
        with self._connect() as conn:
            rows = conn.execute(
                "SELECT source, started_at, ok, fetched, new_count, error FROM poll_log p"
                " WHERE id = (SELECT MAX(id) FROM poll_log WHERE source = p.source)"
                " ORDER BY source"
            ).fetchall()
        return [
            {
                "source": r["source"],
                "last_run": r["started_at"],
                "ok": bool(r["ok"]),
                "fetched": r["fetched"],
                "new": r["new_count"],
                "error": r["error"],
            }
            for r in rows
        ]


def listing_from_dict(data: dict) -> Listing:
    """저장된 payload를 다시 Listing으로. 계산 모듈에 넘길 때 쓴다."""
    data = dict(data)
    data.pop("effective_price_krw", None)
    data.pop("dedupe_key", None)
    data.pop("notified", None)
    data["source"] = Source(data["source"])
    data["property_type"] = PropertyType(data["property_type"])
    return Listing(**data)
