package com.pilot.app.ui.screens

import android.Manifest
import android.content.pm.PackageManager
import android.os.Build
import androidx.activity.compose.rememberLauncherForActivityResult
import androidx.activity.result.contract.ActivityResultContracts
import androidx.compose.foundation.background
import androidx.compose.foundation.layout.Arrangement
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
import androidx.compose.material.icons.filled.Accessibility
import androidx.compose.material.icons.filled.CheckCircle
import androidx.compose.material.icons.filled.Layers
import androidx.compose.material.icons.filled.Mic
import androidx.compose.material.icons.filled.Notifications
import androidx.compose.material3.Button
import androidx.compose.material3.ButtonDefaults
import androidx.compose.material3.Card
import androidx.compose.material3.CardDefaults
import androidx.compose.material3.Icon
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
import androidx.compose.ui.draw.clip
import androidx.compose.ui.graphics.vector.ImageVector
import androidx.compose.ui.platform.LocalContext
import androidx.compose.ui.text.font.FontWeight
import androidx.compose.ui.unit.dp
import androidx.compose.ui.unit.sp
import androidx.core.content.ContextCompat
import androidx.lifecycle.Lifecycle
import androidx.lifecycle.compose.LifecycleEventEffect
import com.pilot.app.ui.theme.PilotCard
import com.pilot.app.ui.theme.PilotGreen
import com.pilot.app.ui.theme.PilotPurple
import com.pilot.app.util.PermissionHelper

@Composable
fun PermissionScreen(
    onAllGranted: () -> Unit
) {
    val context = LocalContext.current
    var accessibilityEnabled by remember { mutableStateOf(false) }
    var overlayEnabled by remember { mutableStateOf(false) }
    var microphoneGranted by remember { mutableStateOf(false) }
    var notificationGranted by remember { mutableStateOf(false) }

    val micLauncher = rememberLauncherForActivityResult(
        ActivityResultContracts.RequestPermission()
    ) { granted ->
        microphoneGranted = granted
    }

    val notifLauncher = rememberLauncherForActivityResult(
        ActivityResultContracts.RequestPermission()
    ) { granted ->
        notificationGranted = granted
    }

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

    LifecycleEventEffect(Lifecycle.Event.ON_RESUME) {
        refreshPermissions()
    }

    LaunchedEffect(accessibilityEnabled, overlayEnabled, microphoneGranted, notificationGranted) {
        if (accessibilityEnabled && overlayEnabled && microphoneGranted && notificationGranted) {
            onAllGranted()
        }
    }

    Column(
        modifier = Modifier
            .fillMaxSize()
            .background(MaterialTheme.colorScheme.background)
            .verticalScroll(rememberScrollState())
            .padding(24.dp),
        horizontalAlignment = Alignment.CenterHorizontally
    ) {
        Spacer(modifier = Modifier.height(48.dp))

        Text(
            text = "PILOT",
            fontSize = 36.sp,
            fontWeight = FontWeight.Bold,
            color = PilotPurple
        )
        Spacer(modifier = Modifier.height(8.dp))
        Text(
            text = "AI Phone Automation",
            fontSize = 16.sp,
            color = MaterialTheme.colorScheme.onBackground.copy(alpha = 0.7f)
        )

        Spacer(modifier = Modifier.height(40.dp))

        Text(
            text = "Grant Permissions",
            fontSize = 20.sp,
            fontWeight = FontWeight.SemiBold,
            color = MaterialTheme.colorScheme.onBackground
        )
        Spacer(modifier = Modifier.height(8.dp))
        Text(
            text = "PILOT needs these permissions to read and control your screen",
            fontSize = 14.sp,
            color = MaterialTheme.colorScheme.onBackground.copy(alpha = 0.6f),
            modifier = Modifier.padding(horizontal = 16.dp)
        )

        Spacer(modifier = Modifier.height(24.dp))

        PermissionItem(
            title = "Accessibility Service",
            description = "Reads screen content and performs actions",
            icon = Icons.Default.Accessibility,
            granted = accessibilityEnabled,
            onRequest = { PermissionHelper.openAccessibilitySettings(context) }
        )

        Spacer(modifier = Modifier.height(12.dp))

        PermissionItem(
            title = "Display Over Apps",
            description = "Shows floating button and glow border",
            icon = Icons.Default.Layers,
            granted = overlayEnabled,
            onRequest = { PermissionHelper.openOverlaySettings(context) }
        )

        Spacer(modifier = Modifier.height(12.dp))

        PermissionItem(
            title = "Microphone",
            description = "Listens to your voice commands",
            icon = Icons.Default.Mic,
            granted = microphoneGranted,
            onRequest = { micLauncher.launch(Manifest.permission.RECORD_AUDIO) }
        )

        if (Build.VERSION.SDK_INT >= Build.VERSION_CODES.TIRAMISU) {
            Spacer(modifier = Modifier.height(12.dp))

            PermissionItem(
                title = "Notifications",
                description = "Shows overlay service notification",
                icon = Icons.Default.Notifications,
                granted = notificationGranted,
                onRequest = { notifLauncher.launch(Manifest.permission.POST_NOTIFICATIONS) }
            )
        }

        Spacer(modifier = Modifier.height(32.dp))

        val allGranted = accessibilityEnabled && overlayEnabled && microphoneGranted && notificationGranted
        if (allGranted) {
            Button(
                onClick = onAllGranted,
                modifier = Modifier
                    .fillMaxWidth()
                    .height(52.dp),
                shape = RoundedCornerShape(16.dp),
                colors = ButtonDefaults.buttonColors(containerColor = PilotGreen)
            ) {
                Text("Continue", fontSize = 16.sp, fontWeight = FontWeight.SemiBold)
            }
        }
    }
}

