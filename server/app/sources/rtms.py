"""국토교통부 아파트 매매 실거래가 어댑터.

이건 '지금 살 수 있는 매물'이 아니라 **이미 체결된 거래**다. 그래서 두 가지로 쓴다.

1. 시세 테이블 - 단지·면적별 최근 거래가 분포. 경매 물건이 실제로 싼지
   판정하고, 매도 시나리오의 가격 범위를 잡는 근거가 된다.
2. 급매 감지 - 같은 단지·비슷한 면적의 최근 중앙값보다 눈에 띄게 낮게
   신고된 거래. 그 단지 가격이 빠지고 있다는 신호일 수 있다.

주의할 것이 셋 있다.
- 실거래 신고는 계약 후 30일 이내라 데이터가 최대 한 달 늦다.
- 해제된 거래가 섞여 들어온다(`cdealType`이 O면 해제건).
- **직거래(`dealingGbn`)를 걸러야 한다.** 중개 없이 이뤄지는 거래에는 가족 간
  저가 양도가 섞여 시세를 왜곡한다. 강남·서초 6개월 실측에서 직거래는 전체
  거래의 5.4%뿐이었는데, 걸러내기 전 급매로 잡힌 4건이 **전부** 직거래였다.
  필터가 없으면 알림이 통째로 오탐이 된다.
"""

from __future__ import annotations

from collections import defaultdict
from datetime import date
from statistics import median

import httpx

from ..models import Listing, PropertyType, Source
from . import regions
from .base import ListingSource, parse_area, parse_manwon, pick, xml_items

ENDPOINT = (
    "http://apis.data.go.kr/1613000/RTMSDataSvcAptTradeDev"
    "/getRTMSDataSvcAptTradeDev"
)
NAVER_SEARCH = "https://m.land.naver.com/search/result/{query}"


class Trade:
    """실거래 한 건."""

    __slots__ = (
        "apt", "dong", "area", "price", "floor", "build_year",
        "deal_date", "sgg_code", "apt_seq", "dealing_type",
    )

    def __init__(
        self,
        apt: str,
        dong: str,
        area: float,
        price: int,
        floor: str,
        build_year: str,
        deal_date: str,
        sgg_code: str,
        apt_seq: str = "",
        dealing_type: str = "",
    ) -> None:
        self.apt = apt
        self.dong = dong
        self.area = area
        self.price = price
        self.floor = floor
        self.build_year = build_year
        self.deal_date = deal_date
        self.sgg_code = sgg_code
        self.apt_seq = apt_seq
        self.dealing_type = dealing_type

    @property
    def is_arms_length(self) -> bool:
        """제3자 간 정상 거래로 볼 수 있는지. 직거래는 제외한다."""
        return self.dealing_type != "직거래"

    @property
    def complex_key(self) -> str:
        """같은 단지·같은 평형끼리 묶는 키. 면적은 1제곱미터 단위로 반올림한다.

        API가 주는 `aptSeq`(예: 11680-3722)가 단지 고유번호라 이름 표기가
        흔들려도 같은 단지로 묶인다. 없으면 이름으로 되돌아간다.
        """
        identity = self.apt_seq or f"{self.sgg_code}|{self.dong}|{self.apt}"
        return f"{identity}|{round(self.area)}"


def _recent_months(count: int) -> list[str]:
    today = date.today()
    months = []
    year, month = today.year, today.month
    for _ in range(count):
        months.append(f"{year}{month:02d}")
        month -= 1
        if month == 0:
            year, month = year - 1, 12
    return months


