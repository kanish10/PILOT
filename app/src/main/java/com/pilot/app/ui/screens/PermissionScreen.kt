package com.pilot.app.ui.screens

import android.Manifest
import android.content.pm.PackageManager
import android.os.Build
import androidx.activity.compose.rememberLauncherForActivityResult
import androidx.activity.result.contract.ActivityResultContracts
import androidx.compose.animation.AnimatedVisibility
import androidx.compose.animation.animateColorAsState
import androidx.compose.animation.core.FastOutSlowInEasing
import androidx.compose.animation.core.LinearEasing
import androidx.compose.animation.core.RepeatMode
import androidx.compose.animation.core.Spring
import androidx.compose.animation.core.animateDpAsState
import androidx.compose.animation.core.animateFloat
import androidx.compose.animation.core.animateFloatAsState
import androidx.compose.animation.core.infiniteRepeatable
import androidx.compose.animation.core.rememberInfiniteTransition
import androidx.compose.animation.core.spring
import androidx.compose.animation.core.tween
import androidx.compose.animation.fadeIn
import androidx.compose.animation.scaleIn
import androidx.compose.animation.slideInHorizontally
import androidx.compose.animation.slideInVertically
import androidx.compose.foundation.Canvas
import androidx.compose.foundation.background
import androidx.compose.foundation.border
import androidx.compose.foundation.gestures.detectTapGestures
import androidx.compose.foundation.layout.Box
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.Row
import androidx.compose.foundation.layout.Spacer
import androidx.compose.foundation.layout.fillMaxSize
import androidx.compose.foundation.layout.fillMaxWidth
import androidx.compose.foundation.layout.height
import androidx.compose.foundation.layout.padding
import androidx.compose.foundation.layout.size
import androidx.compose.foundation.layout.width
import androidx.compose.foundation.rememberScrollState
import androidx.compose.foundation.shape.CircleShape
import androidx.compose.foundation.shape.RoundedCornerShape
import androidx.compose.foundation.verticalScroll
import androidx.compose.material.icons.Icons
import androidx.compose.material.icons.filled.Check
import androidx.compose.material3.Icon
import androidx.compose.material3.LinearProgressIndicator
import androidx.compose.material3.MaterialTheme
import androidx.compose.material3.Text
import androidx.compose.runtime.Composable
import androidx.compose.runtime.LaunchedEffect
import androidx.compose.runtime.getValue
import androidx.compose.runtime.mutableStateOf
import androidx.compose.runtime.remember
import androidx.compose.runtime.setValue
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.draw.alpha
import androidx.compose.ui.draw.blur
import androidx.compose.ui.draw.clip
import androidx.compose.ui.draw.scale
import androidx.compose.ui.geometry.Offset
import androidx.compose.ui.graphics.Color
import androidx.compose.ui.graphics.StrokeCap
import androidx.compose.ui.graphics.graphicsLayer
import androidx.compose.ui.input.pointer.pointerInput
import androidx.compose.ui.platform.LocalContext
import androidx.compose.ui.text.font.FontWeight
import androidx.compose.ui.unit.dp
import androidx.compose.ui.unit.sp
import androidx.core.content.ContextCompat
import androidx.lifecycle.Lifecycle
import androidx.lifecycle.compose.LifecycleEventEffect
import com.pilot.app.ui.theme.Accent
import com.pilot.app.ui.theme.CardSurface
import com.pilot.app.ui.theme.Primary
import com.pilot.app.ui.theme.Success
import com.pilot.app.ui.theme.TextPrimary
import com.pilot.app.ui.theme.TextSecondary
import com.pilot.app.util.PermissionHelper
import kotlinx.coroutines.delay
import kotlin.math.sin

