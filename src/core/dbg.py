# -*- coding: utf-8 -*-
"""轻量崩溃追踪日志：记录关键操作时间戳，崩溃后定位最后执行步骤。"""
import os
import datetime

_LOGPATH = None


def init(path=None):
    global _LOGPATH
    _LOGPATH = path


def _default_log_path():
    """项目根/src/core/dbg.py -> <项目根>/logs/scs_debug.log"""
    root = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
    return os.path.join(root, 'logs', 'scs_debug.log')


def log(msg):
    try:
        p = _LOGPATH or _default_log_path()
        try:
            os.makedirs(os.path.dirname(p), exist_ok=True)
        except Exception:
            pass
        ts = datetime.datetime.now().strftime('%H:%M:%S.%f')[:-3]
        with open(p, 'a', encoding='utf-8') as f:
            f.write('%s %s\n' % (ts, msg))
    except Exception:
        pass
