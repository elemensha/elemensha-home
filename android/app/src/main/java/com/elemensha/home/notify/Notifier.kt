package com.elemensha.home.notify

import android.app.NotificationChannel
import android.app.NotificationManager
import android.app.PendingIntent
import android.content.Context
import android.content.Intent
import android.content.pm.PackageManager
import android.os.Build
import androidx.core.app.NotificationCompat
import androidx.core.app.NotificationManagerCompat
import androidx.core.content.ContextCompat
import androidx.core.net.toUri
import com.elemensha.home.MainActivity
import com.elemensha.home.data.Listing
import kotlin.math.abs

/**
 * 새 물건 알림.
 *
 * 물건 하나에 알림 하나씩 띄우되, 한 번에 여러 건이 들어오면 요약 하나로 묶는다.
 * 서버를 처음 붙였을 때는 쌓여 있던 수백 건이 한꺼번에 미알림 상태라,
 * 그대로 띄우면 알림창이 도배된다.
 */
class Notifier(private val context: Context) {

    fun ensureChannel() {
        if (Build.VERSION.SDK_INT < Build.VERSION_CODES.O) return
        val channel = NotificationChannel(
            CHANNEL_ID,
            "새 물건",
            NotificationManager.IMPORTANCE_DEFAULT,
        ).apply {
            description = "조건에 맞는 공매·급매 물건이 올라오면 알린다"
        }
        context.getSystemService(NotificationManager::class.java)
            ?.createNotificationChannel(channel)
    }

    fun canPost(): Boolean {
        if (Build.VERSION.SDK_INT < Build.VERSION_CODES.TIRAMISU) return true
        return ContextCompat.checkSelfPermission(
            context, android.Manifest.permission.POST_NOTIFICATIONS,
        ) == PackageManager.PERMISSION_GRANTED
    }

    /** 실제로 띄운 알림 수. 권한이 없으면 0. */
    fun notifyListings(listings: List<Listing>): Int {
        if (listings.isEmpty() || !canPost()) return 0
        ensureChannel()
        val manager = NotificationManagerCompat.from(context)

        if (listings.size > INDIVIDUAL_LIMIT) {
            manager.notify(SUMMARY_ID, buildSummary(listings))
            return 1
        }

        listings.forEach { listing ->
            manager.notify(idFor(listing), buildOne(listing))
        }
        return listings.size
    }

    private fun buildOne(listing: Listing): android.app.Notification {
        val price = formatShort(listing.effectivePriceKrw)
        val detail = buildString {
            append(listing.sido).append(' ').append(listing.sigungu)
            append(" · ").append(listing.propertyType)
            listing.discountRatio?.let {
                append(" · 감정가 대비 -").append((it * 100).toInt()).append('%')
            }
            if (listing.failedBidCount > 0) {
                append(" · 유찰 ").append(listing.failedBidCount).append("회")
            }
        }

        // 알림을 누르면 물건 원문으로 바로 간다. 링크가 없으면 앱을 연다.
        val intent = if (listing.url.isNotBlank()) {
            Intent(Intent.ACTION_VIEW, listing.url.toUri())
        } else {
            Intent(context, MainActivity::class.java)
        }.addFlags(Intent.FLAG_ACTIVITY_NEW_TASK)

        return NotificationCompat.Builder(context, CHANNEL_ID)
            .setSmallIcon(android.R.drawable.ic_menu_search)
            .setContentTitle("$price · ${listing.title.take(40)}")
            .setContentText(detail)
            .setStyle(NotificationCompat.BigTextStyle().bigText("${listing.title}\n$detail"))
            .setAutoCancel(true)
            .setContentIntent(
                PendingIntent.getActivity(
                    context, idFor(listing), intent,
                    PendingIntent.FLAG_IMMUTABLE or PendingIntent.FLAG_UPDATE_CURRENT,
                )
            )
            .build()
    }

    private fun buildSummary(listings: List<Listing>): android.app.Notification {
        val lines = listings.take(6).map {
            "${formatShort(it.effectivePriceKrw)} · ${it.title.take(34)}"
        }
        val style = NotificationCompat.InboxStyle()
        lines.forEach(style::addLine)
        if (listings.size > lines.size) {
            style.setSummaryText("외 ${listings.size - lines.size}건")
        }

        val intent = Intent(context, MainActivity::class.java)
            .addFlags(Intent.FLAG_ACTIVITY_NEW_TASK)

        return NotificationCompat.Builder(context, CHANNEL_ID)
            .setSmallIcon(android.R.drawable.ic_menu_search)
            .setContentTitle("조건에 맞는 새 물건 ${listings.size}건")
            .setContentText(lines.firstOrNull().orEmpty())
            .setStyle(style)
            .setAutoCancel(true)
            .setContentIntent(
                PendingIntent.getActivity(
                    context, SUMMARY_ID, intent,
                    PendingIntent.FLAG_IMMUTABLE or PendingIntent.FLAG_UPDATE_CURRENT,
                )
            )
            .build()
    }

    /** '4억 4,520만' 처럼 짧게. 알림 제목은 자리가 좁다. */
    private fun formatShort(amount: Long?): String {
        if (amount == null || amount <= 0) return "가격 미상"
        val eok = amount / 100_000_000
        val man = (amount % 100_000_000) / 10_000
        return when {
            eok > 0 && man > 0 -> "%d억 %,d만".format(eok, man)
            eok > 0 -> "%d억".format(eok)
            else -> "%,d만".format(man)
        }
    }

    private fun idFor(listing: Listing): Int =
        abs((listing.source + listing.sourceId).hashCode())

    private companion object {
        const val CHANNEL_ID = "new_listings"
        const val SUMMARY_ID = 1
        // 이보다 많으면 개별 알림 대신 요약 하나로 묶는다.
        const val INDIVIDUAL_LIMIT = 5
    }
}
