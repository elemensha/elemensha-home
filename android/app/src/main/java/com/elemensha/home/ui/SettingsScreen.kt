package com.elemensha.home.ui

import androidx.compose.foundation.layout.Arrangement
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.Spacer
import androidx.compose.foundation.layout.fillMaxWidth
import androidx.compose.foundation.layout.height
import androidx.compose.foundation.layout.padding
import androidx.compose.foundation.lazy.LazyColumn
import androidx.compose.material3.Button
import androidx.compose.material3.MaterialTheme
import androidx.compose.material3.OutlinedButton
import androidx.compose.material3.OutlinedTextField
import androidx.compose.material3.Text
import androidx.compose.runtime.Composable
import androidx.compose.runtime.getValue
import androidx.compose.runtime.mutableStateOf
import androidx.compose.runtime.remember
import androidx.compose.runtime.setValue
import androidx.compose.ui.Modifier
import androidx.compose.ui.text.input.PasswordVisualTransformation
import androidx.compose.ui.unit.dp
import androidx.compose.material3.LinearProgressIndicator
import com.elemensha.home.UiState
import com.elemensha.home.update.Updater
import java.io.File

@Composable
fun SettingsScreen(
    state: UiState,
    onSave: (String, String) -> Unit,
    onServerRefresh: () -> Unit,
    onCheckUpdate: () -> Unit,
    onDownloadUpdate: () -> Unit,
    onInstallUpdate: (File) -> Unit,
    onOpenInstallPermission: () -> Unit,
) {
    var url by remember { mutableStateOf(state.serverUrl) }
    var token by remember { mutableStateOf(state.apiToken) }

    LazyColumn(
        modifier = Modifier.fillMaxWidth().padding(horizontal = 16.dp),
        verticalArrangement = Arrangement.spacedBy(12.dp),
    ) {
        item { Spacer(Modifier.height(8.dp)) }

        item {
            SectionCard("서버 연결") {
                OutlinedTextField(
                    value = url,
                    onValueChange = { url = it },
                    label = { Text("서버 주소") },
                    placeholder = { Text("https://example.duckdns.org") },
                    singleLine = true,
                    modifier = Modifier.fillMaxWidth(),
                )
                Spacer(Modifier.height(8.dp))
                OutlinedTextField(
                    value = token,
                    onValueChange = { token = it },
                    label = { Text("API 토큰") },
                    supportingText = {
                        Text("서버 .env의 HOME_API_TOKEN. 비우면 누구나 내 소득 정보를 읽을 수 있다")
                    },
                    visualTransformation = PasswordVisualTransformation(),
                    singleLine = true,
                    modifier = Modifier.fillMaxWidth(),
                )
                Spacer(Modifier.height(12.dp))
                Button(
                    onClick = { onSave(url, token) },
                    modifier = Modifier.fillMaxWidth(),
                ) { Text("저장하고 연결") }
            }
        }

        state.health?.let { health ->
            item {
                SectionCard("서버 상태") {
                    KeyValue("규제 기준일", health.rulesetVersion)
                    KeyValue(
                        "출처 검증률",
                        "${health.sourceCoverage.verified} / ${health.sourceCoverage.total}",
                    )
                    if (health.sourceCoverage.verified < health.sourceCoverage.total) {
                        Text(
                            "검증되지 않은 파라미터로 계산 중이다. 결과를 실제 규정과 " +
                                "대조하기 전에는 참고용으로만 볼 것.",
                            style = MaterialTheme.typography.bodySmall,
                            color = WarningAmber,
                        )
                    }
                    if (!health.authEnabled) {
                        Text(
                            "서버에 인증이 걸려 있지 않다. HOME_API_TOKEN을 설정할 것.",
                            style = MaterialTheme.typography.bodySmall,
                            color = MaterialTheme.colorScheme.error,
                        )
                    }

                    Spacer(Modifier.height(8.dp))
                    Text("데이터 소스", style = MaterialTheme.typography.labelLarge)
                    health.sourcesConfigured.forEach { (name, configured) ->
                        KeyValue(name, if (configured) "키 설정됨" else "키 없음")
                    }

                    if (health.pollStatus.isNotEmpty()) {
                        Spacer(Modifier.height(8.dp))
                        Text("마지막 수집", style = MaterialTheme.typography.labelLarge)
                        health.pollStatus.forEach { poll ->
                            KeyValue(
                                poll.source,
                                if (poll.ok) "${poll.fetched}건 · 신규 ${poll.newCount}"
                                else "실패 · ${poll.error ?: "원인 미상"}",
                            )
                        }
                    }

                    Spacer(Modifier.height(12.dp))
                    OutlinedButton(
                        onClick = onServerRefresh,
                        enabled = !state.loading,
                        modifier = Modifier.fillMaxWidth(),
                    ) { Text("지금 수집") }
                }
            }
        }

        item {
            SectionCard("앱 업데이트") {
                KeyValue("현재 버전", state.appVersion)
                Spacer(Modifier.height(8.dp))

                when (val u = state.update) {
                    is Updater.State.Idle -> {
                        Button(onClick = onCheckUpdate, modifier = Modifier.fillMaxWidth()) {
                            Text("업데이트 확인")
                        }
                    }
                    is Updater.State.Checking -> {
                        Text("확인 중...", style = MaterialTheme.typography.bodyMedium)
                    }
                    is Updater.State.UpToDate -> {
                        Text("최신 버전입니다 (${u.current})",
                            style = MaterialTheme.typography.bodyMedium, color = VerifiedGreen)
                        Spacer(Modifier.height(8.dp))
                        OutlinedButton(onClick = onCheckUpdate, modifier = Modifier.fillMaxWidth()) {
                            Text("다시 확인")
                        }
                    }
                    is Updater.State.Available -> {
                        Text("새 버전 ${u.info.versionName}",
                            style = MaterialTheme.typography.titleSmall)
                        if (u.info.notes.isNotBlank()) {
                            Text(u.info.notes.take(300),
                                style = MaterialTheme.typography.bodySmall,
                                color = MaterialTheme.colorScheme.onSurfaceVariant)
                        }
                        Spacer(Modifier.height(8.dp))
                        Button(onClick = onDownloadUpdate, modifier = Modifier.fillMaxWidth()) {
                            Text("내려받기")
                        }
                    }
                    is Updater.State.Downloading -> {
                        Text("내려받는 중 ${u.percent}%",
                            style = MaterialTheme.typography.bodyMedium)
                        Spacer(Modifier.height(6.dp))
                        LinearProgressIndicator(
                            progress = { u.percent / 100f },
                            modifier = Modifier.fillMaxWidth(),
                        )
                    }
                    is Updater.State.ReadyToInstall -> {
                        Text("받기 완료 — 설치하면 앱이 잠시 닫힙니다.",
                            style = MaterialTheme.typography.bodyMedium)
                        Spacer(Modifier.height(8.dp))
                        Button(onClick = { onInstallUpdate(u.file) },
                            modifier = Modifier.fillMaxWidth()) {
                            Text("설치")
                        }
                    }
                    is Updater.State.NeedsPermission -> {
                        Text("'알 수 없는 앱 설치'를 켜야 설치할 수 있습니다. " +
                            "설정에서 허용한 뒤 이 화면으로 돌아오세요.",
                            style = MaterialTheme.typography.bodySmall, color = WarningAmber)
                        Spacer(Modifier.height(8.dp))
                        Button(onClick = onOpenInstallPermission,
                            modifier = Modifier.fillMaxWidth()) {
                            Text("권한 설정 열기")
                        }
                    }
                    is Updater.State.Failed -> {
                        Text(u.message, style = MaterialTheme.typography.bodySmall,
                            color = MaterialTheme.colorScheme.error)
                        Spacer(Modifier.height(8.dp))
                        OutlinedButton(onClick = onCheckUpdate, modifier = Modifier.fillMaxWidth()) {
                            Text("다시 시도")
                        }
                    }
                }
            }
        }

        item {
            SectionCard("이 앱이 하지 않는 것") {
                Column {
                    Text(
                        "집값을 예측하지 않는다. 매도 시나리오의 가격은 전부 입력한 " +
                            "가정이거나 과거 실거래 범위에서 뽑은 값이다.",
                        style = MaterialTheme.typography.bodySmall,
                    )
                    Spacer(Modifier.height(6.dp))
                    Text(
                        "투자 판단을 대신하지 않는다. 어떤 물건이 좋은지 순위를 매기지 " +
                            "않고, 조건에 맞는 것을 걸러 계산 결과만 보여준다.",
                        style = MaterialTheme.typography.bodySmall,
                    )
                    Spacer(Modifier.height(6.dp))
                    Text(
                        "세무·법률 자문이 아니다. 대출 한도는 은행 심사에서, 세액은 " +
                            "신고 시점 세법과 개인 사정에 따라 달라진다.",
                        style = MaterialTheme.typography.bodySmall,
                    )
                }
            }
        }

        item { Spacer(Modifier.height(24.dp)) }
    }
}
