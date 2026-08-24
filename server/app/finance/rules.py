"""부동산 금융 규제 파라미터.

여기 있는 숫자는 **자주 바뀐다.** 정부 대책 하나로 LTV 한도와 DSR 가산금리가
하룻밤에 달라진다. 그래서 코드에 상수로 박지 않고, 날짜가 찍힌 룰셋으로 분리해
`data/rules.json`으로 덮어쓸 수 있게 했다.

`RULESET_VERSION`이 오래됐다면 계산 결과를 믿지 말 것. API 응답과 앱 화면에
항상 이 날짜를 함께 실어 보낸다.
"""

from __future__ import annotations

import json
from dataclasses import dataclass, field, asdict
from pathlib import Path

# 이 룰셋이 반영한 규제 기준일. 실제 규정과 대조해 확인한 뒤 갱신할 것.
RULESET_VERSION = "2026-08-24"
RULESET_SOURCE_NOTE = (
    "2026-08-24에 1차 출처(금융위·국토부 보도자료, 국가법령정보센터 조문)로 "
    "검증한 값. 파라미터별 출처는 data/citations.json에 있다. 실제 대출 한도는 "
    "은행 심사에서, 세액은 신고 시점 세법과 개인 사정에 따라 달라진다."
)


@dataclass
class LtvRule:
    """주택담보인정비율. 지역·주택수·자격에 따라 갈린다.

    2025-10-15 대책(시행 2025-10-16)으로 규제지역 LTV가 크게 내려갔고,
    '처분조건부 1주택'이 무주택과 같은 취급을 받게 되면서 1주택 항목이
    둘로 갈렸다. 처분조건이 없는 유주택은 규제지역에서 0%다.

    출처: 국토교통부 「[참고] 투기과열지구 및 조정대상지역 추가 지정」
    (2026-06-30 배포) 참고1 '규제지역 지정효과'
    """

    # --- 규제지역 ---
    regulated_no_house: float = 0.40
    regulated_one_house_disposal: float = 0.40  # 처분조건부 1주택 = 무주택 취급
    regulated_one_house: float = 0.0            # 처분조건 없는 1주택
    regulated_multi_house: float = 0.0
    regulated_first_time: float = 0.70          # 생애최초
    regulated_low_income: float = 0.60          # 서민·실수요자

    # --- 비규제지역 ---
    normal_no_house: float = 0.70
    normal_one_house_disposal: float = 0.70
    normal_one_house: float = 0.60
    normal_multi_house: float = 0.60
    normal_first_time: float = 0.70

    # 수도권·규제지역 주담대 절대한도. 주택가격 구간별로 다르다.
    # (주택가격 상한, 대출 한도) — 2025-10-16 시행
    metro_loan_caps: list[tuple[int, int]] = field(
        default_factory=lambda: [
            (1_500_000_000, 600_000_000),
            (2_500_000_000, 400_000_000),
            (2**63 - 1, 200_000_000),
        ]
    )

    def cap_for_price(self, price_krw: int) -> int:
        """주택가격에 걸리는 절대한도."""
        for upper, cap in self.metro_loan_caps:
            if price_krw <= upper:
                return cap
        return 0


@dataclass
class DsrRule:
    """총부채원리금상환비율."""

    bank_ratio: float = 0.40        # 은행권
    non_bank_ratio: float = 0.50    # 제2금융권

    # 스트레스 DSR 3단계(2025-07-01 시행)의 기본 가산금리.
    stress_rate_default: float = 0.015
    # 수도권·규제지역 '주담대'에만 걸리는 하한. 2025-10-16 시행.
    stress_rate_metro_mortgage: float = 0.030
    # 비수도권 주담대 완화분. **근거가 2026-06-30까지만 확인됐다.**
    # 하반기 연장 여부를 밝힌 1차 출처를 못 찾아 provenance에서 unknown으로 둔다.
    stress_rate_non_metro: float = 0.0075

    # DSR 산정 제외 기준: 총대출액이 이 금액 이하면 차주단위 DSR 미적용
    exempt_below_krw: int = 100_000_000


@dataclass
class AcquisitionTaxRule:
    """취득세. 주택 유상취득 기준."""

    # 1주택 기본: 6억 이하 1%, 6~9억 누진, 9억 초과 3%
    tier1_limit: int = 600_000_000
    tier1_rate: float = 0.01
    tier3_limit: int = 900_000_000
    tier3_rate: float = 0.03

    # 다주택 중과 (지방세법 제13조의2). 취득 **후** 주택 수 기준이며
    # 조정대상지역이냐에 따라 같은 주택 수라도 세율이 다르다.
    heavy_2house_regulated: float = 0.08    # 조정 2주택
    heavy_3house_regulated: float = 0.12    # 조정 3주택 이상
    heavy_3house_normal: float = 0.08       # 비조정 3주택
    heavy_4house_normal: float = 0.12       # 비조정 4주택 이상

    # 부가세목
    local_edu_tax_ratio: float = 0.10   # 표준세율 주택: 취득세액 대비
    # 중과세율 적용 시 지방교육세는 취득세액 비례가 아니라 과세표준의 0.4% 고정
    # (지방세법 제151조 제1항 제1호 나목)
    local_edu_tax_heavy_rate: float = 0.004
    rural_tax_rate: float = 0.002       # 국민주택규모 초과분에만 과세표준 대비

    # 농특세 비과세 기준. 수도권은 85㎡지만 수도권 외 읍·면은 100㎡다.
    exclusive_area_exempt_sqm: float = 85.0
    exclusive_area_exempt_sqm_rural: float = 100.0

    # 생애최초 감면 (지방세특례제한법 제36조의3). 일몰 2028-12-31.
    # 소득요건은 2023-03-14 개정으로 폐지, 취득가액 12억 이하 요건만 남았다.
    first_time_relief_cap: int = 2_000_000
    first_time_relief_price_limit: int = 1_200_000_000


