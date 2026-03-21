package com.pilot.app

import android.os.Bundle
import androidx.activity.ComponentActivity
import androidx.activity.compose.setContent
import androidx.activity.enableEdgeToEdge
import androidx.compose.runtime.getValue
import androidx.compose.runtime.mutableStateOf
import androidx.compose.runtime.remember
import androidx.compose.runtime.setValue
import com.pilot.app.ui.screens.PermissionScreen
import com.pilot.app.ui.screens.SettingsScreen
import com.pilot.app.ui.theme.PilotTheme
import com.pilot.app.util.PermissionHelper
import dagger.hilt.android.AndroidEntryPoint

@AndroidEntryPoint
class MainActivity : ComponentActivity() {

    override fun onCreate(savedInstanceState: Bundle?) {
        super.onCreate(savedInstanceState)
        enableEdgeToEdge()

        setContent {
            PilotTheme {
                var permissionsGranted by remember {
                    mutableStateOf(checkAllPermissions())
                }

                if (permissionsGranted) {
                    SettingsScreen()
                } else {
                    PermissionScreen(
                        onAllGranted = { permissionsGranted = true }
                    )
                }
            }
        }
    }

    private fun checkAllPermissions(): Boolean {
        return PermissionHelper.isAccessibilityEnabled(this) &&
                PermissionHelper.isOverlayEnabled(this)
    }
}
