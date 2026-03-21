package com.pilot.app

import android.content.Context
import android.os.Bundle
import androidx.activity.ComponentActivity
import androidx.activity.compose.setContent
import androidx.activity.enableEdgeToEdge
import androidx.compose.runtime.Composable
import androidx.compose.runtime.remember
import androidx.compose.ui.platform.LocalContext
import androidx.navigation.compose.NavHost
import androidx.navigation.compose.composable
import androidx.navigation.compose.rememberNavController
import com.pilot.app.service.OverlayService
import com.pilot.app.ui.screens.HomeScreen
import com.pilot.app.ui.screens.LandingScreen
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
                PilotNavigation()
            }
        }
    }
}

private object Routes {
    const val LANDING = "landing"
    const val PERMISSIONS = "permissions"
    const val HOME = "home"
    const val SETTINGS = "settings"
}

@Composable
private fun PilotNavigation() {
    val context = LocalContext.current
    val navController = rememberNavController()

    val isFirstBoot = remember { !hasCompletedOnboarding(context) }
    val permissionsGranted = remember {
        PermissionHelper.isAccessibilityEnabled(context) &&
                PermissionHelper.isOverlayEnabled(context)
    }

    val startDestination = when {
        isFirstBoot -> Routes.LANDING
        !permissionsGranted -> Routes.PERMISSIONS
        else -> Routes.HOME
    }

    NavHost(navController = navController, startDestination = startDestination) {
        composable(Routes.LANDING) {
            LandingScreen(
                onGetStarted = {
                    setOnboardingCompleted(context)
                    navController.navigate(Routes.PERMISSIONS) {
                        popUpTo(Routes.LANDING) { inclusive = true }
                    }
                }
            )
        }

        composable(Routes.PERMISSIONS) {
            PermissionScreen(
                onAllGranted = {
                    try { OverlayService.start(context) } catch (_: Exception) {}
                    navController.navigate(Routes.HOME) {
                        popUpTo(Routes.PERMISSIONS) { inclusive = true }
                    }
                }
            )
        }

        composable(Routes.HOME) {
            HomeScreen(
                onNavigateToSettings = {
                    navController.navigate(Routes.SETTINGS)
                }
            )
        }

        composable(Routes.SETTINGS) {
            SettingsScreen(
                onBack = { navController.popBackStack() }
            )
        }
    }
}

private const val PREFS_NAME = "pilot_prefs"
private const val KEY_ONBOARDING_DONE = "onboarding_completed"

private fun hasCompletedOnboarding(context: Context): Boolean {
    val prefs = context.getSharedPreferences(PREFS_NAME, Context.MODE_PRIVATE)
    return prefs.getBoolean(KEY_ONBOARDING_DONE, false)
}

private fun setOnboardingCompleted(context: Context) {
    val prefs = context.getSharedPreferences(PREFS_NAME, Context.MODE_PRIVATE)
    prefs.edit().putBoolean(KEY_ONBOARDING_DONE, true).apply()
}
