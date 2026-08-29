"""FastAPI 서버.

앱이 보는 면은 여기 하나뿐이다. 소스가 몇 개든, 규제가 어떻게 바뀌든
엔드포인트 모양은 그대로 유지한다.
"""

from __future__ import annotations

import asyncio
import contextlib
import logging
from datetime import datetime, timedelta, timezone

import httpx
from fastapi import Depends, FastAPI, Header, HTTPException
from pydantic import BaseModel, Field

from .config import settings
from .finance.loan import (
    BorrowerProfile,
    HouseCount,
    LoanTerms,
    calculate_capacity,
    max_affordable_price,
)
from .finance.roi import ExitScenario, estimate_holding_cost, evaluate_scenario
from .finance.provenance import Status, load_provenance
from .finance.rules import load_ruleset
from .finance.tax import calculate_acquisition_cost
from .models import KST, FilterProfile, Source, now_kst_iso
from .sources.onbid import OnbidSource
from .sources.onbid_detail import fetch_detail
from .sources.rtms import RtmsSource
from .store import Store

STARTED_AT = datetime.now(timezone.utc).isoformat(timespec="seconds")

# 앱과 서버가 같은 버전 체계를 쓴다. 릴리스를 못 읽을 때의 바닥값이다.
APP_VERSION = "0.1.0"
APP_VERSION_CODE = 1

# 조건 매칭 시 훑어볼 최근 물건 수. 전부 객체로 만들어 비교해야 해서
# 무제한으로 두면 작은 VM 의 메모리를 밀어낸다.
# uvicorn 은 자기 로거만 설정한다. 이걸 안 걸면 수집 로그가
# journald 에 아예 안 남아서, 나중에 원인을 물어볼 데가 없다.
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)s %(name)s: %(message)s",
)
LOGGER = logging.getLogger("elemensha.home")

MATCH_SCAN_LIMIT = 6000

# 한 번에 넘길 알림 최대 건수. 앱이 하루 한 번 가져가므로 하루치가
# 한꺼번에 온다. 개별 알림이 아니라 요약으로 묶이니 많아도 괜찮다.
NOTIFY_BATCH = 300


def _expired(row: dict) -> bool:
    """이미 마감된 물건인지. 마감일이 없으면 만료가 아니다.

    입찰이 끝난 물건이 목록에 절반 가까이 섞여 있었다. 온비드는 마감되면
    조회에서 빠지는데 DB 에는 남기 때문이다.
    """
    deadline = row.get("deadline")
    return bool(deadline) and str(deadline)[:16] < now_kst_iso()

store = Store(settings.db_path)
rules = load_ruleset(settings.rules_path)
provenance = load_provenance(settings.citations_path)


def require_token(authorization: str = Header(default="")) -> None:
    """토큰을 설정하지 않았으면 인증을 요구하지 않는다(로컬 개발용).

    운영에 올릴 때 HOME_API_TOKEN을 반드시 넣을 것. 넣지 않으면 URL을 아는
    누구나 내 소득·자산 정보를 읽을 수 있다.
    """
    if not settings.api_token:
        return
    expected = f"Bearer {settings.api_token}"
    if authorization != expected:
        raise HTTPException(status_code=401, detail="인증 실패")


# ---------- 폴링 ----------


def build_sources(full: bool = False) -> dict[str, object]:
    """이번 폴링에 쓸 소스들.

    `full=False` 면 온비드는 '진행중' 물건만 본다(20~30회 호출).
    `full=True` 면 '준비중'까지 훑는다(200회쯤). 하루 한 번만 쓴다.
    """
    available: dict[str, object] = {}
    if settings.onbid_key:
        available["onbid"] = OnbidSource(
            settings.onbid_key,
            target_sido=settings.target_sido,
            include_upcoming=full,
            upcoming_days=settings.onbid_upcoming_days,
        )
    if settings.rtms_key:
        # 실거래가는 시군구 코드로만 조회된다. 전국은 법정동코드 250여 개가
        # 필요하고 1회 폴링에 1,500회를 쓰므로 아직 수도권으로 둔다.
        available["rtms"] = RtmsSource(
            settings.rtms_key,
            sido=settings.target_sido or ["서울특별시", "경기도", "인천광역시"],
        )
    return available


