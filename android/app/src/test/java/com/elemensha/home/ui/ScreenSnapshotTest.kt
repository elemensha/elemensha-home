package com.elemensha.home.ui

import app.cash.paparazzi.DeviceConfig
import app.cash.paparazzi.Paparazzi
import com.android.resources.Density
import com.android.resources.ScreenOrientation
import com.elemensha.home.UiState
import com.elemensha.home.data.BorrowerProfile
import com.elemensha.home.data.FilterProfile
import com.elemensha.home.data.HealthResponse
import com.elemensha.home.data.LandCategoryCount
import com.elemensha.home.data.Listing
import com.elemensha.home.data.RegionCount
import kotlinx.serialization.json.Json
import kotlinx.serialization.json.JsonObject
import androidx.compose.foundation.background
import androidx.compose.foundation.layout.fillMaxSize
import androidx.compose.foundation.layout.padding
import org.junit.Rule
import org.junit.Test

/**
 * 화면을 실제로 그려서 그림으로 뽑는다.
 *
 * 에뮬레이터가 없는 기계라 이게 유일하게 **진짜 Compose 코드**를 보는 길이다.
 * 목업을 따로 그려 놓고 앱이 그렇다고 말하지 않기 위해 이걸 둔다.
 *
 * 자료는 고정이다. 전후를 비교하려면 같은 값을 같은 폭에서 그려야 한다.
 */
class ScreenSnapshotTest {

    @get:Rule
    val paparazzi = Paparazzi(
        deviceConfig = phone(390),
        theme = "android:Theme.Material.Light.NoActionBar",
        showSystemUi = false,
    )

    @Test fun listings390() = shot(390) { ListingsBoard(SAMPLE) }
    @Test fun listings360() = shot(360) { ListingsBoard(SAMPLE) }
    @Test fun listings430() = shot(430) { ListingsBoard(SAMPLE) }
    @Test fun listings320() = shot(320) { ListingsBoard(SAMPLE) }

    @Test fun filters390() = shot(390) { FiltersBoard(SAMPLE) }
    @Test fun filters320() = shot(320) { FiltersBoard(SAMPLE) }

    @Test fun plan390() = shot(390) { PlanBoard(SAMPLE) }
    @Test fun plan320() = shot(320) { PlanBoard(SAMPLE) }

    @Test fun settings390() = shot(390) { SettingsBoard(SAMPLE) }
    @Test fun settings320() = shot(320) { SettingsBoard(SAMPLE) }

    @Test fun empty390() = shot(390) { ListingsBoard(EMPTY) }

    // 펼친 상세가 이 앱에서 제일 중요한 화면이다. 보증금 인수 판정이 여기 있다.
    // 목록 화면에 펼치면 머리띠·칩·카드가 위 900px 를 먹어 상세가 안 보인다.
    // 상세 덩어리만 따로 그린다. 한 장에 다 안 들어가서 앞뒤 두 장으로 나눈다.
    @Test fun detailTop390() = shot(390) { DetailBoard(DETAIL_SAMPLE) }
    @Test fun detailTop320() = shot(320) { DetailBoard(DETAIL_SAMPLE) }
    @Test fun detailRest390() = shot(390) { DetailBoard(DETAIL_REST) }

    private fun shot(widthDp: Int, content: @androidx.compose.runtime.Composable () -> Unit) {
        paparazzi.unsafeUpdateConfig(deviceConfig = phone(widthDp))
        paparazzi.snapshot { HomeTheme(darkTheme = false) { content() } }
    }

