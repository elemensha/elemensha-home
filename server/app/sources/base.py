"""소스 어댑터 공통 뼈대."""

from __future__ import annotations

import abc
import re
import xml.etree.ElementTree as ET

import httpx

from ..models import Listing, PropertyType

# 서울·경기 판정. 소스마다 표기가 제각각이라 앞부분만 보고 정규화한다.
_SIDO_ALIASES = {
    "서울": "서울특별시",
    "서울시": "서울특별시",
    "서울특별시": "서울특별시",
    "경기": "경기도",
    "경기도": "경기도",
    "인천": "인천광역시",
    "인천시": "인천광역시",
    "인천광역시": "인천광역시",
}

_TYPE_KEYWORDS = [
    (PropertyType.APARTMENT, ("아파트",)),
    (PropertyType.OFFICETEL, ("오피스텔",)),
    (PropertyType.VILLA, ("연립", "다세대", "빌라")),
    (PropertyType.HOUSE, ("단독", "다가구", "주택")),
    (PropertyType.COMMERCIAL, ("상가", "근린", "점포", "업무")),
    (PropertyType.LAND, ("토지", "대지", "임야", "전답")),
]


def normalize_sido(address: str) -> tuple[str, str]:
    """주소 문자열에서 (시도, 시군구)를 뽑는다."""
    if not address:
        return "", ""
    parts = address.split()
    if not parts:
        return "", ""

    sido = ""
    for alias, full in _SIDO_ALIASES.items():
        if parts[0].startswith(alias):
            sido = full
            break
    if not sido:
        sido = parts[0]

    sigungu = ""
    for token in parts[1:3]:
        if token.endswith(("시", "군", "구")):
            sigungu = token if not sigungu else f"{sigungu} {token}"
            if token.endswith(("군", "구")):
                break
    return sido, sigungu


def classify_property(*texts: str) -> PropertyType:
    blob = " ".join(t for t in texts if t)
    for ptype, keywords in _TYPE_KEYWORDS:
        if any(k in blob for k in keywords):
            return ptype
    return PropertyType.OTHER


_UNITS = (("조", 1_000_000_000_000), ("억", 100_000_000), ("만", 10_000))


def parse_krw(value: str | int | float | None) -> int | None:
    """'445,200,000원', '44520만원', '6억 3,600만' 을 전부 정수 원으로.

    단위가 섞인 표기가 핵심이다. 단위별로 따로 뽑아 더하지 않고 통째로
    숫자를 긁은 뒤 마지막 단위를 곱하면 '6억 3,600만'이 6조가 된다.
    """
    if value is None:
        return None
    if isinstance(value, (int, float)):
        return int(value)

    text = str(value).strip().replace(",", "").replace(" ", "")
    if not text:
        return None

    total = 0.0
    matched = False
    remainder = text
    for unit, multiplier in _UNITS:
        match = re.search(rf"([\d.]+){unit}", remainder)
        if match:
            total += float(match.group(1)) * multiplier
            remainder = remainder.replace(match.group(0), "", 1)
            matched = True

    if matched:
        # '6억3600' 처럼 단위 없이 남은 꼬리는 원 단위로 본다.
        tail = re.sub(r"[^\d]", "", remainder)
        if tail:
            total += float(tail)
        return int(total)

    digits = re.sub(r"[^\d.]", "", text)
    if not digits:
        return None
    return int(float(digits))


def parse_manwon(value: str | int | float | None) -> int | None:
    """'만원' 단위로만 오는 필드를 원으로. 실거래가 API의 dealAmount용.

    `parse_krw`를 쓰면 값에 '만'이 붙어 있을 때 배수가 두 번 먹는다.
    """
    if value is None:
        return None
    text = str(value).strip().replace(",", "").replace(" ", "")
    digits = re.sub(r"[^\d.]", "", text)
    if not digits:
        return None
    return int(float(digits) * 10_000)


def parse_area(value: str | float | None) -> float | None:
    if value is None:
        return None
    if isinstance(value, (int, float)):
        return float(value) or None
    digits = re.sub(r"[^\d.]", "", str(value))
    try:
        return float(digits) or None
    except ValueError:
        return None


def pick(item: dict, *candidates: str) -> str | None:
    """응답 필드명이 확실하지 않을 때 후보를 순서대로 시도한다.

    공공 API는 문서와 실제 태그명이 어긋나는 경우가 잦고, 개편 때 조용히
    바뀌기도 한다. 하나가 없으면 다음 것을 보게 해서 조용한 전멸을 막는다.
    """
    for key in candidates:
        value = item.get(key)
        if value not in (None, "", "-"):
            return str(value).strip()
    return None


def xml_items(payload: str, item_tag: str = "item") -> list[dict]:
    """공공데이터 표준 XML 응답에서 item 목록을 평평한 dict로 뽑는다."""
    root = ET.fromstring(payload)

    # 에러 응답을 조용히 빈 목록으로 넘기지 않는다.
    for tag in ("returnAuthMsg", "errMsg", "cmmMsgHeader"):
        node = root.find(f".//{tag}")
        if node is not None and (node.text or "").strip():
            reason = node.text.strip()
            detail = root.find(".//returnReasonCode")
            code = detail.text.strip() if detail is not None and detail.text else "?"
            raise RuntimeError(f"API 오류 [{code}] {reason}")

    header_code = root.find(".//resultCode")
    # 성공 코드는 기관마다 자릿수가 다르다. 실거래가는 "000", 온비드는 "00".
    # 앞자리 0을 걷어내고 남는 게 없으면 성공으로 본다.
    code_text = (header_code.text or "").strip() if header_code is not None else ""
    if code_text and code_text.lstrip("0") != "":
        msg = root.find(".//resultMsg")
        raise RuntimeError(
            f"API 오류 [{code_text}] {msg.text if msg is not None else ''}"
        )

    items = []
    for node in root.iter(item_tag):
        items.append({child.tag: (child.text or "").strip() for child in node})
    return items


class ListingSource(abc.ABC):
    """모든 소스 어댑터의 계약."""

    name: str

    def __init__(self, service_key: str, timeout: float = 20.0) -> None:
        self.service_key = service_key
        self.timeout = timeout

    @property
    def configured(self) -> bool:
        return bool(self.service_key)

    @abc.abstractmethod
    async def fetch(self, client: httpx.AsyncClient) -> list[Listing]:
        """이번 폴링에서 볼 수 있는 물건 전부. 중복 제거는 호출자가 한다."""

    async def stream(self, client: httpx.AsyncClient):
        """페이지 단위로 흘려보낸다.

        전국 수집이 1.5만 건이 되면서 리스트로 다 들고 있으면 956MB VM 에서
        메모리 한도(280MB)를 넘겼다. 받는 대로 저장하면 한 페이지치만 든다.
        기본 구현은 fetch() 를 그대로 쓰므로 어댑터가 필요할 때만 재정의한다.
        """
        for listing in await self.fetch(client):
            yield listing

    async def probe(self, client: httpx.AsyncClient) -> dict:
        """응답 첫 건의 원본 필드를 그대로 돌려준다.

        키를 처음 발급받았을 때 실제 태그명이 어댑터의 가정과 맞는지
        눈으로 확인하는 용도. 필드명이 틀리면 여기서 바로 드러난다.
        """
        listings = await self.fetch(client)
        return listings[0].raw if listings else {}
