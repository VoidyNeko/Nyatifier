package com.nyatifier.app

import android.accessibilityservice.AccessibilityService
import android.content.*
import android.graphics.PixelFormat
import android.os.Build
import android.os.Bundle
import android.os.Handler
import android.os.Looper
import android.util.Log
import android.view.Gravity
import android.view.LayoutInflater
import android.view.View
import android.view.WindowManager
import android.view.accessibility.AccessibilityEvent
import android.view.accessibility.AccessibilityNodeInfo
import android.widget.*

class NyatifierService : AccessibilityService() {

    enum class NyatifyResult { SUCCESS, NO_INPUT, EMPTY, OVER_THRESHOLD, DISABLED }

    companion object {
        private const val TAG = "Nyatifier"
        const val PREF_NAME = "nyatifier_prefs"
        const val KEY_CAT_MODE = "cat_mode"
        const val KEY_CHAR_THRESHOLD = "char_threshold"
        const val KEY_ENABLED = "enabled"
        const val KEY_OVERLAY_SIZE = "overlay_size"

        @Volatile
        var instance: NyatifierService? = null
            private set
    }

    private lateinit var overlay: FloatingOverlay
    private lateinit var notificationHelper: NotificationHelper
    private var catMode = true
    private var charThreshold = 500
    private var enabled = true
    private var overlaySizeDp = 64

    private var nyatifyDialogView: View? = null  // 双击弹出对话框

    private var lastOriginalText: String? = null
    private var lastConvertedText: String? = null
    private var lastNodeWindowId = -1
    private var lastNodeViewId: String? = null
    private var lastNodeClassName: String? = null
    private var lastNodeText: String? = null  // 用于撤回时精准匹配

    override fun onCreate() {
        super.onCreate()
        instance = this

        KaomojiManager.load(this)

        val prefs = getSharedPreferences(PREF_NAME, MODE_PRIVATE)
        catMode = prefs.getBoolean(KEY_CAT_MODE, true)
        charThreshold = prefs.getInt(KEY_CHAR_THRESHOLD, 500)
        enabled = prefs.getBoolean(KEY_ENABLED, true)
        overlaySizeDp = prefs.getInt(KEY_OVERLAY_SIZE, 64)
        Log.d(TAG, "onCreate: catMode=$catMode threshold=$charThreshold enabled=$enabled size=$overlaySizeDp")

        overlay = FloatingOverlay(this, {
            val intent = Intent(this, SettingsActivity::class.java)
            intent.addFlags(Intent.FLAG_ACTIVITY_NEW_TASK)
            startActivity(intent)
        }, {
            showNyatifyDialog()
        })

        notificationHelper = NotificationHelper(this)
    }

    override fun onServiceConnected() {
        super.onServiceConnected()
        Log.d(TAG, "Service connected, enabled=$enabled, size=$overlaySizeDp")

        if (enabled) overlay.show(overlaySizeDp)
        if (Build.VERSION.SDK_INT >= Build.VERSION_CODES.Q) notificationHelper.startForeground()
    }

    override fun onAccessibilityEvent(event: AccessibilityEvent?) {}

    override fun onInterrupt() {}

    override fun onTaskRemoved(rootIntent: Intent?) {
        super.onTaskRemoved(rootIntent)
    }

    override fun onDestroy() {
        Log.d(TAG, "Service destroying")
        dismissNyatifyDialog()
        overlay.hide()
        notificationHelper.cancel()
        instance = null
        super.onDestroy()
    }

    // ========== 核心 ==========

    fun onNyatify(): NyatifyResult {
        if (!enabled) return NyatifyResult.DISABLED
        Log.d(TAG, "onNyatify() start, catMode=$catMode, threshold=$charThreshold")

        val focused = findFocusedInput()
        if (focused == null) {
            Log.d(TAG, "onNyatify() -> NO_INPUT (no editable node found)")
            return NyatifyResult.NO_INPUT
        }
        Log.d(TAG, "onNyatify() found focused node: className=${focused.className}, packageName=${focused.packageName}")

        val text = focused.text?.toString() ?: ""
        if (text.isEmpty()) {
            Log.d(TAG, "onNyatify() -> EMPTY (text is blank)")
            return NyatifyResult.EMPTY
        }
        Log.d(TAG, "onNyatify() text len=${text.length}, preview=${text.take(30)}")

        if (charThreshold > 0 && text.length > charThreshold) {
            Log.d(TAG, "onNyatify() -> OVER_THRESHOLD (len=${text.length} > $charThreshold)")
            return NyatifyResult.OVER_THRESHOLD
        }

        val converted = CatConverter.convertToCatSpeak(text, catMode)
        lastOriginalText = text
        lastConvertedText = converted
        lastNodeWindowId = focused.windowId
        lastNodeViewId = focused.viewIdResourceName
        lastNodeClassName = focused.className?.toString()
        lastNodeText = focused.text?.toString()

        val directOk = setNodeText(focused, converted)
        if (!directOk) {
            Log.d(TAG, "onNyatify() ACTION_SET_TEXT failed, trying clipboard paste")
            pasteViaClipboard(focused, text, converted)
        } else {
            Log.d(TAG, "onNyatify() ACTION_SET_TEXT success")
        }

        Log.d(TAG, "onNyatify() -> SUCCESS (${text.length} chars -> ${converted.length} chars)")
        return NyatifyResult.SUCCESS
    }

