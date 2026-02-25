package com.example.project115.ui.screens

import androidx.lifecycle.compose.collectAsStateWithLifecycle
import com.example.project115.viewmodel.MainViewModel

import androidx.compose.foundation.background
import androidx.compose.foundation.clickable
import androidx.compose.foundation.layout.*
import androidx.compose.foundation.shape.RoundedCornerShape
import androidx.compose.material.icons.Icons
import androidx.compose.material.icons.filled.ArrowBackIosNew
import androidx.compose.material3.*
import androidx.compose.runtime.Composable
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.res.painterResource
import androidx.compose.foundation.Image
import androidx.compose.ui.text.font.FontWeight
import androidx.compose.ui.unit.dp
import androidx.compose.ui.unit.sp
import com.example.project115.R
import com.example.project115.ui.design.DT
import com.example.project115.ui.design.SuggestedCardOutlined

import androidx.compose.foundation.layout.statusBarsPadding
import androidx.compose.runtime.getValue
import androidx.compose.ui.graphics.Color
import androidx.compose.ui.text.style.TextAlign

@Composable
fun EnvironmentScreen(
    viewModel: MainViewModel,
    stationName: String,
    lineName: String,
    onBack: () -> Unit,
) {
    val stations by viewModel.stations.collectAsStateWithLifecycle()
    val currentStation = stations.find { it.StationName == stationName }
    val weatherData = currentStation?.weather
    
    val wind = weatherData?.wind_speed ?: 0.0
    val rain1h = weatherData?.rain_1hr ?: 0.0
    val fcst = currentStation?.forecast
    Column(
        modifier = Modifier
            .fillMaxSize()
            .background(DT.PageBg)
            .statusBarsPadding()
            .padding(16.dp)
    ) {
        Box(
            modifier = Modifier
                .fillMaxWidth()
                .padding(top = 8.dp, bottom = 4.dp),
            contentAlignment = Alignment.CenterStart
        ) {
            IconButton(onClick = onBack, modifier = Modifier.offset(x = (-12).dp)) {
                Icon(
                    Icons.Filled.ArrowBackIosNew,
                    contentDescription = "返回",
                    tint = DT.TextMain,
                    modifier = Modifier.size(22.dp)
                )
            }
            Text(
                "環境狀態",
                style = MaterialTheme.typography.headlineMedium,
                fontWeight = FontWeight.Black,
                color = DT.TextMain,
                modifier = Modifier.padding(start = 36.dp)
            )
        }
        
        Text("微氣候與預報資訊（$lineName）", color = MaterialTheme.colorScheme.onSurfaceVariant)

        Spacer(Modifier.height(16.dp))

        // 及時氣象（照你圖六中間：左右兩格）
        SuggestedCardOutlined(modifier = Modifier.padding(bottom = 16.dp)) {
            Column(Modifier.fillMaxWidth()) {
                Text("及時氣象", color = DT.TextMain, fontSize = 20.sp, fontWeight = FontWeight.Bold)
                Spacer(Modifier.height(16.dp))

                Row(Modifier.fillMaxWidth(), horizontalArrangement = Arrangement.spacedBy(12.dp)) {
                    RealtimeRainCard(rain1h = rain1h, modifier = Modifier.weight(1f))
                    RealtimeWindCard(windSpeed = wind, modifier = Modifier.weight(1f))
                }
            }
        }

        // 預報資訊 (縣市級距 36-hr Forecast)
        SuggestedCardOutlined {
            Column(Modifier.fillMaxWidth()) {
                Text("36小時天氣預報", color = DT.TextMain, fontSize = 20.sp, fontWeight = FontWeight.Bold)
                Spacer(Modifier.height(16.dp))

                Row(Modifier.fillMaxWidth(), horizontalArrangement = Arrangement.spacedBy(12.dp)) {
                    InfoBox(
                        title = fcst?.wx ?: "未知", 
                        subtitle = "降雨機率 ${fcst?.pop ?: 0}%", 
                        modifier = Modifier.weight(1f)
                    )
                    InfoBox(
                        title = "氣溫預測", 
                        subtitle = "${fcst?.min_t ?: 0}°C - ${fcst?.max_t ?: 0}°C", 
                        modifier = Modifier.weight(1f)
                    )
                }
            }
        }
    }
}