async def poll_once(name: str, source, client: httpx.AsyncClient) -> dict:
    """한 소스를 한 번 긁어 저장한다. 실패는 삼키지 않고 기록한다."""
    fetched = new_count = 0
    try:
        # 받는 대로 저장한다. 전국 1.5만 건을 리스트로 들고 있으면
        # 956MB VM 에서 메모리 한도를 넘긴다.
        async for listing in source.stream(client):
            fetched += 1
            if store.upsert(listing):
                new_count += 1
    except Exception as exc:  # 어댑터 하나가 죽어도 서버는 살아 있어야 한다
        calls = getattr(source, "api_calls", None)
        store.log_poll(
            name, ok=False, fetched=fetched,
            error=f"{type(exc).__name__}: {exc}",
        )
        LOGGER.warning("%s 수집 실패 (API %s회): %s", name, calls, exc)
        return {"source": name, "ok": False, "fetched": fetched,
                "api_calls": calls, "error": str(exc)}

    calls = getattr(source, "api_calls", None)
    store.log_poll(name, ok=True, fetched=fetched, new_count=new_count)
    # 호출 수를 추정으로 잡았다가 일일 한도를 실제로 넘긴 적이 있다.
    # 로그에 남겨야 다음에 주기를 조정할 근거가 생긴다.
    LOGGER.info("%s 수집 완료: %d건 (신규 %d) / API %s회",
                name, fetched, new_count, calls)
    return {"source": name, "ok": True, "fetched": fetched,
            "new": new_count, "api_calls": calls}


async def notify_pending(client: httpx.AsyncClient) -> int:
    """필터에 걸린 새 물건을 알린다.

    앱은 `/api/notifications`를 폴링해 가져가므로 여기서는 텔레그램만 쏜다.
    앱 쪽 확인(ack)은 별도 엔드포인트에서 처리한다.
    """
    if not settings.telegram_enabled:
        return 0

    pending = store.pending_notifications()
    if not pending:
        return 0

    profiles = store.filters()
    sent = 0
    for item in pending:
        from .store import listing_from_dict

        listing = listing_from_dict(item)
        if profiles and not any(p.matches(listing) for p in profiles):
            continue

        price = listing.effective_price_krw or 0
        text = (
            f"[{listing.source.value}] {listing.title}\n"
            f"{listing.address}\n"
            f"{price // 100_000_000}억 {(price % 100_000_000) // 10_000:,}만원"
            + (f" (감정가 대비 -{listing.discount_ratio:.0%})" if listing.discount_ratio else "")
            + f"\n{listing.url}"
        )
        try:
            await client.post(
                f"https://api.telegram.org/bot{settings.telegram_token}/sendMessage",
                json={"chat_id": settings.telegram_chat_id, "text": text},
                timeout=15,
            )
            sent += 1
        except httpx.HTTPError:
            break  # 텔레그램이 죽었으면 다음 주기에 다시 시도한다
    return sent


def _seconds_until_hour(hour: int) -> float:
    """다음 `hour` 시(KST)까지 남은 초.

    상대 주기만 쓰면 서비스를 재시작한 시각에 수집 시각이 끌려다닌다.
    앱 알림이 아침 7시라 그보다 앞서 끝나야 하므로 벽시계에 고정한다.
    """
    now = datetime.now(KST)
    target = now.replace(hour=hour % 24, minute=0, second=0, microsecond=0)
    if target <= now:
        target += timedelta(days=1)
    return (target - now).total_seconds()


