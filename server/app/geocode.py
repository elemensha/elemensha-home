"""주소를 좌표로 바꾼다.

온비드 주소는 지번 뒤에 건물명·동·층·호수·용도가 줄줄이 붙어 있다.
그대로 넣으면 지오코더가 못 찾는다. 지번까지만 잘라내는 것이 핵심이다.

    서울특별시 구로구 구로동 339-39 제에이동 제2층 제203호 근린생활시설
    -> 서울특별시 구로구 구로동 339-39

같은 건물의 여러 호실이 한 지번을 공유하므로, 잘라낸 주소를 키로
캐시하면 호출이 크게 줄어든다. 실패도 캐시한다 - 못 찾는 주소를
매번 다시 물어보면 한도만 먹는다.
"""

from __future__ import annotations

import asyncio
import logging
import re

import httpx

LOGGER = logging.getLogger("elemensha.home.geocode")

# 네이버 클라우드 플랫폼 지오코딩. 지도도 네이버라 계정을 하나만 만든다.
NAVER_GEOCODE = "https://maps.apigw.ntruss.com/map-geocode/v2/geocode"

# 괄호·꺾쇠 안의 부연 설명. 「오정 군부대 일원 도시개발사업」 같은 것.
_PARENTHETICAL = re.compile(r"[（(\[［【「][^）)\]］】」]*[）)\]］】」]")

# 지번 한 덩어리. '산18-17', '339-39', '155-1외' 를 모두 잡는다.
_LOT = re.compile(r"^산?\d+(-\d+)?(외)?$")

# 지번 앞에 오는 법정동 단위. 이게 있어야 뒤의 숫자를 지번으로 본다.
_DONG_SUFFIX = ("동", "리", "가", "읍", "면", "로", "길")


def clean_address(address: str) -> str:
    """지번까지만 남긴다. 못 자르면 원본을 그대로 돌려준다.

    억지로 자르면 엉뚱한 곳을 찍는다. 못 찾고 지도에서 빠지는 편이 낫다.
    """
    text = _PARENTHETICAL.sub(" ", address or "")
    text = text.replace("　", " ")
    # '용정리 1013, 산209' 나 '903-29,30' 처럼 쉼표로 다른 필지가 붙는다.
    # 앞의 것만 쓴다. 구두점을 떼지 않으면 '1013,' 이 지번으로 안 잡힌다.
    text = re.sub(r"(\d)\s*,\s*(?=\d)", r"\1 ", text)
    # '산 190-1' 은 '산190-1' 과 같은 뜻인데 토큰이 갈라진다.
    text = re.sub(r"\b산\s+(?=\d)", "산", text)
    tokens = [t.strip(",.·") for t in text.split()]
    # '598번지' 의 접미사를 뗀다. 지번 자체는 그대로다.
    tokens = [re.sub(r"번지$", "", t) for t in tokens]
    tokens = [t for t in tokens if t]

    for i, token in enumerate(tokens):
        if not _LOT.match(token):
            continue
        # 지번은 법정동 뒤에 온다. 앞 토큰을 보고 확인한다. 확인 없이
        # 첫 숫자에서 자르면 '더페이스3차' 같은 건물명에 걸린다.
        if i == 0:
            continue
        prev = tokens[i - 1]
        if not prev.endswith(_DONG_SUFFIX):
            continue
        return " ".join(tokens[: i + 1]).rstrip("외")

    return " ".join(tokens)


class Geocoder:
    """주소 -> 좌표. 네이버 클라우드 플랫폼 지오코딩.

    지번 주소만 다룬다. 지번이 없는 이름뿐인 주소('천왕2지구 주차장3')는
    못 찾고 넘어간다 - 실제 주소 250건 중 2건이라 지도를 위해 엉뚱한
    좌표를 만들어 낼 이유가 없다.
    """

    def __init__(self, key_id: str, key_secret: str, store=None, delay: float = 0.05) -> None:
        self.key_id = (key_id or "").strip()
        self.key_secret = (key_secret or "").strip()
        self.store = store
        self.delay = delay
        self.api_calls = 0

    @property
    def configured(self) -> bool:
        return bool(self.key_id and self.key_secret)

    async def _query(self, client: httpx.AsyncClient, query: str):
        self.api_calls += 1
        response = await client.get(
            NAVER_GEOCODE,
            params={"query": query},
            headers={
                "X-NCP-APIGW-API-KEY-ID": self.key_id,
                "X-NCP-APIGW-API-KEY": self.key_secret,
            },
            timeout=10.0,
        )
        response.raise_for_status()
        data = response.json()
        found = data.get("addresses") or []
        if not found:
            return None
        first = found[0]
        try:
            # 네이버는 x 가 경도, y 가 위도다. 뒤집으면 지도에 바다가 찍힌다.
            return float(first["y"]), float(first["x"])
        except (KeyError, TypeError, ValueError):
            return None

    async def locate(self, client: httpx.AsyncClient, address: str):
        """(lat, lon) 또는 None. 캐시를 먼저 본다."""
        key = clean_address(address)
        if not key:
            return None

        if self.store is not None:
            hit = self.store.get_geocode(key)
            if hit is not None:
                # (None, None) 은 '전에 찾아봤지만 없었다'는 뜻이다.
                return hit if hit[0] is not None else None

        try:
            found = await self._query(client, key)
        except Exception as exc:
            # 네트워크·한도 문제는 캐시하지 않는다. 캐시하면 키를 고친
            # 뒤에도 영영 안 찾는다.
            LOGGER.warning("지오코딩 실패 %r: %s", key, exc)
            return None

        if self.store is not None:
            self.store.save_geocode(key, found)
        await asyncio.sleep(self.delay)
        return found
