"""SQLite 저장소.

폴링할 때마다 같은 물건이 계속 딸려 온다. 이미 본 것인지 판정해서 **처음 본
것만** 알림 큐에 넣는 게 이 계층의 핵심이다. 판정 기준은 `Listing.dedupe_key`.

가격이 바뀐 경우(유찰로 최저가가 내려간 경우)는 새 물건은 아니지만 알릴
가치가 있어서, 값이 달라지면 다시 알림 대상으로 올린다.
"""

from __future__ import annotations

import json
import sqlite3
from dataclasses import asdict, fields
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
CREATE INDEX IF NOT EXISTS idx_listings_price ON listings(effective_price);

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

-- 주소 -> 좌표 캐시. 같은 건물의 여러 호실이 한 지번을 공유하므로
-- 정제한 주소를 키로 둔다. lat 이 NULL 이면 '찾아봤지만 없었다'는 뜻이고,
-- 그것도 캐시해야 못 찾는 주소를 매번 다시 묻지 않는다.
CREATE TABLE IF NOT EXISTS geocode (
    address_key TEXT PRIMARY KEY,
    lat         REAL,
    lon         REAL,
    tried_at    TEXT NOT NULL
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
        sources: list[str] | None = None,
        min_price: int | None = None,
        max_price: int | None = None,
        not_expired_at: str | None = None,
    ) -> list[dict]:
        """물건 목록.

        가격·소스는 SQL 에서 먼저 거른다. 수집 범위를 넓히면서 1.5만 건이
        됐는데, 전부 파이썬으로 올려 json 을 풀어 비교하면 작은 VM 에서
        요청마다 몇 초가 걸린다. 인덱스가 있는 컬럼으로 먼저 줄인다.
        """
        clauses: list[str] = []
        params: list = []
        if source:
            clauses.append("source = ?")
            params.append(source)
        elif sources:
            clauses.append(f"source IN ({','.join('?' * len(sources))})")
            params += sources
        if min_price is not None:
            clauses.append("(effective_price IS NULL OR effective_price >= ?)")
            params.append(min_price)
        if max_price is not None:
            clauses.append("(effective_price IS NULL OR effective_price <= ?)")
            params.append(max_price)
        if not_expired_at is not None:
            # 마감 판정도 SQL 에서 한다. 파이썬으로 올려 세면 스캔 한도에
            # 걸려 '유효 6000건' 같은 잘린 숫자가 총계로 나간다.
            clauses.append(
                "(json_extract(payload,'$.deadline') IS NULL"
                " OR substr(json_extract(payload,'$.deadline'),1,16) >= ?)"
            )
            params.append(not_expired_at)

        query = "SELECT payload, first_seen_at, notified_at FROM listings"
        if clauses:
            query += " WHERE " + " AND ".join(clauses)
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

    def count(self, not_expired_at: str | None = None) -> dict[str, int]:
        query = "SELECT source, COUNT(*) AS n FROM listings"
        params: list = []
        if not_expired_at is not None:
            query += (" WHERE json_extract(payload,'$.deadline') IS NULL"
                      " OR substr(json_extract(payload,'$.deadline'),1,16) >= ?")
            params.append(not_expired_at)
        query += " GROUP BY source"
        with self._connect() as conn:
            rows = conn.execute(query, params).fetchall()
        return {r["source"]: r["n"] for r in rows}

    # ---- 지오코딩 캐시 ----

    def get_geocode(self, address_key: str) -> tuple[float | None, float | None] | None:
        """(lat, lon) / (None, None) = 실패 기록 / None = 아직 안 해봄."""
        with self._connect() as conn:
            row = conn.execute(
                "SELECT lat, lon FROM geocode WHERE address_key = ?", (address_key,)
            ).fetchone()
        if row is None:
            return None
        return (row["lat"], row["lon"])

    def save_geocode(self, address_key: str, found: tuple[float, float] | None) -> None:
        lat, lon = found if found else (None, None)
        with self._connect() as conn:
            conn.execute(
                "INSERT INTO geocode(address_key, lat, lon, tried_at) VALUES(?,?,?,?)"
                " ON CONFLICT(address_key) DO UPDATE SET"
                " lat=excluded.lat, lon=excluded.lon, tried_at=excluded.tried_at",
                (address_key, lat, lon, _now()),
            )

    def geocode_coverage(self) -> dict[str, int]:
        with self._connect() as conn:
            row = conn.execute(
                "SELECT COUNT(*) AS n,"
                " SUM(CASE WHEN lat IS NOT NULL THEN 1 ELSE 0 END) AS hit"
                " FROM geocode"
            ).fetchone()
        return {"tried": row["n"] or 0, "found": row["hit"] or 0}

    def listings_missing_coords(self, limit: int) -> list[dict]:
        """좌표가 아직 안 붙은 물건. 지오코딩 백필 대상이다."""
        with self._connect() as conn:
            rows = conn.execute(
                "SELECT dedupe_key, payload FROM listings"
                " WHERE json_extract(payload,'$.lat') IS NULL"
                "   AND COALESCE(json_extract(payload,'$.address'),'') != ''"
                " ORDER BY first_seen_at DESC LIMIT ?",
                (limit,),
            ).fetchall()
        return [{"dedupe_key": r["dedupe_key"], **json.loads(r["payload"])} for r in rows]

    def set_coords(self, dedupe_key: str, lat: float, lon: float) -> None:
        """이미 저장된 물건에 좌표만 덧입힌다."""
        with self._connect() as conn:
            conn.execute(
                "UPDATE listings SET payload = json_set(payload, '$.lat', ?, '$.lon', ?)"
                " WHERE dedupe_key = ?",
                (lat, lon, dedupe_key),
            )

    def migrate_area_cap(self) -> int:
        """옛 기본값 1000.0 이 박힌 조건의 면적 상한을 푼다.

        앱에 면적 입력이 없던 시절의 기본값이라 사용자가 고른 적이 없다.
        그대로 두면 302평 넘는 토지가 계속 안 보인다.
        """
        changed = 0
        with self._connect() as conn:
            rows = conn.execute("SELECT id, payload FROM filters").fetchall()
            for row in rows:
                data = json.loads(row["payload"])
                if data.get("max_area_sqm") == 1000.0:
                    data["max_area_sqm"] = None
                    conn.execute(
                        "UPDATE filters SET payload = ? WHERE id = ?",
                        (json.dumps(data, ensure_ascii=False), row["id"]),
                    )
                    changed += 1
        return changed

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

    def regions(self) -> list[dict]:
        """실제로 수집된 시도와 건수.

        시도 목록을 앱에 하드코딩하면 행정구역 개편을 놓친다. 실측에서
        '전남광주통합특별시' 같은 이름이 나왔는데 미리 적어 뒀다면 그 지역
        물건이 통째로 필터에서 빠졌을 것이다.
        """
        with self._connect() as conn:
            rows = conn.execute(
                "SELECT json_extract(payload, '$.sido') AS sido, COUNT(*) AS n"
                " FROM listings WHERE sido IS NOT NULL AND sido != ''"
                " GROUP BY sido ORDER BY n DESC"
            ).fetchall()
        return [{"sido": r["sido"], "count": r["n"]} for r in rows if r["sido"]]

    def land_categories(self) -> list[dict]:
        """수집된 토지의 지목과 건수. 앱의 지목 칩이 이걸로 만들어진다."""
        with self._connect() as conn:
            rows = conn.execute(
                "SELECT json_extract(payload, '$.raw.usage_minor') AS cat,"
                " COUNT(*) AS n FROM listings"
                " WHERE json_extract(payload, '$.property_type') = '토지'"
                " GROUP BY cat ORDER BY n DESC"
            ).fetchall()
        return [{"category": r["cat"], "count": r["n"]} for r in rows if r["cat"]]

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
    """저장된 payload를 다시 Listing으로. 계산 모듈에 넘길 때 쓴다.

    `to_dict()` 는 화면 편의를 위해 파생 필드(effective_price_krw, is_expired
    등)를 얹는다. 그것들을 그대로 생성자에 넘기면 TypeError 로 죽는데,
    파생 필드를 하나 추가할 때마다 여기에 제외 목록을 늘리는 방식은 결국
    빠뜨린다. 실제로 is_expired 를 추가했다가 목록 조회가 통째로 500 이 났다.
    그래서 **아는 필드만 골라 넘긴다.**
    """
    known = {f.name for f in fields(Listing)}
    kwargs = {k: v for k, v in data.items() if k in known}
    kwargs["source"] = Source(kwargs["source"])
    kwargs["property_type"] = PropertyType(kwargs["property_type"])
    return Listing(**kwargs)
