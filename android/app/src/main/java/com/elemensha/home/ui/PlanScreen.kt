package com.elemensha.home.ui

import androidx.compose.foundation.layout.Arrangement
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.ColumnScope
import androidx.compose.foundation.layout.Row
import androidx.compose.foundation.layout.Spacer
import androidx.compose.foundation.layout.fillMaxWidth
import androidx.compose.foundation.layout.height
import androidx.compose.foundation.layout.padding
import androidx.compose.foundation.lazy.LazyColumn
import androidx.compose.foundation.text.KeyboardOptions
import androidx.compose.material3.Button
import androidx.compose.material3.Card
import androidx.compose.material3.CardDefaults
import androidx.compose.material3.CircularProgressIndicator
import androidx.compose.material3.FilterChip
import androidx.compose.material3.HorizontalDivider
import androidx.compose.material3.MaterialTheme
import androidx.compose.material3.OutlinedTextField
import androidx.compose.material3.Switch
import androidx.compose.material3.Text
import androidx.compose.runtime.Composable
import androidx.compose.runtime.getValue
import androidx.compose.runtime.mutableStateOf
import androidx.compose.runtime.remember
import androidx.compose.runtime.setValue
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.text.font.FontWeight
import androidx.compose.ui.text.input.KeyboardType
import androidx.compose.ui.unit.dp
import com.elemensha.home.UiState
import com.elemensha.home.data.BorrowerProfile
import com.elemensha.home.data.Citation
import com.elemensha.home.data.PlanResponse

/**
 * 자금계획 화면.
 *
 * 설계 원칙 두 가지가 화면에 그대로 드러나야 한다.
 * 1. 매도가는 **가정**이다. 앱이 집값을 예측하지 않는다는 걸 숨기지 않는다.
 * 2. 출처가 검증되지 않은 파라미터로 계산했으면 그 사실을 결과 옆에 붙인다.
 */
