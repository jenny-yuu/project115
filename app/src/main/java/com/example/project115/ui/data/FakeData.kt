package com.example.project115.ui.data

data class LineItem(val name: String)

enum class Health { DELAY, SUSPENDED }

data class AbnormalStation(
    val stationName: String,
    val lineName: String,
    val health: Health,
    val delayMinutes: Int = 0,
)

object FakeData {
    val lines = listOf(
        LineItem("北迴線"),
        LineItem("宜蘭線"),
        LineItem("台東線"),
    )

    // ✅ 每條路線展開後顯示的異常車站（照你圖六：誤點/停駛）
    val abnormalByLine: Map<String, List<AbnormalStation>> = mapOf(
        "北迴線" to listOf(
            AbnormalStation("和平站", "北迴線", Health.SUSPENDED),
            AbnormalStation("新城站", "北迴線", Health.DELAY, delayMinutes = 3),
        ),
        "宜蘭線" to listOf(
            AbnormalStation("羅東站", "宜蘭線", Health.DELAY, delayMinutes = 6),
            AbnormalStation("宜蘭站", "宜蘭線", Health.DELAY, delayMinutes = 4),
        ),
        "台東線" to listOf(
            AbnormalStation("吉安站", "台東線", Health.DELAY, delayMinutes = 5),
            AbnormalStation("壽豐站", "台東線", Health.SUSPENDED),
        )
    )

    fun counts(line: String): Pair<Int, Int> {
        val list = abnormalByLine[line].orEmpty()
        val delay = list.count { it.health == Health.DELAY }
        val suspended = list.count { it.health == Health.SUSPENDED }
        return delay to suspended
    }
}