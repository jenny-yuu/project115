package com.example.project115.ui.screens

import androidx.compose.foundation.background
import androidx.compose.foundation.clickable
import androidx.compose.foundation.layout.*
import androidx.compose.foundation.shape.RoundedCornerShape
import androidx.compose.material.icons.Icons
import androidx.compose.material.icons.filled.ArrowBackIosNew
import androidx.compose.material.icons.filled.NotificationsNone
import androidx.compose.material3.*
import androidx.compose.runtime.*
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.text.font.FontWeight
import androidx.compose.ui.unit.dp
import androidx.compose.ui.unit.sp
import androidx.compose.foundation.layout.statusBarsPadding
import com.example.project115.ui.design.DT

data class CommuteSlotUi(
    val title: String,
    val station: String,
    val time: String,
    val enabled: Boolean
)

@Composable
fun SettingsScreen(onBack: () -> Unit) {
    var slots by remember {
        mutableStateOf(
            listOf(
                CommuteSlotUi("通勤時段 1", "花蓮站", "08:00-09:00", true),
                CommuteSlotUi("通勤時段 2", "壽豐站", "15:00-18:00", false),
            )
        )
    }

    Column(
        modifier = Modifier
            .fillMaxSize()
            .background(DT.PageBg)
            .statusBarsPadding()
            .padding(16.dp)
    ) {
        // Top Navigation Bar
        Box(
            modifier = Modifier
                .fillMaxWidth()
                .padding(top = 8.dp, bottom = 12.dp),
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
            Row(verticalAlignment = Alignment.CenterVertically, modifier = Modifier.padding(start = 36.dp)) {
                Icon(Icons.Filled.NotificationsNone, contentDescription = null, tint = DT.TextMain)
                Spacer(Modifier.width(8.dp))
                Text(
                    "設定",
                    color = DT.TextMain,
                    fontSize = 28.sp,
                    fontWeight = FontWeight.Black
                )
            }
        }
        Text("個人化推播設定", color = MaterialTheme.colorScheme.onSurfaceVariant)

        Spacer(Modifier.height(16.dp))

        slots.forEachIndexed { idx, slot ->
            Card(shape = RoundedCornerShape(14.dp)) {
                Column(Modifier.padding(14.dp)) {
                    Text(slot.title, style = MaterialTheme.typography.titleMedium, fontWeight = FontWeight.SemiBold)
                    Spacer(Modifier.height(10.dp))

                    Row(
                        Modifier.fillMaxWidth(),
                        horizontalArrangement = Arrangement.SpaceBetween,
                        verticalAlignment = Alignment.CenterVertically
                    ) {
                        Column {
                            Text(slot.station, style = MaterialTheme.typography.titleSmall, fontWeight = FontWeight.SemiBold)
                            Text("通勤時段：${slot.time}", color = MaterialTheme.colorScheme.onSurfaceVariant)
                        }
                        Switch(
                            checked = slot.enabled,
                            onCheckedChange = { checked ->
                                slots = slots.toMutableList().also { list ->
                                    list[idx] = list[idx].copy(enabled = checked)
                                }
                            }
                        )
                    }
                }
            }
            Spacer(Modifier.height(12.dp))
        }
    }
}