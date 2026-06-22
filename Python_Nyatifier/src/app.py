"""主应用程序 — 纯钩子拦截、剪贴板操作、系统托盘"""

import ctypes
import ctypes.wintypes
import threading
import time
import json
import os
import queue
import logging
import winreg
import sys

from PyQt6.QtCore import QTimer, QObject
from PyQt6.QtGui import QAction, QPixmap, QPainter, QColor, QIcon
from PyQt6.QtWidgets import QApplication, QSystemTrayIcon, QMenu

from .cat_converter import convert_to_cat_speak
from .floating_window import FloatingWindow
from .settings_window import SettingsWindow, RulesWindow, MinMaxFilter

logger = logging.getLogger("Nyatifier")
logging.basicConfig(
    level=logging.DEBUG,
    format="[%(asctime)s] %(levelname)s %(name)s: %(message)s",
    datefmt="%H:%M:%S",
)

# Win32 API 常量
WH_KEYBOARD_LL = 13
WM_KEYDOWN = 0x0100
WM_KEYUP = 0x0101
WM_SYSKEYDOWN = 0x0104
WM_SYSKEYUP = 0x0105
LLKHF_INJECTED = 0x10  # KBDLLHOOKSTRUCT.flags 位：事件由 SendInput/keybd_event 注入
PM_NOREMOVE = 0x0000
PM_REMOVE = 0x0001

# 虚拟键码
VK_RETURN = 0x0D
VK_LCONTROL = 0xA2
VK_RCONTROL = 0xA3
VK_CONTROL = 0x11  # Ctrl (generic)
VK_LMENU = 0xA4     # Left Alt
VK_RMENU = 0xA5     # Right Alt
VK_MENU = 0x12      # Alt (generic)
VK_LSHIFT = 0xA0
VK_RSHIFT = 0xA1
VK_Q = 0x51
VK_Z = 0x5A

# 字符串热键 -> VK码映射
HOTKEY_TO_VK: dict[str, int] = {
    "a": 0x41, "b": 0x42, "c": 0x43, "d": 0x44, "e": 0x45,
    "f": 0x46, "g": 0x47, "h": 0x48, "i": 0x49, "j": 0x4A,
    "k": 0x4B, "l": 0x4C, "m": 0x4D, "n": 0x4E, "o": 0x4F,
    "p": 0x50, "q": 0x51, "r": 0x52, "s": 0x53, "t": 0x54,
    "u": 0x55, "v": 0x56, "w": 0x57, "x": 0x58, "y": 0x59,
    "z": 0x5A,
    "0": 0x30, "1": 0x31, "2": 0x32, "3": 0x33, "4": 0x34,
    "5": 0x35, "6": 0x36, "7": 0x37, "8": 0x38, "9": 0x39,
    "f1": 0x70, "f2": 0x71, "f3": 0x72, "f4": 0x73,
    "f5": 0x74, "f6": 0x75, "f7": 0x76, "f8": 0x77,
    "f9": 0x78, "f10": 0x79, "f11": 0x7A, "f12": 0x7B,
    "space": 0x20, "enter": VK_RETURN, "return": VK_RETURN,
    "tab": 0x09, "escape": 0x1B, "esc": 0x1B,
    "backspace": 0x08, "up": 0x26, "down": 0x28,
    "left": 0x25, "right": 0x27,
}
MOD_NAME = {"ctrl", "alt", "shift", "meta"}


def _parse_hotkey(hotkey_str: str) -> tuple[int, bool, bool, bool] | None:
    """解析热键字符串 -> (vk_code, need_ctrl, need_alt, need_shift)，无法解析返回None"""
    if not hotkey_str:
        return None
    parts = [p.strip().lower() for p in hotkey_str.split("+")]
    mods = [p for p in parts if p in MOD_NAME]
    keys = [p for p in parts if p not in MOD_NAME]
    if len(keys) != 1:
        return None
    key = keys[0]
    vk = HOTKEY_TO_VK.get(key)
    if vk is None:
        return None
    return (vk, "ctrl" in mods, "alt" in mods, "shift" in mods)


# 修饰键掩码（用于 GetAsyncKeyState 检测同时按下）
MOD_SHIFT_MASK = 0x8000

