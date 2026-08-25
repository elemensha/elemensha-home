package com.elemensha.home.data

import kotlinx.serialization.SerialName
import kotlinx.serialization.Serializable
import kotlinx.serialization.json.JsonElement
import kotlinx.serialization.json.JsonObject
import kotlinx.serialization.json.contentOrNull
import kotlinx.serialization.json.jsonPrimitive

/**
 * 서버 JSON과 1:1로 맞춘 모델.
 *
 * 필드명이 곧 JSON 키다. 이름을 바꾸면 서버와 어긋나는데, 파싱 예외가 아니라
 * 값이 조용히 기본값으로 채워지는 형태로 터진다. 릴리스 빌드에서 R8이 필드명을
 * 줄여도 같은 일이 생기므로 proguard-rules.pro에서 keep 해뒀다.
 */

@Serializable
data class Listing(
    val source: String = "",
    @SerialName("source_id") val sourceId: String = "",
    @SerialName("dedupe_key") val dedupeKey: String? = null,
    val title: String = "",
    val url: String = "",
    val sido: String = "",
    val sigungu: String = "",
    val address: String = "",
    @SerialName("property_type") val propertyType: String = "",
    @SerialName("exclusive_area_sqm") val exclusiveAreaSqm: Double? = null,
    @SerialName("appraised_price_krw") val appraisedPriceKrw: Long? = null,
    @SerialName("min_bid_price_krw") val minBidPriceKrw: Long? = null,
    @SerialName("asking_price_krw") val askingPriceKrw: Long? = null,
    @SerialName("effective_price_krw") val effectivePriceKrw: Long? = null,
    val deadline: String? = null,
    @SerialName("failed_bid_count") val failedBidCount: Int = 0,
    @SerialName("market_price_krw") val marketPriceKrw: Long? = null,
    @SerialName("discount_ratio") val discountRatio: Double? = null,
    @SerialName("first_seen_at") val firstSeenAt: String = "",
    val notified: Boolean = false,
    val raw: JsonElement? = null,
) {
    /** 토지는 명도 대상이 없다. 공매에서 이 차이가 크다. */
    val isLand: Boolean get() = propertyType == "토지"
    /** 화면에 쓸 평 단위. 전용면적 기준이라 분양면적보다 작게 나온다. */
    val pyeong: Double? get() = exclusiveAreaSqm?.let { it / 3.3058 }

    private fun rawText(key: String): String =
        (raw as? JsonObject)?.get(key)?.jsonPrimitive?.contentOrNull.orEmpty()

    val usageMinor: String get() = rawText("usage_minor")
    val caution: String get() = rawText("caution")
    val needsFarmlandPermit: Boolean
        get() = (raw as? JsonObject)?.get("needs_farmland_permit")
            ?.jsonPrimitive?.contentOrNull == "true"
}

@Serializable
data class ListingsResponse(
    val items: List<Listing> = emptyList(),
    /** 조건을 통과한 전체 건수. 화면에 몇 건 중 몇 건인지 보여준다. */
    @SerialName("total_matched") val totalMatched: Int = 0,
    @SerialName("filters_applied") val filtersApplied: List<String> = emptyList(),
)

@Serializable
data class FilterProfile(
    val id: Int? = null,
    val name: String = "내 조건",
    val enabled: Boolean = true,
    val sources: List<String> = listOf("onbid"),
    val sido: List<String> = listOf("서울특별시", "경기도"),
    val sigungu: List<String> = emptyList(),
    @SerialName("min_price_krw") val minPriceKrw: Long = 0,
    @SerialName("max_price_krw") val maxPriceKrw: Long = 2_000_000_000,
    @SerialName("min_area_sqm") val minAreaSqm: Double = 0.0,
    @SerialName("max_area_sqm") val maxAreaSqm: Double = 1000.0,
    @SerialName("property_types") val propertyTypes: List<String> = listOf("아파트"),
    @SerialName("min_discount_ratio") val minDiscountRatio: Double? = null,
    @SerialName("use_loan_capacity_as_budget") val useLoanCapacityAsBudget: Boolean = true,
)

@Serializable
data class FiltersResponse(val items: List<FilterProfile> = emptyList())

// ---------------------------------------------------------------- 자금계획

