"""자금계획 계산기 CLI.

API 키 없이 지금 바로 돌려볼 수 있다. 서버·앱이 붙기 전에 계산 로직이
말이 되는지 눈으로 확인하는 용도.

    python server/plan.py --income 7000 --cash 25000 --price 44520 --first-time

금액 단위는 전부 **만원**이다.
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

from app.finance.loan import (  # noqa: E402
    BorrowerProfile,
    HouseCount,
    LoanTerms,
    calculate_capacity,
    max_affordable_price,
)
from app.finance.roi import (  # noqa: E402
    ExitScenario,
    estimate_holding_cost,
    evaluate_scenario,
    scenarios_from_market,
)
from app.finance.rules import load_ruleset  # noqa: E402
from app.finance.tax import calculate_acquisition_cost  # noqa: E402

MAN = 10_000


def won(amount: int | float) -> str:
    """원 단위 정수를 '4억 4,520만원' 꼴로."""
    amount = int(amount)
    sign = "-" if amount < 0 else ""
    amount = abs(amount)
    eok, rest = divmod(amount, 100_000_000)
    man = rest // 10_000
    if eok and man:
        return f"{sign}{eok}억 {man:,}만원"
    if eok:
        return f"{sign}{eok}억원"
    return f"{sign}{man:,}만원"


def main() -> int:
    parser = argparse.ArgumentParser(description="집 살 때 자금계획 (금액 단위: 만원)")
    parser.add_argument("--income", type=int, required=True, help="연소득(세전)")
    parser.add_argument("--cash", type=int, required=True, help="동원 가능 현금")
    parser.add_argument("--price", type=int, help="검토할 물건 가격. 없으면 최대 구매가능가만 계산")
    parser.add_argument("--area", type=float, default=84.9, help="전용면적(제곱미터)")
    parser.add_argument("--rate", type=float, default=4.2, help="대출 금리(%%)")
    parser.add_argument("--years", type=int, default=30, help="대출 만기(년)")
    parser.add_argument("--houses", type=int, default=0, help="현재 보유 주택 수")
    parser.add_argument("--disposal", action="store_true", help="기존 주택 처분조건 설정")
    parser.add_argument("--live-years", type=float, help="실제 거주 기간(년). 생략하면 보유기간과 동일")
    parser.add_argument("--first-time", action="store_true", help="생애최초 구입")
    parser.add_argument("--regulated", action="store_true", help="규제지역")
    parser.add_argument("--non-metro", action="store_true", help="비수도권")
    parser.add_argument("--auction", action="store_true", help="경매·공매 물건")
    parser.add_argument("--existing-repay", type=int, default=0, help="기존 대출 연 상환액")
    parser.add_argument("--hold-years", type=float, default=5.0, help="보유 예정 기간")
    parser.add_argument(
        "--rent-saved",
        type=int,
        default=0,
        help="실거주로 안 내게 되는 월세(만원/월). 넣지 않으면 거주 가치가 0으로 잡힌다",
    )
    parser.add_argument("--rent-income", type=int, default=0, help="월 임대수입(만원/월)")
    parser.add_argument(
        "--sell",
        type=int,
        nargs="*",
        default=[],
        help="매도 가정 가격들. 여러 개 주면 시나리오로 비교한다",
    )
    args = parser.parse_args()

    rules = load_ruleset()
    profile = BorrowerProfile(
        annual_income_krw=args.income * MAN,
        cash_krw=args.cash * MAN,
        house_count=(
            HouseCount.NONE if args.houses <= 0
            else HouseCount.ONE if args.houses == 1
            else HouseCount.MULTI
        ),
        is_first_time_buyer=args.first_time,
        has_disposal_condition=args.disposal,
        existing_annual_repayment_krw=args.existing_repay * MAN,
    )
    terms = LoanTerms(
        annual_rate=args.rate / 100,
        years=args.years,
        is_metro=not args.non_metro,
        is_regulated_area=args.regulated,
    )

    print(f"규제 기준일 {rules.version} - {rules.note}\n")

    ceiling = max_affordable_price(profile, terms, rules)
    print("== 살 수 있는 최대 가격 ==")
    print(f"  현금 {won(profile.cash_krw)} + 대출 -> 최대 {won(ceiling)}\n")

    if not args.price:
        return 0

    price = args.price * MAN
    print(f"== 대상 물건 {won(price)} ==")
    capacity = calculate_capacity(price, profile, terms, rules)
    for note in capacity.notes:
        print(f"  - {note}")
    print(f"  => 대출 한도 {won(capacity.limit_krw)} (제약: {capacity.binding_constraint})")
    print(f"     월 납입액 {capacity.monthly_payment_krw:,}원\n")

    acq = calculate_acquisition_cost(
        price,
        args.area,
        args.houses + 1,
        args.regulated,
        rules,
        is_first_time_buyer=args.first_time,
        is_auction=args.auction,
    )
    print(f"== 취득 부대비용 {won(acq.total_krw)} (가격의 {acq.effective_rate:.2%}) ==")
    for note in acq.breakdown_notes:
        print(f"  - {note}")

    loan = capacity.limit_krw
    equity_needed = price - loan + acq.total_krw
    print(f"\n== 필요 현금 {won(equity_needed)} ==")
    if equity_needed > profile.cash_krw:
        print(f"  ! 보유 현금 {won(profile.cash_krw)}로는 {won(equity_needed - profile.cash_krw)} 부족")
    else:
        print(f"  보유 현금 {won(profile.cash_krw)} 중 {won(profile.cash_krw - equity_needed)} 남음")

    holding = estimate_holding_cost(
        loan,
        terms,
        price,
        monthly_rental_income_krw=args.rent_income * MAN,
        monthly_rent_saved_krw=args.rent_saved * MAN,
        is_single_house=args.houses == 0,
    )
    print(f"\n== 보유 중 연 현금흐름 {won(holding.annual_net_krw)} ==")
    for note in holding.notes:
        print(f"  - {note}")

    if args.sell:
        scenarios = [
            ExitScenario(f"가정{i + 1}", value * MAN, args.hold_years, "사용자 입력")
            for i, value in enumerate(args.sell)
        ]
    else:
        # 가정을 안 주면 매수가 기준 -10% / 유지 / +20%로 감을 잡게 한다.
        scenarios = scenarios_from_market(
            [int(price * 0.9), price, int(price * 1.2)], args.hold_years
        )
        for scenario in scenarios:
            scenario.basis = "매수가 기준 임의 가정 (-10% / 0% / +20%). 예측이 아님"

    print(f"\n== 매도 시나리오 ({args.hold_years}년 보유) ==")
    print("   아래 가격은 전부 가정이다. 실제로 그 값에 팔린다는 뜻이 아니다.")
    for scenario in scenarios:
        result = evaluate_scenario(
            scenario,
            price,
            loan,
            acq.total_krw,
            terms,
            rules,
            holding,
            other_houses_at_sale=args.houses,
            live_years=args.live_years,
            acquired_in_regulated_area=args.regulated,
            sale_in_regulated_area=args.regulated,
        )
        print(
            f"  [{result.label}] 매도 {won(result.sell_price_krw)}"
            f" | 양도세 {won(result.capital_gains_tax_krw)}"
            f" | 순손익 {won(result.net_profit_krw)}"
            f" | ROI {result.roi:+.1%} (연 {result.annualized_roi:+.1%})"
        )
        print(f"        근거: {result.basis}")

    print(
        "\n  ROI는 '넣은 현금' 대비다. 대출을 많이 낄수록 같은 가격 변동에도"
        "\n  퍼센트가 크게 튄다. 손실 쪽도 똑같이 증폭된다."
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
