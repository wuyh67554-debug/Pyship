# -*- coding: utf-8 -*-
"""SOLIDWORKS 风格 Qt 3D 曲面视窗。

技术路线：
- PyQt5.QOpenGLWidget + opengl32.dll 固定管线 GL（兼容 profile 4.x），
  不依赖 Qt3D 模块、不需要 GLSL 着色器，普通显卡/远程桌面/软渲染均可用；
- 客户端顶点数组 (glVertexPointer + glDrawArrays) 一次性提交网格，
  90k 顶点毫秒级绘制，旋转流畅；
- 轨道相机：左键旋转 / 中键(或Shift+左键)平移 / 滚轮缩放 / 双击适合；
- SOLIDWORKS 风格：渐变背景、地面网格、双方向光 + 高光材质、坐标轴、
  实体 / 实体+边缘 / 纯线框 三种显示模式；
- 通过 Windows SetParent 把 QOpenGLWidget 嵌入 tkinter 页面，
  用 tk.after 事件泵驱动 Qt 重绘。
"""

import math
import os
import ctypes
import functools
import numpy as np

from src.viewer import glc

_QT_OK = False
try:
    from PyQt5.QtCore import Qt
    from PyQt5.QtGui import QSurfaceFormat
    from PyQt5.QtWidgets import QApplication, QOpenGLWidget
    _QT_OK = True
except Exception:  # pragma: no cover
    _QT_OK = False

# 环境变量可关闭 Qt 3D（测试/无桌面环境用）
_ENABLED = _QT_OK and not os.environ.get('SCS_DISABLE_QT3D', '').strip().lower() in ('1', 'true', 'yes', 'on')

_QT_APP = None

# 当前激活的 Qt3DHost（一般为单例）；文件对话框 guard 用它暂停事件泵
_ACTIVE_HOST = None

# 已安装 tkinter.filedialog 防护的标志（避免重复包装）
_FILE_DIALOG_GUARDED = False


def _set_active_host(host):
    """记录当前激活的 Qt3DHost（供文件对话框防护暂停事件泵）。"""
    global _ACTIVE_HOST
    _ACTIVE_HOST = host


def qt_available():
    return _ENABLED


def pause_active_qt():
    """暂停当前激活 Qt 3D 事件泵（弹原生文件对话框前调用）。"""
    h = _ACTIVE_HOST
    if h is not None:
        try:
            h.pause()
        except Exception:
            pass


def resume_active_qt():
    """恢复当前激活 Qt 3D 事件泵（文件对话框关闭后调用）。"""
    h = _ACTIVE_HOST
    if h is not None:
        try:
            h.resume()
        except Exception:
            pass


def install_file_dialog_guard():
    """给 tkinter.filedialog 的 ask* 系列统一加 Qt 泵暂停防护。

    Windows 原生文件对话框是 COM/OLE 模态循环，若嵌入式 Qt 3D 视窗的
    tk.after 事件泵仍在 processEvents，会触发 0x8001010d
    (RPC_E_SERVERCALL_RETRYLATER) 重入崩溃。这里在弹框期间暂停泵。
    """
    global _FILE_DIALOG_GUARDED
    if _FILE_DIALOG_GUARDED:
        return
    _FILE_DIALOG_GUARDED = True
    try:
        import tkinter.filedialog as _fd

        def _wrap(fn):
            @functools.wraps(fn)
            def _guarded(*args, **kwargs):
                pause_active_qt()
                try:
                    return fn(*args, **kwargs)
                finally:
                    resume_active_qt()
            return _guarded

        for _name in ('askopenfilename', 'asksaveasfilename', 'askdirectory',
                      'askopenfilenames', 'askopenfile', 'asksaveasfile'):
            if hasattr(_fd, _name):
                try:
                    setattr(_fd, _name, _wrap(getattr(_fd, _name)))
                except Exception:
                    pass
    except Exception:
        pass


def ensure_qapplication():
    """确保全局唯一 QApplication；返回 None 表示不可用。"""
    global _QT_APP
    if not _ENABLED:
        return None
    if _QT_APP is None or QApplication.instance() is None:
        try:
            QApplication.setAttribute(Qt.AA_ShareOpenGLContexts, True)
            fmt = QSurfaceFormat()
            fmt.setDepthBufferSize(24)
            fmt.setVersion(3, 3)
            fmt.setProfile(QSurfaceFormat.CompatibilityProfile)
            QSurfaceFormat.setDefaultFormat(fmt)
            _QT_APP = QApplication(['scs_qt3d'])
        except Exception:
            _QT_APP = None
    return _QT_APP