@Serializable
data class BorrowerProfile(
    @SerialName("annual_income_krw") val annualIncomeKrw: Long = 0,
    @SerialName("cash_krw") val cashKrw: Long = 0,
    /** 보유 주택 수. LTV 구간과 취득세 중과가 둘 다 여기서 갈린다. */
    @SerialName("owned_houses") val ownedHouses: Int = 0,
    @SerialName("is_first_time_buyer") val isFirstTimeBuyer: Boolean = false,
    /** 규제지역 1주택자는 처분조건 유무로 LTV가 0%와 40%를 오간다. */
    @SerialName("has_disposal_condition") val hasDisposalCondition: Boolean = false,
    @SerialName("is_low_income_priority") val isLowIncomePriority: Boolean = false,
    @SerialName("existing_annual_repayment_krw") val existingAnnualRepaymentKrw: Long = 0,
    @SerialName("annual_rate") val annualRate: Double = 0.042,
    @SerialName("loan_years") val loanYears: Int = 30,
    @SerialName("monthly_rent_saved_krw") val monthlyRentSavedKrw: Long = 0,
)

@Serializable
data class PlanRequest(
    val profile: BorrowerProfile,
    @SerialName("price_krw") val priceKrw: Long,
    @SerialName("exclusive_area_sqm") val exclusiveAreaSqm: Double = 84.9,
    @SerialName("is_regulated_area") val isRegulatedArea: Boolean = false,
    @SerialName("is_auction") val isAuction: Boolean = false,
    @SerialName("hold_years") val holdYears: Double = 5.0,
    /** 실제 거주 기간. 비과세 요건과 장특공제 표2가 여기서 갈린다. */
    @SerialName("live_years") val liveYears: Double? = null,
    @SerialName("sell_price_options_krw") val sellPriceOptionsKrw: List<Long> = emptyList(),
)

@Serializable
data class LoanCapacity(
    @SerialName("ltv_limit_krw") val ltvLimitKrw: Long = 0,
    @SerialName("dsr_limit_krw") val dsrLimitKrw: Long = 0,
    @SerialName("absolute_cap_krw") val absoluteCapKrw: Long? = null,
    @SerialName("limit_krw") val limitKrw: Long = 0,
    /** "LTV" / "DSR" / "절대한도" — 어디에 막혔는지가 금액보다 중요하다. */
    @SerialName("binding_constraint") val bindingConstraint: String = "",
    @SerialName("ltv_ratio_applied") val ltvRatioApplied: Double = 0.0,
    @SerialName("dsr_ratio_applied") val dsrRatioApplied: Double = 0.0,
    @SerialName("stress_rate_applied") val stressRateApplied: Double = 0.0,
    @SerialName("monthly_payment_krw") val monthlyPaymentKrw: Long = 0,
    val notes: List<String> = emptyList(),
)

@Serializable
data class AcquisitionCost(
    @SerialName("acquisition_tax_krw") val acquisitionTaxKrw: Long = 0,
    @SerialName("local_edu_tax_krw") val localEduTaxKrw: Long = 0,
    @SerialName("rural_tax_krw") val ruralTaxKrw: Long = 0,
    @SerialName("brokerage_fee_krw") val brokerageFeeKrw: Long = 0,
    @SerialName("legal_fee_krw") val legalFeeKrw: Long = 0,
    @SerialName("bond_discount_krw") val bondDiscountKrw: Long = 0,
    @SerialName("total_krw") val totalKrw: Long = 0,
    @SerialName("effective_rate") val effectiveRate: Double = 0.0,
    @SerialName("breakdown_notes") val breakdownNotes: List<String> = emptyList(),
    val warnings: List<String> = emptyList(),
)

@Serializable
data class HoldingCost(
    @SerialName("annual_interest_krw") val annualInterestKrw: Long = 0,
    @SerialName("annual_property_tax_krw") val annualPropertyTaxKrw: Long = 0,
    @SerialName("annual_maintenance_krw") val annualMaintenanceKrw: Long = 0,
    @SerialName("annual_rental_income_krw") val annualRentalIncomeKrw: Long = 0,
    @SerialName("annual_rent_saved_krw") val annualRentSavedKrw: Long = 0,
    @SerialName("annual_net_krw") val annualNetKrw: Long = 0,
    val notes: List<String> = emptyList(),
)

