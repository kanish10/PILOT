package com.pilot.app.ui.screens

import androidx.compose.foundation.background
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.Row
import androidx.compose.foundation.layout.Spacer
import androidx.compose.foundation.layout.fillMaxSize
import androidx.compose.foundation.layout.fillMaxWidth
import androidx.compose.foundation.layout.height
import androidx.compose.foundation.layout.padding
import androidx.compose.foundation.layout.size
import androidx.compose.foundation.layout.width
import androidx.compose.foundation.shape.CircleShape
import androidx.compose.foundation.shape.RoundedCornerShape
import androidx.compose.material.icons.Icons
import androidx.compose.material.icons.filled.Cloud
import androidx.compose.material.icons.filled.PlayArrow
import androidx.compose.material.icons.filled.Stop
import androidx.compose.material.icons.filled.VolumeUp
import androidx.compose.material3.Button
import androidx.compose.material3.ButtonDefaults
import androidx.compose.material3.Card
import androidx.compose.material3.CardDefaults
import androidx.compose.material3.Icon
import androidx.compose.material3.MaterialTheme
import androidx.compose.material3.OutlinedTextField
import androidx.compose.material3.OutlinedTextFieldDefaults
import androidx.compose.material3.Switch
import androidx.compose.material3.SwitchDefaults
import androidx.compose.material3.Text
import androidx.compose.runtime.Composable
import androidx.compose.runtime.collectAsState
import androidx.compose.runtime.getValue
import androidx.compose.runtime.mutableStateOf
import androidx.compose.runtime.remember
import androidx.compose.runtime.setValue
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.draw.clip
import androidx.compose.ui.graphics.Color
import androidx.compose.ui.platform.LocalContext
import androidx.compose.ui.text.font.FontWeight
import androidx.compose.ui.unit.dp
import androidx.compose.ui.unit.sp
import com.pilot.app.BuildConfig
import com.pilot.app.agent.TaskStateManager
import com.pilot.app.service.OverlayService
import com.pilot.app.ui.theme.PilotCard
import com.pilot.app.ui.theme.PilotGreen
import com.pilot.app.ui.theme.PilotOrange
import com.pilot.app.ui.theme.PilotPurple