def _get_data_dir() -> str:
    """返回数据文件所在目录，兼容 PyInstaller 打包后的路径"""
    if getattr(sys, 'frozen', False):
        return getattr(sys, '_MEIPASS', os.path.dirname(sys.executable))
    return os.path.dirname(os.path.dirname(__file__))

SETTINGS_FILE = os.path.join(_get_data_dir(), "nyatifier_settings.json")
KAMOJIS_FILE = os.path.join(_get_data_dir(), "kamojis.json")

user32 = ctypes.windll.user32
kernel32 = ctypes.windll.kernel32

user32.CallNextHookEx.argtypes = [
    ctypes.wintypes.HHOOK, ctypes.c_int,
    ctypes.wintypes.WPARAM, ctypes.wintypes.LPARAM,
]
user32.CallNextHookEx.restype = ctypes.wintypes.LPARAM

user32.GetAsyncKeyState.argtypes = [ctypes.c_int]
user32.GetAsyncKeyState.restype = ctypes.c_short


# ============================================================
# 加载颜文字
# ============================================================
def _load_kamojis() -> dict:
    try:
        if os.path.exists(KAMOJIS_FILE):
            with open(KAMOJIS_FILE, "r", encoding="utf-8") as f:
                return json.load(f)
    except Exception as e:
        logger.warning(f"加载颜文字失败: {e}")
    return {"enabled": ["(^ω^)"], "disabled": [",,◔ д ◔,,"]}



# ============================================================
# 键盘钩子回调
# ============================================================
_hook_instance_ref = None
_hook_lock = threading.Lock()
_pressed_keys: set[int] = set()  # 已按下的 VK 码，用于防止长按连续触发


def _get_hook_instance():
    with _hook_lock:
        return _hook_instance_ref


def _is_key_down(vk: int) -> bool:
    return bool(user32.GetAsyncKeyState(vk) & MOD_SHIFT_MASK)


def _is_ctrl_down() -> bool:
    return (
        _is_key_down(VK_LCONTROL)
        or _is_key_down(VK_RCONTROL)
        or _is_key_down(VK_CONTROL)
    )


def _is_alt_down() -> bool:
    return (
        _is_key_down(VK_LMENU)
        or _is_key_down(VK_RMENU)
        or _is_key_down(VK_MENU)
    )


def _is_shift_down() -> bool:
    return _is_key_down(VK_LSHIFT) or _is_key_down(VK_RSHIFT)


