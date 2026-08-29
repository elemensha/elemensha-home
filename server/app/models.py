"""소스가 달라도 앱은 한 가지 모양만 본다.

온비드 공매, 법원경매, 청약 공고, 실거래 급매는 원본 스키마가 전부 다르다.
어댑터가 각자 `Listing`으로 번역해 넣고, 필터·알림·수익률 계산은 이 하나만 안다.
"""

from __future__ import annotations

from dataclasses import dataclass, field, asdict
from datetime import datetime, timedelta, timezone
from enum import Enum


class Source(str, Enum):
    ONBID = "onbid"            # 캠코 온비드 공매
    COURT = "court"            # 법원경매
    RTMS = "rtms"              # 국토부 실거래 (급매 감지)
    APPLYHOME = "applyhome"    # 청약홈 분양공고


class PropertyType(str, Enum):
    APARTMENT = "아파트"
    OFFICETEL = "오피스텔"
    VILLA = "연립다세대"
    HOUSE = "단독주택"
    LAND = "토지"
    COMMERCIAL = "상가"
    OTHER = "기타"


# 온비드가 주는 입찰 마감 시각은 한국시간이다. 서버는 UTC 로 도니
# 그대로 비교하면 9시간이 어긋난다.
KST = timezone(timedelta(hours=9))


def _now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def now_kst_iso() -> str:
    """'2026-08-27T00:51' 꼴. 마감 문자열과 사전순으로 비교할 수 있다."""
    return datetime.now(KST).strftime("%Y-%m-%dT%H:%M")


@dataclass
class Listing:
    """정규화된 매물 하나."""

    source: Source
    source_id: str                 # 소스 안에서 고유한 키. 중복 판정의 기준이다.
    title: str
    url: str

    sido: str = ""                 # 시도 (서울특별시, 경기도)
    sigungu: str = ""              # 시군구
    address: str = ""
    # 지도용 좌표. 주소를 지오코딩해 채운다. 못 찾으면 None 으로 남고
    # 지도에서 빠진다 - 엉뚱한 곳에 찍는 것보다 안 보이는 편이 낫다.
    lat: float | None = None
    lon: float | None = None

    property_type: PropertyType = PropertyType.OTHER
    exclusive_area_sqm: float | None = None

    # 소스마다 "가격"의 의미가 다르다. 셋 중 있는 것만 채운다.
    appraised_price_krw: int | None = None   # 감정가 (경매·공매)
    min_bid_price_krw: int | None = None     # 최저입찰가 (유찰로 내려간 값)
    asking_price_krw: int | None = None      # 호가·분양가·실거래가

    deadline: str | None = None    # 입찰 마감 / 청약 접수 마감 (ISO date)
    bid_start: str | None = None   # 입찰 시작 (ISO). 지금 입찰 가능한지 판정에 쓴다
    bid_status: str = ""           # '진행중' | '준비중' | ''
    failed_bid_count: int = 0      # 유찰 횟수

    # 실거래 대비 얼마나 싼지. 시세 정보가 있을 때만 채워진다.
    market_price_krw: int | None = None
    discount_ratio: float | None = None

    first_seen_at: str = field(default_factory=_now)
    last_seen_at: str = field(default_factory=_now)
    raw: dict = field(default_factory=dict)

    @property
    def dedupe_key(self) -> str:
        return f"{self.source.value}:{self.source_id}"

    @property
    def is_expired(self) -> bool:
        """입찰 마감이 지났는지. 마감일이 없으면 만료로 보지 않는다.

        실거래(rtms)처럼 마감 개념이 없는 소스가 있어서, 값이 없다는 것을
        '지났다'로 해석하면 통째로 사라진다.
        """
        if not self.deadline:
            return False
        return self.deadline[:16] < now_kst_iso()

    @property
    def is_biddable(self) -> bool:
        """지금 당장 입찰할 수 있는지.

        API 의 상태 코드는 회차 전환기에 늦게 따라오는 경우가 있어, 실제
        입찰 기간에 들어와 있는지를 시각으로 직접 본다. 시작일이 없으면
        상태 코드를 믿는다.
        """
        now = now_kst_iso()
        if self.bid_start:
            return self.bid_start[:16] <= now and not self.is_expired
        return self.bid_status == "진행중" and not self.is_expired

    @property
    def effective_price_krw(self) -> int | None:
        """필터와 수익률 계산이 쓸 '지금 사려면 드는 돈'.

        경매·공매는 최저입찰가, 그 외에는 호가를 쓴다. 실제 낙찰가는 이보다
        높게 형성되는 게 보통이라는 점은 앱에서 따로 경고한다.
        """
        return self.min_bid_price_krw or self.asking_price_krw or self.appraised_price_krw

    def to_dict(self) -> dict:
        data = asdict(self)
        data["source"] = self.source.value
        data["property_type"] = self.property_type.value
        data["effective_price_krw"] = self.effective_price_krw
        data["is_expired"] = self.is_expired
        data["is_biddable"] = self.is_biddable
        return data


