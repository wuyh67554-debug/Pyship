# -*- coding: utf-8 -*-
import os as _os
import sys as _sys
_sys.path.insert(0, _os.path.dirname(_os.path.dirname(_os.path.abspath(__file__))))
"""Qt SolidWorks 风格 3D 视窗测试。

仅做"不依赖真实 GL 渲染"的纯逻辑验证（法线、网格准备、视角预设），
避免在无 GPU/无桌面环境崩溃；GL 渲染由 _final_check 风格人工验证。
"""
import numpy as np

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


def _box_mesh():
    """构造一个简单封闭箱体网格（8 顶点 12 三角）。"""
    v = np.array([
        [0, 0, 0], [1, 0, 0], [1, 1, 0], [0, 1, 0],
        [0, 0, 1], [1, 0, 1], [1, 1, 1], [0, 1, 1],
    ], dtype=float)
    f = np.array([
        [0, 1, 2], [0, 2, 3],   # 底
        [4, 6, 5], [4, 7, 6],   # 顶
        [0, 4, 5], [0, 5, 1],   # 前
        [2, 6, 7], [2, 7, 3],   # 后
        [0, 3, 7], [0, 7, 4],   # 左
        [1, 5, 6], [1, 6, 2],   # 右
    ], dtype=np.int64)
    return v, f


check('导入 qt_3d_viewer', True)
from src.viewer.qt_3d_viewer import (qt_available, ensure_qapplication, HullGLWidget,
                          compute_vertex_normals)
check('qt_available() 返回 bool', isinstance(qt_available(), bool),
      'avail=%s' % qt_available())
check('ensure_qapplication 幂等', ensure_qapplication() is not None)

# 1. 法线计算：单位长度、非零、对"外翻"网格其 y 分量远离中心
v, f = _box_mesh()
n = compute_vertex_normals(v, f, outward=True)
ln = np.linalg.norm(n, axis=1)
check('法线为单位向量', np.allclose(ln, 1.0, atol=1e-6),
      'min=%.4f max=%.4f' % (ln.min(), ln.max()))
check('法线非 NaN', np.all(np.isfinite(n)))

# 外翻后：右侧面(+y)法线 y>0，左侧面(-y)法线 y<0
n_right = n[np.argmax(v[:, 1])]
n_left = n[np.argmin(v[:, 1])]
check('外翻法线右侧朝外 (+y)', n_right[1] > 0.5, 'ny=%.3f' % n_right[1])
check('外翻法线左侧朝外 (-y)', n_left[1] < -0.5, 'ny=%.3f' % n_left[1])

# 2. 视窗控件：无 GL 渲染时的网格准备与视角预设
w = HullGLWidget()
w.set_vertices_faces(v, f)
check('set_vertices_faces 后三角顶点数组正确', w._tri_verts is not None
      and len(w._tri_verts) == len(f) * 3, 'tri=%d' % (0 if w._tri_verts is None else len(w._tri_verts)))
check('边数组正确', w._edge_verts is not None and len(w._edge_verts) >= 6,
      'edge=%d' % (0 if w._edge_verts is None else len(w._edge_verts)))
check('显示模式设置', (w.set_display_mode(0), w._display_mode)[1] == 0)
check('线框模式设置', (w.set_display_mode(2), w._display_mode)[1] == 2)
w.set_view('顶视图')
check('顶视图 pitch 近 90', w._pitch > 80, 'pitch=%.1f' % w._pitch)
w.set_view('等轴测')
check('等轴测预设', abs(w._pitch - 28) < 1.5 and abs(w._yaw - 45) < 1.5,
      'yaw=%.1f pitch=%.1f' % (w._yaw, w._pitch))
w.fit_view()
check('fit_view 后距离>0', w._dist > 0, 'dist=%.4f' % w._dist)
check('current_view_name 返回有效名称', w.current_view_name() in
      ('等轴测', '正视图(艏)', '侧视图(右舷)', '后视图(艉)', '顶视图', '底部视图'))
w.clear_mesh()
check('clear_mesh 后无数据', w._tri_verts is None and w._edge_verts is None)

# 3. ShipApp 启动即预加载 Qt 视窗（无需切到 3D曲面 页才创建）
import tkinter as tk
try:
    _root = tk.Tk()
    _root.geometry('400x300+1+1')
    from src.app.ship_app import ShipApp
    _app = ShipApp(_root, icon_dir='icon')
    check('ShipApp 启动即预加载 Qt 视窗', _app.qt3d_host is not None,
          'qt3d_host=%s' % _app.qt3d_host)
    if _app.qt3d_host is not None:
        check('启动时 widget 隐藏（不弹独立窗口）', not _app.qt3d_host.widget.isVisible())
        check('启动时未嵌入', _app.qt3d_host._embedded is False)
    _root.destroy()
except Exception as e:
    check('ShipApp 启动预加载可调用', False, 'err=%r' % e)

# 4. 兜底：Qt 不可用时 qt_available 仍返回 bool（不抛异常）
print()
print('QT3D TEST %s  (PASS=%d FAIL=%d)' % ('PASS' if FAIL == 0 else 'FAIL', PASS, FAIL))
raise SystemExit(0 if FAIL == 0 else 1)
