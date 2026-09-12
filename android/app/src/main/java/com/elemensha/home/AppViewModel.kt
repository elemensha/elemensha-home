package com.elemensha.home

import android.app.Application
import androidx.lifecycle.AndroidViewModel
import androidx.lifecycle.viewModelScope
import com.elemensha.home.data.Api
import com.elemensha.home.data.BorrowerProfile
import com.elemensha.home.data.FilterProfile
import com.elemensha.home.data.ManualCourtListing
import com.elemensha.home.data.HealthResponse
import com.elemensha.home.data.Listing
import com.elemensha.home.data.ListingDetail
import com.elemensha.home.data.PlanRequest
import com.elemensha.home.data.LandCategoryCount
import com.elemensha.home.data.RegionCount
import com.elemensha.home.data.PlanResponse
import com.elemensha.home.data.Prefs
import com.elemensha.home.notify.Notifier
import com.elemensha.home.update.Updater
import com.elemensha.home.work.ListingWorker
import java.io.File
import kotlinx.coroutines.flow.MutableStateFlow
import kotlinx.coroutines.flow.StateFlow
import kotlinx.coroutines.flow.asStateFlow
import kotlinx.coroutines.flow.update
import kotlinx.coroutines.launch

data class UiState(
    val serverUrl: String = "",
    val apiToken: String = "",
    val health: HealthResponse? = null,
    val listings: List<Listing> = emptyList(),
    /** 조건을 통과한 전체 건수. listings 는 그중 앞부분만 담는다. */
    val totalMatched: Int = 0,
    val filters: List<FilterProfile> = emptyList(),
    /** 서버가 실제로 수집한 지역. 조건 화면의 지역 칩이 이걸로 만들어진다. */
    val regions: List<RegionCount> = emptyList(),
    /** 수집된 토지 지목. 조건 화면의 지목 칩이 이걸로 만들어진다. */
    val landCategories: List<LandCategoryCount> = emptyList(),
    /** null 이면 켜져 있는 조건 전체(합집합). */
    val selectedFilterId: Int? = null,
    val applyFilters: Boolean = true,
    val sort: String = "recent",
    /** 지금 입찰할 수 있는 물건만 볼지. */
    val biddableOnly: Boolean = false,
    /** 관심 물건만 보기. */
    val favoritesOnly: Boolean = false,
    /** 마지막 수집 시각. 언제 자료인지 화면에 밝힌다. */
    val lastCollectedAt: String? = null,
    /** 최근 본 물건만 보기. */
    val recentOnly: Boolean = false,
    val borrower: BorrowerProfile = BorrowerProfile(),
    val plan: PlanResponse? = null,
    /** 지금 펼친 물건의 자금계획. 탭으로 튀지 않고 그 자리에서 본다. */
    val detailPlan: PlanResponse? = null,
    /** 지금 펼쳐 놓은 물건의 상세. null 이면 아직 안 열었다. */
    val detailKey: String? = null,
    val detail: ListingDetail? = null,
    val detailLoading: Boolean = false,
    val update: Updater.State = Updater.State.Idle,
    val appVersion: String = "",
    val notificationsEnabled: Boolean = true,
    /** 알림을 받을 시각(0~23시). 하루 한 번. */
    val notifyHour: Int = 7,
    /** 시스템 알림 권한. 꺼져 있으면 워커가 돌아도 알림이 안 뜬다. */
    val notificationPermission: Boolean = true,
    val lastNotifyResult: String? = null,
    val loading: Boolean = false,
    /** 마지막 실패 사유. 화면에 그대로 띄운다. */
    val error: String? = null,
) {
    val isConfigured: Boolean get() = serverUrl.isNotBlank()
}

class AppViewModel(app: Application) : AndroidViewModel(app) {

    private val prefs = Prefs(app)
    private val api = Api(
        baseUrlProvider = { prefs.serverUrl },
        tokenProvider = { prefs.apiToken },
    )

    private val updater = Updater(app, api)

    private val _state = MutableStateFlow(
        UiState(
            serverUrl = prefs.serverUrl,
            apiToken = prefs.apiToken,
            borrower = prefs.borrower,
            appVersion = Updater(app, api).currentVersionName,
            notificationsEnabled = prefs.notificationsEnabled,
            notifyHour = prefs.notifyHour,
            notificationPermission = Notifier(app).canPost(),
        )
    )
    val state: StateFlow<UiState> = _state.asStateFlow()

    init {
        if (prefs.isConfigured) refresh()
    }

