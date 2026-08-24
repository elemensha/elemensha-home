"""세금과 거래 부대비용.

취득 단계(취득세·중개보수·등기)와 처분 단계(양도소득세)를 나눠 계산한다.
세법에는 예외 규정이 촘촘해서 여기 계산은 **일반적인 경우의 근사치**다.
1세대 1주택 비과세, 장기보유특별공제 정도만 반영하고, 다주택 중과 유예나
상생임대인 같은 특례는 다루지 않는다. 한계는 결과에 경고로 실어 보낸다.
"""

from __future__ import annotations

from dataclasses import dataclass, field

from .rules import RuleSet


@dataclass
class AcquisitionCost:
    acquisition_tax_krw: int
    local_edu_tax_krw: int
    rural_tax_krw: int
    brokerage_fee_krw: int
    legal_fee_krw: int
    bond_discount_krw: int
    total_krw: int
    effective_rate: float          # 매매가 대비 부대비용 비율
    breakdown_notes: list[str] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)


def _standard_acquisition_rate(price_krw: int, rules: RuleSet) -> tuple[float, str]:
    """중과가 걸리지 않는 주택의 기본세율."""
    tax = rules.acquisition_tax
    if price_krw <= tax.tier1_limit:
        return tax.tier1_rate, "6억 이하 기본세율"
    if price_krw >= tax.tier3_limit:
        return tax.tier3_rate, "9억 초과 기본세율"

    # 6~9억 구간 누진 (지방세법 제11조 제1항 제8호):
    #   세율(%) = 취득가액(억) x 2/3 - 3
    # 소수점 다섯째 자리에서 반올림해 넷째 자리까지 계산한다. 반올림 자리가
    # 비율(0.01)이 아니라 백분율(1.0) 기준이라는 점이 중요하다.
    percent = round(price_krw / 100_000_000 * 2 / 3 - 3, 4)
    return percent / 100, "6~9억 구간 누진세율"


def _acquisition_tax_rate(
    price_krw: int, houses_after: int, is_regulated: bool, rules: RuleSet
) -> tuple[float, str]:
    """취득세율. `houses_after`는 이번 취득을 **포함한** 보유 주택 수다.

    같은 주택 수라도 조정대상지역이냐에 따라 세율이 다르다. 비조정지역
    3주택은 8%인데 12%로 잡으면 세액이 50% 부풀려진다.
    """
    tax = rules.acquisition_tax

    if is_regulated:
        if houses_after >= 3:
            return tax.heavy_3house_regulated, "조정대상지역 3주택 이상 중과"
        if houses_after == 2:
            return tax.heavy_2house_regulated, "조정대상지역 2주택 중과"
    else:
        if houses_after >= 4:
            return tax.heavy_4house_normal, "비조정지역 4주택 이상 중과"
        if houses_after == 3:
            return tax.heavy_3house_normal, "비조정지역 3주택 중과"

    return _standard_acquisition_rate(price_krw, rules)


def _brokerage_fee(price_krw: int, rules: RuleSet) -> tuple[int, float, int]:
    """중개보수 상한. 요율을 곱한 값과 한도액 중 작은 쪽이다."""
    for upper, rate, cap in rules.transaction_cost.brokerage_brackets:
        # 조례가 "N원 미만"으로 쓰므로 경계값은 다음 구간에 속한다.
        if price_krw < upper:
            fee = int(price_krw * rate)
            if cap:
                fee = min(fee, cap)
            return fee, rate, cap
    return 0, 0.0, 0


