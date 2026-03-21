package com.pilot.app.ui.screens

import androidx.compose.animation.AnimatedContent
import androidx.compose.animation.AnimatedVisibility
import androidx.compose.animation.animateColorAsState
import androidx.compose.animation.core.Spring
import androidx.compose.animation.core.animateDpAsState
import androidx.compose.animation.core.animateFloatAsState
import androidx.compose.animation.core.spring
import androidx.compose.animation.core.tween
import androidx.compose.animation.fadeIn
import androidx.compose.animation.fadeOut
import androidx.compose.animation.slideInHorizontally
import androidx.compose.animation.slideInVertically
import androidx.compose.animation.slideOutHorizontally
import androidx.compose.animation.togetherWith
import androidx.compose.foundation.background
import androidx.compose.foundation.clickable
import androidx.compose.foundation.interaction.MutableInteractionSource
import androidx.compose.foundation.layout.Box
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.Row
import androidx.compose.foundation.layout.Spacer
import androidx.compose.foundation.layout.fillMaxHeight
import androidx.compose.foundation.layout.fillMaxSize
import androidx.compose.foundation.layout.fillMaxWidth
import androidx.compose.foundation.layout.height
import androidx.compose.foundation.layout.offset
import androidx.compose.foundation.layout.padding
import androidx.compose.foundation.layout.width
import androidx.compose.foundation.shape.RoundedCornerShape
import androidx.compose.material.icons.Icons
import androidx.compose.material.icons.automirrored.filled.ArrowBack
import androidx.compose.material3.HorizontalDivider
import androidx.compose.material3.Icon
import androidx.compose.material3.IconButton
import androidx.compose.material3.MaterialTheme
import androidx.compose.material3.OutlinedTextField
import androidx.compose.material3.OutlinedTextFieldDefaults
import androidx.compose.material3.Switch
import androidx.compose.material3.SwitchDefaults
import androidx.compose.material3.Text
import androidx.compose.runtime.Composable
import androidx.compose.runtime.LaunchedEffect
import androidx.compose.runtime.getValue
import androidx.compose.runtime.mutableIntStateOf
import androidx.compose.runtime.mutableStateOf
import androidx.compose.runtime.remember
import androidx.compose.runtime.setValue
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.draw.clip
import androidx.compose.ui.draw.scale
import androidx.compose.ui.graphics.Color
import androidx.compose.ui.graphics.graphicsLayer
import androidx.compose.ui.text.font.FontWeight
import androidx.compose.ui.unit.dp
import androidx.compose.ui.unit.sp
import com.pilot.app.BuildConfig
import com.pilot.app.service.OverlayService
import com.pilot.app.ui.theme.Primary
import com.pilot.app.ui.theme.TextPrimary
import com.pilot.app.ui.theme.TextSecondary
import kotlinx.coroutines.delay

private data class SettingItem(val id: Int, val title: String)

private val settingItems = listOf(
    SettingItem(0, "Server"),
    SettingItem(1, "Voice"),
    SettingItem(2, "Overlay"),
    SettingItem(3, "About")
)