async def poller() -> None:
    """소스별로 다른 주기를 각자 지키며 도는 루프."""
    intervals = {
        "onbid": settings.onbid_interval_min * 60,
        "rtms": settings.rtms_interval_min * 60,
        "applyhome": settings.applyhome_interval_min * 60,
    }
    loop = asyncio.get_running_loop()
    # 온비드는 지정 시각에 처음 돌고, 그다음부터 24시간 주기.
    # 나머지 소스는 서비스가 뜨자마자 한 번 돈다.
    onbid_first = loop.time() + _seconds_until_hour(settings.onbid_poll_hour)
    next_run: dict[str, float] = {"onbid": onbid_first}
    next_full = onbid_first

    async with httpx.AsyncClient(follow_redirects=True) as client:
        while True:
            now = loop.time()
            # 준비중까지 훑는 무거운 회차인지 판단한다.
            full = now >= next_full
            for name, source in build_sources(full=full).items():
                if now < next_run.get(name, 0):
                    continue
                result = await poll_once(name, source, client)

                # 일일 한도를 넘겼으면 다음 회차를 멀리 민다. 계속 두드려 봐야
                # 429 만 받고, 자정에 초기화될 때까지 아무 소득이 없다.
                if not result.get("ok") and "429" in str(result.get("error", "")):
                    next_run[name] = now + 3 * 3600
                    continue

                # 수집에 성공했을 때만 정리한다. 실패 뒤에 지우면 멀쩡한
                # 물건이 통째로 날아간다. 진행중만 본 회차에는 하지 않는다 -
                # 준비중 물건이 전부 '안 잡힌 것'이 되어 지워진다.
                if result.get("ok") and name == "onbid" and full:
                    dropped = store.drop_stale("onbid", hours=36)
                    if dropped:
                        result["dropped"] = dropped
                next_run[name] = now + intervals.get(name, 3600)
            if full:
                next_full = now + settings.onbid_full_interval_min * 60

            await notify_pending(client)
            store.prune(settings.keep_days)
            await asyncio.sleep(60)


@contextlib.asynccontextmanager
async def lifespan(app: FastAPI):
    task = asyncio.create_task(poller())
    try:
        yield
    finally:
        task.cancel()
        with contextlib.suppress(asyncio.CancelledError):
            await task


app = FastAPI(title="elemensha-home", lifespan=lifespan)


# ---------- 스키마 ----------


class ProfileIn(BaseModel):
    annual_income_krw: int = Field(ge=0)
    cash_krw: int = Field(ge=0)
    # 보유 주택 수. LTV 구간과 취득세 중과가 둘 다 여기서 갈린다.
    owned_houses: int = 0
    is_first_time_buyer: bool = False
    # 규제지역에서 처분조건을 걸었는지. 1주택자는 이것 하나로 LTV가 0과 40%를 오간다.
    has_disposal_condition: bool = False
    is_low_income_priority: bool = False
    existing_annual_repayment_krw: int = 0
    annual_rate: float = 0.042
    loan_years: int = 30
    monthly_rent_saved_krw: int = 0

    @property
    def house_count_enum(self) -> HouseCount:
        if self.owned_houses <= 0:
            return HouseCount.NONE
        return HouseCount.ONE if self.owned_houses == 1 else HouseCount.MULTI

    def to_borrower(self) -> BorrowerProfile:
        return BorrowerProfile(
            annual_income_krw=self.annual_income_krw,
            cash_krw=self.cash_krw,
            house_count=self.house_count_enum,
            is_first_time_buyer=self.is_first_time_buyer,
            existing_annual_repayment_krw=self.existing_annual_repayment_krw,
            has_disposal_condition=self.has_disposal_condition,
            is_low_income_priority=self.is_low_income_priority,
        )

    def to_terms(self, is_regulated: bool, is_metro: bool = True) -> LoanTerms:
        return LoanTerms(
            annual_rate=self.annual_rate,
            years=self.loan_years,
            is_metro=is_metro,
            is_regulated_area=is_regulated,
        )


class PlanIn(BaseModel):
    profile: ProfileIn
    price_krw: int = Field(gt=0)
    exclusive_area_sqm: float = 84.9
    is_regulated_area: bool = False
    is_auction: bool = False
    hold_years: float = 5.0
    # 실제 거주한 기간. 비과세 요건과 장특공제 표2가 여기서 갈린다.
    live_years: float | None = None
    # 매도 가정. 비우면 시나리오 없이 매수 단계까지만 계산한다.
    sell_price_options_krw: list[int] = Field(default_factory=list)


