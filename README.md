# 喵笔生花 / Nyatifier

猫猫语转换悬浮窗工具 — 一键把输入框中的中文字符变成猫猫语 (。>ω<)。  
A cat-language text converter with floating overlay — turns any text into 'catspeak'.

## 功能 / Features

- **猫语转换**：中文输入框文字自动替换为猫猫语
- **手动替换**：双击悬浮球手动替换（微信等软件识别不到输入框,,Ծ‸Ծ,,）
- **悬浮窗**：点击悬浮球即可在当前输入框一键猫化
- **手动模式**：双击悬浮球弹出对话框，手动粘贴文字进行转换
- **撤回支持**：转换后可一键撤回，恢复原文

## 项目结构 / Structure

| 目录 | 说明 |
|------|------|
| `Nyatifier-Android/` | Android 端 (Kotlin)，通过无障碍服务实现输入框文本替换 |
| `Python_Nyatifier/` | 桌面端 (Python + PyQt6)，通过剪贴板监控实现全局文本替换 |

## 运行 / Usage

### Android
用 Android Studio 打开 `Nyatifier-Android/`，编译安装后开启无障碍服务即可。

### Python 桌面版 (源码运行)
```bash
cd Python_Nyatifier
pip install PyQt6
python main.py
```

### 打包为 Windows EXE
```bash
cd Python_Nyatifier
pip install pyinstaller
pyinstaller Nyatifier.spec
# 输出在 dist/Nyatifier.exe
```

## 许可 / License

[MIT](LICENSE)
