package com.example.project115.ui.design

import androidx.compose.foundation.BorderStroke
import androidx.compose.foundation.Canvas
import androidx.compose.foundation.background
import androidx.compose.foundation.clickable
import androidx.compose.foundation.layout.*
import androidx.compose.foundation.shape.CircleShape
import androidx.compose.foundation.shape.RoundedCornerShape
import androidx.compose.material3.*
import androidx.compose.runtime.Composable
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.draw.clip
import androidx.compose.ui.graphics.Color
import androidx.compose.ui.res.painterResource
import androidx.compose.foundation.Image
import androidx.compose.ui.graphics.drawscope.Stroke
import androidx.compose.ui.text.font.FontWeight
import androidx.compose.ui.unit.dp
import androidx.compose.ui.unit.sp

@Composable
fun InfoCardFilled(
    text: String,
    modifier: Modifier = Modifier
) {
    Card(
        shape = RoundedCornerShape(DT.R12),
        colors = CardDefaults.cardColors(containerColor = DT.CardBgFilled),
        modifier = modifier.fillMaxWidth()
    ) {
        Box(
            modifier = Modifier
                .fillMaxWidth()
                .padding(vertical = 16.dp),
            contentAlignment = Alignment.Center
        ) {
            Text(text, color = DT.TextMain, fontSize = 18.sp, fontWeight = FontWeight.Bold)
        }
    }
}

@Composable
fun SuggestedCardOutlined(
    modifier: Modifier = Modifier,
    content: @Composable ColumnScope.() -> Unit
) {
    Card(
        shape = RoundedCornerShape(DT.R12),
        colors = CardDefaults.cardColors(containerColor = DT.CardBgWhite),
        border = BorderStroke(2.dp, DT.CardBorder),
        modifier = modifier.fillMaxWidth()
    ) {
        Column(
            modifier = Modifier.padding(16.dp).fillMaxWidth(),
            horizontalAlignment = Alignment.CenterHorizontally,
            content = content
        )
    }
}

@Composable
fun HealthRing(
    ringColor: Color,
    label: String,
    fillColor: Color,
    modifier: Modifier = Modifier
) {
    Box(
        modifier = modifier.size(160.dp),
        contentAlignment = Alignment.Center
    ) {
        Canvas(modifier = Modifier.fillMaxSize()) {
            drawCircle(
                color = ringColor,
                style = Stroke(width = 16.dp.toPx())
            )
        }
        Box(
            modifier = Modifier
                .size(136.dp)
                .clip(CircleShape)
                .background(fillColor)
        )
        Column(horizontalAlignment = Alignment.CenterHorizontally) {
            Box(
                modifier = Modifier
                    .size(28.dp)
                    .clip(CircleShape)
                    .background(Color.Transparent),
                contentAlignment = Alignment.Center
            ) {
                Text("⚠", color = ringColor, fontSize = 24.sp, fontWeight = FontWeight.Black)
            }
            Spacer(Modifier.height(2.dp))
            Text(label, color = DT.TextMain, fontSize = 32.sp, fontWeight = FontWeight.Black)
        }
    }
}

@Composable
fun WeatherLink(
    text: String,
    onClick: () -> Unit,
    modifier: Modifier = Modifier
) {
    Row(
        modifier = modifier.clickable { onClick() }.padding(vertical = 8.dp),
        verticalAlignment = Alignment.CenterVertically,
        horizontalArrangement = Arrangement.Center
    ) {
        Text(text, color = DT.TextMain, fontSize = 16.sp, fontWeight = FontWeight.Bold)
        Spacer(Modifier.width(4.dp))
        Text("»", color = DT.TextSub, fontSize = 20.sp, fontWeight = FontWeight.Bold)
    }
}

@Composable
fun ActionButton(
    text: String,
    onClick: () -> Unit,
    modifier: Modifier = Modifier
) {
    Button(
        onClick = onClick,
        shape = RoundedCornerShape(8.dp),
        colors = ButtonDefaults.buttonColors(containerColor = DT.ButtonBg),
        modifier = modifier.height(46.dp),
        contentPadding = PaddingValues(horizontal = 8.dp)
    ) {
        Text(text, color = Color.White, fontSize = 15.sp, fontWeight = FontWeight.Bold)
    }
}

@Composable
fun ChipElement(
    text: String,
    icon: String = "",
    iconRes: Int? = null,
    bgColor: Color,
    modifier: Modifier = Modifier
) {
    Row(
        modifier = modifier
            .clip(RoundedCornerShape(8.dp))
            .background(bgColor)
            .padding(horizontal = 12.dp, vertical = 10.dp),
        verticalAlignment = Alignment.CenterVertically,
        horizontalArrangement = Arrangement.Center
    ) {
        if (iconRes != null) {
            Image(
                painter = painterResource(id = iconRes),
                contentDescription = null,
                modifier = Modifier.size(20.dp)
            )
        } else if (icon.isNotEmpty()) {
            Text(icon, fontSize = 16.sp)
        }
        Spacer(Modifier.width(8.dp))
        Text(text, color = DT.TextMain, fontSize = 15.sp, fontWeight = FontWeight.Bold)
    }
}

@Composable
fun StatusTag(text: String, bg: Color, modifier: Modifier = Modifier) {
    Box(
        modifier = modifier
            .background(bg)
            .padding(horizontal = 8.dp, vertical = 6.dp)
    ) {
        Text(text, color = DT.White, fontSize = 14.sp, fontWeight = FontWeight.Bold)
    }
}