# ---------- 엔드포인트 ----------


def _version_code(tag: str) -> int:
    """'1.2.3' -> 10203. 앱이 정수 비교로 신버전을 판정한다."""
    parts = (tag.split("-")[0].split(".") + ["0", "0", "0"])[:3]
    try:
        major, minor, patch = (int(x) for x in parts)
    except ValueError:
        return APP_VERSION_CODE
    return major * 10000 + minor * 100 + patch


@app.get("/api/app/version")
async def app_version() -> dict:
    """인앱 업데이트용. GitHub Releases의 최신 APK를 중계한다.

    릴리스 조회가 실패해도 앱이 멈추면 안 되므로 현재 버전을 그대로 돌려준다.
    """
    fallback = {
        "versionName": APP_VERSION,
        "versionCode": APP_VERSION_CODE,
        "apkUrl": None,
        "notes": "",
        "source": "server",
    }
    if not settings.release_api:
        return fallback

    try:
        async with httpx.AsyncClient(timeout=10) as client:
            response = await client.get(
                settings.release_api,
                headers={"Accept": "application/vnd.github+json"},
            )
            response.raise_for_status()
            data = response.json()
    except Exception:
        return fallback

    apk = next(
        (a for a in data.get("assets", []) if str(a.get("name", "")).endswith(".apk")),
        None,
    )
    tag = str(data.get("tag_name", "")).lstrip("v")
    return {
        "versionName": tag or APP_VERSION,
        "versionCode": _version_code(tag),
        "apkUrl": apk.get("browser_download_url") if apk else None,
        "apkSize": apk.get("size") if apk else None,
        "notes": data.get("body", "") or "",
        "publishedAt": data.get("published_at"),
        "source": "github",
    }


@app.get("/api/health")
async def health() -> dict:
    return {
        "ok": True,
        "started_at": STARTED_AT,
        "sources_configured": settings.source_status(),
        "poll_status": store.poll_status(),
        "listing_count": store.count(),
        "ruleset_version": rules.version,
        "source_coverage": provenance.coverage(),
        "auth_enabled": bool(settings.api_token),
    }


@app.get("/api/rules")
async def get_rules(_: None = Depends(require_token)) -> dict:
    return {"rules": rules.to_dict(), "provenance": provenance.to_dict()}


