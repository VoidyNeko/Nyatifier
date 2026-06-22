"""设置窗口（含自写按键捕获控件）"""

import logging
import ctypes
import ctypes.wintypes

from PyQt6.QtCore import Qt, QEvent, pyqtSignal, QAbstractNativeEventFilter
from PyQt6.QtGui import QPainter, QColor, QPen, QKeyEvent, QIntValidator
from PyQt6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QLabel,
    QPushButton, QFormLayout, QLineEdit, QCheckBox, QScrollArea, QComboBox,
)

logger = logging.getLogger("Nyatifier")

KEY_NAMES = {
    "ctrl": "Ctrl", "control": "Ctrl",
    "alt": "Alt", "shift": "Shift", "meta": "Win",
    "capslock": "Caps Lock", "numlock": "Num Lock", "scrolllock": "Scroll Lock",
    "space": "Space", "enter": "Enter", "return": "Enter",
    "backspace": "Backspace", "tab": "Tab", "escape": "Esc",
    "up": "↑", "down": "↓", "left": "←", "right": "→",
    "f1": "F1", "f2": "F2", "f3": "F3", "f4": "F4",
    "f5": "F5", "f6": "F6", "f7": "F7", "f8": "F8",
    "f9": "F9", "f10": "F10", "f11": "F11", "f12": "F12",
}


