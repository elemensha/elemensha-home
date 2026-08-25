"""캠코 온비드 공매물건 어댑터 (차세대 규격).

공공데이터포털 '한국자산관리공사_차세대 온비드 부동산 물건목록 조회서비스'
(데이터셋 15157207)를 쓴다. 구 API(openapi.onbid.co.kr)는 개편으로 내려갔다.

**일일 한도가 1,000회뿐이다.** 전체 압류재산만 55,086건이라 필터 없이
페이지네이션하면 하루치 할당량을 한 번에 태운다. 그래서 두 가지를 건다.

- `lctnSdnm` (시도명) - 실측으로 동작 확인. 55,086 -> 서울 4,528
- `pbctStatCd=0002` (입찰진행중) - 이미 끝난 물건을 걷어낸다

수도권 3개 시도 x 재산유형 5종 = 1회 폴링 약 18회 호출. 시간당 돌려도
하루 432회로 여유가 있다.

필드명은 2026-08-25에 실제 응답을 찍어 확인했다.
"""

from __future__ import annotations

import xml.etree.ElementTree as ET
from urllib.parse import quote

import httpx

from ..models import Listing, PropertyType, Source
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
MAP_URL = "https://map.kakao.com/?q="

# 재산유형코드. 실측으로 확인한 값만 넣었다(0001·0003·0006 등은 결과 없음).
PROPERTY_DIVISIONS = {
    "0007": "압류재산",
    "0005": "기타일반재산",
    "0010": "국유재산",
    "0002": "공유재산",
}

BID_IN_PROGRESS = "0002"   # pbctStatCd: 입찰진행중
SALE = "매각"              # dspsMthodNm. 나머지는 임대이며 매물이 아니다.

# 유찰이 이만큼 쌓이면 감정가 대비 하락폭이 커 보이지만, 그건 싸다는 뜻이
# 아니라 시장이 거듭 거부했다는 뜻이다. 실측에서 24회 유찰 -98%짜리가
# 최상단에 올라왔는데 전부 생활형숙박시설·오피스텔이었다.
SUSPICIOUS_FAILED_BIDS = 5


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
        max_pages: int = 6,
        rows_per_page: int = 100,
        timeout: float = 25.0,
        only_in_progress: bool = True,
        sale_only: bool = True,
    ) -> None:
        super().__init__(service_key, timeout)
        self.target_sido = target_sido or ["서울특별시", "경기도", "인천광역시"]
        self.divisions = divisions or list(PROPERTY_DIVISIONS)
        self.max_pages = max_pages
        self.rows_per_page = rows_per_page
        self.only_in_progress = only_in_progress
        self.sale_only = sale_only

    async def fetch(self, client: httpx.AsyncClient) -> list[Listing]:
        if not self.configured:
            raise RuntimeError("온비드 서비스키가 설정되지 않았다 (ONBID_SERVICE_KEY)")

        listings: list[Listing] = []
        errors: list[str] = []

        for division in self.divisions:
            for sido in self.target_sido:
                try:
                    listings.extend(await self._fetch_slice(client, division, sido))
                except Exception as exc:
                    # 한 조합이 실패해도 나머지는 계속 모은다. 전부 실패하면 아래에서 드러난다.
                    errors.append(f"{PROPERTY_DIVISIONS.get(division, division)}/{sido}: {exc}")

        if not listings and errors:
            raise RuntimeError("온비드 조회가 전부 실패했다 - " + "; ".join(errors[:3]))
        return listings

    async def _fetch_slice(
        self, client: httpx.AsyncClient, division: str, sido: str
    ) -> list[Listing]:
        collected: list[Listing] = []
        for page in range(1, self.max_pages + 1):
            params = {
                "serviceKey": self.service_key,
                "numOfRows": self.rows_per_page,
                "pageNo": page,
                "prptDivCd": division,
                "pvctTrgtYn": "N",
                "lctnSdnm": sido,
            }
            if self.only_in_progress:
                params["pbctStatCd"] = BID_IN_PROGRESS

            response = await client.get(ENDPOINT, params=params, timeout=self.timeout)
            response.raise_for_status()
            root = ET.fromstring(response.text)

            code = (root.findtext(".//resultCode") or "").strip()
            if code and code.lstrip("0") != "":
                message = (root.findtext(".//resultMsg") or "").strip()
                if message == "NODATA_ERROR":
                    break
                raise RuntimeError(f"[{code}] {message}")

            items = [
                {child.tag: (child.text or "").strip() for child in node}
                for node in root.iter("item")
            ]
            if not items:
                break

            for item in items:
                listing = self._to_listing(item)
                if listing is not None:
                    collected.append(listing)

            if len(items) < self.rows_per_page:
                break

        return collected

    def _to_listing(self, item: dict) -> Listing | None:
        cltr_mng_no = pick(item, "cltrMngNo")
        cdtn_no = pick(item, "pbctCdtnNo") or ""
        if not cltr_mng_no:
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

        appraised = parse_krw(pick(item, "apslEvlAmt"))
        min_bid = parse_krw(pick(item, "lowstBidPrcIndctCont", "frstBidPrc"))

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
            sido=pick(item, "lctnSdnm") or "",
            sigungu=pick(item, "lctnSggnm") or "",
            address=title,   # onbidCltrNm 자체가 전체 주소 + 물건 표시다
            property_type=self._classify(mcls, scls, title),
            exclusive_area_sqm=area,
            appraised_price_krw=appraised,
            min_bid_price_krw=min_bid,
            deadline=_parse_onbid_datetime(pick(item, "cltrBidEndDt")),
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
                "needs_farmland_permit": scls in ("전", "답", "과수원"),
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