@ctypes.WINFUNCTYPE(
    ctypes.wintypes.LPARAM,
    ctypes.c_int, ctypes.wintypes.WPARAM, ctypes.wintypes.LPARAM,
)
def _low_level_keyboard_proc(nCode, wParam, lParam):
    global _pressed_keys
    try:
        if nCode < 0:
            return user32.CallNextHookEx(None, nCode, wParam, lParam)

        # 读取虚拟键码（lParam 指向 KBDLLHOOKSTRUCT，首个 DWORD 即 vkCode）
        vk_code = ctypes.cast(
            lParam, ctypes.POINTER(ctypes.c_ulong)
        ).contents.value

        # 读取 flags（KBDLLHOOKSTRUCT 的第三个 DWORD，offset 8）
        flags = ctypes.cast(lParam, ctypes.POINTER(ctypes.c_ulong))[2]

        # 注入的模拟按键（keybd_event / SendInput）：直接放行，不做热键匹配
        if flags & LLKHF_INJECTED:
            return user32.CallNextHookEx(None, nCode, wParam, lParam)

        # 弹起：从 pressed 集合中移除，同时检查推迟的撤回
        if wParam in (WM_KEYUP, WM_SYSKEYUP):
            _pressed_keys.discard(vk_code)
            # Alt 松开 → 触发推迟的撤回合仅喵化
            if vk_code in (VK_MENU, VK_LMENU, VK_RMENU):
                instance = _get_hook_instance()
                if instance is not None:
                    if instance._undo_pending:
                        instance._set_undo_pending(False)
                        instance._request_undo()
                        logger.debug("[HOOK] Alt 松开，触发推迟的撤回")
                    if instance._convert_pending:
                        instance._set_convert_pending(False)
                        instance._request_convert_only()
                        logger.debug("[HOOK] Alt 松开，触发推迟的仅喵化")
            return user32.CallNextHookEx(None, nCode, wParam, lParam)

        if wParam not in (WM_KEYDOWN, WM_SYSKEYDOWN):
            return user32.CallNextHookEx(None, nCode, wParam, lParam)

        # 长按重复：已在 pressed 集合中 → 跳过，不做任何热键匹配
        if vk_code in _pressed_keys:
            return user32.CallNextHookEx(None, nCode, wParam, lParam)

        _pressed_keys.add(vk_code)

        instance = _get_hook_instance()
        if instance is None:
            return user32.CallNextHookEx(None, nCode, wParam, lParam)

        ctrl = _is_ctrl_down()
        alt = _is_alt_down()
        shift = _is_shift_down()

        # =====================
        # KeyCaptureEdit 正在捕获组合键：放行所有按键，不做处理
        # =====================
        if instance._capturing_keys:
            return user32.CallNextHookEx(None, nCode, wParam, lParam)

        # =====================
        # 启用/禁用开关（仅悬浮窗可见时生效）
        # =====================
        enable_toggle_info = instance._enable_toggle_info
        if enable_toggle_info and instance._floating_visible and vk_code == enable_toggle_info[0] and ctrl == enable_toggle_info[1] and alt == enable_toggle_info[2] and shift == enable_toggle_info[3]:
            instance._request_enable_toggle()
            return 1

        # =====================
        # 动态热键匹配
        # =====================
        # 显示/隐藏
        toggle_info = instance._toggle_info
        if toggle_info and vk_code == toggle_info[0] and ctrl == toggle_info[1] and alt == toggle_info[2] and shift == toggle_info[3]:
            instance._request_toggle()
            return 1

        # 撤回（Alt+Z）：推迟到 Alt 松开后再执行，避免物理 Alt 干扰 Ctrl+A
        undo_info = instance._undo_info
        if undo_info and vk_code == undo_info[0] and ctrl == undo_info[1] and alt == undo_info[2] and shift == undo_info[3]:
            instance._set_undo_pending(True)
            logger.debug("[HOOK] 撤回推迟等待 Alt 松开")
            return 1

        # 以下仅悬浮窗可见 + 启用 + 非动作中 + 设置窗口未打开时生效
        if (
            not instance._floating_visible
            or not instance._enabled
            or instance._performing
            or instance._settings_visible
        ):
            return user32.CallNextHookEx(None, nCode, wParam, lParam)

        # 悬浮窗内直接按 Enter → 钩子不处理（让Qt处理）
        # 但钩子无法判断焦点，统一拦截，由app决定

        # 仅喵化（Alt+Enter）：推迟到 Alt 松开后执行，避免物理 Alt 干扰 Ctrl+A/Ctrl+X/Ctrl+V
        convert_info = instance._convert_info
        if convert_info and vk_code == convert_info[0] and ctrl == convert_info[1] and alt == convert_info[2] and shift == convert_info[3]:
            instance._set_convert_pending(True)
            logger.debug("[HOOK] 仅喵化推迟等待 Alt 松开")
            return 1

        # Enter（无修饰键）: 喵化并发送
        if vk_code == VK_RETURN and not ctrl and not alt and not shift:
            instance._request_full_action()
            return 1

    except Exception as e:
        logger.error(f"Hook error: {e}")

    return user32.CallNextHookEx(None, nCode, wParam, lParam)


# ============================================================
# KeyboardHook
# ============================================================