class KeyCaptureEdit(QLineEdit):
    """按键捕获输入框，支持组合键（互斥：任一捕获时自动取消其他）"""

    key_captured = pyqtSignal(str)

    # 类级互斥：所有 KeyCaptureEdit 实例共享
    _all_instances: list["KeyCaptureEdit"] = []
    _capture_active_callback = None  # (bool) -> None, 通知钩子线程

    _CAPTURE_STYLE = """
        border: 2px solid #FFB6C1;
        border-radius: 10px;
        padding: 8px 12px;
        background: transparent;
        color: #FFF5F7;
        font-size: 14px;
    """
    _CAPTURING_STYLE = """
        border: 2px solid #FF69B4;
        border-radius: 10px;
        padding: 8px 12px;
        background: rgba(255,182,193,15);
        color: #FFF5F7;
        font-size: 14px;
    """

    def __init__(self, parent=None):
        super().__init__(parent)
        self._captured_key = ""
        self._is_capturing = False
        self._pressed_modifiers = []

        self.setReadOnly(True)
        self.setContextMenuPolicy(Qt.ContextMenuPolicy.NoContextMenu)
        self.setPlaceholderText("点击设置")
        self.setFocusPolicy(Qt.FocusPolicy.StrongFocus)
        self.setFixedHeight(36)
        self.setText("点击设置")
        self._update_style_normal()

        KeyCaptureEdit._all_instances.append(self)

    def get_key(self) -> str:
        return self._captured_key

    def set_key(self, key: str):
        self._captured_key = key.lower() if key else ""
        if not self._captured_key:
            self.setText("点击设置")
        else:
            self.setText(self._format_key_name(self._captured_key))

    def _format_key_name(self, key: str) -> str:
        parts = key.split("+")
        result = []
        for part in parts:
            result.append(KEY_NAMES.get(part, part.upper()))
        return "+".join(result)

    def _update_style_normal(self):
        self.setStyleSheet(self._CAPTURE_STYLE)

    def _update_style_capturing(self):
        self.setStyleSheet(self._CAPTURING_STYLE)

    def event(self, e):
        """拦截鼠标按下（ReadOnly 模式下 mousePressEvent 可能不触发）"""
        if e.type() == QEvent.Type.MouseButtonPress:
            if e.button() == Qt.MouseButton.LeftButton:
                if not self._is_capturing:
                    self._start_capture()
                else:
                    self._end_capture()
                return True
        return super().event(e)

    def keyPressEvent(self, event: QKeyEvent):
        if not self._is_capturing:
            event.ignore()
            return

        key = event.key()

        if key == Qt.Key.Key_Escape:
            self._captured_key = ""
            self.setText("点击设置")
            self.key_captured.emit("")
            self._end_capture()
            event.accept()
            return

        if key in (Qt.Key.Key_Shift, Qt.Key.Key_Control, Qt.Key.Key_Alt, Qt.Key.Key_Meta):
            mod_name = self._modifier_key_to_name(key)
            if mod_name and mod_name not in self._pressed_modifiers:
                self._pressed_modifiers.append(mod_name)
            event.accept()
            return

        main_key = self._key_to_name(key)
        if main_key:
            if self._pressed_modifiers:
                parts = self._pressed_modifiers + [main_key]
                self._captured_key = "+".join(parts)
            else:
                self._captured_key = main_key
            self.setText(self._format_key_name(self._captured_key))
            self.key_captured.emit(self._captured_key)
            self._end_capture()
        event.accept()

    def keyReleaseEvent(self, event: QKeyEvent):
        if not self._is_capturing:
            event.ignore()
            return
        key = event.key()
        if key in (Qt.Key.Key_Shift, Qt.Key.Key_Control, Qt.Key.Key_Alt, Qt.Key.Key_Meta):
            mod_name = self._modifier_key_to_name(key)
            if mod_name in self._pressed_modifiers:
                self._pressed_modifiers.remove(mod_name)
        event.accept()

    def _start_capture(self):
        if self._is_capturing:
            return
        # 互斥：取消其他所有实例的捕获
        for inst in KeyCaptureEdit._all_instances:
            if inst is not self and inst._is_capturing:
                inst._end_capture()
        self._is_capturing = True
        self._pressed_modifiers = []
        self.setText("...")
        self._update_style_capturing()
        self.window().activateWindow()
        self.setFocus()
        # 通知钩子线程：放行按键
        if KeyCaptureEdit._capture_active_callback:
            KeyCaptureEdit._capture_active_callback(True)

    def _end_capture(self):
        if not self._is_capturing:
            return
        self._is_capturing = False
        self._pressed_modifiers = []
        self._update_style_normal()
        self.clearFocus()
        if KeyCaptureEdit._capture_active_callback:
            KeyCaptureEdit._capture_active_callback(False)

    def focusOutEvent(self, event):
        if self._is_capturing:
            self._end_capture()
        super().focusOutEvent(event)

    def _modifier_key_to_name(self, key) -> str:
        mapping = {
            Qt.Key.Key_Shift: "shift",
            Qt.Key.Key_Control: "ctrl",
            Qt.Key.Key_Alt: "alt",
            Qt.Key.Key_Meta: "meta",
        }
        return mapping.get(key, "")

    def _key_to_name(self, key) -> str:
        if Qt.Key.Key_A <= key <= Qt.Key.Key_Z:
            return chr(key).lower()
        if Qt.Key.Key_0 <= key <= Qt.Key.Key_9:
            return chr(key)
        if Qt.Key.Key_F1 <= key <= Qt.Key.Key_F12:
            return f"f{key - Qt.Key.Key_F1 + 1}"
        special_keys = {
            Qt.Key.Key_Space: "space",
            Qt.Key.Key_Return: "return",
            Qt.Key.Key_Enter: "enter",
            Qt.Key.Key_Backspace: "backspace",
            Qt.Key.Key_Tab: "tab",
            Qt.Key.Key_Escape: "escape",
            Qt.Key.Key_Up: "up",
            Qt.Key.Key_Down: "down",
            Qt.Key.Key_Left: "left",
            Qt.Key.Key_Right: "right",
        }
        return special_keys.get(key, "")


SETTINGS_STYLE = """
QWidget#SettingsWindow {
    background-color: transparent;
    border-radius: 15px;
}

QLabel {
    color: #FFF5F7;
    font-size: 14px;
}

QPushButton {
    border: 2px solid #FFB6C1;
    border-radius: 10px;
    padding: 8px 20px;
    font-weight: bold;
    font-size: 14px;
    background: transparent;
    color: #FFB6C1;
    outline: none;
}

QPushButton:focus {
    outline: none;
}

QPushButton#SaveBtn:hover {
    background-color: #FFB6C1;
    color: white;
}

QPushButton#CancelBtn:hover {
    background-color: #FFB6C1;
    color: white;
}

QCheckBox {
    color: #FFF5F7;
    font-size: 14px;
    spacing: 8px;
}

QCheckBox::indicator {
    width: 18px;
    height: 18px;
    border: 2px solid #FFB6C1;
    border-radius: 4px;
    background: transparent;
}

QCheckBox::indicator:checked {
    background-color: #FFB6C1;
}

QCheckBox::indicator:hover {
    border-color: #FF9FAA;
}

QLineEdit#ThresholdInput {
    border: 2px solid #FFB6C1;
    border-radius: 10px;
    padding: 6px 12px;
    background: transparent;
    color: #FFF5F7;
    font-size: 14px;
}

QLineEdit#ThresholdInput:focus {
    border-color: #FF69B4;
}
"""