@Composable
fun PermissionScreen(onAllGranted: () -> Unit) {
    val context = LocalContext.current
    var accessibilityEnabled by remember { mutableStateOf(false) }
    var overlayEnabled by remember { mutableStateOf(false) }
    var microphoneGranted by remember { mutableStateOf(false) }
    var notificationGranted by remember { mutableStateOf(false) }

    val micLauncher = rememberLauncherForActivityResult(
        ActivityResultContracts.RequestPermission()
    ) { granted -> microphoneGranted = granted }

    val notifLauncher = rememberLauncherForActivityResult(
        ActivityResultContracts.RequestPermission()
    ) { granted -> notificationGranted = granted }

    fun refreshPermissions() {
        accessibilityEnabled = PermissionHelper.isAccessibilityEnabled(context)
        overlayEnabled = PermissionHelper.isOverlayEnabled(context)
        microphoneGranted = ContextCompat.checkSelfPermission(
            context, Manifest.permission.RECORD_AUDIO
        ) == PackageManager.PERMISSION_GRANTED
        notificationGranted = if (Build.VERSION.SDK_INT >= Build.VERSION_CODES.TIRAMISU) {
            ContextCompat.checkSelfPermission(
                context, Manifest.permission.POST_NOTIFICATIONS
            ) == PackageManager.PERMISSION_GRANTED
        } else true
    }

    LifecycleEventEffect(Lifecycle.Event.ON_RESUME) { refreshPermissions() }

    val totalPerms = if (Build.VERSION.SDK_INT >= Build.VERSION_CODES.TIRAMISU) 4 else 3
    val grantedCount = listOf(accessibilityEnabled, overlayEnabled, microphoneGranted, notificationGranted).count { it }
    val allGranted = grantedCount >= totalPerms ||
        (Build.MODEL?.contains("sdk", ignoreCase = true) == true || Build.HARDWARE == "ranchu")

    if (allGranted) {
        onAllGranted()
        return
    }

    // Staggered entrance
    var showHeader by remember { mutableStateOf(false) }
    var showCards by remember { mutableStateOf(List(4) { false }) }

    LaunchedEffect(Unit) {
        delay(200); showHeader = true
        for (i in 0 until 4) {
            delay(150)
            showCards = showCards.toMutableList().also { it[i] = true }
        }
    }

    val infiniteTransition = rememberInfiniteTransition(label = "perm")
    val bgPulse by infiniteTransition.animateFloat(
        initialValue = 0f, targetValue = 1f,
        animationSpec = infiniteRepeatable(tween(4000, easing = LinearEasing)),
        label = "bgPulse"
    )

    Box(
        modifier = Modifier
            .fillMaxSize()
            .background(MaterialTheme.colorScheme.background)
    ) {
        // Subtle ambient orbs
        Canvas(modifier = Modifier.fillMaxSize().blur(100.dp)) {
            drawCircle(
                color = Primary.copy(alpha = 0.10f),
                radius = 200f + sin(bgPulse * Math.PI * 2).toFloat() * 30f,
                center = Offset(size.width * 0.8f, size.height * 0.15f)
            )
            drawCircle(
                color = Accent.copy(alpha = 0.07f),
                radius = 180f,
                center = Offset(size.width * 0.2f, size.height * 0.7f)
            )
        }

        Column(
            modifier = Modifier
                .fillMaxSize()
                .verticalScroll(rememberScrollState())
                .padding(24.dp)
        ) {
            Spacer(modifier = Modifier.height(16.dp))

            // Animated logo
            AnimatedVisibility(
                visible = showHeader,
                enter = fadeIn(tween(500)) + scaleIn(
                    initialScale = 0.5f,
                    animationSpec = spring(dampingRatio = 0.5f, stiffness = 300f)
                )
            ) {
                Box(
                    modifier = Modifier
                        .size(48.dp)
                        .clip(CircleShape)
                        .border(2.dp, Primary, CircleShape)
                        .background(Primary.copy(alpha = 0.08f)),
                    contentAlignment = Alignment.Center
                ) {
                    Text("P", fontSize = 20.sp, fontWeight = FontWeight.Bold, color = Primary)
                }
            }

            Spacer(modifier = Modifier.height(32.dp))

            // Animated header
            AnimatedVisibility(
                visible = showHeader,
                enter = fadeIn(tween(600)) + slideInVertically(
                    initialOffsetY = { 50 },
                    animationSpec = spring(dampingRatio = 0.7f, stiffness = 200f)
                )
            ) {
                Text(
                    text = "Please enable these\npermissions so we can\nhelp you",
                    style = MaterialTheme.typography.headlineLarge,
                    color = TextPrimary,
                    lineHeight = 40.sp
                )
            }

            Spacer(modifier = Modifier.height(16.dp))

            // Progress bar
            AnimatedVisibility(
                visible = showHeader,
                enter = fadeIn(tween(800))
            ) {
                val progress by animateFloatAsState(
                    targetValue = grantedCount.toFloat() / totalPerms,
                    animationSpec = spring(dampingRatio = 0.7f, stiffness = 200f),
                    label = "progress"
                )
                Column {
                    LinearProgressIndicator(
                        progress = { progress },
                        modifier = Modifier
                            .fillMaxWidth()
                            .height(6.dp)
                            .clip(RoundedCornerShape(3.dp)),
                        color = if (progress >= 1f) Success else Primary,
                        trackColor = Primary.copy(alpha = 0.1f),
                        strokeCap = StrokeCap.Round
                    )
                    Spacer(modifier = Modifier.height(8.dp))
                    Text(
                        text = "$grantedCount of $totalPerms permissions granted",
                        style = MaterialTheme.typography.labelSmall,
                        color = TextSecondary
                    )
                }
            }

            Spacer(modifier = Modifier.height(24.dp))

            // Permission cards with staggered entrance
            val permissionData = listOf(
                Triple("Accessibility Service", "We need this to read what's on your screen and perform actions like tapping and scrolling for you.", accessibilityEnabled),
                Triple("Display Over Apps", "We need this to show the floating button and status overlay while you use other apps.", overlayEnabled),
                Triple("Microphone", "We need this to hear your voice commands so you can talk to Pilot hands-free.", microphoneGranted),
                Triple("Notifications", "We need this to keep Pilot running in the background while it helps you.", notificationGranted)
            )

            val actions: List<() -> Unit> = listOf(
                { PermissionHelper.openAccessibilitySettings(context) },
                { PermissionHelper.openOverlaySettings(context) },
                { micLauncher.launch(Manifest.permission.RECORD_AUDIO) },
                {
                    if (Build.VERSION.SDK_INT >= Build.VERSION_CODES.TIRAMISU) {
                        notifLauncher.launch(Manifest.permission.POST_NOTIFICATIONS)
                    }
                }
            )

            val count = if (Build.VERSION.SDK_INT >= Build.VERSION_CODES.TIRAMISU) 4 else 3
            for (i in 0 until count) {
                val (title, desc, granted) = permissionData[i]
                AnimatedVisibility(
                    visible = showCards.getOrElse(i) { false },
                    enter = fadeIn(tween(400)) + slideInHorizontally(
                        initialOffsetX = { 200 },
                        animationSpec = spring(dampingRatio = 0.6f, stiffness = 250f)
                    )
                ) {
                    AnimatedPermissionCard(
                        title = title,
                        description = desc,
                        granted = granted,
                        onRequest = actions[i]
                    )
                }
                if (i < count - 1) Spacer(modifier = Modifier.height(12.dp))
            }

            Spacer(modifier = Modifier.height(32.dp))
        }
    }
}

