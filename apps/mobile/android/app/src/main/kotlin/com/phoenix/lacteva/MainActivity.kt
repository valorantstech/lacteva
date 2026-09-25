package com.phoenix.lacteva

import android.app.NotificationChannel
import android.app.NotificationManager
import android.os.Build
import android.os.Bundle
import io.flutter.embedding.android.FlutterActivity

class MainActivity : FlutterActivity() {
    override fun onCreate(savedInstanceState: Bundle?) {
        super.onCreate(savedInstanceState)
        createNotificationChannel()
    }

    /**
     * WO-77. The channel every Lacteva notification is posted to, created
     * before any can arrive so Android shows a name a person can read in
     * system settings rather than "Miscellaneous". The platform's FCM
     * adapter names the same id in every message it sends.
     */
    private fun createNotificationChannel() {
        if (Build.VERSION.SDK_INT < Build.VERSION_CODES.O) return
        val channel = NotificationChannel(
            CHANNEL_ID,
            "Lacteva",
            NotificationManager.IMPORTANCE_HIGH,
        ).apply {
            description = "Bills, payments and the day's round"
        }
        val manager = getSystemService(NotificationManager::class.java)
        manager.createNotificationChannel(channel)
    }

    companion object {
        const val CHANNEL_ID = "lacteva"
    }
}
