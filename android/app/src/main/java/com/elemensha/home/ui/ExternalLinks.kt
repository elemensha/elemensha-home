package com.elemensha.home.ui

import android.content.ActivityNotFoundException
import android.content.Context
import android.content.Intent
import android.net.Uri

/** 온비드 안드로이드 앱. 물건 링크를 이 앱으로 넘겨 본다. */
private const val ONBID_PACKAGE = "net.ib.asp.android.kamco.mb"

/**
 * 링크를 앱 밖에서 연다. 온비드 링크는 온비드 앱을 먼저 시도한다.
 *
 * 온비드는 개편 뒤 물건 하나를 여는 GET 주소가 없다(상세가 POST 전용이고
 * 공유 URL 은 서버가 만드는 난수다). 그래서 세 단계로 물러난다:
 *
 *   1. 주소를 온비드 앱에 넘긴다 - 앱이 그 주소를 받도록 돼 있으면 바로 열린다
 *   2. 안 받으면 앱을 그냥 실행한다 - 물건관리번호를 복사해 뒀으니 앱에서 검색하면 된다
 *   3. 앱이 없으면 브라우저로 연다
 *
 * 1단계가 될지는 온비드 앱이 어떤 인텐트 필터를 걸어 뒀는지에 달렸고
 * 공개된 문서가 없다. 되면 좋고, 안 되면 2단계로 조용히 내려간다.
 */
fun openExternalLink(context: Context, url: String): Boolean {
    if (url.isBlank()) return false

    val uri = runCatching { Uri.parse(url) }.getOrNull() ?: return false
    val isOnbid = uri.host?.contains("onbid.co.kr") == true

    if (isOnbid) {
        // 1단계: 주소째로 온비드 앱에 넘긴다.
        if (start(context, Intent(Intent.ACTION_VIEW, uri).setPackage(ONBID_PACKAGE))) {
            return true
        }
        // 2단계: 앱만 띄운다.
        val launch = context.packageManager.getLaunchIntentForPackage(ONBID_PACKAGE)
        if (launch != null && start(context, launch)) return true
    }

    // intent:// 같은 앱 실행 스킴은 풀어서 넘겨야 열린다.
    if (url.startsWith("intent:")) {
        val parsed = runCatching {
            Intent.parseUri(url, Intent.URI_INTENT_SCHEME)
        }.getOrNull()
        if (parsed != null) {
            if (start(context, parsed)) return true
            val fallback = parsed.getStringExtra("browser_fallback_url")
            if (fallback != null) {
                return start(context, Intent(Intent.ACTION_VIEW, Uri.parse(fallback)))
            }
            return false
        }
    }

    // 3단계: 평범하게 연다(브라우저).
    return start(context, Intent(Intent.ACTION_VIEW, uri))
}

private fun start(context: Context, intent: Intent): Boolean = try {
    context.startActivity(intent.addFlags(Intent.FLAG_ACTIVITY_NEW_TASK))
    true
} catch (e: ActivityNotFoundException) {
    false
} catch (e: SecurityException) {
    // 앱이 외부 실행을 막아 둔 경우. 다음 단계로 넘어간다.
    false
}