def calculate_acquisition_cost(
    price_krw: int,
    exclusive_area_sqm: float,
    houses_after: int,
    is_regulated: bool,
    rules: RuleSet,
    is_first_time_buyer: bool = False,
    is_auction: bool = False,
    is_rural_area: bool = False,
) -> AcquisitionCost:
    """집을 살 때 매매가 위에 얹히는 현금 비용.

    `houses_after`는 이번 취득을 포함한 보유 주택 수다(무주택자가 사면 1).
    """
    at = rules.acquisition_tax
    notes: list[str] = []
    warnings: list[str] = []

    rate, rate_label = _acquisition_tax_rate(price_krw, houses_after, is_regulated, rules)
    is_heavy = rate >= at.heavy_2house_regulated
    acq_tax = int(price_krw * rate)
    notes.append(f"취득세 {rate:.4%} ({rate_label}) = {acq_tax:,}원")

    if is_first_time_buyer and houses_after <= 1:
        if price_krw <= at.first_time_relief_price_limit:
            relief = min(acq_tax, at.first_time_relief_cap)
            acq_tax -= relief
            notes.append(
                f"생애최초 감면 {relief:,}원 차감 (한도 {at.first_time_relief_cap:,}원, "
                f"일몰 2028-12-31)"
            )
        else:
            notes.append(
                f"생애최초 감면 미적용: 취득가액이 "
                f"{at.first_time_relief_price_limit:,}원을 넘는다"
            )

    # 중과 주택의 지방교육세는 취득세액 비례가 아니라 과세표준의 0.4% 고정이다.
    if is_heavy:
        edu_tax = int(price_krw * at.local_edu_tax_heavy_rate)
        notes.append(f"지방교육세 (중과: 과세표준의 {at.local_edu_tax_heavy_rate:.1%}) = {edu_tax:,}원")
    else:
        edu_tax = int(acq_tax * at.local_edu_tax_ratio)
        notes.append(f"지방교육세 (취득세액의 {at.local_edu_tax_ratio:.0%}) = {edu_tax:,}원")

    exempt_area = (
        at.exclusive_area_exempt_sqm_rural if is_rural_area else at.exclusive_area_exempt_sqm
    )
    rural_tax = 0
    if exclusive_area_sqm > exempt_area:
        rural_tax = int(price_krw * at.rural_tax_rate)
        notes.append(
            f"농어촌특별세 (전용 {exclusive_area_sqm:.1f}m2 > 국민주택규모 {exempt_area:.0f}m2)"
            f" = {rural_tax:,}원"
        )

    if is_auction:
        brokerage, brokerage_rate, brokerage_cap = 0, 0.0, 0
        notes.append("경매·공매는 중개보수 없음")
        warnings.append(
            "경매는 명도비·미납관리비·인수보증금 같은 변수가 따로 붙는다. "
            "권리분석 결과를 별도 비용으로 입력할 것."
        )
    else:
        brokerage, brokerage_rate, brokerage_cap = _brokerage_fee(price_krw, rules)
        cap_note = f", 한도 {brokerage_cap:,}원" if brokerage_cap else ""
        notes.append(
            f"중개보수 상한 {brokerage_rate:.2%}{cap_note} = {brokerage:,}원 (협의로 낮출 수 있음)"
        )

    legal = rules.transaction_cost.legal_fee
    bond = int(price_krw * rules.transaction_cost.bond_discount_ratio)
    notes.append(f"법무사 보수 {legal:,}원 + 국민주택채권 할인손실 약 {bond:,}원")
    warnings.append(
        "법무사 보수는 법정 요율이 없고, 국민주택채권 할인율은 매일 바뀐다. "
        "두 항목은 고정 상수가 아니라 어림값이다."
    )

    total = acq_tax + edu_tax + rural_tax + brokerage + legal + bond
    return AcquisitionCost(
        acquisition_tax_krw=acq_tax,
        local_edu_tax_krw=edu_tax,
        rural_tax_krw=rural_tax,
        brokerage_fee_krw=brokerage,
        legal_fee_krw=legal,
        bond_discount_krw=bond,
        total_krw=total,
        effective_rate=total / price_krw if price_krw else 0.0,
        breakdown_notes=notes,
        warnings=warnings,
    )


@dataclass
class CapitalGainsTax:
    gross_gain_krw: int
    taxable_base_krw: int
    long_term_deduction_krw: int
    tax_krw: int
    local_income_tax_krw: int
    total_krw: int
    effective_rate: float          # 양도차익 대비
    is_exempt: bool
    notes: list[str] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)


def _progressive_tax(base: int, rules: RuleSet) -> tuple[int, float, int]:
    """누진세율표 적용. (세액, 적용세율, 누진공제)를 돌려준다."""
    for upper, rate, progressive in rules.capital_gains_tax.brackets:
        if base <= upper:
            return max(int(base * rate - progressive), 0), rate, progressive
    return 0, 0.0, 0


