package com.elemensha.home.ui

import android.content.Intent
import androidx.compose.foundation.clickable
import androidx.compose.foundation.layout.Arrangement
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.Row
import androidx.compose.foundation.layout.Spacer
import androidx.compose.foundation.layout.fillMaxWidth
import androidx.compose.foundation.layout.height
import androidx.compose.foundation.layout.padding
import androidx.compose.foundation.lazy.LazyColumn
import androidx.compose.foundation.lazy.items
import androidx.compose.foundation.layout.ExperimentalLayoutApi
import androidx.compose.foundation.layout.FlowRow
import androidx.compose.material3.AssistChip
import androidx.compose.material3.AssistChipDefaults
import androidx.compose.material3.FilterChip
import androidx.compose.material3.Button
import androidx.compose.material3.Card
import androidx.compose.material3.CardDefaults
import androidx.compose.material3.MaterialTheme
import androidx.compose.material3.OutlinedButton
import androidx.compose.material3.Text
import androidx.compose.runtime.Composable
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.platform.LocalClipboardManager
import androidx.compose.ui.platform.LocalContext
import androidx.compose.ui.text.AnnotatedString
import androidx.compose.ui.text.font.FontWeight
import androidx.compose.ui.unit.dp
import androidx.core.net.toUri
import androidx.compose.runtime.getValue
import androidx.compose.runtime.mutableStateOf
import androidx.compose.runtime.remember
import androidx.compose.runtime.setValue
import com.elemensha.home.UiState
import com.elemensha.home.data.Listing
import com.elemensha.home.data.ManualCourtListing
import com.elemensha.home.data.ListingDetail
import androidx.compose.material3.CircularProgressIndicator
import androidx.compose.material3.HorizontalDivider

/**
 * 물건 목록.
 *
 * 목록이 비었을 때 **왜 비었는지**를 반드시 알려준다. 서버가 안 붙었는지,
 * 서비스키가 없는지, 조건에 맞는 물건이 정말 없는지는 전혀 다른 상황인데
 * 화면상으로는 똑같이 "빈 목록"이라 구분이 안 된다.
 */
@OptIn(ExperimentalLayoutApi::class)
@Composable
fun ListingsScreen(
    state: UiState,
    onRefresh: () -> Unit,
    onPlanForListing: (Listing) -> Unit,
    onSelectFilter: (Int?) -> Unit,
    onShowAll: () -> Unit,
    onSort: (String) -> Unit,
    onOpenDetail: (Listing) -> Unit,
    onToggleBiddable: (Boolean) -> Unit,
    onAddCourtListing: (ManualCourtListing) -> Unit,
) {
    val context = LocalContext.current
    var showCourtEntry by remember { mutableStateOf(false) }

    if (showCourtEntry) {
        CourtEntryDialog(
            onDismiss = { showCourtEntry = false },
            onSave = { showCourtEntry = false; onAddCourtListing(it) },
        )
    }

    LazyColumn(
        modifier = Modifier.fillMaxWidth().padding(horizontal = 16.dp),
        verticalArrangement = Arrangement.spacedBy(10.dp),
    ) {
        item { Spacer(Modifier.height(8.dp)) }

        item {
            Row(
                Modifier.fillMaxWidth(),
                horizontalArrangement = Arrangement.SpaceBetween,
                verticalAlignment = Alignment.CenterVertically,
            ) {
                Column {
                    Text(
                        if (state.totalMatched > state.listings.size)
                            "물건 ${state.listings.size} / ${state.totalMatched}건"
                        else "물건 ${state.totalMatched}건",
                        style = MaterialTheme.typography.titleMedium,
                    )
                    Text(
                        (if (state.applyFilters) "조건 적용됨" else "조건 없이 전체") +
                            " · 마감된 물건 숨김",
                        style = MaterialTheme.typography.bodySmall,
                        color = MaterialTheme.colorScheme.onSurfaceVariant,
                    )
                }
                Row(horizontalArrangement = Arrangement.spacedBy(6.dp)) {
                    // 법원경매는 자동 수집이 막혀 있어 손으로 넣는다.
                    OutlinedButton(
                        onClick = { showCourtEntry = true },
                        enabled = state.isConfigured,
                    ) { Text("＋ 경매") }
                    OutlinedButton(onClick = onRefresh, enabled = !state.loading) {
                        Text("새로고침")
                    }
                }
            }
        }

        // 조건 선택. 조건 탭에서 만든 것이 여기 칩으로 뜬다.
        item {
            FlowRow(horizontalArrangement = Arrangement.spacedBy(6.dp)) {
                FilterChip(
                    selected = !state.applyFilters,
                    onClick = onShowAll,
                    label = { Text("전체") },
                )
                FilterChip(
                    selected = state.biddableOnly,
                    onClick = { onToggleBiddable(!state.biddableOnly) },
                    label = { Text("지금 입찰 가능") },
                )
                FilterChip(
                    selected = state.applyFilters && state.selectedFilterId == null,
                    onClick = { onSelectFilter(null) },
                    label = { Text("내 조건 전부") },
                    enabled = state.filters.isNotEmpty(),
                )
                state.filters.forEach { filter ->
                    FilterChip(
                        selected = state.selectedFilterId == filter.id,
                        onClick = { filter.id?.let(onSelectFilter) },
                        label = { Text(filter.name) },
                    )
                }
            }
        }

        item {
            FlowRow(horizontalArrangement = Arrangement.spacedBy(6.dp)) {
                listOf(
                    "recent" to "최신순",
                    "discount" to "할인폭순",
                    "price" to "가격순",
                    "deadline" to "마감임박순",
                ).forEach { (key, label) ->
                    FilterChip(
                        selected = state.sort == key,
                        onClick = { onSort(key) },
                        label = { Text(label) },
                    )
                }
            }
        }

        if (state.listings.isEmpty()) {
            item { EmptyExplanation(state) }
        }

        items(state.listings, key = { it.source + it.sourceId }) { listing ->
            ListingCard(
                listing = listing,
                onOpen = {
                    if (listing.url.isNotBlank()) {
                        // 온비드 링크는 온비드 앱으로 먼저 넘긴다.
                        openExternalLink(context, listing.url)
                    }
                },
                onPlan = { onPlanForListing(listing) },
                onDetail = { onOpenDetail(listing) },
                detail = if (state.detailKey ==
                    (listing.dedupeKey ?: (listing.source + ":" + listing.sourceId))
                ) state.detail else null,
                detailLoading = state.detailLoading && state.detailKey ==
                    (listing.dedupeKey ?: (listing.source + ":" + listing.sourceId)),
            )
        }

        item { Spacer(Modifier.height(24.dp)) }
    }
}

