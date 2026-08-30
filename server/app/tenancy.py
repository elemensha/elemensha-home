"""전입일과 말소기준권리를 비교해 보증금 인수 위험을 판정한다.

공매에서 값을 매길 때 가장 크게 틀리는 지점이 여기다. 낙찰가 4억짜리
물건에 대항력 있는 임차인이 있으면 보증금이 그 위에 얹힌다. 그 사실을
모르고 예산을 짜면 낙찰받은 뒤에 알게 된다.

판정은 단순하다. 등기부에서 가장 빠른 (근)저당권·압류·가압류·담보가등기·
경매개시결정등기가 기준선이고, 임차인의 전입일이 그보다 빠르면 대항력이
있어 낙찰자가 보증금을 떠안는다.

**이건 공고 데이터로 한 계산이고 등기부 원본이 아니다.** 온비드 공고에
안 나오는 권리가 등기부에 있을 수 있다. 그래서 결과에 항상 '등기부로
직접 확인하라'를 붙여 내보낸다.
"""

from __future__ import annotations

import re

# 말소의 기준이 되는 권리들. 이 중 가장 먼저 등기된 것이 기준선이다.
# '위임기관'은 공매를 맡긴 기관 기록이지 권리가 아니라서 뺀다.
BASELINE_KINDS = (
    "근저당", "저당", "압류", "가압류", "담보가등기", "경매개시결정", "강제경매",
)


def _ymd(value: str) -> str:
    """'20101109' -> '2010-11-09'. 못 읽으면 빈 문자열."""
    digits = re.sub(r"\D", "", str(value or ""))
    if len(digits) != 8:
        return ""
    return f"{digits[:4]}-{digits[4:6]}-{digits[6:]}"


def _amount(value) -> int | None:
    digits = re.sub(r"\D", "", str(value or ""))
    return int(digits) if digits else None


def find_baseline(rights: list[dict]) -> dict | None:
    """말소기준권리. 없으면 None."""
    found = []
    for r in rights or []:
        kind = str(r.get("구분") or "")
        if not any(k in kind for k in BASELINE_KINDS):
            continue
        date = _ymd(r.get("등기일"))
        if date:
            found.append({"date": date, "kind": kind,
                          "holder": str(r.get("권리자") or "")})
    if not found:
        return None
    return min(found, key=lambda x: x["date"])


def analyze(detail: dict) -> dict:
    """보증금 인수 위험 판정. 판단할 근거가 없으면 빈 dict."""
    tenants_raw = detail.get("tenancies") or []
    rights = detail.get("rights") or []
    if not tenants_raw:
        return {}

    baseline = find_baseline(rights)
    tenants = []
    senior = unknown_amount = False

    for t in tenants_raw:
        move_in = _ymd(t.get("전입일"))
        deposit = _amount(t.get("보증금")) or _amount(t.get("환산보증금"))
        entry = {
            "name": str(t.get("이름") or ""),
            "role": str(t.get("구분") or ""),
            "move_in": move_in,
            "confirmed": _ymd(t.get("확정자")) or _ymd(t.get("확정일자")),
            "deposit_krw": deposit,
        }

        if not baseline or not move_in:
            entry["status"] = "unknown"
            entry["verdict"] = (
                "전입일이나 기준선을 알 수 없어 판단할 수 없다. "
                "등기부와 전입세대확인서로 직접 확인할 것."
            )
        elif move_in < baseline["date"]:
            # 대항력은 전입 다음 날 0시부터라, 같은 날이면 후순위다.
            entry["status"] = "senior"
            entry["verdict"] = (
                f"전입 {move_in} 이 기준선 {baseline['date']} 보다 빠르다. "
                "대항력이 있어 보증금을 낙찰자가 떠안을 수 있다."
            )
            senior = True
            if deposit is None:
                unknown_amount = True
        else:
            entry["status"] = "junior"
            entry["verdict"] = (
                f"전입 {move_in} 이 기준선 {baseline['date']} 이후다. "
                "보증금은 인수하지 않지만, 나가지 않으면 명도는 해야 한다."
            )
        tenants.append(entry)

    if senior and unknown_amount:
        level, summary = "danger", (
            "매수인이 떠안을 임차보증금이 있을 수 있고, 금액이 공고에 없다. "
            "얼마가 낙찰가 위에 얹힐지 모르는 상태다. 등기부와 전입세대확인서로 "
            "확인하기 전에는 입찰가를 정할 수 없다."
        )
    elif senior:
        total = sum(t["deposit_krw"] or 0 for t in tenants if t["status"] == "senior")
        level, summary = "danger", (
            f"매수인이 떠안을 임차보증금이 있을 수 있다(공고상 {total:,}원). "
            "낙찰가에 이 금액을 더한 것이 실제로 드는 돈이다."
        )
    elif any(t["status"] == "unknown" for t in tenants):
        level, summary = "caution", (
            "임차인 기재는 있으나 순위를 판단할 자료가 부족하다. "
            "직접 확인하지 않으면 인수 여부를 알 수 없다."
        )
    else:
        level, summary = "caution", (
            "공고상 임차인은 모두 기준선 이후라 보증금 인수는 없어 보인다. "
            "다만 점유자가 있으면 명도는 별개의 문제다."
        )

    return {
        "level": level,
        "summary": summary,
        "baseline": baseline,
        "tenants": tenants,
        "caveat": (
            "온비드 공고 자료로 한 계산이다. 공고에 없는 권리가 등기부에 있을 수 "
            "있고, 대항력은 전입과 실제 점유가 모두 있어야 하며 전입 다음 날 "
            "0시부터 생긴다. 입찰 전에 등기부등본과 전입세대확인서로 직접 확인할 것."
        ),
    }