class _KeyboardHook:
    def __init__(self, app):
        self._app = app
        self._hook_id = None
        self._running = False

    @property
    def _floating_visible(self):
        return self._app._floating_visible

    @property
    def _enabled(self):
        return self._app._enabled

    @property
    def _performing(self):
        return self._app._performing_action

    @property
    def _settings_visible(self):
        return self._app._settings_visible_flag

    @property
    def _capturing_keys(self):
        return self._app._key_capture_active

    @property
    def _toggle_info(self):
        hotkey = self._app._settings.get("show_hotkey", "Alt+Q")
        return _parse_hotkey(hotkey)

    @property
    def _convert_info(self):
        hotkey = self._app._settings.get("convert_only_hotkey", "Ctrl+Enter")
        return _parse_hotkey(hotkey)

    @property
    def _undo_info(self):
        hotkey = self._app._settings.get("undo_hotkey", "Alt+Z")
        return _parse_hotkey(hotkey)

    @property
    def _enable_toggle_info(self):
        hotkey = self._app._settings.get("toggle_hotkey", "Alt+Q")
        return _parse_hotkey(hotkey)

    @property
    def _undo_pending(self):
        return self._app._undo_pending

    def _set_undo_pending(self, value: bool):
        self._app._undo_pending = value

    @property
    def _convert_pending(self):
        return self._app._convert_pending

    def _set_convert_pending(self, value: bool):
        self._app._convert_pending = value

    def _request_toggle(self):
        self._app._queue_request("toggle")

    def _request_enable_toggle(self):
        self._app._queue_request("enable_toggle")

    def _request_full_action(self):
        self._app._queue_request("full")

    def _request_convert_only(self):
        self._app._queue_request("convert_only")

    def _request_undo(self):
        self._app._queue_request("undo")

    def start(self):
        global _hook_instance_ref
        with _hook_lock:
            _hook_instance_ref = self

        self._running = True
        logger.info("键盘钩子线程启动")

        self._hook_id = user32.SetWindowsHookExW(
            WH_KEYBOARD_LL, _low_level_keyboard_proc, None, 0
        )
        if not self._hook_id:
            err = kernel32.GetLastError()
            logger.error(f"SetWindowsHookExW 失败，错误码: {err}")
            self._running = False
            return
        logger.info(f"键盘钩子注册成功，hook_id={self._hook_id}")

        msg = ctypes.wintypes.MSG()
        user32.PeekMessageW(ctypes.byref(msg), None, 0, 0, PM_NOREMOVE)

        while self._running:
            ret = user32.GetMessageW(ctypes.byref(msg), None, 0, 0)
            if ret in (0, -1):
                if ret == -1:
                    time.sleep(0.01)
                    continue
                else:
                    break

        logger.info("键盘钩子线程退出")

    def _detach_hook(self):
        if self._hook_id:
            user32.UnhookWindowsHookEx(self._hook_id)
            self._hook_id = None
            logger.info("键盘钩子已卸载")

    def stop(self):
        global _hook_instance_ref
        self._running = False
        self._detach_hook()
        with _hook_lock:
            _hook_instance_ref = None
        logger.info("键盘钩子已停止")


# ============================================================
# NyatifierApp
# ============================================================


