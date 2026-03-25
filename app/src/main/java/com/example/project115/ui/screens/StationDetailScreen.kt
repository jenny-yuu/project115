package com.example.project115.ui.screens

import android.os.Build
import androidx.compose.foundation.background
import androidx.lifecycle.compose.collectAsStateWithLifecycle
import com.example.project115.viewmodel.MainViewModel
import androidx.compose.foundation.clickable
import androidx.compose.foundation.layout.*
import androidx.compose.foundation.rememberScrollState
import androidx.compose.foundation.verticalScroll
import androidx.compose.material.icons.Icons
import androidx.compose.material.icons.filled.ArrowBackIosNew
import androidx.compose.material.icons.filled.DirectionsBus
import androidx.compose.material.icons.filled.DirectionsBike
import androidx.compose.material.icons.filled.LocalTaxi
import androidx.compose.material.icons.filled.Notifications
import androidx.compose.material.icons.filled.Train
import androidx.compose.material3.*
import androidx.compose.runtime.*
import androidx.compose.ui.Modifier
import androidx.compose.ui.graphics.Color
import androidx.compose.ui.text.font.FontWeight
import androidx.compose.ui.Alignment
import androidx.compose.ui.text.style.TextAlign
import androidx.compose.ui.unit.dp
import androidx.compose.ui.unit.sp
import com.example.project115.ui.design.*
import androidx.compose.foundation.layout.statusBarsPadding
import com.example.project115.R
import kotlinx.coroutines.Dispatchers
import kotlinx.coroutines.launch
import kotlinx.coroutines.withContext
import java.net.HttpURLConnection
import java.net.URL
import org.json.JSONObject
import android.util.Log
import androidx.annotation.RequiresApi
import androidx.activity.compose.rememberLauncherForActivityResult
import androidx.activity.result.contract.ActivityResultContracts
import android.app.NotificationChannel
import android.app.NotificationManager
import android.app.PendingIntent
import android.content.Context
import android.content.Intent
import androidx.core.app.NotificationCompat
import androidx.core.app.NotificationManagerCompat
import androidx.core.net.toUri
import androidx.core.content.ContextCompat
import android.Manifest
import android.content.pm.PackageManager

// 結構化資料類別 (放在最外層避免 Reference 錯誤)
data class TaskRoute(
    val type: String,
    val title: String,
    val priority: String,
    val departure: String = "",
    val duration: String = ""
)
data class AiAdviceData(
    val summary: String = "",
    val aiAdvice: String = "",
    val routes: List<TaskRoute> = emptyList(),
    val emergency: String = "",
    val navDest: String = "",
    val sources: String = ""
)

data class SimulationScenario(
    val type: String,
    val intensity: Int,
    val description: String
)