@dataclass
class CapitalGainsTaxRule:
    """양도소득세."""

    basic_deduction: int = 2_500_000

    # 단기 보유 중과세율
    under_1year_rate: float = 0.70
    under_2year_rate: float = 0.60

    # 누진세율 구간: (과세표준 상한, 세율, 누진공제)
    brackets: list[tuple[int, float, int]] = field(
        default_factory=lambda: [
            (14_000_000, 0.06, 0),
            (50_000_000, 0.15, 1_260_000),
            (88_000_000, 0.24, 5_760_000),
            (150_000_000, 0.35, 15_440_000),
            (300_000_000, 0.38, 19_940_000),
            (500_000_000, 0.40, 25_940_000),
            (1_000_000_000, 0.42, 35_940_000),
            (2**63 - 1, 0.45, 65_940_000),
        ]
    )

    local_income_tax_ratio: float = 0.10  # 산출세액 대비 지방소득세

    # 1세대 1주택 비과세 기준
    one_house_exempt_price: int = 1_200_000_000
    one_house_min_hold_years: float = 2.0
    # 취득 당시 조정대상지역이었으면 보유 2년에 더해 거주 2년이 필요하다.
    # (소득세법 시행령 제154조 제1항) 양도 시 해제됐어도 요건은 그대로다.
    one_house_min_live_years_regulated: float = 2.0

    # 장기보유특별공제 표1 (일반): 3년 이상부터 연 2%, 최대 30%.
    # 30% 상한은 흔히 알려진 10년이 아니라 15년 이상에서 도달한다.
    ltd_start_year: int = 3
    ltd_rate_per_year: float = 0.02
    ltd_max: float = 0.30

    # 장기보유특별공제 표2 (1세대 1주택). 보유·거주를 각각 연 4%씩 매겨
    # 합산하며 최대 80%. 거주 2년 미만이면 표1로 떨어진다.
    # (소득세법 제95조 제2항 표2, 시행령 제159조의4)
    ltd_single_hold_per_year: float = 0.04
    ltd_single_live_per_year: float = 0.04
    ltd_single_max: float = 0.80
    ltd_single_min_live_years: float = 2.0

    # 다주택 중과 (소득세법 제104조 제7항).
    # 시행령 제167조의3·제167조의10이 중과 배제 대상을 "2026년 5월 9일까지
    # 양도하는 주택"으로 한정했고, 2026-05-22 개정에서 연장되지 않았다.
    # 즉 2026-05-10 이후 양도분부터 중과가 되살아났다.
    multi_house_surcharge_active: bool = True
    multi_house_surcharge_grace_until: str = "2026-05-09"
    surcharge_2house: float = 0.20   # 조정대상지역 2주택 +20%p
    surcharge_3house: float = 0.30   # 3주택 이상 +30%p


@dataclass
class TransactionCostRule:
    """거래 부대비용."""

    # 중개보수 상한 (매매). 서울시·경기도 조례 요율은 동일하다.
    # (거래금액 상한, 요율, 한도액). 구간은 "미만" 기준이라 경계값은 위 구간에
    # 속한다 - 5천만원 정확히면 0.6%가 아니라 0.5%다. 한도액 0은 상한 없음.
    brokerage_brackets: list[tuple[int, float, int]] = field(
        default_factory=lambda: [
            (50_000_000, 0.006, 250_000),
            (200_000_000, 0.005, 800_000),
            (900_000_000, 0.004, 0),
            (1_200_000_000, 0.005, 0),
            (1_500_000_000, 0.006, 0),
            (2**63 - 1, 0.007, 0),
        ]
    )

    # 소유권이전 등기 법무사 보수 근사치(원)
    legal_fee: int = 700_000
    # 국민주택채권 매입 할인 손실 근사치: 매매가 대비
    bond_discount_ratio: float = 0.002


@dataclass
class RuleSet:
    version: str = RULESET_VERSION
    note: str = RULESET_SOURCE_NOTE
    ltv: LtvRule = field(default_factory=LtvRule)
    dsr: DsrRule = field(default_factory=DsrRule)
    acquisition_tax: AcquisitionTaxRule = field(default_factory=AcquisitionTaxRule)
    capital_gains_tax: CapitalGainsTaxRule = field(default_factory=CapitalGainsTaxRule)
    transaction_cost: TransactionCostRule = field(default_factory=TransactionCostRule)

    def to_dict(self) -> dict:
        return asdict(self)


def load_ruleset(path: Path | None = None) -> RuleSet:
    """기본 룰셋을 만들고, 파일이 있으면 그 값으로 덮어쓴다.

    규제가 바뀌면 코드를 고치는 대신 이 JSON만 갈아끼우면 된다.
    """
    rules = RuleSet()
    if path is None or not path.exists():
        return rules

    raw = json.loads(path.read_text(encoding="utf-8"))
    for section, values in raw.items():
        if section in ("version", "note"):
            setattr(rules, section, values)
            continue
        target = getattr(rules, section, None)
        if target is None or not isinstance(values, dict):
            continue
        for key, value in values.items():
            if hasattr(target, key):
                setattr(target, key, value)
    return rules
