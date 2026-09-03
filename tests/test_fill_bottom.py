# -*- coding: utf-8 -*-
import os as _os
import sys as _sys
_sys.path.insert(0, _os.path.dirname(_os.path.dirname(_os.path.abspath(__file__))))
"""验证"补齐底部"：点云/二维线/蒙皮面三处协同（仿 MATLAB Button_FillBottomPointsClicked）"""
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


# ================= 构造船体（船底未闭合：最低点 Z=0 处半宽>0） =================
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
app.bodyplans = []
app.sections = {}
for s in st:
    y = 6.0 * np.sin(np.pi * s / 10) * (1 - (np.linspace(0, 6, 7) / 6.0) ** 2 * 0.6)
    app.sections[float(s)] = {'Y': y.tolist(), 'Z': np.linspace(0, 6, 7).tolist()}
    app.bodyplans.append({'type': 'bodyplan', 'name': '站 %g' % s, 'station': float(s),
                          'table': {'columns': ['列', '高度', '半宽'],
                                    'rows': [[i + 1, float(np.linspace(0, 6, 7)[i]), float(y[i])]
                                             for i in range(7)]}})

# ================= 1. 点云 =================
print('=' * 60)
print('1. 点云补齐底部')
print('=' * 60)
app.gen_pointcloud_clicked()
sd = app.SurfaceGenerationData
n_before = len(sd['HalfPoints'])
check('初始点云已生成', n_before > 0)
check('初始无 BottomPoints', 'BottomPoints' not in sd or len(sd['BottomPoints']) == 0)

app.fill_bottom_points()
sd = app.SurfaceGenerationData
bp = sd.get('BottomPoints')
check('补齐后新增底部点', bp is not None and len(bp) > 0,
      '实际 %d' % (0 if bp is None else len(bp)))
check('HalfPoints 增加', len(sd['HalfPoints']) > n_before,
      '%d -> %d' % (n_before, len(sd['HalfPoints'])))

# 底部点：每站 Z = 该站最低 Z（此处为 0），Y ∈ [0, minY]
if bp is not None and len(bp):
    unique_x = np.unique(bp[:, 0])
    all_ok = True
    for xb in unique_x:
        seg = bp[np.abs(bp[:, 0] - xb) < 1e-6]
        zs = seg[:, 2]
        ys = seg[:, 1]
        if not (np.all(np.abs(zs - zs[0]) < 1e-9)):      # 同一站 Z 恒定
            all_ok = False
        if not (np.min(ys) <= 1e-6):                      # 含中线 y=0
            all_ok = False
        if not (np.max(ys) > 0):                          # 延伸至最低点半宽
            all_ok = False
    check('每站底部点：Z 恒定、含 y=0、延伸至最低点半宽', all_ok)

# 镜像完整性
ap = sd['AllPoints']
check('AllPoints 镜像对称', np.allclose(np.sort(ap[:, 1]), np.sort(-ap[:, 1])))
check('AllPoints 数量不少于镜像前', len(ap) >= len(sd['HalfPoints']))

# 点云视图标题（原始红 + 底部蓝）
check('点云视图标题含"补齐底部"', '补齐底部' in app.plot_face_area.ax.get_title(),
      app.plot_face_area.ax.get_title())

# ================= 2. 二维线（型线视图含底部） =================
print()
print('=' * 60)
print('2. 二维线（型线）')
print('=' * 60)
app.gen_lines_clicked()
colors = [l.get_color() for l in app.plot_face_area.ax.get_lines()]
check('型线视图包含绿色底部/龙骨线', any(c == 'g' for c in colors),
      str(sorted(set(colors))))

# ================= 3. 蒙皮面 =================
print()
print('=' * 60)
print('3. 蒙皮面')
print('=' * 60)
app.var_mesh_quality.set('流畅')
app.gen_hull_clicked()
check('补齐底部后蒙皮仍可生成', app.SurfaceGenerationData.get('display_faces', 0) > 0,
      '显示面片 %d' % app.SurfaceGenerationData.get('display_faces', 0))
# 蒙皮数据网格应覆盖到底部 z=minZ（底部点参与插值）
grid = app.SurfaceGenerationData.get('grid')
check('蒙皮网格已存储', grid is not None)
if grid is not None:
    zmin_grid = float(np.min(grid[2]))
    check('蒙皮网格延伸到底部(Z≈0)', zmin_grid <= 0.01, 'zmin=%.3f' % zmin_grid)

# 边界曲面封底验证：mesh 顶点含 y=0 龙骨点；至少有一些面片引用龙骨点
verts = app.SurfaceGenerationData.get('Vertices')
faces = app.SurfaceGenerationData.get('Faces')
keel_mask = verts[:, 1] <= 0.001
check('网格含龙骨点 (y≈0)', int(np.sum(keel_mask)) > 0,
      '龙骨点 %d' % int(np.sum(keel_mask)))
if faces is not None and np.any(keel_mask):
    used = np.unique(faces.ravel())
    keel_used = np.intersect1d(used, np.nonzero(keel_mask)[0])
    cap_faces = np.any(np.isin(faces, keel_used), axis=1)
    check('至少 100 个封底三角带引用龙骨点', int(np.sum(cap_faces)) >= 100,
          '封底面片 %d' % int(np.sum(cap_faces)))

# ================= 4. 重复补齐：底部已闭合则提示无需补齐 =================
print()
print('=' * 60)
print('4. 重复补齐')
print('=' * 60)
before = len(app.SurfaceGenerationData['HalfPoints'])
app.fill_bottom_points()
after = len(app.SurfaceGenerationData['HalfPoints'])
check('重复补齐不再增加点（已闭合）', after == before,
      'before %d / after %d' % (before, after))

print()
print('FILL BOTTOM TEST %s' % ('PASS' if ok else 'FAIL'))
root.destroy()
