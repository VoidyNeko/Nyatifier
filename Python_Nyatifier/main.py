"""喵笔生花 / Nyatifier — 猫猫语转换悬浮窗工具"""

import sys

from PyQt6.QtWidgets import QApplication

from src.app import NyatifierApp, logger


def main():
    logger.info("=== 喵笔生花 启动 ===")
    app = QApplication(sys.argv)
    app.setApplicationName("喵笔生花")
    app.setQuitOnLastWindowClosed(False)

    nyatifier = NyatifierApp(app)
    nyatifier.start()

    logger.info("进入 Qt 事件循环")
    exit_code = app.exec()
    logger.info(f"Qt 事件循环结束, exit_code={exit_code}")
    sys.exit(exit_code)


if __name__ == "__main__":
    main()