class RtmsSource(ListingSource):
    """실거래 조회 + 급매 감지."""

    name = Source.RTMS.value

    def __init__(
        self,
        service_key: str,
        sido: list[str] | None = None,
        months: int = 6,
        # 기본 임계는 실측으로 정했다. 강남·서초 6개월 정상거래에서 단지
        # 중앙값 대비 하락폭은 최대 -13%였다. 15%로 두면 알림이 영원히
        # 울리지 않는다.
        discount_threshold: float = 0.10,
        min_samples: int = 4,
        timeout: float = 20.0,
        exclude_direct_deals: bool = True,
    ) -> None:
        super().__init__(service_key, timeout)
        self.sgg_codes = regions.codes_for(sido or ["서울특별시", "경기도"])
        self.months = months
        self.discount_threshold = discount_threshold
        self.min_samples = min_samples
        self.exclude_direct_deals = exclude_direct_deals
        self._trades: list[Trade] = []

    async def fetch_trades(self, client: httpx.AsyncClient) -> list[Trade]:
        """대상 지역·기간의 실거래를 전부 긁는다.

        시군구 x 개월 수만큼 호출이 나간다. 서울+경기 6개월이면 400건이 넘으니
        개발계정 일일 한도(10,000건)를 고려해 폴링 주기를 잡을 것.
        """
        if not self.configured:
            raise RuntimeError("실거래가 서비스키가 설정되지 않았다 (RTMS_SERVICE_KEY)")

        trades: list[Trade] = []
        for code in self.sgg_codes:
            for ym in _recent_months(self.months):
                params = {
                    "serviceKey": self.service_key,
                    "LAWD_CD": code,
                    "DEAL_YMD": ym,
                    "numOfRows": 1000,
                    "pageNo": 1,
                }
                try:
                    response = await client.get(ENDPOINT, params=params, timeout=self.timeout)
                    response.raise_for_status()
                    items = xml_items(response.text)
                except (httpx.HTTPError, RuntimeError):
                    # 한 지역이 실패해도 나머지는 계속 모은다. 조용히 넘기되
                    # 전부 실패하면 아래에서 드러난다.
                    continue

                for item in items:
                    trade = self._to_trade(item, code)
                    if trade is not None:
                        trades.append(trade)

        if not trades:
            raise RuntimeError(
                "실거래 데이터를 한 건도 받지 못했다. 서비스키 승인 여부와 "
                "법정동코드를 확인할 것."
            )
        self._trades = trades
        return trades

    def _to_trade(self, item: dict, sgg_code: str) -> Trade | None:
        # 해제된 거래는 시세를 왜곡하므로 버린다.
        if (pick(item, "cdealType", "CDEAL_TYPE") or "").upper() == "O":
            return None

        # 이 API는 금액을 '만원' 단위 문자열로 준다 (예: "44,520").
        price = parse_manwon(pick(item, "dealAmount", "DEAL_AMOUNT"))
        if price is None:
            return None

        area = parse_area(pick(item, "excluUseAr", "EXCLU_USE_AR"))
        apt = pick(item, "aptNm", "APT_NM", "aptName")
        if not apt or area is None:
            return None

        year = pick(item, "dealYear", "DEAL_YEAR") or ""
        month = (pick(item, "dealMonth", "DEAL_MONTH") or "").zfill(2)
        day = (pick(item, "dealDay", "DEAL_DAY") or "").zfill(2)

        return Trade(
            apt=apt,
            dong=pick(item, "umdNm", "UMD_NM") or "",
            area=area,
            price=price,
            floor=pick(item, "floor", "FLOOR") or "",
            build_year=pick(item, "buildYear", "BUILD_YEAR") or "",
            deal_date=f"{year}-{month}-{day}",
            sgg_code=sgg_code,
            apt_seq=pick(item, "aptSeq", "APT_SEQ") or "",
            dealing_type=pick(item, "dealingGbn", "DEALING_GBN") or "",
        )

    def _usable(self, trades: list[Trade]) -> list[Trade]:
        if not self.exclude_direct_deals:
            return trades
        return [t for t in trades if t.is_arms_length]

    def market_table(self) -> dict[str, list[int]]:
        """단지·평형별 최근 거래가 목록. 시세 판정과 시나리오의 근거."""
        table: dict[str, list[int]] = defaultdict(list)
        for trade in self._usable(self._trades):
            table[trade.complex_key].append(trade.price)
        return dict(table)

    async def fetch(self, client: httpx.AsyncClient) -> list[Listing]:
        """중앙값 대비 크게 낮게 신고된 거래만 Listing으로 올린다."""
        trades = await self.fetch_trades(client)

        grouped: dict[str, list[Trade]] = defaultdict(list)
        for trade in self._usable(trades):
            grouped[trade.complex_key].append(trade)

        listings: list[Listing] = []
        for key, group in grouped.items():
            if len(group) < self.min_samples:
                continue
            prices = [t.price for t in group]
            mid = int(median(prices))
            if mid <= 0:
                continue

            newest = max(group, key=lambda t: t.deal_date)
            discount = 1 - newest.price / mid
            if discount < self.discount_threshold:
                continue

            region_name = regions.name_of(newest.sgg_code)
            parts = region_name.split()
            address = f"{region_name} {newest.dong}".strip()

            listings.append(
                Listing(
                    source=Source.RTMS,
                    source_id=f"{key}|{newest.deal_date}|{newest.price}",
                    title=f"{newest.apt} 전용 {newest.area:.1f}㎡ {newest.floor}층",
                    url=NAVER_SEARCH.format(query=newest.apt),
                    sido=parts[0] if parts else "",
                    sigungu=" ".join(parts[1:]) if len(parts) > 1 else "",
                    address=address,
                    property_type=PropertyType.APARTMENT,
                    exclusive_area_sqm=newest.area,
                    asking_price_krw=newest.price,
                    market_price_krw=mid,
                    discount_ratio=discount,
                    deadline=None,
                    raw={
                        "deal_date": newest.deal_date,
                        "median_of_recent": mid,
                        "sample_count": len(group),
                        "build_year": newest.build_year,
                        "dealing_type": newest.dealing_type,
                        "floors_in_sample": sorted({t.floor for t in group}),
                        "note": (
                            "이미 체결된 거래다. 지금 살 수 있는 매물이 아니다. "
                            "층·향·수리 상태 차이가 가격에 반영돼 있을 수 있다."
                        ),
                    },
                )
            )

        return listings
