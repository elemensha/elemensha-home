package com.elemensha.home.ui

import android.annotation.SuppressLint
import android.net.Uri
import android.view.ViewGroup
import android.webkit.WebView
import android.webkit.WebViewClient
import androidx.compose.foundation.layout.Box
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.fillMaxSize
import androidx.compose.foundation.layout.fillMaxWidth
import androidx.compose.foundation.layout.padding
import androidx.compose.material3.MaterialTheme
import androidx.compose.material3.Text
import androidx.compose.runtime.Composable
import androidx.compose.runtime.getValue
import androidx.compose.runtime.mutableStateOf
import androidx.compose.runtime.remember
import androidx.compose.runtime.setValue
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.unit.dp
import androidx.compose.ui.viewinterop.AndroidView
import com.elemensha.home.UiState

/**
 * 서버가 그린 지도 페이지를 그대로 띄운다.
 *
 * 네이티브 지도 SDK 대신 WebView 를 쓰는 이유는 화면을 한 번만 만들기
 * 위해서다. 같은 주소를 PC 브라우저로 열면 똑같은 지도가 나온다.
 *
 * 토큰은 URL 이 아니라 헤더로 보낸다. 쿼리에 넣으면 서버 접근 로그와
 * WebView 방문 기록에 토큰이 남는다.
 */
@SuppressLint("SetJavaScriptEnabled")
@Composable
fun MapScreen(state: UiState) {
    if (!state.isConfigured) {
        Box(Modifier.fillMaxSize(), contentAlignment = Alignment.Center) {
            Text(
                "설정에서 서버를 먼저 연결하세요.",
                style = MaterialTheme.typography.bodyMedium,
                color = MaterialTheme.colorScheme.onSurfaceVariant,
            )
        }
        return
    }

    val base = state.serverUrl.trimEnd('/')
    val url = "$base/map"
    val headers = if (state.apiToken.isBlank()) emptyMap()
                  else mapOf("Authorization" to "Bearer ${state.apiToken}")
    // 이미 읽은 주소. WebView 를 불필요하게 다시 읽지 않으려고 들고 있다.
    var loaded by remember { mutableStateOf("") }
    // 이 호스트만 WebView 안에서 연다. 나머지는 바깥 브라우저로 보낸다.
    val serverHost = remember(base) { runCatching { Uri.parse(base).host }.getOrNull() }

    Column(Modifier.fillMaxSize()) {
        AndroidView(
            modifier = Modifier.fillMaxSize(),
            factory = { context ->
                WebView(context).apply {
                    layoutParams = ViewGroup.LayoutParams(
                        ViewGroup.LayoutParams.MATCH_PARENT,
                        ViewGroup.LayoutParams.MATCH_PARENT,
                    )
                    settings.javaScriptEnabled = true
                    // 네이버 지도 타일이 여러 호스트에서 온다.
                    settings.domStorageEnabled = true
                    settings.loadWithOverviewMode = true
                    settings.useWideViewPort = true
                    // 이 WebView 는 우리 지도 페이지만 띄운다. 바깥으로 나가는
                    // 링크는 전부 밖에서 연다.
                    //
                    // onbid 만 내보냈더니 네이버 지도 링크가 WebView 안에서
                    // 열렸고, 네이버가 앱 실행 스킴(intent://)으로 넘기는 것을
                    // WebView 가 못 열어 "웹페이지를 사용할 수 없음"이 떴다.
                    webViewClient = object : WebViewClient() {
                        override fun shouldOverrideUrlLoading(
                            view: WebView?, request: android.webkit.WebResourceRequest?,
                        ): Boolean {
                            val target = request?.url ?: return false
                            val scheme = target.scheme?.lowercase()
                            val isWeb = scheme == "http" || scheme == "https"
                            // 우리 서버 페이지는 그대로 WebView 안에서 돈다.
                            if (isWeb && target.host != null && target.host == serverHost) {
                                return false
                            }
                            val ctx = view?.context ?: return false
                            return openExternalLink(ctx, target.toString())
                        }
                    }
                    loadUrl(url, headers)
                    loaded = url
                }
            },
            update = { view ->
                // 주소가 바뀔 때만 다시 읽는다. 재구성마다 loadUrl 을 부르면
                // 확대해 둔 지도가 매번 전국 화면으로 되돌아간다.
                if (loaded != url) {
                    view.loadUrl(url, headers)
                    loaded = url
                }
            },
        )

        state.error?.let { message ->
            Text(
                message,
                style = MaterialTheme.typography.bodySmall,
                color = MaterialTheme.colorScheme.error,
                modifier = Modifier.fillMaxWidth().padding(12.dp),
            )
        }
    }
}
