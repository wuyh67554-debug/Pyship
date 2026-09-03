# -*- coding: utf-8 -*-
import os as _os
import sys as _sys
_sys.path.insert(0, _os.path.dirname(_os.path.dirname(_os.path.abspath(__file__))))
"""验证：3D 蒙皮显示降采样（面片数/质量档位）与邦戎综合视图 X 轴=站位"""
import tkinter as tk
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


# ================= 1. 3D 蒙皮降采样 =================
print('=' * 60)
print('1. 3D 蒙皮显示降采样')
print('=' * 60)
app.Lpp, app.Breadth, app.Depth = 100.0, 12.0, 8.0
app.LppStartStation, app.LppEndStation = 0.0, 10.0
st = np.linspace(0, 10, 11)
rows = [[i + 1, float(s), '%.3f' % (6 * np.sin(np.pi * s / 10)), '', '']
        for i, s in enumerate(st)]
app.waterlines = [{'type': 'waterline', 'name': 'WL0', 'height': 0.0,
                   'table': {'columns': ['列', '站号', '半宽'], 'rows': rows}},
                  {'type': 'waterline', 'name': 'WL4', 'height': 4.0,
                   'table': {'columns': ['列', '站号', '半宽'], 'rows': rows}}]
app.bodyplans = []
z = np.linspace(0, 6, 7)
app.sections = {}
for s in [0.0, 5.0, 10.0]:
    y = np.clip(6 * np.sin(np.pi * s / 10) * (1 - (z / 6.0) ** 2 * 0.6), 0, None)
    app.sections[float(s)] = {'Y': y.tolist(), 'Z': z.tolist()}
    app.bodyplans.append({'type': 'bodyplan', 'name': '站 %g' % s, 'station': float(s),
                          'table': {'columns': ['列', '高度', '半宽'],
                                    'rows': [[i + 1, float(z[i]), float(y[i])]
                                             for i in range(len(z))]}})

# 标准质量
app.var_mesh_quality.set('标准')
app.gen_hull_clicked()
full_faces = app.SurfaceGenerationData['Faces']
check('全精度面片已存储（STL 用）', len(full_faces) > 5000,
      '实际 %d' % len(full_faces))
disp_faces = app.SurfaceGenerationData['display_faces']
check('显示面片数远小于全精度', disp_faces < len(full_faces) / 2,
      '显示 %d / 全精度 %d' % (disp_faces, len(full_faces)))
check('显示面片数在合理范围（<4000）', 200 < disp_faces < 4000,
      '实际 %d' % disp_faces)

# 流畅质量更少
app.var_mesh_quality.set('流畅')
app.gen_hull_clicked()
disp_faces_fast = app.SurfaceGenerationData['display_faces']
check('流畅档面片更少', disp_faces_fast < disp_faces,
      '流畅 %d / 标准 %d' % (disp_faces_fast, disp_faces))

# 精细档更多
app.var_mesh_quality.set('精细')
app.gen_hull_clicked()
disp_faces_fine = app.SurfaceGenerationData['display_faces']
check('精细档面片更多', disp_faces_fine > disp_faces,
      '精细 %d / 标准 %d' % (disp_faces_fine, disp_faces))

# STL 仍是全精度
check('STL 导出仍用全精度面片', len(app.SurfaceGenerationData['Faces']) == len(full_faces))

# ================= 2. 邦戎综合视图 X 轴 =站号/站位 =================
print()
print('=' * 60)
print('2. 邦戎综合视图 X 轴')
print('=' * 60)
app.var_bonjean_min.set(0.0)
app.var_bonjean_max.set(4.0)
app.var_bonjean_steps.set(9)
app.var_bonjean_all.set(True)
app.calc_bonjean_clicked()

p = app.bonjean_plots['综合图']
xlabel = p.ax.get_xlabel()
check('综合图 X 轴为站位纵向位置', '纵向位置' in xlabel and 'm' in xlabel,
      xlabel)
lines = p.ax.get_lines()
check('综合图已绘制曲线', len(lines) >= 4, '实际 %d' % len(lines))
# 站号标注（text 对象）
texts = [t.get_text() for t in p.ax.texts]
check('综合图有站号标注', any('站' in t for t in texts), str(texts))
# 曲线 X 数据应围绕站位（0 和 50/100 或船中为0的位置），而非面积量级
if lines:
    xdata = np.concatenate([np.asarray(l.get_xdata()) for l in lines])
    xdata = xdata[np.isfinite(xdata)]
    check('曲线 X 数据为站位坐标量级（不直接是面积）',
          np.all(np.abs(xdata) < 200), 'max|x|=%.1f' % np.max(np.abs(xdata)))

print()
print('3D/BONJEAN TEST %s' % ('PASS' if ok else 'FAIL'))
root.destroy()
