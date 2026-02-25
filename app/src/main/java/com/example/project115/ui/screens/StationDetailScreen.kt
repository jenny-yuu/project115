package com.example.project115.ui.screens

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
import androidx.compose.material.icons.filled.Train
import androidx.compose.material.icons.filled.Warning
import androidx.compose.material3.*
import androidx.compose.runtime.Composable
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.graphics.Color
import androidx.compose.ui.text.font.FontWeight
import androidx.compose.ui.text.style.TextAlign
import androidx.compose.ui.unit.dp
import androidx.compose.ui.unit.sp
import com.example.project115.ui.design.*
import androidx.compose.foundation.layout.statusBarsPadding
import androidx.compose.runtime.getValue
import com.example.project115.R

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
    // 觀測 Firebase 資料流
    val stations by viewModel.stations.collectAsStateWithLifecycle()
    // 尋找對應的車站資料，若無則提供預設的正常表現
    val currentStation = stations.find { it.StationName == stationName }

    // 依 Firebase 的資料決定健康狀態與燈號 (我們根據 Firebase 的 RiskLevel / HealthLight)
    val isSuspended = currentStation?.health_light == "紅燈" || health == "SUSPENDED"
    val ringColor = if (isSuspended) DT.SuspendRed else if (currentStation?.is_delayed == true) DT.DelayYellow else DT.StatusGreen

    val actualDelay = currentStation?.live_delay_max_minutes ?: delayMinutes
    val weatherData = currentStation?.weather
    val temperatureStr = weatherData?.temperature?.let { "${Math.round(it)}°C" } ?: "26°C"
    
    val rain1hr = weatherData?.rain_1hr ?: 0.0
    val rainTagText = if (rain1hr > 40.0) "大豪雨" else if (rain1hr > 15.0) "大雨" else if (rain1hr > 0) "降雨中" else "雨量正常"
    val rainTagBg = if (rain1hr > 15.0) Color(0xFFFBE9E7) else Color(0xFFE8F5E9)
    val weatherDesc = weatherData?.description ?: "多雲"
    // Simulate earthquake data (or read from risk_level if available)
    val eqMagnitude = if (currentStation?.health_light == "紅燈" || health == "SUSPENDED") 4 else 0
    val eqText = if (eqMagnitude > 0) "震度 $eqMagnitude 級" else "正常"
    val eqBg = if (eqMagnitude > 0) Color(0xFFFBE9E7) else Color(0xFFE8F5E9)

    val ringFill = if (isSuspended) DT.RingInnerRed else if (currentStation?.is_delayed == true) DT.RingInnerYellow else Color(0xFFE8F5E9)
    val contentModifier = Modifier.fillMaxWidth(0.92f)

    Column(
        modifier = Modifier
            .fillMaxSize()
            .background(DT.PageBg)
            .statusBarsPadding()
            .navigationBarsPadding()
            .verticalScroll(rememberScrollState())
            .padding(top = 4.dp, bottom = 12.dp),
        horizontalAlignment = Alignment.CenterHorizontally
    ) {
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
                    contentDescription = "返回",
                    tint = DT.TextMain,
                    modifier = Modifier.size(22.dp)
                )
            }
            Text(
                stationName,
                color = DT.TextMain,
                fontSize = 38.sp,
                fontWeight = FontWeight.Black,
                textAlign = TextAlign.Center
            )
        }
        Spacer(Modifier.height(4.dp))
        Text(
            "$lineName ｜ 車站即時健康狀態",
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
            InfoCardFilled("停駛原因：地震", modifier = contentModifier)
            Spacer(Modifier.height(12.dp))
            InfoCardFilled("預估恢復：2～4 小時", modifier = contentModifier)

            Spacer(Modifier.height(16.dp))

            SuggestedCardOutlined(modifier = contentModifier) {
                Text("應變建議", color = DT.TextMain, fontSize = 18.sp, fontWeight = FontWeight.Black)
                Spacer(Modifier.height(16.dp))

                Row(Modifier.fillMaxWidth(), horizontalArrangement = Arrangement.SpaceBetween, verticalAlignment = Alignment.CenterVertically) {
                    Row(verticalAlignment = Alignment.CenterVertically) {
                        Icon(imageVector = Icons.Filled.Train, contentDescription = "train", tint = DT.TextMain, modifier = Modifier.size(20.dp))
                        Spacer(Modifier.width(8.dp))
                        Text("至 OO 站轉乘", color = DT.TextMain, fontSize = 16.sp, fontWeight = FontWeight.Bold)
                    }
                    Text("急件", color = DT.TextMain, fontWeight = FontWeight.Bold, fontSize = 14.sp)
                }
                Spacer(Modifier.height(16.dp))
                Row(Modifier.fillMaxWidth(), horizontalArrangement = Arrangement.SpaceBetween, verticalAlignment = Alignment.CenterVertically) {
                    Row(verticalAlignment = Alignment.CenterVertically) {
                        Icon(imageVector = Icons.Filled.DirectionsBus, contentDescription = "bus", tint = DT.TextMain, modifier = Modifier.size(20.dp))
                        Spacer(Modifier.width(8.dp))
                        Text("花蓮客運 / 站前轉運站", color = DT.TextMain, fontSize = 16.sp, fontWeight = FontWeight.Bold)
                    }
                    Text("建議", color = DT.TextMain, fontWeight = FontWeight.Bold, fontSize = 14.sp)
                }

                Spacer(Modifier.height(20.dp))
                Row(Modifier.fillMaxWidth(), verticalAlignment = Alignment.CenterVertically) {
                    Icon(Icons.Filled.Warning, contentDescription = null, tint = DT.AlertYellow, modifier = Modifier.size(20.dp))
                    Spacer(Modifier.width(8.dp))
                    Text("[! 蘇花公路管制中]", color = DT.AlertRed, fontWeight = FontWeight.Black, fontSize = 16.sp)
                }

                Spacer(Modifier.height(20.dp))

                val context = androidx.compose.ui.platform.LocalContext.current

                Row(Modifier.fillMaxWidth(), horizontalArrangement = Arrangement.spacedBy(10.dp)) {
                    ActionButton(
                        text = "其他替代路線 >",
                        onClick = {
                            val uri = android.net.Uri.parse("https://www.google.com/maps/dir/?api=1&origin=${stationName}車站&destination=台鐵替代路線")
                            val intent = android.content.Intent(android.content.Intent.ACTION_VIEW, uri)
                            context.startActivity(intent)
                        },
                        modifier = Modifier.weight(1f)
                    )
                    ActionButton(
                        text = "導航到轉運站 >",
                        onClick = {
                            val uri = android.net.Uri.parse("https://www.google.com/maps/dir/?api=1&origin=${stationName}車站&destination=花蓮轉運站")
                            val intent = android.content.Intent(android.content.Intent.ACTION_VIEW, uri)
                            context.startActivity(intent)
                        },
                        modifier = Modifier.weight(1f)
                    )
                }
            }

            Spacer(Modifier.height(24.dp))

            Row(modifier = contentModifier, horizontalArrangement = Arrangement.spacedBy(12.dp)) {
                ChipElement(rainTagText, iconRes = R.drawable.images, bgColor = rainTagBg, modifier = Modifier.weight(1f))
                ChipElement(eqText, iconRes = R.drawable.denryoku_mark, bgColor = eqBg, modifier = Modifier.weight(1f))
            }

        } else { // 延誤 或 正常
            if (actualDelay > 0) {
                InfoCardFilled("即時延誤：$actualDelay 分鐘", modifier = contentModifier)
                Spacer(Modifier.height(16.dp))

                SuggestedCardOutlined(modifier = contentModifier) {
                    Spacer(Modifier.height(8.dp))
                    Text(
                        "班次稍有延誤 請耐心等候",
                        color = DT.TextMain,
                        fontSize = 18.sp,
                        fontWeight = FontWeight.Bold
                    )
                    Spacer(Modifier.height(8.dp))
                }
            } else {
                InfoCardFilled("列車準點中", modifier = contentModifier)
            }

            Spacer(Modifier.height(24.dp))

            Row(modifier = contentModifier, horizontalArrangement = Arrangement.spacedBy(12.dp)) {
                ChipElement(rainTagText, iconRes = R.drawable.images, bgColor = rainTagBg, modifier = Modifier.weight(1f))
                ChipElement(eqText, iconRes = R.drawable.denryoku_mark, bgColor = eqBg, modifier = Modifier.weight(1f))
            }
        }
    }
}