@Composable
private fun EmptyExplanation(state: UiState) {
    val health = state.health
    Card(Modifier.fillMaxWidth()) {
        Column(Modifier.padding(16.dp)) {
            Text("물건이 없다", style = MaterialTheme.typography.titleMedium)
            Spacer(Modifier.height(8.dp))

            val reason = when {
                !state.isConfigured -> "설정 탭에서 서버 주소를 먼저 넣어야 한다."
                health == null -> "서버에 아직 연결되지 않았다. 주소와 토큰을 확인할 것."
                health.sourcesConfigured.none { it.value } ->
                    "서버에 데이터 소스 키가 하나도 설정되지 않았다. " +
                        "data.go.kr에서 서비스키를 발급받아 서버 .env에 넣어야 한다."
                health.pollStatus.isEmpty() ->
                    "아직 한 번도 수집하지 않았다. 설정 탭의 '지금 수집'을 눌러볼 것."
                health.pollStatus.any { !it.ok } ->
                    "수집이 실패하고 있다: " +
                        health.pollStatus.filter { !it.ok }
                            .joinToString(", ") { "${it.source} - ${it.error ?: "원인 미상"}" }
                state.applyFilters && state.filters.isNotEmpty() ->
                    "수집된 물건은 있는데 조건에 걸리는 게 없다. 위의 '전체' 칩을 눌러 " +
                        "조건 없이 보거나, 조건 탭에서 범위를 넓혀볼 것."
                else -> "수집은 정상인데 보여줄 물건이 없다."
            }
            Text(reason, style = MaterialTheme.typography.bodyMedium)

            if (health != null) {
                Spacer(Modifier.height(12.dp))
                Text("소스 상태", style = MaterialTheme.typography.labelLarge)
                health.sourcesConfigured.forEach { (name, configured) ->
                    val poll = health.pollStatus.firstOrNull { it.source == name }
                    val detail = when {
                        !configured -> "키 미설정"
                        poll == null -> "대기 중"
                        poll.ok -> "정상 · ${poll.fetched}건 수집"
                        else -> "실패 · ${poll.error ?: "원인 미상"}"
                    }
                    KeyValue(name, detail)
                }
            }
        }
    }
}

