"""대출 한도 계산.

LTV·DSR·절대한도 셋을 각각 구하고 **가장 작은 값**이 실제 한도가 된다.
어느 규제에 걸려서 한도가 정해졌는지를 함께 돌려준다 — 사용자가 알아야 할
정보는 "얼마"보다 "왜 거기서 막혔나"이기 때문이다.
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum

from .rules import RuleSet


class HouseCount(str, Enum):
    NONE = "none"      # 무주택
    ONE = "one"        # 1주택
    MULTI = "multi"    # 2주택 이상


@dataclass
class BorrowerProfile:
    """차주 정보. 앱에서 사용자가 채우는 값."""

    annual_income_krw: int              # 연소득(세전)
    cash_krw: int                       # 동원 가능 현금성 자산
    house_count: HouseCount = HouseCount.NONE
    is_first_time_buyer: bool = False   # 생애최초
    # 기존 대출의 연간 원리금 상환액 합계 (신용대출·기존 주담대 등)
    existing_annual_repayment_krw: int = 0
    # 기존 주택 처분 조건을 걸었는지. 규제지역에서 이게 있으면 1주택자도
    # 무주택과 같은 LTV를 받고, 없으면 0%다. 차이가 전부다.
    has_disposal_condition: bool = False
    # 서민·실수요자 우대 대상 (소득·주택가격 요건 충족)
    is_low_income_priority: bool = False


@dataclass
class LoanTerms:
    annual_rate: float = 0.042    # 명목 금리
    years: int = 30               # 만기
    is_metro: bool = True         # 수도권 여부 (스트레스 가산금리 구분)
    is_regulated_area: bool = False  # 규제지역(투기과열/조정대상) 여부
    use_non_bank: bool = False    # 제2금융권 DSR 적용


@dataclass
class LoanCapacity:
    ltv_limit_krw: int
    dsr_limit_krw: int
    absolute_cap_krw: int | None
    limit_krw: int
    binding_constraint: str       # "LTV" | "DSR" | "절대한도"
    ltv_ratio_applied: float
    dsr_ratio_applied: float
    stress_rate_applied: float
    monthly_payment_krw: int
    notes: list[str]


def _monthly_payment(principal: float, annual_rate: float, years: int) -> float:
    """원리금균등상환 월 납입액."""
    n = years * 12
    if n <= 0:
        return 0.0
    r = annual_rate / 12
    if r == 0:
        return principal / n
    factor = (1 + r) ** n
    return principal * r * factor / (factor - 1)


def _principal_from_payment(payment: float, annual_rate: float, years: int) -> float:
    """월 납입액을 감당할 수 있는 최대 원금 (위 식의 역산)."""
    n = years * 12
    if n <= 0:
        return 0.0
    r = annual_rate / 12
    if r == 0:
        return payment * n
    factor = (1 + r) ** n
    return payment * (factor - 1) / (r * factor)


def _ltv_ratio(rules: RuleSet, profile: BorrowerProfile, terms: LoanTerms) -> tuple[float, str]:
    """적용 LTV와 그 근거 이름.

    우대(생애최초·서민실수요자)는 무주택자에게만 적용되고, 우대 비율이
    기본 비율보다 낮으면 기본을 쓴다 - 우대를 신청했다는 이유로 한도가
    줄어드는 일은 없어야 한다.
    """
    ltv = rules.ltv
    regulated = terms.is_regulated_area

    if profile.house_count is HouseCount.NONE:
        base = ltv.regulated_no_house if regulated else ltv.normal_no_house
        label = "규제지역 무주택" if regulated else "비규제지역 무주택"

        candidates = [(base, label)]
        if profile.is_first_time_buyer:
            rate = ltv.regulated_first_time if regulated else ltv.normal_first_time
            candidates.append((rate, "생애최초 우대"))
        if profile.is_low_income_priority:
            rate = ltv.regulated_low_income if regulated else ltv.normal_no_house
            candidates.append((rate, "서민·실수요자 우대"))
        return max(candidates, key=lambda item: item[0])

    if profile.house_count is HouseCount.ONE:
        if profile.has_disposal_condition:
            rate = ltv.regulated_one_house_disposal if regulated else ltv.normal_one_house_disposal
            return rate, ("규제지역 처분조건부 1주택" if regulated else "비규제지역 처분조건부 1주택")
        rate = ltv.regulated_one_house if regulated else ltv.normal_one_house
        return rate, ("규제지역 1주택(처분조건 없음)" if regulated else "비규제지역 1주택")

    rate = ltv.regulated_multi_house if regulated else ltv.normal_multi_house
    return rate, ("규제지역 2주택 이상" if regulated else "비규제지역 2주택 이상")


def calculate_capacity(
    price_krw: int,
    profile: BorrowerProfile,
    terms: LoanTerms,
    rules: RuleSet,
) -> LoanCapacity:
    """주택가격과 차주 정보로 실제 나올 수 있는 대출 한도를 구한다."""
    notes: list[str] = []

    # 1) LTV 한도
    ltv_ratio, ltv_label = _ltv_ratio(rules, profile, terms)
    ltv_limit = int(price_krw * ltv_ratio)
    notes.append(f"{ltv_label}: LTV {ltv_ratio:.0%} → {ltv_limit:,}원")
    if ltv_ratio == 0:
        notes.append("해당 조건에서는 주택담보대출이 나오지 않는다.")

    # 2) DSR 한도 — 스트레스 금리를 얹은 상환액으로 역산
    dsr = rules.dsr
    dsr_ratio = dsr.non_bank_ratio if terms.use_non_bank else dsr.bank_ratio

    # 수도권·규제지역 주담대는 3.0%p 하한이 따로 걸린다(2025-10-16).
    # 그 외에는 3단계 기본 1.5%p, 비수도권은 완화분 0.75%p.
    if terms.is_metro or terms.is_regulated_area:
        stress = max(dsr.stress_rate_metro_mortgage, dsr.stress_rate_default)
        stress_label = "수도권·규제지역 주담대 하한"
    else:
        stress = dsr.stress_rate_non_metro
        stress_label = "비수도권 완화 적용"
    stressed_rate = terms.annual_rate + stress

    allowed_annual = profile.annual_income_krw * dsr_ratio - profile.existing_annual_repayment_krw
    allowed_annual = max(allowed_annual, 0)
    dsr_limit = int(_principal_from_payment(allowed_annual / 12, stressed_rate, terms.years))
    notes.append(
        f"DSR {dsr_ratio:.0%} · 스트레스금리 {stressed_rate:.2%}"
        f"(명목 {terms.annual_rate:.2%} + {stress:.2%}p, {stress_label}) → {dsr_limit:,}원"
    )
    if profile.existing_annual_repayment_krw:
        notes.append(
            f"기존 대출 연 상환액 {profile.existing_annual_repayment_krw:,}원이 한도를 깎았다."
        )

    # 3) 절대 한도 — 주택가격 구간별 (수도권·규제지역)
    absolute_cap: int | None = None
    if terms.is_metro or terms.is_regulated_area:
        absolute_cap = rules.ltv.cap_for_price(price_krw)
        notes.append(
            f"수도권·규제지역 주담대 절대한도: 주택가격 {price_krw:,}원 구간 "
            f"→ {absolute_cap:,}원"
        )

    # DSR 미적용 소액 구간
    candidates = {"LTV": ltv_limit, "DSR": dsr_limit}
    if absolute_cap is not None:
        candidates["절대한도"] = absolute_cap

    if min(ltv_limit, dsr_limit) <= dsr.exempt_below_krw:
        notes.append(
            f"대출액이 {dsr.exempt_below_krw:,}원 이하면 DSR 산정에서 빠질 수 있다."
        )

    binding = min(candidates, key=lambda k: candidates[k])
    limit = max(candidates[binding], 0)

    monthly = int(_monthly_payment(limit, terms.annual_rate, terms.years))

    return LoanCapacity(
        ltv_limit_krw=ltv_limit,
        dsr_limit_krw=dsr_limit,
        absolute_cap_krw=absolute_cap,
        limit_krw=limit,
        binding_constraint=binding,
        ltv_ratio_applied=ltv_ratio,
        dsr_ratio_applied=dsr_ratio,
        stress_rate_applied=stressed_rate,
        monthly_payment_krw=monthly,
        notes=notes,
    )


def max_affordable_price(
    profile: BorrowerProfile,
    terms: LoanTerms,
    rules: RuleSet,
    upfront_cost_ratio: float = 0.04,
) -> int:
    """현금 + 대출로 살 수 있는 최대 주택가격.

    가격이 오르면 LTV 한도도 같이 오르므로 순환 관계다. 이분 탐색으로 푼다.
    `upfront_cost_ratio`는 취득세·중개보수 등 현금으로 내야 하는 부대비용의
    가격 대비 개략 비율 — 정확한 값은 tax 모듈이 따로 계산한다.
    """
    low, high = 0, 10_000_000_000
    for _ in range(60):
        mid = (low + high) // 2
        capacity = calculate_capacity(mid, profile, terms, rules)
        cash_needed = mid - capacity.limit_krw + int(mid * upfront_cost_ratio)
        if cash_needed <= profile.cash_krw:
            low = mid
        else:
            high = mid - 1
    return low