class SettingsWindow(QWidget):
    """设置窗口 — 快捷键配置"""

    settings_saved = pyqtSignal(dict)
    hidden_signal = pyqtSignal()

    def __init__(
        self,
        show_hotkey: str = "Alt+Q",
        convert_only_hotkey: str = "Ctrl+Enter",
        undo_hotkey: str = "Alt+Z",
        toggle_hotkey: str = "Alt+Q",
        auto_start: bool = False,
        char_threshold: int = 500,
    ):
        super().__init__()
        self.setObjectName("SettingsWindow")
        self.setWindowFlags(
            Qt.WindowType.FramelessWindowHint
            | Qt.WindowType.WindowStaysOnTopHint
        )
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground)

        self.setStyleSheet(SETTINGS_STYLE)
        self._drag_pos = None
        self._show_hotkey = show_hotkey.lower()
        self._convert_only_hotkey = convert_only_hotkey.lower()
        self._undo_hotkey = undo_hotkey.lower()
        self._toggle_hotkey = toggle_hotkey.lower()
        self._auto_start = auto_start
        self._char_threshold = char_threshold
        self._init_ui()

    def set_key_capture_callback(self, callback):
        """设置捕获状态回调，通知钩子线程放行/拦截按键"""
        KeyCaptureEdit._capture_active_callback = callback

    def hide(self):
        """隐藏前确保所有捕获被释放"""
        for edit in (self._show_hotkey_edit, self._convert_only_edit, self._undo_edit, self._toggle_edit):
            if edit._is_capturing:
                edit._end_capture()
        # 释放 MINMAXINFO 注册
        try:
            hwnd = int(self.winId())
            if hwnd:
                MinMaxFilter.unregister(hwnd)
        except Exception:
            pass
        super().hide()

    def hideEvent(self, event):
        self.hidden_signal.emit()
        super().hideEvent(event)

    def closeEvent(self, event):
        self.hide()
        event.ignore()

    def _init_ui(self):
        layout = QVBoxLayout(self)
        layout.setContentsMargins(24, 24, 24, 20)
        layout.setSpacing(14)

        title = QLabel("⚙ 设置")
        title.setStyleSheet("font-size: 22px; font-weight: bold; color: #FFF5F7;")
        title.setAlignment(Qt.AlignmentFlag.AlignCenter)
        layout.addWidget(title)

        form = QFormLayout()
        form.setSpacing(12)
        form.setContentsMargins(0, 6, 0, 6)

        self._show_hotkey_edit = KeyCaptureEdit()
        self._show_hotkey_edit.set_key(self._show_hotkey)
        self._show_hotkey_edit.setToolTip("显示/隐藏悬浮窗")
        form.addRow("显示/隐藏:", self._show_hotkey_edit)

        self._convert_only_edit = KeyCaptureEdit()
        self._convert_only_edit.set_key(self._convert_only_hotkey)
        self._convert_only_edit.setToolTip("仅喵化不发送")
        form.addRow("仅喵化:", self._convert_only_edit)

        self._undo_edit = KeyCaptureEdit()
        self._undo_edit.set_key(self._undo_hotkey)
        self._undo_edit.setToolTip("撤回上一次喵化")
        form.addRow("撤回:", self._undo_edit)

        self._toggle_edit = KeyCaptureEdit()
        self._toggle_edit.set_key(self._toggle_hotkey)
        self._toggle_edit.setToolTip("启用/禁用喵化开关")
        form.addRow("开关:", self._toggle_edit)

        note = QLabel("提示：Enter 为喵化发送（固定快捷键）")
        note.setStyleSheet("color: #FFF5F7; font-size: 13px;")
        note.setWordWrap(True)
        form.addRow(note)

        layout.addLayout(form)
        layout.addSpacing(4)

        # === 开机自启动 ===
        self._auto_start_check = QCheckBox("开机自启动")
        self._auto_start_check.setChecked(self._auto_start)
        self._auto_start_check.setCursor(Qt.CursorShape.PointingHandCursor)
        layout.addWidget(self._auto_start_check)

        layout.addSpacing(4)

        # === 字符阈值 ===
        threshold_row = QHBoxLayout()
        threshold_label = QLabel("字符阈值:")
        threshold_label.setFixedWidth(80)
        threshold_row.addWidget(threshold_label)
        self._threshold_input = QLineEdit()
        self._threshold_input.setObjectName("ThresholdInput")
        self._threshold_input.setValidator(QIntValidator(0, 99999))
        self._threshold_input.setText(str(self._char_threshold))
        self._threshold_input.setPlaceholderText("0=不提醒")
        self._threshold_input.setToolTip("超过此字符数时弹窗确认，0=不提醒")
        self._threshold_input.setFixedWidth(120)
        self._threshold_input.setFixedHeight(32)
        threshold_row.addWidget(self._threshold_input)
        suffix_label = QLabel("字")
        suffix_label.setFixedWidth(20)
        threshold_row.addWidget(suffix_label)
        threshold_row.addStretch()
        layout.addLayout(threshold_row)

        layout.addStretch()

        btn_row = QHBoxLayout()
        btn_row.setSpacing(12)

        cancel_btn = QPushButton("算了喵")
        cancel_btn.setObjectName("CancelBtn")
        cancel_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        cancel_btn.setFocusPolicy(Qt.FocusPolicy.NoFocus)
        cancel_btn.clicked.connect(self.hide)

        save_btn = QPushButton("彳亍")
        save_btn.setObjectName("SaveBtn")
        save_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        save_btn.setFocusPolicy(Qt.FocusPolicy.NoFocus)
        save_btn.clicked.connect(self._on_save)

        btn_row.addStretch()
        btn_row.addWidget(cancel_btn)
        btn_row.addWidget(save_btn)
        layout.addLayout(btn_row)

    def paintEvent(self, event):
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)

        r = self.rect().adjusted(1, 1, -1, -1)

        # 10透明度填充（保证全区域可拖动，且不遮挡子控件点击）
        painter.setBrush(QColor(255, 245, 247, 10))
        painter.setPen(Qt.PenStyle.NoPen)
        painter.drawRoundedRect(r, 15, 15)

        # 边框
        painter.setBrush(Qt.BrushStyle.NoBrush)
        painter.setPen(QPen(QColor("#FFB6C1"), 2))
        painter.drawRoundedRect(r, 15, 15)

    def sync_from_settings(self, settings: dict):
        """外部调用：同步设置 dict 到控件"""
        show = settings.get("show_hotkey", "Alt+Q")
        self._show_hotkey_edit.set_key(show)
        self._show_hotkey = show.lower()
        convert = settings.get("convert_only_hotkey", "Ctrl+Enter")
        self._convert_only_edit.set_key(convert)
        self._convert_only_hotkey = convert.lower()
        undo = settings.get("undo_hotkey", "Alt+Z")
        self._undo_edit.set_key(undo)
        self._undo_hotkey = undo.lower()
        toggle = settings.get("toggle_hotkey", "Alt+Q")
        self._toggle_edit.set_key(toggle)
        self._toggle_hotkey = toggle.lower()
        self._auto_start = settings.get("auto_start", False)
        self._auto_start_check.setChecked(self._auto_start)
        threshold = settings.get("char_threshold", 500)
        self._char_threshold = threshold
        self._threshold_input.setText(str(threshold))

    def _on_save(self):
        # 先释放所有捕获，确保值正确
        for edit in (self._show_hotkey_edit, self._convert_only_edit, self._undo_edit, self._toggle_edit):
            if edit._is_capturing:
                edit._end_capture()
        show = self._show_hotkey_edit.get_key()
        convert = self._convert_only_edit.get_key()
        undo = self._undo_edit.get_key()
        toggle = self._toggle_edit.get_key()
        settings = {}
        if show:
            parts = show.lower().split("+")
            formatted = "+".join(KEY_NAMES.get(p, p.upper()) for p in parts)
            settings["show_hotkey"] = formatted
            self._show_hotkey = show
        if convert:
            parts = convert.lower().split("+")
            formatted = "+".join(KEY_NAMES.get(p, p.upper()) for p in parts)
            settings["convert_only_hotkey"] = formatted
            self._convert_only_hotkey = convert
        if undo:
            parts = undo.lower().split("+")
            formatted = "+".join(KEY_NAMES.get(p, p.upper()) for p in parts)
            settings["undo_hotkey"] = formatted
            self._undo_hotkey = undo
        if toggle:
            parts = toggle.lower().split("+")
            formatted = "+".join(KEY_NAMES.get(p, p.upper()) for p in parts)
            settings["toggle_hotkey"] = formatted
            self._toggle_hotkey = toggle
        self._auto_start = self._auto_start_check.isChecked()
        settings["auto_start"] = self._auto_start
        try:
            self._char_threshold = int(self._threshold_input.text()) if self._threshold_input.text() else 0
        except ValueError:
            self._char_threshold = 500
        settings["char_threshold"] = self._char_threshold
        if settings:
            self.settings_saved.emit(settings)
        self.hide()

    def _is_interactive_child_at(self, pos):
        """检查点击位置是否落在任意可见子控件上"""
        for ch in self.children():
            if isinstance(ch, QWidget) and ch.isVisible() and ch.geometry().contains(pos):
                return True
        return False

    def mousePressEvent(self, event):
        if event.button() == Qt.MouseButton.LeftButton:
            if self._is_interactive_child_at(event.pos()):
                super().mousePressEvent(event)
            else:
                self._drag_pos = event.globalPosition().toPoint() - self.frameGeometry().topLeft()
        elif hasattr(super(), 'mousePressEvent'):
            super().mousePressEvent(event)

    def mouseMoveEvent(self, event):
        if self._drag_pos is not None and event.buttons() & Qt.MouseButton.LeftButton:
            self.move(event.globalPosition().toPoint() - self._drag_pos)

    def mouseReleaseEvent(self, event):
        self._drag_pos = None


