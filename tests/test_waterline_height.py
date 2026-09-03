# -*- coding: utf-8 -*-
import os as _os
import sys as _sys
_sys.path.insert(0, _os.path.dirname(_os.path.dirname(_os.path.abspath(__file__))))
"""验证水线高度输入的严格校验（识别后必须输入、非法输入拒绝、导入前再校验）"""
import tkinter as tk
from tkinter import messagebox

import numpy as np

for _fn in ('showinfo', 'showwarning', 'showerror', 'askyesno'):
    setattr(messagebox, _fn, lambda *a, **k: True)

from src.ui import ui_widgets
ui_widgets.ask_multi_select = lambda *a, **k: [1]
ui_widgets.ask_numeric_dialog = lambda *a, **k: None
ui_widgets.ask_multiline_input = lambda *a, **k: ''
from src.core import ship_app_actions
ship_app_actions.ask_multi_select = ui_widgets.ask_multi_select
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


# ---------- 1. _ask_waterline_height 的严格校验 ----------
print('=' * 60)
print('1. 水线高度输入校验')
print('=' * 60)
# 序列：非数字 -> 负数 -> 与已有重复 -> 合法
app._askyesno_answers = []
seq = iter(['abc', '-3', '2.5', '2.5', '4.0'])
ship_app_actions.ask_text_dialog = lambda *a, **k: next(seq)
v = app._ask_waterline_height('WL1', 0.0, [2.5])
check('非法/负数/重复输入被拒绝，最终接受合法值', v == 4.0, '实际 %r' % v)

# 留空 -> 确认中止 -> 返回 None
ship_app_actions.ask_text_dialog = lambda *a, **k: ''
v = app._ask_waterline_height('WL1', 0.0, [])
check('留空并确认中止返回 None', v is None, '实际 %r' % v)

# 留空 -> 拒绝中止(askyesno=False) -> 继续输入 -> 合法
answers = iter([False])
ship_app_actions.messagebox.askyesno = lambda *a, **k: next(answers)
seq = iter(['', '1.5'])
ship_app_actions.ask_text_dialog = lambda *a, **k: next(seq)
v = app._ask_waterline_height('WL1', 0.0, [])
check('留空但拒绝中止时继续要求输入', v == 1.5, '实际 %r' % v)
ship_app_actions.messagebox.askyesno = lambda *a, **k: True

# ---------- 2. 识别后必须输入高度：取消则中止，不生成识别结果 ----------
print()
print('=' * 60)
print('2. 特征提取后强制输入水线高度')
print('=' * 60)


class _StubModel:
    def predict(self, X):
        # 模型输出的是粗角色 station/z/half；half_wl 由角色修正对话框确定
        return np.array(['station', 'half', 'half'], dtype=object)


from src.core import ml_utils
app.ML_model = {'model': _StubModel(),
                'required_variables': list(ml_utils.DEFAULT_FEATURES),
                'kind': 'Python'}
app._ask_roles_dialog = lambda names, roles: ['station', 'half_wl', 'half_wl']

rows = [[i + 1, 1000.0 * i, 2000.0 * i] for i in range(10)]
node = app._tree_add(app.table_root, 'tbl', {
    'type': 'table', 'Data': rows, 'VariableNames': ['s', 'wl1', 'wl2']})
n_result_before = sum(1 for c in app.tree.get_children('')
                      for d in app.tree.get_children(c)
                      if app.tree_meta.get(d, {}).get('type') == 'result')

# 2a. 用户在水线高度处取消 -> 整个识别中止
ship_app_actions.ask_text_dialog = lambda *a, **k: None
app.tree.selection_set(node)
app.extract_clicked()
root.update()
n_result_after = sum(1 for c in app.tree.get_children('')
                     for d in app.tree.get_children(c)
                     if app.tree_meta.get(d, {}).get('type') == 'result')
check('取消高度输入 -> 不生成"识别结果"节点（中止）',
      n_result_after == n_result_before, '前后 %d/%d' % (n_result_before, n_result_after))

# 2b. 正常输入 -> 生成识别结果，高度已写入且无 NaN
_height_seq = iter(['0', '2'])
ship_app_actions.ask_text_dialog = lambda *a, **k: next(_height_seq)
app.tree.selection_set(node)
app.extract_clicked()
root.update()
sel = app._selected_node()
meta = app.tree_meta.get(sel, {})
hv = meta.get('heightValues')
check('正常输入后生成"识别结果"节点', meta.get('type') == 'result')
check('两条水线高度分别为 0 和 2',
      hv is not None and hv[1] == 0.0 and hv[2] == 2.0, str(hv))
check('高度值中不再有 NaN',
      hv is not None and not any(np.isnan(hv[i]) for i in range(len(hv))
                                 if app.tree_meta[sel]['Roles'][i] == 'half_wl'))

# ---------- 3. 高度缺失时导入被拦截 ----------
print()
print('=' * 60)
print('3. 高度缺失时导入拦截')
print('=' * 60)
app.waterlines.clear()
bad_node = app._tree_add(app.table_root, 'bad_result', {
    'type': 'result', 'Roles': ['station', 'half_wl'],
    'UserNames': ['站号列', '水线半宽'],
    'Data': [[0, 0], [1, 1000], [2, 2000]],
    'Numeric': np.array([[0, 0], [1, 1000], [2, 2000]], dtype=float),
    'heightValues': np.array([np.nan, np.nan])})
app.tree.selection_set(bad_node)
app.isTap = 2
app.import_from_offset_clicked()
root.update()
check('高度为 NaN 时水线导入被拦截（未生成水线）', len(app.waterlines) == 0,
      '实际 %d' % len(app.waterlines))

# 补齐高度后（编辑水线高度）可正常导入
_edit_seq = iter(['1.5'])
ship_app_actions.ask_text_dialog = lambda *a, **k: next(_edit_seq)
app.tree.selection_set(bad_node)
app.edit_waterline_heights_clicked()
app.tree.selection_set(bad_node)
app.import_from_offset_clicked()
root.update()
check('补齐高度后导入成功', len(app.waterlines) == 1, '实际 %d' % len(app.waterlines))
if app.waterlines:
    check('导入的水线高度为 1.5 m', app.waterlines[0]['height'] == 1.5,
          '实际 %r' % app.waterlines[0]['height'])

# ---------- 4. 横剖面：全部水线高度缺失且无甲板列时被拦截 ----------
print()
print('=' * 60)
print('4. 横剖面导入拦截')
print('=' * 60)
app.bodyplans.clear()
app.sections.clear()
# 全新节点：高度全 NaN、无甲板列 —— 横剖面必然一个点都没有
nan_node = app._tree_add(app.table_root, 'nan_result', {
    'type': 'result', 'Roles': ['station', 'half_wl'],
    'UserNames': ['站号列', '水线半宽'],
    'Data': [[0, 0], [1, 1000], [2, 2000]],
    'Numeric': np.array([[0, 0], [1, 1000], [2, 2000]], dtype=float),
    'heightValues': np.array([np.nan, np.nan])})
app.tree.selection_set(nan_node)
app.isTap = 3
app.import_from_offset_clicked()
root.update()
check('水线高度全缺失且无甲板列时横剖面导入被拦截',
      len(app.bodyplans) == 0, '实际 %d' % len(app.bodyplans))

print()
print('WATERLINE HEIGHT TEST %s' % ('PASS' if ok else 'FAIL'))
root.destroy()