def _long_term_deduction(
    gain: int,
    hold_years: float,
    live_years: float,
    is_one_house: bool,
    surcharged: bool,
    rules: RuleSet,
) -> tuple[int, str]:
    """장기보유특별공제. 어느 표를 썼는지도 함께 돌려준다."""
    cgt = rules.capital_gains_tax

    if surcharged:
        # 중과 대상 주택은 장특공제가 전면 배제된다.
        return 0, "중과 대상이라 장특공제 배제"

    if hold_years < cgt.ltd_start_year:
        return 0, f"보유 {cgt.ltd_start_year}년 미만이라 장특공제 없음"

    # 표2: 1세대 1주택이면서 거주 2년 이상. 보유·거주를 따로 계산해 더한다.
    if is_one_house and live_years >= cgt.ltd_single_min_live_years:
        hold_rate = min(int(hold_years) * cgt.ltd_single_hold_per_year, 0.40)
        live_rate = min(int(live_years) * cgt.ltd_single_live_per_year, 0.40)
        ratio = min(hold_rate + live_rate, cgt.ltd_single_max)
        return (
            int(gain * ratio),
            f"1세대1주택 표2: 보유 {hold_rate:.0%} + 거주 {live_rate:.0%} = {ratio:.0%}",
        )

    ratio = min(int(hold_years) * cgt.ltd_rate_per_year, cgt.ltd_max)
    return int(gain * ratio), f"일반 표1: {ratio:.0%}"


