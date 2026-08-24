package com.elemensha.home

import android.app.Application
import androidx.lifecycle.AndroidViewModel
import androidx.lifecycle.viewModelScope
import com.elemensha.home.data.Api
import com.elemensha.home.data.BorrowerProfile
import com.elemensha.home.data.FilterProfile
import com.elemensha.home.data.HealthResponse
import com.elemensha.home.data.Listing
import com.elemensha.home.data.PlanRequest
import com.elemensha.home.data.PlanResponse
import com.elemensha.home.data.Prefs
import com.elemensha.home.update.Updater
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
    val filters: List<FilterProfile> = emptyList(),
    val borrower: BorrowerProfile = BorrowerProfile(),
    val plan: PlanResponse? = null,
    val update: Updater.State = Updater.State.Idle,
    val appVersion: String = "",
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
        refresh()
    }

    fun refresh() = launchGuarded {
        val health = api.health()
        val listings = api.listings()
        val filters = api.filters()
        _state.update { it.copy(health = health, listings = listings, filters = filters) }
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

    fun saveFilter(filter: FilterProfile) = launchGuarded {
        api.saveFilter(filter)
        _state.update { it.copy(filters = api.filters()) }
    }

    fun deleteFilter(id: Int) = launchGuarded {
        api.deleteFilter(id)
        _state.update { it.copy(filters = api.filters()) }
    }

    fun triggerServerRefresh() = launchGuarded {
        api.refresh()
        _state.update { it.copy(listings = api.listings(), health = api.health()) }
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

    fun dismissError() = _state.update { it.copy(error = null) }
}