RULES_TEXT_HUMAN = """<style>body{color:#FFF5F7;font-size:13px;line-height:1.8;} b{color:#FFB6C1;}</style>
<b>句尾、换行和标点前，喵！</b><br>
<br>
<b>「吗」「嘛」变喵！</b><br>
&nbsp;&nbsp;「在吗」「来嘛」<br>
<br>
<b>「干嘛」人猫共识，不喵</b><br>
&nbsp;&nbsp;「NreaSCcanes，你在干嘛？」 → 「NreaSCcanes，你在干嘛<b>喵</b>？」<br>
<br>
<b>呀/吧 不喵</b><br>
&nbsp;&nbsp;「杂鱼吧，这都搞不好」 → 「杂鱼吧，这都搞不好<b>喵</b>」<br>
<br>
<b>冒号、引号前不喵</b><br>
&nbsp;&nbsp;「我的世界：地下城」 → 「我的世界：地下城<b>喵</b>」<br>
<br>
<b>外语、数字不喵</b><br>
&nbsp;&nbsp;「"何の意味ですか"是什么意思」 → 「"何の意味ですか"是什么意思<b>喵</b>」<br>
&nbsp;&nbsp;「114514」<br>
<br>
<b>喵过不再喵</b><br>
&nbsp;&nbsp;「干嘛，我已经准备好变猫娘了喵」 → 「干嘛<b>喵</b>，我已经准备好变猫娘了喵」<br>
"""

