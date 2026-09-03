# -*- coding: utf-8 -*-
import os as _os
import sys as _sys
_sys.path.insert(0, _os.path.dirname(_os.path.dirname(_os.path.abspath(__file__))))
"""UX/产品完整性回归：状态栏增强、页签快捷键、最近文件、自动保存、
偏好扩展(字体/自动保存)、诊断面板、忙指示。"""
import os
import time
import tempfile
import numpy as np
import tkinter as tk
from tkinter import ttk, messagebox

PASS = 0
FAIL = 0


def check(name, cond, detail=''):
    global PASS, FAIL
    if cond:
        PASS += 1
        print('[PASS] %s %s' % (name, detail))
    else:
        FAIL += 1
        print('[FAIL] %s %s' % (name, detail))


# 备份/恢复用户 prefs
_bk = os.path.expanduser('~/scs_prefs.json')
_prefs_backup = None
if os.path.exists(_bk):
    with open(_bk, 'r', encoding='utf-8') as f:
        _prefs_backup = f.read()

for _fn in ('showinfo', 'showwarning', 'showerror', 'askyesno'):
    setattr(messagebox, _fn, lambda *a, **k: True)
from src.ui import ui_widgets
ui_widgets.ask_text_dialog = lambda *a, **k: ''
ui_widgets.ask_numeric_dialog = lambda *a, **k: None
ui_widgets.ask_multi_select = lambda *a, **k: [1]
ui_widgets.ask_multiline_input = lambda *a, **k: ''
from src.core import ship_app_actions
for _m in ('ask_text_dialog', 'ask_numeric_dialog', 'ask_multi_select', 'ask_multiline_input'):
    setattr(ship_app_actions, _m, getattr(ui_widgets, _m))

root = tk.Tk()
root.geometry('500x400+1+1')
from src.app.ship_app import ShipApp
app = ShipApp(root, icon_dir='icon')
root.update()

try:
    # ---------- 1. 状态栏：项目名 + 脏标记 ----------
    app._refresh_statusbar()
    check('状态栏含项目名', '项目: 项目' in app.var_project.get(), app.var_project.get())
    app._mark_dirty()
    check('脏标记显示 *', '*' in app.var_project.get(), app.var_project.get())
    app._clear_dirty()
    check('保存后脏标记清除', '*' not in app.var_project.get(), app.var_project.get())

    # ---------- 2. 页签快捷键 ----------
    app._goto_tab(3)
    check('直达第4页签', app.notebook.select() == app.notebook.tabs()[3])
    app._cycle_tab(1)
    check('循环下一页', app.notebook.select() == app.notebook.tabs()[4])
    app._goto_tab(0)

    # ---------- 3. 最近文件 ----------
    tmpdir = tempfile.mkdtemp()
    scs = os.path.join(tmpdir, 'ux_test.scs')
    app._atomic_save(scs, app._build_project_payload())
    app._add_recent_project(scs)
    check('最近文件已记录', scs in app._recent_projects())
    check('最近菜单已重建', hasattr(app, 'm_recent') and app.m_recent.index('end') >= 0)
    app._open_recent(scs)
    check('最近文件打开成功', app._current_project_path == os.path.abspath(scs))
    app._remove_recent_project(scs)
    check('最近文件移除', scs not in app._recent_projects())

    # ---------- 4. 自动保存（独立备份） ----------
    app.prefs['autosave_enabled'] = True  # 显式开启，避免受用户偏好残留影响
    app._mark_dirty()
    app._current_project_path = os.path.abspath(scs)
    app._do_autosave()
    backup = app._autosave_backup_path()
    check('自动保存备份已生成', os.path.exists(backup))
    check('自动保存后仍标记未保存', app._dirty is True)
    for p in (backup, scs):
        try:
            os.remove(p)
        except OSError:
            pass

    # ---------- 5. 首选项扩展 ----------
    app.prefs.update({'ui_font_size': 11, 'autosave_enabled': True,
                      'autosave_interval': 10})
    app._apply_ui_prefs()
    check('自动保存间隔读取', app._autosave_interval_min() == 10)
    check('自动保存启用', app._autosave_enabled() is True)
    app.set_preferences_clicked()
    dlg = None
    for _ in range(20):
        root.update()
        for w in root.winfo_children():
            if isinstance(w, tk.Toplevel):
                dlg = w
                break
        if dlg:
            break
        time.sleep(0.03)
    if dlg is not None:
        labels = []
        for w in dlg.winfo_children():
            for sub in w.winfo_children():
                if isinstance(sub, tk.Label):
                    labels.append(sub['text'])
        check('首选项含字体设置', any('字体' in t for t in labels))
        check('首选项含自动保存设置', any('自动保存' in t for t in labels))
        for w in dlg.winfo_children():
            for sub in w.winfo_children():
                for btn in sub.winfo_children():
                    if isinstance(btn, tk.Button) and btn['text'] == '取消':
                        btn.invoke()
        root.update()

    # ---------- 6. 诊断面板 + 忙指示 ----------
    env = app._env_info_text()
    check('诊断信息含 Python', 'Python' in env)
    check('诊断信息含 Qt3D', 'Qt 3D' in env)
    app.show_diagnostics_clicked()
    root.update()
    dlg2 = None
    for w in root.winfo_children():
        if isinstance(w, tk.Toplevel):
            dlg2 = w
            break
    check('诊断对话框已打开', dlg2 is not None)
    if dlg2 is not None:
        for w in dlg2.winfo_children():
            for sub in w.winfo_children():
                if isinstance(sub, ttk.Button) and sub['text'] == '关闭':
                    sub.invoke()
        root.update()
    app.set_busy(True, '测试中...')
    check('忙指示状态栏', app.var_status.get() == '测试中...')
    app.set_busy(False)
    check('忙指示复位', app.var_status.get().startswith('当前'))
finally:
    try:
        if _prefs_backup is None:
            if os.path.exists(_bk):
                os.remove(_bk)
        else:
            with open(_bk, 'w', encoding='utf-8') as f:
                f.write(_prefs_backup)
    except Exception:
        pass
    try:
        root.destroy()
    except Exception:
        pass

print()
print('UX TEST %s  (PASS=%d FAIL=%d)' % ('PASS' if FAIL == 0 else 'FAIL', PASS, FAIL))
raise SystemExit(0 if FAIL == 0 else 1)