@Composable
private fun ListingCard(
    listing: Listing,
    onOpen: () -> Unit,
    onPlan: () -> Unit,
    onDetail: () -> Unit,
    detail: ListingDetail?,
    detailLoading: Boolean,
) {
    val context = LocalContext.current
    Card(
        modifier = Modifier.fillMaxWidth().clickable(onClick = onOpen),
        colors = CardDefaults.cardColors(
            containerColor = MaterialTheme.colorScheme.surface,
        ),
    ) {
        Column(Modifier.padding(16.dp)) {
            Row(
                Modifier.fillMaxWidth(),
                horizontalArrangement = Arrangement.spacedBy(6.dp),
            ) {
                AssistChip(onClick = {}, label = { Text(sourceLabel(listing.source)) })
                if (listing.source == "onbid") {
                    AssistChip(
                        onClick = {},
                        label = {
                            Text(
                                if (listing.isBiddable) "지금 입찰 가능"
                                else listing.bidStatus.ifBlank { "준비중" }
                            )
                        },
                        colors = AssistChipDefaults.assistChipColors(
                            labelColor = if (listing.isBiddable) VerifiedGreen
                            else MaterialTheme.colorScheme.onSurfaceVariant,
                        ),
                    )
                }
                if (listing.failedBidCount > 0) {
                    AssistChip(
                        onClick = {},
                        label = { Text("유찰 ${listing.failedBidCount}회") },
                    )
                }
            }

            Spacer(Modifier.height(8.dp))
            Text(listing.title, style = MaterialTheme.typography.titleMedium)
            Text(
                listing.address.ifBlank { "${listing.sido} ${listing.sigungu}" },
                style = MaterialTheme.typography.bodySmall,
                color = MaterialTheme.colorScheme.onSurfaceVariant,
            )

            Spacer(Modifier.height(8.dp))
            Text(
                formatKrw(listing.effectivePriceKrw),
                style = MaterialTheme.typography.headlineSmall,
                fontWeight = FontWeight.Bold,
            )

            if (listing.priceNote.isNotBlank()) {
                Text(
                    listing.priceNote,
                    style = MaterialTheme.typography.bodySmall,
                    color = WarningAmber,
                )
            }

            listing.appraisedPriceKrw?.let { appraised ->
                if (listing.minBidPriceKrw != null && listing.minBidPriceKrw < appraised) {
                    Text(
                        "감정가 ${formatKrw(appraised)} 대비 " +
                            formatPercent(listing.discountRatio, 0) + " 낮음",
                        style = MaterialTheme.typography.bodySmall,
                        color = VerifiedGreen,
                    )
                }
            }
            if (listing.source == "rtms") {
                Text(
                    "최근 실거래 중앙값 ${formatKrw(listing.marketPriceKrw)} 대비 " +
                        formatPercent(listing.discountRatio, 0) + " 낮게 신고됨",
                    style = MaterialTheme.typography.bodySmall,
                    color = WarningAmber,
                )
                Text(
                    "이미 체결된 거래다. 지금 살 수 있는 매물이 아니다.",
                    style = MaterialTheme.typography.bodySmall,
                    color = MaterialTheme.colorScheme.onSurfaceVariant,
                )
            }

            listing.exclusiveAreaSqm?.let {
                Text(formatArea(it), style = MaterialTheme.typography.bodySmall)
            }

            // 공매의 핵심 리스크. 인도명령이 없어 점유자가 있으면 협의가
            // 깨졌을 때 명도소송으로 가고 5~6개월이 걸린다. 토지는 그 대상이
            // 아예 없어서 성격이 완전히 다르다.
            if (listing.source == "onbid") {
                Spacer(Modifier.height(6.dp))
                if (listing.isLand) {
                    Text(
                        "명도 부담 없음 (토지)" +
                            if (listing.usageMinor.isNotBlank()) " · 지목 ${listing.usageMinor}" else "",
                        style = MaterialTheme.typography.bodySmall,
                        color = VerifiedGreen,
                    )
                    if (listing.needsFarmlandPermit) {
                        Text(
                            "농지취득자격증명 필요 — 못 받으면 보증금을 잃는다",
                            style = MaterialTheme.typography.bodySmall,
                            color = MaterialTheme.colorScheme.error,
                        )
                    }
                    Text(
                        "맹지 여부·용도지역은 이 앱이 판정하지 못한다. 지도에서 " +
                            "도로가 필지에 닿는지 직접 확인할 것.",
                        style = MaterialTheme.typography.bodySmall,
                        color = MaterialTheme.colorScheme.onSurfaceVariant,
                    )
                } else {
                    Text(
                        "명도는 매수자 부담 — 공매는 인도명령이 없어 협의가 안 되면 " +
                            "명도소송(5~6개월)으로 간다",
                        style = MaterialTheme.typography.bodySmall,
                        color = WarningAmber,
                    )
                }
            }

            if (listing.caution.isNotBlank()) {
                Text(
                    listing.caution,
                    style = MaterialTheme.typography.bodySmall,
                    color = WarningAmber,
                )
            }
            if (!listing.isBiddable && !listing.bidStart.isNullOrBlank()) {
                Text(
                    "입찰 시작 " + listing.bidStart.replace('T', ' ') + " (한국시간)",
                    style = MaterialTheme.typography.bodySmall,
                    color = MaterialTheme.colorScheme.onSurfaceVariant,
                )
            }
            listing.deadline?.let { dl ->
                val days = daysUntil(dl)
                Text(
                    "${formatDeadline(dl)} · ${dl.replace('T', ' ')} (한국시간)",
                    style = MaterialTheme.typography.bodySmall,
                    // 사흘 안쪽이면 눈에 띄게. 준비할 시간이 없다는 뜻이다.
                    color = if (days != null && days <= 3) MaterialTheme.colorScheme.error
                    else MaterialTheme.colorScheme.onSurfaceVariant,
                )
            }

            // 온비드는 개편 뒤 물건 하나를 바로 여는 주소가 없다. 번호를
            // 복사해 온비드에서 검색하는 것이 유일한 경로라 눌러서 복사되게 둔다.
            if (listing.managementNo.isNotBlank()) {
                val clipboard = LocalClipboardManager.current
                var copied by remember(listing.managementNo) { mutableStateOf(false) }
                Spacer(Modifier.height(6.dp))
                Text(
                    if (copied) "복사됨 · ${listing.managementNo}"
                    else "물건관리번호 ${listing.managementNo} (눌러서 복사)",
                    style = MaterialTheme.typography.bodySmall,
                    color = if (copied) VerifiedGreen
                    else MaterialTheme.colorScheme.onSurfaceVariant,
                    modifier = Modifier.clickable {
                        clipboard.setText(AnnotatedString(listing.managementNo))
                        copied = true
                    },
                )
            }

            Spacer(Modifier.height(12.dp))
            Row(horizontalArrangement = Arrangement.spacedBy(8.dp)) {
                Button(onClick = onPlan, modifier = Modifier.weight(1f)) {
                    Text("자금계획")
                }
                OutlinedButton(onClick = onOpen, modifier = Modifier.weight(1f)) {
                    Text("온비드")
                }
                if (listing.mapUrl.isNotBlank()) {
                    OutlinedButton(
                        onClick = { openExternalLink(context, listing.mapUrl) },
                        modifier = Modifier.weight(1f),
                    ) { Text("지도") }
                }
            }

            if (listing.source == "onbid") {
                Spacer(Modifier.height(6.dp))
                OutlinedButton(onClick = onDetail, modifier = Modifier.fillMaxWidth()) {
                    Text(if (detail != null) "상세 접기" else "권리·점유 상세")
                }
            }

            if (detailLoading) {
                Spacer(Modifier.height(8.dp))
                CircularProgressIndicator(Modifier.height(20.dp), strokeWidth = 2.dp)
            }
            detail?.let { DetailBlock(it) }
        }
    }
}

