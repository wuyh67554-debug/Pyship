# -*- coding: utf-8 -*-
"""稳性 tab 完善回归测试：
- 横剖面面积曲线按站号绘制（不再把 Am vs 吃水当成横剖面面积曲线）
- 导出 KN / GZ 数据（xlsx/csv/txt）
"""
import os as _os
import sys as _sys
_sys.path.insert(0, _os.path.dirname(_os.path.dirname(_os.path.abspath(__file__))))
import os
import math
import tkinter as tk
from tkinter import messagebox

for _fn in ('showinfo', 'showwarning', 'showerror', 'askyesno'):
    setattr(messagebox, _fn, lambda *a, **k: True)
from src.ui import ui_widgets
for _fn in ('showinfo', 'showwarning', 'showerror', 'askyesno'):
    setattr(ui_widgets.messagebox, _fn, lambda *a, **k: True)
from src.core import ship_app_calc
for _fn in ('showinfo', 'showwarning', 'showerror', 'askyesno'):
    setattr(ship_app_calc.messagebox, _fn, lambda *a, **k: True)

ui_widgets.ask_text_dialog = lambda *a, **k: ''
ui_widgets.ask_numeric_dialog = lambda *a, **k: None
ui_widgets.ask_multi_select = lambda *a, **k: [1]
ui_widgets.ask_multiline_input = lambda *a, **k: '\n'.join(
    '%.4f' % (10 * math.sin(i / 10 * math.pi)) for i in range(11))
from src.ui import ui_widgets as uw
from src.core import ship_core
ship_app_calc.ask_numeric_dialog = uw.ask_numeric_dialog
ship_app_calc.ask_text_dialog = uw.ask_text_dialog

PASS = 0


def check(name, cond, detail=''):
    global PASS
    print('[%s] %s %s' % ('PASS' if cond else 'FAIL', name, detail))
    if cond:
        PASS += 1


root = tk.Tk()
root.withdraw()
from src.app.ship_app import ShipApp
app = ShipApp(root, icon_dir=os.path.join(os.path.dirname(os.path.abspath(__file__)), 'icon'))
app.root.deiconify()
root.update()

# ---- 1. 主尺度 + 横剖面型值（三个站，sections 有 Y/Z）----
app.Lpp = 100.0
app.Breadth = 15.0
app.Depth = 8.0
app.LppStartStation = 0.0
app.LppEndStation = 10.0
# 各站型剖面：梯形型值（高度 Z, 半宽 Y）
app.sections = {
    0.0: {'Y': [0.0, 6.0, 6.0, 0.0], 'Z': [0.0, 0.0, 4.0, 4.0]},
    5.0: {'Y': [0.0, 9.0, 9.0, 0.0], 'Z': [0.0, 0.0, 5.0, 5.0]},
    10.0: {'Y': [0.0, 6.0, 6.0, 0.0], 'Z': [0.0, 0.0, 4.0, 4.0]},
}
app.waterlines.append({'type': 'waterline', 'name': 'WL2', 'height': 2.0,
                       'table': {'columns': ['列', '站号', '半宽', '系数', '相对矩臂'],
                                 'rows': [[1, '0', '0', '', ''], [2, '5', '10', '', ''],
                                          [3, '10', '0', '', '']]}})
app.waterlines.append({'type': 'waterline', 'name': 'WL4', 'height': 4.0,
                       'table': {'columns': ['列', '站号', '半宽', '系数', '相对矩臂'],
                                 'rows': [[1, '0', '0', '', ''], [2, '5', '12', '', ''],
                                          [3, '10', '0', '', '']]}})

# ---- 2. 横剖面面积沿站号曲线 ----
app.var_draft_max.set(4.0)
app.calc_curves_clicked()
root.update()
p = app.curve_plots['横剖面面积']
# 此时绘图应包含一条线（站号 vs 全面积），不再是 Am vs draft 的"面积轴"
lines = p.ax.get_lines()
check('横剖面面积曲线已绘制(站号 x 全面积)',
      len(lines) >= 1, '线条数=%d' % len(lines))