@Composable
private fun InfoBox(title: String, subtitle: String, modifier: Modifier = Modifier) {
    Card(
        modifier = modifier.height(96.dp),
        shape = RoundedCornerShape(DT.R12),
        colors = CardDefaults.cardColors(containerColor = DT.CardBgFilled),
        elevation = CardDefaults.cardElevation(defaultElevation = 0.dp)
    ) {
        Column(
            Modifier.fillMaxSize().padding(14.dp), 
            verticalArrangement = Arrangement.Center
        ) {
            Text(title, color = DT.TextMain, fontSize = 18.sp, fontWeight = FontWeight.Black)
            if (subtitle.isNotBlank()) {
                Spacer(Modifier.height(6.dp))
                Text(subtitle, color = DT.TextSub, fontSize = 14.sp, fontWeight = FontWeight.Bold)
            }
        }
    }
}

@Composable
private fun RealtimeRainCard(rain1h: Double, modifier: Modifier = Modifier) {
    Card(
        modifier = modifier.height(140.dp),
        shape = RoundedCornerShape(DT.R12),
        colors = CardDefaults.cardColors(containerColor = DT.CardBgFilled),
        elevation = CardDefaults.cardElevation(defaultElevation = 0.dp)
    ) {
        Column(
            Modifier.fillMaxSize().padding(14.dp), 
            horizontalAlignment = Alignment.CenterHorizontally,
            verticalArrangement = Arrangement.Center
        ) {
            val isRaining = rain1h > 0.0
            val bgColor = if (isRaining) Color(0xFFFFF9C4) else Color(0xFFE8F5E9)
            val textColor = if (isRaining) Color(0xFFF57F17) else Color(0xFF2E7D32)
            val textStr = if (isRaining) "⚠️ \n降雨發生中" else "✅ \n雨量正常"

            Box(
                modifier = Modifier
                    .background(bgColor, RoundedCornerShape(8.dp))
                    .padding(horizontal = 14.dp, vertical = 6.dp),
                contentAlignment = Alignment.Center
            ) {
                Text(
                    textStr,
                    color = textColor,
                    fontWeight = FontWeight.Black,
                    fontSize = 16.sp,
                    textAlign = TextAlign.Center,
                    lineHeight = 22.sp
                )
            }
            Spacer(Modifier.height(14.dp))
            Image(
                painter = painterResource(id = R.drawable.images),
                contentDescription = null,
                modifier = Modifier.size(54.dp)
            )
        }
    }
}

@Composable
private fun RealtimeWindCard(windSpeed: Double, modifier: Modifier = Modifier) {
    Card(
        modifier = modifier.height(140.dp),
        shape = RoundedCornerShape(DT.R12),
        colors = CardDefaults.cardColors(containerColor = DT.CardBgFilled),
        elevation = CardDefaults.cardElevation(defaultElevation = 0.dp)
    ) {
        Column(
            Modifier.fillMaxSize().padding(14.dp), 
            horizontalAlignment = Alignment.CenterHorizontally,
            verticalArrangement = Arrangement.Center
        ) {
            val isHighWind = windSpeed > 10.0
            val bgColor = if (isHighWind) Color(0xFFFFF9C4) else Color(0xFFE8F5E9)
            val textColor = if (isHighWind) Color(0xFFF57F17) else Color(0xFF2E7D32)
            val textStr = if (isHighWind) "⚠️ \n注意強風" else "✅ \n風速正常"
            val emojiStr = if (isHighWind) "🌪️" else "🍃"

            Box(
                modifier = Modifier
                    .background(bgColor, RoundedCornerShape(8.dp))
                    .padding(horizontal = 14.dp, vertical = 6.dp),
                contentAlignment = Alignment.Center
            ) {
                Text(
                    textStr,
                    color = textColor,
                    fontWeight = FontWeight.Black,
                    fontSize = 16.sp,
                    textAlign = TextAlign.Center,
                    lineHeight = 22.sp
                )
            }
            Spacer(Modifier.height(14.dp))
            val windIcon = if (isHighWind) R.drawable.tenki_mark10_taifuu else R.drawable.tenki_mark01_hare
            Image(
                painter = painterResource(id = windIcon),
                contentDescription = null,
                modifier = Modifier.size(54.dp)
            )
        }
    }
}