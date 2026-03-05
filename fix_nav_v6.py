import os

path = r"D:\Android_Project\project115\app\src\main\java\com\example\project115\ui\screens\StationDetailScreen.kt"

with open(path, 'r', encoding='utf-8') as f:
    lines = f.readlines()

new_lines = []
skip_until = -1

for i, line in enumerate(lines):
    if i < skip_until:
        continue
    
    # 1. 新增 Evidence 與 Simulation 狀態
    if 'var recoveryReason by remember { mutableStateOf<String>("") }' in line:
        new_lines.append(line)
        new_lines.append('    // 新增證據紀錄與顯示開關\n')
        new_lines.append('    var evidenceList by remember { mutableStateOf<List<JSONObject>>(emptyList()) }\n')
        new_lines.append('    var showEvidenceDialog by remember { mutableStateOf(false) }\n')
        new_lines.append('    var isSimulationMode by remember { mutableStateOf(false) }\n')
        continue

    # 2. 修改 fetchAiAdvice 邏輯：更新證據列表與模擬參數
    if 'put("query", "目前地震或強降雨導致${stationName}營運中斷，請參考歷史經驗推估恢復時間。")' in line:
        indent = line[:line.find('put')]
        new_lines.append(f'{indent}put("query", "目前地震或強降雨導致${{stationName}}營運中斷，請參考歷史經驗推估恢復時間。")\n')
        new_lines.append(f'{indent}put("is_simulation", isSimulationMode)\n')
        continue

    if 'recoveryReason = res.optString("reason", "")' in line:
        indent = line[:line.find('recoveryReason')]
        new_lines.append(line)
        new_lines.append(f'{indent}val evArray = res.optJSONArray("evidence")\n')
        new_lines.append(f'{indent}val list = mutableListOf<JSONObject>()\n')
        new_lines.append(f'{indent}if (evArray != null) {{\n')
        new_lines.append(f'{indent}    for (j in 0 until evArray.length()) list.add(evArray.getJSONObject(j))\n')
        new_lines.append(f'{indent}}}\n')
        new_lines.append(f'{indent}evidenceList = list\n')
        continue

    # 3. 更新停駛判斷 (支援模擬模式)
    if 'val isSuspended = currentStation?.health_light == "紅燈" || health == "SUSPENDED"' in line:
        new_lines.append('    val isSuspended = currentStation?.health_light == "紅燈" || health == "SUSPENDED" || isSimulationMode\n')
        continue

    # 4. 卡片加入點擊事件
    if 'InfoCardFilled("預估恢復：$recoveryTime", modifier = contentModifier)' in line:
        indent = line[:line.find('InfoCardFilled')]
        new_lines.append(f'{indent}InfoCardFilled(\n')
        new_lines.append(f'{indent}    "預估恢復：$recoveryTime", \n')
        new_lines.append(f'{indent}    modifier = contentModifier.clickable {{ \n')
        new_lines.append(f'{indent}        if (evidenceList.isNotEmpty()) showEvidenceDialog = true \n')
        new_lines.append(f'{indent}    }}\n')
        new_lines.append(f'{indent})\n')
        continue

    # 5. 在頁面底端加入 Evidence Dialog
    if 'Box(' in line and i > 200: # 確保在主 UI Box 內
        # 尋找 IconButton 區域插入模擬按鈕
        pass
    
    if 'onBack' in line and 'IconButton' in line:
        indent = line[:line.find('IconButton')]
        # 在返回鍵旁邊加一個隱藏的模擬按鈕
        new_lines.append(f'{indent}IconButton(onClick = {{ isSimulationMode = !isSimulationMode; fetchAiAdvice() }}) {{\n')
        new_lines.append(f'{indent}    Icon(Icons.Filled.NotificationsNone, contentDescription = null, tint = if (isSimulationMode) DT.BtnBlue else DT.TextSub.copy(alpha=0.3f))\n')
        new_lines.append(f'{indent}}}\n')
        new_lines.append(line)
        continue

    new_lines.append(line)

# 在檔案末尾插入 Dialog 函數 (或是直接在最後一個花括號前)
# 我們先嘗試在最後一個 } 前插入
for i in range(len(new_lines)-1, -1, -1):
    if '}' in new_lines[i]:
        # 插入對話框 Composable
        dialog_code = """
    if (showEvidenceDialog) {
        AlertDialog(
            onDismissRequest = { showEvidenceDialog = false },
            title = { Text("RAG 恢復時間推估依據", fontWeight = FontWeight.Bold) },
            text = {
                Column(modifier = Modifier.verticalScroll(rememberScrollState())) {
                    Text("AI 自動檢索了以下歷史案例與 SOP 作為參考：", color = DT.TextSub, fontSize = 14.sp)
                    Spacer(Modifier.height(12.dp))
                    evidenceList.forEach { ev ->
                        Card(
                            modifier = Modifier.fillMaxWidth().padding(vertical = 4.dp),
                            colors = CardDefaults.cardColors(containerColor = Color(0xFFF5F7FA))
                        ) {
                            Column(Modifier.padding(12.dp)) {
                                Text("情境：${ev.optString("situation")}", fontWeight = FontWeight.Bold, fontSize = 14.sp)
                                Text("處置：${ev.optString("solution")}", fontSize = 13.sp)
                                Text("耗時：${ev.optString("recovery_time")}", color = DT.BtnBlue, fontSize = 13.sp, fontWeight = FontWeight.Bold)
                                Text("來源：${ev.optString("source")}", color = Color.Gray, fontSize = 11.sp)
                            }
                        }
                    }
                }
            },
            confirmButton = {
                TextButton(onClick = { showEvidenceDialog = false }) { Text("關閉") }
            }
        )
    }
"""
        new_lines.insert(i, dialog_code)
        break

with open(path, 'w', encoding='utf-8') as f:
    f.writelines(new_lines)

print("Done")