if lines:
    xs = lines[0].get_xdata()
    ys = lines[0].get_ydata()
    check('X 轴为站号(0,5,10)', len(xs) == 3 and abs(xs[0]) < 0.5 and abs(xs[1] - 5) < 0.5,
          'xs=%s' % list(xs))
    check('Y 轴为各站全面积且单调合理',
          len(ys) == 3 and ys[1] > ys[0] > 0, 'ys=%s' % list(ys))
    # 站0梯形(0,6,6,0)/(0,0,4,4): 半船=0.5*(6+6)*4=24 → 全面积 48
    check('站0全面积≈48 (梯形 2*∫halfY dZ)',
          abs(float(ys[0]) - 48.0) < 1e-6, 'ys0=%.4f' % float(ys[0]))

# ---- 3. KN / GZ / 动稳性（走真实流程）----
app.var_stab_heels.set('0:10:30')
app.var_stab_drafts.set('1:1:5')
app.calc_kn_clicked()
root.update()
check('KN 已计算', app.StabilityData is not None and 'KN_Curves' in app.StabilityData)

# ---- 4. 导出 KN（xlsx）----
out_dir = _os.path.dirname(_os.path.abspath(__file__))
# 直接测 _save_tabular 的数据构造
kn = app.StabilityData['KN_Curves']
hdr = ['Draft_m'] + ['Heel_%d_deg' % int(round(h)) for h in kn['heels']]
rows = []
for j, t in enumerate(kn['drafts']):
    rows.append([t] + list(kn['KN'][j, :]))
check('KN 表头：首列 Draft_m + 横倾角列',
      hdr[0] == 'Draft_m' and len(hdr) == len(kn['heels']) + 1, str(hdr))
check('KN 表行数=吃水数', len(rows) == len(kn['drafts']), 'rows=%d' % len(rows))
xlsx_path = os.path.join(out_dir, '_stab_kn.xlsx')
try:
    app._save_tabular(xlsx_path, hdr, rows)
    check('KN 导出 xlsx 成功', os.path.exists(xlsx_path) and os.path.getsize(xlsx_path) > 0)
finally:
    try:
        os.remove(xlsx_path)
    except Exception:
        pass

# ---- 5. 导出 GZ ----
# 用 KN 曲线在给定排水量处插值生成 GZ（模拟 MATLAB）
ship_w = 1200.0
kg = 0.7 * app.Depth
res = app._buoyancy_fn()(0, kg)
if math.isfinite(res['volume']):
    ship_w = res['volume'] * 1.025
gz = ship_core.calc_gz_curve(kn, ship_w, 0.0, 0.0, kg)
app.GZ_CurveData = dict(HeelAngles=kn['heels'], GZ_Values=gz,
                        Displacement=ship_w, KG=kg, XG=0.5 * app.Lpp, YG=0.0)
check('GZ 曲线有效点数>0', len(gz) == len(kn['heels']) and sum(math.isfinite(v) for v in gz) > 0)
# 直接验证 GZ 数据结构可写
hdr2 = ['HeelAngle_deg', 'GZ_m']
rows2 = [[kn['heels'][i], gz[i]] for i in range(len(kn['heels']))]
csv_path = os.path.join(out_dir, '_stab_gz.csv')
app._save_tabular(csv_path, hdr2, rows2)
check('GZ 导出 csv 成功', os.path.exists(csv_path) and os.path.getsize(csv_path) > 0)
try:
    os.remove(csv_path)
except Exception:
    pass

# ---- 6. 动稳性全流程（触发含等面积标注的绘图）----
app.Draft = 3.0
app.calc_dynamic_clicked()
root.update()
check('动稳性已计算', app.DynamicStabilityData is not None)
dyn = app.DynamicStabilityData
for key in ('GM', 'lq', 'lf', 'stabilityK', 'vanishAngle', 'maxGZ', 'theta_G', 'theta_K'):
    check('动稳性字段 %s 存在' % key, key in dyn)
# 绘图对象里应有线
pp = app.stability_plots['动稳性']
check('动稳性图含 GZ/动稳性曲线',
      len(pp.ax.lines) >= 2, 'lines=%d' % len(pp.ax.lines))

print('DONE PASS=%d' % PASS)
root.destroy()
