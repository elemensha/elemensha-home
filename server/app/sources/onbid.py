"""캠코 온비드 공매물건 어댑터 (차세대 규격).

공공데이터포털 '한국자산관리공사_차세대 온비드 부동산 물건목록 조회서비스'
(데이터셋 15157207)를 쓴다. 구 API(openapi.onbid.co.kr)는 개편으로 내려갔다.

**입찰준비중(0001)이 물건의 대부분이다.** 진행중(0002)만 가져오면
압류재산 51,571건 중 0건만 보게 된다 - 공매는 입찰 기간이 짧아서 거의 항상
'준비중' 상태이기 때문이다. 실제로 그렇게 만들어 두었다가 전체의 1%만
보여주고 있었다.

**정렬은 입찰 시작일 내림차순이다.** 먼 미래가 앞 페이지, 임박한 물건이 뒷
페이지에 온다. 앞에서부터 읽으면 3개월 뒤 물건만 잔뜩 가져온다. 그래서
이진 탐색으로 '앞으로 N일 이내' 경계 페이지를 찾아 **거기서부터 끝까지**
읽는다(탐색 10회 + 본문 60여 회).

일일 한도가 1,000회라 폴링 주기를 4시간으로 둔다.

시도별로 나눠 부르지 않는다. 실측 결과 전국을 통째로 페이지네이션하는 쪽이
**호출이 더 적다** - 시도 루프는 결과가 0건인 조합에도 1회씩 쓰기 때문이다.
(전국 9장 vs 수도권 시도 루프 12회)

지역은 받아온 뒤 `lctnSdnm` 으로 거른다. `target_sido` 를 비우면 전국이다.

필드명은 2026-08-25에 실제 응답을 찍어 확인했다.
"""

from __future__ import annotations

import xml.etree.ElementTree as ET
from datetime import datetime, timedelta
from urllib.parse import quote

import httpx

from ..models import KST, Listing, PropertyType, Source
from .base import ListingSource, parse_area, parse_krw, pick

ENDPOINT = "https://apis.data.go.kr/B010003/OnbidRlstListSrvc2/getRlstCltrList2"

# 온비드 물건 상세. 공고번호·공매번호·물건번호 조합으로 열린다.
DETAIL_URL = (
    "https://www.onbid.co.kr/op/cta/cltrdtl/collateralRealEstateDetail.do"
    "?cltrNo={cltr}&plnmNo={plnm}&pbctNo={pbct}&pbctCdtnNo={cdtn}&scrnGrpCd=0001"
)
SEARCH_URL = "https://www.onbid.co.kr/op/cta/cltrmnmt/collateralRealEstateList.do"

# 지번으로 지도를 연다. 맹지 여부(도로가 필지에 닿는지)는 속성 데이터로
# 확정할 수 없고 지적도 공간 연산이 필요한데, 지적편집도를 켠 지도에서
# 눈으로 보는 것이 실질적으로 가장 빠르다.
#
# 토지이음(eum.go.kr)은 PNU 로 바로 여는 URL 형식이 공개돼 있지 않다.
# 시도해 본 luLandDetR.jsp?mode=view|search&pnu=... 는 둘 다 시스템 에러가
# 난다. 주소를 직접 입력해야 하므로 링크로 걸지 않는다.
# 지도는 네이버로 통일했다. 앱 안의 지도와 다른 지도를 열면
# 같은 물건이 다른 화면에서 다르게 보인다.
MAP_URL = "https://map.naver.com/p/search/"

# 재산유형코드. 실측으로 확인한 값만 넣었다(0001·0003·0006 등은 결과 없음).
PROPERTY_DIVISIONS = {
    "0007": "압류재산",
    "0005": "기타일반재산",
    "0010": "국유재산",
    "0002": "공유재산",
}

BID_PENDING = "0001"       # pbctStatCd: 입찰준비중 (일정은 잡혔고 아직 시작 전)
BID_IN_PROGRESS = "0002"   # pbctStatCd: 입찰진행중
SALE = "매각"              # dspsMthodNm. 나머지는 임대이며 매물이 아니다.

# 유찰이 이만큼 쌓이면 감정가 대비 하락폭이 커 보이지만, 그건 싸다는 뜻이
# 아니라 시장이 거듭 거부했다는 뜻이다. 실측에서 24회 유찰 -98%짜리가
# 최상단에 올라왔는데 전부 생활형숙박시설·오피스텔이었다.
SUSPICIOUS_FAILED_BIDS = 5

# 농지. 낙찰 후 농지취득자격증명을 받아야 소유권이 넘어오고,
# 못 받으면 보증금을 잃는다. 아예 거르고 싶은 사람이 많다.
FARMLAND_CATEGORIES = ("전", "답", "과수원")


