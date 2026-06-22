package com.nyatifier.app

import android.animation.ArgbEvaluator
import android.animation.ValueAnimator
import android.content.Context
import android.graphics.Outline
import android.graphics.PixelFormat
import android.os.Build
import android.os.Handler
import android.os.Looper
import android.view.Gravity
import android.view.MotionEvent
import android.view.View
import android.view.ViewOutlineProvider
import android.view.WindowManager
import android.widget.ImageView
import android.widget.TextView

/**
 * 悬浮喵球 + 撤回箭头
 * 单击：猫化当前输入框文字
 * 双击：弹出手动喵化对话框（微信等无法自动获取文字的兜底）
 * 长按：进入设置页
 */
class FloatingOverlay(
    private val service: NyatifierService,
    private val onLongClick: () -> Unit,
    private val onDoubleClick: () -> Unit
) {
    private val windowManager: WindowManager =
        service.getSystemService(Context.WINDOW_SERVICE) as WindowManager
    private val density: Float = service.resources.displayMetrics.density
    private val handler = Handler(Looper.getMainLooper())

    private var floatingView: ImageView? = null
    private var undoView: View? = null
    private var currentSizeDp = 64
    private var isVisible = false
    private var lastParams: WindowManager.LayoutParams? = null

    // 拖动
    private var initialX = 0
    private var initialY = 0
    private var initialTouchX = 0f
    private var initialTouchY = 0f
    private var isDragging = false
    private var dragThreshold = 10f
    private var longPressRunnable: Runnable? = null
    private var isLongPress = false
    private var screenW = 0
    private var screenH = 0

    // 双击检测（DOWN时判断，UP无延迟执行）
    private var lastUpTime = 0L
    private var isDoubleTap = false
    private var wasLastTapDragged = false

    companion object {
        private const val SIZE_DP_DEFAULT = 64
        private const val FLASH_RED = 0x80FF4444.toInt()
        private const val FLASH_YELLOW = 0x80FFCC00.toInt()
        private const val FLASH_GREEN = 0x8044CC66.toInt()
        private const val FLASH_DURATION = 350L
        private const val FLASH_HOLD = 50L
        private const val DOUBLE_TAP_WINDOW = 400L
    }

    fun show(initialSizeDp: Int = SIZE_DP_DEFAULT) {
        if (isVisible) return
        isVisible = true
        currentSizeDp = initialSizeDp

        val px = (currentSizeDp * density).toInt()
        val cornerRadius = (currentSizeDp * density * 0.3f)

        val imageView = ImageView(service).apply {
            setImageResource(R.drawable.cat_icon)
            scaleType = ImageView.ScaleType.CENTER_CROP
            layoutParams = android.view.ViewGroup.LayoutParams(px, px)
            clipToOutline = true
            outlineProvider = object : ViewOutlineProvider() {
                override fun getOutline(view: View, outline: Outline) {
                    outline.setRoundRect(0, 0, view.width, view.height, cornerRadius)
                }
            }
            setColorFilter(0x00000000)
        }

        val displayMetrics = service.resources.displayMetrics
        val screenWidth = displayMetrics.widthPixels
        val screenHeight = displayMetrics.heightPixels
        screenW = screenWidth
        screenH = screenHeight

        val params = WindowManager.LayoutParams(
            px, px,
            if (Build.VERSION.SDK_INT >= Build.VERSION_CODES.O)
                WindowManager.LayoutParams.TYPE_ACCESSIBILITY_OVERLAY
            else @Suppress("DEPRECATION") WindowManager.LayoutParams.TYPE_PHONE,
            WindowManager.LayoutParams.FLAG_NOT_FOCUSABLE or
                WindowManager.LayoutParams.FLAG_LAYOUT_NO_LIMITS,
            PixelFormat.TRANSLUCENT
        ).apply {
            gravity = Gravity.TOP or Gravity.START
            x = (screenWidth - px) / 2
            y = (screenHeight - px) / 2
        }

        imageView.setOnTouchListener { view, event ->
            when (event.action) {
                MotionEvent.ACTION_DOWN -> {
                    isDragging = false
                    isLongPress = false
                    initialX = params.x
                    initialY = params.y
                    initialTouchX = event.rawX
                    initialTouchY = event.rawY

                    // 双击判断在DOWN时做：上一次UP在窗口内且没拖动 → 双击
                    val now = System.currentTimeMillis()
                    isDoubleTap = !wasLastTapDragged && (now - lastUpTime) < DOUBLE_TAP_WINDOW
                    if (isDoubleTap) {
                        lastUpTime = 0L
                        longPressRunnable?.let { handler.removeCallbacks(it) }
                        onDoubleClick()
                        true
                    } else {
                        longPressRunnable?.let { handler.removeCallbacks(it) }
                        longPressRunnable = Runnable {
                            isLongPress = true
                            onLongClick()
                        }
                        handler.postDelayed(longPressRunnable!!, 500)
                        true
                    }
                }
                MotionEvent.ACTION_MOVE -> {
                    val dx = event.rawX - initialTouchX
                    val dy = event.rawY - initialTouchY
                    if (Math.abs(dx) > dragThreshold || Math.abs(dy) > dragThreshold) {
                        isDragging = true
                        longPressRunnable?.let { handler.removeCallbacks(it) }
                    }
                    if (isDragging) {
                        params.x = (initialX + dx.toInt()).coerceIn(0, screenW - px)
                        params.y = (initialY + dy.toInt()).coerceIn(0, screenH - px)
                        windowManager.updateViewLayout(view, params)
                        repositionUndo(params)
                    }
                    true
                }
                MotionEvent.ACTION_UP -> {
                    longPressRunnable?.let { handler.removeCallbacks(it) }
                    if (isDoubleTap) {
                        // 双击已在DOWN处理，跳过
                        isDoubleTap = false
                    } else if (!isDragging && !isLongPress) {
                        // 单击立即执行，无延迟
                        onNyatifyClick()
                    }
                    lastUpTime = System.currentTimeMillis()
                    wasLastTapDragged = isDragging
                    true
                }
                else -> false
            }
        }

        floatingView = imageView
        lastParams = params
        windowManager.addView(imageView, params)
    }

    fun hide() {
        hideUndo()
        floatingView?.let {
            try { windowManager.removeView(it) } catch (_: Exception) {}
        }
        floatingView = null
        lastParams = null
        isVisible = false
    }

    fun resize(newSizeDp: Int) {
        if (!isVisible || newSizeDp == currentSizeDp) return
        hide()
        show(newSizeDp)
    }

    fun isShowing(): Boolean = isVisible

    // ========== 闪灯效果 ==========

    fun flashRed() = flash(FLASH_RED)
    fun flashYellow() = flash(FLASH_YELLOW)
    fun flashGreen() = flash(FLASH_GREEN)

    private fun flash(color: Int) {
        val view = floatingView ?: return
        view.post {
            view.setColorFilter(color)
            val anim = ValueAnimator.ofObject(ArgbEvaluator(), color, 0x00000000)
            anim.duration = FLASH_DURATION
            anim.startDelay = FLASH_HOLD
            anim.addUpdateListener { va ->
                view.setColorFilter(va.animatedValue as Int)
            }
            anim.start()
        }
    }

    // ========== 撤回按钮 ==========

    fun showUndoButton() {
        hideUndo()
        val params = lastParams ?: return
        val ballPx = (currentSizeDp * density).toInt()
        val btnSize = (32 * density).toInt()

        val undoBtn = TextView(service).apply {
            text = "↩"
            textSize = 18f
            setTextColor(0xFFFFB6C1.toInt())
            gravity = Gravity.CENTER
            setBackgroundColor(0xCC1A1A2E.toInt())
            clipToOutline = true
            outlineProvider = object : ViewOutlineProvider() {
                override fun getOutline(view: View, outline: Outline) {
                    outline.setRoundRect(0, 0, view.width, view.height, 16f * density)
                }
            }
            setOnClickListener {
                handler.postDelayed({
                    service.onUndo()
                    handler.post { hideUndo() }
                }, 100)
            }
        }

        val undoParams = WindowManager.LayoutParams(
            btnSize, btnSize,
            if (Build.VERSION.SDK_INT >= Build.VERSION_CODES.O)
                WindowManager.LayoutParams.TYPE_ACCESSIBILITY_OVERLAY
            else @Suppress("DEPRECATION") WindowManager.LayoutParams.TYPE_PHONE,
            WindowManager.LayoutParams.FLAG_NOT_FOCUSABLE or
                WindowManager.LayoutParams.FLAG_LAYOUT_NO_LIMITS,
            PixelFormat.TRANSLUCENT
        ).apply {
            gravity = Gravity.TOP or Gravity.START
            val totalWidth = ballPx + btnSize + (4 * density).toInt()
            if (params.x + totalWidth > screenW) {
                x = (params.x - btnSize - (4 * density).toInt()).coerceAtLeast(0)
            } else {
                x = params.x + ballPx + (4 * density).toInt()
            }
            y = (params.y + (ballPx - btnSize) / 2).coerceIn(0, screenH - btnSize)
        }

        undoView = undoBtn
        windowManager.addView(undoBtn, undoParams)
    }

    fun hideUndo() {
        undoView?.let {
            try { windowManager.removeView(it) } catch (_: Exception) {}
        }
        undoView = null
    }

    // ========== 内部 ==========

    private fun onNyatifyClick() {
        hideUndo()
        val result = service.onNyatify()
        when (result) {
            NyatifierService.NyatifyResult.SUCCESS -> {
                flashGreen()
                showUndoButton()
            }
            NyatifierService.NyatifyResult.NO_INPUT -> flashRed()
            NyatifierService.NyatifyResult.EMPTY -> flashRed()
            NyatifierService.NyatifyResult.OVER_THRESHOLD -> flashYellow()
            NyatifierService.NyatifyResult.DISABLED -> {}
        }
    }

    private fun repositionUndo(ballParams: WindowManager.LayoutParams) {
        val uView = undoView ?: return
        val ballPx = (currentSizeDp * density).toInt()
        val btnSize = (32 * density).toInt()
        val totalWidth = ballPx + btnSize + (4 * density).toInt()

        val undoParams = WindowManager.LayoutParams().apply {
            copyFrom(uView.layoutParams as WindowManager.LayoutParams)
            gravity = Gravity.TOP or Gravity.START
            height = btnSize
            width = btnSize
            if (ballParams.x + totalWidth > screenW) {
                x = (ballParams.x - btnSize - (4 * density).toInt()).coerceAtLeast(0)
            } else {
                x = ballParams.x + ballPx + (4 * density).toInt()
            }
            y = (ballParams.y + (ballPx - btnSize) / 2).coerceIn(0, screenH - btnSize)
        }
        windowManager.updateViewLayout(uView, undoParams)
    }
}