RULES_TEXT_CAT = """<style>body{color:#FFF5F7;font-size:13px;line-height:1.8;} b{color:#FFB6C1;}</style>
<b>句尾、换行和标点前，喵！</b><br>
<br>
人类用的<b>「吗」「嘛」「啊」「啦」「呢」都变喵！</b><br>
&nbsp;&nbsp;「在吗」「来嘛」「你好啊」「别生气啦」「好的呢」<br>
<br>
<b>「干嘛」人猫共识，不喵</b><br>
&nbsp;&nbsp;「NreaSCcanes，你在干嘛？」 → 「NreaSCcanes，你在干嘛<b>喵</b>？」<br>
<br>
<b>呀/吧喵起来怪怪的，不喵</b><br>
&nbsp;&nbsp;「杂鱼吧，这都搞不好」 → 「杂鱼吧，这都搞不好<b>喵</b>」<br>
<br>
<b>冒号后、引号前就说明要开始话里有话了，不喵</b><br>
&nbsp;&nbsp;「我的世界：地下城」 → 「我的世界：地下城<b>喵</b>」<br>
<br>
<b>看不懂的外语、看花眼的数字不喵</b><br>
&nbsp;&nbsp;「"何の意味ですか"是什么意思」 → 「"何の意味ですか"是什么意思<b>喵</b>」<br>
&nbsp;&nbsp;「114514」<br>
<br>
<b>喵 过 不 再 喵</b><br>
&nbsp;&nbsp;「干嘛，我已经准备好变猫娘了喵」 → 「干嘛<b>喵</b>，我已经准备好变猫娘了喵」<br>
"""

