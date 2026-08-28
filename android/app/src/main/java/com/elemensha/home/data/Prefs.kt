package com.elemensha.home.data

import android.content.Context
import android.content.SharedPreferences
import androidx.security.crypto.EncryptedSharedPreferences
import androidx.security.crypto.MasterKey
import kotlinx.serialization.json.Json

/**
 * 로컬 저장소.
 *
 * 여기 들어가는 건 서버 토큰과 **연소득·보유 현금**이다. 남이 보면 곤란한
 * 정보라 EncryptedSharedPreferences를 쓴다. 키스토어가 깨져서 복호화가
 * 실패하면(기기 초기화, 백업 복원 등) 평문 저장으로 내려가지 않고 저장소를
 * 비우고 다시 만든다 - 조용히 평문으로 떨어지는 게 더 나쁘다.
 */
class Prefs(context: Context) {

    private val json = Json { ignoreUnknownKeys = true; encodeDefaults = true }

    private val prefs: SharedPreferences = runCatching {
        val masterKey = MasterKey.Builder(context)
            .setKeyScheme(MasterKey.KeyScheme.AES256_GCM)
            .build()
        EncryptedSharedPreferences.create(
            context,
            FILE_NAME,
            masterKey,
            EncryptedSharedPreferences.PrefKeyEncryptionScheme.AES256_SIV,
            EncryptedSharedPreferences.PrefValueEncryptionScheme.AES256_GCM,
        ) as SharedPreferences
    }.getOrElse {
        // 복호화 불가: 손상된 파일을 지우고 빈 저장소로 재생성한다.
        context.deleteSharedPreferences(FILE_NAME)
        val masterKey = MasterKey.Builder(context)
            .setKeyScheme(MasterKey.KeyScheme.AES256_GCM)
            .build()
        EncryptedSharedPreferences.create(
            context,
            FILE_NAME,
            masterKey,
            EncryptedSharedPreferences.PrefKeyEncryptionScheme.AES256_SIV,
            EncryptedSharedPreferences.PrefValueEncryptionScheme.AES256_GCM,
        ) as SharedPreferences
    }

    var serverUrl: String
        get() = prefs.getString(KEY_SERVER, "").orEmpty()
        set(value) = prefs.edit().putString(KEY_SERVER, value.trim()).apply()

    var apiToken: String
        get() = prefs.getString(KEY_TOKEN, "").orEmpty()
        set(value) = prefs.edit().putString(KEY_TOKEN, value.trim()).apply()

    /** 차주 프로필. 서버에도 저장하지만 오프라인에서 화면을 그리려면 로컬에도 둔다. */
    var borrower: BorrowerProfile
        get() = prefs.getString(KEY_BORROWER, null)
            ?.let { runCatching { json.decodeFromString<BorrowerProfile>(it) }.getOrNull() }
            ?: BorrowerProfile()
        set(value) = prefs.edit()
            .putString(KEY_BORROWER, json.encodeToString(BorrowerProfile.serializer(), value))
            .apply()

    /** 이미 알림을 띄운 물건. 워커가 같은 걸 두 번 울리지 않게 한다. */
    var notifiedKeys: Set<String>
        get() = prefs.getStringSet(KEY_NOTIFIED, emptySet()).orEmpty()
        set(value) = prefs.edit()
            .putStringSet(KEY_NOTIFIED, value.take(MAX_NOTIFIED_KEYS).toSet())
            .apply()

    /** 백그라운드 알림 사용 여부. 기본 켜짐 - 알림이 이 앱의 존재 이유다. */
    var notificationsEnabled: Boolean
        get() = prefs.getBoolean(KEY_NOTIFY, true)
        set(value) = prefs.edit().putBoolean(KEY_NOTIFY, value).apply()

    /** 알림을 받을 시각(0~23시). 하루 한 번 이 시각에 확인한다. */
    var notifyHour: Int
        get() = prefs.getInt(KEY_NOTIFY_HOUR, 7)
        set(value) = prefs.edit().putInt(KEY_NOTIFY_HOUR, value.coerceIn(0, 23)).apply()

    /** 알림 기준선을 잡았는지. 한 번만 하면 된다. */
    var notificationBaselineDone: Boolean
        get() = prefs.getBoolean(KEY_BASELINE, false)
        set(value) = prefs.edit().putBoolean(KEY_BASELINE, value).apply()

    val isConfigured: Boolean get() = serverUrl.isNotBlank()

    fun clear() = prefs.edit().clear().apply()

    private companion object {
        const val FILE_NAME = "elemensha_home_secure"
        const val KEY_SERVER = "server_url"
        const val KEY_TOKEN = "api_token"
        const val KEY_BORROWER = "borrower"
        const val KEY_NOTIFIED = "notified_keys"
        const val KEY_NOTIFY = "notifications_enabled"
        const val KEY_BASELINE = "notification_baseline_done"
        const val KEY_NOTIFY_HOUR = "notify_hour"
        // 무한정 쌓이면 SharedPreferences가 비대해진다.
        const val MAX_NOTIFIED_KEYS = 500
    }
}