    /** 실패해도 화면이 멈추지 않게, 사유를 상태에 담고 로딩만 푼다. */
    private fun launchGuarded(block: suspend () -> Unit) {
        viewModelScope.launch {
            _state.update { it.copy(loading = true, error = null) }
            runCatching { block() }
                .onFailure { e -> _state.update { it.copy(error = e.message ?: "알 수 없는 오류") } }
            _state.update { it.copy(loading = false) }
        }
    }

    fun saveConnection(url: String, token: String) {
        prefs.serverUrl = url
        prefs.apiToken = token
        _state.update { it.copy(serverUrl = prefs.serverUrl, apiToken = prefs.apiToken) }
        if (prefs.isConfigured && prefs.notificationsEnabled) {
            ListingWorker.schedule(getApplication(), prefs.notifyHour)
        }
        refresh()
    }

    fun refresh() = launchGuarded {
        val health = api.health()
        val filters = api.filters()
        val regionData = runCatching { api.regions() }.getOrNull()
        val current = _state.value
        val response = api.listings(
            filterId = current.selectedFilterId,
            applyFilters = current.applyFilters,
            sort = current.sort,
            biddableOnly = current.biddableOnly,
        )
        _state.update {
            it.copy(
                health = health,
                filters = filters,
                regions = regionData?.items ?: it.regions,
                landCategories = regionData?.landCategories ?: it.landCategories,
                listings = response.items,
                totalMatched = response.totalMatched,
            )
        }
    }

    /** 목록만 다시 가져온다. 조건·정렬을 바꿀 때 쓴다. */
    private fun reloadListings() = launchGuarded { fetchListings() }

    /**
     * 목록을 가져와 상태에 넣는다.
     *
     * launchGuarded 를 걸지 않은 순수 suspend 함수다. 다른 작업 뒤에 이어
     * 부를 때 launchGuarded 안에서 또 launchGuarded 를 부르면, 바깥이 먼저
     * 끝나 loading 이 꺼지고 안쪽 실패가 묻힌다.
     */
    private suspend fun fetchListings() {
        val current = _state.value
        val response = api.listings(
            filterId = current.selectedFilterId,
            applyFilters = current.applyFilters,
            sort = current.sort,
            biddableOnly = current.biddableOnly,
            favoritesOnly = current.favoritesOnly,
        )
        _state.update {
            it.copy(listings = response.items, totalMatched = response.totalMatched,
                    lastCollectedAt = response.lastCollectedAt)
        }
    }

    /** 관심 물건 담기·빼기. 화면은 바로 바꾸고 서버에 따라 보낸다. */
    fun toggleFavorite(listing: Listing) {
        val key = listing.dedupeKey ?: (listing.source + ":" + listing.sourceId)
        val on = !listing.favorite
        // 먼저 화면을 바꾼다. 별을 눌렀는데 한 박자 늦게 켜지면 안 눌린 줄 안다.
        _state.update { st ->
            st.copy(listings = st.listings.map {
                if ((it.dedupeKey ?: (it.source + ":" + it.sourceId)) == key)
                    it.copy(favorite = on) else it
            })
        }
        viewModelScope.launch {
            runCatching { api.setFavorite(key, on) }.onFailure { e ->
                // 실패하면 화면을 되돌린다. 담긴 줄 알고 넘어가면 잃어버린다.
                _state.update { st ->
                    st.copy(
                        listings = st.listings.map {
                            if ((it.dedupeKey ?: (it.source + ":" + it.sourceId)) == key)
                                it.copy(favorite = !on) else it
                        },
                        error = "관심 물건 저장 실패: " + (e.message ?: ""),
                    )
                }
            }
        }
    }

    /** 최근 본 물건 보기. 기기에 남은 기록이라 서버를 부르지 않는다. */
    fun setRecentOnly(on: Boolean) {
        _state.update { it.copy(recentOnly = on) }
        if (on) showRecent() else reloadListings()
    }

    private fun showRecent() = launchGuarded {
        val keys = prefs.recentKeys
        if (keys.isEmpty()) {
            _state.update { it.copy(listings = emptyList(), totalMatched = 0) }
            return@launchGuarded
        }
        // 최근 본 것은 조건 밖일 수 있으므로 조건 없이 받아서 골라낸다.
        val all = api.listings(limit = 500, applyFilters = false).items
        val byKey = all.associateBy { it.dedupeKey ?: (it.source + ":" + it.sourceId) }
        val picked = keys.mapNotNull { byKey[it] }
        _state.update { it.copy(listings = picked, totalMatched = picked.size) }
    }