RULES_STYLE = """
QWidget#RulesWindow {
    background-color: transparent;
    border-radius: 15px;
}

QLabel#RulesTitle {
    font-size: 22px;
    font-weight: bold;
    color: #FFF5F7;
}

QLabel#RulesContent {
    color: #FFF5F7;
    font-size: 13px;
}

QScrollArea#RulesScroll {
    background-color: transparent;
    border: none;
}

QScrollBar:vertical {
    background: rgba(255,245,247,10);
    width: 6px;
    border-radius: 3px;
}

QScrollBar::handle:vertical {
    background: #FFB6C1;
    border-radius: 3px;
    min-height: 30px;
}

QScrollBar::add-line:vertical, QScrollBar::sub-line:vertical {
    height: 0px;
}

QPushButton#RulesCloseBtn {
    border: 2px solid #FFB6C1;
    border-radius: 10px;
    padding: 6px 20px;
    font-weight: bold;
    font-size: 14px;
    background: transparent;
    color: #FFB6C1;
    outline: none;
}

QPushButton#RulesCloseBtn:hover {
    background-color: #FFB6C1;
    color: white;
}

QComboBox#ModeCombo {
    border: 2px solid #FFB6C1;
    border-radius: 10px;
    padding: 6px 12px;
    padding-right: 6px;
    background: transparent;
    color: #FFB6C1;
    font-size: 13px;
    font-weight: bold;
    min-height: 30px;
}

QComboBox#ModeCombo::drop-down {
    subcontrol-position: right center;
    padding-right: 4px;
}

QComboBox#ModeCombo:hover {
    background: rgba(255,182,193,20);
}

QComboBox#ModeCombo QAbstractItemView {
    background: #2a1a2e;
    border: 1px solid #FFB6C1;
    border-radius: 8px;
    color: #FFF5F7;
    selection-background-color: #FFB6C1;
    selection-color: white;
    padding: 4px;
    outline: none;
}
"""


class RulesWindow(QWidget):
    """规则弹窗 — 显示猫语转换规则"""

    mode_changed = pyqtSignal(bool)  # True=猫模式, False=人模式

    def __init__(self):
        super().__init__()
        self.setObjectName("RulesWindow")
        self.setWindowFlags(
            Qt.WindowType.FramelessWindowHint
            | Qt.WindowType.WindowStaysOnTopHint
        )
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground)
        self.setStyleSheet(RULES_STYLE)
        self._drag_pos = None
        self._full_mode = True
        self._init_ui()

    def _init_ui(self):
        main = QVBoxLayout(self)
        main.setContentsMargins(24, 24, 24, 16)
        main.setSpacing(12)

        title = QLabel("📖 喵言喵语")
        title.setObjectName("RulesTitle")
        title.setAlignment(Qt.AlignmentFlag.AlignCenter)
        main.addWidget(title)

        # 规则内容放在滚动区
        scroll = QScrollArea()
        scroll.setObjectName("RulesScroll")
        scroll.setWidgetResizable(True)
        scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        scroll.setStyleSheet("QScrollArea { background: transparent; border: none; }")

        inner = QWidget()
        inner.setStyleSheet("background: transparent;")
        inner_layout = QVBoxLayout(inner)
        inner_layout.setContentsMargins(0, 0, 4, 0)
        inner_layout.setSpacing(0)

        self._rules_text = QLabel(RULES_TEXT_CAT)
        self._rules_text.setObjectName("RulesContent")
        self._rules_text.setWordWrap(True)
        self._rules_text.setTextFormat(Qt.TextFormat.RichText)
        inner_layout.addWidget(self._rules_text)

        scroll.setWidget(inner)
        main.addWidget(scroll, 1)

        # 模式下拉框（收起后靠底部）
        self._combo = QComboBox()
        self._combo.setObjectName("ModeCombo")
        self._combo.addItems(["我是人！ - 只变吗和嘛！", "我是猫！ - 吗嘛啊啦呢都变变变！"])
        self._combo.setCurrentIndex(1)  # 默认猫模式
        self._combo.currentIndexChanged.connect(self._on_mode_changed)
        main.addWidget(self._combo)

        close_btn = QPushButton("知道了喵")
        close_btn.setObjectName("RulesCloseBtn")
        close_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        close_btn.setFocusPolicy(Qt.FocusPolicy.NoFocus)
        close_btn.clicked.connect(self.hide)
        main.addWidget(close_btn)

    def _on_mode_changed(self, idx: int):
        self._full_mode = (idx == 1)
        self._rules_text.setText(RULES_TEXT_CAT if self._full_mode else RULES_TEXT_HUMAN)
        self.mode_changed.emit(self._full_mode)

    def is_full_mode(self) -> bool:
        return self._full_mode

    def paintEvent(self, event):
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        r = self.rect().adjusted(1, 1, -1, -1)
        painter.setBrush(QColor(255, 245, 247, 10))
        painter.setPen(Qt.PenStyle.NoPen)
        painter.drawRoundedRect(r, 15, 15)
        painter.setBrush(Qt.BrushStyle.NoBrush)
        painter.setPen(QPen(QColor("#FFB6C1"), 2))
        painter.drawRoundedRect(r, 15, 15)

    def closeEvent(self, event):
        self.hide()
        event.ignore()

    def mousePressEvent(self, event):
        if event.button() == Qt.MouseButton.LeftButton:
            child = self.childAt(event.pos())
            if child is not None and hasattr(child, 'objectName') and child.objectName() in ("RulesCloseBtn", "ModeCombo"):
                super().mousePressEvent(event)
            else:
                self._drag_pos = event.globalPosition().toPoint() - self.frameGeometry().topLeft()

    def mouseMoveEvent(self, event):
        if self._drag_pos is not None and event.buttons() & Qt.MouseButton.LeftButton:
            self.move(event.globalPosition().toPoint() - self._drag_pos)

    def mouseReleaseEvent(self, event):
        self._drag_pos = None


