package com.elemensha.home.ui

import android.app.Activity
import androidx.compose.foundation.isSystemInDarkTheme
import androidx.compose.material3.MaterialTheme
import androidx.compose.material3.darkColorScheme
import androidx.compose.material3.lightColorScheme
import androidx.compose.runtime.Composable
import androidx.compose.runtime.SideEffect
import androidx.compose.ui.graphics.Color
import androidx.compose.ui.graphics.toArgb
import androidx.compose.ui.platform.LocalView
import androidx.core.view.WindowCompat

private val DarkColors = darkColorScheme(
    primary = Color(0xFF8AB4F8),
    onPrimary = Color(0xFF0B1B2B),
    secondary = Color(0xFF7FD1AE),
    background = Color(0xFF10141A),
    surface = Color(0xFF171C24),
    surfaceVariant = Color(0xFF232A35),
    error = Color(0xFFF2857F),
)

private val LightColors = lightColorScheme(
    primary = Color(0xFF1B62D6),
    onPrimary = Color(0xFFFFFFFF),
    secondary = Color(0xFF1E8A63),
    background = Color(0xFFF7F8FA),
    surface = Color(0xFFFFFFFF),
    surfaceVariant = Color(0xFFEDF0F5),
    error = Color(0xFFB3261E),
)

/** 출처가 검증되지 않은 값에 쓰는 색. 화면 어디서든 같은 의미로 보이게 한다. */
val WarningAmber = Color(0xFFE0A030)
val VerifiedGreen = Color(0xFF2E9E6B)

@Composable
fun HomeTheme(
    darkTheme: Boolean = isSystemInDarkTheme(),
    content: @Composable () -> Unit,
) {
    val colors = if (darkTheme) DarkColors else LightColors
    val view = LocalView.current

    if (!view.isInEditMode) {
        SideEffect {
            val window = (view.context as Activity).window
            window.statusBarColor = colors.background.toArgb()
            WindowCompat.getInsetsController(window, view)
                .isAppearanceLightStatusBars = !darkTheme
        }
    }

    MaterialTheme(colorScheme = colors, content = content)
}
