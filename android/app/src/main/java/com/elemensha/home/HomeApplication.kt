package com.elemensha.home

import android.app.Application
import com.elemensha.home.data.Prefs
import com.elemensha.home.notify.Notifier
import com.elemensha.home.work.ListingWorker

/**
 * 앱이 뜰 때 알림 채널을 만들고 폴링 워커를 예약한다.
 *
 * 워커 예약은 KEEP 정책이라 이미 걸려 있으면 그대로 둔다. 앱을 열 때마다
 * 새로 걸면 주기가 계속 초기화돼서 영영 돌지 않는다.
 */
class HomeApplication : Application() {
    override fun onCreate() {
        super.onCreate()
        Notifier(this).ensureChannel()
        val prefs = Prefs(this)
        if (prefs.isConfigured && prefs.notificationsEnabled) {
            ListingWorker.schedule(this, prefs.notifyHour)
        }
    }
}