    fun setFavoritesOnly(on: Boolean) {
        _state.update { it.copy(favoritesOnly = on, applyFilters = !on || it.applyFilters) }
        reloadListings()
    }

    fun setBiddableOnly(on: Boolean) {
        _state.update { it.copy(biddableOnly = on) }
        reloadListings()
    }

    fun selectFilter(id: Int?) {
        _state.update { it.copy(selectedFilterId = id, applyFilters = true) }
        reloadListings()
    }

    fun showAllListings() {
        _state.update { it.copy(selectedFilterId = null, applyFilters = false) }
        reloadListings()
    }

    fun setSort(sort: String) {
        _state.update { it.copy(sort = sort) }
        reloadListings()
    }

    fun updateBorrower(profile: BorrowerProfile) {
        prefs.borrower = profile
        _state.update { it.copy(borrower = profile) }
    }

    fun calculatePlan(
        priceKrw: Long,
        areaSqm: Double,
        isRegulated: Boolean,
        isAuction: Boolean,
        holdYears: Double,
        sellOptions: List<Long>,
    ) = launchGuarded {
        val response = api.plan(
            PlanRequest(
                profile = _state.value.borrower,
                priceKrw = priceKrw,
                exclusiveAreaSqm = areaSqm,
                isRegulatedArea = isRegulated,
                isAuction = isAuction,
                holdYears = holdYears,
                sellPriceOptionsKrw = sellOptions,
            )
        )
        _state.update { it.copy(plan = response) }
    }

    /** 물건 카드에서 바로 "이거 살 수 있나" 를 계산한다. */
    fun planForListing(listing: Listing, holdYears: Double = 5.0) {
        val price = listing.effectivePriceKrw ?: return
        // 매도 가정은 예측하지 않는다. 시세를 알면 그 값을, 모르면 매수가를 쓴다.
        val reference = listing.marketPriceKrw ?: price
        calculatePlan(
            priceKrw = price,
            areaSqm = listing.exclusiveAreaSqm ?: 84.9,
            isRegulated = false,
            isAuction = listing.source == "onbid" || listing.source == "court",
            holdYears = holdYears,
            sellOptions = listOf(price, reference),
        )
    }

    /** 법원경매 물건을 손으로 추가한다. 넣고 나면 목록을 다시 읽어 바로 보인다. */
    fun addManualListing(item: ManualCourtListing) = launchGuarded {
        api.addManualListing(item)
        fetchListings()
    }

    fun deleteManualListing(dedupeKey: String) = launchGuarded {
        api.deleteManualListing(dedupeKey)
        fetchListings()
    }

    fun saveFilter(filter: FilterProfile) = launchGuarded {
        api.saveFilter(filter)
        _state.update { it.copy(filters = api.filters()) }
        // 조건을 바꿨는데 목록이 그대로면 적용됐는지 알 수 없다.
        reloadListings()
    }

    fun deleteFilter(id: Int) = launchGuarded {
        api.deleteFilter(id)
        val remaining = api.filters()
        _state.update {
            it.copy(
                filters = remaining,
                selectedFilterId = if (it.selectedFilterId == id) null else it.selectedFilterId,
            )
        }
        reloadListings()
    }

    fun triggerServerRefresh() = launchGuarded {
        api.refresh()
        val current = _state.value
        val response = api.listings(
            filterId = current.selectedFilterId,
            applyFilters = current.applyFilters,
            sort = current.sort,
            biddableOnly = current.biddableOnly,
        )
        _state.update {
            it.copy(
                listings = response.items,
                totalMatched = response.totalMatched,
                health = api.health(),
            )
        }
    }

    // ---------------------------------------------------------- 인앱 업데이트

    fun checkUpdate() {
        viewModelScope.launch {
            _state.update { it.copy(update = Updater.State.Checking) }
            _state.update { it.copy(update = updater.check()) }
        }
    }

    fun downloadUpdate() {
        val available = _state.value.update as? Updater.State.Available ?: return
        viewModelScope.launch {
            val result = updater.download(available.info) { percent ->
                _state.update {
                    it.copy(update = Updater.State.Downloading(percent, available.info))
                }
            }
            // 권한이 없으면 설치 화면을 띄워봐야 튕긴다. 먼저 물어보게 상태를 바꾼다.
            val next = if (result is Updater.State.ReadyToInstall && !updater.canInstall()) {
                Updater.State.NeedsPermission(result.file, result.info)
            } else {
                result
            }
            _state.update { it.copy(update = next) }
        }
    }

