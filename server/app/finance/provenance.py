"""파라미터마다 출처를 묶어두는 계층.

이 앱이 내놓는 숫자는 사람이 수천만원짜리 결정을 하는 데 쓰인다. "LTV 70%"라는
값만 보여주면 그게 법령에서 온 건지 누가 기억으로 적은 건지 구분되지 않는다.
그래서 **모든 파라미터는 기본이 미검증(UNVERIFIED)이고**, 1차 출처를 확인한
것만 검증됨으로 올린다. 앱은 미검증 값을 쓸 때 그 사실을 화면에 표시한다.

검증 결과는 `data/citations.json`으로 들어온다. 코드를 고치지 않고 갱신할 수
있어야 규제가 바뀔 때마다 배포하지 않아도 되기 때문이다.
"""

from __future__ import annotations

import json
from dataclasses import asdict, dataclass, field
from enum import Enum
from pathlib import Path


class Status(str, Enum):
    VERIFIED = "verified"          # 1차 출처로 확인됨
    UNVERIFIED = "unverified"      # 출처 없음. 기억·추정에서 온 값
    CONFLICTING = "conflicting"    # 출처마다 값이 다름
    EXPIRED = "expired"            # 일몰·유예 종료로 더 이상 유효하지 않음
    UNKNOWN = "unknown"            # 확인 시도했으나 근거를 못 찾음


# 미검증 상태에서 사용자에게 보여줄 경고. 상태별로 강도가 다르다.
STATUS_WARNING = {
    Status.VERIFIED: "",
    Status.UNVERIFIED: "출처 미확인 값이다. 실제 규정과 다를 수 있다.",
    Status.CONFLICTING: "출처마다 값이 달라 확정하지 못했다. 반드시 직접 확인할 것.",
    Status.EXPIRED: "만료된 규정일 수 있다. 현행 여부를 확인하기 전에는 쓰지 말 것.",
    Status.UNKNOWN: "근거를 찾지 못했다. 이 값에 기대어 판단하지 말 것.",
}


@dataclass(frozen=True)
class Citation:
    """파라미터 하나의 출처."""

    parameter: str                 # "ltv.normal_no_house" 처럼 점으로 구분한 경로
    label: str                     # 사람이 읽을 이름
    status: Status = Status.UNVERIFIED
    authority: str = ""            # 금융위원회, 국세청, 법제처 ...
    document: str = ""             # 문서 제목 또는 법령명·조항
    url: str = ""
    effective_date: str = ""       # 시행일
    verified_at: str = ""          # 확인한 날짜
    note: str = ""

    @property
    def warning(self) -> str:
        return STATUS_WARNING.get(self.status, "")

    def to_dict(self) -> dict:
        data = asdict(self)
        data["status"] = self.status.value
        data["warning"] = self.warning
        return data


def _stub(parameter: str, label: str) -> Citation:
    return Citation(parameter=parameter, label=label)


# 검증 대상 파라미터 전체 목록. 여기 없는 값을 계산에 쓰면 출처 추적이 끊긴다.
# 처음에는 전부 미검증이고, 1차 출처를 확인한 것만 citations.json이 덮어쓴다.
PARAMETERS: list[Citation] = [
    # 대출 - LTV
    _stub("ltv.regulated_no_house", "규제지역 무주택 LTV"),
    _stub("ltv.regulated_one_house", "규제지역 1주택 LTV"),
    _stub("ltv.regulated_multi_house", "규제지역 다주택 LTV"),
    _stub("ltv.normal_no_house", "비규제지역 무주택 LTV"),
    _stub("ltv.normal_one_house", "비규제지역 1주택 LTV"),
    _stub("ltv.normal_multi_house", "비규제지역 다주택 LTV"),
    _stub("ltv.first_time_buyer", "생애최초 LTV 상한"),
    _stub("ltv.metro_loan_cap_krw", "수도권·규제지역 주담대 절대한도"),
    # 대출 - DSR
    _stub("dsr.bank_ratio", "은행권 DSR 상한"),
    _stub("dsr.non_bank_ratio", "제2금융권 DSR 상한"),
    _stub("dsr.stress_rate_metro", "스트레스 DSR 가산금리(수도권)"),
    _stub("dsr.stress_rate_non_metro", "스트레스 DSR 가산금리(비수도권)"),
    _stub("dsr.exempt_below_krw", "DSR 산정 제외 기준"),
    # 취득세
    _stub("acquisition_tax.tier1_limit", "취득세 1구간 상한(6억)"),
    _stub("acquisition_tax.tier1_rate", "취득세 1구간 세율"),
    _stub("acquisition_tax.tier3_limit", "취득세 3구간 하한(9억)"),
    _stub("acquisition_tax.tier3_rate", "취득세 3구간 세율"),
    _stub("acquisition_tax.progressive_formula", "6~9억 구간 누진 산식"),
    _stub("acquisition_tax.heavy_2house_regulated", "조정대상지역 2주택 중과"),
    _stub("acquisition_tax.heavy_3house", "3주택 이상 중과"),
    _stub("acquisition_tax.local_edu_tax_ratio", "지방교육세 비율"),
    _stub("acquisition_tax.rural_tax_rate", "농어촌특별세율"),
    _stub("acquisition_tax.exclusive_area_exempt_sqm", "농특세 비과세 면적기준"),
    _stub("acquisition_tax.first_time_relief_cap", "생애최초 취득세 감면 한도"),
    # 양도소득세
    _stub("capital_gains_tax.basic_deduction", "양도소득 기본공제"),
    _stub("capital_gains_tax.under_1year_rate", "1년 미만 보유 세율"),
    _stub("capital_gains_tax.under_2year_rate", "1~2년 보유 세율"),
    _stub("capital_gains_tax.brackets", "양도세 누진세율표"),
    _stub("capital_gains_tax.local_income_tax_ratio", "지방소득세 비율"),
    _stub("capital_gains_tax.one_house_exempt_price", "1세대1주택 비과세 기준가"),
    _stub("capital_gains_tax.one_house_min_hold_years", "비과세 최소 보유기간"),
    _stub("capital_gains_tax.ltd_start_year", "장특공제 시작 연수"),
    _stub("capital_gains_tax.ltd_rate_per_year", "장특공제 연간 공제율"),
    _stub("capital_gains_tax.ltd_max", "장특공제 최대율"),
    _stub("capital_gains_tax.multi_house_surcharge", "다주택 중과 시행 여부"),
    # 거래비용
    _stub("transaction_cost.brokerage_brackets", "중개보수 상한요율"),
    _stub("transaction_cost.legal_fee", "법무사 보수"),
    _stub("transaction_cost.bond_discount_ratio", "국민주택채권 할인손실률"),
    # 보유세
    _stub("property_tax.fair_market_ratio", "재산세 공정시장가액비율"),
    _stub("property_tax.brackets", "재산세 누진세율표"),
    _stub("property_tax.single_house_relief", "1주택 특례세율"),
    _stub("property_tax.urban_area_rate", "도시지역분 세율"),
    _stub("comprehensive_tax.threshold", "종합부동산세 공제액"),
    _stub("comprehensive_tax.brackets", "종합부동산세 세율"),
    # 지역
    _stub("regions.regulated_areas", "규제지역 지정 현황"),
]


