plugins {
    id("com.android.application") version "8.7.3" apply false
    id("org.jetbrains.kotlin.android") version "2.0.21" apply false
    id("org.jetbrains.kotlin.plugin.compose") version "2.0.21" apply false
    id("org.jetbrains.kotlin.plugin.serialization") version "2.0.21" apply false
    // 화면을 눈으로 확인하려고 넣었다. 테스트에서만 돈다 - 앱에는 안 들어간다.
    id("app.cash.paparazzi") version "1.3.5" apply false
}