@dataclass
class FilterProfile:
    """알림을 받고 싶은 조건. 앱에서 사용자가 만든다."""

    id: int | None = None
    name: str = "내 조건"
    enabled: bool = True

    sources: list[str] = field(default_factory=lambda: [Source.ONBID.value])
    sido: list[str] = field(default_factory=lambda: ["서울특별시", "경기도"])
    sigungu: list[str] = field(default_factory=list)   # 비우면 시도 전체

    min_price_krw: int = 0
    max_price_krw: int = 2_000_000_000
    min_area_sqm: float = 0.0
    # None = 상한 없음. 예전 기본값이 1000.0 이었는데 앱에 면적 입력이
    # 없어서 아무도 고른 적 없는 값이었고, 302평 넘는 토지가 조용히
    # 빠지고 있었다. 토지는 그보다 큰 것이 흔하다.
    max_area_sqm: float | None = None
    property_types: list[str] = field(default_factory=lambda: [PropertyType.APARTMENT.value])

    # 토지 지목(대지·임야·전·답 ...). 비우면 전부.
    land_categories: list[str] = field(default_factory=list)
    # 농지(전·답·과수원) 제외. 농지취득자격증명을 못 받으면 보증금을 잃는다.
    exclude_farmland: bool = False
    # 지금 입찰할 수 있는 물건만. 알림은 이쪽이 훨씬 유용하다 -
    # 3개월 뒤 물건을 오늘 알려줘 봐야 그때 가면 잊는다.
    biddable_only: bool = False

    # 실거래 대비 이 비율 이상 싼 것만. None이면 미적용.
    min_discount_ratio: float | None = None
    # 예산은 현금이 아니라 '대출 포함 구매가능액'으로 볼지
    use_loan_capacity_as_budget: bool = True

    def matches(self, listing: Listing) -> bool:
        if not self.enabled:
            return False
        if self.sources and listing.source.value not in self.sources:
            return False
        if self.sido and listing.sido and listing.sido not in self.sido:
            return False
        if self.sigungu and listing.sigungu and listing.sigungu not in self.sigungu:
            return False
        if self.property_types and listing.property_type.value not in self.property_types:
            return False

        price = listing.effective_price_krw
        if price is None or not (self.min_price_krw <= price <= self.max_price_krw):
            return False

        area = listing.exclusive_area_sqm
        if area is not None:
            if area < self.min_area_sqm:
                return False
            if self.max_area_sqm is not None and area > self.max_area_sqm:
                return False

        if self.biddable_only and not listing.is_biddable:
            return False

        # 지목은 raw 에 들어 있다. 토지가 아닌 물건에는 적용하지 않는다.
        if listing.property_type is PropertyType.LAND:
            minor = str(listing.raw.get("usage_minor", ""))
            if self.land_categories and minor not in self.land_categories:
                return False
            if self.exclude_farmland and listing.raw.get("needs_farmland_permit"):
                return False

        if self.min_discount_ratio is not None:
            if listing.discount_ratio is None or listing.discount_ratio < self.min_discount_ratio:
                return False

        return True

    def to_dict(self) -> dict:
        return asdict(self)
