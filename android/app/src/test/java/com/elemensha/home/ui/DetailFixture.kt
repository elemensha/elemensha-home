package com.elemensha.home.ui

import com.elemensha.home.data.Baseline
import com.elemensha.home.data.CheckStep
import com.elemensha.home.data.GlossaryItem
import com.elemensha.home.data.ListingDetail
import com.elemensha.home.data.PricePoint
import com.elemensha.home.data.SaleKind
import com.elemensha.home.data.TenancyAnalysis
import com.elemensha.home.data.TenantEntry

/**
 * 펼친 상세 화면을 그려 보려고 만든 고정 자료.
 *
 * 2026-08842-001 을 본떴다. 압류재산이고, 기준선보다 먼저 전입한 임차인이
 * 있는데 보증금 금액이 공고에 없다 - 이 앱에서 가장 위험한 조합이고,
 * 그래서 화면에서 제일 크게 보여야 하는 경우다.
 */
val DETAIL_SAMPLE = ListingDetail(
    address = "서울특별시 중구 을지로3가 12-3",
    notes = "점유자 있음. 명도 책임은 매수자에게 있음.",
    usageStatus = "1층 근린생활시설, 2층 주거용으로 사용 중",
    vicinity = "지하철 2호선 을지로3가역 도보 4분",
    riskFlags = listOf(
        "유의사항에 점유자 기재가 있다",
        "이용현황이 공부상 용도와 다르다",
    ),
    evictionBurden = "매수자",
    delegatingOrg = "서울특별시 중구청",
    areas = listOf(mapOf("구분" to "토지", "면적" to "82.4㎡")),
    appraisals = listOf(
        mapOf("평가기관" to "가온감정평가법인", "감정평가서" to "https://www.onbid.co.kr"),
    ),
    saleKind = SaleKind(
        kind = "압류재산",
        plain = "세금을 안 낸 사람의 재산을 국가가 대신 팔아 세금을 받는 것이다.",
        keyPoint = "인도명령이 없다. 점유자가 안 나가면 명도소송으로 가야 한다.",
        law = "국세징수법 제66조",
    ),
    tenancy = TenancyAnalysis(
        level = "danger",
        summary = "매수인이 떠안을 임차보증금이 있을 수 있고, 금액이 공고에 없다. " +
            "얼마가 낙찰가 위에 얹힐지 모르는 상태다.",
        baseline = Baseline(date = "2012-03-14", kind = "근저당권", holder = "○○은행"),
        tenants = listOf(
            TenantEntry(
                name = "조○○", role = "임차인", moveIn = "2010-11-09",
                confirmed = "2010-11-09", depositKrw = null, status = "senior",
                verdict = "전입 2010-11-09 이 기준선 2012-03-14 보다 빠르다. " +
                    "대항력이 있어 보증금을 낙찰자가 떠안을 수 있다.",
            ),
        ),
        caveat = "온비드 공고 자료로 한 계산이다. 공고에 없는 권리가 등기부에 있을 수 " +
            "있고, 대항력은 전입 다음 날 0시부터 생긴다. 입찰 전에 등기부등본과 " +
            "전입세대확인서로 직접 확인할 것.",
    ),
    priceHistory = listOf(
        PricePoint(price = 530_000_000, at = "2026-07-21"),
        PricePoint(price = 477_000_000, at = "2026-08-18"),
        PricePoint(price = 412_000_000, at = "2026-09-08"),
    ),
    checklist = listOf(
        CheckStep(
            step = 1, title = "등기부등본을 뗀다",
            why = "말소기준권리가 언제인지 알아야 임차인 순위를 판단할 수 있다.",
            how = "인터넷등기소에서 소재지로 열람한다.",
            judge = "가장 빠른 (근)저당·압류·가압류 날짜가 기준선이다.",
            cost = "700원",
        ),
        CheckStep(
            step = 2, title = "전입세대확인서를 뗀다",
            why = "공고에 없는 세대가 살고 있을 수 있다.",
            how = "주민센터에서 매각공고문을 들고 신청한다.",
            judge = "기준선보다 빠른 전입이 있으면 보증금을 떠안는다.",
            cost = "400원",
        ),
    ),
    glossary = listOf(
        GlossaryItem(
            term = "말소기준권리",
            plain = "등기부에서 가장 먼저 잡힌 (근)저당·압류 같은 권리다. " +
                "낙찰되면 이것과 그 뒤의 권리는 전부 지워진다.",
            impact = "이 날짜보다 먼저 전입한 임차인의 보증금은 지워지지 않고 " +
                "낙찰자가 떠안는다.",
            law = "민사집행법 제91조",
        ),
        GlossaryItem(
            term = "대항력",
            plain = "임차인이 집을 넘겨받고 전입신고를 마치면 생기는 힘이다.",
            impact = "대항력 있는 임차인은 낙찰자에게 '내 보증금 돌려달라'고 할 수 있다.",
            law = "주택임대차보호법 제3조",
        ),
    ),
    rights = listOf(
        mapOf("구분" to "근저당권", "권리자" to "○○은행", "등기일" to "2012-03-14",
              "설정액" to "240000000"),
        mapOf("구분" to "압류", "권리자" to "중구청", "등기일" to "2025-06-02"),
    ),
)
