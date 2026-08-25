package com.elemensha.home.data

import kotlinx.coroutines.Dispatchers
import kotlinx.coroutines.withContext
import kotlinx.serialization.encodeToString
import kotlinx.serialization.json.Json
import okhttp3.MediaType.Companion.toMediaType
import okhttp3.OkHttpClient
import okhttp3.Request
import okhttp3.RequestBody.Companion.toRequestBody
import java.io.IOException
import java.util.concurrent.TimeUnit

/**
 * 서버 클라이언트.
 *
 * 실패를 감추지 않는다. 네트워크 오류든 서버 오류든 [ApiException]으로 올려서
 * 화면에 사유가 뜨게 한다. 빈 목록으로 조용히 넘기면 "매물이 없는 것"과
 * "서버가 죽은 것"이 구분되지 않는다.
 */
class ApiException(message: String, val code: Int = 0) : IOException(message)

class Api(
    private val baseUrlProvider: () -> String,
    private val tokenProvider: () -> String,
) {
    private val json = Json {
        ignoreUnknownKeys = true      // 서버가 필드를 추가해도 앱이 죽지 않게
        coerceInputValues = true
        explicitNulls = false
    }

    private val client = OkHttpClient.Builder()
        .connectTimeout(15, TimeUnit.SECONDS)
        .readTimeout(30, TimeUnit.SECONDS)
        .build()

    /** APK 다운로드용. 수십 MB를 받으므로 읽기 타임아웃을 길게 잡는다. */
    val downloadClient: OkHttpClient = client.newBuilder()
        .readTimeout(5, TimeUnit.MINUTES)
        .writeTimeout(5, TimeUnit.MINUTES)
        .build()

    private val jsonMedia = "application/json; charset=utf-8".toMediaType()

    private fun buildRequest(path: String): Request.Builder {
        val base = baseUrlProvider().trimEnd('/')
        if (base.isEmpty()) throw ApiException("서버 주소가 설정되지 않았다")
        val builder = Request.Builder().url("$base$path")
        val token = tokenProvider()
        if (token.isNotBlank()) builder.header("Authorization", "Bearer $token")
        return builder
    }

    private suspend fun execute(request: Request): String = withContext(Dispatchers.IO) {
        try {
            client.newCall(request).execute().use { response ->
                val body = response.body?.string().orEmpty()
                if (!response.isSuccessful) {
                    val detail = runCatching {
                        json.parseToJsonElement(body)
                            .let { it as? kotlinx.serialization.json.JsonObject }
                            ?.get("detail")?.toString()?.trim('"')
                    }.getOrNull()
                    throw ApiException(
                        detail ?: "서버 오류 ${response.code}",
                        response.code,
                    )
                }
                body
            }
        } catch (e: ApiException) {
            throw e
        } catch (e: IOException) {
            throw ApiException("서버에 연결할 수 없다: ${e.message}")
        }
    }

    private suspend inline fun <reified T> get(path: String): T =
        json.decodeFromString(execute(buildRequest(path).get().build()))

    private suspend inline fun <reified B, reified T> post(path: String, body: B): T {
        val payload = json.encodeToString(body).toRequestBody(jsonMedia)
        return json.decodeFromString(execute(buildRequest(path).post(payload).build()))
    }

    suspend fun health(): HealthResponse = get("/api/health")

    suspend fun listings(
        source: String? = null,
        limit: Int = 100,
        filterId: Int? = null,
        applyFilters: Boolean = true,
        sort: String = "recent",
    ): ListingsResponse {
        val query = buildString {
            append("/api/listings?limit=").append(limit)
            append("&apply_filters=").append(applyFilters)
            append("&sort=").append(sort)
            if (source != null) append("&source=").append(source)
            if (filterId != null) append("&filter_id=").append(filterId)
        }
        return get(query)
    }

    /** 아직 알리지 않은, 필터에 걸린 물건. 백그라운드 워커가 이걸 본다. */
    suspend fun notifications(): List<Listing> =
        get<ListingsResponse>("/api/notifications").items

    suspend fun ackNotifications(keys: List<String>) {
        if (keys.isEmpty()) return
        post<Map<String, List<String>>, Map<String, Int>>(
            "/api/notifications/ack",
            mapOf("dedupe_keys" to keys),
        )
    }

    suspend fun filters(): List<FilterProfile> =
        get<FiltersResponse>("/api/filters").items

    suspend fun saveFilter(filter: FilterProfile): FilterProfile =
        post("/api/filters", filter)

    suspend fun deleteFilter(id: Int) {
        execute(buildRequest("/api/filters/$id").delete().build())
    }

    suspend fun plan(request: PlanRequest): PlanResponse = post("/api/plan", request)

    /** 지금까지 쌓인 물건을 '이미 알림'으로 표시한다. 알림을 처음 켤 때 부른다. */
    suspend fun baselineNotifications(): Int =
        post<Map<String, String>, Map<String, Int>>("/api/notifications/baseline", emptyMap())["baselined"] ?: 0

    suspend fun latestVersion(): AppVersionInfo = get("/api/app/version")

    /** 키를 새로 넣었을 때 즉시 확인하는 수동 폴링. */
    suspend fun refresh(): String = execute(
        buildRequest("/api/refresh").post(ByteArray(0).toRequestBody(jsonMedia)).build()
    )
}
