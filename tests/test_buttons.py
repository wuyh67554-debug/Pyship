# -*- coding: utf-8 -*-
import os as _os
import sys as _sys
_sys.path.insert(0, _os.path.dirname(_os.path.dirname(_os.path.abspath(__file__))))
"""验证工具栏按钮 enable 状态与 MATLAB 一致"""
import tkinter as tk
from tkinter import messagebox

for _fn in ('showinfo', 'showwarning', 'showerror', 'askyesno'):
    setattr(messagebox, _fn, lambda *a, **k: True)

from src.ui import ui_widgets
ui_widgets.ask_text_dialog = lambda *a, **k: ''
ui_widgets.ask_numeric_dialog = lambda *a, **k: None
ui_widgets.ask_multi_select = lambda *a, **k: [1]
ui_widgets.ask_multiline_input = lambda *a, **k: ''
from src.core import ship_app_actions
ship_app_actions.ask_text_dialog = ui_widgets.ask_text_dialog
ship_app_actions.ask_numeric_dialog = ui_widgets.ask_numeric_dialog
ship_app_actions.ask_multi_select = ui_widgets.ask_multi_select
ship_app_actions.ask_multiline_input = ui_widgets.ask_multiline_input

root = tk.Tk()
root.withdraw()
from src.app.ship_app import ShipApp
app = ShipApp(root, icon_dir='icon')
root.update()

tb = app.tool_buttons

def state(name):
    s = tb[name].cget('state')
    return 'normal' if str(s) == 'normal' else 'disabled'

# 创建一个表格节点并选中（用于特征提取按钮测试）
import os, tempfile
tmp = tempfile.mkdtemp()
csv_path = os.path.join(tmp, 'test.csv')
with open(csv_path, 'w', encoding='utf-8') as f:
    f.write('a,b,c\n1,2,3\n4,5,6\n')
headers, rows = app._read_table_file(csv_path)
filled = app.fill_merged_cells(rows)
h2, d2 = app.extract_header_and_data(headers, filled)
node = app._tree_add(app.table_root, 'test.csv',
                     {'type': 'table', 'Data': d2, 'Headers': h2, 'VariableNames': h2})
app.tree.selection_set(node)
root.update()

# 期望矩阵：每个 Tab 下各按钮的 enable 状态
# 与 MATLAB 各 TabButtonDown 一致
expect = {
    1: {  # Tab_2ButtonDown (调试/原表格): 编辑类 disabled，主尺度/模型/导入/锁定 可用
        '导入表格': 'normal', '模型': 'normal', '特征提取': 'normal',
        '主尺度': 'normal', '锁定': 'normal',
        '站号': 'disabled', '半宽': 'disabled', '系数': 'disabled', '矩臂': 'disabled',
        '对称': 'disabled', '拟合': 'disabled', '删列': 'disabled',
        '分段': 'disabled', '计算': 'disabled', '增行': 'disabled', '删行': 'disabled',
    },
    2: {  # 半宽: 所有编辑类 enabled
        '导入表格': 'normal', '模型': 'normal', '特征提取': 'normal', '主尺度': 'normal',
        '锁定': 'normal',
        '站号': 'normal', '半宽': 'normal', '系数': 'normal', '矩臂': 'normal',
        '对称': 'normal', '拟合': 'normal', '删列': 'normal',
        '分段': 'normal', '计算': 'normal', '增行': 'normal', '删行': 'normal',
    },
    3: {  # 横剖面: 仅 对称 enabled（MATLAB Tab_3ButtonDown 行为）
        '导入表格': 'normal', '模型': 'normal', '主尺度': 'normal', '锁定': 'normal',
        '特征提取': 'normal',
        '站号': 'disabled', '半宽': 'disabled', '系数': 'disabled', '矩臂': 'disabled',
        '对称': 'normal', '拟合': 'disabled', '删列': 'disabled',
        '分段': 'disabled', '计算': 'disabled', '增行': 'disabled', '删行': 'disabled',
    },
    4: {  # 3D曲面: 编辑类 disabled（Tab4 内部按钮独立）
        '导入表格': 'normal', '模型': 'normal', '主尺度': 'normal', '锁定': 'normal',
        '特征提取': 'normal',
        '站号': 'disabled', '半宽': 'disabled', '系数': 'disabled', '矩臂': 'disabled',
        '对称': 'disabled', '拟合': 'disabled', '删列': 'disabled',
        '分段': 'disabled', '计算': 'disabled', '增行': 'disabled', '删行': 'disabled',
    },
    5: {  # 浮心: 编辑类 disabled
        '导入表格': 'normal', '模型': 'normal', '主尺度': 'normal', '锁定': 'normal',
        '特征提取': 'normal',
        '站号': 'disabled', '半宽': 'disabled', '系数': 'disabled', '矩臂': 'disabled',
        '对称': 'disabled', '拟合': 'disabled', '删列': 'disabled',
        '分段': 'disabled', '计算': 'disabled', '增行': 'disabled', '删行': 'disabled',
    },
}

ok_all = True
for tab_idx, expected in expect.items():
    app.notebook.select(tab_idx - 1)  # 0-based
    root.update()
    for name, exp_state in expected.items():
        actual = state(name)
        if actual != exp_state:
            print('FAIL Tab%d 按钮[%s] 期望=%s 实际=%s' % (tab_idx, name, exp_state, actual))
            ok_all = False
print()
print('BUTTON EN EN 测试 %s' % ('PASS' if ok_all else 'FAIL'))
root.destroy()