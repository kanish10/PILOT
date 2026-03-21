package com.pilot.app.ui.screens

import androidx.compose.animation.AnimatedVisibility
import androidx.compose.animation.core.FastOutSlowInEasing
import androidx.compose.animation.core.LinearEasing
import androidx.compose.animation.core.RepeatMode
import androidx.compose.animation.core.Spring
import androidx.compose.animation.core.animateFloat
import androidx.compose.animation.core.animateFloatAsState
import androidx.compose.animation.core.infiniteRepeatable
import androidx.compose.animation.core.rememberInfiniteTransition
import androidx.compose.animation.core.spring
import androidx.compose.animation.core.tween
import androidx.compose.animation.fadeIn
import androidx.compose.animation.slideInVertically
import androidx.compose.foundation.Canvas
import androidx.compose.foundation.background
import androidx.compose.foundation.border
import androidx.compose.foundation.gestures.detectTapGestures
import androidx.compose.foundation.layout.Arrangement
import androidx.compose.foundation.layout.Box
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.Spacer
import androidx.compose.foundation.layout.fillMaxSize
import androidx.compose.foundation.layout.fillMaxWidth
import androidx.compose.foundation.layout.height
import androidx.compose.foundation.layout.padding
import androidx.compose.foundation.layout.size
import androidx.compose.foundation.shape.RoundedCornerShape
import androidx.compose.foundation.text.BasicTextField
import androidx.compose.material.icons.Icons
import androidx.compose.material.icons.filled.Mic
import androidx.compose.material.icons.filled.Settings
import androidx.compose.material3.Icon
import androidx.compose.material3.IconButton
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
import androidx.compose.ui.draw.rotate
import androidx.compose.ui.draw.scale
import androidx.compose.ui.focus.onFocusChanged
import androidx.compose.ui.geometry.Offset
import androidx.compose.ui.graphics.Brush
import androidx.compose.ui.graphics.Color
import androidx.compose.ui.graphics.SolidColor
import androidx.compose.ui.graphics.graphicsLayer
import androidx.compose.ui.input.pointer.pointerInput
import androidx.compose.ui.platform.LocalContext
import androidx.compose.ui.text.TextStyle
import androidx.compose.ui.text.font.FontWeight
import androidx.compose.ui.unit.dp
import androidx.compose.ui.unit.sp
import com.pilot.app.service.OverlayService
import com.pilot.app.ui.theme.Accent
import com.pilot.app.ui.theme.CardSurface
import com.pilot.app.ui.theme.Primary
import com.pilot.app.ui.theme.PrimaryLight
import com.pilot.app.ui.theme.TextPrimary
import com.pilot.app.ui.theme.TextSecondary
import kotlinx.coroutines.delay
import kotlin.math.cos
import kotlin.math.sin

