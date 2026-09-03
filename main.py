# -*- coding: utf-8 -*-
"""
main.py —— 船舶静水力计算软件 (SCS Python 移植版) 根入口（薄启动器）

实际逻辑在 src/app/main.py；本项目从 v3 起按功能分层：
    src/app/    应用组合与入口
    src/core/   业务计算 / 操作 / ML / 日志
    src/ui/     tkinter 界面
    src/viewer/ Qt 3D 视窗
本文件仅负责把项目根加入 sys.path 后转调 src.app.main.main()，
保持「python main.py」的启动习惯不变。
"""
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))


def main():
    if HERE not in sys.path:
        sys.path.insert(0, HERE)
    from src.app.main import main as _entry
    _entry()


if __name__ == '__main__':
    main()
