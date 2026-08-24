package com.elemensha.home.update

import android.content.Context
import android.content.Intent
import android.net.Uri
import android.provider.Settings
import androidx.core.content.FileProvider
import com.elemensha.home.BuildConfig
import com.elemensha.home.data.Api
import com.elemensha.home.data.AppVersionInfo
import kotlinx.coroutines.Dispatchers
import kotlinx.coroutines.withContext
import okhttp3.Request
import java.io.File

/**
 * 인앱 업데이트.
 *
 * APK 최초 1회만 수동 설치하고, 이후에는 설정 탭의 버튼으로 갱신한다.
 * APK는 GitHub Releases에 올라가고 서버가 최신 정보를 중계한다.
 *
 * 흐름: 버전 확인 -> 다운로드 -> '알 수 없는 앱 설치' 권한 확인 -> 설치 화면 호출
 */
class Updater(private val context: Context, private val api: Api) {

    sealed interface State {
        data object Idle : State
        data object Checking : State
        data class UpToDate(val current: String) : State
        data class Available(val info: AppVersionInfo) : State
        data class Downloading(val percent: Int, val info: AppVersionInfo) : State
        data class ReadyToInstall(val file: File, val info: AppVersionInfo) : State
        data class NeedsPermission(val file: File, val info: AppVersionInfo) : State
        data class Failed(val message: String) : State
    }

    val currentVersionName: String = BuildConfig.VERSION_NAME
    private val currentVersionCode: Int = BuildConfig.VERSION_CODE

    /** 서버에 최신 버전을 물어본다. */
    suspend fun check(): State = runCatching {
        val info = api.latestVersion()
        when {
            // 아직 GitHub에 올라간 APK가 없으면 서버가 바닥값을 돌려준다.
            info.apkUrl.isNullOrBlank() -> State.UpToDate(currentVersionName)
            info.versionCode > currentVersionCode -> State.Available(info)
            else -> State.UpToDate(currentVersionName)
        }
    }.getOrElse { State.Failed(it.message ?: "버전 확인 실패") }

    /**
     * APK를 캐시에 내려받는다. 같은 버전을 이미 받아뒀으면 재사용한다.
     * `onProgress`는 0~100.
     */
    suspend fun download(
        info: AppVersionInfo,
        onProgress: (Int) -> Unit,
    ): State = withContext(Dispatchers.IO) {
        val url = info.apkUrl ?: return@withContext State.Failed("APK 주소가 없습니다.")
        val dir = File(context.cacheDir, "updates").apply { mkdirs() }
        // 지난 버전 APK는 지운다. 20MB짜리가 쌓이면 기기 용량을 잡아먹는다.
        dir.listFiles()?.forEach { if (it.name != fileName(info)) it.delete() }

        val target = File(dir, fileName(info))
        if (target.exists() && info.apkSize != null && target.length() == info.apkSize) {
            return@withContext State.ReadyToInstall(target, info)
        }

        runCatching {
            val request = Request.Builder().url(url).build()
            api.downloadClient.newCall(request).execute().use { response ->
                if (!response.isSuccessful) {
                    return@withContext State.Failed("다운로드 실패 (HTTP ${response.code})")
                }
                val body = response.body ?: return@withContext State.Failed("응답이 비었습니다.")
                val total = if (body.contentLength() > 0) body.contentLength()
                else info.apkSize ?: -1L
                var written = 0L
                var lastPercent = -1

                body.byteStream().use { input ->
                    target.outputStream().use { output ->
                        val buffer = ByteArray(64 * 1024)
                        while (true) {
                            val read = input.read(buffer)
                            if (read == -1) break
                            output.write(buffer, 0, read)
                            written += read
                            if (total > 0) {
                                val percent = (written * 100 / total).toInt().coerceIn(0, 100)
                                if (percent != lastPercent) {
                                    lastPercent = percent
                                    onProgress(percent)
                                }
                            }
                        }
                    }
                }
            }
            if (target.length() == 0L) {
                // 빈 파일을 설치 화면에 넘기면 정체불명의 파싱 오류가 뜬다.
                target.delete()
                State.Failed("빈 파일을 받았습니다.")
            } else {
                State.ReadyToInstall(target, info)
            }
        }.getOrElse {
            target.delete()
            State.Failed("다운로드 실패: ${it.message}")
        }
    }

    /** '알 수 없는 앱 설치' 권한이 있는지. 없으면 설정 화면으로 보내야 한다. */
    fun canInstall(): Boolean = context.packageManager.canRequestPackageInstalls()

    fun openInstallPermissionSettings() {
        val intent = Intent(
            Settings.ACTION_MANAGE_UNKNOWN_APP_SOURCES,
            Uri.parse("package:${context.packageName}"),
        ).addFlags(Intent.FLAG_ACTIVITY_NEW_TASK)
        context.startActivity(intent)
    }

    /** 시스템 설치 화면을 띄운다. 실제 설치 여부는 사용자가 결정한다. */
    fun install(file: File) {
        val uri = FileProvider.getUriForFile(
            context, "${BuildConfig.APPLICATION_ID}.fileprovider", file,
        )
        val intent = Intent(Intent.ACTION_VIEW).apply {
            setDataAndType(uri, "application/vnd.android.package-archive")
            addFlags(Intent.FLAG_GRANT_READ_URI_PERMISSION)
            addFlags(Intent.FLAG_ACTIVITY_NEW_TASK)
        }
        context.startActivity(intent)
    }

    private fun fileName(info: AppVersionInfo) = "elemensha-home-${info.versionName}.apk"
}