@Composable
fun HomeScreen(onNavigateToSettings: () -> Unit) {
    val context = LocalContext.current
    var textInput by remember { mutableStateOf("") }
    var isFocused by remember { mutableStateOf(false) }

    val infiniteTransition = rememberInfiniteTransition(label = "home")

    // Animated gradient for heading
    val gradientShift by infiniteTransition.animateFloat(
        initialValue = 0f, targetValue = 1f,
        animationSpec = infiniteRepeatable(tween(4000, easing = LinearEasing)),
        label = "gradShift"
    )

    // Mic button pulse glow
    val micGlow by infiniteTransition.animateFloat(
        initialValue = 0.4f, targetValue = 1f,
        animationSpec = infiniteRepeatable(
            tween(1500, easing = FastOutSlowInEasing), RepeatMode.Reverse
        ), label = "micGlow"
    )

    val micScale by infiniteTransition.animateFloat(
        initialValue = 1f, targetValue = 1.08f,
        animationSpec = infiniteRepeatable(
            tween(2000, easing = FastOutSlowInEasing), RepeatMode.Reverse
        ), label = "micBreath"
    )

    // Floating particles
    val particleTime by infiniteTransition.animateFloat(
        initialValue = 0f, targetValue = 1000f,
        animationSpec = infiniteRepeatable(tween(50000, easing = LinearEasing)),
        label = "pTime"
    )

    // Settings gear subtle rotation on press
    var gearPressed by remember { mutableStateOf(false) }
    val gearRotation by animateFloatAsState(
        targetValue = if (gearPressed) 90f else 0f,
        animationSpec = spring(dampingRatio = 0.5f, stiffness = 300f),
        label = "gearRot"
    )

    // Input border animation
    val borderAlpha by animateFloatAsState(
        targetValue = if (isFocused) 1f else 0.3f,
        animationSpec = tween(300), label = "borderA"
    )

    // Mic press
    var micPressed by remember { mutableStateOf(false) }
    val micPressScale by animateFloatAsState(
        targetValue = if (micPressed) 0.85f else 1f,
        animationSpec = spring(dampingRatio = 0.35f, stiffness = 600f),
        label = "micPress"
    )

    // Staggered entrance
    var showHeading by remember { mutableStateOf(false) }
    var showInput by remember { mutableStateOf(false) }
    var showMic by remember { mutableStateOf(false) }

    LaunchedEffect(Unit) {
        delay(200); showHeading = true
        delay(300); showInput = true
        delay(300); showMic = true
    }

    Box(
        modifier = Modifier
            .fillMaxSize()
            .background(MaterialTheme.colorScheme.background)
    ) {
        // Ambient floating orbs
        Canvas(modifier = Modifier.fillMaxSize().blur(90.dp)) {
            val t = particleTime
            drawCircle(
                color = Primary.copy(alpha = 0.12f),
                radius = 250f + sin(t * 0.004).toFloat() * 40f,
                center = Offset(
                    size.width * 0.2f + cos(t * 0.003).toFloat() * 60f,
                    size.height * 0.3f + sin(t * 0.005).toFloat() * 40f
                )
            )
            drawCircle(
                color = Accent.copy(alpha = 0.08f),
                radius = 200f + cos(t * 0.003).toFloat() * 30f,
                center = Offset(
                    size.width * 0.8f + sin(t * 0.004).toFloat() * 50f,
                    size.height * 0.7f
                )
            )
            drawCircle(
                color = PrimaryLight.copy(alpha = 0.06f),
                radius = 150f,
                center = Offset(
                    size.width * 0.5f,
                    size.height * 0.1f + cos(t * 0.003).toFloat() * 20f
                )
            )
        }

        // Small floating particles
        Canvas(modifier = Modifier.fillMaxSize()) {
            val t = particleTime
            for (i in 0 until 10) {
                val phase = i * 0.7f
                val x = ((0.1f + i * 0.09f + sin(t * 0.002 + phase).toFloat() * 0.05f) % 1f) * size.width
                val y = ((0.1f + i * 0.085f + cos(t * 0.0015 + phase).toFloat() * 0.04f) % 1f) * size.height
                drawCircle(
                    color = Primary.copy(alpha = 0.08f + sin(t * 0.003 + phase).toFloat() * 0.04f),
                    radius = 6f + sin(t * 0.005 + phase).toFloat() * 3f,
                    center = Offset(x, y)
                )
            }
        }

        // Settings gear top-right
        IconButton(
            onClick = {
                gearPressed = true
                onNavigateToSettings()
            },
            modifier = Modifier
                .align(Alignment.TopEnd)
                .padding(top = 48.dp, end = 16.dp)
        ) {
            Icon(
                imageVector = Icons.Default.Settings,
                contentDescription = "Settings",
                tint = TextPrimary,
                modifier = Modifier
                    .size(28.dp)
                    .rotate(gearRotation)
            )
        }

        // Center content
        Column(
            modifier = Modifier
                .fillMaxSize()
                .padding(horizontal = 32.dp),
            horizontalAlignment = Alignment.CenterHorizontally,
            verticalArrangement = Arrangement.Center
        ) {
            // Animated gradient heading
            AnimatedVisibility(
                visible = showHeading,
                enter = fadeIn(tween(600)) + slideInVertically(
                    initialOffsetY = { 60 },
                    animationSpec = spring(dampingRatio = 0.6f, stiffness = 200f)
                )
            ) {
                val gradientColors = listOf(
                    TextPrimary,
                    Primary,
                    Accent,
                    PrimaryLight,
                    TextPrimary
                )
                Text(
                    text = "How can I help?",
                    style = MaterialTheme.typography.headlineLarge.copy(
                        brush = Brush.linearGradient(
                            colors = gradientColors,
                            start = Offset(gradientShift * 800f, 0f),
                            end = Offset(gradientShift * 800f + 400f, 100f)
                        )
                    ),
                    fontWeight = FontWeight.Bold,
                    fontSize = 32.sp
                )
            }

            Spacer(modifier = Modifier.height(32.dp))

            // Animated text input
            AnimatedVisibility(
                visible = showInput,
                enter = fadeIn(tween(500)) + slideInVertically(
                    initialOffsetY = { 40 },
                    animationSpec = spring(dampingRatio = 0.7f, stiffness = 250f)
                )
            ) {
                Box(
                    modifier = Modifier
                        .fillMaxWidth()
                        .height(56.dp)
                        .clip(RoundedCornerShape(16.dp))
                        .border(
                            width = if (isFocused) 2.dp else 1.5.dp,
                            color = Primary.copy(alpha = borderAlpha),
                            shape = RoundedCornerShape(16.dp)
                        )
                        .background(CardSurface.copy(alpha = if (isFocused) 0.9f else 0.6f))
                        .padding(horizontal = 20.dp),
                    contentAlignment = Alignment.CenterStart
                ) {
                    if (textInput.isEmpty()) {
                        Text(
                            text = "Type a command...",
                            style = MaterialTheme.typography.bodyLarge,
                            color = TextSecondary
                        )
                    }
                    BasicTextField(
                        value = textInput,
                        onValueChange = { textInput = it },
                        modifier = Modifier
                            .fillMaxWidth()
                            .onFocusChanged { isFocused = it.isFocused },
                        textStyle = TextStyle(fontSize = 16.sp, color = TextPrimary),
                        singleLine = true,
                        cursorBrush = SolidColor(Primary)
                    )
                }
            }

            Spacer(modifier = Modifier.height(32.dp))

            // Pulsing mic button with glow
            AnimatedVisibility(
                visible = showMic,
                enter = fadeIn(tween(400)) + slideInVertically(
                    initialOffsetY = { 80 },
                    animationSpec = spring(dampingRatio = 0.4f, stiffness = 200f)
                )
            ) {
                Box(contentAlignment = Alignment.Center) {
                    // Outer glow ring
                    Box(
                        modifier = Modifier
                            .size(90.dp)
                            .scale(micScale * 1.1f)
                            .alpha(micGlow * 0.25f)
                            .clip(RoundedCornerShape(20.dp))
                            .background(
                                Brush.radialGradient(
                                    colors = listOf(Primary.copy(alpha = 0.4f), Color.Transparent)
                                )
                            )
                    )
                    // Second glow ring
                    Box(
                        modifier = Modifier
                            .size(78.dp)
                            .scale(micScale)
                            .alpha(micGlow * 0.15f)
                            .clip(RoundedCornerShape(18.dp))
                            .background(Primary.copy(alpha = 0.2f))
                    )
                    // Main button
                    Box(
                        modifier = Modifier
                            .size(64.dp)
                            .scale(micPressScale)
                            .clip(RoundedCornerShape(16.dp))
                            .background(
                                Brush.linearGradient(
                                    colors = listOf(Primary, Accent)
                                )
                            )
                            .pointerInput(Unit) {
                                detectTapGestures(
                                    onPress = {
                                        micPressed = true
                                        tryAwaitRelease()
                                        micPressed = false
                                        if (textInput.isNotBlank()) {
                                            OverlayService.instance?.agentLoop?.onVoiceResult(textInput)
                                            textInput = ""
                                        } else {
                                            val overlay = OverlayService.instance
                                            if (overlay != null) {
                                                overlay.speechHelper.onResult = { transcription ->
                                                    overlay.agentLoop.onVoiceResult(transcription)
                                                }
                                                overlay.speechHelper.startListening()
                                            }
                                        }
                                    }
                                )
                            },
                        contentAlignment = Alignment.Center
                    ) {
                        Icon(
                            imageVector = Icons.Default.Mic,
                            contentDescription = "Voice input",
                            tint = Color.White,
                            modifier = Modifier.size(28.dp)
                        )
                    }
                }
            }
        }
    }
}