    /** 撤回 */
    fun onUndo() {
        val original = lastOriginalText ?: return
        val expected = lastConvertedText ?: return
        Log.d(TAG, "onUndo() start, target windowId=$lastNodeWindowId, viewId=$lastNodeViewId")

        val focused = findNodeById(lastNodeWindowId, lastNodeViewId, lastNodeClassName, lastNodeText)
            ?: findFocusedInput()
        if (focused == null) {
            Log.d(TAG, "onUndo() -> can't find target node")
            return
        }
        Log.d(TAG, "onUndo() found node: ${focused.className} in window ${focused.windowId}")

        val current = focused.text?.toString() ?: ""
        if (current != expected) {
            Log.d(TAG, "onUndo() text mismatch: current=${current.take(20)}, expected=${expected.take(20)}")
            if (!current.contains(expected) && !expected.contains(current)) {
                Log.d(TAG, "onUndo() -> text changed, giving up")
                return
            }
        }

        lastOriginalText = null
        lastConvertedText = null
        lastNodeWindowId = -1
        lastNodeViewId = null
        lastNodeClassName = null
        lastNodeText = null

        Log.d(TAG, "onUndo() using clipboard paste for reliability")
        clipboardReplace(focused, original)
        Log.d(TAG, "onUndo() -> done")
    }

    fun toggleMode() {
        catMode = !catMode
        getSharedPreferences(PREF_NAME, MODE_PRIVATE)
            .edit().putBoolean(KEY_CAT_MODE, catMode).apply()
        notificationHelper.updateNotification(catMode, enabled)
    }

    fun toggleEnabled() {
        enabled = !enabled
        getSharedPreferences(PREF_NAME, MODE_PRIVATE)
            .edit().putBoolean(KEY_ENABLED, enabled).apply()
        if (enabled) overlay.show(overlaySizeDp) else overlay.hide()
        notificationHelper.updateNotification(catMode, enabled)
    }

    fun refreshSettings() {
        val prefs = getSharedPreferences(PREF_NAME, MODE_PRIVATE)
        catMode = prefs.getBoolean(KEY_CAT_MODE, true)
        charThreshold = prefs.getInt(KEY_CHAR_THRESHOLD, 500)
        enabled = prefs.getBoolean(KEY_ENABLED, true)
        Log.d(TAG, "refreshSettings: catMode=$catMode threshold=$charThreshold enabled=$enabled")
    }

    fun updateOverlaySize(newSizeDp: Int) {
        overlaySizeDp = newSizeDp
        overlay.resize(newSizeDp)
    }

    fun isCatMode(): Boolean = catMode

    // ========== 内部 ==========

    private fun findFocusedInput(): AccessibilityNodeInfo? {
        var wechatDebugged = false
        for (i in 0 until windows.size) {
            val root = windows[i]?.root ?: continue
            if (root.childCount == 0) continue
            val pkg = root.packageName?.toString() ?: ""

            if (!wechatDebugged && pkg == "com.tencent.mm") {
                wechatDebugged = true
                Log.d(TAG, "WeChat window found: childCount=${root.childCount}, className=${root.className}")
                dumpInputNodes(root, 0)
            }

            root.findFocus(AccessibilityNodeInfo.FOCUS_INPUT)?.let {
                if (it.isEditable) return it
                if (it.text != null && it.isFocused) return it
            }

            findEditableNode(root)?.let { return it }
            findFocusedTextNode(root)?.let { return it }
        }
        val root = rootInActiveWindow ?: return null
        if (root.childCount == 0) return null
        root.findFocus(AccessibilityNodeInfo.FOCUS_INPUT)?.let {
            if (it.isEditable) return it
            if (it.text != null && it.isFocused) return it
        }
        findEditableNode(root)?.let { return it }
        return findFocusedTextNode(root)
    }

    private fun findEditableNode(node: AccessibilityNodeInfo): AccessibilityNodeInfo? {
        if (node.isEditable && node.isFocused) return node
        if (node.isEditable) return node
        for (i in 0 until node.childCount) {
            node.getChild(i)?.let { findEditableNode(it)?.let { f -> return f } }
        }
        return null
    }

