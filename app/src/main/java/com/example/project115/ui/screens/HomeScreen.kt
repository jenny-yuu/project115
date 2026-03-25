package com.example.project115.ui.screens

import androidx.lifecycle.compose.collectAsStateWithLifecycle
import com.example.project115.viewmodel.MainViewModel
import com.example.project115.data.Station
import androidx.compose.foundation.layout.statusBarsPadding
import androidx.compose.ui.unit.sp
import androidx.compose.foundation.background
import androidx.compose.foundation.clickable
import androidx.compose.foundation.layout.*
import androidx.compose.foundation.shape.CircleShape
import androidx.compose.foundation.shape.RoundedCornerShape
import androidx.compose.material.icons.Icons
import androidx.compose.material.icons.filled.ChevronRight
import androidx.compose.material.icons.filled.KeyboardArrowDown
import androidx.compose.material.icons.filled.NotificationsNone
import androidx.compose.material3.*
import androidx.compose.ui.text.font.FontWeight
import androidx.compose.ui.text.style.TextAlign
import androidx.compose.ui.unit.dp
import androidx.compose.runtime.*
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.graphics.Color
import androidx.compose.foundation.layout.navigationBarsPadding
import androidx.compose.foundation.rememberScrollState
import androidx.compose.foundation.verticalScroll
import com.example.project115.ui.design.DT
import com.example.project115.ui.design.StatusTag



@Composable
fun HomeScreen(
    viewModel: MainViewModel,
    onOpenSettings: () -> Unit,
    onOpenStation: (stationName: String, lineName: String, health: String, delayMin: Int) -> Unit,
) {
    var selectedLine by remember { mutableStateOf("臺東線") }

    // 觀測 Firebase 資料流
    val stations by viewModel.stations.collectAsStateWithLifecycle()
    val errorMessage by viewModel.errorMessage.collectAsStateWithLifecycle()

    // 依據 "是否誤點" (is_delayed) 或 "天氣停駛" (health_light == "紅燈") 來過濾異常車站
    val abnormalStations = remember(stations) {
        stations.filter { it.is_delayed || it.health_light == "紅燈" || it.health_light == "黃燈" }
    }

    // 將異常車站依路線分群
    val groupedAbnormal = remember(abnormalStations) {
        // 利用 Firebase 下載回來的路線屬性去找出他所屬的鐵路總線
        abnormalStations.groupBy { it.Route }
    }

    // 因為範例 UI 寫死了三條線，我們這邊依舊保留這三條線的架構
    val uiLines = listOf("北迴線", "宜蘭線", "臺東線")

    Column(
        modifier = Modifier
            .fillMaxSize()
            .background(DT.PageBg)
            .statusBarsPadding()
            .navigationBarsPadding()
            .verticalScroll(rememberScrollState())
            .padding(horizontal = DT.PadH)
            .padding(top = 6.dp, bottom = 24.dp)
    ) {

        // ✅ 你圖六：標題區置中 + 層級清楚
        Text(
            "台鐵東部幹線",
            modifier = Modifier.fillMaxWidth(),
            color = DT.TextMain,
            fontWeight = FontWeight.Black,
            fontSize = 26.sp,
            textAlign = TextAlign.Center
        )
        Spacer(Modifier.height(4.dp))
        Text(
            "路線總覽",
            modifier = Modifier.fillMaxWidth(),
            color = DT.TextSub,
            fontSize = 22.sp,
            textAlign = TextAlign.Center
        )

        Spacer(Modifier.height(16.dp))

        Spacer(Modifier.height(16.dp))

        uiLines.forEach { lineName ->
            val list = groupedAbnormal[lineName].orEmpty()
            val delayCount = list.count { it.is_delayed }
            val suspendCount = list.count { it.health_light == "紅燈" }
            val expanded = (lineName == selectedLine)

            Card(
                shape = RoundedCornerShape(DT.R14),
                colors = CardDefaults.cardColors(containerColor = DT.CardBg),
                elevation = CardDefaults.cardElevation(defaultElevation = 2.dp),
                modifier = Modifier
                    .fillMaxWidth()
                    .padding(vertical = 4.dp),
                onClick = { selectedLine = lineName }
            ) {
                Row(
                    modifier = Modifier
                        .fillMaxWidth()
                        .padding(horizontal = 16.dp, vertical = 20.dp),
                    verticalAlignment = Alignment.CenterVertically
                ) {
                    Text(lineName, color = DT.TextMain, fontWeight = FontWeight.Black, fontSize = 20.sp)
                    Spacer(Modifier.width(16.dp))
                    Text("誤點 $delayCount｜停駛 $suspendCount", color = DT.TextSub, fontWeight = FontWeight.SemiBold, fontSize = 16.sp)
                    Spacer(Modifier.weight(1f))
                    Icon(
                        if (expanded) Icons.Filled.KeyboardArrowDown else Icons.Filled.ChevronRight,
                        contentDescription = null,
                        tint = DT.TextSub
                    )
                }
            }

            if (expanded) {
                Spacer(Modifier.height(14.dp))
                AbnormalList(
                    lineName = lineName,
                    stations = list,
                    onClick = { sName, lName, h, d -> onOpenStation(sName, lName, h, d) }
                )
            }

            Spacer(Modifier.height(14.dp))
        }

        Spacer(Modifier.weight(1f))

        Row(
            modifier = Modifier
                .fillMaxWidth()
                .padding(bottom = 10.dp),
            horizontalArrangement = Arrangement.End,
            verticalAlignment = Alignment.CenterVertically
        ) {
            Text("推播設定", color = DT.Cyan, fontWeight = FontWeight.Black)
            Spacer(Modifier.width(10.dp))
            IconButton(onClick = onOpenSettings) {
                Icon(Icons.Filled.NotificationsNone, contentDescription = null, tint = DT.TextMain)
            }
        }
    }
}