@Composable
fun PlanScreen(
    state: UiState,
    onBorrowerChange: (BorrowerProfile) -> Unit,
    onCalculate: (Long, Double, Boolean, Boolean, Double, List<Long>) -> Unit,
) {
    val borrower = state.borrower

    var priceText by remember { mutableStateOf("") }
    var areaText by remember { mutableStateOf("84.9") }
    var isRegulated by remember { mutableStateOf(false) }
    var isAuction by remember { mutableStateOf(false) }
    var holdYearsText by remember { mutableStateOf("5") }
    var sellText by remember { mutableStateOf("") }

    LazyColumn(
        modifier = Modifier.fillMaxWidth().padding(horizontal = 16.dp),
        verticalArrangement = Arrangement.spacedBy(12.dp),
    ) {
        item { Spacer(Modifier.height(8.dp)) }

        item {
            SectionCard("내 자산") {
                MoneyField("연소득 (세전)", borrower.annualIncomeKrw) {
                    onBorrowerChange(borrower.copy(annualIncomeKrw = it))
                }
                MoneyField("동원 가능 현금", borrower.cashKrw) {
                    onBorrowerChange(borrower.copy(cashKrw = it))
                }
                MoneyField("기존 대출 연 상환액", borrower.existingAnnualRepaymentKrw) {
                    onBorrowerChange(borrower.copy(existingAnnualRepaymentKrw = it))
                }
                MoneyField(
                    "실거주 시 안 내게 되는 월세",
                    borrower.monthlyRentSavedKrw,
                    hint = "이걸 비우면 이자만 비용으로 잡혀 결과가 실제보다 나쁘게 나온다",
                ) {
                    onBorrowerChange(borrower.copy(monthlyRentSavedKrw = it))
                }

                Spacer(Modifier.height(8.dp))
                Text("보유 주택 수", style = MaterialTheme.typography.labelLarge)
                Row(horizontalArrangement = Arrangement.spacedBy(8.dp)) {
                    listOf(0 to "무주택", 1 to "1주택", 2 to "2주택", 3 to "3주택+")
                        .forEach { (value, label) ->
                            FilterChip(
                                selected = borrower.ownedHouses == value,
                                onClick = { onBorrowerChange(borrower.copy(ownedHouses = value)) },
                                label = { Text(label) },
                            )
                        }
                }

                ToggleRow("생애최초 구입", borrower.isFirstTimeBuyer) {
                    onBorrowerChange(borrower.copy(isFirstTimeBuyer = it))
                }
                if (borrower.ownedHouses >= 1) {
                    ToggleRow("기존 주택 처분조건 설정", borrower.hasDisposalCondition) {
                        onBorrowerChange(borrower.copy(hasDisposalCondition = it))
                    }
                    Text(
                        "규제지역 1주택자는 처분조건이 없으면 주담대가 아예 나오지 않는다 (LTV 0%).",
                        style = MaterialTheme.typography.bodySmall,
                        color = WarningAmber,
                    )
                }
                ToggleRow("서민·실수요자 우대 대상", borrower.isLowIncomePriority) {
                    onBorrowerChange(borrower.copy(isLowIncomePriority = it))
                }

                Row(
                    Modifier.fillMaxWidth(),
                    horizontalArrangement = Arrangement.spacedBy(8.dp),
                ) {
                    NumberField(
                        "금리 (%)",
                        (borrower.annualRate * 100).toString(),
                        Modifier.weight(1f),
                    ) { text ->
                        text.toDoubleOrNull()?.let {
                            onBorrowerChange(borrower.copy(annualRate = it / 100))
                        }
                    }
                    NumberField(
                        "만기 (년)",
                        borrower.loanYears.toString(),
                        Modifier.weight(1f),
                    ) { text ->
                        text.toIntOrNull()?.let {
                            onBorrowerChange(borrower.copy(loanYears = it))
                        }
                    }
                }
            }
        }

        item {
            SectionCard("검토할 물건") {
                MoneyFieldText("매매가 / 최저입찰가", priceText) { priceText = it }
                NumberField("전용면적 (㎡)", areaText) { areaText = it }
                NumberField("보유 예정 기간 (년)", holdYearsText) { holdYearsText = it }
                ToggleRow("규제지역", isRegulated) { isRegulated = it }
                ToggleRow("경매·공매 물건", isAuction) { isAuction = it }

                Spacer(Modifier.height(8.dp))
                OutlinedTextField(
                    value = sellText,
                    onValueChange = { sellText = it },
                    label = { Text("매도 가정 (만원, 쉼표로 구분)") },
                    supportingText = {
                        Text("예: 50000, 55000, 60000 — 예측이 아니라 '이 값에 팔린다면' 가정이다")
                    },
                    singleLine = true,
                    keyboardOptions = KeyboardOptions(keyboardType = KeyboardType.Number),
                    modifier = Modifier.fillMaxWidth(),
                )

                Spacer(Modifier.height(12.dp))
                Button(
                    onClick = {
                        val price = parseManwonInput(priceText)
                        if (price <= 0) return@Button
                        val sells = sellText.split(",", " ")
                            .mapNotNull { it.filter(Char::isDigit).toLongOrNull() }
                            .map { it * 10_000 }
                        onCalculate(
                            price,
                            areaText.toDoubleOrNull() ?: 84.9,
                            isRegulated,
                            isAuction,
                            holdYearsText.toDoubleOrNull() ?: 5.0,
                            sells,
                        )
                    },
                    enabled = !state.loading && state.isConfigured,
                    modifier = Modifier.fillMaxWidth(),
                ) {
                    if (state.loading) {
                        CircularProgressIndicator(Modifier.height(18.dp), strokeWidth = 2.dp)
                    } else {
                        Text("계산")
                    }
                }
                if (!state.isConfigured) {
                    Text(
                        "설정 탭에서 서버 주소를 먼저 넣어야 한다.",
                        style = MaterialTheme.typography.bodySmall,
                        color = MaterialTheme.colorScheme.error,
                    )
                }
            }
        }

        state.plan?.let { plan ->
            item { PlanResultCard(plan) }
            item { SourcesCard(plan) }
        }

        item { Spacer(Modifier.height(24.dp)) }
    }
}