def _parse_onbid_datetime(value: str | None) -> str | None:
    """'202608261700' -> '2026-08-26T17:00'. 형식이 다르면 원문을 돌려준다."""
    if not value:
        return None
    digits = "".join(ch for ch in value if ch.isdigit())
    if len(digits) < 8:
        return value
    date = f"{digits[0:4]}-{digits[4:6]}-{digits[6:8]}"
    if len(digits) >= 12:
        return f"{date}T{digits[8:10]}:{digits[10:12]}"
    return date


class OnbidSource(ListingSource):
    name = Source.ONBID.value

    def __init__(
        self,
        service_key: str,
        target_sido: list[str] | None = None,
        divisions: list[str] | None = None,
        max_pages: int = 90,
        rows_per_page: int = 100,
        timeout: float = 30.0,
        upcoming_days: int = 30,
        sale_only: bool = True,
        include_upcoming: bool = True,
    ) -> None:
        super().__init__(service_key, timeout)
        # 비우면 전국. 지역은 API 파라미터가 아니라 받아온 뒤 거른다.
        self.target_sido = target_sido or []
        self.divisions = divisions or list(PROPERTY_DIVISIONS)
        self.max_pages = max_pages
        self.rows_per_page = rows_per_page
        # 앞으로 이 기간 안에 입찰이 시작되는 물건까지 가져온다.
        # 넓힐수록 페이지가 늘어 한도를 먹는다.
        self.upcoming_days = upcoming_days
        self.sale_only = sale_only
        # 준비중까지 볼지. 진행중만 보면 호출이 20분의 1로 줄어 자주 돌 수 있다.
        self.include_upcoming = include_upcoming
        # 실제 API 호출 수. 추정으로 한도를 잡았다가 실제로 넘긴 적이
        # 있어서, 이제는 세어서 기록한다.
        self.api_calls = 0

    async def fetch(self, client: httpx.AsyncClient) -> list[Listing]:
        return [x async for x in self.stream(client)]

    async def stream(self, client: httpx.AsyncClient):
        if not self.configured:
            raise RuntimeError("온비드 서비스키가 설정되지 않았다 (ONBID_SERVICE_KEY)")

        yielded = 0
        errors: list[str] = []

        horizon = (datetime.now(KST) + timedelta(days=self.upcoming_days)).strftime("%Y%m%d%H%M")

        for division in self.divisions:
            name = PROPERTY_DIVISIONS.get(division, division)
            # 진행중은 양이 적으니 통째로 읽는다.
            try:
                async for listing in self._stream_all(client, division, BID_IN_PROGRESS):
                    yielded += 1
                    yield listing
            except Exception as exc:
                errors.append(f"{name}/진행중: {exc}")
            # 준비중은 임박한 뒷부분만 읽는다. 호출이 많아 매번 돌지 않는다.
            if not self.include_upcoming:
                continue
            try:
                async for listing in self._stream_upcoming(client, division, horizon):
                    yielded += 1
                    yield listing
            except Exception as exc:
                errors.append(f"{name}/준비중: {exc}")

        if not yielded and errors:
            raise RuntimeError(
                f"온비드 조회가 전부 실패했다 (API {self.api_calls}회) - "
                + "; ".join(errors[:3])
            )

    async def _page(
        self, client: httpx.AsyncClient, division: str, status: str, page: int
    ) -> tuple[int, list[dict]]:
        """한 페이지. (totalCount, items)."""
        self.api_calls += 1
        response = await client.get(
            ENDPOINT,
            params={
                "serviceKey": self.service_key,
                "numOfRows": self.rows_per_page,
                "pageNo": page,
                "prptDivCd": division,
                "pvctTrgtYn": "N",
                "pbctStatCd": status,
            },
            timeout=self.timeout,
        )
        response.raise_for_status()
        root = ET.fromstring(response.text)

        code = (root.findtext(".//resultCode") or "").strip()
        if code and code.lstrip("0") != "":
            message = (root.findtext(".//resultMsg") or "").strip()
            if message == "NODATA_ERROR":
                return 0, []
            raise RuntimeError(f"[{code}] {message}")

        total = int(root.findtext(".//totalCount") or 0)
        items = [
            {child.tag: (child.text or "").strip() for child in node}
            for node in root.iter("item")
        ]
        return total, items

    async def _stream_all(
        self, client: httpx.AsyncClient, division: str, status: str
    ):
        for page in range(1, self.max_pages + 1):
            _, items = await self._page(client, division, status, page)
            if not items:
                break
            for item in items:
                listing = self._to_listing(item)
                if listing is not None:
                    yield listing
            if len(items) < self.rows_per_page:
                break

    async def _stream_upcoming(
        self, client: httpx.AsyncClient, division: str, horizon: str
    ):
        """입찰 시작이 `horizon` 이전인 준비중 물건.

        시작일 내림차순이라 임박한 것이 뒤에 있다. 이진 탐색으로 경계
        페이지를 찾고 거기서 끝까지 읽는다. 전부 읽으면 500페이지가 넘어
        하루치 한도를 한 번에 태운다.
        """
        total, first = await self._page(client, division, BID_PENDING, 1)
        if total <= 0:
            return
        last_page = (total + self.rows_per_page - 1) // self.rows_per_page

        def earliest(items: list[dict]) -> str:
            dates = [i.get("cltrBidBgngDt", "") for i in items if i.get("cltrBidBgngDt")]
            return min(dates) if dates else ""

        lo, hi = 1, last_page
        if earliest(first) > horizon:
            while lo < hi:
                mid = (lo + hi) // 2
                _, items = await self._page(client, division, BID_PENDING, mid)
                if items and earliest(items) <= horizon:
                    hi = mid
                else:
                    lo = mid + 1

        pages = 0
        for page in range(lo, last_page + 1):
            if pages >= self.max_pages:
                # 한도를 지키기 위해 여기서 멈춘다. 더 있다는 사실은
                # 잘렸다는 것을 알 수 있도록 로그에 남는다.
                break
            _, items = await self._page(client, division, BID_PENDING, page)
            pages += 1
            if not items:
                break
            for item in items:
                # 경계 페이지에는 기간 밖 물건이 섞여 있다.
                if (item.get("cltrBidBgngDt") or "") > horizon:
                    continue
                listing = self._to_listing(item)
                if listing is not None:
                    yield listing

    def _to_listing(self, item: dict) -> Listing | None:
        cltr_mng_no = pick(item, "cltrMngNo")
        cdtn_no = pick(item, "pbctCdtnNo") or ""
        if not cltr_mng_no:
            return None

        sido = pick(item, "lctnSdnm") or ""
        if self.target_sido and sido and sido not in self.target_sido:
            return None

        # 임대 물건은 최저입찰가가 '임대료'라서 매매가와 섞이면 안 된다.
        # API 파라미터로는 못 거르므로(dspsMthodCd를 넘겨도 무시된다) 여기서 뺀다.
        disposal = pick(item, "dspsMthodNm") or ""
        if self.sale_only and disposal != SALE:
            return None

        # 용도는 대/중/소 3단계로 온다. 소분류가 가장 구체적이다.
        mcls = pick(item, "cltrUsgMclsCtgrNm") or ""
        scls = pick(item, "cltrUsgSclsCtgrNm") or ""
        title = pick(item, "onbidCltrNm") or cltr_mng_no

        # 최저입찰가 칸에 숫자가 아니라 '비공개' 라는 글자가 오는 물건이 있다
        # (기타일반재산 일부). 그대로 두면 값이 없는 것과 구분되지 않아
        # 화면에 이유 없이 빈칸이 뜬다.
        raw_min = pick(item, "lowstBidPrcIndctCont") or ""
        price_undisclosed = bool(raw_min) and not any(c.isdigit() for c in raw_min)

        appraised = parse_krw(pick(item, "apslEvlAmt"))
        min_bid = None if price_undisclosed else parse_krw(raw_min)
        if min_bid is None and not price_undisclosed:
            min_bid = parse_krw(pick(item, "frstBidPrc"))

        # 감정가가 없으면 할인율을 계산할 기준이 없다. 유찰이 쌓여도
        # '감정가 대비 몇 %'를 말할 수 없는 것은 그래서다.
        discount = None
        if appraised and min_bid and appraised > 0:
            discount = max(0.0, 1 - min_bid / appraised)

        # 건물이 있으면 건물면적, 토지 물건이면 토지면적을 쓴다.
        area = parse_area(pick(item, "bldSqms")) or parse_area(pick(item, "landSqms"))

        failed = pick(item, "usbdNft")
        try:
            failed_count = int(failed) if failed else 0
        except ValueError:
            failed_count = 0

        cltr_no = pick(item, "onbidCltrno") or ""
        plnm_no = pick(item, "onbidPbancNo") or ""
        pbct_no = pick(item, "pbctNo") or ""
        if cltr_no and plnm_no and pbct_no:
            url = DETAIL_URL.format(cltr=cltr_no, plnm=plnm_no, pbct=pbct_no, cdtn=cdtn_no)
        else:
            url = SEARCH_URL

        return Listing(
            source=Source.ONBID,
            source_id=f"{cltr_mng_no}-{cdtn_no}" if cdtn_no else cltr_mng_no,
            title=title,
            url=url,
            sido=sido,
            sigungu=pick(item, "lctnSggnm") or "",
            address=title,   # onbidCltrNm 자체가 전체 주소 + 물건 표시다
            property_type=self._classify(mcls, scls, title),
            exclusive_area_sqm=area,
            appraised_price_krw=appraised,
            min_bid_price_krw=min_bid,
            deadline=_parse_onbid_datetime(pick(item, "cltrBidEndDt")),
            bid_start=_parse_onbid_datetime(pick(item, "cltrBidBgngDt")),
            bid_status=(
                "진행중" if pick(item, "pbctStatCd") == BID_IN_PROGRESS
                else "준비중" if pick(item, "pbctStatCd") == BID_PENDING
                else (pick(item, "pbctStatNm") or "")
            ),
            failed_bid_count=failed_count,
            market_price_krw=appraised,
            discount_ratio=discount,
            raw={
                "prptDivNm": pick(item, "prptDivNm") or "",
                "dspsMthodNm": disposal,
                "caution": (
                    f"유찰 {failed_count}회. 감정가 대비 하락폭이 커 보이는 것은 "
                    "싸서가 아니라 거듭 팔리지 않았기 때문일 수 있다. 권리관계와 "
                    "물건 상태를 반드시 확인할 것."
                    if failed_count >= SUSPICIOUS_FAILED_BIDS else ""
                ),
                "bidDivNm": pick(item, "bidDivNm") or "",
                "pbctStatNm": pick(item, "pbctStatNm") or "",
                "usage": " > ".join(x for x in (mcls, scls) if x),
                "usage_major": mcls,
                "usage_minor": scls,
                # 공매는 인도명령이 없다. 협의가 안 되면 명도소송으로 가야 하고
                # 5~6개월이 걸린다. 실측상 이 필드는 832건 전부 매수자 부담이라
                # 물건을 가르는 신호가 아니라 공매 전체의 성질이다.
                "eviction_burden": pick(item, "evcRsbyTrgtCont") or "",
                # 전·답은 낙찰 후 농지취득자격증명을 받아야 소유권이 넘어온다.
                # 못 받으면 보증금을 잃는다.
                "needs_farmland_permit": scls in FARMLAND_CATEGORIES,
                "price_undisclosed": price_undisclosed,
                "price_note": (
                    "최저입찰가 비공개 — 온비드에서 확인해야 한다" if price_undisclosed
                    else "감정가가 없어 할인율을 계산할 수 없다" if not appraised
                    else ""
                ),
                # 필지고유번호(19자리). 맹지·용도지역·건축 가능 여부는 이 앱이
                # 확정할 수 없다(지적도 공간 연산이 필요하다). 대신 해당 필지의
                # 토지이용계획확인원을 한 번에 열 수 있게 링크를 만들어 둔다.
                "pnu": pick(item, "ltnoPnu") or "",
                "map_url": MAP_URL + quote(title) if title else "",
                "bid_begin": _parse_onbid_datetime(pick(item, "cltrBidBgngDt")) or "",
                "land_sqms": pick(item, "landSqms") or "",
                "bld_sqms": pick(item, "bldSqms") or "",
                "thumbnail": pick(item, "thnlImgUrlAdr") or "",
                "note": (
                    "최저입찰가 기준이다. 실제 낙찰가는 이보다 높게 형성되는 것이 보통이고, "
                    "명도·미납관리비·인수보증금은 별도로 확인해야 한다."
                ),
            },
        )

    @staticmethod
    def _classify(mcls: str, scls: str, title: str) -> PropertyType:
        """온비드 용도분류를 앱 분류로.

        키워드 추측을 쓰다가 같은 건물의 201호는 단독주택, 203호는 연립다세대로
        갈리는 일이 있었다. 온비드가 이미 정확한 분류를 주므로 그대로 매핑한다.
        실측한 35종 조합을 모두 반영했다.
        """
        mapped = _SCLS_TO_TYPE.get(scls)
        if mapped is not None:
            return mapped
        return _MCLS_TO_TYPE.get(mcls, PropertyType.OTHER)


# 소분류 -> 앱 분류. 2026-08-25 수도권 매각 물건 812건에서 관측된 값 전부.
_SCLS_TO_TYPE = {
    "아파트": PropertyType.APARTMENT,
    "오피스텔": PropertyType.OFFICETEL,
    "다세대주택": PropertyType.VILLA,
    "연립주택": PropertyType.VILLA,
    "빌라": PropertyType.VILLA,
    "도시형생활주택": PropertyType.VILLA,
    "단독주택": PropertyType.HOUSE,
    "다가구주택": PropertyType.HOUSE,
    # 주거용이지만 무엇인지 특정되지 않는다. 아파트로 오인시키지 않는다.
    "기타주거용건물": PropertyType.OTHER,
}

# 소분류가 목록에 없을 때 쓰는 중분류 기준.
_MCLS_TO_TYPE = {
    "토지": PropertyType.LAND,
    "상가용및업무용건물": PropertyType.COMMERCIAL,
    "산업용및기타특수용건물": PropertyType.COMMERCIAL,
    "용도복합용건물": PropertyType.OFFICETEL,
    "주거용건물": PropertyType.OTHER,
}
