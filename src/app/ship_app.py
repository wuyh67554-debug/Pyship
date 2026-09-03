# -*- coding: utf-8 -*-
"""
ship_app.py —— 主应用类（组合 UI / 操作 / 计算三个模块）
"""

from src.ui.ship_app_ui import ShipAppUI
from src.core.ship_app_actions import ShipAppActions
from src.core.ship_app_calc import ShipAppCalc


class ShipApp(ShipAppUI, ShipAppActions, ShipAppCalc):
    """船舶静水力计算软件主应用"""

    def __init__(self, root, icon_dir=None):
        # 先初始化 UI 基类
        super().__init__(root, icon_dir)
        # 启动提示
        self.log('欢迎使用船舶计算软件 SCS ')
        self._ensure_qt3d()
        self._register_scs_file_association()
        # 应用界面偏好（字体大小等，保持 Windows 原生外观）
        self._apply_ui_prefs()
        # 自动保存（独立备份文件）+ 崩溃恢复检测（延迟到窗口显示后）
        self._start_autosave()
        try:
            self.root.after(600, self._check_autosave_recovery)
        except Exception:
            pass


def main():
    import tkinter as tk
    root = tk.Tk()
    app = ShipApp(root)
    root.mainloop()


if __name__ == '__main__':
    main()