@Composable
private fun AbnormalList(
    lineName: String,
    stations: List<Station>,
    onClick: (String, String, String, Int) -> Unit
) {
    Column {
        stations.forEachIndexed { idx, s ->
            Row(
                modifier = Modifier
                    .fillMaxWidth()
                    .padding(vertical = 12.dp)
                    .clickable {
                        onClick(
                            s.StationName,
                            lineName,
                            if (s.health_light == "紅燈") "SUSPENDED" else "DELAY",
                            s.live_delay_max_minutes
                        )
                    },
                verticalAlignment = Alignment.CenterVertically
            ) {
                Column(horizontalAlignment = Alignment.CenterHorizontally) {
                    val dot = if (s.health_light == "紅燈") DT.SuspendDot else DT.DelayDot
                    Box(
                        modifier = Modifier
                            .size(18.dp)
                            .background(dot, shape = CircleShape)
                    )
                    if (idx != stations.lastIndex) {
                        Box(
                            modifier = Modifier
                                .width(3.dp)
                                .height(32.dp)
                                .background(DT.TimelineLine)
                        )
                    }
                }

                Spacer(Modifier.width(14.dp))

                Column {
                    Text(s.StationName, color = DT.TextMain, fontWeight = FontWeight.Black)
                    if (s.live_delay_trains.isNotEmpty()) {
                        val trains = s.live_delay_trains.joinToString(", ") { it.TrainNo + "次" }
                        Text(trains, color = DT.TextSub, fontSize = 12.sp, fontWeight = FontWeight.Medium)
                    }
                }

                Spacer(Modifier.weight(1f))

                val statusText = if (s.health_light == "紅燈") "暫行停駛" else "誤點 ${s.live_delay_max_minutes} 分"
                Text(statusText, color = DT.TextSub, fontWeight = FontWeight.SemiBold)

                Spacer(Modifier.width(12.dp))

                if (s.health_light == "紅燈") {
                    StatusTag("停駛車站", DT.SuspendRed)
                } else {
                    StatusTag("誤點車站", DT.DelayYellow)
                }
            }
        }
    }
}