    fun installUpdate(file: File) = updater.install(file)

    fun openInstallPermission() = updater.openInstallPermissionSettings()

    /** 권한 설정에서 돌아왔을 때 다시 판정한다. */
    fun recheckInstallPermission() {
        val pending = _state.value.update as? Updater.State.NeedsPermission ?: return
        if (updater.canInstall()) {
            _state.update {
                it.copy(update = Updater.State.ReadyToInstall(pending.file, pending.info))
            }
        }
    }

    // ---------------------------------------------------------- 알림

    fun setNotificationsEnabled(enabled: Boolean) {
        prefs.notificationsEnabled = enabled
        _state.update { it.copy(notificationsEnabled = enabled) }
        val app = getApplication<Application>()
        if (enabled && prefs.isConfigured) {
            ListingWorker.schedule(app, prefs.notifyHour)
        } else {
            ListingWorker.cancel(app)
        }
    }

    fun setNotifyHour(hour: Int) {
        prefs.notifyHour = hour
        _state.update { it.copy(notifyHour = prefs.notifyHour) }
        if (prefs.notificationsEnabled && prefs.isConfigured) {
            ListingWorker.schedule(getApplication(), prefs.notifyHour)
        }
    }

    fun refreshNotificationPermission() {
        _state.update { it.copy(notificationPermission = Notifier(getApplication()).canPost()) }
    }

    /** 지금 한 번 확인해서 알림을 띄운다. 설정이 제대로 됐는지 눈으로 보는 용도. */
    fun testNotificationNow() = launchGuarded {
        val app = getApplication<Application>()
        val notifier = Notifier(app)
        if (!notifier.canPost()) {
            _state.update { it.copy(lastNotifyResult = "알림 권한이 꺼져 있다") }
            return@launchGuarded
        }
        if (!prefs.notificationBaselineDone) {
            val n = api.baselineNotifications()
            prefs.notificationBaselineDone = true
            _state.update {
                it.copy(lastNotifyResult = "기준선 설정: 기존 ${n}건은 알리지 않는다. 이후 새 물건부터 알림")
            }
            return@launchGuarded
        }
        val pending = api.notifications()
        val posted = notifier.notifyListings(pending)
        if (posted > 0) api.ackNotifications(pending.mapNotNull { it.dedupeKey })
        _state.update {
            it.copy(
                lastNotifyResult = if (pending.isEmpty()) "새 물건 없음"
                else "새 물건 ${pending.size}건 알림",
            )
        }
    }

    // ---------------------------------------------------------- 물건 상세

    fun openDetail(listing: Listing) {
        // 상세를 연 것이 '봤다'의 기준이다. 목록을 스크롤만 한 것은 아니다.
        prefs.pushRecent(listing.dedupeKey ?: (listing.source + ":" + listing.sourceId))
        val key = listing.dedupeKey ?: (listing.source + ":" + listing.sourceId)
        if (_state.value.detailKey == key) {
            // 같은 카드를 다시 누르면 접는다.
            _state.update { it.copy(detailKey = null, detail = null, detailPlan = null) }
            return
        }
        _state.update {
            it.copy(detailKey = key, detail = null, detailPlan = null, detailLoading = true)
        }
        // 자금계획을 그 자리에서 함께 계산한다. 탭을 옮기면 어느 물건을
        // 보고 있었는지가 끊긴다.
        viewModelScope.launch {
            val price = listing.effectivePriceKrw
            if (price != null && price > 0) {
                runCatching {
                    api.plan(PlanRequest(
                        profile = _state.value.borrower,
                        priceKrw = price,
                        exclusiveAreaSqm = listing.exclusiveAreaSqm ?: 84.9,
                        isAuction = listing.source == "onbid" || listing.source == "court",
                    ))
                }.onSuccess { r ->
                    // 그 사이 다른 물건을 폈으면 덮어쓰지 않는다.
                    _state.update {
                        if (it.detailKey == key) it.copy(detailPlan = r) else it
                    }
                }
            }
        }
        viewModelScope.launch {
            runCatching { api.detail(key).detail }
                .onSuccess { d -> _state.update { it.copy(detail = d, detailLoading = false) } }
                .onFailure { e ->
                    _state.update {
                        it.copy(detailLoading = false, error = e.message ?: "상세 조회 실패")
                    }
                }
        }
    }

    fun dismissError() = _state.update { it.copy(error = null) }
}