    private companion object {
        /**
         * 폭만 바꾼 같은 기계.
         *
         * 밀도를 1배로 두는 이유는 그림 때문이다. 이 도구는 긴 변을 1000px 로
         * 줄여 저장해서, 2배 밀도에 화면을 길게 잡으면 205px 짜리 그림이
         * 나와 아무것도 안 읽힌다. 1dp=1px 로 두면 줄이지 않는다.
         */
        fun phone(widthDp: Int) = DeviceConfig(
            screenWidth = widthDp,
            screenHeight = 1000,
            density = Density.MEDIUM,
            orientation = ScreenOrientation.PORTRAIT,
            locale = "ko-rKR",
            softButtons = false,
        )

        private val json = Json { ignoreUnknownKeys = true }

        private fun raw(text: String) = json.decodeFromString(JsonObject.serializer(), text)

        val LISTINGS = listOf(
            Listing(
                source = "onbid",
                sourceId = "2026-08842-001-0000000",
                title = "서울 중구 을지로3가 대지 82㎡ 및 지상 건물",
                url = "https://www.onbid.co.kr",
                sido = "서울특별시", sigungu = "중구",
                address = "서울특별시 중구 을지로3가 12-3",
                propertyType = "상가",
                exclusiveAreaSqm = 82.4,
                favorite = true,
                appraisedPriceKrw = 530_000_000,
                minBidPriceKrw = 412_000_000,
                effectivePriceKrw = 412_000_000,
                deadline = "2026-09-15T17:00",
                bidStatus = "진행중",
                isBiddable = true,
                failedBidCount = 2,
                discountRatio = 0.223,
                raw = raw("""{"map_url":"https://map.naver.com","caution":""}"""),
            ),
            Listing(
                source = "onbid",
                sourceId = "2026-07711-002-0000000",
                title = "서울 강남구 역삼동 오피스텔 29㎡ 지분 1/2",
                url = "https://www.onbid.co.kr",
                sido = "서울특별시", sigungu = "강남구",
                address = "서울특별시 강남구 역삼동 736-21",
                propertyType = "오피스텔",
                exclusiveAreaSqm = 29.7,
                shareSale = true,
                appraisedPriceKrw = 310_000_000,
                minBidPriceKrw = 268_000_000,
                effectivePriceKrw = 268_000_000,
                deadline = "2026-10-02T17:00",
                bidStatus = "준비중",
                bidStart = "2026-09-28T10:00",
                isBiddable = false,
                failedBidCount = 1,
                discountRatio = 0.135,
                raw = raw("""{"map_url":"https://map.naver.com"}"""),
            ),
            Listing(
                source = "onbid",
                sourceId = "2026-05520-004-0000000",
                title = "경기 성남시 분당구 대장동 임야 1,204㎡",
                url = "https://www.onbid.co.kr",
                sido = "경기도", sigungu = "성남시 분당구",
                address = "경기도 성남시 분당구 대장동 산 18",
                propertyType = "토지",
                exclusiveAreaSqm = 1204.0,
                appraisedPriceKrw = 154_000_000,
                minBidPriceKrw = 96_000_000,
                effectivePriceKrw = 96_000_000,
                deadline = "2026-10-20T17:00",
                bidStatus = "진행중",
                isBiddable = true,
                failedBidCount = 3,
                discountRatio = 0.376,
                raw = raw(
                    """{"usage_minor":"임야","needs_farmland_permit":"true",""" +
                        """"map_url":"https://map.naver.com"}"""
                ),
            ),
        )

        val SAMPLE = UiState(
            serverUrl = "https://elemensha-claude.duckdns.org/home",
            apiToken = "x",
            listings = LISTINGS,
            totalMatched = 2116,
            filters = listOf(
                FilterProfile(id = 1, name = "서울·경기 5억 이하"),
                FilterProfile(id = 2, name = "토지 3천 이하"),
            ),
            regions = listOf(
                RegionCount("서울특별시", 412),
                RegionCount("경기도", 907),
                RegionCount("부산광역시", 188),
            ),
            landCategories = listOf(
                LandCategoryCount("전", 221),
                LandCategoryCount("답", 174),
                LandCategoryCount("임야", 903),
            ),
            selectedFilterId = 1,
            lastCollectedAt = "2026-09-13T05:12:04",
            borrower = BorrowerProfile(
                annualIncomeKrw = 72_000_000,
                cashKrw = 180_000_000,
            ),
            appVersion = "0.18.0",
            notifyHour = 7,
        )

        /** 상세의 뒷부분. 앞 장에 나온 덩어리를 빼서 점검 순서부터 보이게 한다. */
        val DETAIL_REST = DETAIL_SAMPLE.copy(
            riskFlags = emptyList(),
            tenancy = null,
            saleKind = null,
            priceHistory = emptyList(),
        )

        val EMPTY = UiState(
            serverUrl = "https://elemensha-claude.duckdns.org/home",
            listings = emptyList(),
            totalMatched = 0,
            filters = listOf(FilterProfile(id = 1, name = "서울·경기 5억 이하")),
            health = HealthResponse(),
            lastCollectedAt = "2026-09-13T05:12:04",
        )
    }
}

@androidx.compose.runtime.Composable
private fun ListingsBoard(state: UiState) = ListingsScreen(
    state = state,
    onRefresh = {}, onPlanForListing = {}, onSelectFilter = {}, onShowAll = {},
    onSort = {}, onOpenDetail = {}, onToggleBiddable = {}, onAddCourtListing = {},
    onToggleFavorite = {}, onToggleFavoritesOnly = {}, onToggleRecent = {},
)

@androidx.compose.runtime.Composable
private fun FiltersBoard(state: UiState) =
    FiltersScreen(state = state, onSave = {}, onDelete = {})

@androidx.compose.runtime.Composable
private fun PlanBoard(state: UiState) = PlanScreen(
    state = state,
    onBorrowerChange = {},
    onCalculate = { _, _, _, _, _, _ -> },
)

@androidx.compose.runtime.Composable
private fun SettingsBoard(state: UiState) = SettingsScreen(
    state = state,
    onSave = { _, _ -> }, onServerRefresh = {}, onCheckUpdate = {},
    onDownloadUpdate = {}, onInstallUpdate = {}, onOpenInstallPermission = {},
    onToggleNotifications = {}, onSetNotifyHour = {}, onTestNotification = {},
    onRequestNotificationPermission = {},
)

@androidx.compose.runtime.Composable
private fun DetailBoard(detail: com.elemensha.home.data.ListingDetail) =
    androidx.compose.foundation.layout.Box(
        androidx.compose.ui.Modifier
            .fillMaxSize()
    ) {
        androidx.compose.foundation.layout.Column(
            androidx.compose.ui.Modifier
                .background(androidx.compose.material3.MaterialTheme.colorScheme.background)
                .padding(Dim.ScreenPad)
        ) {
            HomeCard { DetailBlock(detail, null) }
        }
    }
