package com.nyatifier.app

import android.accessibilityservice.AccessibilityServiceInfo
import android.content.Context
import android.content.Intent
import android.os.Bundle
import android.provider.Settings
import android.util.Log
import android.view.accessibility.AccessibilityManager
import androidx.appcompat.app.AppCompatActivity

class MainActivity : AppCompatActivity() {

    companion object {
        private const val TAG = "Nyatifier"
    }

    override fun onCreate(savedInstanceState: Bundle?) {
        super.onCreate(savedInstanceState)
        Log.d(TAG, "MainActivity.onCreate()")
        setContentView(R.layout.activity_main)

        val btnEnable = findViewById<android.widget.Button>(R.id.btn_enable_service)
        val btnSettings = findViewById<android.widget.Button>(R.id.btn_settings)
        val statusText = findViewById<android.widget.TextView>(R.id.tv_status)

        btnEnable.setOnClickListener {
            val intent = Intent(Settings.ACTION_ACCESSIBILITY_SETTINGS)
            startActivity(intent)
        }

        btnSettings.setOnClickListener {
            startActivity(Intent(this, SettingsActivity::class.java))
        }

        updateUI(statusText, btnEnable, btnSettings)
    }

    override fun onResume() {
        super.onResume()
        val btnEnable = findViewById<android.widget.Button>(R.id.btn_enable_service)
        val btnSettings = findViewById<android.widget.Button>(R.id.btn_settings)
        val statusText = findViewById<android.widget.TextView>(R.id.tv_status)
        updateUI(statusText, btnEnable, btnSettings)
    }

    private fun updateUI(
        statusText: android.widget.TextView,
        btnEnable: android.widget.Button,
        btnSettings: android.widget.Button
    ) {
        if (isAccessibilityServiceEnabled()) {
            statusText.text = getString(R.string.service_status_on)
            statusText.setTextColor(0xFF88FF88.toInt())
            btnEnable.visibility = android.view.View.GONE
            btnSettings.visibility = android.view.View.VISIBLE
        } else {
            statusText.text = getString(R.string.service_status_off)
            statusText.setTextColor(0xFFFF8888.toInt())
            btnEnable.visibility = android.view.View.VISIBLE
            btnSettings.visibility = android.view.View.GONE
        }
    }

    private fun isAccessibilityServiceEnabled(): Boolean {
        val am = getSystemService(Context.ACCESSIBILITY_SERVICE) as AccessibilityManager
        val services = am.getEnabledAccessibilityServiceList(AccessibilityServiceInfo.FEEDBACK_ALL_MASK)
        val enabled = services.any {
            it.resolveInfo.serviceInfo.packageName == packageName &&
                it.resolveInfo.serviceInfo.name == NyatifierService::class.java.name
        }
        Log.d(TAG, "isAccessibilityServiceEnabled() = $enabled")
        return enabled
    }
}
