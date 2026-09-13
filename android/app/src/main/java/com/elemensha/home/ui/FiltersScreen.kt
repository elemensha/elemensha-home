package com.elemensha.home.ui

import androidx.compose.foundation.layout.Arrangement
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.FlowRow
import androidx.compose.foundation.layout.ExperimentalLayoutApi
import androidx.compose.foundation.layout.Row
import androidx.compose.foundation.layout.Spacer
import androidx.compose.foundation.layout.fillMaxWidth
import androidx.compose.foundation.layout.height
import androidx.compose.foundation.layout.padding
import androidx.compose.foundation.lazy.LazyColumn
import androidx.compose.foundation.lazy.items
import androidx.compose.foundation.text.KeyboardOptions
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
import androidx.compose.ui.text.input.KeyboardType
import androidx.compose.ui.unit.dp
import com.elemensha.home.UiState
import com.elemensha.home.data.FilterProfile

private val SOURCES = listOf(
    "onbid" to "공매",
    "court" to "법원경매",
    "rtms" to "실거래 급매",
    "applyhome" to "청약",
)

// 서버가 분류하는 값과 문자열이 정확히 같아야 필터가 걸린다.
// 토지가 빠져 있어서 수집은 되는데 고를 수가 없었다.
private val TYPES = listOf(
    "아파트", "오피스텔", "연립다세대", "단독주택", "토지", "상가", "기타",
)

private const val SQM_PER_PYEONG = 3.305785

/** 원 -> 만원 입력값. 0 이나 기본 상한은 비워 둔다(안 고른 값이므로). */
private fun manwonText(krw: Long): String =
    if (krw <= 0 || krw >= 2_000_000_000) "" else (krw / 10_000).toString()

/** ㎡ -> 평 입력값. 없거나 0 이면 비운다. */
private fun pyeongText(sqm: Double?): String =
    if (sqm == null || sqm <= 0) "" else Math.round(sqm / SQM_PER_PYEONG).toString()

/** 평 입력을 ㎡ 로. 비었으면 null 이라 호출부가 기본값을 정한다. */
private fun pyeongToSqm(text: String): Double? =
    text.trim().toDoubleOrNull()?.takeIf { it > 0 }?.times(SQM_PER_PYEONG)