@Composable
fun SettingsScreen(onBack: () -> Unit) {
    var selectedIndex by remember { mutableIntStateOf(0) }
    var serverUrl by remember { mutableStateOf(BuildConfig.SERVER_URL) }
    var ttsEnabled by remember { mutableStateOf(true) }
    var overlayAutoStart by remember { mutableStateOf(false) }

    // Staggered entrance for sidebar items
    var showItems by remember { mutableStateOf(List(4) { false }) }
    var showContent by remember { mutableStateOf(false) }

    LaunchedEffect(Unit) {
        for (i in 0 until 4) {
            delay(80)
            showItems = showItems.toMutableList().also { it[i] = true }
        }
        delay(100)
        showContent = true
    }

    // Back button press animation
    var backPressed by remember { mutableStateOf(false) }
    val backScale by animateFloatAsState(
        targetValue = if (backPressed) 0.85f else 1f,
        animationSpec = spring(dampingRatio = 0.5f, stiffness = 800f),
        label = "backScale"
    )

    Row(
        modifier = Modifier
            .fillMaxSize()
            .background(MaterialTheme.colorScheme.background)
    ) {
        // Left sidebar
        Column(
            modifier = Modifier
                .width(140.dp)
                .fillMaxHeight()
                .padding(top = 48.dp)
        ) {
            IconButton(
                onClick = {
                    backPressed = true
                    onBack()
                },
                modifier = Modifier
                    .padding(start = 8.dp)
                    .scale(backScale)
            ) {
                Icon(
                    imageVector = Icons.AutoMirrored.Filled.ArrowBack,
                    contentDescription = "Back",
                    tint = TextPrimary
                )
            }

            Spacer(modifier = Modifier.height(16.dp))

            settingItems.forEachIndexed { index, item ->
                val isSelected = item.id == selectedIndex

                // Animated properties
                val bgAlpha by animateFloatAsState(
                    targetValue = if (isSelected) 0.1f else 0f,
                    animationSpec = tween(300), label = "bgA_$index"
                )
                val textColor by animateColorAsState(
                    targetValue = if (isSelected) Primary else TextSecondary,
                    animationSpec = tween(300), label = "txtC_$index"
                )
                val indicatorWidth by animateDpAsState(
                    targetValue = if (isSelected) 4.dp else 0.dp,
                    animationSpec = spring(dampingRatio = 0.6f, stiffness = 400f),
                    label = "ind_$index"
                )

                AnimatedVisibility(
                    visible = showItems.getOrElse(index) { false },
                    enter = fadeIn(tween(300)) + slideInVertically(
                        initialOffsetY = { 30 },
                        animationSpec = spring(dampingRatio = 0.7f, stiffness = 300f)
                    )
                ) {
                    Row(verticalAlignment = Alignment.CenterVertically) {
                        // Animated left indicator bar
                        Box(
                            modifier = Modifier
                                .width(indicatorWidth)
                                .height(36.dp)
                                .clip(RoundedCornerShape(topEnd = 4.dp, bottomEnd = 4.dp))
                                .background(Primary)
                        )

                        Text(
                            text = item.title,
                            style = MaterialTheme.typography.titleMedium,
                            color = textColor,
                            fontWeight = if (isSelected) FontWeight.Bold else FontWeight.Normal,
                            modifier = Modifier
                                .fillMaxWidth()
                                .clip(RoundedCornerShape(topEnd = 12.dp, bottomEnd = 12.dp))
                                .background(Primary.copy(alpha = bgAlpha))
                                .clickable(
                                    indication = null,
                                    interactionSource = remember { MutableInteractionSource() }
                                ) { selectedIndex = item.id }
                                .padding(horizontal = 20.dp, vertical = 14.dp)
                        )
                    }
                }
            }
        }

        // Divider
        HorizontalDivider(
            modifier = Modifier
                .width(1.dp)
                .fillMaxHeight()
                .padding(vertical = 48.dp),
            color = Primary.copy(alpha = 0.12f)
        )

        // Right detail panel with crossfade
        AnimatedContent(
            targetState = selectedIndex,
            transitionSpec = {
                (fadeIn(tween(250)) + slideInHorizontally(
                    initialOffsetX = { 60 },
                    animationSpec = spring(dampingRatio = 0.8f, stiffness = 300f)
                )) togetherWith (fadeOut(tween(150)) + slideOutHorizontally(
                    targetOffsetX = { -30 },
                    animationSpec = tween(150)
                ))
            },
            label = "settingsContent"
        ) { targetIndex ->
            Column(
                modifier = Modifier
                    .fillMaxSize()
                    .padding(start = 24.dp, end = 24.dp, top = 48.dp)
            ) {
                Text(
                    text = settingItems[targetIndex].title,
                    style = MaterialTheme.typography.headlineMedium,
                    color = TextPrimary
                )

                Spacer(modifier = Modifier.height(32.dp))

                when (targetIndex) {
                    0 -> ServerSettings(
                        serverUrl = serverUrl,
                        onUrlChange = {
                            serverUrl = it
                            OverlayService.instance?.agentLoop?.updateServerUrl(it)
                        }
                    )
                    1 -> VoiceSettings(
                        ttsEnabled = ttsEnabled,
                        onToggle = {
                            ttsEnabled = it
                            OverlayService.instance?.ttsHelper?.enabled = it
                        }
                    )
                    2 -> OverlaySettings(
                        autoStart = overlayAutoStart,
                        onToggle = { overlayAutoStart = it }
                    )
                    3 -> AboutSettings()
                }
            }
        }
    }
}

