# -*- coding: utf-8 -*-
"""
src/app/main.py —— 船舶静水力计算软件 (SCS Python 移植版) 启动入口
由根目录 main.py 引导调用；也可直接运行本文件（需项目根在 sys.path）。

使用方法：
    python main.py
"""
import os
import sys


def main():
    # 项目根 = src 的上一级（含 icon/ 与 logs/）
    here = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
    if here not in sys.path:
        sys.path.insert(0, here)

    # 日志统一写入 <项目根>/logs/（确保目录存在）
    log_dir = os.path.join(here, 'logs')
    try:
        os.makedirs(log_dir, exist_ok=True)
    except Exception:
        pass

    # 避免 Windows 控制台 GBK 编码导致打印 Unicode 报错
    for stream in (sys.stdout, sys.stderr):
        try:
            stream.reconfigure(encoding='utf-8', errors='replace')
        except Exception:
            pass

    # 崩溃诊断：原生崩溃（段错误）时把 Python 线程回溯写入 scs_crash.log
    # 与 stderr。file 用"二进制追加"模式（faulthandler 需要真实 fd），
    # 确保崩溃时日志一定落盘。
    from src.core import dbg
    dbg.init(os.path.join(log_dir, 'scs_debug.log'))
    try:
        import faulthandler
        _crash_fh = open(os.path.join(log_dir, 'scs_crash.log'), 'ab', buffering=0)
        faulthandler.enable(file=_crash_fh, all_threads=True)
        dbg.log('faulthandler enabled')
    except Exception as _e:
        try:
            import faulthandler
            faulthandler.enable(all_threads=True)   # 回退到 stderr
        except Exception:
            pass

    import tkinter as tk
    from src.app.ship_app import ShipApp

    root = tk.Tk()
    icon_dir = os.path.join(here, 'icon')
    app = ShipApp(root, icon_dir=icon_dir)
    dbg.log('app started')
    root.mainloop()


if __name__ == '__main__':
    main()