@Composable
private fun PlanResultCard(plan: PlanResponse) {
    SectionCard("결과") {
        KeyValue("살 수 있는 최대 가격", formatKrw(plan.maxAffordablePriceKrw), emphasize = true)
        HorizontalDivider(Modifier.padding(vertical = 8.dp))

        KeyValue("대출 한도", formatKrw(plan.capacity.limitKrw), emphasize = true)
        Text(
            "${plan.capacity.bindingConstraint}에 막혔다 · " +
                "LTV ${formatKrw(plan.capacity.ltvLimitKrw)} / " +
                "DSR ${formatKrw(plan.capacity.dsrLimitKrw)}",
            style = MaterialTheme.typography.bodySmall,
            color = MaterialTheme.colorScheme.onSurfaceVariant,
        )
        KeyValue("월 납입액", formatKrw(plan.capacity.monthlyPaymentKrw))
        KeyValue(
            "스트레스 금리 적용",
            formatPercent(plan.capacity.stressRateApplied, 2),
        )

        HorizontalDivider(Modifier.padding(vertical = 8.dp))
        KeyValue(
            "취득 부대비용",
            "${formatKrw(plan.acquisitionCost.totalKrw)} (${formatPercent(plan.acquisitionCost.effectiveRate, 2)})",
        )
        KeyValue("필요 현금", formatKrw(plan.cashNeededKrw), emphasize = true)
        if (plan.cashShortfallKrw > 0) {
            Text(
                "현금 ${formatKrw(plan.cashShortfallKrw)} 부족",
                style = MaterialTheme.typography.bodyMedium,
                color = MaterialTheme.colorScheme.error,
                fontWeight = FontWeight.Bold,
            )
        }

        HorizontalDivider(Modifier.padding(vertical = 8.dp))
        KeyValue("보유 중 연 현금흐름", formatKrw(plan.holding.annualNetKrw))
        if (plan.holding.annualRentSavedKrw == 0L) {
            Text(
                "안 내게 되는 월세를 0으로 두고 계산했다. 실거주라면 그 값을 넣어야 " +
                    "결과가 한쪽으로 기울지 않는다.",
                style = MaterialTheme.typography.bodySmall,
                color = WarningAmber,
            )
        }

        if (plan.scenarios.isNotEmpty()) {
            HorizontalDivider(Modifier.padding(vertical = 8.dp))
            Text("매도 시나리오", style = MaterialTheme.typography.titleSmall)
            Text(
                "아래 가격은 전부 가정이다. 그 값에 팔린다는 뜻이 아니다.",
                style = MaterialTheme.typography.bodySmall,
                color = MaterialTheme.colorScheme.onSurfaceVariant,
            )
            Spacer(Modifier.height(4.dp))
            plan.scenarios.forEach { scenario ->
                Row(
                    Modifier.fillMaxWidth().padding(vertical = 4.dp),
                    horizontalArrangement = Arrangement.SpaceBetween,
                ) {
                    Column(Modifier.weight(1f)) {
                        Text(
                            "${scenario.label} · ${formatKrw(scenario.sellPriceKrw)}",
                            style = MaterialTheme.typography.bodyMedium,
                        )
                        Text(
                            "양도세 ${formatKrw(scenario.capitalGainsTaxKrw)} · " +
                                "순손익 ${formatKrw(scenario.netProfitKrw)}",
                            style = MaterialTheme.typography.bodySmall,
                            color = MaterialTheme.colorScheme.onSurfaceVariant,
                        )
                    }
                    Column(horizontalAlignment = Alignment.End) {
                        Text(
                            formatSignedPercent(scenario.roi),
                            style = MaterialTheme.typography.titleMedium,
                            color = if (scenario.roi >= 0) VerifiedGreen else MaterialTheme.colorScheme.error,
                        )
                        Text(
                            "연 ${formatSignedPercent(scenario.annualizedRoi)}",
                            style = MaterialTheme.typography.bodySmall,
                            color = MaterialTheme.colorScheme.onSurfaceVariant,
                        )
                    }
                }
            }
            Text(
                "ROI는 넣은 현금 대비다. 대출을 많이 낄수록 같은 가격 변동에도 " +
                    "퍼센트가 크게 튄다. 손실 쪽도 똑같이 증폭된다.",
                style = MaterialTheme.typography.bodySmall,
                color = MaterialTheme.colorScheme.onSurfaceVariant,
            )
        }

        if (plan.disclaimer.isNotBlank()) {
            Spacer(Modifier.height(8.dp))
            Text(
                plan.disclaimer,
                style = MaterialTheme.typography.bodySmall,
                color = MaterialTheme.colorScheme.onSurfaceVariant,
            )
        }
    }
}

/** 이 계산이 어떤 근거로 나왔는지. 검증 안 된 값이 있으면 숨기지 않는다. */
@Composable
private fun SourcesCard(plan: PlanResponse) {
    var expanded by remember { mutableStateOf(false) }
    val sources = plan.sources

    SectionCard("계산 근거") {
        Text(sources.summary, style = MaterialTheme.typography.bodyMedium)
        Text(
            "규제 기준일 ${plan.rulesetVersion}",
            style = MaterialTheme.typography.bodySmall,
            color = MaterialTheme.colorScheme.onSurfaceVariant,
        )

        if (sources.unverifiedCount > 0) {
            Spacer(Modifier.height(8.dp))
            Text(
                "이번 계산에 쓰인 ${sources.used.size}개 값 중 ${sources.unverifiedCount}개가 미검증이다.",
                style = MaterialTheme.typography.bodyMedium,
                color = WarningAmber,
                fontWeight = FontWeight.Bold,
            )
        }

        Spacer(Modifier.height(8.dp))
        Button(onClick = { expanded = !expanded }, modifier = Modifier.fillMaxWidth()) {
            Text(if (expanded) "출처 접기" else "파라미터별 출처 보기")
        }

        if (expanded) {
            Spacer(Modifier.height(8.dp))
            sources.used.forEach { CitationRow(it) }
        }
    }
}