@Composable
private fun ServerSettings(serverUrl: String, onUrlChange: (String) -> Unit) {
    Text("Server URL", style = MaterialTheme.typography.titleMedium, color = TextPrimary)
    Spacer(modifier = Modifier.height(8.dp))
    Text(
        "The address of the Mac server running the AI backend.",
        style = MaterialTheme.typography.bodySmall, color = TextSecondary
    )
    Spacer(modifier = Modifier.height(16.dp))
    OutlinedTextField(
        value = serverUrl,
        onValueChange = onUrlChange,
        label = { Text("URL") },
        singleLine = true,
        modifier = Modifier.fillMaxWidth(),
        shape = RoundedCornerShape(12.dp),
        colors = OutlinedTextFieldDefaults.colors(
            focusedBorderColor = Primary,
            cursorColor = Primary,
            unfocusedBorderColor = Primary.copy(alpha = 0.3f)
        )
    )
}

@Composable
private fun VoiceSettings(ttsEnabled: Boolean, onToggle: (Boolean) -> Unit) {
    SettingToggleRow(
        title = "Voice Feedback",
        description = "Speak status updates aloud while performing tasks.",
        checked = ttsEnabled,
        onToggle = onToggle
    )
}

@Composable
private fun OverlaySettings(autoStart: Boolean, onToggle: (Boolean) -> Unit) {
    SettingToggleRow(
        title = "Auto-start Overlay",
        description = "Automatically show the floating button when the app launches.",
        checked = autoStart,
        onToggle = onToggle
    )
}

@Composable
private fun AboutSettings() {
    Text("PILOT v1.0", style = MaterialTheme.typography.titleMedium, color = TextPrimary)
    Spacer(modifier = Modifier.height(8.dp))
    Text(
        "AI-powered phone automation assistant. Built for the IEEE UBC EDT Competition.",
        style = MaterialTheme.typography.bodyMedium, color = TextSecondary, lineHeight = 22.sp
    )
    Spacer(modifier = Modifier.height(24.dp))
    Text(
        "Tap the floating button to speak a command. Pilot will read the screen, plan the steps, and execute them for you.",
        style = MaterialTheme.typography.bodyMedium, color = TextSecondary, lineHeight = 22.sp
    )
}

@Composable
private fun SettingToggleRow(
    title: String, description: String,
    checked: Boolean, onToggle: (Boolean) -> Unit
) {
    Row(
        modifier = Modifier.fillMaxWidth(),
        verticalAlignment = Alignment.Top
    ) {
        Column(modifier = Modifier.weight(1f)) {
            Text(title, style = MaterialTheme.typography.titleMedium, color = TextPrimary)
            Spacer(modifier = Modifier.height(4.dp))
            Text(
                description, style = MaterialTheme.typography.bodySmall,
                color = TextSecondary, lineHeight = 18.sp
            )
        }
        Spacer(modifier = Modifier.width(16.dp))
        Switch(
            checked = checked,
            onCheckedChange = onToggle,
            colors = SwitchDefaults.colors(
                checkedTrackColor = Primary,
                checkedThumbColor = Color.White
            )
        )
    }
}
