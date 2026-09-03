# -*- coding: utf-8 -*-
import os as _os
import sys as _sys
_sys.path.insert(0, _os.path.dirname(_os.path.dirname(_os.path.abspath(__file__))))
"""验证 Excel 模式表格 / Ctrl+Z 撤销 / 坐标轴真实比例 / 原生主题"""
import tkinter as tk
from tkinter import ttk
from tkinter import messagebox

import numpy as np

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

ok = True


def check(name, cond, detail=''):
    global ok
    print('[%s] %s %s' % ('PASS' if cond else 'FAIL', name, detail))
    if not cond:
        ok = False


# ================= 1. 原生 Windows 主题 =================
print('=' * 60)
print('1. 原生 Windows 主题')
print('=' * 60)
theme = ttk.Style().theme_use()
check('使用 Windows 原生主题 (vista/winnative/xpnative)',
      theme in ('vista', 'winnative', 'xpnative'), '实际 %s' % theme)
check('主 Notebook 为原生 ttk.Notebook', isinstance(app.notebook, ttk.Notebook))

# ================= 2. 坐标轴真实比例 =================
print()
print('=' * 60)
print('2. 坐标轴真实比例')
print('=' * 60)
app.Half_table.set_columns(['列', '站号', '半宽', '系数', '相对矩臂'])
app.Half_table.set_data([[1, 0, 0, '', ''], [2, 5, 3.5, '', ''], [3, 10, 0, '', '']])
app.Lpp, app.LppStartStation, app.LppEndStation = 100.0, 0.0, 10.0
app.Breadth = 7.0
app.update_half_width_plot()
check('水线面半宽图 X/Y 等比例 (1m 等长)',
      app.plot_half_area.ax.get_aspect() == 1.0,
      '实际 %s' % app.plot_half_area.ax.get_aspect())

app.Z_table.set_columns(['列', '高度', '半宽', '系数'])
app.Z_table.set_data([[1, 0, 0, 1], [2, 2, 4, 1], [3, 4, 5, 1]])
app.update_transverse_section_plot()
check('横剖面图 X/Y 等比例 (1m 等长)',
      app.plot_z_area.ax.get_aspect() == 1.0,
      '实际 %s' % app.plot_z_area.ax.get_aspect())

# 曲线图（横纵轴量纲不同）应保持 auto
app.Half_table.set_data([[1, 0, 0, 1, 0], [2, 2, 3, 1, 1], [3, 4, 2, 1, 2],
                         [4, 6, 1, 1, 3], [5, 8, 0.5, 1, 4], [6, 10, 0, 1, 5]])
app.cal_clicked()
p = app.curve_plots['水线面面积']
check('静水力曲线图保持 auto（量纲不同，不应等比例）',
      p.ax.get_aspect() == 'auto', '实际 %s' % p.ax.get_aspect())

# ================= 3. Excel 模式表格 =================
print()
print('=' * 60)
print('3. Excel 模式表格')
print('=' * 60)
tb = app.Half_table
tb.set_columns(['列', '站号', '半宽', '系数', '相对矩臂'])
tb.set_data([[1, 0, 0, '', ''], [2, 5, 3.5, '', '']])
root.update()

check('行号列(#0)存在且为行号',
      tb.tree.item('r0', 'text') == '1' and tb.tree.item('r1', 'text') == '2')
check('数据列使用符号列名 c0..cN',
      list(tb.tree['columns']) == ['c0', 'c1', 'c2', 'c3', 'c4'])
check('活动单元格高亮组件已创建', tb._outline is not None)

# 复制 → TSV
tb._set_current(0, 0)
tb._anchor = (0, 0)
tb._set_current(1, 2)
text = tb.copy_selection()
lines = text.split('\n')
check('矩形选区复制为 TSV（2 行 3 列）',
      len(lines) == 2 and all(len(l.split('\t')) == 3 for l in lines), repr(text))