private fun sourceLabel(source: String): String = when (source) {
    "onbid" -> "공매"
    "court" -> "법원경매"
    "rtms" -> "실거래"
    "applyhome" -> "청약"
    else -> source
}


/**
 * 물건 상세. 목록 API 에는 없고 상세 API 에만 있는 것들이다.
 *
 * 위험 신호를 맨 위에 둔다. 공매에서 낙찰 뒤 곤란해지는 원인은 대부분
 * 가격이 아니라 여기 적힌 점유·권리 관계다.
 */
@Composable
private fun DetailBlock(detail: ListingDetail) {
    Spacer(Modifier.height(10.dp))
    HorizontalDivider()
    Spacer(Modifier.height(10.dp))

    if (detail.riskFlags.isNotEmpty()) {
        Text("확인할 것", style = MaterialTheme.typography.titleSmall, color = WarningAmber)
        detail.riskFlags.forEach {
            Text("· $it", style = MaterialTheme.typography.bodySmall, color = WarningAmber)
        }
        Spacer(Modifier.height(8.dp))
    }

    // 서류에 나온 말을 쉬운 말로. 읽어도 무슨 뜻인지 모르겠다는 것이
    // 이 서류들의 가장 큰 벽이라, 원문보다 위에 둔다.
    if (detail.glossary.isNotEmpty()) {
        Text("이 말이 무슨 뜻이냐면", style = MaterialTheme.typography.titleSmall)
        Spacer(Modifier.height(6.dp))
        detail.glossary.forEach { g ->
            Card(
                Modifier.fillMaxWidth().padding(bottom = 6.dp),
                colors = CardDefaults.cardColors(
                    containerColor = MaterialTheme.colorScheme.surfaceVariant,
                ),
            ) {
                Column(Modifier.padding(10.dp)) {
                    Text(g.term, style = MaterialTheme.typography.labelLarge)
                    Spacer(Modifier.height(3.dp))
                    Text(g.plain, style = MaterialTheme.typography.bodySmall)
                    if (g.impact.isNotBlank()) {
                        Spacer(Modifier.height(4.dp))
                        Text(
                            "→ ${g.impact}",
                            style = MaterialTheme.typography.bodySmall,
                            color = WarningAmber,
                        )
                    }
                    if (g.law.isNotBlank()) {
                        Spacer(Modifier.height(4.dp))
                        Text(
                            g.law,
                            style = MaterialTheme.typography.bodySmall,
                            color = MaterialTheme.colorScheme.onSurfaceVariant,
                        )
                    }
                }
            }
        }
        Spacer(Modifier.height(8.dp))
    }

    listOf(
        "유의사항" to detail.notes,
        "이용현황" to detail.usageStatus,
        "위치·부근" to detail.vicinity,
    ).forEach { (label, value) ->
        if (value.isNotBlank()) {
            Text(label, style = MaterialTheme.typography.labelLarge)
            Text(
                value,
                style = MaterialTheme.typography.bodySmall,
                color = MaterialTheme.colorScheme.onSurfaceVariant,
            )
            Spacer(Modifier.height(6.dp))
        }
    }

    if (detail.rights.isNotEmpty()) {
        Spacer(Modifier.height(4.dp))
        Text("등기 권리", style = MaterialTheme.typography.labelLarge)
        detail.rights.forEach { row ->
            val amount = row["설정액"]?.toLongOrNull()?.takeIf { it > 0 }
            Text(
                listOfNotNull(
                    row["구분"], row["권리자"], row["등기일"],
                    amount?.let { formatKrw(it) },
                ).joinToString(" · "),
                style = MaterialTheme.typography.bodySmall,
                color = MaterialTheme.colorScheme.onSurfaceVariant,
            )
        }
    }

    if (detail.areas.isNotEmpty()) {
        Spacer(Modifier.height(6.dp))
        Text(
            "면적: " + detail.areas.joinToString(", ") {
                "${it["구분"].orEmpty()} ${it["면적"].orEmpty()}".trim()
            },
            style = MaterialTheme.typography.bodySmall,
        )
    }

    val extras = listOfNotNull(
        detail.evictionBurden.takeIf { it.isNotBlank() }?.let { "명도책임 $it" },
        detail.rentPeriod.takeIf { it.isNotBlank() && it != "-" }?.let { "임대기간 $it" },
        detail.distributionDeadline.takeIf { it.isNotBlank() && it != "-" }
            ?.let { "배분요구종기 $it" },
        detail.delegatingOrg.takeIf { it.isNotBlank() }?.let { "위임 $it" },
    )
    if (extras.isNotEmpty()) {
        Spacer(Modifier.height(6.dp))
        Text(
            extras.joinToString(" · "),
            style = MaterialTheme.typography.bodySmall,
            color = MaterialTheme.colorScheme.onSurfaceVariant,
        )
    }

    detail.appraisals.firstOrNull()?.let { a ->
        val url = a["감정평가서"].orEmpty()
        if (url.isNotBlank()) {
            val context = LocalContext.current
            Spacer(Modifier.height(8.dp))
            OutlinedButton(
                onClick = { openExternalLink(context, url) },
                modifier = Modifier.fillMaxWidth(),
            ) { Text("감정평가서 보기 (${a["평가기관"].orEmpty()})") }
        }
    }
}
