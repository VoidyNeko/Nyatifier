package com.nyatifier.app

import android.app.Notification
import android.app.NotificationChannel
import android.app.NotificationManager
import android.app.PendingIntent
import android.content.Intent
import android.os.Build

/**
 * 通知栏助手 — 前途服务保活 + 快捷操作
 * IMPORTANCE_MIN = 静默，不弹出横幅
 */
class NotificationHelper(private val service: NyatifierService) {

    companion object {
        const val CHANNEL_ID = "nyatifier_foreground"
        const val NOTIFICATION_ID = 1
    }

    private val notificationManager =
        service.getSystemService(NotificationManager::class.java)

    init {
        createChannel()
    }

    private fun createChannel() {
        if (Build.VERSION.SDK_INT >= Build.VERSION_CODES.O) {
            val channel = NotificationChannel(
                CHANNEL_ID,
                "喵笔生花",
                NotificationManager.IMPORTANCE_MIN  // 静默，不响铃不弹横幅
            ).apply {
                description = "喵笔生花无障碍服务"
                setShowBadge(false)
                setSound(null, null)
                vibrationPattern = longArrayOf(0)
                enableVibration(false)
            }
            notificationManager.createNotificationChannel(channel)
        }
    }

    fun startForeground() {
        if (Build.VERSION.SDK_INT >= Build.VERSION_CODES.Q) {
            service.startForeground(
                NOTIFICATION_ID,
                buildNotification(),
                android.content.pm.ServiceInfo.FOREGROUND_SERVICE_TYPE_SPECIAL_USE
            )
        }
    }

    fun updateNotification(catMode: Boolean, enabled: Boolean) {
        notificationManager.notify(NOTIFICATION_ID, buildNotification())
    }

    fun cancel() {
        notificationManager.cancel(NOTIFICATION_ID)
    }

    private fun buildNotification(): Notification {
        val openIntent = PendingIntent.getActivity(
            service, 0,
            Intent(service, SettingsActivity::class.java),
            PendingIntent.FLAG_IMMUTABLE or PendingIntent.FLAG_UPDATE_CURRENT
        )

        @Suppress("DEPRECATION")
        return if (Build.VERSION.SDK_INT >= Build.VERSION_CODES.O) {
            Notification.Builder(service, CHANNEL_ID)
                .setContentTitle("喵笔生花")
                .setContentText("(=^・ω・^=) 运行中")
                .setSmallIcon(android.R.drawable.star_on)
                .setOngoing(true)
                .setContentIntent(openIntent)
                .build()
        } else {
            Notification.Builder(service)
                .setContentTitle("喵笔生花")
                .setContentText("(=^・ω・^=) 运行中")
                .setSmallIcon(android.R.drawable.star_on)
                .setOngoing(true)
                .setContentIntent(openIntent)
                .setPriority(Notification.PRIORITY_MIN)
                .build()
        }
    }
}
