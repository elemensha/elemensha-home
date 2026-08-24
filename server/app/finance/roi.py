"""보유·처분 시나리오와 수익률.

**이 모듈은 집값을 예측하지 않는다.** 매도가는 언제나 바깥에서 들어온 가정이다.
사용자가 직접 넣거나, 과거 실거래 범위에서 뽑아 온다. 하는 일은 "그 가격에
팔린다면 손에 얼마가 남는가"를 산수로 보여주는 것뿐이다.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from statistics import median

from .loan import LoanTerms, _monthly_payment
from .rules import RuleSet
from .tax import calculate_capital_gains_tax


@dataclass
class HoldingCost:
    annual_interest_krw: int
    annual_property_tax_krw: int
    annual_maintenance_krw: int
    annual_rental_income_krw: int
    annual_rent_saved_krw: int       # 실거주로 안 내게 된 월세 (귀속임대료)
    annual_net_krw: int              # 음수면 매년 현금이 나간다
    notes: list[str] = field(default_factory=list)


# 주택 재산세 표준세율 (지방세법 제111조). (과세표준 상한, 누진기초액, 초과분 세율)
_PROPERTY_TAX_STANDARD = [
    (60_000_000, 0, 0.001),
    (150_000_000, 60_000, 0.0015),
    (300_000_000, 195_000, 0.0025),
    (2**63 - 1, 570_000, 0.004),
]

# 1세대 1주택 특례세율 (지방세법 제111조의2). 별도 표이지 표준세율에 배수를
# 곱하는 방식이 아니다. 저가 구간일수록 경감폭이 크다(6천만에서 실효 0.5배).
_PROPERTY_TAX_SINGLE_HOUSE = [
    (60_000_000, 0, 0.0005),
    (150_000_000, 30_000, 0.001),
    (300_000_000, 120_000, 0.002),
    (2**63 - 1, 420_000, 0.0035),
]

# 특례세율 적용 상한. 공시가격이 이보다 크면 표준세율을 쓴다.
SINGLE_HOUSE_SPECIAL_LIMIT = 900_000_000

# 공정시장가액비율. 1세대 1주택은 공시가격대별로 더 낮은 특례가 적용된다.
# **주의: 확인된 43~45%는 2025년도분이다.** 시행령이 매년 개정되므로
# 2026년도분은 미확인 상태다(provenance에서 unknown으로 관리).
FAIR_MARKET_RATIO_DEFAULT = 0.60
_SINGLE_HOUSE_FAIR_MARKET = [
    (300_000_000, 0.43),
    (600_000_000, 0.44),
    (2**63 - 1, 0.45),
]


def _bracket_tax(base: float, table: list[tuple[int, int, float]]) -> float:
    lower = 0
    for upper, floor_amount, rate in table:
        if base <= upper:
            return floor_amount + (base - lower) * rate
        lower = upper
    return 0.0


def single_house_fair_market_ratio(published_price_krw: int) -> float:
    for upper, ratio in _SINGLE_HOUSE_FAIR_MARKET:
        if published_price_krw <= upper:
            return ratio
    return FAIR_MARKET_RATIO_DEFAULT


def estimate_property_tax(
    published_price_krw: int,
    is_single_house: bool = True,
    fair_market_ratio: float | None = None,
) -> int:
    """재산세 근사치. 공시가격을 넣는다. 도시지역분·지방교육세를 포함한다.

    1세대 1주택은 공정시장가액비율과 세율표가 **둘 다** 따로 있다. 예전에는
    표준세율에 0.95를 곱하고 비율도 60%를 그대로 썼는데, 두 오차가 같은
    방향으로 겹쳐 1주택 재산세가 크게 부풀려졌다.
    """
    use_special = is_single_house and published_price_krw <= SINGLE_HOUSE_SPECIAL_LIMIT

    if fair_market_ratio is None:
        fair_market_ratio = (
            single_house_fair_market_ratio(published_price_krw)
            if use_special
            else FAIR_MARKET_RATIO_DEFAULT
        )

    base = published_price_krw * fair_market_ratio
    table = _PROPERTY_TAX_SINGLE_HOUSE if use_special else _PROPERTY_TAX_STANDARD
    tax = _bracket_tax(base, table)

    # 지방교육세(재산세의 20%) + 도시지역분(과세표준의 0.14%)
    return int(tax * 1.2 + base * 0.0014)


def estimate_holding_cost(
    loan_krw: int,
    terms: LoanTerms,
    price_krw: int,
    monthly_maintenance_krw: int = 200_000,
    monthly_rental_income_krw: int = 0,
    published_price_ratio: float = 0.70,
    monthly_rent_saved_krw: int = 0,
    is_single_house: bool = True,
) -> HoldingCost:
    """1년치 보유 현금흐름.

    이자는 원리금균등 첫해의 이자분에 가깝게 잡는다(잔액이 큰 초기 기준).
    원금 상환분은 자산으로 남으므로 비용에 넣지 않는다.

    실거주라면 `monthly_rent_saved_krw`에 '안 내게 된 월세'를 넣는다.
    이걸 빼먹으면 이자만 비용으로 잡히고 그 대가로 얻은 거주 가치는
    사라져서, 실거주 매수가 실제보다 훨씬 나쁘게 보인다.
    """
    notes: list[str] = []
    annual_interest = int(loan_krw * terms.annual_rate)
    notes.append(f"대출 {loan_krw:,}원 x 금리 {terms.annual_rate:.2%} = 연 이자 {annual_interest:,}원")

    monthly_total = int(_monthly_payment(loan_krw, terms.annual_rate, terms.years))
    notes.append(f"실제 월 납입액(원리금균등) {monthly_total:,}원 - 이 중 원금은 자산으로 남는다")

    published = int(price_krw * published_price_ratio)
    prop_tax = estimate_property_tax(published, is_single_house=is_single_house)
    notes.append(
        f"재산세 근사 {prop_tax:,}원 (공시가격을 시세의 {published_price_ratio:.0%}인 "
        f"{published:,}원으로 가정"
        + ("· 1세대1주택 특례세율 적용)" if is_single_house and published <= 900_000_000
           else "· 표준세율 적용)")
    )

    maintenance = monthly_maintenance_krw * 12
    rental = monthly_rental_income_krw * 12
    if rental:
        notes.append(f"임대수입 연 {rental:,}원")

    rent_saved = monthly_rent_saved_krw * 12
    if rent_saved:
        notes.append(f"실거주로 안 내게 된 월세 연 {rent_saved:,}원 (귀속임대료)")

    net = rental + rent_saved - annual_interest - prop_tax - maintenance
    return HoldingCost(
        annual_interest_krw=annual_interest,
        annual_property_tax_krw=prop_tax,
        annual_maintenance_krw=maintenance,
        annual_rental_income_krw=rental,
        annual_rent_saved_krw=rent_saved,
        annual_net_krw=net,
        notes=notes,
    )


@dataclass
class ExitScenario:
    """매도 가정. 예측이 아니라 입력값이다."""

    label: str
    sell_price_krw: int
    hold_years: float = 5.0
    basis: str = "사용자 입력"    # 이 가격이 어디서 왔는지


@dataclass
class ScenarioResult:
    label: str
    basis: str
    sell_price_krw: int
    hold_years: float

    equity_invested_krw: int      # 실제로 넣은 현금 (계약금+잔금+부대비용)
    loan_krw: int
    loan_balance_at_sale_krw: int

    selling_cost_krw: int
    capital_gains_tax_krw: int
    cumulative_holding_cash_krw: int   # 보유기간 누적 현금흐름 (보통 음수)

    net_proceeds_krw: int         # 매도 후 손에 쥐는 현금
    net_profit_krw: int           # 순손익
    roi: float                    # 투입 자기자본 대비
    annualized_roi: float
    notes: list[str] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)


def _remaining_balance(principal: float, annual_rate: float, years: int, elapsed_years: float) -> float:
    """원리금균등 상환 중 elapsed_years 시점의 잔액."""
    n = years * 12
    k = min(int(elapsed_years * 12), n)
    r = annual_rate / 12
    if r == 0:
        return max(principal * (1 - k / n), 0.0)
    factor = (1 + r) ** n
    payment = principal * r * factor / (factor - 1)
    balance = principal * (1 + r) ** k - payment * (((1 + r) ** k - 1) / r)
    return max(balance, 0.0)


def evaluate_scenario(
    scenario: ExitScenario,
    buy_price_krw: int,
    loan_krw: int,
    acquisition_cost_krw: int,
    terms: LoanTerms,
    rules: RuleSet,
    holding: HoldingCost,
    other_houses_at_sale: int = 0,
    live_years: float | None = None,
    acquired_in_regulated_area: bool = False,
    sale_in_regulated_area: bool = False,
    selling_brokerage_ratio: float = 0.005,
) -> ScenarioResult:
    """하나의 매도 가정을 끝까지 계산한다."""
    notes: list[str] = []
    warnings: list[str] = []

    equity = buy_price_krw - loan_krw + acquisition_cost_krw
    notes.append(
        f"투입 자기자본 = 매매가 {buy_price_krw:,} - 대출 {loan_krw:,} "
        f"+ 취득부대비용 {acquisition_cost_krw:,} = {equity:,}원"
    )

    selling_cost = int(scenario.sell_price_krw * selling_brokerage_ratio)
    notes.append(f"매도 중개보수 등 {selling_cost:,}원")

    cgt = calculate_capital_gains_tax(
        buy_price_krw=buy_price_krw,
        sell_price_krw=scenario.sell_price_krw,
        hold_years=scenario.hold_years,
        acquisition_cost_krw=acquisition_cost_krw,
        selling_cost_krw=selling_cost,
        rules=rules,
        other_houses_at_sale=other_houses_at_sale,
        live_years=live_years,
        acquired_in_regulated_area=acquired_in_regulated_area,
        sale_in_regulated_area=sale_in_regulated_area,
    )
    notes.extend(cgt.notes)
    warnings.extend(cgt.warnings)

    balance = int(_remaining_balance(loan_krw, terms.annual_rate, terms.years, scenario.hold_years))
    notes.append(f"{scenario.hold_years}년 뒤 대출 잔액 {balance:,}원")

    cumulative_holding = int(holding.annual_net_krw * scenario.hold_years)
    notes.append(f"보유기간 누적 현금흐름 {cumulative_holding:,}원")

    net_proceeds = scenario.sell_price_krw - selling_cost - cgt.total_krw - balance
    net_profit = net_proceeds + cumulative_holding - equity

    roi = net_profit / equity if equity > 0 else 0.0
    if scenario.hold_years <= 0 or equity <= 0:
        annualized = 0.0
    elif (1 + roi) <= 0:
        # 넣은 돈보다 더 잃은 경우. 연환산은 수학적으로 정의되지 않으므로
        # -100%로 눌러 표시한다. 0%로 두면 손실이 사라진 것처럼 보인다.
        annualized = -1.0
        warnings.append(
            "투입 자본을 전부 잃고도 모자라는 시나리오다. 연환산 수익률은 "
            "의미가 없어 -100%로 표시했다."
        )
    else:
        annualized = (1 + roi) ** (1 / scenario.hold_years) - 1

    notes.append(
        f"매도 순수취 {net_proceeds:,}원 + 누적 현금흐름 {cumulative_holding:,}원 "
        f"- 투입자본 {equity:,}원 = 순손익 {net_profit:,}원"
    )

    return ScenarioResult(
        label=scenario.label,
        basis=scenario.basis,
        sell_price_krw=scenario.sell_price_krw,
        hold_years=scenario.hold_years,
        equity_invested_krw=equity,
        loan_krw=loan_krw,
        loan_balance_at_sale_krw=balance,
        selling_cost_krw=selling_cost,
        capital_gains_tax_krw=cgt.total_krw,
        cumulative_holding_cash_krw=cumulative_holding,
        net_proceeds_krw=net_proceeds,
        net_profit_krw=net_profit,
        roi=roi,
        annualized_roi=annualized,
        notes=notes,
        warnings=warnings,
    )


def scenarios_from_market(
    recent_prices_krw: list[int],
    hold_years: float = 5.0,
) -> list[ExitScenario]:
    """과거 실거래 범위에서 보수/중립/낙관 세 가정을 뽑는다.

    **미래 가격 예측이 아니다.** 같은 단지·같은 면적이 최근 실제로 얼마에
    거래됐는지의 하단·중앙·상단일 뿐이다. 이 범위 밖으로 나갈 수 있다.
    """
    if not recent_prices_krw:
        return []

    ordered = sorted(recent_prices_krw)
    low = ordered[0]
    mid = int(median(ordered))
    high = ordered[-1]
    basis = f"최근 실거래 {len(ordered)}건의 범위 (예측 아님)"

    return [
        ExitScenario("보수", low, hold_years, basis + " - 하단"),
        ExitScenario("중립", mid, hold_years, basis + " - 중앙값"),
        ExitScenario("낙관", high, hold_years, basis + " - 상단"),
    ]
