package com.pilot.app.ui.theme

import androidx.compose.material3.MaterialTheme
import androidx.compose.material3.darkColorScheme
import androidx.compose.runtime.Composable
import androidx.compose.ui.graphics.Color

val PilotBlue = Color(0xFF00CEFF)
val PilotPurple = Color(0xFF6C5CE7)
val PilotGreen = Color(0xFF00E676)
val PilotOrange = Color(0xFFFF6D00)
val PilotDark = Color(0xFF1A1A2E)
val PilotSurface = Color(0xFF16213E)
val PilotCard = Color(0xFF1E2D4A)

private val DarkColorScheme = darkColorScheme(
    primary = PilotPurple,
    secondary = PilotBlue,
    tertiary = PilotGreen,
    background = PilotDark,
    surface = PilotSurface,
    onPrimary = Color.White,
    onSecondary = Color.White,
    onBackground = Color.White,
    onSurface = Color.White,
    error = PilotOrange,
    onError = Color.White
)

@Composable
fun PilotTheme(content: @Composable () -> Unit) {
    MaterialTheme(
        colorScheme = DarkColorScheme,
        content = content
    )
}
