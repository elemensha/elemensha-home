package com.elemensha.home

import android.os.Bundle
import androidx.activity.ComponentActivity
import android.Manifest
import android.os.Build
import androidx.activity.compose.rememberLauncherForActivityResult
import androidx.activity.compose.setContent
import androidx.activity.result.contract.ActivityResultContracts
import androidx.activity.enableEdgeToEdge
import androidx.activity.viewModels
import androidx.compose.foundation.layout.Box
import androidx.compose.foundation.layout.fillMaxSize
import androidx.compose.foundation.layout.padding
import androidx.compose.material.icons.Icons
import androidx.compose.material.icons.filled.Calculate
import androidx.compose.material.icons.filled.Home
import androidx.compose.material.icons.filled.Settings
import androidx.compose.material.icons.filled.Tune
import androidx.compose.material3.Icon
import androidx.compose.material3.NavigationBar
import androidx.compose.material3.NavigationBarItem
import androidx.compose.material3.Scaffold
import androidx.compose.material3.SnackbarHost
import androidx.compose.material3.SnackbarHostState
import androidx.compose.material3.Text
import androidx.compose.runtime.Composable
import androidx.compose.runtime.LaunchedEffect
import androidx.compose.runtime.getValue
import androidx.compose.runtime.mutableStateOf
import androidx.compose.runtime.remember
import androidx.compose.runtime.setValue
import androidx.compose.ui.Modifier
import androidx.compose.ui.graphics.vector.ImageVector
import androidx.lifecycle.compose.collectAsStateWithLifecycle
import com.elemensha.home.ui.FiltersScreen
import com.elemensha.home.ui.HomeTheme
import com.elemensha.home.ui.ListingsScreen
import com.elemensha.home.ui.PlanScreen
import com.elemensha.home.ui.SettingsScreen

private enum class Tab(val label: String, val icon: ImageVector) {
    LISTINGS("물건", Icons.Filled.Home),
    PLAN("자금계획", Icons.Filled.Calculate),
    FILTERS("조건", Icons.Filled.Tune),
    SETTINGS("설정", Icons.Filled.Settings),
}

class MainActivity : ComponentActivity() {

    private val viewModel: AppViewModel by viewModels()

    override fun onResume() {
        super.onResume()
        // '알 수 없는 앱 설치'를 켜고 돌아온 경우를 잡는다.
        viewModel.recheckInstallPermission()
        viewModel.refreshNotificationPermission()
    }

    override fun onCreate(savedInstanceState: Bundle?) {
        super.onCreate(savedInstanceState)
        enableEdgeToEdge()
        setContent {
            HomeTheme {
                AppScaffold(viewModel)
            }
        }
    }
}

@Composable
private fun AppScaffold(viewModel: AppViewModel) {
    val state by viewModel.state.collectAsStateWithLifecycle()
    // 서버가 아직 없으면 설정부터 보여준다. 빈 목록만 띄우면 왜 비었는지 모른다.
    var tab by remember { mutableStateOf(if (state.isConfigured) Tab.LISTINGS else Tab.SETTINGS) }
    val snackbar = remember { SnackbarHostState() }

    // Android 13+ 는 알림 권한을 사용자가 허용해야 한다. 없으면 워커가
    // 돌아도 아무것도 안 뜨는데, 그 사실이 화면에 드러나지 않으면
    // "알림이 안 온다"로만 보인다.
    val permissionLauncher = rememberLauncherForActivityResult(
        ActivityResultContracts.RequestPermission()
    ) { viewModel.refreshNotificationPermission() }

    LaunchedEffect(Unit) {
        if (Build.VERSION.SDK_INT >= Build.VERSION_CODES.TIRAMISU &&
            !state.notificationPermission
        ) {
            permissionLauncher.launch(Manifest.permission.POST_NOTIFICATIONS)
        }
    }

    LaunchedEffect(state.error) {
        state.error?.let {
            snackbar.showSnackbar(it)
            viewModel.dismissError()
        }
    }

    Scaffold(
        snackbarHost = { SnackbarHost(snackbar) },
        bottomBar = {
            NavigationBar {
                Tab.entries.forEach { entry ->
                    NavigationBarItem(
                        selected = tab == entry,
                        onClick = { tab = entry },
                        icon = { Icon(entry.icon, contentDescription = entry.label) },
                        label = { Text(entry.label) },
                    )
                }
            }
        },
    ) { padding ->
        Box(Modifier.fillMaxSize().padding(padding)) {
            when (tab) {
                Tab.LISTINGS -> ListingsScreen(
                    state = state,
                    onRefresh = viewModel::refresh,
                    onPlanForListing = { listing ->
                        viewModel.planForListing(listing)
                        tab = Tab.PLAN
                    },
                    onSelectFilter = viewModel::selectFilter,
                    onShowAll = viewModel::showAllListings,
                    onSort = viewModel::setSort,
                    onOpenDetail = viewModel::openDetail,
                )
                Tab.PLAN -> PlanScreen(
                    state = state,
                    onBorrowerChange = viewModel::updateBorrower,
                    onCalculate = viewModel::calculatePlan,
                )
                Tab.FILTERS -> FiltersScreen(
                    state = state,
                    onSave = viewModel::saveFilter,
                    onDelete = viewModel::deleteFilter,
                )
                Tab.SETTINGS -> SettingsScreen(
                    state = state,
                    onSave = viewModel::saveConnection,
                    onServerRefresh = viewModel::triggerServerRefresh,
                    onCheckUpdate = viewModel::checkUpdate,
                    onDownloadUpdate = viewModel::downloadUpdate,
                    onInstallUpdate = viewModel::installUpdate,
                    onOpenInstallPermission = viewModel::openInstallPermission,
                    onToggleNotifications = viewModel::setNotificationsEnabled,
                    onTestNotification = viewModel::testNotificationNow,
                    onRequestNotificationPermission = {
                        if (Build.VERSION.SDK_INT >= Build.VERSION_CODES.TIRAMISU) {
                            permissionLauncher.launch(Manifest.permission.POST_NOTIFICATIONS)
                        }
                    },
                )
            }
        }
    }
}
