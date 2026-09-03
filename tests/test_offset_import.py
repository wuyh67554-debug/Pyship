# -*- coding: utf-8 -*-
import os as _os
import sys as _sys
_sys.path.insert(0, _os.path.dirname(_os.path.dirname(_os.path.abspath(__file__))))
"""验证从"识别结果"导入：半宽页 → 水线面/甲板线；横剖面页 → 横剖面"""
import os
import sys
import math
import tkinter as tk
from tkinter import messagebox

import numpy as np

for _fn in ('showinfo', 'showwarning', 'showerror', 'askyesno'):
    setattr(messagebox, _fn, lambda *a, **k: True)

from src.ui import ui_widgets
# [1] == 列表第 1 项 == "-- 全部导入 --"
ui_widgets.ask_multi_select = lambda *a, **k: [1]
ui_widgets.ask_text_dialog = lambda *a, **k: ''
ui_widgets.ask_numeric_dialog = lambda *a, **k: None
ui_widgets.ask_multiline_input = lambda *a, **k: ''

from src.core import ship_app_actions
ship_app_actions.ask_multi_select = ui_widgets.ask_multi_select
ship_app_actions.ask_text_dialog = ui_widgets.ask_text_dialog
ship_app_actions.ask_numeric_dialog = ui_widgets.ask_numeric_dialog
ship_app_actions.ask_multiline_input = ui_widgets.ask_multiline_input

root = tk.Tk()
root.withdraw()
from src.app.ship_app import ShipApp
app = ShipApp(root, icon_dir='icon')
root.update()

ok = True


def check(name, cond, detail=''):
    global ok
    print('[%s] %s %s' % ('PASS' if cond else 'FAIL', name, detail))
    if not cond:
        ok = False


# ---- 构造"识别结果"节点 ----
# 列：station | half_wl(h=1.0) | half_wl(h=3.0) | half_deck | z_deck
roles = ['station', 'half_wl', 'half_wl', 'half_deck', 'z_deck']
user_names = ['站号列_1', '水线半宽_1', '水线半宽_2', '甲板半宽_1', '甲板高度_1']
stations = [0, 1, 2, 3, 4, 5]
hw1 = [0, 3000, 5000, 5000, 3000, 0]      # mm, 高度 1.0 m
hw2 = [0, 4000, 6000, 6000, 4000, 0]      # mm, 高度 3.0 m
hd = [0, 5000, 7000, 7000, 5000, 0]       # mm
zd = [8000, 8200, 8500, 8500, 8200, 8000]  # mm

data = [[stations[i], hw1[i], hw2[i], hd[i], zd[i]] for i in range(len(stations))]
numeric = np.array(data, dtype=float)
heights = np.array([math.nan, 1.0, 3.0, math.nan, math.nan])


def make_result_node():
    return app._tree_add(app.table_root, '识别结果', {
        'type': 'result', 'Roles': roles, 'BaseNames': user_names,
        'UserNames': user_names, 'Data': data, 'Numeric': numeric,
        'heightValues': heights})


def tree_texts(parent):
    return [app.tree.item(c, 'text') for c in app.tree.get_children(parent)]


# ================= 1. 横剖面页 (isTap=3) → 导入横剖面 =================
print('=' * 60)
print('横剖面页 (isTap=3) 导入横剖面')
print('=' * 60)
app.notebook.select(2)
root.update()
check('当前 isTap == 3', app.isTap == 3, '实际 %d' % app.isTap)

node = make_result_node()
app.tree.selection_set(node)
root.update()
check('选中"识别结果"节点后仍停留在横剖面页 (isTap 仍为 3)',
      app.isTap == 3, '实际 %d' % app.isTap)

app.import_from_offset_clicked()
root.update()

check('bodyplans 已生成（6 个站）', len(app.bodyplans) == 6,
      '实际 %d' % len(app.bodyplans))
check('sections 已生成（6 个站）', len(app.sections) == 6,
      '实际 %d' % len(app.sections))
check('水线面未被误导入', len(app.waterlines) == 0,
      '实际 %d' % len(app.waterlines))

# 站 2 的剖面：z=[1.0,3.0,8.5]，半宽=[5.0,6.0,7.0] m
sec2 = app.sections.get(2.0)
check('站 2 存在', sec2 is not None)
if sec2:
    check('站 2 高度序列 [1.0, 3.0, 8.5]',
          np.allclose(sec2['Z'], [1.0, 3.0, 8.5]), str(sec2['Z']))
    check('站 2 半宽序列 [5.0, 6.0, 7.0] m（mm 已 /1000）',
          np.allclose(sec2['Y'], [5.0, 6.0, 7.0]), str(sec2['Y']))

# 树结构：Face -> 船型模型 -> Body Plan -> 站 x
ships = [c for c in app.tree.get_children(app.face_root)
         if app.tree.item(c, 'text') == '船型模型']
check('Face 下创建了"船型模型"节点', len(ships) == 1, '实际 %d' % len(ships))
if ships:
    bodies = [c for c in app.tree.get_children(ships[0])
              if app.tree.item(c, 'text') == 'Body Plan']
    check('船型模型下创建了 Body Plan 节点', len(bodies) == 1, '实际 %d' % len(bodies))
    if bodies:
        check('Body Plan 下有 6 个站节点',
              len(app.tree.get_children(bodies[0])) == 6,
              '实际 %d' % len(app.tree.get_children(bodies[0])))

# 重复导入应复用节点，而不是再建一个"船型模型"
app.tree.selection_set(node)
app.import_from_offset_clicked()
root.update()
ships2 = [c for c in app.tree.get_children(app.face_root)
          if app.tree.item(c, 'text') == '船型模型']
check('重复导入复用同一"船型模型"节点（无重复）', len(ships2) == 1,
      '实际 %d' % len(ships2))
if ships2:
    bodies2 = [c for c in app.tree.get_children(ships2[0])
               if app.tree.item(c, 'text') == 'Body Plan']
    check('重复导入复用同一 Body Plan 节点', len(bodies2) == 1,
          '实际 %d' % len(bodies2))

# ================= 2. 半宽页 (isTap=2) → 导入水线面/甲板线 =================
print()
print('=' * 60)
print('半宽页 (isTap=2) 导入水线面/甲板线')
print('=' * 60)
app.bodyplans.clear()
app.sections.clear()
app.waterlines.clear()
app.decklines.clear()
app.isTap = 2

node2 = make_result_node()
app.tree.selection_set(node2)
root.update()

app.import_from_offset_clicked()
root.update()

check('水线面已导入 2 条', len(app.waterlines) == 2, '实际 %d' % len(app.waterlines))
check('甲板线已导入 1 条', len(app.decklines) == 1, '实际 %d' % len(app.decklines))
check('横剖面未被误导入', len(app.bodyplans) == 0, '实际 %d' % len(app.bodyplans))

# ================= 3. 其它页 → 提示切换，不导入 =================
print()
print('=' * 60)
print('其它页 (isTap=1) 应提示切换，不执行导入')
print('=' * 60)
app.bodyplans.clear()
app.sections.clear()
app.waterlines.clear()
app.decklines.clear()
app.isTap = 1
node3 = make_result_node()
app.tree.selection_set(node3)
app.import_from_offset_clicked()
root.update()
check('未导入任何数据', not app.bodyplans and not app.waterlines)

print()
print('OFFSET IMPORT TEST %s' % ('PASS' if ok else 'FAIL'))
root.destroy()