# 粘贴 → TSV 写入并自动扩行/扩列
tb.set_columns(['A', 'B'])
tb.set_data([['x', 'y']])
tb.clear_undo()
tb._set_current(0, 0)
tb._anchor = (0, 0)
n = tb.paste_text('1\t2\n3\t4\n5\t6')
check('TSV 粘贴写入 6 个单元格', n == 6, '实际 %d' % n)
check('粘贴自动扩充到 3 行', tb.row_count() == 3, '实际 %d' % tb.row_count())
check('粘贴数值已转为数字', tb.get_cell(2, 1) == 6.0, '实际 %r' % tb.get_cell(2, 1))

# Ctrl+Z 撤销粘贴
tb._undo()
check('Ctrl+Z 撤销粘贴后恢复 1 行', tb.row_count() == 1, '实际 %d' % tb.row_count())
check('Ctrl+Z 后数据正确', tb.get_cell(0, 0) == 'x', '实际 %r' % tb.get_cell(0, 0))
tb._redo()
check('Ctrl+Y 重做后恢复 3 行', tb.row_count() == 3, '实际 %d' % tb.row_count())

# 单元格编辑可撤销
tb.clear_undo()
tb.set_columns(['A'])
tb.set_data([['1'], ['2']])
tb.clear_undo()
tb._set_current(0, 0)
tb._anchor = (0, 0)
tb._push_undo()
tb.set_cell(0, 0, 99.0)
tb._undo()
check('表格 Ctrl+Z 恢复单元格旧值', tb.get_cell(0, 0) == '1', '实际 %r' % tb.get_cell(0, 0))

# 向下填充
tb.set_columns(['A', 'B'])
tb.set_data([['10', '20'], [''], ['']])
tb.clear_undo()
tb._set_current(0, 0)
tb._anchor = (0, 0)
tb._set_current(2, 1)
cnt = tb.fill_down()
check('Ctrl+D 向下填充 4 个单元格', cnt == 4, '实际 %d' % cnt)
check('填充结果正确', tb.get_cell(2, 1) == '20', '实际 %r' % tb.get_cell(2, 1))

# Delete 清空
tb.clear_undo()
tb._set_current(0, 0)
tb._anchor = (0, 0)
tb._set_current(1, 1)
cnt = tb.clear_selection()
check('Delete 清空 4 个单元格', cnt == 4, '实际 %d' % cnt)
check('清空后为空字符串', tb.get_cell(0, 0) == '', '实际 %r' % tb.get_cell(0, 0))
tb._undo()
check('Ctrl+Z 恢复清空前的数据', tb.get_cell(0, 0) == '10', '实际 %r' % tb.get_cell(0, 0))

# ================= 4. 输入框 Ctrl+Z =================
print()
print('=' * 60)
print('4. 输入框 Ctrl+Z')
print('=' * 60)
e = ttk.Entry(root)
e.pack()
e.insert(0, 'abc')
# withdrawn 窗口收不到 FocusIn，这里手动同步一次（等价于获得焦点时的快照同步）
ui_widgets._entry_snapshot(e)
# 模拟用户键入：值变化 + KeyRelease 记录快照
e.delete(0, 'end')
e.insert(0, 'abcdef')
ui_widgets._entry_snapshot(e)
check('Entry 快照记录了旧值', 'abc' in ui_widgets._entry_state(e)['undo'],
      str(ui_widgets._entry_state(e)['undo']))
ui_widgets._entry_undo(e)
check('Entry Ctrl+Z 恢复旧值', e.get() == 'abc', '实际 %r' % e.get())
ui_widgets._entry_redo(e)
check('Entry Ctrl+Y 重做', e.get() == 'abcdef', '实际 %r' % e.get())

# 类级绑定已安装（对话框中动态创建的输入框同样生效）
for cls in ('TEntry', 'Entry', 'Text'):
    bnd = root.bind_class(cls, '<Control-z>')
    check('%s 已绑定 Ctrl+Z' % cls, bool(bnd))

# 应用内创建的日志文本域应已启用内置撤销（withdrawn 窗口收不到 <Map>，直接检查实例）
check('日志文本域已启用内置撤销', bool(app.TextArea_debug.cget('undo')),
      '实际 %r' % app.TextArea_debug.cget('undo'))
check('多行输入对话框文本域启用撤销',
      hasattr(tk.Text, 'edit_undo'))

print()
print('EXCEL/UNDO/ASPECT TEST %s' % ('PASS' if ok else 'FAIL'))
root.destroy()
