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

    target_sido: list[str] = field(
        default_factory=lambda: _env_list("TARGET_SIDO", ["서울특별시", "경기도", "인천광역시"])
    )

    # 소스별 폴링 주기(분).
    # 온비드는 개발계정 일일 한도가 1,000회뿐이다. 1시간 주기 x 페이지 10장이면
    # 하루 240회라 여유가 있지만, 지역을 넓히면 금방 닿는다.
    # 실거래가는 시군구x월 조합이라 1회 폴링에 460여 건이 나가지만 한도가
    # 10,000회라 12시간 주기면 충분하다.
    onbid_interval_min: int = field(default_factory=lambda: _env_int("ONBID_INTERVAL_MIN", 60))
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
