"""온비드 부동산 물건상세 어댑터.

공공데이터포털 '차세대 온비드 부동산 물건상세 조회서비스'(15157247).
물건관리번호로 한 건씩 조회한다.

**일일 한도가 1,000회이고 물건마다 한 번씩 든다.** 목록 폴링만으로도
하루 432회를 쓰므로 상세를 미리 다 채우면 금방 한도에 닿는다. 그래서
사용자가 물건을 열었을 때만 가져오고 결과를 캐시한다.

여기서 얻는 것 중 목록에는 없는 것:
- 유의사항(pytnMtrsCont) - 점유자·분묘·유치권이 적히는 자리다
- 이용현황(utlzPscdCont) - 실제로 뭐가 있는지
- 위치 및 부근현황(locVntyPscdCont) - 도로 접근성이 기술되기도 한다
- 감정평가 내역과 감정평가서 URL
- 등기 권리 목록, 사진, 위치도
"""

from __future__ import annotations

import xml.etree.ElementTree as ET

import httpx

from .base import parse_krw, pick

ENDPOINT = "https://apis.data.go.kr/B010003/OnbidRlstDtlSrvc2/getRlstDtlInf2"

# 유의사항·이용현황에서 찾아낼 위험 신호. 공매는 인도명령이 없어서
# 점유자가 있으면 협의가 깨졌을 때 명도소송(5~6개월)으로 간다.
#
# (계열, 찾을 문구, 표시할 말). 같은 계열에서는 **먼저 걸린 것만** 쓴다.
# 구체적인 문구를 앞에 두어야 "임대차 미확인"이 "임대차"에 먹히지 않는다.
# 실제로 '임차'로만 찾다가 '임대차 미확인'을 통째로 놓쳤다.
RISK_PATTERNS: list[tuple[str, str, str]] = [
    ("tenancy", "임대차 미확인", "임대차 미확인 - 점유 여부를 알 수 없다"),
    ("tenancy", "임대차 관계 미상", "임대차 미상 - 점유 여부를 알 수 없다"),
    ("tenancy", "대항력", "대항력 있는 임차인 가능성 - 보증금 인수 위험"),
    ("tenancy", "임대차", "임대차 관련 기재"),
    ("tenancy", "임차", "임차인 관련 기재"),
    ("occupancy", "점유", "점유자 있음"),
    ("occupancy", "명도", "명도 관련 기재"),
    ("lien", "유치권", "유치권 주장 가능성"),
    ("grave", "분묘", "분묘 있음 - 개장·이장 부담"),
    ("superficies", "법정지상권", "법정지상권 성립 여지"),
    ("access", "맹지", "맹지로 기재됨"),
    ("access", "도로에 접하지", "도로에 접하지 않음"),
    ("extra", "제시외", "제시외 건물 - 감정에서 빠진 구조물"),
    ("unregistered", "미등기", "미등기 부분 있음"),
]


def detect_risks(text: str) -> list[str]:
    """위험 신호를 계열별로 하나씩만 뽑는다."""
    found: dict[str, str] = {}
    for family, needle, label in RISK_PATTERNS:
        if family not in found and needle in text:
            found[family] = label
    return list(found.values())


def _text_list(node: ET.Element | None, tag: str) -> list[str]:
    if node is None:
        return []
    return [(e.text or "").strip() for e in node.iter(tag) if (e.text or "").strip()]


def _rows(item: ET.Element, list_tag: str, fields: dict[str, str]) -> list[dict]:
    """반복 목록을 dict 리스트로. 값들이 형제로 평평하게 오므로 묶어준다."""
    container = item.find(list_tag)
    if container is None:
        return []
    columns = {label: _text_list(container, tag) for tag, label in fields.items()}
    length = max((len(v) for v in columns.values()), default=0)
    return [
        {label: (values[i] if i < len(values) else "") for label, values in columns.items()}
        for i in range(length)
    ]


async def fetch_detail(
    client: httpx.AsyncClient,
    service_key: str,
    cltr_mng_no: str,
    pbct_cdtn_no: str = "",
    timeout: float = 25.0,
) -> dict:
    """물건 하나의 상세. 실패하면 예외를 올린다(조용히 빈 dict 를 주지 않는다)."""
    params = {"serviceKey": service_key, "cltrMngNo": cltr_mng_no}
    if pbct_cdtn_no:
        params["pbctCdtnNo"] = pbct_cdtn_no

    response = await client.get(ENDPOINT, params=params, timeout=timeout)
    response.raise_for_status()
    root = ET.fromstring(response.text)

    code = (root.findtext(".//resultCode") or "").strip()
    if code and code.lstrip("0") != "":
        raise RuntimeError(f"[{code}] {root.findtext('.//resultMsg') or ''}")

    item = root.find(".//item")
    if item is None:
        raise RuntimeError("상세 정보가 비어 있다")

    flat = {ch.tag: (ch.text or "").strip() for ch in item if not len(ch)}

    notes = pick(flat, "pytnMtrsCont") or ""
    usage = pick(flat, "utlzPscdCont") or ""
    vicinity = pick(flat, "locVntyPscdCont") or ""
    blob = " ".join((notes, usage, vicinity))

    return {
        "cltr_mng_no": cltr_mng_no,
        "address": pick(flat, "zadrNm", "onbidCltrNm") or "",
        # 사람이 읽어야 하는 세 덩어리. 여기에 위험이 적혀 있다.
        "notes": notes,                 # 유의사항
        "usage_status": usage,          # 이용현황
        "vicinity": vicinity,           # 위치 및 부근현황
        "risk_flags": detect_risks(blob),
        "eviction_burden": pick(flat, "evcRsbyTrgtCont") or "",
        "rent_period": pick(flat, "rentPerdCont") or "",
        "distribution_deadline": pick(flat, "dtbtRqrEdtmCont") or "",
        "delegating_org": pick(flat, "rqstOrgNm") or "",
        "first_notice_date": pick(flat, "frstPbancYmd") or "",
        "failed_bid_count": pick(flat, "usbdNft") or "",
        "appraised_price_krw": parse_krw(pick(flat, "apslEvlAmt")),
        "min_bid_price_krw": parse_krw(pick(flat, "lowstBidPrcIndctCont")),
        "areas": _rows(item, "sqmsList", {"clandCont": "구분", "sqmsCont": "면적"}),
        "appraisals": _rows(item, "apslEvlClgList", {
            "apslEvlYmd": "평가일", "apslEvlOrgNm": "평가기관",
            "apslEvlAmt": "평가액", "urlAdr": "감정평가서",
        }),
        # 임대차 정보. 전입일자가 여기 있고, 이게 말소기준권리보다 빠르면
        # 낙찰자가 보증금을 떠안는다. 안 읽으면 그 판단을 아예 못 한다.
        "tenancies": _rows(item, "leasInfList", {
            "irstDivNm": "구분", "cltrInprNm": "이름",
            "mvinYmd": "전입일", "cfmtnYmd": "확정일자",
            "bidGrteeAmt": "보증금", "mthrAmt": "차임",
            "convGrteeAmt": "환산보증금",
        }),
        "rights": _rows(item, "rgstPrmrInfList", {
            "irstDivNm": "구분", "cltrInprNm": "권리자",
            "rgstYmd": "등기일", "inprStngAmt": "설정액",
        }),
        "photos": _text_list(item.find("potoUrlList"), "urlAdr"),
        "location_map": pick(flat, "lrmUrlAdrList") or "",
    }
