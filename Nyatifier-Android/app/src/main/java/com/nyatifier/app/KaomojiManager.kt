package com.nyatifier.app

import android.content.Context
import org.json.JSONObject
import java.io.BufferedReader
import java.io.InputStreamReader

/**
 * 颜文字管理器
 * 从 raw/kamojis.json 加载，按 enabled/disabled/exceeded 分类管理
 */
object KaomojiManager {

    data class KaomojiSet(
        val enabled: List<String>,
        val disabled: List<String>,
        val exceeded: List<String>
    )

    private var kamojis: KaomojiSet = KaomojiSet(
        enabled = listOf("(^ω^)"),
        disabled = listOf(",,◔ д ◔,,"),
        exceeded = emptyList()
    )

    fun load(context: Context) {
        try {
            val input = context.resources.openRawResource(R.raw.kamojis)
            val reader = BufferedReader(InputStreamReader(input, "UTF-8"))
            val json = reader.readText()
            reader.close()

            val obj = JSONObject(json)
            kamojis = KaomojiSet(
                enabled = obj.getJSONArray("enabled").toStringList(),
                disabled = obj.getJSONArray("disabled").toStringList(),
                exceeded = obj.getJSONArray("exceeded").toStringList()
            )
        } catch (e: Exception) {
            // 保持默认值
        }
    }

    /** 随机取一个开启模式的颜文字 */
    fun randomEnabled(): String = kamojis.enabled.random()

    /** 随机取一个关闭模式的颜文字 */
    fun randomDisabled(): String = kamojis.disabled.random()

    /** 随机取一个超字数模式的颜文字 */
    fun randomExceeded(): String = kamojis.exceeded.random()

    /** 获取所有启用列表（供设置页勾选） */
    fun getAllEnabled(): List<String> = kamojis.enabled

    fun getAllDisabled(): List<String> = kamojis.disabled

    private fun org.json.JSONArray.toStringList(): List<String> {
        val list = mutableListOf<String>()
        for (i in 0 until length()) {
            list.add(getString(i))
        }
        return list
    }
}