@RequiresApi(Build.VERSION_CODES.O)
@Composable
fun StationDetailScreen(
    viewModel: MainViewModel,
    stationName: String,
    lineName: String,
    health: String,     // "SUSPENDED"/"DELAY"
    delayMinutes: Int,
    onBack: () -> Unit,
    onOpenEnvironment: () -> Unit,
) {
    // 1. AI Assistant State
    val coroutineScope = rememberCoroutineScope()
    var aiResult by remember { mutableStateOf<AiAdviceData?>(null) }
    var isLoadingAi by remember { mutableStateOf(false) }
    var aiError by remember { mutableStateOf<String?>(null) }
    var recoveryTime by remember { mutableStateOf<String>("評估中") }
    var recoveryReason by remember { mutableStateOf<String>("") }
    var evidenceList by remember { mutableStateOf<List<JSONObject>>(emptyList()) }
    var showEvidenceDialog by remember { mutableStateOf(false) }
    var simulationConfig by remember { mutableStateOf<SimulationScenario?>(null) }
    var showSimulationDialog by remember { mutableStateOf(false) }

    // 2. 核心狀態判斷
    val stations by viewModel.stations.collectAsStateWithLifecycle()
    val currentStation = stations.find { it.StationName == stationName }
    val isSuspended =
        currentStation?.health_light == "紅燈" || health == "SUSPENDED" || (simulationConfig != null)
    val ringColor =
        if (isSuspended) DT.SuspendRed else if (currentStation?.is_delayed == true) DT.DelayYellow else DT.StatusGreen

    val actualDelay = currentStation?.live_delay_max_minutes ?: delayMinutes
    val weatherData = currentStation?.weather
    val temperatureStr = weatherData?.temperature?.let { "${it.toInt()}°C" } ?: "22°C"

    val rain1hr = if (simulationConfig?.type == "強降雨") simulationConfig!!.intensity.toDouble() else (weatherData?.rain_1hr ?: 0.0)
    val rainTagText = if (rain1hr > 40.0) "大豪雨" else if (rain1hr > 15.0) "大雨" else if (rain1hr > 0) "${if (simulationConfig?.type == "強降雨") "模擬" else ""}降雨中" else "雨量正常"
    val rainTagBg = if (rain1hr > 15.0) Color(0xFFFBE9E7) else Color(0xFFE8F5E9)
    val weatherDesc = weatherData?.description ?: "多雲"
    val eqMagnitude =
        if (simulationConfig?.type == "地震") simulationConfig!!.intensity 
        else if (currentStation?.earthquake != null && currentStation.earthquake.intensity > 0) currentStation.earthquake.intensity
        else if (isSuspended && simulationConfig == null) 4 
        else 0
    val eqText = if (eqMagnitude > 0) "震度 $eqMagnitude 級" else "正常"
    val eqBg = if (eqMagnitude > 0) Color(0xFFFBE9E7) else Color(0xFFE8F5E9)

    val ringFill =
        if (isSuspended) DT.RingInnerRed else if (currentStation?.is_delayed == true) DT.RingInnerYellow else Color(
            0xFFE8F5E9
        )
    val contentModifier = Modifier.fillMaxWidth(0.92f)
    val context = androidx.compose.ui.platform.LocalContext.current

    var hasNotificationPermission by remember {
        mutableStateOf(
            if (Build.VERSION.SDK_INT >= Build.VERSION_CODES.TIRAMISU) {
                ContextCompat.checkSelfPermission(
                    context,
                    Manifest.permission.POST_NOTIFICATIONS
                ) == PackageManager.PERMISSION_GRANTED
            } else {
                true
            }
        )
    }

    fun showDisasterNotification(scenario: SimulationScenario) {
        val builder = NotificationCompat.Builder(context, "disaster_alerts")
            .setSmallIcon(R.drawable.denryoku_mark)
            .setContentTitle("【災害預警】${scenario.type}警報")
            .setContentText("目前${stationName}因${scenario.description}暫停營運，請查看應變建議。")
            .setPriority(NotificationCompat.PRIORITY_HIGH)
            // .setAutoCancel(true) 這裡拿掉，讓點擊通知時不會自動消失（如果需要）
            .setCategory(NotificationCompat.CATEGORY_ALARM) // 設置為警報層級，停留時間較長
        
        NotificationManagerCompat.from(context).apply {
            try {
                notify(System.currentTimeMillis().toInt(), builder.build())
            } catch (e: SecurityException) {
                Log.e("Notification", "Permission missing: ${e.message}")
            }
        }
    }

    val permissionLauncher = rememberLauncherForActivityResult(
        contract = ActivityResultContracts.RequestPermission(),
        onResult = { isGranted ->
            hasNotificationPermission = isGranted
            if (isGranted && simulationConfig != null) {
                // If permission granted immediately after selecting a simulation, show the notification
                showDisasterNotification(simulationConfig!!) 
            }
        }
    )

    // 通知頻道初始化
    LaunchedEffect(Unit) {
        val channel = NotificationChannel(
            "disaster_alerts",
            "災害預警通知",
            NotificationManager.IMPORTANCE_HIGH
        ).apply {
            description = "用於模擬災害發生時的即時推播"
        }
        val notificationManager: NotificationManager =
            context.getSystemService(Context.NOTIFICATION_SERVICE) as NotificationManager
        notificationManager.createNotificationChannel(channel)
    }

    // 呼叫後端 AI 的核心函數
    suspend fun fetchAiAdvice() {
        // 1. 啟動回復時間推估 (僅在停駛或嚴重延誤時)
        if (isSuspended || actualDelay >= 20) {
            coroutineScope.launch(Dispatchers.IO) {
                try {
                    // 已連接雲端網址
                    val cloudUrl = "https://tra-assistant.onrender.com/predict_recovery"
                    val ips = listOf(cloudUrl, "http://10.0.2.2:5000/predict_recovery")
                    for (target in ips) {
                        try {
                            val url = URL(target)
                            val conn = url.openConnection() as HttpURLConnection
                            conn.requestMethod = "POST"
                            conn.setRequestProperty("Content-Type", "application/json")
                            conn.connectTimeout = 60000
                            conn.readTimeout = 60000
                            conn.doOutput = true
                            val param = JSONObject().apply {
                                put("station_name", stationName)
                                put(
                                    "query",
                                    if (simulationConfig != null) "目前因${simulationConfig!!.description}導致${stationName}營運中斷，請參考歷史經驗推估恢復時間。" else "目前地震或強降雨導致${stationName}營運中斷，請參考歷史經驗推估恢復時間。"
                                )
                                put("is_simulation", simulationConfig != null)
                                put("sim_type", simulationConfig?.type ?: "")
                                put("sim_intensity", simulationConfig?.intensity ?: 0)
                            }
                            conn.outputStream.write(param.toString().toByteArray())
                            if (conn.responseCode == 200) {
                                val resString = conn.inputStream.bufferedReader().readText()
                                val res = JSONObject(resString)
                                val time = res.optString("recovery_time", "評估中")
                                val reason = res.optString("reason", "")
                                val evArray = res.optJSONArray("evidence")
                                val list = mutableListOf<JSONObject>()
                                if (evArray != null) {
                                    for (j in 0 until evArray.length()) list.add(
                                        evArray.getJSONObject(
                                            j
                                        )
                                    )
                                }
                                withContext(Dispatchers.Main) {
                                    recoveryTime = time
                                    recoveryReason = reason
                                    evidenceList = list
                                }
                                break
                            }
                        } catch (_: Exception) {
                        }
                    }
                } catch (_: Exception) {
                }
            }
        }

        // 2. 獲取應變建議
        isLoadingAi = true
        aiError = null
        withContext(Dispatchers.IO) {
            try {
                // 已連接雲端網址
                // 優先連線至本機開發環境，以確保看到最新的計程車注入邏輯
                val localIp = "http://10.1.204.137:5000/ask_ai"
                val cloudUrl = "https://tra-assistant.onrender.com/ask_ai"
                val ips = listOf(localIp, cloudUrl, "http://10.0.2.2:5000/ask_ai")
                var success = false

                for (target in ips) {
                    try {
                        val url = URL(target)
                        val conn = url.openConnection() as HttpURLConnection
                        conn.requestMethod = "POST"
                        conn.setRequestProperty("Content-Type", "application/json")
                        conn.connectTimeout = 90000
                        conn.readTimeout = 90000
                        conn.doOutput = true

                        val official = currentStation?.official_transfers
                        val transfersText = if (official?.status == "Available") {
                            val details = official.data.entries.joinToString("; ") { (k, v) ->
                                val type = when (k) {
                                    "taxi" -> "計程車"
                                    "bus" -> "公車/客運"
                                    "rail" -> "鐵路/火車"
                                    "bike" -> "自行車"
                                    else -> k
                                }
                                "$type: ${v.joinToString("、")}"
                            }
                            "，官方轉乘：$details"
                        } else ""

                        val eqInfoStr = currentStation?.earthquake?.let { 
                            if (it.intensity > 0) "，地震：震度 ${it.intensity} 級" else ""
                        } ?: ""
                        val query =
                            "人在${stationName}，${if (isSuspended) "停駛" else "正常/延誤"}，天氣${weatherData?.description}${eqInfoStr}${transfersText}。"
                        val jsonParam = JSONObject().apply {
                            put("query", query)
                            put("delay_time", if (isSuspended) 999 else actualDelay)
                            put("is_suspended", isSuspended)
                            put("station_name", stationName)
                            put("sim_type", simulationConfig?.type ?: "")
                            put("sim_intensity", simulationConfig?.intensity ?: 0)
                        }

                        conn.outputStream.write(jsonParam.toString().toByteArray())

                        if (conn.responseCode == 200) {
                            val response = conn.inputStream.bufferedReader().readText()
                            val jsonResponse = JSONObject(response)
                            val structJson = jsonResponse.getJSONObject("structured")

                            val routesArray = structJson.optJSONArray("routes")
                            val rList = mutableListOf<TaskRoute>()
                            if (routesArray != null) {
                                for (i in 0 until routesArray.length()) {
                                    val r = routesArray.getJSONObject(i)
                                    rList.add(
                                        TaskRoute(
                                            type = r.optString("type", "other"),
                                            title = r.optString("title", ""),
                                            priority = r.optString("priority", "建議"),
                                            departure = r.optString("departure", ""),
                                            duration = r.optString("duration", "")
                                        )
                                    )
                                }
                            }

                            val advice = AiAdviceData(
                                summary = structJson.optString("summary", ""),
                                aiAdvice = structJson.optString("ai_advice", ""),
                                routes = rList,
                                emergency = structJson.optString("emergency", ""),
                                navDest = structJson.optString("nav_dest", ""),
                                sources = structJson.optString("sources", "歷史災害資料庫")
                            )
                            withContext(Dispatchers.Main) {
                                aiResult = advice
                            }
                            success = true
                            break
                        }
                    } catch (_: Exception) {
                        Log.e("StationDetail", "連接 $target 失敗")
                    }
                }
                withContext(Dispatchers.Main) {
                    if (!success) aiError = "無法連接到伺服器 (請確認已啟動 app_bridge.py)"
                    isLoadingAi = false
                }
            } catch (err: Exception) {
                withContext(Dispatchers.Main) {
                    aiError = "資料解析錯誤: ${err.message}"
                    isLoadingAi = false
                }
            }
        }
    }

    LaunchedEffect(stationName, simulationConfig) {
        fetchAiAdvice()
    }

    Box(
        modifier = Modifier
            .fillMaxSize()
            .background(DT.PageBg)
            .statusBarsPadding()
            .navigationBarsPadding()
    ) {
        Column(
            modifier = Modifier
                .fillMaxSize()
                .verticalScroll(rememberScrollState())
                .padding(top = 4.dp, bottom = 80.dp),
            horizontalAlignment = Alignment.CenterHorizontally
        ) {
            // Header
            Box(
                modifier = Modifier
                    .fillMaxWidth()
                    .padding(horizontal = 4.dp, vertical = 8.dp),
                contentAlignment = Alignment.Center
            ) {
                IconButton(
                    onClick = onBack,
                    modifier = Modifier.align(Alignment.CenterStart)
                ) {
                    Icon(
                        Icons.Filled.ArrowBackIosNew,
                        "返回",
                        tint = DT.TextMain,
                        modifier = Modifier.size(22.dp)
                    )
                }
                Text(
                    stationName,
                    color = DT.TextMain,
                    fontSize = 38.sp,
                    fontWeight = FontWeight.Black
                )

                // 隱藏的模擬按鈕
                IconButton(
                    onClick = { showSimulationDialog = true },
                    modifier = Modifier.align(Alignment.CenterEnd)
                ) {
                    Icon(
                        imageVector = Icons.Filled.Notifications,
                        contentDescription = "Simulation",
                        tint = if (simulationConfig != null) DT.BtnBlue else DT.TextSub.copy(alpha = 0.3f),
                        modifier = Modifier.size(20.dp)
                    )
                }
            }

            Text(
                "$lineName ｜ 車站健康狀態",
                modifier = contentModifier,
                color = DT.TextMain,
                fontSize = 15.sp,
                fontWeight = FontWeight.Bold,
                textAlign = TextAlign.Center
            )
            Spacer(Modifier.height(24.dp))

            HealthRing(
                ringColor = ringColor,
                label = if (isSuspended) "停駛" else if (currentStation?.is_delayed == true) "延誤" else "正常",
                fillColor = ringFill
            )

            Spacer(Modifier.height(20.dp))
            WeatherLink(
                text = "$weatherDesc ｜ $temperatureStr",
                onClick = onOpenEnvironment,
                modifier = contentModifier
            )
            Spacer(Modifier.height(16.dp))

            if (isSuspended) {
                val reasonText =
                    if (simulationConfig != null) "模擬災害：${simulationConfig!!.description}" else "停駛原因：${currentStation?.weather?.description ?: "地震"}"
                InfoCardFilled(reasonText, modifier = contentModifier)
                Spacer(Modifier.height(12.dp))
                InfoCardFilled(
                    "預估恢復：$recoveryTime",
                    modifier = contentModifier.clickable {
                        if (evidenceList.isNotEmpty()) showEvidenceDialog = true
                    }
                )
                if (recoveryReason.isNotEmpty()) {
                    Spacer(Modifier.height(4.dp))
                    Text(
                        "依據：$recoveryReason",
                        color = DT.TextSub,
                        fontSize = 12.sp,
                        modifier = contentModifier.padding(horizontal = 8.dp)
                    )
                }
                Spacer(Modifier.height(16.dp))
            } else {
                InfoCardFilled(
                    if (actualDelay > 0) "預估延誤：$actualDelay 分鐘" else "列車準點中",
                    modifier = contentModifier
                )
                Spacer(Modifier.height(16.dp))
            }

            // 應變建議區塊
            Card(
                modifier = contentModifier,
                shape = androidx.compose.foundation.shape.RoundedCornerShape(8.dp),
                colors = CardDefaults.cardColors(containerColor = DT.White),
                border = androidx.compose.foundation.BorderStroke(2.dp, DT.BtnBlue)
            ) {
                Column(modifier = Modifier.fillMaxWidth()) {
                    Box(
                        modifier = Modifier.fillMaxWidth().padding(vertical = 12.dp),
                        contentAlignment = Alignment.Center
                    ) {
                        Text(
                            "應變建議",
                            color = DT.TextMain,
                            fontSize = 18.sp,
                            fontWeight = FontWeight.Black
                        )
                        if (!isLoadingAi) {
                            Text(
                                "重新詢問",
                                color = DT.Cyan,
                                fontSize = 12.sp,
                                fontWeight = FontWeight.Bold,
                                modifier = Modifier.align(Alignment.CenterEnd).padding(end = 16.dp)
                                    .clickable { coroutineScope.launch { fetchAiAdvice() } }
                            )
                        }
                    }
                    HorizontalDivider(color = DT.BtnBlue, thickness = 1.dp)

                    Column(
                        modifier = Modifier.padding(16.dp).heightIn(max = 240.dp)
                            .verticalScroll(rememberScrollState())
                    ) {
                        if (isLoadingAi) {
                            Box(
                                Modifier.fillMaxWidth().height(60.dp),
                                contentAlignment = Alignment.Center
                            ) {
                                CircularProgressIndicator(
                                    modifier = Modifier.size(24.dp),
                                    color = DT.TextMain
                                )
                            }
                        } else if (aiResult != null) {
                            // 顯示 AI 的文字建議與總結
                            if (aiResult!!.summary.isNotEmpty() || aiResult!!.aiAdvice.isNotEmpty()) {
                                Column(modifier = Modifier.padding(bottom = 8.dp)) {
                                    if (aiResult!!.summary.isNotEmpty()) {
                                        Text(
                                            aiResult!!.summary,
                                            color = DT.AlertRed,
                                            fontSize = 17.sp,
                                            fontWeight = FontWeight.Black,
                                            modifier = Modifier.padding(bottom = 4.dp)
                                        )
                                    }
                                    Text(
                                        aiResult!!.aiAdvice,
                                        color = DT.TextMain,
                                        fontSize = 14.sp,
                                        lineHeight = 20.sp
                                    )
                                    Spacer(modifier = Modifier.height(12.dp))
                                    HorizontalDivider(color = DT.PageBg, thickness = 1.dp)
                                }
                            }

                            aiResult!!.routes.forEach { route ->
                                Row(
                                    modifier = Modifier.fillMaxWidth().padding(vertical = 12.dp),
                                    verticalAlignment = Alignment.CenterVertically
                                ) {
                                    val icon = when (route.type) {
                                        "train" -> Icons.Filled.Train
                                        "taxi" -> Icons.Filled.LocalTaxi
                                        "u-bike", "bike", "bicycle" -> Icons.Filled.DirectionsBike
                                        else -> Icons.Filled.DirectionsBus
                                    }
                                    Icon(
                                        icon,
                                        null,
                                        tint = DT.TextMain,
                                        modifier = Modifier.size(22.dp)
                                    )
                                    Spacer(Modifier.width(12.dp))
                                    Column(Modifier.weight(1f)) {
                                        Text(
                                            route.title,
                                            color = DT.TextMain,
                                            fontSize = 16.sp,
                                            fontWeight = FontWeight.Bold
                                        )
                                        if (route.departure.isNotEmpty() || route.duration.isNotEmpty()) {
                                            val timeInfo = listOfNotNull(
                                                if (route.departure.isNotEmpty()) "發車 ${route.departure}" else null,
                                                route.duration.ifEmpty { null }).joinToString(" ｜ ")
                                            Text(timeInfo, color = DT.TextSub, fontSize = 13.sp)
                                        }
                                    }
                                    Column(horizontalAlignment = Alignment.End) {
                                        Text(
                                            route.priority,
                                            color = if (route.priority.contains("急")) DT.TextMain else DT.TextSub,
                                            fontWeight = FontWeight.Bold,
                                            fontSize = 14.sp
                                        )
                                        Spacer(Modifier.height(4.dp))
                                        val context =
                                            androidx.compose.ui.platform.LocalContext.current
                                        androidx.compose.material3.Button(
                                            onClick = {
                                                try {
                                                    val travelMode =
                                                        if (route.title.contains("步行")) "walking" else "transit"
                                                    var dest = ""
                                                    val addressMatch =
                                                        "\\(([^)]+)\\)".toRegex().find(route.title)
                                                    if (addressMatch != null) {
                                                        dest = addressMatch.groupValues[1]
                                                    }
                                                    if (dest.isBlank()) {
                                                        dest = route.title.let { t ->
                                                            when {
                                                                t.contains("至") -> t.substringAfter(
                                                                    "至"
                                                                )

                                                                else -> t
                                                            }
                                                        }.replace("建議", "").trim()
                                                    }
                                                    if (dest.length < 2) dest =
                                                        aiResult?.navDest ?: "${stationName}附近"

                                                    val uri = "https://www.google.com/maps/dir/?api=1&origin=台灣${stationName}火車站&destination=台灣$dest&travel_mode=$travelMode".toUri()
                                                    with(Intent(Intent.ACTION_VIEW, uri)) {
                                                        try {
                                                            context.startActivity(this.apply { setPackage("com.google.android.apps.maps") })
                                                        } catch (_: Exception) {
                                                            context.startActivity(this)
                                                        }
                                                    }
                                                } catch (ex: Exception) {
                                                    Log.e("Nav", "Error: ${ex.message}")
                                                }
                                            },
                                            modifier = Modifier.height(28.dp),
                                            shape = androidx.compose.foundation.shape.RoundedCornerShape(
                                                4.dp
                                            ),
                                            colors = ButtonDefaults.buttonColors(containerColor = DT.BtnBlue),
                                            contentPadding = PaddingValues(
                                                horizontal = 8.dp,
                                                vertical = 0.dp
                                            )
                                        ) { Text("去導航", color = DT.White, fontSize = 11.sp) }
                                    }
                                }
                                if (route != aiResult!!.routes.last()) HorizontalDivider(color = DT.PageBg)
                            }
                            if (aiResult!!.emergency.isNotEmpty()) {
                                Text(
                                    "[⚠️ ${aiResult!!.emergency}]",
                                    color = DT.AlertRed,
                                    fontWeight = FontWeight.Black,
                                    modifier = Modifier.padding(top = 12.dp)
                                )
                            }
                            
                            // 顯示資料來源 (RAG)
                            Spacer(Modifier.height(16.dp))
                            Row(
                                modifier = Modifier.fillMaxWidth(),
                                horizontalArrangement = Arrangement.SpaceBetween,
                                verticalAlignment = Alignment.Bottom
                            ) {
                                Text(
                                    "來源：${aiResult!!.sources}",
                                    color = DT.TextSub,
                                    fontSize = 11.sp,
                                    fontStyle = androidx.compose.ui.text.font.FontStyle.Italic,
                                    modifier = Modifier.weight(1f).padding(end = 8.dp),
                                    lineHeight = 16.sp
                                )
                                if (evidenceList.isNotEmpty()) {
                                    Text(
                                        "查看檢索細節",
                                        color = DT.BtnBlue,
                                        fontSize = 11.sp,
                                        fontWeight = FontWeight.Bold,
                                        modifier = Modifier.clickable { showEvidenceDialog = true },
                                        textAlign = TextAlign.End
                                    )
                                }
                            }
                        } else {
                            Text(
                                aiError ?: "目前無即時建議路線",
                                color = DT.TextSub,
                                fontSize = 14.sp,
                                modifier = Modifier.fillMaxWidth().padding(vertical = 12.dp),
                                textAlign = TextAlign.Center
                            )
                        }
                    }
                }
            }
        }

        // Bottom Chips
        Box(
            modifier = Modifier.align(Alignment.BottomCenter).fillMaxWidth()
                .background(DT.White.copy(alpha = 0.9f)).padding(16.dp)
        ) {
            Row(horizontalArrangement = Arrangement.spacedBy(12.dp)) {
                ChipElement(
                    rainTagText,
                    iconRes = R.drawable.character_water,
                    bgColor = rainTagBg,
                    modifier = Modifier.weight(1f)
                )
                ChipElement(
                    eqText,
                    iconRes = R.drawable.denryoku_mark,
                    bgColor = eqBg,
                    modifier = Modifier.weight(1f)
                )
            }
        }
    }

    if (showEvidenceDialog) {
        AlertDialog(
            onDismissRequest = { showEvidenceDialog = false },
            title = { Text("AI 推估依據 (RAG)", fontWeight = FontWeight.Bold) },
            text = {
                Column(modifier = Modifier.verticalScroll(rememberScrollState())) {
                    evidenceList.forEach { ev ->
                        Card(
                            modifier = Modifier.padding(vertical = 4.dp),
                            colors = CardDefaults.cardColors(containerColor = DT.PageBg)
                        ) {
                            Column(Modifier.padding(12.dp)) {
                                Text(
                                    "情境：${ev.optString("situation")}",
                                    fontWeight = FontWeight.Bold,
                                    fontSize = 14.sp
                                )
                                Text(
                                    "耗時：${ev.optString("recovery_time")}",
                                    color = DT.BtnBlue,
                                    fontWeight = FontWeight.Bold
                                )
                                Text("細節：${ev.optString("solution")}", fontSize = 12.sp)
                            }
                        }
                    }
                }
            },
            confirmButton = {
                TextButton(onClick = {
                    showEvidenceDialog = false
                }) { Text("關閉") }
            }
        )
    }

    if (showSimulationDialog) {
        AlertDialog(
            onDismissRequest = { showSimulationDialog = false },
            title = { Text("模擬災害設定", fontWeight = FontWeight.Bold) },
            text = {
                Column {
                    Text("請選擇模擬情境：", fontSize = 14.sp, color = DT.TextSub)
                    Spacer(Modifier.height(12.dp))

                    val scenarios = listOf(
                        SimulationScenario("地震", 4, "地震 (震度 4 級)"),
                        SimulationScenario("地震", 5, "大地震 (震度 5 級)"),
                        SimulationScenario("強降雨", 100, "強降雨 (雨量 100mm/h)"),
                        SimulationScenario("土石流", 1, "邊坡土石流警報"),
                        SimulationScenario("正常", 0, "恢復正常營運")
                    )

                    scenarios.forEach { scenario ->
                        androidx.compose.material3.OutlinedButton(
                            onClick = {
                                if (scenario.type == "正常") {
                                    simulationConfig = null
                                } else {
                                    simulationConfig = scenario
                                    if (Build.VERSION.SDK_INT >= Build.VERSION_CODES.TIRAMISU && !hasNotificationPermission) {
                                        permissionLauncher.launch(Manifest.permission.POST_NOTIFICATIONS)
                                    } else {
                                        showDisasterNotification(scenario) // 觸發模擬推播
                                    }
                                }
                                showSimulationDialog = false
                            },
                            modifier = Modifier.fillMaxWidth().padding(vertical = 4.dp),
                            colors = ButtonDefaults.outlinedButtonColors(
                                contentColor = if (simulationConfig?.description == scenario.description) DT.BtnBlue else DT.TextMain
                            ),
                            border = androidx.compose.foundation.BorderStroke(
                                1.dp,
                                if (simulationConfig?.description == scenario.description) DT.BtnBlue else DT.PageBg.copy(
                                    alpha = 0.5f
                                )
                            )
                        ) {
                            Text(scenario.description)
                        }
                    }
                }
            },
            confirmButton = {}
        )
    }
}
