# -*- coding: utf-8 -*-
import os as _os
import sys as _sys
_sys.path.insert(0, _os.path.dirname(_os.path.dirname(_os.path.abspath(__file__))))
"""验证可见 PanedWindow 拉杆钳制（逐个选中 Tab 测试其内部 paned）"""
import tkinter as tk
from tkinter import messagebox

for _fn in ('showinfo', 'showwarning', 'showerror', 'askyesno'):
    setattr(messagebox, _fn, lambda *a, **k: True)

from src.ui import ui_widgets
ui_widgets.ask_text_dialog = lambda *a, **k: ''
ui_widgets.ask_numeric_dialog = lambda *a, **k: None
ui_widgets.ask_multi_select = lambda *a, **k: [1]
ui_widgets.ask_multiline_input = lambda *a, **k: ''

root = tk.Tk()
root.geometry('1380x860')
from src.app.ship_app import ShipApp
app = ShipApp(root, icon_dir='icon')
root.update()


def visible_paneds(w, out):
    """收集当前真实映射在屏幕上的 ClampedPanedWindow"""
    for c in w.winfo_children():
        if isinstance(c, ui_widgets.ClampedPanedWindow) and c.winfo_ismapped():
            out.append(c)
        visible_paneds(c, out)


ok_all = True
tested = 0
for t in range(8):
    app.notebook.select(t)
    root.update()
    paneds = []
    visible_paneds(root, paneds)
    for pw in paneds:
        orient = str(pw.cget('orient'))
        n = len(pw._panes)
        min_sizes = pw._min_sizes
        total = pw.winfo_width() if orient == 'horizontal' else pw.winfo_height()
        if total < 100:
            continue
        for i in range(n - 1):
            # 拖到最左/上
            pw.sashpos(i, 5)
            root.update()
            pw._clamp()
            root.update()
            pos = pw.sashpos(i)
            min_pos = sum(min_sizes[:i + 1])
            if pos < min_pos - 2:
                print('FAIL Tab%d %s sash%d 左钳制失败 pos=%d min=%d total=%d'
                      % (t, orient, i, pos, min_pos, total))
                ok_all = False
            tested += 1
            # 拖到最右/下（与 clamp 内部相同的修正逻辑）
            pw.sashpos(i, total - 5)
            root.update()
            pw._clamp()
            root.update()
            pos = pw.sashpos(i)
            max_pos = total - sum(min_sizes[i + 1:])
            min_pos = sum(min_sizes[:i + 1])
            if max_pos < min_pos:
                max_pos = min_pos
            if pos > max_pos + 2:
                print('FAIL Tab%d %s sash%d 右钳制失败 pos=%d max=%d total=%d'
                      % (t, orient, i, pos, max_pos, total))
                ok_all = False
            tested += 1

print('测试 sash 次数: %d' % tested)
print('SASH CLAMP %s' % ('PASS' if ok_all else 'FAIL'))
root.destroy()