@Composable
private fun CitationRow(citation: Citation) {
    Column(Modifier.fillMaxWidth().padding(vertical = 6.dp)) {
        Row(verticalAlignment = Alignment.CenterVertically) {
            Text(
                if (citation.isVerified) "확인됨" else "미확인",
                style = MaterialTheme.typography.labelSmall,
                color = if (citation.isVerified) VerifiedGreen else WarningAmber,
                fontWeight = FontWeight.Bold,
            )
            Text(
                "  ${citation.label}",
                style = MaterialTheme.typography.bodyMedium,
            )
        }
        if (citation.isVerified) {
            Text(
                "${citation.authority} · ${citation.document}" +
                    if (citation.effectiveDate.isNotBlank()) " (시행 ${citation.effectiveDate})" else "",
                style = MaterialTheme.typography.bodySmall,
                color = MaterialTheme.colorScheme.onSurfaceVariant,
            )
            if (citation.url.isNotBlank()) {
                Text(
                    citation.url,
                    style = MaterialTheme.typography.bodySmall,
                    color = MaterialTheme.colorScheme.primary,
                )
            }
        } else {
            Text(
                citation.warning,
                style = MaterialTheme.typography.bodySmall,
                color = WarningAmber,
            )
        }
    }
}

// ------------------------------------------------------------- 공통 조각

@Composable
fun SectionCard(title: String, content: @Composable ColumnScope.() -> Unit) {
    Card(
        modifier = Modifier.fillMaxWidth(),
        colors = CardDefaults.cardColors(
            containerColor = MaterialTheme.colorScheme.surface,
        ),
    ) {
        Column(Modifier.padding(16.dp)) {
            Text(title, style = MaterialTheme.typography.titleMedium)
            Spacer(Modifier.height(8.dp))
            content()
        }
    }
}

@Composable
private fun MoneyField(
    label: String,
    value: Long,
    hint: String? = null,
    onChange: (Long) -> Unit,
) {
    // remember(value) 로 키를 걸면 onChange -> 재구성 순환에서 입력이 되돌아간다.
    var text by remember { mutableStateOf(if (value == 0L) "" else (value / 10_000).toString()) }
    OutlinedTextField(
        value = text,
        onValueChange = {
            text = it.filter(Char::isDigit)
            onChange(parseManwonInput(text))
        },
        label = { Text("$label (만원)") },
        supportingText = hint?.let { { Text(it) } },
        singleLine = true,
        keyboardOptions = KeyboardOptions(keyboardType = KeyboardType.Number),
        modifier = Modifier.fillMaxWidth().padding(vertical = 4.dp),
    )
}

@Composable
private fun MoneyFieldText(label: String, value: String, onChange: (String) -> Unit) {
    OutlinedTextField(
        value = value,
        onValueChange = { onChange(it.filter(Char::isDigit)) },
        label = { Text("$label (만원)") },
        singleLine = true,
        keyboardOptions = KeyboardOptions(keyboardType = KeyboardType.Number),
        modifier = Modifier.fillMaxWidth().padding(vertical = 4.dp),
    )
}

@Composable
private fun NumberField(
    label: String,
    value: String,
    modifier: Modifier = Modifier,
    onChange: (String) -> Unit,
) {
    OutlinedTextField(
        value = value,
        onValueChange = onChange,
        label = { Text(label) },
        singleLine = true,
        keyboardOptions = KeyboardOptions(keyboardType = KeyboardType.Decimal),
        modifier = modifier.fillMaxWidth().padding(vertical = 4.dp),
    )
}

@Composable
private fun ToggleRow(label: String, checked: Boolean, onChange: (Boolean) -> Unit) {
    Row(
        Modifier.fillMaxWidth().padding(vertical = 4.dp),
        horizontalArrangement = Arrangement.SpaceBetween,
        verticalAlignment = Alignment.CenterVertically,
    ) {
        Text(label, style = MaterialTheme.typography.bodyLarge)
        Switch(checked = checked, onCheckedChange = onChange)
    }
}

@Composable
fun KeyValue(label: String, value: String, emphasize: Boolean = false) {
    Row(
        Modifier.fillMaxWidth().padding(vertical = 3.dp),
        horizontalArrangement = Arrangement.SpaceBetween,
    ) {
        Text(label, style = MaterialTheme.typography.bodyMedium)
        Text(
            value,
            style = if (emphasize) MaterialTheme.typography.titleMedium
            else MaterialTheme.typography.bodyMedium,
            fontWeight = if (emphasize) FontWeight.Bold else FontWeight.Normal,
        )
    }
}
