package com.elemensha.home.ui

import androidx.compose.foundation.layout.Arrangement
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.ExperimentalLayoutApi
import androidx.compose.foundation.layout.FlowRow
import androidx.compose.foundation.layout.Row
import androidx.compose.foundation.layout.Spacer
import androidx.compose.foundation.layout.fillMaxWidth
import androidx.compose.foundation.layout.height
import androidx.compose.foundation.rememberScrollState
import androidx.compose.foundation.verticalScroll
import androidx.compose.material3.AlertDialog
import androidx.compose.material3.FilterChip
import androidx.compose.material3.MaterialTheme
import androidx.compose.material3.OutlinedTextField
import androidx.compose.material3.Text
import androidx.compose.material3.TextButton
import androidx.compose.runtime.Composable
import androidx.compose.runtime.getValue
import androidx.compose.runtime.mutableStateOf
import androidx.compose.runtime.remember
import androidx.compose.runtime.setValue
import androidx.compose.ui.Modifier
import androidx.compose.ui.text.input.KeyboardType
import androidx.compose.ui.unit.dp
import androidx.compose.foundation.text.KeyboardOptions
import com.elemensha.home.data.ManualCourtListing

private val TYPES = listOf("토지", "아파트", "오피스텔", "연립다세대", "단독주택", "상가", "기타")

/**
 * 법원경매 물건을 손으로 넣는 입력창.
 *
 * 법원경매정보 사이트는 공식 API 가 없고 자동 수집을 보안정책으로 막는다.
 * 그래서 목록은 그 사이트에서 직접 보고, 살 만한 물건만 여기에 옮겨 담는다.
 * 옮겨 담으면 공매 물건과 똑같이 자금계획·지도·면적 필터에 들어간다.
 */
