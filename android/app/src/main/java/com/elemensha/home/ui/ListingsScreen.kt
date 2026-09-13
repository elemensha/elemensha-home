package com.elemensha.home.ui

import androidx.compose.foundation.clickable
import androidx.compose.foundation.layout.Arrangement
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.ExperimentalLayoutApi
import androidx.compose.foundation.layout.FlowRow
import androidx.compose.foundation.layout.Row
import androidx.compose.foundation.layout.Spacer
import androidx.compose.foundation.layout.fillMaxWidth
import androidx.compose.foundation.layout.height
import androidx.compose.foundation.layout.padding
import androidx.compose.foundation.lazy.LazyColumn
import androidx.compose.foundation.lazy.items
import androidx.compose.material3.CircularProgressIndicator
import androidx.compose.material3.HorizontalDivider
import androidx.compose.material3.MaterialTheme
import androidx.compose.material3.Text
import androidx.compose.runtime.Composable
import androidx.compose.runtime.getValue
import androidx.compose.runtime.mutableStateOf
import androidx.compose.runtime.remember
import androidx.compose.runtime.setValue
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.platform.LocalClipboardManager
import androidx.compose.ui.platform.LocalContext
import androidx.compose.ui.text.AnnotatedString
import androidx.compose.ui.text.font.FontWeight
import androidx.compose.ui.unit.dp
import com.elemensha.home.UiState
import com.elemensha.home.data.Listing
import com.elemensha.home.data.ListingDetail
import com.elemensha.home.data.ManualCourtListing
import com.elemensha.home.data.PlanResponse

