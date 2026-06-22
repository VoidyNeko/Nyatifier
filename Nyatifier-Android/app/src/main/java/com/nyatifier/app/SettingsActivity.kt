package com.nyatifier.app

import android.os.Bundle
import android.text.Editable
import android.text.TextWatcher
import android.view.View
import android.view.ViewGroup
import android.widget.*
import androidx.appcompat.app.AppCompatActivity

class SettingsActivity : AppCompatActivity() {

    private var catMode = true
    private var enableMode = true
    private var charThreshold = 500
    private var overlaySizeDp = 64

    private val dependentViews = mutableListOf<View>()

    override fun onCreate(savedInstanceState: Bundle?) {
        super.onCreate(savedInstanceState)
        setContentView(R.layout.activity_settings)

        val prefs = getSharedPreferences(NyatifierService.PREF_NAME, MODE_PRIVATE)
        catMode = prefs.getBoolean(NyatifierService.KEY_CAT_MODE, true)
        enableMode = prefs.getBoolean(NyatifierService.KEY_ENABLED, true)
        charThreshold = prefs.getInt(NyatifierService.KEY_CHAR_THRESHOLD, 500)
        overlaySizeDp = prefs.getInt(NyatifierService.KEY_OVERLAY_SIZE, 64)

        // ====== 启用开关 ======
        val switchEnabled = findViewById<androidx.appcompat.widget.SwitchCompat>(R.id.switch_enabled)
        switchEnabled.isChecked = enableMode
        switchEnabled.setOnCheckedChangeListener { _, isChecked ->
            enableMode = isChecked
            prefs.edit().putBoolean(NyatifierService.KEY_ENABLED, enableMode).apply()
            NyatifierService.instance?.toggleEnabled()
            refreshGrey()
        }

        // ====== 模式下拉 ======
        val spinnerMode = findViewById<Spinner>(R.id.spinner_mode)
        val modes = arrayOf(
            "我是猫！ - 吗嘛啊啦呢都变变变！",
            "我是人！ - 只变吗和嘛！"
        )
        val adapter = object : ArrayAdapter<String>(this, android.R.layout.simple_spinner_item, modes) {
            override fun getDropDownView(position: Int, convertView: View?, parent: ViewGroup): View {
                val view = super.getDropDownView(position, convertView, parent)
                (view as TextView).setTextColor(0xFFFFF5F7.toInt())
                return view
            }
            override fun getView(position: Int, convertView: View?, parent: ViewGroup): View {
                val view = super.getView(position, convertView, parent)
                (view as TextView).setTextColor(0xFFFFF5F7.toInt())
                return view
            }
        }
        spinnerMode.adapter = adapter
        spinnerMode.setSelection(if (catMode) 0 else 1)
        spinnerMode.onItemSelectedListener = object : AdapterView.OnItemSelectedListener {
            override fun onItemSelected(parent: AdapterView<*>?, view: View?, position: Int, id: Long) {
                catMode = position == 0
                prefs.edit().putBoolean(NyatifierService.KEY_CAT_MODE, catMode).apply()
                NyatifierService.instance?.refreshSettings()
            }
            override fun onNothingSelected(parent: AdapterView<*>?) {}
        }

        // ====== 字符阈值 ======
        val editThreshold = findViewById<EditText>(R.id.edit_char_threshold)
        editThreshold.setText(charThreshold.toString())
        editThreshold.addTextChangedListener(object : TextWatcher {
            override fun afterTextChanged(s: Editable?) {
                val num = s?.toString()?.toIntOrNull() ?: return
                charThreshold = num
                prefs.edit().putInt(NyatifierService.KEY_CHAR_THRESHOLD, charThreshold).apply()
                NyatifierService.instance?.refreshSettings()
            }
            override fun beforeTextChanged(s: CharSequence?, start: Int, count: Int, after: Int) {}
            override fun onTextChanged(s: CharSequence?, start: Int, before: Int, count: Int) {}
        })

        // ====== 悬浮球大小 ======
        val seekSize = findViewById<SeekBar>(R.id.seek_overlay_size)
        val tvSize = findViewById<TextView>(R.id.tv_overlay_size)
        val sizeDpValues = intArrayOf(40, 52, 64, 76, 88, 100)
        val currentIdx = sizeDpValues.indexOfFirst { it >= overlaySizeDp }.coerceAtLeast(0)
        seekSize.progress = currentIdx
        tvSize.text = "${sizeDpValues[currentIdx]}dp"
        seekSize.setOnSeekBarChangeListener(object : SeekBar.OnSeekBarChangeListener {
            override fun onProgressChanged(seekBar: SeekBar?, progress: Int, fromUser: Boolean) {
                tvSize.text = "${sizeDpValues[progress]}dp"
            }
            override fun onStartTrackingTouch(seekBar: SeekBar?) {}
            override fun onStopTrackingTouch(seekBar: SeekBar?) {
                val dp = sizeDpValues[seekBar?.progress ?: 2]
                overlaySizeDp = dp
                prefs.edit().putInt(NyatifierService.KEY_OVERLAY_SIZE, overlaySizeDp).apply()
                NyatifierService.instance?.updateOverlaySize(overlaySizeDp)
            }
        })

        // ====== 收集依赖 enableMode 的控件 ======
        dependentViews.add(findViewById(R.id.label_mode))
        dependentViews.add(spinnerMode)
        dependentViews.add(findViewById(R.id.label_threshold))
        dependentViews.add(editThreshold)
        dependentViews.add(findViewById(R.id.label_size))
        dependentViews.add(seekSize)
        dependentViews.add(tvSize)
        dependentViews.add(findViewById(R.id.label_test))
        dependentViews.add(findViewById(R.id.edit_test_text))

        // ====== 抛弃猫猫 ======
        findViewById<Button>(R.id.btn_abandon_cat).setOnClickListener {
            NyatifierService.instance?.disableSelf()
            finish()
        }

        refreshGrey()
    }

    private fun refreshGrey() {
        val alpha = if (enableMode) 1.0f else 0.4f
        for (v in dependentViews) {
            v.isEnabled = enableMode
            v.alpha = alpha
        }
    }
}
