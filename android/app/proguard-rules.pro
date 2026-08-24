# ============================================================================
#  R8 / ProGuard 규칙
#  봇 앱에서 R8 관련으로 한 번 물렸던 것들을 그대로 가져왔다.
# ============================================================================

# ---------------------------------------------------------- kotlinx.serialization
-keepattributes *Annotation*, InnerClasses
-dontnote kotlinx.serialization.**
-keepclassmembers class com.elemensha.home.** {
    *** Companion;
    <fields>;
}
-keepclasseswithmembers class com.elemensha.home.** {
    kotlinx.serialization.KSerializer serializer(...);
}
-keep,includedescriptorclasses class com.elemensha.home.**$$serializer { *; }
# @Serializable 데이터 클래스는 필드명이 그대로 JSON 키다. 축약되면 서버와
# 주고받는 키가 어긋나는데, 예외 없이 조용히 값만 누락되므로 찾기 어렵다.
-keepclassmembers @kotlinx.serialization.Serializable class com.elemensha.home.** {
    <fields>;
}

# ---------------------------------------------------------------------- OkHttp
-dontwarn okhttp3.**
-dontwarn okio.**
-dontwarn org.conscrypt.**
-dontwarn org.bouncycastle.**
-dontwarn org.openjsse.**

# ------------------------------------------------- androidx.security-crypto / Tink
# Tink 가 참조하는 errorprone 어노테이션은 컴파일 전용이라 APK 에 없다.
# R8 이 "Missing class" 로 빌드를 세우므로 무시하게 한다. 런타임에 불필요하다.
-dontwarn com.google.errorprone.annotations.**
-dontwarn javax.annotation.**
-dontwarn com.google.api.client.**
-dontwarn com.google.auto.value.**
# KeysDownloader 는 원격 키셋을 받을 때만 joda-time 을 쓴다. 로컬 키스토어만
# 쓰는 우리는 그 경로를 타지 않는다.
-dontwarn org.joda.time.**
-keep class com.google.crypto.tink.** { *; }