    private fun findFocusedTextNode(node: AccessibilityNodeInfo): AccessibilityNodeInfo? {
        if (node.isFocused && node.text != null && node.text.length > 0) return node
        for (i in 0 until node.childCount) {
            node.getChild(i)?.let { findFocusedTextNode(it)?.let { f -> return f } }
        }
        return null
    }

    private fun dumpInputNodes(node: AccessibilityNodeInfo, depth: Int) {
        if (depth > 3) return
        val info = buildString {
            append("  ".repeat(depth))
            append("${node.className}")
            if (node.isEditable) append(" [EDITABLE]")
            if (node.isFocused) append(" [FOCUSED]")
            if (node.isClickable) append(" [CLICKABLE]")
            val t = node.text?.toString()?.take(30) ?: ""
            if (t.isNotEmpty()) append(" text=\"$t\"")
            val vid = node.viewIdResourceName ?: ""
            if (vid.isNotEmpty()) append(" id=$vid")
        }
        Log.d(TAG, info)
        for (i in 0 until node.childCount) {
            node.getChild(i)?.let { dumpInputNodes(it, depth + 1) }
        }
    }

    private fun findNodeById(windowId: Int, viewId: String?, className: String?, nodeText: String?): AccessibilityNodeInfo? {
        if (windowId < 0) return null
        for (i in 0 until windows.size) {
            val window = windows[i] ?: continue
            if (window.id != windowId) continue
            val root = window.root ?: continue
            val found = findByViewId(root, viewId, className, nodeText)
            if (found != null) return found
        }
        return null
    }

    private fun findByViewId(node: AccessibilityNodeInfo, viewId: String?, className: String?, nodeText: String?): AccessibilityNodeInfo? {
        if (viewId != null && node.viewIdResourceName == viewId) {
            if (node.isEditable) return node
        }
        if (viewId == null && className != null && node.className?.toString() == className && node.isEditable) {
            val current = node.text?.toString() ?: ""
            if (nodeText != null && current == nodeText) return node
            if (nodeText == null) return node
        }
        for (i in 0 until node.childCount) {
            node.getChild(i)?.let { findByViewId(it, viewId, className, nodeText)?.let { f -> return f } }
        }
        return null
    }

    private fun setNodeText(node: AccessibilityNodeInfo, text: String): Boolean {
        if (Build.VERSION.SDK_INT < Build.VERSION_CODES.LOLLIPOP) return false
        node.performAction(AccessibilityNodeInfo.ACTION_FOCUS)
        val args = Bundle().apply {
            putCharSequence(AccessibilityNodeInfo.ACTION_ARGUMENT_SET_TEXT_CHARSEQUENCE, text)
        }
        return node.performAction(AccessibilityNodeInfo.ACTION_SET_TEXT, args)
    }

    // ========== 剪贴板粘贴兜底 (WeChat / WebView) ==========

    private fun pasteViaClipboard(node: AccessibilityNodeInfo, originalText: String, convertedText: String) {
        Log.d(TAG, "pasteViaClipboard() start, origLen=${originalText.length}, newLen=${convertedText.length}")
        node.performAction(AccessibilityNodeInfo.ACTION_FOCUS)
        node.performAction(AccessibilityNodeInfo.ACTION_SET_SELECTION, Bundle().apply {
            putInt(AccessibilityNodeInfo.ACTION_ARGUMENT_SELECTION_START_INT, 0)
            putInt(AccessibilityNodeInfo.ACTION_ARGUMENT_SELECTION_END_INT, originalText.length)
        })

        val clipboard = getSystemService(CLIPBOARD_SERVICE) as android.content.ClipboardManager
        val oldClip = clipboard.primaryClip
        clipboard.setPrimaryClip(ClipData.newPlainText("nyatifier", convertedText))

        android.os.Handler(mainLooper).postDelayed({
            node.performAction(AccessibilityNodeInfo.ACTION_PASTE)
            Log.d(TAG, "pasteViaClipboard() PASTE executed")
            oldClip?.let {
                android.os.Handler(mainLooper).postDelayed({
                    clipboard.setPrimaryClip(it)
                }, 300)
            }
        }, 80)
    }

