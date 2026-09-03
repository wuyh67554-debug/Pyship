# -*- coding: utf-8 -*-
import os as _os
import sys as _sys
_sys.path.insert(0, _os.path.dirname(_os.path.dirname(_os.path.abspath(__file__))))
"""5 项功能回归：多项目树/重命名、首选项、Qt 点云与型线、scs logo、日志清理。

不依赖 GPU 渲染；Qt 视窗可用时额外校验点云/型线/偏好应用。
"""
import os
import json
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


# 备份用户 prefs，测试结束恢复，避免污染
_bk = os.path.expanduser('~/scs_prefs.json')
_prefs_backup = None
if os.path.exists(_bk):
    with open(_bk, 'r', encoding='utf-8') as _f:
        _prefs_backup = _f.read()

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
root.geometry('400x300+1+1')
from src.app.ship_app import ShipApp
app = ShipApp(root, icon_dir='icon')
root.update()

try:
    # ---------- 1. 树：多项目 / 重命名 / 空白新建 ----------
    tree = app.tree
    orig_root = app.tree_root
    check('默认项目节点存在', tree.exists(orig_root) and app.tree.item(orig_root, 'text') == '项目')
    check('项目节点为 project 类型', app.tree_meta.get(orig_root, {}).get('type') == 'project')

    n_before = len([c for c in tree.get_children('')
                    if app.tree_meta.get(c, {}).get('type') == 'project'])
    app._new_project()
    n_after = len([c for c in tree.get_children('')
                   if app.tree_meta.get(c, {}).get('type') == 'project'])
    check('右键空白新建项目', n_after == n_before + 1, '项目数 %d->%d' % (n_before, n_after))
    new_proj = app._current_project
    check('新项目成为当前项目', new_proj != orig_root and app.tree.item(new_proj, 'text') == '项目 2')
    check('新项目含 Table/Model/Face',
          app.table_root == app._find_project_child(new_proj, 'Table')
          and app.model_root == app._find_project_child(new_proj, 'Model')
          and app.face_root == app._find_project_child(new_proj, 'Face'))
    app.tree.item(new_proj, text='我的船A')
    check('项目可重命名', app.tree.item(new_proj, 'text') == '我的船A')
    app.tree.item(app.table_root, text='表格')
    check('分组可重命名', app.tree.item(app.table_root, 'text') == '表格')

    # 删除项目（保留至少一个）
    app._switch_project(orig_root)
    app._delete_tree_node(new_proj)
    check('删除项目后仍有项目', len([c for c in tree.get_children('')
                                if app.tree_meta.get(c, {}).get('type') == 'project']) == 1)

    # ---------- 2. 首选项 ----------
    app.prefs.update({'qt3d_background': 'light', 'qt3d_invert_rotate': True,
                      'qt3d_invert_zoom': False, 'qt3d_show_axes': False,
                      'qt3d_show_grid': False})
    app._save_prefs()
    check('首选项 JSON 已保存', os.path.exists(app._prefs_path()))
    reloaded = app._load_prefs()
    check('首选项重载一致',
          reloaded.get('qt3d_background') == 'light' and reloaded.get('qt3d_invert_rotate') is True)
    check('首选项对话框方法存在', hasattr(app, 'set_preferences_clicked'))

    # 对话框全流程：打开 -> 确定 -> 关闭；再打开 -> 取消 -> 关闭（不闪退、Qt 泵正常恢复）
    def _find_dlg():
        for w in root.winfo_children():
            if isinstance(w, tk.Toplevel):
                return w
        return None

    def _click_dlg_button(dlg, text):
        for w in dlg.winfo_children():
            for sub in w.winfo_children():
                for btn in sub.winfo_children():
                    if isinstance(btn, (tk.Button, ttk.Button)) and btn['text'] == text:
                        btn.invoke()
                        return True
        return False

    def _open_dlg():
        app.set_preferences_clicked()
        for _ in range(20):  # 对话框经 after(30) 延迟构建
            root.update()
            if _find_dlg() is not None:
                break
            import time
            time.sleep(0.03)
        return _find_dlg()

    dlg1 = _open_dlg()
    check('首选项对话框可打开', dlg1 is not None)
    if dlg1 is not None:
        if app.qt3d_host is not None:
            check('对话框打开期间 Qt 泵暂停', app.qt3d_host._pump_active is False)
        _click_dlg_button(dlg1, '确定')
        root.update()
        check('确定后对话框关闭', _find_dlg() is None)
        if app.qt3d_host is not None:
            check('确定后 Qt 泵恢复', app.qt3d_host._pump_active is True)
    dlg2 = _open_dlg()
    if dlg2 is not None:
        _click_dlg_button(dlg2, '取消')
        root.update()
        check('取消后对话框关闭', _find_dlg() is None)
        if app.qt3d_host is not None:
            check('取消后 Qt 泵恢复', app.qt3d_host._pump_active is True)

    if app.qt3d_host is not None:
        app._apply_qt3d_prefs()
        w = app.qt3d_host.widget
        check('背景样式已应用', w._bg_style == 'light', 'bg=%s' % w._bg_style)
        check('旋转反转已应用', w._invert_rotate is True)
        check('坐标轴开关已应用', w._show_axes is False)
        check('地面网格开关已应用', w._show_grid is False)

    # ---------- 3. 点云 / 型线显示到 Qt ----------
    app.Lpp, app.Breadth, app.Depth = 100.0, 12.0, 8.0
    app.LppStartStation, app.LppEndStation = 0.0, 10.0
    st = np.linspace(0, 10, 11)
    hw = 6.0 * np.sin(np.pi * st / 10)
    app.waterlines = [
        {'type': 'waterline', 'name': 'WL0', 'height': 0.0,
         'table': {'columns': ['列', '站号', '半宽'],
                   'rows': [[i + 1, float(s), float(h)] for i, (s, h) in enumerate(zip(st, hw))]}},
        {'type': 'waterline', 'name': 'WL4', 'height': 4.0,
         'table': {'columns': ['列', '站号', '半宽'],
                   'rows': [[i + 1, float(s), float(h * 0.8)] for i, (s, h) in enumerate(zip(st, hw))]}},
    ]
    app.sections = {}
    z = np.linspace(0, 6, 7)
    for s in st:
        y = 6.0 * np.sin(np.pi * s / 10) * (1 - (z / 6.0) ** 2 * 0.6)
        app.sections[float(s)] = {'Y': y.tolist(), 'Z': z.tolist()}
    app.var_mesh_quality.set('标准')
    app.gen_pointcloud_clicked()
    if app.qt3d_host is not None:
        check('点云推送到 Qt 视窗', app.qt3d_host.widget._points is not None,
              'points=%d' % (0 if app.qt3d_host.widget._points is None
                             else len(app.qt3d_host.widget._points)))
    app.gen_lines_clicked()
    if app.qt3d_host is not None:
        check('型线推送到 Qt 视窗', len(app.qt3d_host.widget._line_groups) > 0,
              'groups=%d' % len(app.qt3d_host.widget._line_groups))

    # ---------- 4. scs logo ----------
    payload = app._build_project_payload()
    check('项目文件内嵌 logo', bool(payload.get('logo')),
          'len=%d' % len(payload.get('logo') or ''))
    app._apply_project_logo(payload)
    check('项目 logo 应用到窗口图标', hasattr(app, '_project_logo_photo'))
    tmpdir = tempfile.mkdtemp()
    scs = os.path.join(tmpdir, 'test.scs')
    app._atomic_save(scs, payload)
    with open(scs, 'rb') as f:
        import pickle
        back = pickle.load(f)
    check('scs 文件可回读且含 logo', back.get('logo') == payload.get('logo'))
    os.remove(scs)

    # ---------- 5. 日志清理 ----------
    logs = '\n'.join(app.LogBuffer)
    check('日志不含"步骤"字样', '步骤' not in logs)
    check('日志不含装饰分隔线', '====' not in logs and '---' not in logs)
    app.gen_hull_clicked()
    logs2 = '\n'.join(app.LogBuffer)
    check('蒙皮日志为简洁描述（无面片数细节）', '船体蒙皮生成成功（质量: 标准）。' in logs2)
    check('蒙皮日志不含"面片数"细节', '面片数' not in logs2.split('\n')[-1])
finally:
    # 恢复用户 prefs（测试前不存在则删除，存在则还原内容）
    try:
        if _prefs_backup is None:
            if os.path.exists(_bk):
                try:
                    os.remove(_bk)
                except OSError:
                    pass
        else:
            with open(_bk, 'w', encoding='utf-8') as _f:
                _f.write(_prefs_backup)
    except Exception:
        pass
    try:
        root.destroy()
    except Exception:
        pass

print()
print('FEATURES TEST %s  (PASS=%d FAIL=%d)' % ('PASS' if FAIL == 0 else 'FAIL', PASS, FAIL))
raise SystemExit(0 if FAIL == 0 else 1)