@OptIn(ExperimentalLayoutApi::class)
@Composable
fun CourtEntryDialog(
    onDismiss: () -> Unit,
    onSave: (ManualCourtListing) -> Unit,
) {
    var caseNo by remember { mutableStateOf("") }
    var itemNo by remember { mutableStateOf("1") }
    var address by remember { mutableStateOf("") }
    var type by remember { mutableStateOf("토지") }
    var appraised by remember { mutableStateOf("") }
    var minBid by remember { mutableStateOf("") }
    var pyeong by remember { mutableStateOf("") }
    var failed by remember { mutableStateOf("") }
    var saleDate by remember { mutableStateOf("") }
    var court by remember { mutableStateOf("") }
    var category by remember { mutableStateOf("") }
    var note by remember { mutableStateOf("") }

    val scroll = rememberScrollState()

    AlertDialog(
        onDismissRequest = onDismiss,
        title = { Text("법원경매 물건 추가") },
        text = {
            Column(
                Modifier.verticalScroll(scroll),
                verticalArrangement = Arrangement.spacedBy(8.dp),
            ) {
                Text(
                    "법원경매정보 사이트에서 본 물건을 옮겨 적으면, 공매 물건과 " +
                        "똑같이 대출한도·취득세·ROI 계산과 지도에 들어갑니다.",
                    style = MaterialTheme.typography.bodySmall,
                    color = MaterialTheme.colorScheme.onSurfaceVariant,
                )

                Row(horizontalArrangement = Arrangement.spacedBy(8.dp)) {
                    OutlinedTextField(
                        value = caseNo,
                        onValueChange = { caseNo = it },
                        label = { Text("사건번호") },
                        placeholder = { Text("2026타경1234") },
                        singleLine = true,
                        modifier = Modifier.weight(2f),
                    )
                    OutlinedTextField(
                        value = itemNo,
                        onValueChange = { itemNo = it.filter(Char::isDigit) },
                        label = { Text("물건번호") },
                        singleLine = true,
                        keyboardOptions = KeyboardOptions(keyboardType = KeyboardType.Number),
                        modifier = Modifier.weight(1f),
                    )
                }

                OutlinedTextField(
                    value = address,
                    onValueChange = { address = it },
                    label = { Text("소재지") },
                    supportingText = { Text("지번까지 있어야 지도에 찍힙니다") },
                    modifier = Modifier.fillMaxWidth(),
                )

                Text("물건 종류", style = MaterialTheme.typography.labelLarge)
                FlowRow(horizontalArrangement = Arrangement.spacedBy(6.dp)) {
                    TYPES.forEach {
                        FilterChip(
                            selected = type == it,
                            onClick = { type = it },
                            label = { Text(it) },
                        )
                    }
                }

                if (type == "토지") {
                    OutlinedTextField(
                        value = category,
                        onValueChange = { category = it },
                        label = { Text("지목") },
                        placeholder = { Text("임야 / 대지 / 답 …") },
                        singleLine = true,
                        modifier = Modifier.fillMaxWidth(),
                    )
                }

                Row(horizontalArrangement = Arrangement.spacedBy(8.dp)) {
                    OutlinedTextField(
                        value = appraised,
                        onValueChange = { appraised = it.filter(Char::isDigit) },
                        label = { Text("감정가 (만원)") },
                        singleLine = true,
                        keyboardOptions = KeyboardOptions(keyboardType = KeyboardType.Number),
                        modifier = Modifier.weight(1f),
                    )
                    OutlinedTextField(
                        value = minBid,
                        onValueChange = { minBid = it.filter(Char::isDigit) },
                        label = { Text("최저가 (만원)") },
                        singleLine = true,
                        keyboardOptions = KeyboardOptions(keyboardType = KeyboardType.Number),
                        modifier = Modifier.weight(1f),
                    )
                }

                Row(horizontalArrangement = Arrangement.spacedBy(8.dp)) {
                    OutlinedTextField(
                        value = pyeong,
                        onValueChange = { pyeong = it.filter { c -> c.isDigit() || c == '.' } },
                        label = { Text("면적 (평)") },
                        singleLine = true,
                        keyboardOptions = KeyboardOptions(keyboardType = KeyboardType.Number),
                        modifier = Modifier.weight(1f),
                    )
                    OutlinedTextField(
                        value = failed,
                        onValueChange = { failed = it.filter(Char::isDigit) },
                        label = { Text("유찰 횟수") },
                        singleLine = true,
                        keyboardOptions = KeyboardOptions(keyboardType = KeyboardType.Number),
                        modifier = Modifier.weight(1f),
                    )
                }

                OutlinedTextField(
                    value = saleDate,
                    onValueChange = { saleDate = it },
                    label = { Text("매각기일") },
                    placeholder = { Text("2026-09-15") },
                    supportingText = { Text("이 날 법원에서 입찰합니다. 당일에 '입찰 가능'으로 뜹니다") },
                    singleLine = true,
                    modifier = Modifier.fillMaxWidth(),
                )

                OutlinedTextField(
                    value = court,
                    onValueChange = { court = it },
                    label = { Text("법원·담당계") },
                    placeholder = { Text("수원지방법원 여주지원 경매3계") },
                    singleLine = true,
                    modifier = Modifier.fillMaxWidth(),
                )

                OutlinedTextField(
                    value = note,
                    onValueChange = { note = it },
                    label = { Text("메모") },
                    placeholder = { Text("권리분석, 명도 여부 등") },
                    modifier = Modifier.fillMaxWidth(),
                )

                Spacer(Modifier.height(4.dp))
                Text(
                    "경매는 명도비·미납관리비·인수보증금이 따로 붙습니다. " +
                        "권리분석 결과는 직접 확인하세요.",
                    style = MaterialTheme.typography.bodySmall,
                    color = WarningAmber,
                )
            }
        },
        confirmButton = {
            TextButton(
                enabled = caseNo.isNotBlank(),
                onClick = {
                    onSave(
                        ManualCourtListing(
                            caseNo = caseNo.trim(),
                            itemNo = itemNo.ifBlank { "1" },
                            address = address.trim(),
                            propertyType = type,
                            appraisedPriceKrw = manwonToKrw(appraised),
                            minBidPriceKrw = manwonToKrw(minBid),
                            exclusiveAreaSqm = pyeong.toDoubleOrNull()
                                ?.takeIf { it > 0 }?.times(SQM_PER_PYEONG),
                            failedBidCount = failed.toIntOrNull() ?: 0,
                            saleDate = saleDate.trim(),
                            courtName = court.trim(),
                            landCategory = category.trim(),
                            note = note.trim(),
                        )
                    )
                },
            ) { Text("추가") }
        },
        dismissButton = { TextButton(onClick = onDismiss) { Text("취소") } },
    )
}

private const val SQM_PER_PYEONG = 3.305785

private fun manwonToKrw(text: String): Long? =
    text.trim().toLongOrNull()?.takeIf { it > 0 }?.times(10_000)
