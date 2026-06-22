package com.nyatifier.app

import android.content.BroadcastReceiver
import android.content.Context
import android.content.Intent

/**
 * 通知栏按钮点击处理器
 */
class NotificationReceiver : BroadcastReceiver() {
    override fun onReceive(context: Context, intent: Intent) {
        val service = NyatifierService.instance ?: return

        when (intent.action) {
            "toggle_mode" -> service.toggleMode()
            "undo" -> service.onUndo()
        }
    }
}
