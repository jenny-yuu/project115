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
    val rain1h = weatherData?.rain_1hr ?: 0.0
    val temperature = weatherData?.temperature ?: 0.0

    // 解決無論幾度都顯示舒適的問題：根據溫度動態判斷體感描述
    val tempFeel = when {
        temperature >= 33 -> "酷熱"
        temperature >= 28 -> "悶熱"
        temperature >= 22 -> "舒適"
        temperature >= 17 -> "微涼"
        temperature >= 10 -> "寒冷"
        else -> "極寒"
    }

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
                Text(
                    "及時氣象", 
                    color = DT.TextMain, 
                    fontSize = 20.sp, 
                    fontWeight = FontWeight.Bold,
                    modifier = Modifier.fillMaxWidth(),
                    textAlign = TextAlign.Center
                )
                Spacer(Modifier.height(16.dp))

                Row(Modifier.fillMaxWidth(), horizontalArrangement = Arrangement.spacedBy(12.dp)) {
                    RealtimeRainCard(rain1h = rain1h, modifier = Modifier.weight(1f))
                    RealtimeClimateCard(temp = temperature, feel = tempFeel, modifier = Modifier.weight(1f))
                }
            }
        }

        // 預報資訊 (縣市級距 36-hr Forecast)
        SuggestedCardOutlined {
            Column(Modifier.fillMaxWidth()) {
                Text(
                    "36小時天氣預報", 
                    color = DT.TextMain, 
                    fontSize = 20.sp, 
                    fontWeight = FontWeight.Bold,
                    modifier = Modifier.fillMaxWidth(),
                    textAlign = TextAlign.Center
                )
                Spacer(Modifier.height(16.dp))

                val wxText = fcst?.wx ?: "未知"
                val wxIcon = when {
                    wxText.contains("雷") -> R.drawable.tenki_mark07_kami_nari
                    wxText.contains("雨") -> R.drawable.tenki_mark03_gouu
                    wxText.contains("雲") -> R.drawable.tenki_mark05_kumori
                    else -> R.drawable.tenki_mark01_hare
                }

                Row(Modifier.fillMaxWidth(), horizontalArrangement = Arrangement.spacedBy(12.dp)) {
                    InfoBox(
                        title = wxText, 
                        subtitle = "降雨機率 ${fcst?.pop ?: 0}%", 
                        iconResId = wxIcon,
                        modifier = Modifier.weight(1f)
                    )
                    InfoBox(
                        title = "氣溫預測", 
                        subtitle = "${fcst?.min_t ?: 0}°C - ${fcst?.max_t ?: 0}°C", 
                        iconResId = R.drawable.tenki_mark01_hare,
                        modifier = Modifier.weight(1f)
                    )
                }
            }
        }
    }
}

@Composable
private fun InfoBox(
    title: String, 
    subtitle: String, 
    iconResId: Int? = null,
    modifier: Modifier = Modifier
) {
    Card(
        modifier = modifier.height(110.dp), // 稍微增加高度以放圖示
        shape = RoundedCornerShape(DT.R12),
        colors = CardDefaults.cardColors(containerColor = DT.CardBgFilled),
        elevation = CardDefaults.cardElevation(defaultElevation = 0.dp)
    ) {
        Row(
            Modifier.fillMaxSize().padding(12.dp), 
            verticalAlignment = Alignment.CenterVertically, // 修正：從 CenterHorizontally 改為 CenterVertically
            horizontalArrangement = Arrangement.Center
        ) {
            Column(
                modifier = Modifier.weight(1f),
                horizontalAlignment = Alignment.CenterHorizontally,
                verticalArrangement = Arrangement.Center
            ) {
                Text(
                    text = title, 
                    color = DT.TextMain, 
                    fontSize = 17.sp, 
                    fontWeight = FontWeight.Black,
                    textAlign = TextAlign.Center,
                    modifier = Modifier.fillMaxWidth()
                )
                if (subtitle.isNotBlank()) {
                    Spacer(Modifier.height(4.dp))
                    Text(
                        text = subtitle, 
                        color = DT.TextSub, 
                        fontSize = 13.sp, 
                        fontWeight = FontWeight.Bold,
                        textAlign = TextAlign.Center,
                        modifier = Modifier.fillMaxWidth()
                    )
                }
            }
            if (iconResId != null) {
                Spacer(Modifier.width(8.dp))
                Image(
                    painter = painterResource(id = iconResId),
                    contentDescription = null,
                    modifier = Modifier.size(40.dp)
                )
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
            val rainIcon = if (isRaining) R.drawable.tenki_mark03_gouu else R.drawable.character_water
            Image(
                painter = painterResource(id = rainIcon),
                contentDescription = null,
                modifier = Modifier.size(54.dp)
            )
        }
    }
}

@Composable
private fun RealtimeClimateCard(temp: Double, feel: String, modifier: Modifier = Modifier) {
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
            val isHot = temp >= 28.0
            val isCold = temp < 18.0
            val bgColor = if (isHot) Color(0xFFFFEBEE) else if (isCold) Color(0xFFE3F2FD) else Color(0xFFE8F5E9)
            val textColor = if (isHot) Color(0xFFC62828) else if (isCold) Color(0xFF1565C0) else Color(0xFF2E7D32)
            val textStr = "${temp.toInt()}°C\n體感${feel}" // 顯示溫度與體感

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
            // 根據熱/舒適/冷/微涼選擇圖示，善用現有素材
            val climateIcon = when {
                temp >= 33.0 -> R.drawable.tenki_mark01_hare   // 酷熱 (大太陽)
                temp >= 28.0 -> R.drawable.sun_yellow2_character   // 悶熱 (太陽)
                temp >= 22.0 -> R.drawable.tenki_mark05_kumori // 舒適 (雲朵)
                temp >= 17.0 -> R.drawable.tenki_mark12_tsuki // 微涼 (雲朵)
                else -> R.drawable.tenki_mark09_gousetsu              // 寒冷 (水滴小人)
            }
            Image(
                painter = painterResource(id = climateIcon),
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