@Serializable
data class ScenarioResult(
    val label: String = "",
    /** 이 매도가가 어디서 왔는지. 예측이 아니라는 걸 화면에 그대로 보여준다. */
    val basis: String = "",
    @SerialName("sell_price_krw") val sellPriceKrw: Long = 0,
    @SerialName("hold_years") val holdYears: Double = 0.0,
    @SerialName("equity_invested_krw") val equityInvestedKrw: Long = 0,
    @SerialName("loan_krw") val loanKrw: Long = 0,
    @SerialName("loan_balance_at_sale_krw") val loanBalanceAtSaleKrw: Long = 0,
    @SerialName("selling_cost_krw") val sellingCostKrw: Long = 0,
    @SerialName("capital_gains_tax_krw") val capitalGainsTaxKrw: Long = 0,
    @SerialName("cumulative_holding_cash_krw") val cumulativeHoldingCashKrw: Long = 0,
    @SerialName("net_proceeds_krw") val netProceedsKrw: Long = 0,
    @SerialName("net_profit_krw") val netProfitKrw: Long = 0,
    val roi: Double = 0.0,
    @SerialName("annualized_roi") val annualizedRoi: Double = 0.0,
    val notes: List<String> = emptyList(),
    val warnings: List<String> = emptyList(),
)

/** 파라미터 하나의 출처. status가 verified가 아니면 화면에 경고를 띄운다. */
@Serializable
data class Citation(
    val parameter: String = "",
    val label: String = "",
    val status: String = "unverified",
    val authority: String = "",
    val document: String = "",
    val url: String = "",
    @SerialName("effective_date") val effectiveDate: String = "",
    @SerialName("verified_at") val verifiedAt: String = "",
    val note: String = "",
    val warning: String = "",
) {
    val isVerified: Boolean get() = status == "verified"
}

@Serializable
data class PlanSources(
    val summary: String = "",
    val used: List<Citation> = emptyList(),
    @SerialName("unverified_count") val unverifiedCount: Int = 0,
    val unverified: List<Citation> = emptyList(),
)

@Serializable
data class PlanResponse(
    @SerialName("ruleset_version") val rulesetVersion: String = "",
    @SerialName("ruleset_note") val rulesetNote: String = "",
    val sources: PlanSources = PlanSources(),
    @SerialName("max_affordable_price_krw") val maxAffordablePriceKrw: Long = 0,
    val capacity: LoanCapacity = LoanCapacity(),
    @SerialName("acquisition_cost") val acquisitionCost: AcquisitionCost = AcquisitionCost(),
    @SerialName("cash_needed_krw") val cashNeededKrw: Long = 0,
    @SerialName("cash_shortfall_krw") val cashShortfallKrw: Long = 0,
    val holding: HoldingCost = HoldingCost(),
    val scenarios: List<ScenarioResult> = emptyList(),
    val disclaimer: String = "",
)

// ---------------------------------------------------------------- 인앱 업데이트

/** 서버가 중계하는 GitHub Releases 최신 정보. */
@Serializable
data class AppVersionInfo(
    val versionName: String = "",
    val versionCode: Int = 0,
    val apkUrl: String? = null,
    val apkSize: Long? = null,
    val notes: String = "",
    val publishedAt: String? = null,
    /** "github" = 실제 릴리스, "server" = 릴리스를 못 읽어 바닥값을 돌려준 것 */
    val source: String = "",
)

// ---------------------------------------------------------------- 상태

@Serializable
data class SourceCoverage(
    val total: Int = 0,
    val verified: Int = 0,
    val ratio: Double = 0.0,
)

@Serializable
data class PollStatus(
    val source: String = "",
    @SerialName("last_run") val lastRun: String = "",
    val ok: Boolean = false,
    val fetched: Int = 0,
    @SerialName("new") val newCount: Int = 0,
    val error: String? = null,
)

@Serializable
data class HealthResponse(
    val ok: Boolean = false,
    @SerialName("sources_configured") val sourcesConfigured: Map<String, Boolean> = emptyMap(),
    @SerialName("poll_status") val pollStatus: List<PollStatus> = emptyList(),
    @SerialName("listing_count") val listingCount: Map<String, Int> = emptyMap(),
    @SerialName("ruleset_version") val rulesetVersion: String = "",
    @SerialName("source_coverage") val sourceCoverage: SourceCoverage = SourceCoverage(),
    @SerialName("auth_enabled") val authEnabled: Boolean = false,
)