WM_GETMINMAXINFO = 0x0024

class _MINMAXINFO(ctypes.Structure):
    _fields_ = [
        ("ptReserved",       ctypes.wintypes.POINT),
        ("ptMaxSize",        ctypes.wintypes.POINT),
        ("ptMaxPosition",    ctypes.wintypes.POINT),
        ("ptMinTrackSize",   ctypes.wintypes.POINT),
        ("ptMaxTrackSize",   ctypes.wintypes.POINT),
    ]


def _get_dpi_scale(hwnd: int) -> float:
    """获取窗口所在显示器的 DPI 缩放比例"""
    try:
        user32 = ctypes.windll.user32
        # GetDpiForWindow (Windows 10 1607+)
        dpi = user32.GetDpiForWindow(hwnd)
        return dpi / 96.0
    except Exception:
        return 1.0


class MinMaxFilter(QAbstractNativeEventFilter):
    """拦截 WM_GETMINMAXINFO，修复 Tool 窗口 mintrack 过大

    注册时的宽高使用 Qt 逻辑像素；过滤器中通过 GetDpiForWindow 转换为
    物理像素写入 MINMAXINFO 结构体，避免 DPI 缩放导致窗口不可交互。
    """

    SIZES: dict[int, tuple[int, int]] = {}  # hwnd -> (logical_w, logical_h)

    @classmethod
    def register(cls, hwnd: int, width: int, height: int):
        cls.SIZES[hwnd] = (width, height)

    @classmethod
    def unregister(cls, hwnd: int):
        cls.SIZES.pop(hwnd, None)

    def nativeEventFilter(self, eventType, message):
        if eventType == b"windows_generic_MSG":
            msg = ctypes.cast(int(message), ctypes.POINTER(ctypes.wintypes.MSG)).contents
            if msg.message == WM_GETMINMAXINFO:
                sz = self.SIZES.get(msg.hWnd)
                if sz is not None:
                    scale = _get_dpi_scale(msg.hWnd)
                    w = int(sz[0] * scale)
                    h = int(sz[1] * scale)
                    h_max = int((sz[1] + 100) * scale)

                    info = ctypes.cast(msg.lParam, ctypes.POINTER(_MINMAXINFO))
                    info.contents.ptMinTrackSize.x = w
                    info.contents.ptMinTrackSize.y = h
                    info.contents.ptMaxTrackSize.x = w
                    info.contents.ptMaxTrackSize.y = h_max
                    info.contents.ptMaxSize.x = w
                    info.contents.ptMaxSize.y = h_max
                    return False, 0
                else:
                    logging.getLogger("Nyatifier").debug(f"MINMAXFIX: UNKNOWN hWnd={msg.hWnd}")
        return False, 0
