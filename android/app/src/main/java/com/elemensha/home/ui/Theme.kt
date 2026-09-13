package com.elemensha.home.ui

import android.app.Activity
import androidx.compose.foundation.isSystemInDarkTheme
import androidx.compose.material3.MaterialTheme
import androidx.compose.material3.Typography
import androidx.compose.material3.darkColorScheme
import androidx.compose.material3.lightColorScheme
import androidx.compose.runtime.Composable
import androidx.compose.runtime.SideEffect
import androidx.compose.ui.graphics.Color
import androidx.compose.ui.graphics.toArgb
import androidx.compose.ui.platform.LocalView
import androidx.compose.ui.text.TextStyle
import androidx.compose.ui.text.font.FontWeight
import androidx.compose.ui.text.style.LineBreak
import androidx.compose.ui.unit.sp
import androidx.core.view.WindowCompat

private val LightColors = lightColorScheme(
    primary = Tone.BlueDeep,
    onPrimary = Color.White,
    primaryContainer = Tone.BlueWash,
    onPrimaryContainer = Tone.BlueDeep,
    secondary = Tone.GreenDeep,
    onSecondary = Color.White,
    secondaryContainer = Tone.GreenWash,
    onSecondaryContainer = Tone.GreenDeep,
    background = Paper.P75,
    onBackground = Paper.Ink,
    surface = Paper.P50,
    onSurface = Paper.Ink,
    surfaceVariant = Paper.P100,
    onSurfaceVariant = Paper.Ink2,
    outline = Paper.Muted,
    outlineVariant = Paper.P200,
    error = Tone.Red,
    onError = Color.White,
    errorContainer = Tone.RedWash,
    onErrorContainer = Tone.RedDeep,
)

private val DarkColors = darkColorScheme(
    primary = Tone.Blue,
    onPrimary = Graphite.G900,
    primaryContainer = Graphite.G700,
    onPrimaryContainer = Tone.Blue,
    secondary = Tone.Green,
    onSecondary = Graphite.G900,
    secondaryContainer = Graphite.G700,
    onSecondaryContainer = Tone.Green,
    background = PaperDark.Background,
    onBackground = PaperDark.Ink,
    surface = PaperDark.Surface,
    onSurface = PaperDark.Ink,
    surfaceVariant = PaperDark.SurfaceHigh,
    onSurfaceVariant = PaperDark.Ink2,
    outline = PaperDark.Muted,
    outlineVariant = PaperDark.Line,
    error = Color(0xFFF07A88),
    onError = Graphite.G900,
    errorContainer = Color(0xFF4A1620),
    onErrorContainer = Color(0xFFFFD9DE),
)

/**
 * 출처가 검증되지 않은 값에 쓰는 색, 자료로 확인된 값에 쓰는 색.
 *
 * 이름을 그대로 두는 이유는 화면 곳곳이 이 두 이름을 부르고 있어서다.
 * 값만 로고 색으로 바꿨다.
 */
val WarningAmber = Tone.Amber
val VerifiedGreen = Tone.GreenDeep

/**
 * 한글은 단어 중간에서 끊기면 읽는 속도가 눈에 띄게 떨어진다.
 * `LineBreak.Heading` 은 어절 단위로 끊어 준다. 제목처럼 짧은 줄일수록 차이가 크다.
 */
private val HeadingBreak = LineBreak.Heading
private val BodyBreak = LineBreak.Paragraph

private fun ko(
    size: Int,
    weight: FontWeight,
    lineHeight: Int,
    tracking: Double,
    heading: Boolean = false,
) = TextStyle(
    fontSize = size.sp,
    fontWeight = weight,
    lineHeight = lineHeight.sp,
    letterSpacing = tracking.sp,
    lineBreak = if (heading) HeadingBreak else BodyBreak,
)

/**
 * 자간을 전부 음수로 당긴다. 한글 기본 자간은 숫자가 섞이면 헐거워 보이고,
 * 금액처럼 긴 숫자에서 특히 그렇다.
 */
private val HomeTypography = Typography(
    displaySmall = ko(30, FontWeight.Bold, 36, -1.0, heading = true),
    headlineMedium = ko(24, FontWeight.Bold, 30, -0.8, heading = true),
    headlineSmall = ko(21, FontWeight.Bold, 27, -0.7, heading = true),
    titleLarge = ko(19, FontWeight.Bold, 25, -0.5, heading = true),
    titleMedium = ko(16, FontWeight.Bold, 22, -0.4, heading = true),
    titleSmall = ko(14, FontWeight.SemiBold, 19, -0.3, heading = true),
    bodyLarge = ko(15, FontWeight.Normal, 22, -0.2),
    bodyMedium = ko(14, FontWeight.Normal, 21, -0.2),
    bodySmall = ko(13, FontWeight.Normal, 19, -0.1),
    labelLarge = ko(14, FontWeight.SemiBold, 18, -0.2, heading = true),
    labelMedium = ko(12, FontWeight.SemiBold, 16, 0.0, heading = true),
    labelSmall = ko(11, FontWeight.Medium, 15, 0.2, heading = true),
)

@Composable
fun HomeTheme(
    darkTheme: Boolean = isSystemInDarkTheme(),
    content: @Composable () -> Unit,
) {
    val colors = if (darkTheme) DarkColors else LightColors
    val view = LocalView.current

    SideEffect {
        // 미리보기·스냅샷에서는 Activity 가 아니다. 강제로 캐스팅하면
        // 화면을 그려 보려던 도구가 통째로 죽는다.
        val window = (view.context as? Activity)?.window ?: return@SideEffect
        // 화면 맨 위는 흑연 띠가 아니라 종이 바탕이다. 상태바 글자를
        // 흰색으로 두면 밝은 바탕에서 안 보인다.
        window.statusBarColor = colors.background.toArgb()
        WindowCompat.getInsetsController(window, view)
            .isAppearanceLightStatusBars = !darkTheme
    }

    MaterialTheme(colorScheme = colors, typography = HomeTypography, content = content)
}