def calculate_capital_gains_tax(
    buy_price_krw: int,
    sell_price_krw: int,
    hold_years: float,
    acquisition_cost_krw: int,
    selling_cost_krw: int,
    rules: RuleSet,
    other_houses_at_sale: int = 0,
    live_years: float | None = None,
    acquired_in_regulated_area: bool = False,
    sale_in_regulated_area: bool = False,
) -> CapitalGainsTax:
    """팔 때 내는 양도소득세.

    `other_houses_at_sale`은 **이 집을 뺀** 나머지 보유 주택 수다. 0이면
    1세대 1주택으로 보고 비과세를 판정한다.

    `live_years`를 생략하면 보유기간 내내 거주한 것으로 본다. 거주기간은
    비과세 요건과 장특공제 표2 양쪽에 걸리므로 값이 크게 달라진다.
    """
    cgt = rules.capital_gains_tax
    notes: list[str] = []
    warnings: list[str] = []
    if live_years is None:
        live_years = hold_years

    gross_gain = sell_price_krw - buy_price_krw - acquisition_cost_krw - selling_cost_krw
    notes.append(
        f"양도차익 = 매도가 {sell_price_krw:,} - 취득가 {buy_price_krw:,} "
        f"- 취득비용 {acquisition_cost_krw:,} - 매도비용 {selling_cost_krw:,} = {gross_gain:,}원"
    )

    if gross_gain <= 0:
        notes.append("양도차손이므로 양도소득세는 없다.")
        return CapitalGainsTax(gross_gain, 0, 0, 0, 0, 0, 0.0, False, notes, warnings)

    is_one_house = other_houses_at_sale == 0

    # --- 1세대 1주택 비과세 ---
    if is_one_house and sell_price_krw <= cgt.one_house_exempt_price:
        needs_residence = acquired_in_regulated_area
        residence_ok = (
            not needs_residence or live_years >= cgt.one_house_min_live_years_regulated
        )
        if hold_years >= cgt.one_house_min_hold_years and residence_ok:
            notes.append(
                f"1세대 1주택 비과세: {cgt.one_house_exempt_price:,}원 이하 · "
                f"보유 {hold_years}년"
                + (f" · 거주 {live_years}년 (조정대상지역 취득)" if needs_residence else "")
            )
            warnings.append(
                "비과세는 세대 전체 기준이다. 배우자·세대원 명의 주택이 있으면 적용되지 않는다."
            )
            return CapitalGainsTax(gross_gain, 0, 0, 0, 0, 0, 0.0, True, notes, warnings)
        if not residence_ok:
            notes.append(
                f"취득 당시 조정대상지역이라 거주 "
                f"{cgt.one_house_min_live_years_regulated}년이 필요한데 "
                f"{live_years}년뿐이라 비과세가 안 된다."
            )

    # --- 고가주택 안분 ---
    if is_one_house and sell_price_krw > cgt.one_house_exempt_price:
        taxable_ratio = (sell_price_krw - cgt.one_house_exempt_price) / sell_price_krw
        gain = int(gross_gain * taxable_ratio)
        notes.append(
            f"1세대 1주택 고가주택: {cgt.one_house_exempt_price:,}원 초과분 "
            f"{taxable_ratio:.1%}만 과세 -> {gain:,}원"
        )
    else:
        gain = gross_gain

    # --- 다주택 중과 판정 ---
    surcharge = 0.0
    surcharge_label = ""
    if (
        cgt.multi_house_surcharge_active
        and sale_in_regulated_area
        and other_houses_at_sale >= 1
    ):
        if other_houses_at_sale >= 2:
            surcharge = cgt.surcharge_3house
            surcharge_label = "조정대상지역 3주택 이상"
        else:
            surcharge = cgt.surcharge_2house
            surcharge_label = "조정대상지역 2주택"
        notes.append(
            f"다주택 중과 +{surcharge:.0%}p ({surcharge_label}). "
            f"유예는 {cgt.multi_house_surcharge_grace_until} 양도분까지였고 연장되지 않았다."
        )
        warnings.append(
            "2026-05-09까지 계약을 체결했다면 경과조치로 중과가 빠질 수 있다. "
            "계약일 기준 요건을 확인할 것."
        )

    surcharged = surcharge > 0

    # --- 장기보유특별공제 ---
    ltd, ltd_label = _long_term_deduction(
        gain, hold_years, live_years, is_one_house, surcharged, rules
    )
    if ltd:
        notes.append(f"장기보유특별공제 {ltd_label} = {ltd:,}원 차감")
    else:
        notes.append(ltd_label)

    # --- 과세표준. 기본공제는 보유기간과 무관하게 연 1회 적용된다. ---
    base = max(gain - ltd - cgt.basic_deduction, 0)
    notes.append(f"기본공제 {cgt.basic_deduction:,}원 차감 -> 과세표준 {base:,}원")

    # --- 세율. 단기세율과 (누진+중과) 중 큰 쪽을 쓴다(비교과세). ---
    progressive_tax, prog_rate, prog_deduction = _progressive_tax(base, rules)
    if surcharged:
        # 중과세율 = 기본세율 + 가산분. 누진공제는 기본세율 구조에서 나오는
        # 값이라 중과되더라도 그대로 빼야 한다. 빼먹으면 세액이 누진공제액만큼
        # 통째로 부풀려진다.
        progressive_tax = max(int(base * (prog_rate + surcharge)) - prog_deduction, 0)

    short_term_rate = 0.0
    if hold_years < 1:
        short_term_rate = cgt.under_1year_rate
    elif hold_years < 2:
        short_term_rate = cgt.under_2year_rate

    if short_term_rate:
        short_tax = int(base * short_term_rate)
        if short_tax >= progressive_tax:
            tax = short_tax
            notes.append(f"단기 보유 {hold_years}년 -> 단일세율 {short_term_rate:.0%} 적용")
        else:
            tax = progressive_tax
            notes.append(
                f"단기세율({short_term_rate:.0%})보다 누진+중과가 커서 그쪽을 적용"
            )
    else:
        tax = progressive_tax
        notes.append(
            f"누진세율 {prog_rate:.0%}"
            + (f" + 중과 {surcharge:.0%}p" if surcharged else "")
        )

    local = int(tax * cgt.local_income_tax_ratio)
    total = tax + local
    notes.append(f"양도세 {tax:,}원 + 지방소득세 {local:,}원 = {total:,}원")

    return CapitalGainsTax(
        gross_gain_krw=gross_gain,
        taxable_base_krw=base,
        long_term_deduction_krw=ltd,
        tax_krw=tax,
        local_income_tax_krw=local,
        total_krw=total,
        effective_rate=total / gross_gain if gross_gain else 0.0,
        is_exempt=False,
        notes=notes,
        warnings=warnings,
    )