@OptIn(ExperimentalLayoutApi::class)
@Composable
fun FiltersScreen(
    state: UiState,
    onSave: (FilterProfile) -> Unit,
    onDelete: (Int) -> Unit,
) {
    // 지역을 비워 두면 전국이 된다.
    var draft by remember { mutableStateOf(FilterProfile(sido = emptyList())) }
    var minText by remember { mutableStateOf("") }
    var maxText by remember { mutableStateOf("50000") }
    // 면적은 평으로 받는다. ㎡ 로 물어보면 머릿속에서 한 번 더 나눠야 한다.
    var minPyeong by remember { mutableStateOf("") }
    var maxPyeong by remember { mutableStateOf("") }

    LazyColumn(
        modifier = Modifier.fillMaxWidth().padding(horizontal = Dim.ScreenPad),
        verticalArrangement = Arrangement.spacedBy(Dim.Gap),
    ) {
        item { Spacer(Modifier.height(6.dp)) }

        item {
            ScreenBand(
                eyebrow = "ELEMENSHA HOME",
                title = "내 조건",
                sub = "여기서 만든 조건이 물건 탭의 칩과 알림 기준이 된다",
            )
        }

        item {
            SectionCard(if (draft.id != null) "조건 수정" else "새 조건") {
                OutlinedTextField(
                    value = draft.name,
                    onValueChange = { draft = draft.copy(name = it) },
                    label = { Text("이름") },
                    singleLine = true,
                    modifier = Modifier.fillMaxWidth(),
                )

                Spacer(Modifier.height(12.dp))
                SectionLabel("소스")
                FlowRow(
                    horizontalArrangement = Arrangement.spacedBy(Dim.GapTight),
                    verticalArrangement = Arrangement.spacedBy(Dim.GapTight),
                ) {
                    SOURCES.forEach { (value, label) ->
                        SelectChip(
                            selected = value in draft.sources,
                            label = label,
                            onClick = {
                                draft = draft.copy(
                                    sources = draft.sources.toggle(value)
                                )
                            },
                        )
                    }
                }

                Spacer(Modifier.height(12.dp))
                SectionLabel("지역")
                Text(
                    if (draft.sido.isEmpty()) "선택 안 하면 전국" else "선택한 지역만",
                    style = MaterialTheme.typography.bodySmall,
                    color = MaterialTheme.colorScheme.onSurfaceVariant,
                )
                // 시도 목록은 서버가 실제로 수집한 것에서 온다. 하드코딩하면
                // '전남광주통합특별시' 같은 개편 이름을 놓친다.
                FlowRow(
                    horizontalArrangement = Arrangement.spacedBy(Dim.GapTight),
                    verticalArrangement = Arrangement.spacedBy(Dim.GapTight),
                ) {
                    state.regions.forEach { region ->
                        SelectChip(
                            selected = region.sido in draft.sido,
                            label = region.sido
                                .removeSuffix("특별자치도")
                                .removeSuffix("특별자치시")
                                .removeSuffix("특별시")
                                .removeSuffix("광역시") + " ${region.count}",
                            onClick = {
                                draft = draft.copy(sido = draft.sido.toggle(region.sido))
                            },
                        )
                    }
                }

                Spacer(Modifier.height(12.dp))
                SectionLabel("물건 종류")
                FlowRow(
                    horizontalArrangement = Arrangement.spacedBy(Dim.GapTight),
                    verticalArrangement = Arrangement.spacedBy(Dim.GapTight),
                ) {
                    TYPES.forEach { value ->
                        SelectChip(
                            selected = value in draft.propertyTypes,
                            label = value,
                            onClick = {
                                draft = draft.copy(
                                    propertyTypes = draft.propertyTypes.toggle(value)
                                )
                            },
                        )
                    }
                }

                // 토지를 고른 경우에만 지목을 보여준다. 다른 종류에는 없는 개념이다.
                if ("토지" in draft.propertyTypes && state.landCategories.isNotEmpty()) {
                    Spacer(Modifier.height(12.dp))
                    SectionLabel("토지 지목")
                    Text(
                        if (draft.landCategories.isEmpty()) "선택 안 하면 전부"
                        else "선택한 지목만",
                        style = MaterialTheme.typography.bodySmall,
                        color = MaterialTheme.colorScheme.onSurfaceVariant,
                    )
                    FlowRow(
                    horizontalArrangement = Arrangement.spacedBy(Dim.GapTight),
                    verticalArrangement = Arrangement.spacedBy(Dim.GapTight),
                ) {
                        state.landCategories.forEach { cat ->
                            SelectChip(
                                selected = cat.category in draft.landCategories,
                                label = "${cat.category} ${cat.count}",
                                onClick = {
                                    draft = draft.copy(
                                        landCategories =
                                            draft.landCategories.toggle(cat.category)
                                    )
                                },
                            )
                        }
                    }

                    Spacer(Modifier.height(8.dp))
                    Row(
                        Modifier.fillMaxWidth(),
                        horizontalArrangement = Arrangement.SpaceBetween,
                        verticalAlignment = Alignment.CenterVertically,
                    ) {
                        Column(Modifier.weight(1f)) {
                            Text("농지 제외", style = MaterialTheme.typography.bodyLarge)
                            Text(
                                "전·답·과수원. 낙찰 후 농지취득자격증명을 못 받으면 " +
                                    "보증금을 잃는다.",
                                style = MaterialTheme.typography.bodySmall,
                                color = MaterialTheme.colorScheme.onSurfaceVariant,
                            )
                        }
                        Switch(
                            checked = draft.excludeFarmland,
                            onCheckedChange = {
                                draft = draft.copy(excludeFarmland = it)
                            },
                        )
                    }
                }

                // 지분은 종류를 가리지 않고 나온다. 토지 조건 밖에 둔다.
                Spacer(Modifier.height(8.dp))
                Row(
                    Modifier.fillMaxWidth(),
                    horizontalArrangement = Arrangement.SpaceBetween,
                    verticalAlignment = Alignment.CenterVertically,
                ) {
                    Column(Modifier.weight(1f)) {
                        Text("지분 매각 제외", style = MaterialTheme.typography.bodyLarge)
                        Text(
                            "여러 명이 나눠 가진 것 중 한 사람 몫만 파는 물건이다. "
                            + "낙찰받아도 혼자 쓸 수 없고 공유물분할 소송이 따라온다.",
                            style = MaterialTheme.typography.bodySmall,
                            color = MaterialTheme.colorScheme.onSurfaceVariant,
                        )
                    }
                    Switch(
                        checked = draft.excludeShareSale,
                        onCheckedChange = { draft = draft.copy(excludeShareSale = it) },
                    )
                }

                Spacer(Modifier.height(12.dp))
                Row(horizontalArrangement = Arrangement.spacedBy(8.dp)) {
                    OutlinedTextField(
                        value = minText,
                        onValueChange = { minText = it.filter(Char::isDigit) },
                        label = { Text("최저가 (만원)") },
                        singleLine = true,
                        keyboardOptions = KeyboardOptions(keyboardType = KeyboardType.Number),
                        modifier = Modifier.weight(1f),
                    )
                    OutlinedTextField(
                        value = maxText,
                        onValueChange = { maxText = it.filter(Char::isDigit) },
                        label = { Text("최고가 (만원)") },
                        singleLine = true,
                        keyboardOptions = KeyboardOptions(keyboardType = KeyboardType.Number),
                        modifier = Modifier.weight(1f),
                    )
                }

                Spacer(Modifier.height(12.dp))
                Row(horizontalArrangement = Arrangement.spacedBy(8.dp)) {
                    OutlinedTextField(
                        value = minPyeong,
                        onValueChange = { minPyeong = it.filter(Char::isDigit) },
                        label = { Text("최소 면적 (평)") },
                        singleLine = true,
                        keyboardOptions = KeyboardOptions(keyboardType = KeyboardType.Number),
                        modifier = Modifier.weight(1f),
                    )
                    OutlinedTextField(
                        value = maxPyeong,
                        onValueChange = { maxPyeong = it.filter(Char::isDigit) },
                        label = { Text("최대 면적 (평)") },
                        singleLine = true,
                        keyboardOptions = KeyboardOptions(keyboardType = KeyboardType.Number),
                        modifier = Modifier.weight(1f),
                    )
                }
                Text(
                    "비워 두면 면적을 따지지 않는다. 1평 = 3.3㎡ 로 환산해 저장한다.",
                    style = MaterialTheme.typography.bodySmall,
                    color = MaterialTheme.colorScheme.onSurfaceVariant,
                )

                Spacer(Modifier.height(12.dp))
                Row(horizontalArrangement = Arrangement.spacedBy(8.dp)) {
                PrimaryAction(
                    text = if (draft.id != null) "수정 저장" else "조건 추가",
                    onClick = {
                        onSave(
                            draft.copy(
                                minPriceKrw = parseManwonInput(minText),
                                maxPriceKrw = parseManwonInput(maxText)
                                    .takeIf { it > 0 } ?: 2_000_000_000,
                                minAreaSqm = pyeongToSqm(minPyeong) ?: 0.0,
                                // 비우면 null - 상한 없음이다.
                                maxAreaSqm = pyeongToSqm(maxPyeong),
                            )
                        )
                        draft = FilterProfile(sido = emptyList())
                        minText = ""
                        maxText = "50000"
                        minPyeong = ""
                        maxPyeong = ""
                    },
                    enabled = !state.loading && state.isConfigured,
                    modifier = Modifier.weight(1f),
                )

                    // 수정 중일 때만. 잘못 눌러 들어왔을 때 빠져나갈 길이 필요하다.
                    if (draft.id != null) {
                        GhostAction(
                            text = "취소",
                            onClick = {
                                draft = FilterProfile(sido = emptyList())
                                minText = ""
                                maxText = "50000"
                                minPyeong = ""
                                maxPyeong = ""
                            },
                        )
                    }
                }
            }
        }

        if (state.filters.isNotEmpty()) {
            item {
                SectionLabel("저장된 조건")
            }
        }

        items(state.filters, key = { it.id ?: it.name.hashCode() }) { filter ->
            HomeCard {
                    Row(
                        Modifier.fillMaxWidth(),
                        horizontalArrangement = Arrangement.SpaceBetween,
                        verticalAlignment = Alignment.CenterVertically,
                    ) {
                        Text(filter.name, style = MaterialTheme.typography.titleSmall)
                        Row(horizontalArrangement = Arrangement.spacedBy(6.dp)) {
                            // 지금까지는 고치려면 지우고 새로 만들어야 했다.
                            // 조건 번호가 계속 올라간 이유가 그것이다.
                            GhostAction("수정", small = true, onClick = {
                                draft = filter
                                minText = manwonText(filter.minPriceKrw)
                                maxText = manwonText(filter.maxPriceKrw)
                                minPyeong = pyeongText(filter.minAreaSqm)
                                maxPyeong = pyeongText(filter.maxAreaSqm)
                            })
                            filter.id?.let { id ->
                                GhostAction("삭제", small = true, onClick = { onDelete(id) })
                            }
                        }
                    }
                    Text(
                        "${filter.sido.joinToString(", ")} · " +
                            "${formatKrw(filter.minPriceKrw)} ~ ${formatKrw(filter.maxPriceKrw)}",
                        style = MaterialTheme.typography.bodySmall,
                        color = MaterialTheme.colorScheme.onSurfaceVariant,
                    )
                    if (filter.landCategories.isNotEmpty() || filter.excludeFarmland) {
                        Text(
                            listOfNotNull(
                                filter.landCategories.takeIf { it.isNotEmpty() }
                                    ?.joinToString("/"),
                                if (filter.excludeFarmland) "농지 제외" else null,
                            ).joinToString(" · "),
                            style = MaterialTheme.typography.bodySmall,
                            color = WarningAmber,
                        )
                    }
                    Text(
                        "${filter.sources.joinToString(", ")} · " +
                            filter.propertyTypes.joinToString(", "),
                        style = MaterialTheme.typography.bodySmall,
                        color = MaterialTheme.colorScheme.onSurfaceVariant,
                    )
            }
        }

        item { Spacer(Modifier.height(24.dp)) }
    }
}

/** 칩 토글. 이미 있으면 빼고 없으면 넣는다. */
private fun List<String>.toggle(value: String): List<String> =
    if (value in this) this - value else this + value
