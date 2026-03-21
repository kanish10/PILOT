package com.pilot.app.ui.screens

import androidx.compose.animation.AnimatedVisibility
import androidx.compose.animation.core.Animatable
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
import androidx.compose.foundation.shape.CircleShape
import androidx.compose.foundation.shape.RoundedCornerShape
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
import androidx.compose.ui.graphics.Brush
import androidx.compose.ui.graphics.Color
import androidx.compose.ui.graphics.graphicsLayer
import androidx.compose.ui.input.pointer.pointerInput
import androidx.compose.ui.text.font.FontWeight
import androidx.compose.ui.unit.dp
import androidx.compose.ui.unit.sp
import com.pilot.app.ui.theme.Accent
import com.pilot.app.ui.theme.Primary
import com.pilot.app.ui.theme.PrimaryLight
import com.pilot.app.ui.theme.TextPrimary
import com.pilot.app.ui.theme.TextSecondary
import kotlinx.coroutines.delay
import kotlin.math.cos
import kotlin.math.sin
import kotlin.random.Random

private data class Particle(
    val x: Float, val y: Float, val radius: Float,
    val speedX: Float, val speedY: Float, val alpha: Float,
    val color: Color
)

@Composable
fun LandingScreen(onGetStarted: () -> Unit) {
    val infiniteTransition = rememberInfiniteTransition(label = "landing")

    // Staggered visibility states
    var showLogo by remember { mutableStateOf(false) }
    var showHi by remember { mutableStateOf(false) }
    var showWelcome by remember { mutableStateOf(false) }
    var showButton by remember { mutableStateOf(false) }

    LaunchedEffect(Unit) {
        delay(300); showLogo = true
        delay(400); showHi = true
        delay(300); showWelcome = true
        delay(400); showButton = true
    }

    // Floating particles
    val particles = remember {
        List(15) {
            Particle(
                x = Random.nextFloat(),
                y = Random.nextFloat(),
                radius = Random.nextFloat() * 20f + 8f,
                speedX = (Random.nextFloat() - 0.5f) * 0.3f,
                speedY = (Random.nextFloat() - 0.5f) * 0.2f,
                alpha = Random.nextFloat() * 0.15f + 0.05f,
                color = if (Random.nextBoolean()) Primary else Accent.copy(alpha = 0.5f)
            )
        }
    }

    val particleTime by infiniteTransition.animateFloat(
        initialValue = 0f, targetValue = 1000f,
        animationSpec = infiniteRepeatable(tween(60000, easing = LinearEasing)),
        label = "particles"
    )

    // Logo breathing glow
    val logoGlow by infiniteTransition.animateFloat(
        initialValue = 0.6f, targetValue = 1f,
        animationSpec = infiniteRepeatable(
            tween(2000, easing = FastOutSlowInEasing), RepeatMode.Reverse
        ), label = "glow"
    )

    val logoScale by infiniteTransition.animateFloat(
        initialValue = 1f, targetValue = 1.05f,
        animationSpec = infiniteRepeatable(
            tween(3000, easing = FastOutSlowInEasing), RepeatMode.Reverse
        ), label = "logoScale"
    )

    // Button shimmer
    val shimmerOffset by infiniteTransition.animateFloat(
        initialValue = -1f, targetValue = 2f,
        animationSpec = infiniteRepeatable(
            tween(2500, easing = LinearEasing)
        ), label = "shimmer"
    )

    // Button press
    var isPressed by remember { mutableStateOf(false) }
    val buttonScale by animateFloatAsState(
        targetValue = if (isPressed) 0.93f else 1f,
        animationSpec = spring(dampingRatio = 0.4f, stiffness = 800f),
        label = "btnScale"
    )

    Box(
        modifier = Modifier
            .fillMaxSize()
            .background(MaterialTheme.colorScheme.background)
    ) {
        // Floating particles layer
        Canvas(modifier = Modifier.fillMaxSize()) {
            particles.forEach { p ->
                val time = particleTime
                val x = ((p.x + p.speedX * time / 100f) % 1.3f) * size.width
                val y = ((p.y + p.speedY * time / 100f + sin(time * 0.01 + p.x * 10).toFloat() * 0.02f) % 1.3f) * size.height
                drawCircle(
                    color = p.color,
                    radius = p.radius * (1f + sin(time * 0.02 + p.radius).toFloat() * 0.3f),
                    center = Offset(x, y),
                    alpha = p.alpha
                )
            }
        }

        // Soft gradient orbs in background
        Canvas(
            modifier = Modifier
                .fillMaxSize()
                .blur(80.dp)
        ) {
            val time = particleTime
            drawCircle(
                color = Primary.copy(alpha = 0.12f),
                radius = 300f + sin(time * 0.005).toFloat() * 50f,
                center = Offset(
                    size.width * 0.3f + cos(time * 0.003).toFloat() * 40f,
                    size.height * 0.25f + sin(time * 0.004).toFloat() * 30f
                )
            )
            drawCircle(
                color = Accent.copy(alpha = 0.08f),
                radius = 250f + cos(time * 0.004).toFloat() * 40f,
                center = Offset(
                    size.width * 0.7f + sin(time * 0.003).toFloat() * 50f,
                    size.height * 0.65f + cos(time * 0.005).toFloat() * 35f
                )
            )
        }

        Column(
            modifier = Modifier
                .fillMaxSize()
                .padding(horizontal = 32.dp),
            horizontalAlignment = Alignment.CenterHorizontally,
            verticalArrangement = Arrangement.Center
        ) {
            Spacer(modifier = Modifier.weight(1f))

            // Animated logo with breathing glow
            AnimatedVisibility(
                visible = showLogo,
                enter = fadeIn(tween(800)) + slideInVertically(
                    initialOffsetY = { 80 },
                    animationSpec = spring(dampingRatio = 0.6f, stiffness = 200f)
                )
            ) {
                Box(contentAlignment = Alignment.Center) {
                    // Glow ring behind logo
                    Box(
                        modifier = Modifier
                            .size(140.dp)
                            .scale(logoScale * 1.1f)
                            .alpha(logoGlow * 0.4f)
                            .clip(CircleShape)
                            .background(
                                Brush.radialGradient(
                                    colors = listOf(Primary.copy(alpha = 0.3f), Color.Transparent)
                                )
                            )
                    )
                    Box(
                        modifier = Modifier
                            .size(120.dp)
                            .scale(logoScale)
                            .clip(CircleShape)
                            .border(3.dp, Primary.copy(alpha = logoGlow), CircleShape)
                            .background(Primary.copy(alpha = 0.06f)),
                        contentAlignment = Alignment.Center
                    ) {
                        Text(
                            text = "P",
                            fontSize = 48.sp,
                            fontWeight = FontWeight.Bold,
                            color = Primary
                        )
                    }
                }
            }

            Spacer(modifier = Modifier.height(48.dp))

            // Staggered "Hi"
            AnimatedVisibility(
                visible = showHi,
                enter = fadeIn(tween(600)) + slideInVertically(
                    initialOffsetY = { 40 },
                    animationSpec = spring(dampingRatio = 0.7f, stiffness = 300f)
                )
            ) {
                Text(
                    text = "Hi",
                    style = MaterialTheme.typography.headlineSmall,
                    color = TextSecondary
                )
            }

            Spacer(modifier = Modifier.height(8.dp))

            // Staggered "Welcome to Pilot"
            AnimatedVisibility(
                visible = showWelcome,
                enter = fadeIn(tween(800)) + slideInVertically(
                    initialOffsetY = { 60 },
                    animationSpec = spring(dampingRatio = 0.6f, stiffness = 200f)
                )
            ) {
                Text(
                    text = "Welcome to Pilot",
                    style = MaterialTheme.typography.displayMedium,
                    color = TextPrimary
                )
            }

            Spacer(modifier = Modifier.weight(1f))

            // Animated button with shimmer + bounce
            AnimatedVisibility(
                visible = showButton,
                enter = fadeIn(tween(600)) + slideInVertically(
                    initialOffsetY = { 100 },
                    animationSpec = spring(dampingRatio = 0.5f, stiffness = 200f)
                )
            ) {
                Box(
                    modifier = Modifier
                        .fillMaxWidth()
                        .height(56.dp)
                        .scale(buttonScale)
                        .clip(RoundedCornerShape(16.dp))
                        .background(
                            Brush.horizontalGradient(
                                colors = listOf(
                                    Primary,
                                    PrimaryLight,
                                    Accent,
                                    PrimaryLight,
                                    Primary
                                ),
                                startX = shimmerOffset * 1000f,
                                endX = (shimmerOffset + 0.6f) * 1000f
                            )
                        )
                        .pointerInput(Unit) {
                            detectTapGestures(
                                onPress = {
                                    isPressed = true
                                    tryAwaitRelease()
                                    isPressed = false
                                    onGetStarted()
                                }
                            )
                        },
                    contentAlignment = Alignment.Center
                ) {
                    Text(
                        text = "Getting Started",
                        style = MaterialTheme.typography.labelLarge,
                        color = Color.White
                    )
                }
            }

            Spacer(modifier = Modifier.height(48.dp))
        }
    }
}