class Provenance:
    """출처 대장. 파라미터 경로로 조회한다."""

    def __init__(self, citations: dict[str, Citation]) -> None:
        self._citations = citations

    def get(self, parameter: str) -> Citation:
        return self._citations.get(parameter, _stub(parameter, parameter))

    def all(self) -> list[Citation]:
        return list(self._citations.values())

    def by_status(self, status: Status) -> list[Citation]:
        return [c for c in self._citations.values() if c.status is status]

    def coverage(self) -> dict:
        """검증률. 앱 화면에 그대로 띄운다 - 낮으면 낮은 대로 보여줘야 한다."""
        total = len(self._citations)
        counts: dict[str, int] = {}
        for citation in self._citations.values():
            counts[citation.status.value] = counts.get(citation.status.value, 0) + 1
        verified = counts.get(Status.VERIFIED.value, 0)
        return {
            "total": total,
            "verified": verified,
            "ratio": round(verified / total, 3) if total else 0.0,
            "by_status": counts,
        }

    def trust_summary(self) -> str:
        """계산 결과에 함께 실어 보낼 한 줄."""
        cov = self.coverage()
        if cov["verified"] == cov["total"]:
            return "모든 파라미터가 1차 출처로 검증됐다."
        return (
            f"파라미터 {cov['total']}개 중 {cov['verified']}개만 1차 출처로 확인됐다. "
            f"나머지는 미검증 값이므로 실제 규정과 다를 수 있다."
        )

    def to_dict(self) -> dict:
        return {
            "coverage": self.coverage(),
            "summary": self.trust_summary(),
            "citations": [c.to_dict() for c in self._citations.values()],
        }


# 코드와 함께 배포되는 기본 출처 대장. 검증 결과는 런타임 상태가 아니라
# 코드와 같은 수명을 갖는 사실이므로 data/ 가 아니라 패키지 안에 둔다.
# (data/ 에 두었더니 배포 tar 에서 제외돼 서버 검증률이 0으로 떨어졌다.)
BUNDLED_CITATIONS = Path(__file__).with_name("citations.json")


def _apply(citations: dict[str, Citation], path: Path) -> None:
    raw = json.loads(path.read_text(encoding="utf-8"))
    for entry in raw.get("citations", []):
        parameter = entry.get("parameter")
        if not parameter:
            continue
        base = citations.get(parameter)
        citations[parameter] = Citation(
            parameter=parameter,
            label=entry.get("label") or (base.label if base else parameter),
            status=Status(entry.get("status", Status.UNVERIFIED.value)),
            authority=entry.get("authority", ""),
            document=entry.get("document", ""),
            url=entry.get("url", ""),
            effective_date=entry.get("effective_date", ""),
            verified_at=entry.get("verified_at", ""),
            note=entry.get("note", ""),
        )


def load_provenance(path: Path | None = None) -> Provenance:
    """패키지에 담긴 대장을 먼저 읽고, 운영 파일이 있으면 그 위에 덮어쓴다.

    규제가 바뀌면 재배포 없이 data/citations.json 만 갈아끼우면 된다.
    """
    citations = {c.parameter: c for c in PARAMETERS}

    if BUNDLED_CITATIONS.exists():
        _apply(citations, BUNDLED_CITATIONS)
    if path is not None and path.exists():
        _apply(citations, path)

    return Provenance(citations)