@app.get("/api/listings")
async def get_listings(
    source: str | None = None,
    limit: int = 100,
    offset: int = 0,
    filter_id: int | None = None,
    apply_filters: bool = True,
    include_expired: bool = False,
    biddable_only: bool = False,
    sort: str = "recent",
    _: None = Depends(require_token),
) -> dict:
    """저장된 조건에 맞는 물건만 돌려준다.

    `apply_filters=false` 면 조건을 무시하고 전부 준다. 조건이 하나도 없으면
    거를 것이 없으므로 역시 전부 준다 - 조건을 안 만든 사용자에게 빈 화면을
    보여주는 것이 더 나쁘다.

    `filter_id` 를 주면 그 조건 하나만 쓴다. 여러 조건이 켜져 있으면 합집합이다.
    """
    from .store import listing_from_dict

    profiles = [p for p in store.filters() if p.enabled]
    if filter_id is not None:
        profiles = [p for p in profiles if p.id == filter_id]
    filtering = apply_filters and bool(profiles)

    page = min(limit, 500)

    # 만료 판정을 SQL 로 내린다. 파이썬으로 올려 세면 스캔 한도에 걸려
    # 총계가 잘린다(실제로 '유효 6000건'이라는 거짓 숫자가 나갔다).
    cutoff = None if include_expired else now_kst_iso()
    now_str = now_kst_iso()

    def biddable(row: dict) -> bool:
        """지금 입찰 기간에 들어와 있는지. 상태 코드보다 시각이 정확하다."""
        start = row.get("bid_start")
        if start:
            return str(start)[:16] <= now_str
        return row.get("bid_status") == "진행중"


    if not filtering:
        # 거를 게 없으면 DB 가 세게 한다. 가져온 행 수를 총계로 쓰면
        # limit=1 일 때 "전체 1건" 같은 거짓말이 나온다.
        counts = store.count(not_expired_at=cutoff)
        total = counts.get(source, 0) if source else sum(counts.values())
        if biddable_only:
            rows = [
                r for r in store.listings(
                    source=source, limit=MATCH_SCAN_LIMIT, offset=0, not_expired_at=cutoff
                ) if biddable(r)
            ]
            total = len(rows)
            rows = rows[offset:offset + page]
        else:
            rows = store.listings(
                source=source, limit=page, offset=offset, not_expired_at=cutoff
            )
    else:
        # 조건을 걸려면 실제 객체로 만들어 봐야 한다. 페이지 단위로 거르면
        # 앞쪽 페이지가 전부 탈락했을 때 빈 목록만 돌아오므로 넉넉히 읽는다.
        # 조건들의 가격 범위 합집합을 SQL 로 먼저 넘긴다. 전부 올려서
        # 파이썬으로 거르면 1.5만 건에서 요청마다 몇 초가 걸린다.
        rows = store.listings(
            source=source,
            limit=MATCH_SCAN_LIMIT,
            offset=0,
            sources=sorted({s for p in profiles for s in p.sources}) or None,
            min_price=min((p.min_price_krw for p in profiles), default=None),
            max_price=max((p.max_price_krw for p in profiles), default=None),
            not_expired_at=cutoff,
        )
        rows = [
            row for row in rows
            if (not biddable_only or biddable(row))
            and any(p.matches(listing_from_dict(row)) for p in profiles)
        ]
        total = len(rows)

    if sort == "discount":
        rows.sort(key=lambda r: r.get("discount_ratio") or 0.0, reverse=True)
    elif sort == "price":
        rows.sort(key=lambda r: r.get("effective_price_krw") or 0)
    elif sort == "deadline":
        rows.sort(key=lambda r: r.get("deadline") or "9999")

    items = rows[offset:offset + page] if filtering else rows

    return {
        "items": items,
        "total_matched": total,
        "filters_applied": [p.name for p in profiles] if filtering else [],
        # 조건 검사는 최근 MATCH_SCAN_LIMIT 건까지만 훑는다. 그 너머에도
        # 맞는 물건이 있을 수 있다는 뜻이라 화면에서 알려줘야 한다.
        "scan_truncated": total >= MATCH_SCAN_LIMIT,
        "expired_hidden": not include_expired,
    }


@app.get("/api/notifications")
async def get_notifications(
    biddable_only: bool = True,
    _: None = Depends(require_token),
) -> dict:
    """앱이 주기적으로 가져가는 새 물건 목록. 필터에 걸린 것만."""
    from .store import listing_from_dict

    profiles = store.filters()
    items = []
    # 하루 한 번만 확인하므로 하루치가 한꺼번에 온다. 50건으로 끊으면
    # 나머지는 다음 날로 밀리므로 넉넉히 읽는다.
    for item in store.pending_notifications(limit=NOTIFY_BATCH):
        # 이미 마감된 물건을 알리는 건 의미가 없다.
        if _expired(item):
            store.mark_notified([item["dedupe_key"]])
            continue
        listing = listing_from_dict(item)
        # 알림은 '지금 입찰할 수 있는 것'이 중요하다. 3개월 뒤 물건을 오늘
        # 알려줘 봐야 그때 가면 잊는다. 준비중 물건은 알리지 않고 남겨 둔다
        # (확인 처리하지 않으므로 입찰이 시작되면 그때 알림이 간다).
        if biddable_only and not listing.is_biddable:
            continue
        if profiles and not any(p.matches(listing) for p in profiles):
            continue
        items.append(item)
    return {"items": items, "total": len(items)}


class AckIn(BaseModel):
    dedupe_keys: list[str]


