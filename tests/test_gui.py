# -*- coding: utf-8 -*-
import os as _os
import sys as _sys
_sys.path.insert(0, _os.path.dirname(_os.path.dirname(_os.path.abspath(__file__))))
"""GUI 冒烟测试：创建应用 → 设置主尺度 → 快速站号 → 计算 → 关闭"""
import os
import math
import tkinter as tk
from tkinter import messagebox

# 自动应答所有模态对话框，避免测试阻塞
for _fn in ('showinfo', 'showwarning', 'showerror', 'askyesno'):
    setattr(messagebox, _fn, lambda *a, **k: True)
from src.ui import ui_widgets
for _fn in ('showinfo', 'showwarning', 'showerror', 'askyesno'):
    setattr(ui_widgets.messagebox, _fn, lambda *a, **k: True)
from src.core import ship_app_actions
for _fn in ('showinfo', 'showwarning', 'showerror', 'askyesno'):
    setattr(ship_app_actions.messagebox, _fn, lambda *a, **k: True)
from src.core import ship_app_calc
for _fn in ('showinfo', 'showwarning', 'showerror', 'askyesno'):
    setattr(ship_app_calc.messagebox, _fn, lambda *a, **k: True)

# 自动应答自定义对话框
ui_widgets.ask_text_dialog = lambda *a, **k: '0:10:1'   # 站号 / 拟合配置等
ui_widgets.ask_numeric_dialog = lambda *a, **k: None    # GZ 参数取消
ui_widgets.ask_multi_select = lambda *a, **k: [1]
ui_widgets.ask_multiline_input = lambda *a, **k: '\n'.join(
    '%.4f' % (10 * math.sin(i / 10 * math.pi)) for i in range(11))
# 更新 actions/calc 模块中引用的对话框
from src.ui import ui_widgets as uw
ship_app_actions.ask_text_dialog = uw.ask_text_dialog
ship_app_actions.ask_numeric_dialog = uw.ask_numeric_dialog
ship_app_actions.ask_multi_select = uw.ask_multi_select
ship_app_actions.ask_multiline_input = uw.ask_multiline_input
ship_app_calc.ask_numeric_dialog = uw.ask_numeric_dialog
ship_app_calc.ask_text_dialog = uw.ask_text_dialog

root = tk.Tk()
root.withdraw()  # 隐藏主窗口进行测试

from src.app.ship_app import ShipApp

app = ShipApp(root, icon_dir=os.path.join(os.path.dirname(os.path.abspath(__file__)), 'icon'))
app.root.deiconify()
root.update()

# 1. 设置主尺度
app.Lpp = 100.0
app.Breadth = 15.0
app.Depth = 8.0
app.LppStartStation = 0.0
app.LppEndStation = 10.0
print('OK 主尺度设置')

# 2. 快速站号
app.Half_table.set_columns(['列', '站号', '半宽', '系数', '相对矩臂'])
rows = [[i + 1, str(i), '', '', ''] for i in range(11)]
app.Half_table.set_data(rows)
print('OK 站号生成')

# 3. 半宽（二次形状）
for i in range(11):
    v = 10 * math.sin(i / 10 * math.pi)
    app.Half_table.set_cell(i, 2, '%.4f' % v)
app.update_half_width_plot()
root.update()
print('OK 半宽+绘图')

# 4. 添加系数（梯形）
app.add_coefficient_clicked()  # 会弹 messagebox... 需要处理
root.update()
print('OK 系数')

# 5. 矩臂
app.OriginFlag = 'amidship'
app.add_moment_arm_clicked()
root.update()
print('OK 矩臂')

# 6. 水线面计算
app.cal_clicked()
root.update()
print('OK 水线面计算')

# 7. 曲线拟合
app.curve_fitting_clicked()
root.update()
print('OK 曲线拟合')

# 8. 横剖面
app.Z_table.set_columns(['列', '高度', '半宽', '系数'])
app.Z_table.set_data([[1, '0', '0', '1'], [2, '2', '8', '1'], [3, '4', '9', '1'], [4, '6', '5', '1']])
app.calc_transverse_section_clicked()
root.update()
print('OK 横剖面')

# 9. 浮心（水线面法）
app.var_draft.set(3.0)
app.waterlines.append({'type': 'waterline', 'name': 'WL2', 'height': 2.0,
                       'table': {'columns': ['列', '站号', '半宽', '系数', '相对矩臂'],
                                 'rows': [[1, '0', '0', '', ''], [2, '5', '10', '', ''], [3, '10', '0', '', '']]}})
app.waterlines.append({'type': 'waterline', 'name': 'WL4', 'height': 4.0,
                       'table': {'columns': ['列', '站号', '半宽', '系数', '相对矩臂'],
                                 'rows': [[1, '0', '0', '', ''], [2, '5', '12', '', ''], [3, '10', '0', '', '']]}})
app.buoyancy_calc_clicked()
root.update()
print('OK 浮心')

# 10. 静水力曲线
app.var_draft_max.set(4.0)
app.calc_curves_clicked()
root.update()
print('OK 静水力曲线')

# 11. 邦戎曲线
app.sections[0] = {'Y': [0, 8, 8, 0], 'Z': [0, 0, 6, 6]}
app.calc_bonjean_clicked()
root.update()
print('OK 邦戎曲线')

# 12. KN / GZ / 动稳性
app.var_stab_heels.set('0:10:90')
app.var_stab_drafts.set('1:1:5')
app.calc_kn_clicked()
root.update()
print('OK KN')
app.calc_gz_clicked()
root.update()
print('OK GZ')
app.calc_dynamic_clicked()
root.update()
print('OK 动稳性')

# 13. 3D
app.gen_pointcloud_clicked()
root.update()
app.gen_lines_clicked()
root.update()
app.gen_hull_clicked()
root.update()
print('OK 3D')

print('GUI 冒烟测试全部完成')
root.destroy()
