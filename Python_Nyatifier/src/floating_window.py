"""悬浮窗 — 可爱风无边框圆角小窗口（带猫耳）"""

import random

from PyQt6.QtCore import Qt, QPoint, QPointF, QRectF, QTimer, pyqtSignal
from PyQt6.QtGui import QMouseEvent, QPainter, QColor, QPen, QPainterPath
from PyQt6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QLabel, QPushButton,
)

WINDOW_STYLE = """
QLabel#TitleLabel {
    font-size: 15px;
    font-weight: bold;
}

QLabel#HintLabel {
    color: #FFF5F7;
    font-size: 12px;
    padding: 2px 0px;
}

QPushButton#SettingsBtn, QPushButton#CloseBtn, QPushButton#RulesBtn {
    background-color: transparent;
    border: none;
    font-size: 20px;
    padding: 0px;
    border-radius: 10px;
    color: #FFB6C1;
    outline: none;
}

QPushButton#SettingsBtn:hover, QPushButton#CloseBtn:hover, QPushButton#RulesBtn:hover {
    background-color: rgba(255, 182, 193, 50);
}

QPushButton#TitleCloseBtn {
    background-color: transparent;
    border: none;
    font-size: 14px;
    padding: 0px 4px;
    color: #FFB6C1;
    outline: none;
}

QPushButton#TitleCloseBtn:hover {
    color: #FF69B4;
}
"""


