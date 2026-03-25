package com.example.project115.ui.model

enum class StationHealth { NORMAL, DELAY, SUSPENDED }

data class LineSummary(
    val name: String,
    val delayCount: Int,
    val suspendCount: Int
)

data class StationStatus(
    val stationName: String,
    val health: StationHealth,
    val delayMinutes: Int? = null
)

data class WeatherNow(
    val tempC: Int,
    val desc: String,
    val alertTitle: String
)

data class ForecastCard(
    val weekday: String,
    val tempC: Int,
    val rainProb: Int
)

data class CommuteSlot(
    val title: String,
    val station: String,
    val timeRange: String,
    val enabled: Boolean
)