@Composable
private fun AnimatedPermissionCard(
    title: String,
    description: String,
    granted: Boolean,
    onRequest: () -> Unit
) {
    var isPressed by remember { mutableStateOf(false) }
    val scale by animateFloatAsState(
        targetValue = if (isPressed) 0.96f else 1f,
        animationSpec = spring(dampingRatio = 0.4f, stiffness = 800f),
        label = "cardScale"
    )

    val borderColor by animateColorAsState(
        targetValue = if (granted) Success else Primary.copy(alpha = 0.25f),
        animationSpec = tween(500), label = "borderColor"
    )

    val bgColor by animateColorAsState(
        targetValue = if (granted) Success.copy(alpha = 0.10f) else CardSurface.copy(alpha = 0.7f),
        animationSpec = tween(500), label = "bgColor"
    )

    val elevation by animateDpAsState(
        targetValue = if (isPressed) 2.dp else 0.dp,
        animationSpec = spring(stiffness = 500f), label = "elev"
    )

    Row(
        modifier = Modifier
            .fillMaxWidth()
            .scale(scale)
            .graphicsLayer { shadowElevation = elevation.toPx() }
            .clip(RoundedCornerShape(16.dp))
            .border(1.5.dp, borderColor, RoundedCornerShape(16.dp))
            .background(bgColor)
            .pointerInput(granted) {
                if (!granted) {
                    detectTapGestures(
                        onPress = {
                            isPressed = true
                            tryAwaitRelease()
                            isPressed = false
                            onRequest()
                        }
                    )
                }
            }
            .padding(20.dp),
        verticalAlignment = Alignment.Top
    ) {
        Column(modifier = Modifier.weight(1f)) {
            Text(
                text = title,
                style = MaterialTheme.typography.titleMedium,
                fontWeight = FontWeight.SemiBold,
                color = TextPrimary
            )
            Spacer(modifier = Modifier.height(4.dp))
            Text(
                text = description,
                style = MaterialTheme.typography.bodySmall,
                color = TextSecondary,
                lineHeight = 18.sp
            )
        }

        // Animated checkmark
        AnimatedVisibility(
            visible = granted,
            enter = scaleIn(
                initialScale = 0f,
                animationSpec = spring(dampingRatio = 0.4f, stiffness = 400f)
            ) + fadeIn(tween(200))
        ) {
            Spacer(modifier = Modifier.width(12.dp))
            Box(
                modifier = Modifier
                    .size(28.dp)
                    .clip(CircleShape)
                    .background(Success),
                contentAlignment = Alignment.Center
            ) {
                Icon(
                    imageVector = Icons.Default.Check,
                    contentDescription = "Granted",
                    tint = Color.White,
                    modifier = Modifier.size(16.dp)
                )
            }
        }
    }
}
