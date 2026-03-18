import os

path = r"D:\Android_Project\project115\app\src\main\java\com\example\project115\ui\screens\StationDetailScreen.kt"

with open(path, 'r', encoding='utf-8') as f:
    lines = f.readlines()

new_lines = []
skip_until = -1

for i, line in enumerate(lines):
    if i < skip_until:
        continue
    
    # 1. 新增 Recovery 狀態
    if 'var aiError by remember { mutableStateOf<String?>(null) }' in line:
        new_lines.append(line)
        new_lines.append('    var recoveryTime by remember { mutableStateOf<String>("評估中") }\n')
        new_lines.append('    var recoveryReason by remember { mutableStateOf<String>("") }\n')
        continue

    # 2. 修改 fetchAiAdvice 加入回復時間推估
    if 'suspend fun fetchAiAdvice() {' in line:
        indent = line[:line.find('suspend')]
        new_lines.append(line)
        new_lines.append(f'{indent}    // 啟動回復時間推估 (僅在嚴重時觸發)\n')
        new_lines.append(f'{indent}    if (isSuspended || actualDelay >= 20) {{\n')
        new_lines.append(f'{indent}        coroutineScope.launch(Dispatchers.IO) {{\n')
        new_lines.append(f'{indent}            try {{\n')
        new_lines.append(f'{indent}                val ips = listOf("10.0.2.2", "172.21.112.1", "192.168.0.129")\n')
        new_lines.append(f'{indent}                for (ip in ips) {{\n')
        new_lines.append(f'{indent}                    try {{\n')
        new_lines.append(f'{indent}                        val url = URL("http://$ip:5000/predict_recovery")\n')
        new_lines.append(f'{indent}                        val conn = url.openConnection() as HttpURLConnection\n')
        new_lines.append(f'{indent}                        conn.requestMethod = "POST"\n')
        new_lines.append(f'{indent}                        conn.setRequestProperty("Content-Type", "application/json")\n')
        new_lines.append(f'{indent}                        conn.doOutput = true\n')
        new_lines.append(f'{indent}                        val param = JSONObject().apply {{\n')
        new_lines.append(f'{indent}                            put("station_name", stationName)\n')
        new_lines.append(f'{indent}                            put("query", "目前地震或強降雨導致${{stationName}}營運中斷，請參考歷史經驗推估恢復時間。")\n')
        new_lines.append(f'{indent}                        }}\n')
        new_lines.append(f'{indent}                        conn.outputStream.write(param.toString().toByteArray())\n')
        new_lines.append(f'{indent}                        if (conn.responseCode == 200) {{\n')
        new_lines.append(f'{indent}                            val res = JSONObject(conn.inputStream.bufferedReader().readText())\n')
        new_lines.append(f'{indent}                            recoveryTime = res.optString("recovery_time", "評估中")\n')
        new_lines.append(f'{indent}                            recoveryReason = res.optString("reason", "")\n')
        new_lines.append(f'{indent}                            break\n')
        new_lines.append(f'{indent}                        }}\n')
        new_lines.append(f'{indent}                    }} catch (e: Exception) {{ }}\n')
        new_lines.append(f'{indent}                }}\n')
        new_lines.append(f'{indent}            }} catch (e: Exception) {{ }}\n')
        new_lines.append(f'{indent}        }}\n')
        new_lines.append(f'{indent}    }}\n')
        continue

    # 3. 更新 UI 顯示 (預估恢復卡片)
    if 'InfoCardFilled("預估恢復：2～4 小時", modifier = contentModifier)' in line:
        indent = line[:line.find('InfoCardFilled')]
        new_lines.append(f'{indent}InfoCardFilled("預估恢復：$recoveryTime", modifier = contentModifier)\n')
        new_lines.append(f'{indent}if (recoveryReason.isNotEmpty()) {{\n')
        new_lines.append(f'{indent}    Spacer(Modifier.height(4.dp))\n')
        new_lines.append(f'{indent}    Text(\n')
        new_lines.append(f'{indent}        "依據：$recoveryReason",\n')
        new_lines.append(f'{indent}        color = DT.TextSub, \n')
        new_lines.append(f'{indent}        fontSize = 12.sp,\n')
        new_lines.append(f'{indent}        modifier = contentModifier.padding(horizontal = 8.dp)\n')
        new_lines.append(f'{indent}    )\n')
        new_lines.append(f'{indent}}}\n')
        continue
        
    new_lines.append(line)

with open(path, 'w', encoding='utf-8') as f:
    f.writelines(new_lines)

print("Done")