class FloatingWindow(QWidget):
    """可爱悬浮窗"""

    close_clicked = pyqtSignal()
    enabled_toggled = pyqtSignal()

    def __init__(
        self,
        show_hotkey: str = "Alt+Q",
        convert_only_hotkey: str = "Ctrl+Enter",
        undo_hotkey: str = "Alt+Z",
        toggle_hotkey: str = "Alt+Q",
        kamojis: dict | None = None,
        enabled: bool = True,
    ):
        super().__init__()
        self._show_hotkey = show_hotkey
        self._convert_only_hotkey = convert_only_hotkey
        self._undo_hotkey = undo_hotkey
        self._toggle_hotkey = toggle_hotkey
        self._kamojis = kamojis or {"enabled": ["(=^・ω・^=)"], "disabled": [",,Ծ‸Ծ,,"]}
        self._enabled = enabled
        self._drag_pos: QPoint | None = None
        self._drag_start: QPoint | None = None
        self._drag_kaomoji = False  # 颜文字区点击标记，用于松开时判断 toggle 还是拖拽
        self._normal_color = "#22cc66" if enabled else "#ee4444"
        self._normal_kamoji = ""
        self._exceeded_timer = QTimer(self)
        self._exceeded_timer.setSingleShot(True)
        self._exceeded_timer.timeout.connect(self._restore_kaomoji)
        self._init_ui()
        self.set_enabled(self._enabled)

    def _init_ui(self):
        self.setObjectName("FloatingWindow")
        self.setWindowFlags(
            Qt.WindowType.FramelessWindowHint
            | Qt.WindowType.WindowStaysOnTopHint
            | Qt.WindowType.Tool
        )
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground)
        self.setFixedSize(280, 248)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(18, 60, 18, 14)
        layout.setSpacing(2)

        # === 标题行（居中，右侧 ✕ 绝对定位确保标题完全居中） ===
        title_row = QHBoxLayout()
        title_row.setContentsMargins(0, 0, 0, 0)
        title_row.setSpacing(0)

        title_text = QLabel(
            '<span style="color:#FFB6C1; font-size:18px; font-weight:bold;">喵</span>'
            '<span style="color:#FFF5F7; font-size:18px; font-weight:bold;">&emsp;笔&emsp;生&emsp;花</span>'
        )
        title_text.setObjectName("TitleLabel")
        title_text.setAlignment(Qt.AlignmentFlag.AlignCenter)
        title_text.setAttribute(Qt.WidgetAttribute.WA_TransparentForMouseEvents)
        title_row.addStretch()
        title_row.addWidget(title_text)
        title_row.addStretch()

        layout.addLayout(title_row)

        # ✕ 按钮（绝对定位，避免影响标题居中）
        self._title_close_btn = QPushButton("✕")
        self._title_close_btn.setObjectName("TitleCloseBtn")
        self._title_close_btn.setFixedSize(22, 22)
        self._title_close_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        self._title_close_btn.setToolTip("退出")
        self._title_close_btn.setFocusPolicy(Qt.FocusPolicy.NoFocus)
        self._title_close_btn.clicked.connect(self.close_clicked.emit)
        self._title_close_btn.setParent(self)

        layout.addSpacing(2)

        # === 颜文字区（点击切换开关） ===
        self._kamoji_label = QLabel("(=^・ω・^=)")
        self._kamoji_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self._kamoji_label.setFixedHeight(36)
        layout.addWidget(self._kamoji_label)

        layout.addSpacing(2)

        # === 提示文字 ===
        hint = QLabel(
            f"Enter → 喵喵叫！\n"
            f"{self._convert_only_hotkey} → 先喵一眼！\n"
            f"{self._show_hotkey} → 跟猫猫捉迷藏！\n"
            f"{self._toggle_hotkey} → 川剧变脸喵！\n"
            f"{self._undo_hotkey} → 背叛猫猫Σ(ﾟдﾟ)"
        )
        hint.setObjectName("HintLabel")
        hint.setAlignment(Qt.AlignmentFlag.AlignCenter)
        hint.setAttribute(Qt.WidgetAttribute.WA_TransparentForMouseEvents)
        layout.addWidget(hint)
        self._hint_label = hint

        # ⚙ 和 📖 按钮（绝对定位，放进猫耳中间）
        self._settings_btn = QPushButton("⚙")
        self._settings_btn.setObjectName("SettingsBtn")
        self._settings_btn.setFixedSize(32, 32)
        self._settings_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        self._settings_btn.setToolTip("设置")
        self._settings_btn.setFocusPolicy(Qt.FocusPolicy.NoFocus)
        self._settings_btn.setParent(self)

        self._rules_btn = QPushButton("📖")
        self._rules_btn.setObjectName("RulesBtn")
        self._rules_btn.setFixedSize(32, 32)
        self._rules_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        self._rules_btn.setToolTip("喵语规则")
        self._rules_btn.setFocusPolicy(Qt.FocusPolicy.NoFocus)
        self._rules_btn.setParent(self)

        self.setStyleSheet(WINDOW_STYLE)

    def resizeEvent(self, event):
        super().resizeEvent(event)
        self._update_ear_buttons()
        # ✕ 按钮靠右上角
        self._title_close_btn.move(self.width() - 36, 63)

    def _update_ear_buttons(self):
        w = self.width()
        # 猫耳内按钮定位
        ear_left_x = int(w * 0.25)
        ear_right_x = int(w * 0.75)
        ear_mid_y = 24
        bs = 32
        self._settings_btn.move(ear_left_x - bs // 2, ear_mid_y)
        self._rules_btn.move(ear_right_x - bs // 2, ear_mid_y)

    # ====== 自绘猫耳（外凸曲线 60px高 70px宽 25%/75%） + 圆角边框 ======

    def paintEvent(self, event):
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)

        w, h = self.width(), self.height()
        ear_h = 58
        radius = 18
        left, top = 12, ear_h
        right, bottom = w - 12, h - 12

        # 身体填充（1透明度 #FFB6C1）
        painter.setBrush(QColor(255, 182, 193, 10))
        painter.setPen(Qt.PenStyle.NoPen)
        painter.drawRoundedRect(QRectF(left, top, right - left, bottom - top), radius, radius)

        pink = QColor("#FFB6C1")
        ear_fill = QColor(255, 182, 193, 10)

        # --- 猫耳参数 ---
        ear_base_half = 30  # 猫耳总宽60px
        ear_peak_y = top - 45
        ear_left_peak_x = int(w * 0.25)
        ear_right_peak_x = int(w * 0.75)

        left_base_left = ear_left_peak_x - ear_base_half
        left_base_right = ear_left_peak_x + ear_base_half
        right_base_left = ear_right_peak_x - ear_base_half
        right_base_right = ear_right_peak_x + ear_base_half

        # --- 左耳：填充（闭合） + 边框（两条开放曲线，无底边）---
        lm = (left_base_left + ear_left_peak_x) / 2
        rm = (ear_left_peak_x + left_base_right) / 2
        my = (top + ear_peak_y) / 2

        # 填充路径（闭合）
        left_fill = QPainterPath()
        left_fill.moveTo(left_base_left, top)
        left_fill.quadTo(QPointF(lm - 7, my), QPointF(ear_left_peak_x, ear_peak_y))
        left_fill.quadTo(QPointF(rm + 7, my), QPointF(left_base_right, top))
        left_fill.closeSubpath()
        painter.setBrush(ear_fill)
        painter.setPen(Qt.PenStyle.NoPen)
        painter.drawPath(left_fill)

        # 描边路径（两条开放曲线，无底边）
        left_stroke = QPainterPath()
        left_stroke.moveTo(left_base_left, top)
        left_stroke.quadTo(QPointF(lm - 7, my), QPointF(ear_left_peak_x, ear_peak_y))
        left_stroke.quadTo(QPointF(rm + 7, my), QPointF(left_base_right, top))
        painter.setBrush(Qt.BrushStyle.NoBrush)
        painter.setPen(QPen(pink, 2))
        painter.drawPath(left_stroke)

        # --- 右耳 ---
        lm2 = (right_base_left + ear_right_peak_x) / 2
        rm2 = (ear_right_peak_x + right_base_right) / 2

        right_fill = QPainterPath()
        right_fill.moveTo(right_base_left, top)
        right_fill.quadTo(QPointF(lm2 - 7, my), QPointF(ear_right_peak_x, ear_peak_y))
        right_fill.quadTo(QPointF(rm2 + 7, my), QPointF(right_base_right, top))
        right_fill.closeSubpath()
        painter.setBrush(ear_fill)
        painter.setPen(Qt.PenStyle.NoPen)
        painter.drawPath(right_fill)

        right_stroke = QPainterPath()
        right_stroke.moveTo(right_base_left, top)
        right_stroke.quadTo(QPointF(lm2 - 7, my), QPointF(ear_right_peak_x, ear_peak_y))
        right_stroke.quadTo(QPointF(rm2 + 7, my), QPointF(right_base_right, top))
        painter.setBrush(Qt.BrushStyle.NoBrush)
        painter.setPen(QPen(pink, 2))
        painter.drawPath(right_stroke)

        # --- 身体边框（顶部缺口对应猫耳间隙）---
        painter.setBrush(Qt.BrushStyle.NoBrush)
        painter.setPen(QPen(pink, 2))
        body_path = QPainterPath()
        body_path.moveTo(left_base_left, top)
        body_path.lineTo(left + radius, top)
        body_path.arcTo(QRectF(left, top, radius * 2, radius * 2), 90, 90)
        body_path.lineTo(left, bottom - radius)
        body_path.arcTo(QRectF(left, bottom - radius * 2, radius * 2, radius * 2), 180, 90)
        body_path.lineTo(right - radius, bottom)
        body_path.arcTo(QRectF(right - radius * 2, bottom - radius * 2, radius * 2, radius * 2), 270, 90)
        body_path.lineTo(right, top + radius)
        body_path.arcTo(QRectF(right - radius * 2, top, radius * 2, radius * 2), 0, 90)
        body_path.lineTo(right_base_right, top)
        body_path.moveTo(right_base_left, top)
        body_path.lineTo(left_base_right, top)
        painter.drawPath(body_path)

    # ====== 公共接口 ======

    def set_enabled(self, enabled: bool):
        self._enabled = enabled
        key = "enabled" if enabled else "disabled"
        items = self._kamojis.get(key, [])
        if items:
            text = random.choice(items)
            self._kamoji_label.setText(text)
            self._saved_kamoji = text
        color = "#22cc66" if enabled else "#ee4444"
        self._normal_color = color
        self._kamoji_label.setStyleSheet(f"color: {color}; font-size: 26px;")

    def show_exceeded_kaomoji(self):
        """超阈值：显示黄色 exceeded 颜文字，3秒后恢复"""
        self._exceeded_timer.stop()
        self._normal_kamoji = self._kamoji_label.text()
        items = self._kamojis.get("exceeded", [])
        if items:
            self._kamoji_label.setText(random.choice(items))
        self._kamoji_label.setStyleSheet("color: #FFD700; font-size: 26px;")
        self._exceeded_timer.start(3000)

    def _restore_kaomoji(self):
        """恢复颜文字到正常状态"""
        if self._normal_kamoji:
            self._kamoji_label.setText(self._normal_kamoji)
        self._kamoji_label.setStyleSheet(f"color: {self._normal_color}; font-size: 26px;")

    def set_hotkeys(self, show_hotkey: str, convert_only_hotkey: str, undo_hotkey: str = "Alt+Z", toggle_hotkey: str = "Alt+Q"):
        self._show_hotkey = show_hotkey
        self._convert_only_hotkey = convert_only_hotkey
        self._undo_hotkey = undo_hotkey
        self._toggle_hotkey = toggle_hotkey
        self._hint_label.setText(
            f"Enter → 喵喵叫！\n"
            f"{self._convert_only_hotkey} → 先喵一眼！\n"
            f"{self._show_hotkey} → 跟猫猫捉迷藏！\n"
            f"{self._toggle_hotkey} → 川剧变喵！\n"
            f"{self._undo_hotkey} → 背叛猫猫Σ(ﾟдﾟ)"
        )

    @property
    def settings_button(self):
        return self._settings_btn

    @property
    def rules_button(self):
        return self._rules_btn

    # ====== 拖拽 + 点击颜文字切换 ======

    def _child_at(self, pos: QPoint) -> QWidget | None:
        return self.childAt(pos)

    def mousePressEvent(self, event: QMouseEvent):
        if event.button() == Qt.MouseButton.LeftButton:
            child = self.childAt(event.pos())
            # 按钮需要独立响应
            if child is self._settings_btn or child is self._rules_btn or child is self._title_close_btn:
                self._drag_pos = None
                self._drag_kaomoji = False
                super().mousePressEvent(event)
                return
            # 颜文字区：记录拖拽偏移，同时标记可能点击 toggle
            self._drag_pos = event.globalPosition().toPoint() - self.frameGeometry().topLeft()
            self._drag_start = event.globalPosition().toPoint()
            self._drag_kaomoji = (child is self._kamoji_label)
            event.accept()
        else:
            super().mousePressEvent(event)

    def mouseMoveEvent(self, event: QMouseEvent):
        if self._drag_pos is not None and event.buttons() & Qt.MouseButton.LeftButton:
            self.move(event.globalPosition().toPoint() - self._drag_pos)
        else:
            super().mouseMoveEvent(event)

    def mouseReleaseEvent(self, event: QMouseEvent):
        if event.button() == Qt.MouseButton.LeftButton and self._drag_start is not None:
            end = event.globalPosition().toPoint()
            dist = (end - self._drag_start).manhattanLength()
            # 颜文字区短距离点击 = 切换开关
            if self._drag_kaomoji and dist < 5:
                self.enabled_toggled.emit()
        self._drag_pos = None
        self._drag_start = None
        self._drag_kaomoji = False
        super().mouseReleaseEvent(event)
