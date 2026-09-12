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
    notified_at     TEXT,
    deadline        TEXT,
    property_type   TEXT,
    sido            TEXT,
    area_sqm        REAL
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

-- 관심 물건. 1.9만 건에서 한 번 놓치면 다시 찾을 방법이 없었다.
CREATE TABLE IF NOT EXISTS favorites (
    dedupe_key TEXT PRIMARY KEY,
    added_at   TEXT NOT NULL,
    memo       TEXT NOT NULL DEFAULT ''
);

-- 가격 이력. 유찰로 값이 내려가는 것이 공매의 핵심인데 현재 값만 보였다.
-- 지금부터 쌓아야 나중에 '3회 유찰, 감정가의 51%'를 보여줄 수 있다.
CREATE TABLE IF NOT EXISTS price_history (
    dedupe_key TEXT NOT NULL,
    price      INTEGER,
    seen_at    TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_price_history_key ON price_history(dedupe_key);

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
    COLUMNS = (
        ("deadline", "TEXT", "$.deadline"),
        ("property_type", "TEXT", "$.property_type"),
        ("sido", "TEXT", "$.sido"),
        ("area_sqm", "REAL", "$.exclusive_area_sqm"),
        ("land_category", "TEXT", "$.raw.usage_minor"),
        ("farmland", "INTEGER", "$.raw.needs_farmland_permit"),
        ("manual", "INTEGER", "$.raw.manual"),
    )

    def _ensure_columns(self, conn) -> None:
        """이미 있는 DB 에 컬럼을 붙이고 한 번 채운다."""
        have = {r["name"] for r in conn.execute("PRAGMA table_info(listings)")}
        added = [c for c in self.COLUMNS if c[0] not in have]
        for name, kind, _ in added:
            conn.execute(f"ALTER TABLE listings ADD COLUMN {name} {kind}")
        if added:
            sets = ", ".join(f"{n} = json_extract(payload, '{path}')"
                             for n, _, path in added)
            conn.execute(f"UPDATE listings SET {sets}")
        # 인덱스는 컬럼이 생긴 뒤에 만든다. SCHEMA 에 두면 옛 DB 에서
        # 컬럼보다 먼저 실행돼 'no such column' 으로 죽는다.
        for name in ("deadline", "property_type", "sido", "manual"):
            conn.execute(
                f"CREATE INDEX IF NOT EXISTS idx_listings_{name} ON listings({name})"
            )

    def __init__(self, path: Path) -> None:
        self.path = path
        self.path.parent.mkdir(parents=True, exist_ok=True)
        with self._connect() as conn:
            conn.executescript(SCHEMA)
            self._ensure_columns(conn)

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
                    " (dedupe_key, source, payload, effective_price, first_seen_at,"
                    "  last_seen_at, deadline, property_type, sido, area_sqm,"
                    "  land_category, farmland, manual)"
                    " VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?)",
                    (listing.dedupe_key, listing.source.value, payload, price, now, now,
                     listing.deadline, listing.property_type.value, listing.sido,
                     listing.exclusive_area_sqm,
                     str(listing.raw.get("usage_minor") or ""),
                     1 if listing.raw.get("needs_farmland_permit") else 0,
                     1 if listing.raw.get("manual") else 0),
                )
                conn.execute(
                    "INSERT INTO price_history(dedupe_key, price, seen_at) VALUES(?,?,?)",
                    (listing.dedupe_key, price, now),
                )
                return True

            price_dropped = (
                price is not None
                and row["effective_price"] is not None
                and price < row["effective_price"]
            )
            # 값이 달라졌을 때만 한 줄 남긴다. 매일 같은 값을 쌓으면
            # 이력이 아니라 로그가 된다.
            if price != row["effective_price"]:
                conn.execute(
                    "INSERT INTO price_history(dedupe_key, price, seen_at) VALUES(?,?,?)",
                    (listing.dedupe_key, price, now),
                )
            conn.execute(
                "UPDATE listings SET payload = ?, effective_price = ?, last_seen_at = ?,"
                " deadline = ?, property_type = ?, sido = ?, area_sqm = ?,"
                " land_category = ?, farmland = ?, manual = ?"
                + (", notified_at = NULL" if price_dropped else "")
                + " WHERE dedupe_key = ?",
                (payload, price, now, listing.deadline, listing.property_type.value,
                 listing.sido, listing.exclusive_area_sqm,
                 str(listing.raw.get("usage_minor") or ""),
                 1 if listing.raw.get("needs_farmland_permit") else 0,
                 1 if listing.raw.get("manual") else 0, listing.dedupe_key),
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

    def _where(
        self,
        source: str | None = None,
        sources: list[str] | None = None,
        min_price: int | None = None,
        max_price: int | None = None,
        not_expired_at: str | None = None,
        property_types: list[str] | None = None,
        sido: list[str] | None = None,
        min_area: float | None = None,
        max_area: float | None = None,
        land_categories: list[str] | None = None,
        exclude_farmland: bool = False,
    ) -> tuple[str, list]:
        """조건을 SQL WHERE 절로 조립한다.

        읽기(listings)와 세기(count_matching)가 같은 조건을 써야 화면의
        총계와 목록이 어긋나지 않는다.
        """
        clauses: list[str] = []
        params: list = []
        if source:
            clauses.append("source = ?")
            params.append(source)
        elif sources:
            clauses.append(f"source IN ({','.join('?' * len(sources))})")
            params += sources
        # 가격 조건이 걸리면 값이 없는 물건은 탈락이다. matches() 가 그렇게
        # 판정하는데 SQL 만 통과시키면, 파이썬까지 올렸다가 버리는 행이 생긴다.
        if min_price is not None or max_price is not None:
            clauses.append("effective_price IS NOT NULL")
        if min_price is not None:
            clauses.append("effective_price >= ?")
            params.append(min_price)
        if max_price is not None:
            clauses.append("effective_price <= ?")
            params.append(max_price)
        if min_area is not None:
            clauses.append("(area_sqm IS NULL OR area_sqm >= ?)")
            params.append(min_area)
        if max_area is not None:
            clauses.append("(area_sqm IS NULL OR area_sqm <= ?)")
            params.append(max_area)
        if not_expired_at is not None:
            # 마감 판정은 SQL 에서 한다. 파이썬으로 올려 세면 스캔 한도에
            # 걸려 '유효 6000건' 같은 잘린 숫자가 총계로 나간다.
            clauses.append("(deadline IS NULL OR substr(deadline,1,16) >= ?)")
            params.append(not_expired_at)
        if property_types:
            clauses.append(f"property_type IN ({','.join('?' * len(property_types))})")
            params += list(property_types)
        if sido:
            # 지역은 비어 있을 수 있어(수집이 못 채운 것) NULL 도 통과시킨다.
            clauses.append(
                f"(sido IS NULL OR sido = '' OR sido IN ({','.join('?' * len(sido))}))"
            )
            params += list(sido)
        # 지목·농지는 토지에만 적용되는 조건이라, 부르는 쪽이 토지로
        # 좁혀 놓았을 때만 넘어온다.
        if land_categories:
            clauses.append(
                f"land_category IN ({','.join('?' * len(land_categories))})"
            )
            params += list(land_categories)
        if exclude_farmland:
            clauses.append("COALESCE(farmland, 0) = 0")

        return (" WHERE " + " AND ".join(clauses) if clauses else ""), params

    def listings(self, limit: int = 100, offset: int = 0, **kw) -> list[dict]:
        """물건 목록.

        조건은 SQL 에서 먼저 거른다. 1.9만 건을 전부 파이썬으로 올려 json 을
        풀어 비교하면 작은 VM 에서 요청마다 몇 초가 걸린다.
        """
        where, params = self._where(**kw)
        query = ("SELECT payload, first_seen_at, notified_at FROM listings" + where
                 + " ORDER BY first_seen_at DESC LIMIT ? OFFSET ?")
        with self._connect() as conn:
            rows = conn.execute(query, params + [limit, offset]).fetchall()
        return [
            {
                **json.loads(r["payload"]),
                "first_seen_at": r["first_seen_at"],
                "notified": r["notified_at"] is not None,
            }
            for r in rows
        ]

    def manual_listings(self, not_expired_at: str | None = None) -> list[dict]:
        """손으로 넣은 물건 전부.

        가격·소스 프리필터를 SQL 로 내리면 조건 밖의 수동 물건이 거기서
        잘린다. 수동 물건은 몇 건뿐이라 통째로 읽어 합치는 편이 싸다.
        """
        query = ("SELECT payload, first_seen_at, notified_at FROM listings"
                 " WHERE manual = 1")
        params: list = []
        if not_expired_at is not None:
            query += (" AND (json_extract(payload,'$.deadline') IS NULL"
                      " OR substr(json_extract(payload,'$.deadline'),1,16) >= ?)")
            params.append(not_expired_at)
        query += " ORDER BY first_seen_at DESC"
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

    def count_matching(self, **kw) -> int:
        """listings() 와 같은 조건으로 개수만 센다.

        payload 를 읽지 않아 즉시 끝난다. 조건을 SQL 로 전부 표현할 수 있을
        때만 쓴다 - 파이썬이 더 거르면 이 숫자가 실제 총계보다 커진다.
        """
        where, params = self._where(**kw)
        with self._connect() as conn:
            return conn.execute(
                "SELECT COUNT(*) AS n FROM listings" + where, params
            ).fetchone()["n"]

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
                # 한 번 못 찾은 주소는 빼둔다. 안 그러면 지번 없는 주소
                # 200여 건을 60초마다 영원히 다시 집어 든다.
                "   AND COALESCE(json_extract(payload,'$.geo_failed'), 0) = 0"
                " ORDER BY first_seen_at DESC LIMIT ?",
                (limit,),
            ).fetchall()
        return [{"dedupe_key": r["dedupe_key"], **json.loads(r["payload"])} for r in rows]

    def mark_geocode_failed(self, dedupe_key: str) -> None:
        """좌표를 못 찾았다고 표시한다.

        다시 수집되면 payload 가 통째로 갈리므로 표시도 사라진다 - 주소가
        고쳐져 들어오면 자동으로 한 번 더 시도한다.
        """
        with self._connect() as conn:
            conn.execute(
                "UPDATE listings SET payload = json_set(payload, '$.geo_failed', 1)"
                " WHERE dedupe_key = ?",
                (dedupe_key,),
            )

    def set_coords(self, dedupe_key: str, lat: float, lon: float) -> None:
        """이미 저장된 물건에 좌표만 덧입힌다."""
        with self._connect() as conn:
            conn.execute(
                "UPDATE listings SET payload = json_set(payload, '$.lat', ?, '$.lon', ?)"
                " WHERE dedupe_key = ?",
                (lat, lon, dedupe_key),
            )

    def migrate_map_links(self) -> int:
        """저장된 카카오맵 링크를 네이버로 바꾼다.

        소스 코드는 고쳤지만 이미 저장된 물건의 raw.map_url 은 옛 링크 그대로다.
        온비드가 한도에 막혀 재수집이 안 되는 동안 앱에서 계속 카카오가 열린다.
        """
        with self._connect() as conn:
            cursor = conn.execute(
                "UPDATE listings SET payload ="
                " replace(payload, 'https://map.kakao.com/?q=',"
                "                  'https://map.naver.com/p/search/')"
                " WHERE payload LIKE '%map.kakao.com%'"
            )
            return cursor.rowcount

    # ---- 관심 물건 ----

    def favorite_keys(self) -> set[str]:
        with self._connect() as conn:
            rows = conn.execute("SELECT dedupe_key FROM favorites").fetchall()
        return {r["dedupe_key"] for r in rows}

    def add_favorite(self, dedupe_key: str, memo: str = "") -> bool:
        with self._connect() as conn:
            conn.execute(
                "INSERT INTO favorites(dedupe_key, added_at, memo) VALUES(?,?,?)"
                " ON CONFLICT(dedupe_key) DO UPDATE SET memo=excluded.memo",
                (dedupe_key, _now(), memo),
            )
        return True

    def remove_favorite(self, dedupe_key: str) -> bool:
        with self._connect() as conn:
            cur = conn.execute("DELETE FROM favorites WHERE dedupe_key = ?", (dedupe_key,))
            return cur.rowcount > 0

    def favorites(self) -> list[dict]:
        """관심 물건. 마감된 것도 준다 - 담아 둔 것이 말없이 사라지면 안 된다."""
        with self._connect() as conn:
            rows = conn.execute(
                "SELECT l.payload, l.first_seen_at, l.notified_at, f.added_at, f.memo"
                " FROM favorites f JOIN listings l ON l.dedupe_key = f.dedupe_key"
                " ORDER BY f.added_at DESC"
            ).fetchall()
        return [
            {**json.loads(r["payload"]), "first_seen_at": r["first_seen_at"],
             "notified": r["notified_at"] is not None,
             "favorite": True, "favorited_at": r["added_at"], "memo": r["memo"]}
            for r in rows
        ]

    def price_history(self, dedupe_key: str) -> list[dict]:
        with self._connect() as conn:
            rows = conn.execute(
                "SELECT price, seen_at FROM price_history"
                " WHERE dedupe_key = ? ORDER BY seen_at",
                (dedupe_key,),
            ).fetchall()
        return [{"price": r["price"], "at": r["seen_at"]} for r in rows]

    def last_collected_at(self, source: str = "onbid") -> str | None:
        """마지막으로 수집에 성공한 시각. 화면에 언제 자료인지 밝히는 데 쓴다."""
        with self._connect() as conn:
            row = conn.execute(
                "SELECT started_at FROM poll_log WHERE source = ? AND ok = 1"
                " ORDER BY started_at DESC LIMIT 1",
                (source,),
            ).fetchone()
        return row["started_at"] if row else None

    def migrate_onbid_urls(self, new_url: str) -> int:
        """404 가 된 옛 온비드 상세 링크를 목록 주소로 바꾼다.

        온비드가 사이트를 개편해 예전 상세 주소가 전부 죽었다. 재수집으로
        갱신되기를 기다리면 한도에 막힌 동안 계속 죽은 링크가 열린다.
        """
        with self._connect() as conn:
            cursor = conn.execute(
                "UPDATE listings SET payload = json_set(payload, '$.url', ?)"
                " WHERE source = 'onbid'"
                "   AND json_extract(payload,'$.url') LIKE '%collateralRealEstate%'",
                (new_url,),
            )
            return cursor.rowcount

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
        """오래된 물건을 지운다. 작은 서버라 무한정 쌓아두지 않는다.

        직접 넣은 법원경매 물건은 건드리지 않는다. 수집으로 갱신되지
        않으니 last_seen_at 이 멈춰 있고, 그대로 두면 손으로 넣은 것이
        90일 뒤 말없이 사라진다.
        """
        with self._connect() as conn:
            cursor = conn.execute(
                "DELETE FROM listings WHERE last_seen_at < datetime('now', ?)"
                " AND source != 'court'",
                (f"-{keep_days} days",),
            )
            return cursor.rowcount

    def delete_listing(self, dedupe_key: str) -> bool:
        with self._connect() as conn:
            cursor = conn.execute(
                "DELETE FROM listings WHERE dedupe_key = ?", (dedupe_key,)
            )
            return cursor.rowcount > 0

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