@Composable
fun SettingsScreen() {
    val context = LocalContext.current
    var serverUrl by remember { mutableStateOf(BuildConfig.SERVER_URL) }
    var ttsEnabled by remember { mutableStateOf(true) }
    val isServiceRunning by TaskStateManager.isServiceRunning.collectAsState()
    val statusText by TaskStateManager.statusText.collectAsState()
    val glowState by TaskStateManager.glowState.collectAsState()

    Column(
        modifier = Modifier
            .fillMaxSize()
            .background(MaterialTheme.colorScheme.background)
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
        Spacer(modifier = Modifier.height(4.dp))
        Text(
            text = "Control Center",
            fontSize = 16.sp,
            color = MaterialTheme.colorScheme.onBackground.copy(alpha = 0.7f)
        )

        Spacer(modifier = Modifier.height(32.dp))

        // Server URL
        Card(
            modifier = Modifier.fillMaxWidth(),
            shape = RoundedCornerShape(16.dp),
            colors = CardDefaults.cardColors(containerColor = PilotCard)
        ) {
            Column(modifier = Modifier.padding(16.dp)) {
                Row(verticalAlignment = Alignment.CenterVertically) {
                    Icon(
                        imageVector = Icons.Default.Cloud,
                        contentDescription = null,
                        tint = PilotPurple,
                        modifier = Modifier
                            .size(36.dp)
                            .clip(CircleShape)
                            .background(PilotPurple.copy(alpha = 0.15f))
                            .padding(8.dp)
                    )
                    Spacer(modifier = Modifier.width(12.dp))
                    Text("Server Connection", fontWeight = FontWeight.Medium, fontSize = 15.sp)
                }
                Spacer(modifier = Modifier.height(12.dp))
                OutlinedTextField(
                    value = serverUrl,
                    onValueChange = {
                        serverUrl = it
                        OverlayService.instance?.agentLoop?.updateServerUrl(it)
                    },
                    label = { Text("Server URL") },
                    singleLine = true,
                    modifier = Modifier.fillMaxWidth(),
                    shape = RoundedCornerShape(12.dp),
                    colors = OutlinedTextFieldDefaults.colors(
                        focusedBorderColor = PilotPurple,
                        cursorColor = PilotPurple
                    )
                )
            }
        }

        Spacer(modifier = Modifier.height(16.dp))

        // TTS Toggle
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
                    imageVector = Icons.Default.VolumeUp,
                    contentDescription = null,
                    tint = PilotPurple,
                    modifier = Modifier
                        .size(36.dp)
                        .clip(CircleShape)
                        .background(PilotPurple.copy(alpha = 0.15f))
                        .padding(8.dp)
                )
                Spacer(modifier = Modifier.width(12.dp))
                Column(modifier = Modifier.weight(1f)) {
                    Text("Voice Feedback", fontWeight = FontWeight.Medium, fontSize = 15.sp)
                    Text(
                        "Speak status updates aloud",
                        fontSize = 12.sp,
                        color = MaterialTheme.colorScheme.onSurface.copy(alpha = 0.6f)
                    )
                }
                Switch(
                    checked = ttsEnabled,
                    onCheckedChange = {
                        ttsEnabled = it
                        OverlayService.instance?.ttsHelper?.enabled = it
                    },
                    colors = SwitchDefaults.colors(checkedTrackColor = PilotPurple)
                )
            }
        }

        Spacer(modifier = Modifier.height(24.dp))

        // Start/Stop overlay
        Button(
            onClick = {
                if (isServiceRunning) {
                    OverlayService.stop(context)
                    TaskStateManager.setServiceRunning(false)
                } else {
                    OverlayService.start(context)
                    TaskStateManager.setServiceRunning(true)
                }
            },
            modifier = Modifier
                .fillMaxWidth()
                .height(56.dp),
            shape = RoundedCornerShape(16.dp),
            colors = ButtonDefaults.buttonColors(
                containerColor = if (isServiceRunning) PilotOrange else PilotGreen
            )
        ) {
            Icon(
                imageVector = if (isServiceRunning) Icons.Default.Stop else Icons.Default.PlayArrow,
                contentDescription = null,
                modifier = Modifier.size(24.dp)
            )
            Spacer(modifier = Modifier.width(8.dp))
            Text(
                text = if (isServiceRunning) "Stop PILOT" else "Start PILOT",
                fontSize = 16.sp,
                fontWeight = FontWeight.SemiBold
            )
        }

        Spacer(modifier = Modifier.height(24.dp))

        // Status info
        if (isServiceRunning) {
            Card(
                modifier = Modifier.fillMaxWidth(),
                shape = RoundedCornerShape(16.dp),
                colors = CardDefaults.cardColors(containerColor = PilotCard)
            ) {
                Column(modifier = Modifier.padding(16.dp)) {
                    Text(
                        "Status",
                        fontWeight = FontWeight.Medium,
                        fontSize = 14.sp,
                        color = MaterialTheme.colorScheme.onSurface.copy(alpha = 0.6f)
                    )
                    Spacer(modifier = Modifier.height(8.dp))
                    Row(verticalAlignment = Alignment.CenterVertically) {
                        val dotColor = when (glowState) {
                            com.pilot.app.model.GlowState.IDLE -> Color.Gray
                            com.pilot.app.model.GlowState.LISTENING -> Color(0xFF00CEFF)
                            com.pilot.app.model.GlowState.WORKING -> PilotPurple
                            com.pilot.app.model.GlowState.DONE -> PilotGreen
                            com.pilot.app.model.GlowState.ERROR -> PilotOrange
                        }
                        Spacer(
                            modifier = Modifier
                                .size(10.dp)
                                .clip(CircleShape)
                                .background(dotColor)
                        )
                        Spacer(modifier = Modifier.width(8.dp))
                        Text(
                            text = glowState.name,
                            fontSize = 14.sp,
                            fontWeight = FontWeight.Medium
                        )
                    }
                    if (statusText.isNotBlank()) {
                        Spacer(modifier = Modifier.height(4.dp))
                        Text(
                            text = statusText,
                            fontSize = 13.sp,
                            color = MaterialTheme.colorScheme.onSurface.copy(alpha = 0.7f)
                        )
                    }
                }
            }
        }
    }
}