@app.post("/api/notifications/ack")
async def ack_notifications(body: AckIn, _: None = Depends(require_token)) -> dict:
    store.mark_notified(body.dedupe_keys)
    return {"acked": len(body.dedupe_keys)}


@app.get("/api/listings/{dedupe_key:path}/detail")
async def listing_detail(
    dedupe_key: str,
    refresh: bool = False,
    _: None = Depends(require_token),
) -> dict:
    """물건 상세. 사용자가 열었을 때만 가져오고 캐시한다.

    상세 API 는 일일 1,000회뿐이라 목록 전체를 미리 채울 수 없다.
    """
    listing = store.find_listing(dedupe_key)
    if listing is None:
        raise HTTPException(status_code=404, detail="없는 물건")

    if not refresh:
        cached = store.get_detail(dedupe_key)
        if cached is not None:
            return {"detail": cached, "cached": True}

    if listing.get("source") != Source.ONBID.value:
        raise HTTPException(status_code=400, detail="온비드 물건만 상세 조회를 지원한다")
    if not settings.onbid_key:
        raise HTTPException(status_code=503, detail="온비드 서비스키가 없다")

    # source_id 는 "물건관리번호-공매조건번호" 형태다.
    source_id = listing.get("source_id", "")
    cltr_mng_no, _, cdtn_no = source_id.rpartition("-")
    if not cltr_mng_no:
        cltr_mng_no, cdtn_no = source_id, ""

    try:
        async with httpx.AsyncClient() as client:
            detail = await fetch_detail(client, settings.onbid_key, cltr_mng_no, cdtn_no)
    except Exception as exc:
        raise HTTPException(status_code=502, detail=f"상세 조회 실패: {exc}") from exc

    store.save_detail(dedupe_key, detail)
    return {"detail": detail, "cached": False}


@app.post("/api/notifications/baseline")
async def baseline_notifications(_: None = Depends(require_token)) -> dict:
    """지금까지 쌓인 물건을 전부 '이미 알림' 처리한다.

    알림을 처음 켤 때 부른다. 그러지 않으면 서버가 그동안 모아둔 수천 건이
    전부 미알림 상태라, 앞으로 올라올 새 물건이 아니라 과거 재고가 알림으로
    쏟아진다. 기준선을 여기로 잡고 이후 신규분만 알린다.
    """
    marked = 0
    while True:
        pending = store.pending_notifications(limit=500)
        if not pending:
            break
        store.mark_notified([p["dedupe_key"] for p in pending])
        marked += len(pending)
        if len(pending) < 500:
            break
    return {"baselined": marked}


@app.get("/api/regions")
async def get_regions(_: None = Depends(require_token)) -> dict:
    """수집된 지역과 토지 지목. 앱의 선택 칩이 이걸로 만들어진다."""
    return {"items": store.regions(), "land_categories": store.land_categories()}


@app.get("/api/filters")
async def get_filters(_: None = Depends(require_token)) -> dict:
    return {"items": [f.to_dict() for f in store.filters()]}


@app.post("/api/filters")
async def post_filter(body: dict, _: None = Depends(require_token)) -> dict:
    profile = FilterProfile(**body)
    return store.save_filter(profile).to_dict()


@app.delete("/api/filters/{filter_id}")
async def delete_filter(filter_id: int, _: None = Depends(require_token)) -> dict:
    if not store.delete_filter(filter_id):
        raise HTTPException(status_code=404, detail="없는 필터")
    return {"deleted": filter_id}


@app.get("/api/profile")
async def get_profile(_: None = Depends(require_token)) -> dict:
    return store.get_setting("borrower") or {}


@app.put("/api/profile")
async def put_profile(body: ProfileIn, _: None = Depends(require_token)) -> dict:
    store.set_setting("borrower", body.model_dump())
    return body.model_dump()


