package com.example.project115.data

import com.google.firebase.firestore.FirebaseFirestore
import kotlinx.coroutines.tasks.await
import kotlinx.coroutines.flow.Flow
import kotlinx.coroutines.flow.MutableStateFlow
import kotlinx.coroutines.flow.asStateFlow
import android.util.Log

data class WeatherInfo(
    val rain_1hr: Double = 0.0,
    val rain_24hr: Double = 0.0,
    val wind_speed: Double = 0.0,
    val peak_gust_speed: Double = 0.0,
    val temperature: Double = 0.0,
    val temp_feel: String = "舒適",
    val risk_level: String = "Normal",
    val description: String = "多雲",
    val updated_at: String = ""
)

data class ForecastInfo(
    val wx: String = "多雲",
    val pop: Int = 0,
    val min_t: Int = 20,
    val max_t: Int = 25
)

data class LiveDelayTrain(
    val TrainNo: String = "",
    val DelayTime: Int = 0
)

data class TransfersInfo(
    val external: List<String> = emptyList(),
    val internal: List<String> = emptyList()
)

data class OfficialTransfersInfo(
    val status: String = "No Data",
    val data: Map<String, List<String>> = emptyMap()
)

data class EarthquakeInfo(
    val intensity: Int = 0,
    val origin_time: String = "",
    val dist_km: Double = 0.0
)

data class Station(
    val id: String = "",
    val StationID: String = "",
    val StationName: String = "",
    val Route: String = "未知",
    val Sequence: Int = 0,
    val Lat: Double = 0.0,
    val Lon: Double = 0.0,
    val is_delayed: Boolean = false,
    val live_delay_max_minutes: Int = 0,
    val health_light: String = "正常",
    val weather: WeatherInfo = WeatherInfo(),
    val forecast: ForecastInfo = ForecastInfo(),
    val live_delay_trains: List<LiveDelayTrain> = emptyList(),
    val transfers: TransfersInfo = TransfersInfo(),
    val official_transfers: OfficialTransfersInfo = OfficialTransfersInfo(),
    val earthquake: EarthquakeInfo = EarthquakeInfo()
)

class StationRepository {
    private val db = FirebaseFirestore.getInstance()
    private val collectionName = "stations"

    private val _stationsFlow = MutableStateFlow<List<Station>>(emptyList())
    val stationsFlow: Flow<List<Station>> = _stationsFlow.asStateFlow()

    private val _errorMessage = MutableStateFlow<String?>(null)
    val errorMessage: Flow<String?> = _errorMessage.asStateFlow()

