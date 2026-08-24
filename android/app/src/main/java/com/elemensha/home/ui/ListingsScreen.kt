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
import androidx.compose.material3.AssistChip
import androidx.compose.material3.Button
import androidx.compose.material3.Card
import androidx.compose.material3.CardDefaults
import androidx.compose.material3.MaterialTheme
import androidx.compose.material3.OutlinedButton
import androidx.compose.material3.Text
import androidx.compose.runtime.Composable
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.platform.LocalContext
import androidx.compose.ui.text.font.FontWeight
import androidx.compose.ui.unit.dp
import androidx.core.net.toUri
import com.elemensha.home.UiState
import com.elemensha.home.data.Listing

/**
 * 물건 목록.
 *
 * 목록이 비었을 때 **왜 비었는지**를 반드시 알려준다. 서버가 안 붙었는지,
 * 서비스키가 없는지, 조건에 맞는 물건이 정말 없는지는 전혀 다른 상황인데
 * 화면상으로는 똑같이 "빈 목록"이라 구분이 안 된다.
 */
@Composable
fun ListingsScreen(
    state: UiState,
    onRefresh: () -> Unit,
    onPlanForListing: (Listing) -> Unit,
) {
    val context = LocalContext.current

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
                Text(
                    "물건 ${state.listings.size}건",
                    style = MaterialTheme.typography.titleMedium,
                )
                OutlinedButton(onClick = onRefresh, enabled = !state.loading) {
                    Text("새로고침")
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
                        context.startActivity(
                            Intent(Intent.ACTION_VIEW, listing.url.toUri())
                        )
                    }
                },
                onPlan = { onPlanForListing(listing) },
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
                else -> "수집은 정상인데 조건에 맞는 물건이 없다. 조건 탭에서 범위를 넓혀볼 것."
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
private fun ListingCard(listing: Listing, onOpen: () -> Unit, onPlan: () -> Unit) {
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
            listing.deadline?.let {
                Text(
                    "마감 ${formatDate(it)}",
                    style = MaterialTheme.typography.bodySmall,
                    color = MaterialTheme.colorScheme.error,
                )
            }

            Spacer(Modifier.height(12.dp))
            Row(horizontalArrangement = Arrangement.spacedBy(8.dp)) {
                Button(onClick = onPlan, modifier = Modifier.weight(1f)) {
                    Text("자금계획")
                }
                OutlinedButton(onClick = onOpen, modifier = Modifier.weight(1f)) {
                    Text("원문 보기")
                }
            }
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
