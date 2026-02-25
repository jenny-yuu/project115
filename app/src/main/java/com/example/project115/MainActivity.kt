package com.example.project115

import android.os.Bundle
import com.google.firebase.FirebaseApp
import androidx.activity.ComponentActivity
import androidx.activity.compose.setContent
import androidx.compose.material3.*
import androidx.compose.runtime.Composable
import androidx.lifecycle.viewmodel.compose.viewModel
import com.example.project115.viewmodel.MainViewModel
import androidx.navigation.NavType
import androidx.navigation.compose.NavHost
import androidx.navigation.compose.composable
import androidx.navigation.compose.rememberNavController
import androidx.navigation.navArgument
import com.example.project115.ui.screens.EnvironmentScreen
import com.example.project115.ui.screens.HomeScreen
import com.example.project115.ui.screens.SettingsScreen
import com.example.project115.ui.screens.StationDetailScreen
import java.net.URLDecoder
import java.net.URLEncoder
import java.nio.charset.StandardCharsets

class MainActivity : ComponentActivity() {
    override fun onCreate(savedInstanceState: Bundle?) {
        super.onCreate(savedInstanceState)
        FirebaseApp.initializeApp(this)
        
        setContent { 
            val viewModel: MainViewModel = viewModel()
            Project115App(viewModel)
        }
    }
}

private object Routes {
    const val HOME = "home"
    const val SETTINGS = "settings"
    const val STATION_DETAIL = "stationDetail/{stationName}/{lineName}/{health}/{delayMin}"
    const val ENV = "environment/{stationName}/{lineName}"

    fun stationDetail(stationName: String, lineName: String, health: String, delayMin: Int): String {
        val s = URLEncoder.encode(stationName, StandardCharsets.UTF_8.toString())
        val l = URLEncoder.encode(lineName, StandardCharsets.UTF_8.toString())
        return "stationDetail/$s/$l/$health/$delayMin"
    }

    fun env(stationName: String, lineName: String): String {
        val s = URLEncoder.encode(stationName, StandardCharsets.UTF_8.toString())
        val l = URLEncoder.encode(lineName, StandardCharsets.UTF_8.toString())
        return "environment/$s/$l"
    }
}

@Composable
fun Project115App(viewModel: MainViewModel) {
    MaterialTheme {
        val nav = rememberNavController()

        NavHost(navController = nav, startDestination = Routes.HOME) {

            composable(Routes.HOME) {
                HomeScreen(
                    viewModel = viewModel,
                    onOpenSettings = { nav.navigate(Routes.SETTINGS) },
                    onOpenStation = { stationName, lineName, health, delayMin ->
                        nav.navigate(Routes.stationDetail(stationName, lineName, health, delayMin))
                    }
                )
            }

            composable(Routes.SETTINGS) {
                SettingsScreen(onBack = { nav.popBackStack() })
            }

            composable(
                route = Routes.STATION_DETAIL,
                arguments = listOf(
                    navArgument("stationName") { type = NavType.StringType },
                    navArgument("lineName") { type = NavType.StringType },
                    navArgument("health") { type = NavType.StringType },
                    navArgument("delayMin") { type = NavType.IntType },
                )
            ) { entry ->
                val stationName = URLDecoder.decode(entry.arguments?.getString("stationName") ?: "未知車站", "UTF-8")
                val lineName = URLDecoder.decode(entry.arguments?.getString("lineName") ?: "未知路線", "UTF-8")
                val health = entry.arguments?.getString("health") ?: "DELAY"
                val delayMin = entry.arguments?.getInt("delayMin") ?: 0

                StationDetailScreen(
                    viewModel = viewModel,
                    stationName = stationName,
                    lineName = lineName,
                    health = health,
                    delayMinutes = delayMin,
                    onBack = { nav.popBackStack() },         // ✅ 一定要是這個
                    onOpenEnvironment = { nav.navigate(Routes.env(stationName, lineName)) }
                )
            }

            composable(
                route = Routes.ENV,
                arguments = listOf(
                    navArgument("stationName") { type = NavType.StringType },
                    navArgument("lineName") { type = NavType.StringType },
                )
            ) { entry ->
                val stationName = URLDecoder.decode(entry.arguments?.getString("stationName") ?: "未知車站", "UTF-8")
                val lineName = URLDecoder.decode(entry.arguments?.getString("lineName") ?: "未知路線", "UTF-8")

                EnvironmentScreen(
                    viewModel = viewModel,
                    stationName = stationName,
                    lineName = lineName,
                    onBack = { nav.popBackStack() }
                )
            }
        }
    }
}