    private fun clipboardReplace(node: AccessibilityNodeInfo, text: String) {
        Log.d(TAG, "clipboardReplace() start, newText=${text.take(20)}")
        node.performAction(AccessibilityNodeInfo.ACTION_FOCUS)
        node.performAction(AccessibilityNodeInfo.ACTION_SET_SELECTION, Bundle().apply {
            putInt(AccessibilityNodeInfo.ACTION_ARGUMENT_SELECTION_START_INT, 0)
            putInt(AccessibilityNodeInfo.ACTION_ARGUMENT_SELECTION_END_INT, node.text?.length ?: 0)
        })
        val clipboard = getSystemService(CLIPBOARD_SERVICE) as android.content.ClipboardManager
        val old = clipboard.primaryClip
        clipboard.setPrimaryClip(ClipData.newPlainText("nyatifier", text))
        android.os.Handler(mainLooper).postDelayed({
            node.performAction(AccessibilityNodeInfo.ACTION_PASTE)
            Log.d(TAG, "clipboardReplace() PASTE executed")
            old?.let {
                android.os.Handler(mainLooper).postDelayed({ clipboard.setPrimaryClip(it) }, 300)
            }
        }, 80)
    }

    // ========== 手动喵化对话框（双击悬浮球） ==========

    private fun showNyatifyDialog() {
        // 已有对话框则先关掉
        dismissNyatifyDialog()

        val wm = getSystemService(WINDOW_SERVICE) as WindowManager
        val inflater = LayoutInflater.from(this)
        val root = inflater.inflate(R.layout.float_dialog_nyatify, null) as LinearLayout

        // 全屏暗背景 + 居中卡片
        val container = LinearLayout(this).apply {
            orientation = LinearLayout.VERTICAL
            gravity = Gravity.CENTER
            setBackgroundColor(0x80000000.toInt())
            setOnClickListener {
                // 点击暗区关闭
                dismissNyatifyDialog()
            }
            addView(root)
        }

        // 阻止卡片内部点击穿透到暗区
        root.setOnClickListener {}

        val etInput = root.findViewById<EditText>(R.id.et_input)
        val tvResult = root.findViewById<TextView>(R.id.tv_result)
        val btnNyatify = root.findViewById<Button>(R.id.btn_nyatify)
        val btnCopy = root.findViewById<Button>(R.id.btn_copy)
        val btnClose = root.findViewById<Button>(R.id.btn_close)

        var lastConverted: String? = null

        btnNyatify.setOnClickListener {
            val text = etInput.text?.toString()?.trim() ?: ""
            if (text.isEmpty()) {
                Toast.makeText(this, "请输入或粘贴文字喵~", Toast.LENGTH_SHORT).show()
                return@setOnClickListener
            }
            if (charThreshold > 0 && text.length > charThreshold) {
                Toast.makeText(this, "超过了${charThreshold}字喵~", Toast.LENGTH_SHORT).show()
                overlay.flashYellow()
                return@setOnClickListener
            }
            val converted = CatConverter.convertToCatSpeak(text, catMode)
            if (converted == text) {
                Toast.makeText(this, "这段文字加不了喵呢...", Toast.LENGTH_SHORT).show()
                overlay.flashRed()
                return@setOnClickListener
            }
            lastConverted = converted
            tvResult.text = converted
            tvResult.visibility = View.VISIBLE
            btnCopy.visibility = View.VISIBLE
            btnNyatify.text = "重喵"
            overlay.flashGreen()
        }

        btnCopy.setOnClickListener {
            val text = lastConverted ?: return@setOnClickListener
            val clipboard = getSystemService(CLIPBOARD_SERVICE) as ClipboardManager
            clipboard.setPrimaryClip(ClipData.newPlainText("nyatifier", text))
            Toast.makeText(this, "已复制喵！切回去粘贴吧~", Toast.LENGTH_SHORT).show()
        }

        btnClose.setOnClickListener {
            dismissNyatifyDialog()
        }

        val params = WindowManager.LayoutParams(
            WindowManager.LayoutParams.MATCH_PARENT,
            WindowManager.LayoutParams.MATCH_PARENT,
            if (Build.VERSION.SDK_INT >= Build.VERSION_CODES.O)
                WindowManager.LayoutParams.TYPE_ACCESSIBILITY_OVERLAY
            else @Suppress("DEPRECATION") WindowManager.LayoutParams.TYPE_PHONE,
            WindowManager.LayoutParams.FLAG_DIM_BEHIND,
            PixelFormat.TRANSLUCENT
        ).apply {
            gravity = Gravity.CENTER
            dimAmount = 0.5f
        }

        nyatifyDialogView = container
        wm.addView(container, params)
        Log.d(TAG, "nyatify dialog shown")
    }

    private fun dismissNyatifyDialog() {
        val view = nyatifyDialogView ?: return
        try {
            val wm = getSystemService(WINDOW_SERVICE) as WindowManager
            wm.removeView(view)
        } catch (_: Exception) {}
        nyatifyDialogView = null
        Log.d(TAG, "nyatify dialog dismissed")
    }
}
