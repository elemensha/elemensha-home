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
import androidx.compose.material3.Button
import androidx.compose.material3.Card
import androidx.compose.material3.FilterChip
import androidx.compose.material3.MaterialTheme
import androidx.compose.material3.OutlinedButton
import androidx.compose.material3.OutlinedTextField
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

private val TYPES = listOf("아파트", "오피스텔", "연립다세대", "단독주택")
private val SIDOS = listOf("서울특별시", "경기도", "인천광역시")

@OptIn(ExperimentalLayoutApi::class)
@Composable
fun FiltersScreen(
    state: UiState,
    onSave: (FilterProfile) -> Unit,
    onDelete: (Int) -> Unit,
) {
    var draft by remember { mutableStateOf(FilterProfile()) }
    var minText by remember { mutableStateOf("") }
    var maxText by remember { mutableStateOf("50000") }

    LazyColumn(
        modifier = Modifier.fillMaxWidth().padding(horizontal = 16.dp),
        verticalArrangement = Arrangement.spacedBy(12.dp),
    ) {
        item { Spacer(Modifier.height(8.dp)) }

        item {
            SectionCard("새 조건") {
                OutlinedTextField(
                    value = draft.name,
                    onValueChange = { draft = draft.copy(name = it) },
                    label = { Text("이름") },
                    singleLine = true,
                    modifier = Modifier.fillMaxWidth(),
                )

                Spacer(Modifier.height(12.dp))
                Text("소스", style = MaterialTheme.typography.labelLarge)
                FlowRow(horizontalArrangement = Arrangement.spacedBy(6.dp)) {
                    SOURCES.forEach { (value, label) ->
                        FilterChip(
                            selected = value in draft.sources,
                            onClick = {
                                draft = draft.copy(
                                    sources = draft.sources.toggle(value)
                                )
                            },
                            label = { Text(label) },
                        )
                    }
                }

                Spacer(Modifier.height(12.dp))
                Text("지역", style = MaterialTheme.typography.labelLarge)
                FlowRow(horizontalArrangement = Arrangement.spacedBy(6.dp)) {
                    SIDOS.forEach { value ->
                        FilterChip(
                            selected = value in draft.sido,
                            onClick = { draft = draft.copy(sido = draft.sido.toggle(value)) },
                            label = { Text(value.removeSuffix("특별시").removeSuffix("광역시")) },
                        )
                    }
                }

                Spacer(Modifier.height(12.dp))
                Text("물건 종류", style = MaterialTheme.typography.labelLarge)
                FlowRow(horizontalArrangement = Arrangement.spacedBy(6.dp)) {
                    TYPES.forEach { value ->
                        FilterChip(
                            selected = value in draft.propertyTypes,
                            onClick = {
                                draft = draft.copy(
                                    propertyTypes = draft.propertyTypes.toggle(value)
                                )
                            },
                            label = { Text(value) },
                        )
                    }
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
                Button(
                    onClick = {
                        onSave(
                            draft.copy(
                                minPriceKrw = parseManwonInput(minText),
                                maxPriceKrw = parseManwonInput(maxText)
                                    .takeIf { it > 0 } ?: 2_000_000_000,
                            )
                        )
                        draft = FilterProfile()
                    },
                    enabled = !state.loading && state.isConfigured,
                    modifier = Modifier.fillMaxWidth(),
                ) { Text("조건 추가") }
            }
        }

        if (state.filters.isNotEmpty()) {
            item {
                Text("저장된 조건", style = MaterialTheme.typography.titleMedium)
            }
        }

        items(state.filters, key = { it.id ?: it.name.hashCode() }) { filter ->
            Card(Modifier.fillMaxWidth()) {
                Column(Modifier.padding(16.dp)) {
                    Row(
                        Modifier.fillMaxWidth(),
                        horizontalArrangement = Arrangement.SpaceBetween,
                        verticalAlignment = Alignment.CenterVertically,
                    ) {
                        Text(filter.name, style = MaterialTheme.typography.titleSmall)
                        filter.id?.let { id ->
                            OutlinedButton(onClick = { onDelete(id) }) { Text("삭제") }
                        }
                    }
                    Text(
                        "${filter.sido.joinToString(", ")} · " +
                            "${formatKrw(filter.minPriceKrw)} ~ ${formatKrw(filter.maxPriceKrw)}",
                        style = MaterialTheme.typography.bodySmall,
                        color = MaterialTheme.colorScheme.onSurfaceVariant,
                    )
                    Text(
                        "${filter.sources.joinToString(", ")} · " +
                            filter.propertyTypes.joinToString(", "),
                        style = MaterialTheme.typography.bodySmall,
                        color = MaterialTheme.colorScheme.onSurfaceVariant,
                    )
                }
            }
        }

        item { Spacer(Modifier.height(24.dp)) }
    }
}

/** 칩 토글. 이미 있으면 빼고 없으면 넣는다. */
private fun List<String>.toggle(value: String): List<String> =
    if (value in this) this - value else this + value
