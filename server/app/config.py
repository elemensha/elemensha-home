"""환경 설정.

키가 없는 소스는 조용히 비활성화하지 않고 `/api/health`에 "미설정"으로
드러낸다. 알림이 안 오는 이유가 "매물이 없어서"인지 "키가 없어서"인지
구분되지 않으면 며칠을 날린다.
"""

from __future__ import annotations

import os
from dataclasses import dataclass, field
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent.parent
DATA_DIR = Path(os.getenv("HOME_DATA_DIR", BASE_DIR / "data"))


def _env_list(name: str, default: list[str]) -> list[str]:
    raw = os.getenv(name, "").strip()
    if not raw:
        return default
    return [item.strip() for item in raw.split(",") if item.strip()]


def _env_int(name: str, default: int) -> int:
    try:
        return int(os.getenv(name, "") or default)
    except ValueError:
        return default


@dataclass
class Settings:
    # 접근 토큰. 앱이 Authorization: Bearer <token> 으로 보낸다.
    api_token: str = field(default_factory=lambda: os.getenv("HOME_API_TOKEN", ""))

    data_dir: Path = field(default_factory=lambda: DATA_DIR)
    db_path: Path = field(default_factory=lambda: DATA_DIR / "home.db")
    rules_path: Path = field(default_factory=lambda: DATA_DIR / "rules.json")
    citations_path: Path = field(default_factory=lambda: DATA_DIR / "citations.json")

    # 공공데이터포털 서비스키 (디코딩된 일반 인증키)
    onbid_key: str = field(default_factory=lambda: os.getenv("ONBID_SERVICE_KEY", ""))
    rtms_key: str = field(default_factory=lambda: os.getenv("RTMS_SERVICE_KEY", ""))
    applyhome_key: str = field(default_factory=lambda: os.getenv("APPLYHOME_SERVICE_KEY", ""))
    court_key: str = field(default_factory=lambda: os.getenv("COURT_API_KEY", ""))

    # 카카오 로컬 API - 주소를 좌표로 바꿔 지도에 찍는다.
    # REST 키는 서버가 지오코딩에, JS 키는 지도 페이지가 쓴다. 둘은 다른
    # 키다. JS 키는 developers.kakao.com 에서 도메인을 등록해야 동작한다.
    kakao_rest_key: str = field(default_factory=lambda: os.getenv("KAKAO_REST_KEY", ""))
    kakao_js_key: str = field(default_factory=lambda: os.getenv("KAKAO_JS_KEY", ""))
    # 한 번 수집에 지오코딩할 최대 건수. 카카오는 하루 10만 회라 넉넉하지만
    # 첫 백필에서 1.6만 건을 한꺼번에 돌리면 수집이 길어진다.
    geocode_batch: int = field(default_factory=lambda: _env_int("GEOCODE_BATCH", 3000))

    # 비우면 전국. 온비드는 전국을 통째로 훑는 쪽이 시도별로 나눠 부르는
    # 것보다 호출이 적어서(9장 vs 12회) 기본값을 전국으로 둔다.
    target_sido: list[str] = field(
        default_factory=lambda: _env_list("TARGET_SIDO", [])
    )

    # 소스별 폴링 주기(분).
    # 온비드는 개발계정 일일 한도가 1,000회뿐이다. 1시간 주기 x 페이지 10장이면
    # 하루 240회라 여유가 있지만, 지역을 넓히면 금방 닿는다.
    # 실거래가는 시군구x월 조합이라 1회 폴링에 460여 건이 나가지만 한도가
    # 10,000회라 12시간 주기면 충분하다.
    # 온비드는 하루 한 번만 돈다. 공매 물건은 시간 단위로 바뀌지 않고,
    # 1회 폴링에 200회쯤 써서 일일 한도(1,000회)를 실제로 넘긴 적이 있다.
    onbid_interval_min: int = field(default_factory=lambda: _env_int("ONBID_INTERVAL_MIN", 1440))
    onbid_full_interval_min: int = field(
        default_factory=lambda: _env_int("ONBID_FULL_INTERVAL_MIN", 1440)
    )
    # 수집을 돌릴 시각(KST, 0~23). 앱 알림이 아침 7시이므로 그 전에
    # 끝나도록 새벽에 둔다. 서비스 재시작 시각에 끌려다니지 않게 한다.
    onbid_poll_hour: int = field(default_factory=lambda: _env_int("ONBID_POLL_HOUR", 5))
    # 앞으로 이 기간 안에 시작하는 준비중 물건까지.
    onbid_upcoming_days: int = field(default_factory=lambda: _env_int("ONBID_UPCOMING_DAYS", 30))
    rtms_interval_min: int = field(default_factory=lambda: _env_int("RTMS_INTERVAL_MIN", 720))
    applyhome_interval_min: int = field(
        default_factory=lambda: _env_int("APPLYHOME_INTERVAL_MIN", 360)
    )

    keep_days: int = field(default_factory=lambda: _env_int("KEEP_DAYS", 90))

    # 인앱 업데이트: APK는 GitHub Releases에 두고 서버는 최신 릴리스를 중계만 한다.
    # 서버가 죽어도 앱이 GitHub을 직접 볼 수 있게 하려는 구조다.
    release_api: str = field(
        default_factory=lambda: os.getenv(
            "RELEASE_API",
            "https://api.github.com/repos/elemensha/elemensha-home/releases/latest",
        )
    )

    # 텔레그램으로도 알림을 받고 싶을 때만 설정
    telegram_token: str = field(default_factory=lambda: os.getenv("TELEGRAM_BOT_TOKEN", ""))
    telegram_chat_id: str = field(default_factory=lambda: os.getenv("TELEGRAM_CHAT_ID", ""))

    def source_status(self) -> dict[str, bool]:
        return {
            "onbid": bool(self.onbid_key),
            "rtms": bool(self.rtms_key),
            "applyhome": bool(self.applyhome_key),
            "court": bool(self.court_key),
        }

    @property
    def telegram_enabled(self) -> bool:
        return bool(self.telegram_token and self.telegram_chat_id)


settings = Settings()