def _citations_used(body: "PlanIn", has_scenarios: bool) -> list:
    """이번 계산이 실제로 건드린 파라미터의 출처만 모은다.

    전부 나열하면 사용자가 안 읽는다. 이 결과에 영향을 준 값만 보여줘야
    "어떤 근거로 나온 숫자인가"에 답이 된다.
    """
    prefixes = ["dsr.", "acquisition_tax.", "transaction_cost.", "property_tax."]
    prefixes.append("ltv.regulated_" if body.is_regulated_area else "ltv.normal_")
    if body.profile.is_first_time_buyer:
        prefixes += ["ltv.first_time_buyer", "acquisition_tax.first_time_relief_cap"]
    if body.is_regulated_area:
        prefixes.append("regions.regulated_areas")
    if has_scenarios:
        prefixes.append("capital_gains_tax.")

    return [
        citation
        for citation in provenance.all()
        if any(citation.parameter.startswith(p) for p in prefixes)
    ]


@app.post("/api/plan")
async def post_plan(body: PlanIn, _: None = Depends(require_token)) -> dict:
    """자금계획 전체 계산. 앱의 핵심 화면이 이걸 그린다."""
    borrower = body.profile.to_borrower()
    terms = body.profile.to_terms(body.is_regulated_area)

    capacity = calculate_capacity(body.price_krw, borrower, terms, rules)
    ceiling = max_affordable_price(borrower, terms, rules)

    acquisition = calculate_acquisition_cost(
        body.price_krw,
        body.exclusive_area_sqm,
        body.profile.owned_houses + 1,
        body.is_regulated_area,
        rules,
        is_first_time_buyer=borrower.is_first_time_buyer,
        is_auction=body.is_auction,
    )

    loan = capacity.limit_krw
    cash_needed = body.price_krw - loan + acquisition.total_krw
    holding = estimate_holding_cost(
        loan,
        terms,
        body.price_krw,
        monthly_rent_saved_krw=body.profile.monthly_rent_saved_krw,
        is_single_house=body.profile.owned_houses == 0,
    )

    scenarios = []
    for index, sell_price in enumerate(body.sell_price_options_krw):
        result = evaluate_scenario(
            ExitScenario(f"가정{index + 1}", sell_price, body.hold_years, "사용자 입력"),
            body.price_krw,
            loan,
            acquisition.total_krw,
            terms,
            rules,
            holding,
            other_houses_at_sale=body.profile.owned_houses,
            live_years=body.live_years,
            acquired_in_regulated_area=body.is_regulated_area,
            sale_in_regulated_area=body.is_regulated_area,
        )
        scenarios.append(result.__dict__)

    used = _citations_used(body, bool(scenarios))
    unverified = [c.to_dict() for c in used if c.status is not Status.VERIFIED]

    return {
        "ruleset_version": rules.version,
        "ruleset_note": rules.note,
        "sources": {
            "summary": provenance.trust_summary(),
            "used": [c.to_dict() for c in used],
            "unverified_count": len(unverified),
            "unverified": unverified,
        },
        "max_affordable_price_krw": ceiling,
        "capacity": capacity.__dict__,
        "acquisition_cost": acquisition.__dict__,
        "cash_needed_krw": cash_needed,
        "cash_shortfall_krw": max(cash_needed - borrower.cash_krw, 0),
        "holding": holding.__dict__,
        "scenarios": scenarios,
        "disclaimer": (
            "이 수치는 공개된 규정으로 계산한 참고값이다. 실제 대출 한도는 은행 "
            "심사에서, 세액은 신고 시점 세법과 개인 사정에 따라 달라진다. "
            "매도 가격은 예측이 아니라 입력한 가정일 뿐이다."
        ),
    }


@app.post("/api/refresh")
async def refresh(full: bool = False, _: None = Depends(require_token)) -> dict:
    """수동 폴링. `full=true` 면 준비중 물건까지 훑는다(호출 200회)."""
    results = []
    async with httpx.AsyncClient(follow_redirects=True) as client:
        for name, source in build_sources(full=full).items():
            results.append(await poll_once(name, source, client))
    if not results:
        raise HTTPException(
            status_code=503, detail="설정된 소스가 없다. 서비스키를 먼저 넣을 것."
        )
    return {"results": results}