/**
 * 물건 목록.
 *
 * 목록이 비었을 때 **왜 비었는지**를 반드시 알려준다. 서버가 안 붙었는지,
 * 서비스키가 없는지, 조건에 맞는 물건이 정말 없는지는 전혀 다른 상황인데
 * 화면상으로는 똑같이 "빈 목록"이라 구분이 안 된다.
 *
 * 화면 구성의 원칙은 하나다. **한 물건에 붙는 경고가 예닐곱 줄인데 전부
 * 같은 크기 같은 회색이면 아무것도 안 읽힌다.** 그래서 숫자는 칸으로 키우고,
 * 경고는 뜻에 따라 색 띠를 세워 묶고, 나머지 설명은 작게 내렸다.
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
    onToggleFavorite: (Listing) -> Unit,
    onToggleFavoritesOnly: (Boolean) -> Unit,
    onToggleRecent: (Boolean) -> Unit,
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
        modifier = Modifier.fillMaxWidth().padding(horizontal = Dim.ScreenPad),
        verticalArrangement = Arrangement.spacedBy(Dim.Gap),
    ) {
        item { Spacer(Modifier.height(6.dp)) }

        item {
            ScreenBand(
                eyebrow = "ELEMENSHA HOME",
                title = if (state.totalMatched > state.listings.size)
                    "물건 ${state.listings.size} / ${countText(state.totalMatched)}건"
                else "물건 ${countText(state.totalMatched)}건",
                sub = (if (state.recentOnly) "최근 본 물건"
                else if (state.favoritesOnly) "관심 물건"
                else if (state.applyFilters) "조건 적용됨" else "조건 없이 전체") +
                    " · 마감된 물건 숨김" +
                    // 언제 자료인지 밝히지 않으면 오래된 값을 지금 값으로 읽는다.
                    (state.lastCollectedAt?.let { "\n갱신 " + it.take(16).replace('T', ' ') }
                        ?: ""),
            )
        }

        item {
            Row(
                Modifier.fillMaxWidth(),
                horizontalArrangement = Arrangement.spacedBy(Dim.GapTight),
            ) {
                // 법원경매는 자동 수집이 막혀 있어 손으로 넣는다.
                GhostAction(
                    text = "＋ 경매 직접 등록",
                    onClick = { showCourtEntry = true },
                    enabled = state.isConfigured,
                    small = true,
                    modifier = Modifier.weight(1f),
                )
                GhostAction(
                    text = if (state.loading) "불러오는 중" else "새로고침",
                    onClick = onRefresh,
                    enabled = !state.loading,
                    small = true,
                    modifier = Modifier.weight(1f),
                )
            }
        }

        // 조건 선택. 조건 탭에서 만든 것이 여기 칩으로 뜬다.
        item {
            Column(verticalArrangement = Arrangement.spacedBy(Dim.GapTight)) {
                SectionLabel("무엇을 볼까")
                FlowRow(
                    horizontalArrangement = Arrangement.spacedBy(Dim.GapTight),
                    verticalArrangement = Arrangement.spacedBy(Dim.GapTight),
                ) {
                    SelectChip(!state.applyFilters, "전체") { onShowAll() }
                    SelectChip(state.favoritesOnly, "★ 관심") {
                        onToggleFavoritesOnly(!state.favoritesOnly)
                    }
                    SelectChip(state.recentOnly, "최근 본") {
                        onToggleRecent(!state.recentOnly)
                    }
                    SelectChip(state.biddableOnly, "지금 입찰 가능") {
                        onToggleBiddable(!state.biddableOnly)
                    }
                    SelectChip(
                        selected = state.applyFilters && state.selectedFilterId == null,
                        label = "내 조건 전부",
                        onClick = { onSelectFilter(null) },
                        enabled = state.filters.isNotEmpty(),
                    )
                    state.filters.forEach { filter ->
                        SelectChip(state.selectedFilterId == filter.id, filter.name) {
                            filter.id?.let(onSelectFilter)
                        }
                    }
                }
            }
        }

        item {
            Column(verticalArrangement = Arrangement.spacedBy(Dim.GapTight)) {
                SectionLabel("정렬")
                FlowRow(
                    horizontalArrangement = Arrangement.spacedBy(Dim.GapTight),
                    verticalArrangement = Arrangement.spacedBy(Dim.GapTight),
                ) {
                    listOf(
                        "recent" to "최신순",
                        "discount" to "할인폭순",
                        "price" to "가격순",
                        "deadline" to "마감임박순",
                    ).forEach { (key, label) ->
                        SelectChip(state.sort == key, label) { onSort(key) }
                    }
                }
            }
        }

        if (state.listings.isEmpty()) {
            item { EmptyExplanation(state) }
        }

        items(state.listings, key = { it.source + it.sourceId }) { listing ->
            val key = listing.dedupeKey ?: (listing.source + ":" + listing.sourceId)
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
                detail = if (state.detailKey == key) state.detail else null,
                detailLoading = state.detailLoading && state.detailKey == key,
                onFavorite = { onToggleFavorite(listing) },
                plan = if (state.detailKey == key) state.detailPlan else null,
            )
        }

        item { Spacer(Modifier.height(24.dp)) }
    }
}

@Composable
private fun EmptyExplanation(state: UiState) {
    val health = state.health
    HomeCard(accent = Meaning.Caution) {
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
            SectionLabel("소스 상태")
            Spacer(Modifier.height(4.dp))
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

/**
 * 카드 왼쪽 띠의 색을 정한다.
 *
 * 여기 쓰는 뜻은 딱 하나다 - **이 물건에서 돈을 잃을 수 있는 요소가 있는가.**
 * 좋아 보이게 만드는 색이 아니라, 스크롤만 해도 걸러낼 수 있게 하는 색이다.
 */