def compute_vertex_normals(verts, faces, outward=True):
    """按三角形面积加权累计的顶点法线（smooth shading）。

    outward=True（默认）时取反方向——对"船体网格（绕轴侧 + 边界封底）"
    这种法线从标准叉积会指向内部的情况，强制让法线指向外部，
    配合 Phong 材质就能让光照落在可见表面上，呈现真实立体感。
    """
    v = verts[faces]
    cr = np.cross(v[:, 1] - v[:, 0], v[:, 2] - v[:, 0])
    if outward:
        cr = -cr
    n = np.zeros_like(verts)
    np.add.at(n, faces[:, 0], cr)
    np.add.at(n, faces[:, 1], cr)
    np.add.at(n, faces[:, 2], cr)
    ln = np.linalg.norm(n, axis=1, keepdims=True)
    ln[ln < 1e-12] = 1.0
    return n / ln


def _unique_edges(faces):
    """从三角面片提取去重后的边索引 (E,2)。"""
    f = np.asarray(faces)
    e = np.concatenate([f[:, [0, 1]], f[:, [1, 2]], f[:, [2, 0]]])
    e = np.sort(e, axis=1)
    e = np.unique(e, axis=0)
    return e


class HullGLWidget(QOpenGLWidget):
    """SOLIDWORKS 风格船体 3D 渲染控件。"""

    # 显示模式
    SOLID = 0        # 实体曲面
    SOLID_EDGES = 1  # 实体 + 边缘
    WIREFRAME = 2    # 纯线框

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setMouseTracking(True)
        self.setMinimumSize(200, 200)

        # ---- 相机 ----
        self._target = np.zeros(3)
        self._yaw = 45.0
        self._pitch = 28.0
        self._dist = 12.0
        self._fov = 32.0
        self._near = 0.02
        self._far = 10000.0

        # ---- 模型 ----
        self._verts = None
        self._faces = None
        self._tri_verts = None      # (M*3,3) float32
        self._tri_normals = None    # (M*3,3) float32
        self._edge_verts = None     # (E*2,3) float32
        self._paint_count = 0
        self._fit_pending = False
        self._bounds = None

        # ---- 外观 ----
        self._display_mode = self.SOLID_EDGES
        self._show_grid = True
        self._show_axes = True
        self._hull_color = (0.18, 0.42, 0.78)      # 工业深蓝（船体涂装，保持色饱和）
        self._bg_style = 'dark'
        self._bg_top = (0.40, 0.43, 0.48)
        self._bg_bottom = (0.10, 0.12, 0.16)
        self._grid_color = (0.55, 0.58, 0.65, 0.35)
        # ---- 显示层开关（点云 / 型线 / 蒙皮）----
        self._show_pointcloud = True
        self._show_lines = True
        self._show_hull = True

        # ---- 点云 / 型线覆盖层 ----
        self._points = None
        self._points_color = (1.0, 0.15, 0.15)
        self._points_size = 2.0
        self._line_groups = []

        # ---- 交互 ----
        self._last_pos = None
        self._panning = False
        self._invert_rotate = False
        self._invert_zoom = False
        self._invert_pan = False

    # ================= 外观 / 交互偏好 =================

    def set_background_style(self, style):
        """背景风格：dark / gray / light。"""
        styles = {
            'dark': ((0.40, 0.43, 0.48), (0.10, 0.12, 0.16)),
            'gray': ((0.60, 0.62, 0.66), (0.34, 0.36, 0.40)),
            'light': ((0.92, 0.93, 0.95), (0.74, 0.76, 0.80)),
        }
        if style in styles:
            self._bg_style = style
            self._bg_top, self._bg_bottom = styles[style]
            self.update()

    def set_layer_visible(self, layer, on):
        """切换显示层：pointcloud / lines / hull。"""
        on = bool(on)
        if layer == 'pointcloud':
            self._show_pointcloud = on
        elif layer == 'lines':
            self._show_lines = on
        elif layer == 'hull':
            self._show_hull = on
        else:
            return
        self.update()

    def set_hull_color(self, color):
        """修改蒙皮颜色。color: (r, g, b)，各分量 0~1。"""
        try:
            r, g, b = color
            self._hull_color = (float(r), float(g), float(b))
            self.update()
        except Exception:
            pass

    def set_mouse_invert(self, invert_rotate=False, invert_zoom=False, invert_pan=False):
        """反转鼠标操作：旋转方向 / 滚轮缩放方向 / 中键平移方向。"""
        self._invert_rotate = bool(invert_rotate)
        self._invert_zoom = bool(invert_zoom)
        self._invert_pan = bool(invert_pan)

    def set_pointcloud(self, points, color=(1.0, 0.15, 0.15), size=2.0):
        """设置点云覆盖层（GL_POINTS）。"""
        pts = np.asarray(points, dtype=np.float32)
        if pts.ndim != 2 or pts.shape[1] != 3 or pts.shape[0] == 0:
            self._points = None
        else:
            self._points = np.ascontiguousarray(pts)
        self._points_color = tuple(color)
        self._points_size = float(size)
        self.update()

    def set_lines(self, line_groups):
        """设置型线覆盖层（GL_LINES）。

        line_groups: [(segments (N,2,3) 或 (2*N,3), (r,g,b), width), ...]
        """
        groups = []
        for segs, color, width in line_groups:
            s = np.asarray(segs, dtype=np.float32)
            if s.ndim == 2 and s.shape[1] == 3:
                s = s.reshape(-1, 3)
            if s.ndim == 3 and s.shape[1:] == (2, 3):
                s = s.reshape(-1, 3)
            if s.ndim == 2 and s.shape[1] == 3 and s.shape[0] >= 2:
                groups.append((np.ascontiguousarray(s), tuple(color), float(width)))
        self._line_groups = groups
        self.update()

    def clear_overlays(self):
        self._points = None
        self._line_groups = []
        self.update()

    # ================= 对外接口 =================

    def set_vertices_faces(self, verts, faces):
        """设置网格并准备 GL 顶点数组；自动适合视图。"""
        verts = np.asarray(verts, dtype=np.float64)
        faces = np.asarray(faces, dtype=np.int64)
        if verts.ndim != 2 or faces.ndim != 2 or verts.shape[1] != 3 or faces.shape[1] < 3:
            return
        self._verts = verts
        self._faces = faces
        tri = verts[faces].reshape(-1, 3)
        norms = compute_vertex_normals(verts, faces, outward=True)
        tri_n = norms[faces].reshape(-1, 3)
        edges = _unique_edges(faces)
        edge_v = verts[edges].reshape(-1, 3)
        self._tri_verts = np.ascontiguousarray(tri, dtype=np.float32)
        self._tri_normals = np.ascontiguousarray(tri_n, dtype=np.float32)
        self._edge_verts = np.ascontiguousarray(edge_v, dtype=np.float32)
        self._bounds = (verts.min(axis=0), verts.max(axis=0))
        if self._paint_count == 0:
            self._fit_pending = True
        else:
            self._fit()
            self.update()

    def clear_mesh(self):
        self._verts = self._faces = None
        self._tri_verts = self._tri_normals = self._edge_verts = None
        self.update()

    def set_display_mode(self, mode):
        if mode in (self.SOLID, self.SOLID_EDGES, self.WIREFRAME):
            self._display_mode = mode
            self.update()

    def set_show_grid(self, on):
        self._show_grid = bool(on)
        self.update()

    def set_show_axes(self, on):
        self._show_axes = bool(on)
        self.update()

    def fit_view(self):
        self._fit()
        self.update()

    def set_view(self, name):
        """视角预设：等轴测 / 正视图(艏) / 侧视图(右舷) / 后视图(艉) / 顶视图 / 底部视图"""
        presets = {
            '等轴测': (45.0, 28.0),
            '正视图(艏)': (0.0, 0.0),
            '侧视图(右舷)': (90.0, 0.0),
            '后视图(艉)': (180.0, 0.0),
            '顶视图': (45.0, 89.0),
            '底部视图': (45.0, -89.0),
        }
        if name in presets:
            self._yaw, self._pitch = presets[name]
            self.update()

    def current_view_name(self):
        for name, (y, p) in {
            '等轴测': (45.0, 28.0),
            '正视图(艏)': (0.0, 0.0),
            '侧视图(右舷)': (90.0, 0.0),
            '后视图(艉)': (180.0, 0.0),
            '顶视图': (45.0, 89.0),
            '底部视图': (45.0, -89.0),
        }.items():
            if abs(self._yaw - y) < 1.5 and abs(self._pitch - p) < 1.5:
                return name
        return '等轴测'

    # ================= 相机 =================

    def _eye(self):
        yaw = math.radians(self._yaw)
        pitch = math.radians(self._pitch)
        d = self._dist
        return self._target + d * np.array([
            math.cos(pitch) * math.cos(yaw),
            math.cos(pitch) * math.sin(yaw),
            math.sin(pitch),
        ])

    def _view_matrix(self):
        eye = self._eye()
        f = self._target - eye
        nf = np.linalg.norm(f)
        f = f / nf if nf > 1e-12 else np.array([0.0, 0.0, -1.0])
        up = np.array([0.0, 0.0, 1.0])
        s = np.cross(f, up)
        ns = np.linalg.norm(s)
        s = s / ns if ns > 1e-12 else np.array([1.0, 0.0, 0.0])
        u = np.cross(s, f)
        return np.array([
            [s[0], s[1], s[2], -np.dot(s, eye)],
            [u[0], u[1], u[2], -np.dot(u, eye)],
            [-f[0], -f[1], -f[2], np.dot(f, eye)],
            [0.0, 0.0, 0.0, 1.0],
        ])

    def _fit(self):
        if self._verts is None or self._verts.shape[0] < 3:
            return
        lo, hi = self._bounds
        c = (lo + hi) / 2.0
        r = float(np.max(hi - lo) / 2.0) or 1.0
        self._target = c.astype(float)
        self._dist = r / math.tan(math.radians(self._fov) / 2.0) * 1.45
        self._near = max(r * 1e-4, 0.001)
        self._far = r * 200.0

    # ================= Qt 回调 =================

    def initializeGL(self):
        glc.enable(glc.GL_DEPTH_TEST)
        glc.depthFunc(glc.GL_LEQUAL)
        glc.enable(glc.GL_NORMALIZE)
        glc.shadeModel(glc.GL_SMOOTH)
        glc.hint(glc.GL_PERSPECTIVE_CORRECTION_HINT, glc.GL_NICEST)
        # 双面光照：无论网格绕序如何，两侧都按各自法线方向正确着色；
        # 同时设置全局环境光避免阴影面过黑。
        glc.lightModelfv(glc.GL_LIGHT_MODEL_TWO_SIDE, glc.farr([1.0]))
        glc.lightModelfv(glc.GL_LIGHT_MODEL_AMBIENT, glc.farr([0.30, 0.30, 0.32]))

    def resizeGL(self, w, h):
        glc.viewport(0, 0, max(w, 1), max(h, 1))

    def paintGL(self):
        try:
            self._render()
        except Exception:
            import traceback
            traceback.print_exc()

    # ================= 渲染 =================

    def _render(self):
        self._paint_count += 1
        if self._fit_pending and self._verts is not None:
            self._fit()
            self._fit_pending = False
        w = max(self.width(), 1)
        h = max(self.height(), 1)
        glc.viewport(0, 0, w, h)
        self._draw_background()
        glc.enable(glc.GL_DEPTH_TEST)
        self._apply_projection(w, h)
        glc.matrixMode(glc.GL_MODELVIEW)
        glc.loadIdentity()
        glc.loadMatrixf(glc.farr(self._view_matrix().T.ravel()))
        self._setup_lights()
        if self._show_grid:
            self._draw_grid()
        # 型线在网格之后、实体之前绘制，避免被实体大面积遮挡
        if self._show_lines:
            self._draw_line_groups()
        if self._show_hull:
            self._draw_hull()
        if self._show_pointcloud:
            self._draw_pointcloud()
        if self._show_axes:
            self._draw_axes()
        glc.flush()

    def _draw_pointcloud(self):
        if self._points is None or len(self._points) < 1:
            return
        glc.disable(glc.GL_LIGHTING)
        glc.pointSize(self._points_size)
        glc.color3f(*self._points_color)
        vp = self._points.ctypes.data_as(ctypes.c_void_p)
        glc.enableClientState(glc.GL_VERTEX_ARRAY)
        glc.vertexPointer(3, glc.GL_FLOAT, 0, vp)
        glc.drawArrays(glc.GL_POINTS, 0, len(self._points))
        glc.disableClientState(glc.GL_VERTEX_ARRAY)

    def _draw_line_groups(self):
        if not self._line_groups:
            return
        glc.disable(glc.GL_LIGHTING)
        for verts, color, width in self._line_groups:
            glc.lineWidth(width)
            glc.color3f(*color)
            vp = verts.ctypes.data_as(ctypes.c_void_p)
            glc.enableClientState(glc.GL_VERTEX_ARRAY)
            glc.vertexPointer(3, glc.GL_FLOAT, 0, vp)
            glc.drawArrays(glc.GL_LINES, 0, len(verts))
            glc.disableClientState(glc.GL_VERTEX_ARRAY)

    def _draw_background(self):
        """垂直渐变背景（SOLIDWORKS 风格）。"""
        glc.disable(glc.GL_DEPTH_TEST)
        glc.disable(glc.GL_LIGHTING)
        glc.matrixMode(glc.GL_PROJECTION)
        glc.loadIdentity()
        glc.ortho(-1.0, 1.0, -1.0, 1.0, -1.0, 1.0)
        glc.matrixMode(glc.GL_MODELVIEW)
        glc.loadIdentity()
        glc.shadeModel(glc.GL_SMOOTH)
        t = self._bg_top
        b = self._bg_bottom
        glc.begin(glc.GL_TRIANGLE_STRIP)
        glc.color3f(*t); glc.vertex3f(-1.0, 1.0, 0.0)
        glc.color3f(*t); glc.vertex3f(1.0, 1.0, 0.0)
        glc.color3f(*b); glc.vertex3f(-1.0, -1.0, 0.0)
        glc.color3f(*b); glc.vertex3f(1.0, -1.0, 0.0)
        glc.end()

    def _apply_projection(self, w, h):
        aspect = w / float(h)
        top = self._near * math.tan(math.radians(self._fov) / 2.0)
        right = top * aspect
        glc.matrixMode(glc.GL_PROJECTION)
        glc.loadIdentity()
        glc.frustum(-right, right, -top, top, self._near, self._far)

    def _setup_lights(self):
        glc.enable(glc.GL_LIGHTING)
        # 主光（前上方）
        glc.lightfv(glc.GL_LIGHT0, glc.GL_POSITION, glc.farr([0.5, 0.7, 1.0, 0.0]))
        glc.lightfv(glc.GL_LIGHT0, glc.GL_AMBIENT, glc.farr([0.20, 0.20, 0.22]))
        glc.lightfv(glc.GL_LIGHT0, glc.GL_DIFFUSE, glc.farr([0.55, 0.55, 0.55]))
        glc.lightfv(glc.GL_LIGHT0, glc.GL_SPECULAR, glc.farr([0.40, 0.40, 0.42]))
        glc.enable(glc.GL_LIGHT0)
        # 补光（背向低强度，压暗背光面）
        glc.lightfv(glc.GL_LIGHT1, glc.GL_POSITION, glc.farr([-0.7, -0.4, -0.6, 0.0]))
        glc.lightfv(glc.GL_LIGHT1, glc.GL_AMBIENT, glc.farr([0.0, 0.0, 0.0]))
        glc.lightfv(glc.GL_LIGHT1, glc.GL_DIFFUSE, glc.farr([0.25, 0.25, 0.28]))
        glc.lightfv(glc.GL_LIGHT1, glc.GL_SPECULAR, glc.farr([0.08, 0.08, 0.08]))
        glc.enable(glc.GL_LIGHT1)

    def _draw_grid(self):
        """地面网格（z=0 平面，贴合船体底面水平面）。"""
        if self._bounds is None:
            return
        lo, hi = self._bounds
        cx = (lo[0] + hi[0]) / 2.0
        cy = (lo[1] + hi[1]) / 2.0
        r = max(hi[0] - lo[0], hi[1] - lo[1], hi[2] - lo[2]) * 0.6 or 5.0
        z = float(lo[2])
        glc.disable(glc.GL_LIGHTING)
        glc.enable(glc.GL_BLEND)
        glc.blendFunc(glc.GL_SRC_ALPHA, glc.GL_ONE_MINUS_SRC_ALPHA)
        glc.color4f(*self._grid_color)
        glc.lineWidth(1.0)
        n = 12
        glc.begin(glc.GL_LINES)
        for i in range(n + 1):
            t = -r + 2 * r * i / n
            glc.vertex3f(cx - r, cy + t, z); glc.vertex3f(cx + r, cy + t, z)
            glc.vertex3f(cx + t, cy - r, z); glc.vertex3f(cx + t, cy + r, z)
        glc.end()
        # 中心轴线更亮
        glc.color4f(0.70, 0.72, 0.78, 0.55)
        glc.begin(glc.GL_LINES)
        glc.vertex3f(cx - r, cy, z); glc.vertex3f(cx + r, cy, z)
        glc.vertex3f(cx, cy - r, z); glc.vertex3f(cx, cy + r, z)
        glc.end()
        glc.disable(glc.GL_BLEND)

    def _draw_hull(self):
        if self._tri_verts is None or len(self._tri_verts) < 3:
            return
        mode = self._display_mode
        if mode in (self.SOLID, self.SOLID_EDGES):
            self._draw_triangles(filled=True)
        if mode == self.SOLID_EDGES:
            self._draw_edges()
        elif mode == self.WIREFRAME:
            self._draw_wireframe()

    def _draw_triangles(self, filled):
        n = len(self._tri_verts)
        glc.enable(glc.GL_LIGHTING)
        c = self._hull_color
        glc.materialfv(glc.GL_FRONT_AND_BACK, glc.GL_AMBIENT, glc.farr([c[0] * 0.45, c[1] * 0.45, c[2] * 0.48]))
        glc.materialfv(glc.GL_FRONT_AND_BACK, glc.GL_DIFFUSE, glc.farr([c[0], c[1], c[2]]))
        glc.materialfv(glc.GL_FRONT_AND_BACK, glc.GL_SPECULAR, glc.farr([0.70, 0.70, 0.74]))
        glc.materialfv(glc.GL_FRONT_AND_BACK, glc.GL_SHININESS, glc.farr([48.0]))
        glc.materialfv(glc.GL_FRONT_AND_BACK, glc.GL_EMISSION, glc.farr([0.0, 0.0, 0.0, 1.0]))
        glc.polygonMode(glc.GL_FRONT_AND_BACK, glc.GL_FILL if filled else glc.GL_LINE)
        glc.disable(glc.GL_CULL_FACE)
        vp = self._tri_verts.ctypes.data_as(ctypes.c_void_p)
        np_ = self._tri_normals.ctypes.data_as(ctypes.c_void_p)
        glc.enableClientState(glc.GL_VERTEX_ARRAY)
        glc.enableClientState(glc.GL_NORMAL_ARRAY)
        glc.vertexPointer(3, glc.GL_FLOAT, 0, vp)
        glc.normalPointer(glc.GL_FLOAT, 0, np_)
        glc.drawArrays(glc.GL_TRIANGLES, 0, n)
        glc.disableClientState(glc.GL_VERTEX_ARRAY)
        glc.disableClientState(glc.GL_NORMAL_ARRAY)
        glc.polygonMode(glc.GL_FRONT_AND_BACK, glc.GL_FILL)

    def _draw_wireframe(self):
        glc.disable(glc.GL_LIGHTING)
        glc.lineWidth(1.0)
        n = len(self._tri_verts)
        vp = self._tri_verts.ctypes.data_as(ctypes.c_void_p)
        glc.enableClientState(glc.GL_VERTEX_ARRAY)
        glc.vertexPointer(3, glc.GL_FLOAT, 0, vp)
        glc.polygonMode(glc.GL_FRONT_AND_BACK, glc.GL_LINE)
        glc.drawArrays(glc.GL_TRIANGLES, 0, n)
        glc.polygonMode(glc.GL_FRONT_AND_BACK, glc.GL_FILL)
        glc.disableClientState(glc.GL_VERTEX_ARRAY)

    def _draw_edges(self):
        """实体之上的棱边（SOLIDWORKS 高光边缘风格）。"""
        if self._edge_verts is None or len(self._edge_verts) < 2:
            return
        glc.disable(glc.GL_LIGHTING)
        glc.enable(glc.GL_POLYGON_OFFSET_LINE)
        glc.polygonOffset(1.0, 1.0)
        glc.lineWidth(1.0)
        glc.color3f(0.10, 0.11, 0.13)
        n = len(self._edge_verts)
        vp = self._edge_verts.ctypes.data_as(ctypes.c_void_p)
        glc.enableClientState(glc.GL_VERTEX_ARRAY)
        glc.vertexPointer(3, glc.GL_FLOAT, 0, vp)
        glc.drawArrays(glc.GL_LINES, 0, n)
        glc.disableClientState(glc.GL_VERTEX_ARRAY)
        glc.disable(glc.GL_POLYGON_OFFSET_LINE)

    def _draw_axes(self):
        """模型原点坐标轴（X=红 Y=绿 Z=蓝），长度取模型尺寸 12%。"""
        if self._bounds is None:
            return
        lo, hi = self._bounds
        r = float(max(hi - lo)) * 0.12 or 1.0
        o = np.array([lo[0] - r * 0.2, lo[1] - r * 0.2, lo[2] - r * 0.2])
        glc.disable(glc.GL_LIGHTING)
        glc.lineWidth(2.0)
        glc.begin(glc.GL_LINES)
        for axis, col in ((0, (0.85, 0.25, 0.25)), (1, (0.25, 0.75, 0.25)), (2, (0.30, 0.45, 0.95))):
            e = o.copy()
            e[axis] += r
            glc.color3f(*col)
            glc.vertex3f(*o)
            glc.vertex3f(*e)
        glc.end()

    # ================= 鼠标交互 =================

    def mousePressEvent(self, e):
        if e.button() == Qt.LeftButton or e.button() == Qt.MiddleButton:
            self._last_pos = (e.x(), e.y())
            self._panning = (e.button() == Qt.MiddleButton) or \
                            (e.button() == Qt.LeftButton and bool(e.modifiers() & Qt.ShiftModifier))
        elif e.button() == Qt.RightButton:
            self._last_pos = None

    def mouseMoveEvent(self, e):
        if self._last_pos is None:
            return
        dx = e.x() - self._last_pos[0]
        dy = e.y() - self._last_pos[1]
        self._last_pos = (e.x(), e.y())
        if self._panning:
            # 平移方向由独立的“平移方向反转”控制（中键拖动）
            if self._invert_pan:
                dx, dy = -dx, -dy
            self._pan(dx, dy)
        else:
            if self._invert_rotate:
                dx, dy = -dx, -dy
            self._yaw = (self._yaw + dx * 0.35) % 360.0
            self._pitch = max(-89.0, min(89.0, self._pitch - dy * 0.35))
        self.update()

    def mouseReleaseEvent(self, e):
        self._last_pos = None
        self._panning = False

    def mouseDoubleClickEvent(self, e):
        self.fit_view()

    def wheelEvent(self, e):
        delta = e.angleDelta().y()
        if delta:
            zoom_in = delta > 0
            if self._invert_zoom:
                zoom_in = not zoom_in
            self._dist *= 0.88 if zoom_in else 1.12
            self._dist = min(max(self._dist, 1e-3), 1e7)
            self.update()
        e.accept()

    def keyPressEvent(self, e):
        super().keyPressEvent(e)

    def _pan(self, dx, dy):
        w = max(self.width(), 1)
        h = max(self.height(), 1)
        top = self._dist * math.tan(math.radians(self._fov) / 2.0)
        scale = 2.0 * top / float(h)
        eye = self._eye()
        f = self._target - eye
        nf = np.linalg.norm(f)
        f = f / nf if nf > 1e-12 else np.array([0.0, 0.0, -1.0])
        up = np.array([0.0, 0.0, 1.0])
        s = np.cross(f, up)
        ns = np.linalg.norm(s)
        s = s / ns if ns > 1e-12 else np.array([1.0, 0.0, 0.0])
        u = np.cross(s, f)
        self._target = self._target - s * (dx * scale) + u * (dy * scale)