    fun fetchStations() {
        Log.d("StationRepo", "開始聆聽 Firebase 'stations' 集合更新...")
        db.collection(collectionName)
            .addSnapshotListener { snapshot, e ->
                if (e != null) {
                    _errorMessage.value = "加載車站失敗: ${e.message}"
                    Log.e("StationRepo", "加載車站失敗", e)
                    return@addSnapshotListener
                }

                if (snapshot != null) {
                    var lastError: String? = null
                    val list = mutableListOf<Station>()
                    for (doc in snapshot.documents) {
                        try {
                            // 解析 Firebase 資料 (使用安全的轉型避免 RuntimeException)
                            val weatherMap = doc.get("weather") as? Map<String, Any> ?: emptyMap()
                            val weatherInfo = WeatherInfo(
                                rain_1hr = (weatherMap["rain_1hr"] as? Number)?.toDouble() ?: 0.0,
                                rain_24hr = (weatherMap["rain_24hr"] as? Number)?.toDouble() ?: 0.0,
                                wind_speed = (weatherMap["wind_speed"] as? Number)?.toDouble() ?: 0.0,
                                peak_gust_speed = (weatherMap["peak_gust_speed"] as? Number)?.toDouble() ?: 0.0,
                                temperature = (weatherMap["temperature"] as? Number)?.toDouble() ?: 0.0,
                                temp_feel = weatherMap["temp_feel"] as? String ?: "舒適",
                                risk_level = weatherMap["risk_level"] as? String ?: "Normal",
                                description = weatherMap["description"] as? String ?: "多雲",
                                updated_at = weatherMap["updated_at"] as? String ?: ""
                            )

                            val trainMaps = doc.get("live_delay_trains") as? List<Map<String, Any>> ?: emptyList()
                            val trains = trainMaps.map {
                                LiveDelayTrain(
                                    TrainNo = it["TrainNo"]?.toString() ?: "",
                                    DelayTime = (it["DelayTime"] as? Number)?.toInt() ?: 0
                                )
                            }
                            
                            val forecastMap = doc.get("forecast") as? Map<String, Any> ?: emptyMap()
                            val forecastInfo = ForecastInfo(
                                wx = forecastMap["wx"] as? String ?: "多雲",
                                pop = (forecastMap["pop"] as? Number)?.toInt() ?: 0,
                                min_t = (forecastMap["min_t"] as? Number)?.toInt() ?: 20,
                                max_t = (forecastMap["max_t"] as? Number)?.toInt() ?: 25
                            )

                            val transfersMap = doc.get("transfers") as? Map<String, Any> ?: emptyMap()
                            val externalTransfers = transfersMap["external"] as? List<String> ?: emptyList()
                            val internalTransfers = transfersMap["internal"] as? List<String> ?: emptyList()
                            val transfersInfo = TransfersInfo(
                                external = externalTransfers,
                                internal = internalTransfers
                            )

                            val officialMap = doc.get("official_transfers") as? Map<String, Any> ?: emptyMap()
                            val officialData = officialMap["data"] as? Map<String, List<String>> ?: emptyMap()
                            val officialTransfers = OfficialTransfersInfo(
                                status = officialMap["status"] as? String ?: "No Data",
                                data = officialData
                            )

                            val eqMap = doc.get("earthquake") as? Map<String, Any> ?: emptyMap()
                            val eqInfo = EarthquakeInfo(
                                intensity = (eqMap["intensity"] as? Number)?.toInt() ?: 0,
                                origin_time = eqMap["origin_time"] as? String ?: "",
                                dist_km = (eqMap["dist_km"] as? Number)?.toDouble() ?: 0.0
                            )

                            val station = Station(
                                id = doc.id,
                                StationID = doc.get("StationID")?.toString() ?: "",
                                StationName = doc.get("StationName")?.toString() ?: "",
                                Route = doc.get("Route")?.toString() ?: "未知",
                                Sequence = (doc.get("Sequence") as? Number)?.toInt() ?: 0,
                                Lat = (doc.get("Lat") as? Number)?.toDouble() ?: 0.0,
                                Lon = (doc.get("Lon") as? Number)?.toDouble() ?: 0.0,
                                is_delayed = doc.get("is_delayed") as? Boolean ?: false,
                                live_delay_max_minutes = (doc.get("live_delay_max_minutes") as? Number)?.toInt() ?: 0,
                                health_light = doc.get("health_light")?.toString() ?: "正常",
                                weather = weatherInfo,
                                forecast = forecastInfo,
                                live_delay_trains = trains,
                                transfers = transfersInfo,
                                official_transfers = officialTransfers,
                                earthquake = eqInfo
                            )
                            list.add(station)
                        } catch (ex: Exception) {
                            lastError = ex.message ?: ex.toString()
                            Log.e("StationRepo", "解析文件錯誤 ${doc.id}", ex)
                        }
                    }
                    
                    // 根據順序排序
                    val sortedList = list.sortedBy { it.Sequence }
                    _stationsFlow.value = sortedList
                    Log.d("StationRepo", "成功解析並發送 ${sortedList.size} 筆車站至 UI")

                    if (sortedList.isEmpty() && lastError != null) {
                        _errorMessage.value = "Parse Error: $lastError"
                    } else {
                        _errorMessage.value = "Loaded ${snapshot.documents.size} docs, Parsed ${sortedList.size}"
                    }
                }
            }
    }
}
