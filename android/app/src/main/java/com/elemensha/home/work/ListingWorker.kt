package com.elemensha.home.work

import android.content.Context
import androidx.work.Constraints
import androidx.work.CoroutineWorker
import androidx.work.ExistingPeriodicWorkPolicy
import androidx.work.NetworkType
import androidx.work.PeriodicWorkRequestBuilder
import androidx.work.WorkManager
import androidx.work.WorkerParameters
import com.elemensha.home.data.Api
import com.elemensha.home.data.Prefs
import com.elemensha.home.notify.Notifier
import java.util.concurrent.TimeUnit

/**
 * 주기적으로 서버에 새 물건이 있는지 묻고 알림을 띄운다.
 *
 * 수집은 서버가 이미 다 해두므로 앱은 짧은 요청 한 번만 보낸다. 배터리
 * 영향이 거의 없고, 기기가 자고 있으면 WorkManager 가 알아서 미룬다.
 *
 * 서버는 아직 알리지 않은 물건만 돌려주고, 앱이 확인(ack)을 보내면 다시
 * 주지 않는다. 알림을 띄우지 못했으면 ack 하지 않아 다음 주기에 다시 온다.
 */
class ListingWorker(
    context: Context,
    params: WorkerParameters,
) : CoroutineWorker(context, params) {

    override suspend fun doWork(): Result {
        val prefs = Prefs(applicationContext)
        if (!prefs.isConfigured || !prefs.notificationsEnabled) return Result.success()

        val api = Api(
            baseUrlProvider = { prefs.serverUrl },
            tokenProvider = { prefs.apiToken },
        )
        val notifier = Notifier(applicationContext)

        return try {
            // 처음 한 번은 그동안 쌓인 재고를 알림 대상에서 뺀다.
            // 안 그러면 과거 수천 건이 '새 물건'으로 쏟아진다.
            if (!prefs.notificationBaselineDone) {
                api.baselineNotifications()
                prefs.notificationBaselineDone = true
                return Result.success()
            }

            val pending = api.notifications()
            if (pending.isEmpty()) return Result.success()

            val posted = notifier.notifyListings(pending)
            if (posted > 0) {
                // 알림에 성공한 것만 확인 처리한다. 권한이 없어 못 띄웠으면
                // ack 하지 않아야 권한을 켠 뒤 다시 받을 수 있다.
                api.ackNotifications(pending.mapNotNull { it.dedupeKey })
            }
            Result.success()
        } catch (e: Exception) {
            // 서버가 잠깐 죽었거나 네트워크가 끊긴 경우. 다음 주기에 다시 온다.
            Result.retry()
        }
    }

    companion object {
        private const val NAME = "listing-poll"

        /**
         * 매일 `hour` 시에 확인하도록 예약한다.
         *
         * 첫 실행까지의 지연을 다음 `hour` 시까지로 잡고 24시간 주기를 건다.
         * 기기가 잠들어 있으면 WorkManager 가 깨어난 뒤로 미루므로 정각에
         * 딱 맞지는 않는다. 하루 한 번이면 그 정도로 충분하다.
         */
        fun schedule(context: Context, hour: Int = 7) {
            val now = java.time.ZonedDateTime.now()
            var next = now.withHour(hour.coerceIn(0, 23))
                .withMinute(0).withSecond(0).withNano(0)
            if (!next.isAfter(now)) next = next.plusDays(1)
            val delay = java.time.Duration.between(now, next).toMinutes()

            val request = PeriodicWorkRequestBuilder<ListingWorker>(1, TimeUnit.DAYS)
                .setInitialDelay(delay, TimeUnit.MINUTES)
                .setConstraints(
                    Constraints.Builder()
                        .setRequiredNetworkType(NetworkType.CONNECTED)
                        .build()
                )
                .build()

            // UPDATE: 시각을 바꾸면 다시 걸려야 한다. KEEP 이면 옛 시각이 남는다.
            WorkManager.getInstance(context).enqueueUniquePeriodicWork(
                NAME, ExistingPeriodicWorkPolicy.UPDATE, request,
            )
        }

        fun cancel(context: Context) {
            WorkManager.getInstance(context).cancelUniqueWork(NAME)
        }
    }
}