class Qt3DHost:
    """把 Qt GL 视窗嵌入 tkinter 帧（Windows SetParent + tk 事件泵）。"""

    def __init__(self, tk_host):
        self._tk_host = tk_host
        if not _ENABLED:
            raise RuntimeError('Qt 3D 不可用')
        ensure_qapplication()
        self.widget = HullGLWidget()
        self.widget.resize(600, 400)
        self.widget.setWindowFlags(Qt.Tool | Qt.FramelessWindowHint)
        # 先显示以尽早建立 GL 上下文（预加载），随后若宿主尚未映射
        # （如启动时 3D曲面 页未选中）则隐藏，避免弹出独立 Qt 窗口；
        # 切到 3D曲面 页触发 <Map> 嵌入时再显示。
        self.widget.show()
        self._embedded = False
        self._pump_active = False
        # 事件泵暂停计数：文件对话框/模态对话框可多层嵌套暂停，避免提前恢复
        self._pump_pause_depth = 0
        tk_host.bind('<Map>', self._on_map, add='+')
        tk_host.bind('<Configure>', self._on_resize, add='+')
        try:
            if not self._tk_host.winfo_ismapped():
                self.widget.hide()
        except Exception:
            self.widget.hide()
        _set_active_host(self)
        # 统一给文件对话框装防护：弹原生对话框期间暂停 Qt 泵，规避 0x8001010d
        install_file_dialog_guard()
        self._start_pump()

    # ---------- 对外 ----------

    def set_mesh(self, verts, faces):
        try:
            self.widget.set_vertices_faces(verts, faces)
        except Exception:
            pass

    def set_display_mode(self, mode):
        self.widget.set_display_mode(mode)

    def set_view(self, name):
        self.widget.set_view(name)

    def fit_view(self):
        self.widget.fit_view()

    def set_show_grid(self, on):
        self.widget.set_show_grid(on)

    def set_show_axes(self, on):
        self.widget.set_show_axes(on)

    def set_background_style(self, style):
        self.widget.set_background_style(style)

    def set_mouse_invert(self, invert_rotate=False, invert_zoom=False, invert_pan=False):
        self.widget.set_mouse_invert(invert_rotate, invert_zoom, invert_pan)

    def set_pointcloud(self, points, color=(1.0, 0.15, 0.15), size=2.0):
        try:
            self.widget.set_pointcloud(points, color, size)
        except Exception:
            pass

    def set_lines(self, line_groups):
        try:
            self.widget.set_lines(line_groups)
        except Exception:
            pass

    def clear_overlays(self):
        try:
            self.widget.clear_overlays()
        except Exception:
            pass

    def set_layer_visible(self, layer, on):
        try:
            self.widget.set_layer_visible(layer, bool(on))
        except Exception:
            pass

    def set_hull_color(self, color):
        try:
            self.widget.set_hull_color(color)
        except Exception:
            pass

    # ---------- 嵌入 ----------

    def _on_map(self, _evt=None):
        if not self._embedded:
            self._embed()

    def _on_resize(self, _evt=None):
        if not self._embedded:
            return
        try:
            w = max(self._tk_host.winfo_width(), 10)
            h = max(self._tk_host.winfo_height(), 10)
            self.widget.resize(w, h)
            ctypes.windll.user32.SetWindowPos(self._hwnd, 0, 0, 0, w, h, 0x0040)
        except Exception:
            pass

    def _embed(self):
        try:
            parent = int(self._tk_host.winfo_id())
            self._hwnd = int(self.widget.winId())
            ctypes.windll.user32.SetParent(self._hwnd, parent)
            style = ctypes.windll.user32.GetWindowLongW(self._hwnd, -16)
            ctypes.windll.user32.SetWindowLongW(self._hwnd, -16, style & ~0x00C00000)
            self.widget.show()
            self._on_resize()
            self._embedded = True
        except Exception:
            self._embedded = False

    # ---------- 事件泵 ----------

    def _start_pump(self):
        if self._pump_active:
            return
        self._pump_active = True
        self._pump()

    def pause(self):
        """暂停 Qt 事件泵（打开模态/文件对话框等场景，避免与 tk 消息循环重入）。

        引用计数式暂停：可被多层层叠调用（如模态框内再弹文件对话框），
        只有最外层 resume 到计数 0 时才真正恢复泵。
        """
        self._pump_pause_depth += 1
        if self._pump_pause_depth == 1:
            self._pump_active = False
            try:
                from src.core import dbg
                dbg.log('qt pump paused')
            except Exception:
                pass

    def resume(self):
        if self._pump_pause_depth > 0:
            self._pump_pause_depth -= 1
        if self._pump_pause_depth == 0 and not self._pump_active:
            self._pump_active = True
            self._pump()
            try:
                from src.core import dbg
                dbg.log('qt pump resumed')
            except Exception:
                pass

    def _pump(self):
        if not self._pump_active:
            return
        try:
            app = QApplication.instance()
            if app is not None:
                app.processEvents()
        except Exception:
            pass
        try:
            # 100ms 泵频率：比 30ms 更少与 Tk 消息循环交叉，降低重入崩溃概率
            self._tk_host.after(100, self._pump)
        except Exception:
            self._pump_active = False