class NyatifierApp(QObject):

    def __init__(self, app: QApplication):
        super().__init__()
        logger.info("NyatifierApp 初始化开始")
        self._app = app
        self._hook: _KeyboardHook | None = None
        self._hook_thread: threading.Thread | None = None
        self._floating_visible = False
        self._enabled = True  # 启用/禁用状态
        self._performing_action = False
        self._original_clipboard = ""
        self._last_original_text = ""   # 撤回用：上一次的原始文本
        self._last_action = ""          # "full" 或 "convert_only"
        self._action_requests: queue.Queue = queue.Queue()
        self._settings_visible_flag = False  # 钩子线程安全：缓存设置窗口可见状态
        self._key_capture_active = False     # 钩子线程安全：按键捕获框正在捕获中
        self._undo_pending = False            # 钩子线程安全：Alt+Z 已触发，等待 Alt 松开
        self._convert_pending = False         # 钩子线程安全：Alt+Enter 已触发，等待 Alt 松开
        self._cat_full_mode = True            # 猫模式开关：True=猫模式，False=人模式

        # 加载资源
        self._settings = self._load_settings()
        self._kamojis = _load_kamojis()
        logger.info(f"加载设置: {self._settings}")

        show_hotkey = self._settings.get("show_hotkey", "Alt+Q")
        convert_only_hotkey = self._settings.get("convert_only_hotkey", "Ctrl+Enter")
        undo_hotkey = self._settings.get("undo_hotkey", "Alt+Z")
        toggle_hotkey = self._settings.get("toggle_hotkey", "Alt+Q")

        self._floating = FloatingWindow(
            show_hotkey=show_hotkey,
            convert_only_hotkey=convert_only_hotkey,
            undo_hotkey=undo_hotkey,
            toggle_hotkey=toggle_hotkey,
            kamojis=self._kamojis,
            enabled=self._enabled,
        )
        self._settings_win = SettingsWindow(
            show_hotkey=show_hotkey,
            convert_only_hotkey=convert_only_hotkey,
            undo_hotkey=undo_hotkey,
            toggle_hotkey=toggle_hotkey,
            auto_start=self._settings.get("auto_start", False),
            char_threshold=self._settings.get("char_threshold", 500),
        )
        self._rules_win = RulesWindow()
        self._settings_win.set_key_capture_callback(self._set_key_capture_active)
        self._minmax_filter = MinMaxFilter()
        self._app.installNativeEventFilter(self._minmax_filter)

        self._setup_tray()
        logger.info("系统托盘已创建")

        # 应用开机自启动设置
        self._set_auto_start(self._settings.get("auto_start", False))

        # 信号连接
        self._floating.close_clicked.connect(self._quit)
        self._floating.settings_button.clicked.connect(self._show_settings)
        self._floating.rules_button.clicked.connect(self._show_rules)
        self._rules_win.mode_changed.connect(self._on_cat_mode_changed)
        self._floating.enabled_toggled.connect(self._on_enabled_toggled)
        self._settings_win.settings_saved.connect(self._on_settings_saved)
        self._settings_win.hidden_signal.connect(self._on_settings_hidden)

        # 轮询钩子请求
        self._poll_timer = QTimer(self)
        self._poll_timer.timeout.connect(self._poll_hook_requests)
        self._poll_timer.start(25)

        # 启动后显示悬浮窗
        QTimer.singleShot(300, self._show_floating)

        logger.info("NyatifierApp 初始化完成")

    # ====== 设置持久化 ======

    def _load_settings(self) -> dict:
        default = {
            "show_hotkey": "Alt+Q",
            "convert_only_hotkey": "Ctrl+Enter",
            "undo_hotkey": "Alt+Z",
            "toggle_hotkey": "Alt+Q",
            "auto_start": False,
            "char_threshold": 500,
        }
        try:
            if os.path.exists(SETTINGS_FILE):
                with open(SETTINGS_FILE, "r", encoding="utf-8") as f:
                    loaded = json.load(f)
                    default.update(loaded)
        except Exception as e:
            logger.warning(f"加载设置失败: {e}")
        return default

    def _save_settings(self, settings: dict):
        try:
            with open(SETTINGS_FILE, "w", encoding="utf-8") as f:
                json.dump(settings, f, ensure_ascii=False, indent=2)
            logger.info(f"设置已保存: {settings}")
        except Exception as e:
            logger.error(f"保存设置失败: {e}")

    def _set_auto_start(self, enable: bool):
        """设置开机自启动（Windows 注册表）"""
        key_path = r"Software\Microsoft\Windows\CurrentVersion\Run"
        app_name = "Nyatifier"
        try:
            key = winreg.OpenKey(winreg.HKEY_CURRENT_USER, key_path, 0, winreg.KEY_SET_VALUE)
            if enable:
                exe_path = sys.executable
                script_path = os.path.abspath(sys.argv[0])
                cmd = f'"{exe_path}" "{script_path}"'
                winreg.SetValueEx(key, app_name, 0, winreg.REG_SZ, cmd)
                logger.info(f"已设置开机自启动: {cmd}")
            else:
                try:
                    winreg.DeleteValue(key, app_name)
                    logger.info("已取消开机自启动")
                except FileNotFoundError:
                    pass
            winreg.CloseKey(key)
        except Exception as e:
            logger.error(f"设置开机自启动失败: {e}")

    # ====== 系统托盘 ======

    def _setup_tray(self):
        self._tray = QSystemTrayIcon(self._app)
        self._tray.setToolTip("喵笔生花 / Nyatifier")
        self._tray.setIcon(QIcon(os.path.join(_get_data_dir(), "favicon.ico")))

        menu = QMenu()

        show_action = QAction("显示/隐藏悬浮窗")
        show_action.triggered.connect(self._toggle_floating)
        menu.addAction(show_action)

        toggle_hk = self._settings.get("toggle_hotkey", "Alt+Q")
        self._tray_enable_action = QAction(f"启用/禁用喵化 ({toggle_hk})")
        self._tray_enable_action.triggered.connect(self._toggle_enabled)
        menu.addAction(self._tray_enable_action)

        settings_action = QAction("设置")
        settings_action.triggered.connect(self._show_settings)
        menu.addAction(settings_action)

        menu.addSeparator()

        quit_action = QAction("退出")
        quit_action.triggered.connect(self._quit)
        menu.addAction(quit_action)

        self._tray.setContextMenu(menu)
        self._tray.activated.connect(self._on_tray_activated)
        self._tray.show()

    def _on_tray_activated(self, reason):
        if reason in (
            QSystemTrayIcon.ActivationReason.Trigger,
            QSystemTrayIcon.ActivationReason.DoubleClick,
        ):
            self._toggle_floating()

    # ====== 启用/禁用 ======

    def _toggle_enabled(self):
        self._enabled = not self._enabled
        self._floating.set_enabled(self._enabled)
        logger.info(f"喵化已{'启用' if self._enabled else '禁用'}")

    def _on_enabled_toggled(self):
        self._toggle_enabled()

    def _set_key_capture_active(self, active: bool):
        self._key_capture_active = active

    # ====== 钩子请求队列 ======

    def _queue_request(self, action_type: str):
        try:
            self._action_requests.put_nowait(action_type)
        except queue.Full:
            pass

    def _poll_hook_requests(self):
        try:
            while True:
                req = self._action_requests.get_nowait()
                if req == "toggle":
                    self._toggle_floating()
                elif req == "enable_toggle":
                    self._toggle_enabled()
                elif req == "full":
                    self._execute_full_action()
                elif req == "convert_only":
                    self._execute_convert_only()
                elif req == "undo":
                    self._execute_undo()
        except queue.Empty:
            pass

    # ====== 悬浮窗 ======

    def _toggle_floating(self):
        if self._floating_visible:
            self._floating.hide()
            self._floating_visible = False
            try:
                hwnd = int(self._floating.winId())
                if hwnd:
                    MinMaxFilter.unregister(hwnd)
            except Exception:
                pass
            logger.info("悬浮窗已隐藏")
        else:
            self._show_floating()

    def _show_floating(self):
        screen = self._app.primaryScreen()
        if screen:
            geo = screen.availableGeometry()
            x = geo.right() - self._floating.width() - 20
            y = geo.top() + 20
            self._floating.move(x, y)
        self._floating.show()
        self._floating.raise_()
        self._floating.activateWindow()
        self._floating.setFocus()
        self._floating_visible = True
        # 注册浮窗 HWND，修复 Tool 窗口 MINMAXINFO 坐标错乱
        MinMaxFilter.register(int(self._floating.winId()), self._floating.width(), self._floating.height())
        logger.info("悬浮窗已显示")

    # ====== 设置窗口 ======

    def _show_settings(self):
        sw = self._settings_win
        sw.sync_from_settings(self._settings)
        fw = self._floating
        fw_pos = fw.pos()
        pw, ph = 340, 420
        tx = fw_pos.x()
        ty = fw_pos.y() + fw.height() + 5
        screen = self._app.primaryScreen()
        if screen:
            geo = screen.availableGeometry()
            tx = max(geo.left() + 5, min(tx, geo.right() - pw - 5))
            ty = max(geo.top() + 5, min(ty, geo.bottom() - ph - 5))
        # 必须在 move/resize 前注册，否则首轮 WM_GETMINMAXINFO 会以默认值处理
        MinMaxFilter.register(int(sw.winId()), pw, ph)
        sw.move(tx, ty)
        sw.resize(pw, ph)
        sw.show()
        sw.raise_()
        sw.activateWindow()

        self._settings_visible_flag = True
        logger.info("设置窗口已显示")

    def _show_rules(self):
        rw = self._rules_win
        fw = self._floating
        fw_pos = fw.pos()
        pw, ph = 400, 420
        tx = fw_pos.x()
        ty = fw_pos.y() + fw.height() + 5
        screen = self._app.primaryScreen()
        if screen:
            geo = screen.availableGeometry()
            tx = max(geo.left() + 5, min(tx, geo.right() - pw - 5))
            ty = max(geo.top() + 5, min(ty, geo.bottom() - ph - 5))
        MinMaxFilter.register(int(rw.winId()), pw, ph)
        rw.move(tx, ty)
        rw.resize(pw, ph)
        rw.show()
        rw.raise_()
        rw.activateWindow()
        logger.info("规则窗口已显示")

    def _on_cat_mode_changed(self, full_mode: bool):
        self._cat_full_mode = full_mode
        logger.info(f"猫语模式切换: {'猫' if full_mode else '人'}")

    def _on_settings_hidden(self):
        self._settings_visible_flag = False

    def _on_settings_saved(self, settings: dict):
        self._settings_visible_flag = False
        self._settings.update(settings)
        self._save_settings(self._settings)
        self._floating.set_hotkeys(
            self._settings.get("show_hotkey", "Alt+Q"),
            self._settings.get("convert_only_hotkey", "Ctrl+Enter"),
            self._settings.get("undo_hotkey", "Alt+Z"),
            self._settings.get("toggle_hotkey", "Alt+Q"),
        )
        if "toggle_hotkey" in settings:
            self._update_tray_action_hotkey()
        if "auto_start" in settings:
            self._set_auto_start(settings["auto_start"])

    def _update_tray_action_hotkey(self):
        toggle_hk = self._settings.get("toggle_hotkey", "Alt+Q")
        if hasattr(self, '_tray_enable_action'):
            self._tray_enable_action.setText(f"启用/禁用喵化 ({toggle_hk})")

    # ====== 核心动作：喵化并发送（Enter） ======

    def _execute_full_action(self):
        """Enter: 全选→剪切→转换→粘贴→发送→恢复剪贴板"""
        if self._performing_action:
            return
        self._performing_action = True
        logger.info("=== [发送] 开始 ===")

        try:
            clipboard = QApplication.clipboard()
            self._original_clipboard = clipboard.text()
            logger.debug(f"原始剪贴板: {self._original_clipboard[:50]}...")
            time.sleep(0.05)

            logger.debug("发送 Ctrl+A")
            self._send_ctrl_key(0x41)
            time.sleep(0.05)

            logger.debug("发送 Ctrl+X")
            self._send_ctrl_key(0x58)
            time.sleep(0.1)

            text = clipboard.text()
            logger.debug(f"剪贴板文本: {text[:80] if text else '(空)'}")

            if text and self._check_threshold(text):
                # 超阈值：已粘贴回原文并显示愤怒颜文字
                self._performing_action = False
                return

            self._do_full_action(text)

        except Exception as e:
            logger.exception(f"动作异常: {e}")
            self._performing_action = False

    def _do_full_action(self, text: str):
        """执行完整的喵化发送（无阈值检查）"""
        self._performing_action = True
        clipboard = QApplication.clipboard()
        try:
            self._last_original_text = text  # 撤回用
            self._last_action = "full"
            converted = convert_to_cat_speak(text, full_mode=self._cat_full_mode) if text else ""
            logger.info(f"喵化: {converted[:60]}")

            if converted:
                clipboard.setText(converted)
                time.sleep(0.05)

                logger.debug("发送 Ctrl+V")
                self._send_ctrl_key(0x56)
                time.sleep(0.05)

                logger.debug("发送 Enter")
                self._send_key(0x0D)
                time.sleep(0.1)

            if self._original_clipboard:
                clipboard.setText(self._original_clipboard)
                logger.debug("剪贴板已恢复")

        except Exception as e:
            logger.exception(f"动作异常: {e}")
        finally:
            self._performing_action = False
            logger.info("=== [发送] 结束 ===")

    # ====== 核心动作：仅喵化（Ctrl+Enter） ======

    def _execute_convert_only(self):
        """Ctrl+Enter: 全选→剪切→转换→粘贴回去（不发送）→恢复剪贴板"""
        if self._performing_action:
            return
        self._performing_action = True
        logger.info("=== [仅喵化] 开始 ===")

        try:
            clipboard = QApplication.clipboard()

            self._original_clipboard = clipboard.text()
            time.sleep(0.05)

            self._send_ctrl_key(0x41)
            time.sleep(0.05)
            self._send_ctrl_key(0x58)
            time.sleep(0.1)

            text = clipboard.text()

            if text and self._check_threshold(text):
                # 超阈值：已粘贴回原文并显示愤怒颜文字
                self._performing_action = False
                return

            self._do_convert_only(text)

        except Exception as e:
            logger.exception(f"动作异常: {e}")
            self._performing_action = False

    def _do_convert_only(self, text: str):
        """执行仅喵化（无阈值检查）"""
        self._performing_action = True
        clipboard = QApplication.clipboard()
        try:
            self._last_original_text = text
            self._last_action = "convert_only"
            converted = convert_to_cat_speak(text, full_mode=self._cat_full_mode) if text else ""

            if converted:
                clipboard.setText(converted)
                time.sleep(0.05)
                self._send_ctrl_key(0x56)
                time.sleep(0.05)

            if self._original_clipboard:
                clipboard.setText(self._original_clipboard)
                logger.debug("剪贴板已恢复")

        except Exception as e:
            logger.exception(f"动作异常: {e}")
        finally:
            self._performing_action = False
            logger.info("=== [仅喵化] 结束 ===")

    # ====== 撤回（Alt+Z） ======

    def _execute_undo(self):
        """撤回：全选→粘贴原始文本"""
        if self._performing_action:
            return
        if not self._last_original_text:
            return
        self._performing_action = True
        logger.info("=== [撤回] 开始 ===")
        logger.debug(f"[撤回] 原始文本: {self._last_original_text[:80]}, action={self._last_action}")

        try:
            clipboard = QApplication.clipboard()
            saved_clipboard = clipboard.text()
            logger.debug(f"[撤回] 保存剪贴板: {saved_clipboard[:50] if saved_clipboard else '(空)'}")
            time.sleep(0.05)

            # 全选
            logger.debug("[撤回] 发送 Ctrl+A 全选")
            self._send_ctrl_key(0x41)
            time.sleep(0.05)

            # 粘贴原始文本
            clipboard.setText(self._last_original_text)
            logger.debug(f"[撤回] 设置剪贴板为原始文本，长度={len(self._last_original_text)}")
            time.sleep(0.05)
            logger.debug("[撤回] 发送 Ctrl+V 粘贴")
            self._send_ctrl_key(0x56)
            time.sleep(0.05)

            # 如果是全发送，自动按 Enter
            if self._last_action == "full":
                self._send_key(0x0D)
                time.sleep(0.05)

            # 恢复剪贴板
            if saved_clipboard:
                clipboard.setText(saved_clipboard)

        except Exception as e:
            logger.exception(f"撤回异常: {e}")
        finally:
            self._performing_action = False
            logger.info("=== [撤回] 结束 ===")

    # ====== 字符阈值检查 ======

    def _check_threshold(self, text: str) -> bool:
        """返回 True 表示超阈值，已显示 exceeded 颜文字并粘贴回原文"""
        threshold = self._settings.get("char_threshold", 500)
        if threshold <= 0:
            return False
        if len(text) >= threshold:
            # 粘贴回原文
            clipboard = QApplication.clipboard()
            clipboard.setText(text)
            time.sleep(0.02)
            self._send_ctrl_key(0x56)
            time.sleep(0.05)
            self._original_clipboard = ""
            # 显示愤怒颜文字，3秒后自动恢复
            self._floating.show_exceeded_kaomoji()
            return True
        return False

    # ====== 模拟按键 ======

    @staticmethod
    def _send_ctrl_key(key_code: int):
        KDOWN, KUP = 0x0000, 0x0002
        user32.keybd_event(0x11, 0, KDOWN, 0)
        time.sleep(0.02)
        user32.keybd_event(key_code, 0, KDOWN, 0)
        time.sleep(0.02)
        user32.keybd_event(key_code, 0, KUP, 0)
        time.sleep(0.02)
        user32.keybd_event(0x11, 0, KUP, 0)
        time.sleep(0.02)

    @staticmethod
    def _send_key(key_code: int):
        user32.keybd_event(key_code, 0, 0x0000, 0)
        time.sleep(0.02)
        user32.keybd_event(key_code, 0, 0x0002, 0)
        time.sleep(0.02)

    # ====== 启动/停止 ======

    def start(self):
        logger.info("启动键盘钩子线程")
        self._hook = _KeyboardHook(self)
        self._hook_thread = threading.Thread(
            target=self._hook.start, daemon=True, name="KeyboardHook"
        )
        self._hook_thread.start()
        logger.info(f"键盘钩子线程已启动: {self._hook_thread.name}")

    def _quit(self):
        logger.info("退出应用")
        if self._hook:
            self._hook.stop()
        self._tray.hide()
        self._app.quit()