private fun cardTone(listing: Listing): Meaning {
    val days = daysUntil(listing.deadline)
    return when {
        listing.shareSale -> Meaning.Danger
        listing.needsFarmlandPermit -> Meaning.Danger
        days != null && days <= 3 -> Meaning.Danger
        listing.source == "rtms" -> Meaning.Caution
        listing.caution.isNotBlank() || listing.priceNote.isNotBlank() -> Meaning.Caution
        listing.source == "onbid" && !listing.isLand -> Meaning.Caution
        listing.isBiddable -> Meaning.Good
        else -> Meaning.Neutral
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
    onFavorite: () -> Unit,
    plan: PlanResponse?,
) {
    val context = LocalContext.current
    HomeCard(accent = cardTone(listing)) {
        Row(
            Modifier.fillMaxWidth(),
            horizontalArrangement = Arrangement.spacedBy(5.dp),
            verticalAlignment = Alignment.CenterVertically,
        ) {
            // 별은 카드를 여는 것과 구분돼야 한다. 별에는 자기 클릭을 따로 건다.
            Text(
                if (listing.favorite) "★" else "☆",
                style = MaterialTheme.typography.titleMedium,
                color = if (listing.favorite) Tone.Amber
                else MaterialTheme.colorScheme.outline,
                modifier = Modifier
                    .clickable(onClick = onFavorite)
                    .padding(end = 2.dp, top = 2.dp, bottom = 2.dp),
            )
            ToneBadge(sourceLabel(listing.source))
            if (listing.source == "onbid") {
                ToneBadge(
                    if (listing.isBiddable) "지금 입찰 가능"
                    else listing.bidStatus.ifBlank { "준비중" },
                    if (listing.isBiddable) Meaning.Good else Meaning.Neutral,
                )
            }
            if (listing.shareSale) ToneBadge("지분", Meaning.Danger)
            if (listing.failedBidCount > 0) {
                ToneBadge("유찰 ${listing.failedBidCount}회", Meaning.Caution)
            }
        }

        Spacer(Modifier.height(7.dp))
        Text(
            listing.title,
            style = MaterialTheme.typography.titleMedium,
            modifier = Modifier.clickable(onClick = onOpen),
        )
        Text(
            listing.address.ifBlank { "${listing.sido} ${listing.sigungu}" },
            style = MaterialTheme.typography.bodySmall,
            color = MaterialTheme.colorScheme.onSurfaceVariant,
        )

        // 값. 여기가 이 카드에서 제일 먼저 읽혀야 하는 곳이다.
        val discounted = listing.appraisedPriceKrw != null &&
            listing.minBidPriceKrw != null &&
            listing.minBidPriceKrw < listing.appraisedPriceKrw
        Spacer(Modifier.height(9.dp))
        Row(horizontalArrangement = Arrangement.spacedBy(6.dp)) {
            StatTile(
                label = if (listing.source == "rtms") "신고가" else "최저 입찰가",
                value = formatKrw(listing.effectivePriceKrw),
                modifier = Modifier.weight(1.4f),
            )
            if (discounted || listing.source == "rtms") {
                StatTile(
                    label = if (listing.source == "rtms") "실거래보다 낮음"
                    else "감정가보다 낮음",
                    value = formatPercent(listing.discountRatio, 0),
                    meaning = if (listing.source == "rtms") Meaning.Caution else Meaning.Good,
                    modifier = Modifier.weight(1f),
                )
            } else if (listing.exclusiveAreaSqm != null) {
                StatTile(
                    label = "면적",
                    value = formatArea(listing.exclusiveAreaSqm),
                    modifier = Modifier.weight(1f),
                )
            }
        }
        // 면적 칸이 위에서 밀렸으면 한 줄로 내려 적는다. 빼지는 않는다.
        if (listing.exclusiveAreaSqm != null && (discounted || listing.source == "rtms")) {
            Spacer(Modifier.height(4.dp))
            Text(
                formatArea(listing.exclusiveAreaSqm),
                style = MaterialTheme.typography.bodySmall,
                color = MaterialTheme.colorScheme.onSurfaceVariant,
            )
        }
        if (discounted) {
            Spacer(Modifier.height(3.dp))
            Text(
                "감정가 " + formatKrw(listing.appraisedPriceKrw),
                style = MaterialTheme.typography.bodySmall,
                color = MaterialTheme.colorScheme.onSurfaceVariant,
            )
        }

        // 조심할 것들. 한 줄짜리 회색 글씨로 늘어놓지 않고 뜻이 있는 칸으로 묶는다.
        val notes = buildList {
            if (listing.priceNote.isNotBlank()) add(Meaning.Caution to listing.priceNote)
            if (listing.source == "rtms") {
                add(
                    Meaning.Caution to ("최근 실거래 중앙값 " +
                        formatKrw(listing.marketPriceKrw) + " 대비 낮게 신고됨. " +
                        "이미 체결된 거래라 지금 살 수 있는 매물이 아니다.")
                )
            }
            // 공매의 핵심 리스크. 인도명령이 없어 점유자가 있으면 협의가
            // 깨졌을 때 명도소송으로 가고 5~6개월이 걸린다. 토지는 그 대상이
            // 아예 없어서 성격이 완전히 다르다.
            if (listing.source == "onbid") {
                if (listing.isLand) {
                    add(
                        Meaning.Good to ("명도 부담 없음 (토지)" +
                            if (listing.usageMinor.isNotBlank()) " · 지목 ${listing.usageMinor}"
                            else "")
                    )
                    if (listing.needsFarmlandPermit) {
                        add(Meaning.Danger to "농지취득자격증명 필요 — 못 받으면 보증금을 잃는다")
                    }
                    add(
                        Meaning.Neutral to ("맹지 여부·용도지역은 이 앱이 판정하지 못한다. " +
                            "지도에서 도로가 필지에 닿는지 직접 확인할 것.")
                    )
                } else {
                    add(
                        Meaning.Caution to ("명도는 매수자 부담 — 공매는 인도명령이 없어 " +
                            "협의가 안 되면 명도소송(5~6개월)으로 간다")
                    )
                }
            }
            if (listing.shareSale) {
                add(Meaning.Danger to "지분 매각 — 낙찰받아도 혼자서는 쓰지도 팔지도 못한다")
            }
            if (listing.caution.isNotBlank()) add(Meaning.Caution to listing.caution)
        }
        if (notes.isNotEmpty()) {
            Spacer(Modifier.height(8.dp))
            Column(verticalArrangement = Arrangement.spacedBy(4.dp)) {
                notes.forEach { (tone, text) -> NoteRow(tone, text) }
            }
        }

        // 언제까지인지. 사흘 안쪽이면 칸으로 띄운다 - 준비할 시간이 없다는 뜻이다.
        Spacer(Modifier.height(7.dp))
        if (!listing.isBiddable && !listing.bidStart.isNullOrBlank()) {
            Text(
                "입찰 시작 " + listing.bidStart.replace('T', ' ') + " (한국시간)",
                style = MaterialTheme.typography.bodySmall,
                color = MaterialTheme.colorScheme.onSurfaceVariant,
            )
        }
        listing.deadline?.let { dl ->
            val days = daysUntil(dl)
            val text = "${formatDeadline(dl)} · ${dl.replace('T', ' ')} (한국시간)"
            if (days != null && days <= 3) {
                NoteRow(Meaning.Danger, text, lead = "마감")
            } else {
                Text(
                    text,
                    style = MaterialTheme.typography.bodySmall,
                    color = MaterialTheme.colorScheme.onSurfaceVariant,
                )
            }
        }

        // 온비드는 개편 뒤 물건 하나를 바로 여는 주소가 없다. 번호를
        // 복사해 온비드에서 검색하는 것이 유일한 경로라 눌러서 복사되게 둔다.
        if (listing.managementNo.isNotBlank()) {
            val clipboard = LocalClipboardManager.current
            var copied by remember(listing.managementNo) { mutableStateOf(false) }
            Spacer(Modifier.height(4.dp))
            Text(
                if (copied) "복사됨 · ${listing.managementNo}"
                else "물건관리번호 ${listing.managementNo} (눌러서 복사)",
                style = MaterialTheme.typography.bodySmall,
                color = if (copied) Tone.GreenDeep
                else MaterialTheme.colorScheme.onSurfaceVariant,
                modifier = Modifier
                    .clickable {
                        clipboard.setText(AnnotatedString(listing.managementNo))
                        copied = true
                    }
                    .padding(vertical = 6.dp),
            )
        }

        // 버튼은 두 줄로 나눈다. 320px 폭에서 세 개를 한 줄에 넣으면 글자가 잘린다.
        Spacer(Modifier.height(10.dp))
        Row(horizontalArrangement = Arrangement.spacedBy(6.dp)) {
            PrimaryAction("자금계획", onPlan, Modifier.weight(1f))
            GhostAction("온비드", onOpen, Modifier.weight(1f))
        }
        val hasMap = listing.mapUrl.isNotBlank()
        val hasDetail = listing.source == "onbid"
        if (hasMap || hasDetail) {
            Spacer(Modifier.height(6.dp))
            Row(horizontalArrangement = Arrangement.spacedBy(6.dp)) {
                if (hasMap) {
                    GhostAction(
                        "지도",
                        { openExternalLink(context, listing.mapUrl) },
                        Modifier.weight(1f),
                    )
                }
                if (hasDetail) {
                    GhostAction(
                        if (detail != null) "상세 접기" else "권리·점유 상세",
                        onDetail,
                        Modifier.weight(if (hasMap) 1.6f else 1f),
                    )
                }
            }
        }

        if (detailLoading) {
            Spacer(Modifier.height(8.dp))
            CircularProgressIndicator(Modifier.height(20.dp), strokeWidth = 2.dp)
        }
        detail?.let { DetailBlock(it, plan) }
    }
}

/** 2116 을 2,116 으로. 네 자리부터는 쉼표가 없으면 자릿수를 잘못 읽는다. */
private fun countText(n: Int): String = "%,d".format(n)

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
internal fun DetailBlock(detail: ListingDetail, plan: PlanResponse?) {
    Spacer(Modifier.height(12.dp))
    HorizontalDivider(color = MaterialTheme.colorScheme.outlineVariant)
    Spacer(Modifier.height(12.dp))

    if (detail.riskFlags.isNotEmpty()) {
        SectionLabel("확인할 것")
        Spacer(Modifier.height(5.dp))
        Column(verticalArrangement = Arrangement.spacedBy(4.dp)) {
            detail.riskFlags.forEach { NoteRow(Meaning.Caution, it) }
        }
        Spacer(Modifier.height(10.dp))
    }

    // 이 물건을 살 수 있는 돈이 되는지. 탭을 옮기면 어느 물건을 보고
    // 있었는지가 끊겨서, 그 자리에서 보여준다.
    plan?.let { pl ->
        val short = pl.cashShortfallKrw > 0
        val tone = if (short) Meaning.Caution else Meaning.Good
        Column(
            Modifier.fillMaxWidth().padding(bottom = 10.dp),
            verticalArrangement = Arrangement.spacedBy(5.dp),
        ) {
            SectionLabel("이 물건 자금계획")
            Row(horizontalArrangement = Arrangement.spacedBy(5.dp)) {
                StatTile(
                    "대출 가능", formatKrw(pl.capacity.limitKrw),
                    Modifier.weight(1f), note = pl.capacity.bindingConstraint + " 제약",
                )
                StatTile("필요한 현금", formatKrw(pl.cashNeededKrw), Modifier.weight(1f))
            }
            KeyValue("취득 비용", formatKrw(pl.acquisitionCost.totalKrw))
            NoteRow(
                tone,
                if (short) "현금이 " + formatKrw(pl.cashShortfallKrw) + " 모자란다"
                else "가진 현금으로 된다",
            )
            // 보증금을 떠안는 물건이면 위 숫자에 그것이 안 들어 있다.
            if (detail.tenancy?.level == "danger") {
                NoteRow(
                    Meaning.Danger,
                    "위 금액에 임차보증금은 들어 있지 않다. 인수하게 되면 그만큼 더 든다.",
                )
            }
        }
    }

    // 값이 어떻게 내려왔는지. 유찰로 떨어지는 것이 공매의 핵심 동학인데
    // 현재 값만 보면 '싼 이유'가 안 보인다. 두 점 이상일 때만 뜻이 있다.
    if (detail.priceHistory.size >= 2) {
        SectionLabel("가격 변동")
        Spacer(Modifier.height(4.dp))
        detail.priceHistory.forEach { pt ->
            Text(
                pt.at.take(10) + "  " + formatKrw(pt.price),
                style = MaterialTheme.typography.bodySmall,
            )
        }
        val first = detail.priceHistory.first().price
        val last = detail.priceHistory.last().price
        if (first != null && last != null && first > 0 && last < first) {
            Spacer(Modifier.height(4.dp))
            NoteRow(
                Meaning.Good,
                "처음 본 값보다 " + formatKrw(first - last) + " 내렸다 " +
                    "(" + Math.round((1 - last.toDouble() / first) * 100) + "%)",
            )
        }
        Spacer(Modifier.height(10.dp))
    }

    // 보증금을 떠안는지가 값을 매길 때 가장 크게 틀리는 지점이다.
    // 상세를 열면 이게 제일 먼저 보여야 한다.
    detail.tenancy?.takeIf { it.summary.isNotBlank() }?.let { tn ->
        val tone = if (tn.level == "danger") Meaning.Danger else Meaning.Caution
        val t = toneSet(tone)
        HomeCard(Modifier.padding(bottom = 10.dp), accent = tone) {
            Text(
                "임차인 · 보증금 인수",
                style = MaterialTheme.typography.titleSmall,
                color = t.fg,
            )
            Spacer(Modifier.height(5.dp))
            Text(
                tn.summary,
                style = MaterialTheme.typography.bodyMedium,
                fontWeight = FontWeight.SemiBold,
                color = t.fg,
            )
            tn.baseline?.let { b ->
                Spacer(Modifier.height(7.dp))
                Text(
                    "기준선 ${b.date} ${b.kind}",
                    style = MaterialTheme.typography.bodySmall,
                    color = MaterialTheme.colorScheme.onSurfaceVariant,
                )
            }
            tn.tenants.forEach { person ->
                Spacer(Modifier.height(7.dp))
                HorizontalDivider(color = MaterialTheme.colorScheme.outlineVariant)
                Spacer(Modifier.height(7.dp))
                Text(
                    "${person.role} ${person.name}" +
                        (if (person.moveIn.isNotBlank()) " · 전입 ${person.moveIn}" else "") +
                        " · 보증금 " + (person.depositKrw?.let { formatKrw(it) } ?: "미상"),
                    style = MaterialTheme.typography.labelLarge,
                )
                Spacer(Modifier.height(2.dp))
                Text(person.verdict, style = MaterialTheme.typography.bodySmall)
            }
            if (tn.caveat.isNotBlank()) {
                Spacer(Modifier.height(9.dp))
                Text(
                    tn.caveat,
                    style = MaterialTheme.typography.bodySmall,
                    color = MaterialTheme.colorScheme.onSurfaceVariant,
                )
            }
        }
    }

    // 어떤 종류의 공매인지부터. 압류재산과 신탁재산은 근거 법령이 달라
    // 조심할 것도 다르므로, 점검 순서보다 먼저 온다.
    detail.saleKind?.takeIf { it.kind.isNotBlank() }?.let { sk ->
        HomeCard(Modifier.padding(bottom = 10.dp), accent = Meaning.Caution) {
            Text(sk.kind, style = MaterialTheme.typography.titleSmall)
            Spacer(Modifier.height(4.dp))
            Text(sk.plain, style = MaterialTheme.typography.bodySmall)
            if (sk.keyPoint.isNotBlank()) {
                Spacer(Modifier.height(6.dp))
                NoteRow(Meaning.Caution, sk.keyPoint)
            }
            if (sk.law.isNotBlank()) {
                Spacer(Modifier.height(5.dp))
                Text(
                    sk.law,
                    style = MaterialTheme.typography.bodySmall,
                    color = MaterialTheme.colorScheme.onSurfaceVariant,
                )
            }
        }
    }

    // 무엇을 어떤 순서로 확인해야 하는지. 순서가 곧 의존 관계라
    // 번호를 그대로 보여준다 - 등기부를 먼저 떼야 전입일을 판단할 수 있다.
    if (detail.checklist.isNotEmpty()) {
        SectionLabel("이 순서로 확인하세요")
        Spacer(Modifier.height(6.dp))
        detail.checklist.forEach { c ->
            HomeCard(Modifier.padding(bottom = 6.dp), accent = Meaning.Good) {
                Row(
                    Modifier.fillMaxWidth(),
                    horizontalArrangement = Arrangement.spacedBy(6.dp),
                ) {
                    Text(
                        "${c.step}. ${c.title}",
                        style = MaterialTheme.typography.labelLarge,
                        modifier = Modifier.weight(1f),
                    )
                    if (c.cost.isNotBlank()) {
                        Text(
                            c.cost,
                            style = MaterialTheme.typography.bodySmall,
                            color = MaterialTheme.colorScheme.onSurfaceVariant,
                        )
                    }
                }
                Spacer(Modifier.height(4.dp))
                Text(c.why, style = MaterialTheme.typography.bodySmall)
                if (c.how.isNotBlank()) {
                    Spacer(Modifier.height(4.dp))
                    Text(
                        c.how,
                        style = MaterialTheme.typography.bodySmall,
                        color = MaterialTheme.colorScheme.onSurfaceVariant,
                    )
                }
                if (c.judge.isNotBlank()) {
                    Spacer(Modifier.height(4.dp))
                    Text(
                        c.judge,
                        style = MaterialTheme.typography.bodySmall,
                        color = Tone.GreenDeep,
                    )
                }
            }
        }
        Spacer(Modifier.height(10.dp))
    }

    // 서류에 나온 말을 쉬운 말로. 읽어도 무슨 뜻인지 모르겠다는 것이
    // 이 서류들의 가장 큰 벽이라, 원문보다 위에 둔다.
    if (detail.glossary.isNotEmpty()) {
        SectionLabel("이 말이 무슨 뜻이냐면")
        Spacer(Modifier.height(6.dp))
        detail.glossary.forEach { g ->
            HomeCard(Modifier.padding(bottom = 6.dp)) {
                Text(g.term, style = MaterialTheme.typography.labelLarge)
                Spacer(Modifier.height(4.dp))
                Text(g.plain, style = MaterialTheme.typography.bodySmall)
                if (g.impact.isNotBlank()) {
                    Spacer(Modifier.height(5.dp))
                    NoteRow(Meaning.Caution, g.impact, lead = "이게 뭘 바꾸냐면")
                }
                if (g.law.isNotBlank()) {
                    Spacer(Modifier.height(5.dp))
                    Text(
                        g.law,
                        style = MaterialTheme.typography.bodySmall,
                        color = MaterialTheme.colorScheme.onSurfaceVariant,
                    )
                }
            }
        }
        Spacer(Modifier.height(10.dp))
    }

    listOf(
        "유의사항" to detail.notes,
        "이용현황" to detail.usageStatus,
        "위치·부근" to detail.vicinity,
    ).forEach { (label, value) ->
        if (value.isNotBlank()) {
            SectionLabel(label)
            Spacer(Modifier.height(2.dp))
            Text(
                value,
                style = MaterialTheme.typography.bodySmall,
                color = MaterialTheme.colorScheme.onSurfaceVariant,
            )
            Spacer(Modifier.height(8.dp))
        }
    }

    if (detail.rights.isNotEmpty()) {
        SectionLabel("등기 권리")
        Spacer(Modifier.height(2.dp))
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
        Spacer(Modifier.height(8.dp))
    }

    if (detail.areas.isNotEmpty()) {
        Text(
            "면적: " + detail.areas.joinToString(", ") {
                "${it["구분"].orEmpty()} ${it["면적"].orEmpty()}".trim()
            },
            style = MaterialTheme.typography.bodySmall,
        )
        Spacer(Modifier.height(6.dp))
    }

    val extras = listOfNotNull(
        detail.evictionBurden.takeIf { it.isNotBlank() }?.let { "명도책임 $it" },
        detail.rentPeriod.takeIf { it.isNotBlank() && it != "-" }?.let { "임대기간 $it" },
        detail.distributionDeadline.takeIf { it.isNotBlank() && it != "-" }
            ?.let { "배분요구종기 $it" },
        detail.delegatingOrg.takeIf { it.isNotBlank() }?.let { "위임 $it" },
    )
    if (extras.isNotEmpty()) {
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
            Spacer(Modifier.height(10.dp))
            GhostAction(
                "감정평가서 보기 (${a["평가기관"].orEmpty()})",
                { openExternalLink(context, url) },
                Modifier.fillMaxWidth(),
            )
        }
    }
}