@Composable
private fun PermissionItem(
    title: String,
    description: String,
    icon: ImageVector,
    granted: Boolean,
    onRequest: () -> Unit
) {
    Card(
        modifier = Modifier.fillMaxWidth(),
        shape = RoundedCornerShape(16.dp),
        colors = CardDefaults.cardColors(containerColor = PilotCard)
    ) {
        Row(
            modifier = Modifier
                .fillMaxWidth()
                .padding(16.dp),
            verticalAlignment = Alignment.CenterVertically
        ) {
            Icon(
                imageVector = icon,
                contentDescription = null,
                tint = if (granted) PilotGreen else PilotPurple,
                modifier = Modifier
                    .size(40.dp)
                    .clip(CircleShape)
                    .background(
                        if (granted) PilotGreen.copy(alpha = 0.15f)
                        else PilotPurple.copy(alpha = 0.15f)
                    )
                    .padding(8.dp)
            )

            Spacer(modifier = Modifier.width(16.dp))

            Column(modifier = Modifier.weight(1f)) {
                Text(
                    text = title,
                    fontSize = 15.sp,
                    fontWeight = FontWeight.Medium,
                    color = MaterialTheme.colorScheme.onSurface
                )
                Text(
                    text = description,
                    fontSize = 12.sp,
                    color = MaterialTheme.colorScheme.onSurface.copy(alpha = 0.6f)
                )
            }

            Spacer(modifier = Modifier.width(8.dp))

            if (granted) {
                Icon(
                    imageVector = Icons.Default.CheckCircle,
                    contentDescription = "Granted",
                    tint = PilotGreen,
                    modifier = Modifier.size(28.dp)
                )
            } else {
                Button(
                    onClick = onRequest,
                    shape = RoundedCornerShape(12.dp),
                    colors = ButtonDefaults.buttonColors(containerColor = PilotPurple),
                    modifier = Modifier.height(36.dp)
                ) {
                    Text("Grant", fontSize = 13.sp)
                }
            }
        }
    }
}
