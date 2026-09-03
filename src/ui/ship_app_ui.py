# -*- coding: utf-8 -*-
"""
ship_app_ui.py —— 主界面 UI 构建（界面布局、菜单、工具栏、树、Tab 页面、日志、撤销）
"""

import os
import sys
import json
import math
import tkinter as tk
from tkinter import ttk, messagebox
import numpy as np

from src.ui.ui_widgets import (ClampedPanedWindow, EditableTable, PlotCanvas,
                        install_undo_support)


class ShipAppUI:
    APP_TITLE = 'SCS '

    # =====================================================================
    # 初始化
    # =====================================================================
    def __init__(self, root, icon_dir=None):
        self.root = root
        self.root.title(self.APP_TITLE)
        self.root.geometry('1380x860')
        self.icon_dir = icon_dir or os.path.join(os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))), 'icon')

        # ---------- 状态 ----------
        self.Lpp = math.nan
        self.Breadth = math.nan
        self.Depth = math.nan
        self.LppStartStation = math.nan
        self.LppEndStation = math.nan
        self.CoefficientMethod = 'trapezoidal'
        self.OriginFlag = 'amidship'
        self.Draft = math.nan
        self.HeelAngle = 0.0
        self.TrimAngle = 0.0
        self.IsLocked = False
        self.IsSymmetricView = False
        self.WireframeMode = '实体曲面'
        self.SurfaceColor = '#ccccff'
        self.LogBuffer = []
        self.isTap = 1
        self._icon_cache = {}
        # 未保存更改标记
        self._dirty = False
        # 当前项目文件路径（保存/打开后记录；None=未命名，自动保存用独立备份）
        self._current_project_path = None
        self._autosave_after = None
        # 用户偏好（全局持久化到用户目录 scs_prefs.json）
        self.prefs = self._load_prefs()

        # 数据存储
        self.waterlines = []
        self.decklines = []
        self.bodyplans = []
        self.sections = {}
        self.original_data = []
        self.original_headers = []
        self.ML_model = None
        self.StationSegments = None
        self.BuoyancyVolume = math.nan
        self.BuoyancyCenter = [math.nan, math.nan, math.nan]
        self.WaterplaneResults = {}
        self.SectionAreas = dict(stations_list=[], halfAreas_list=[],
                                 fullAreas_list=[], centroids_y_list=[],
                                 centroids_z_list=[], station_positions_list=[])
        self.BonjeanCurves = None
        self.Hydrostatics = None
        self.StabilityData = None
        self.GZ_CurveData = None
        self.DynamicStabilityData = None
        self.SurfaceGenerationData = {}

        # 撤销
        self.UndoStack = []
        self.UndoMaxSize = 50

        self._build_ui()
        self._load_app_icon()

    # =====================================================================
    # UI 构建
    # =====================================================================
    def _build_ui(self):
        # 必须在构建任何控件之前安装，类级绑定才能覆盖后续创建的输入框
        install_undo_support(self.root)
        self._apply_modern_style()
        self._build_menu()
        self._build_toolbar()

        main = ClampedPanedWindow(self.root, orient='horizontal',
                                  min_sizes=[170, 520],
                                  init_sash=[260])
        main.pack(fill='both', expand=True, padx=4, pady=(0, 4))
        # 保存引用，供 3D曲面 区域全屏切换使用
        self._main_paned = main

        left = ttk.Frame(main, width=240)
        main.add(left, weight=0)
        self._tree_frame = left
        self._build_tree(left)

        right = ttk.Frame(main)
        main.add(right, weight=1)
        self._tabs_frame = right
        self._build_tabs(right)
        # init_sash=[260] 会在 ClampedPanedWindow 首次 <Map> 时把左侧项目树
        # 拉到 260px 宽，避免一打开时树被默认收纳为 0。

        # 状态栏
        self._build_statusbar()

        # 初始化按钮启用与状态栏（与 MATLAB 一致：默认 Tab 1，所有编辑按钮禁用）
        self._update_button_state()
        self._refresh_statusbar()

        # Ctrl+Z 兜底：焦点不在输入框/表格上时，回退到应用级撤销（bind_all 最后执行）
        self.root.bind_all('<Control-z>', lambda e: self.undo())
        # Ctrl+S 保存项目；关闭前提示未保存更改
        self.root.bind_all('<Control-s>', lambda e: self.menu_save_project())
        # Ctrl+O 打开项目 / Ctrl+N 新建项目 / Ctrl+W 关闭对话框
        self.root.bind_all('<Control-o>', lambda e: self.menu_import_project())
        self.root.bind_all('<Control-n>', lambda e: self._new_project())
        # 页签快速切换：Ctrl+Tab / Ctrl+Shift+Tab 循环；Ctrl+1..8 直达
        self.root.bind_all('<Control-Tab>', lambda e: self._cycle_tab(1))
        self.root.bind_all('<Control-Shift-Tab>', lambda e: self._cycle_tab(-1))
        for i in range(1, 9):
            self.root.bind_all('<Control-KeyPress-%d>' % i,
                               lambda e, n=i - 1: self._goto_tab(n))
        # F11 全屏切换（3D曲面 页区域全屏）
        self.root.bind_all('<F11>', lambda e: self.toggle_fullscreen())
        # Esc 仅在全屏状态下退出
        self.root.bind_all('<Escape>', self._on_escape)
        self.root.protocol('WM_DELETE_WINDOW', self._on_close)

    def _cycle_tab(self, delta):
        """Ctrl+Tab 循环切换工作页签。"""
        try:
            tabs = self.notebook.tabs()
            if len(tabs) < 2:
                return
            cur = tabs.index(self.notebook.select())
            self.notebook.select(tabs[(cur + delta) % len(tabs)])
            self._refresh_statusbar()
        except Exception:
            pass

    def _goto_tab(self, index):
        """Ctrl+1..N 直达页签。"""
        try:
            tabs = self.notebook.tabs()
            if 0 <= index < len(tabs):
                self.notebook.select(tabs[index])
                self._refresh_statusbar()
        except Exception:
            pass

    def _build_statusbar(self):
        sb = ttk.Frame(self.root, relief='sunken', padding=(8, 2))
        sb.pack(side='bottom', fill='x')
        # 供 3D曲面 区域全屏切换使用
        self._statusbar = sb
        self.var_status = tk.StringVar(value='就绪')
        self.var_principal = tk.StringVar(value='主尺度: 未设置')
        self.var_methods = tk.StringVar(value='积分方法: 梯形法 | 原点: 船中 | 机器学习: 未加载')
        # 当前项目 + 未保存标记（多项目支持）
        self.var_project = tk.StringVar(value='项目: 项目')
        ttk.Label(sb, textvariable=self.var_project,
                  width=20, anchor='w').pack(side='left')
        ttk.Separator(sb, orient='vertical').pack(side='left', fill='y', padx=6)
        ttk.Label(sb, textvariable=self.var_status,
                  width=18).pack(side='left')
        ttk.Separator(sb, orient='vertical').pack(side='left', fill='y', padx=6)
        ttk.Label(sb, textvariable=self.var_principal, width=48).pack(side='left')
        ttk.Separator(sb, orient='vertical').pack(side='left', fill='y', padx=6)
        ttk.Label(sb, textvariable=self.var_methods).pack(side='left', padx=4)
        ttk.Separator(sb, orient='vertical').pack(side='left', fill='y', padx=6)
        # 时钟
        self.var_clock = tk.StringVar(value='')
        ttk.Label(sb, textvariable=self.var_clock).pack(side='right', padx=4)
        self._tick_clock()

    def _tick_clock(self):
        try:
            import datetime
            self.var_clock.set(datetime.datetime.now().strftime('%Y-%m-%d %H:%M:%S'))
        except Exception:
            pass
        self.root.after(1000, self._tick_clock)

    def _update_button_state(self):
        """根据当前 Tab、选中节点、表格锁定状态，更新工具栏按钮 enable（与 MATLAB 各 Tab 的 ButtonDown 一致）"""
        if not hasattr(self, 'tool_buttons') or not self.tool_buttons:
            return
        sel = self._selected_node() if hasattr(self, '_selected_node') else None
        node_meta = self.tree_meta.get(sel, {}) if sel else {}
        node_type = node_meta.get('type', '')
        isTap = self.isTap
        unlocked = not self.IsLocked
        for name, btn in self.tool_buttons.items():
            spec = self.tool_button_specs.get(name, {})
            allowed_taps = spec.get('taps', set())
            needs_lock_off = spec.get('needs_lock_off', False)
            node_needed = spec.get('node_type', '')
            if isTap not in allowed_taps:
                btn.config(state='disabled')
                continue
            if needs_lock_off and not unlocked:
                btn.config(state='disabled')
                continue
            if node_needed and node_type != node_needed:
                btn.config(state='disabled')
                continue
            btn.config(state='normal')
        # 3D 曲面 Tab 内部按钮的启用
        if hasattr(self, '_update_td_buttons'):
            self._update_td_buttons()

    def _refresh_statusbar(self):
        if not hasattr(self, 'var_status'):
            return
        # 当前项目名 + 未保存脏标记
        try:
            proj = getattr(self, '_current_project', None)
            name = self.tree.item(proj, 'text') if proj else '项目'
            star = ' *' if getattr(self, '_dirty', False) else ''
            self.var_project.set('项目: %s%s' % (name, star))
        except Exception:
            pass
        self.var_status.set('当前: ' + self._current_tab_name())
        # 主尺度
        if math.isfinite(self.Lpp):
            txt = ('主尺度: Lpp=%.2f B=%.2f D=%.2f | 站号 %.1f~%.1f'
                   % (self.Lpp,
                      self.Breadth if math.isfinite(self.Breadth) else 0,
                      self.Depth if math.isfinite(self.Depth) else 0,
                      self.LppStartStation if math.isfinite(self.LppStartStation) else 0,
                      self.LppEndStation if math.isfinite(self.LppEndStation) else 0))
        else:
            txt = '主尺度: 未设置'
        self.var_principal.set(txt)
        ml_state = '未加载' if self.ML_model is None else (
            '已加载(%s)' % self.ML_model.get('kind', '?'))
        method_names = {'trapezoidal': '梯形法', 'simp1': 'Simpson1/3', 'simp2': 'Simpson3/8'}
        origin_names = {'amidship': '船中', 'stern': '船尾', 'bow': '船首'}
        self.var_methods.set(
            '积分方法: %s | 原点: %s | 机器学习: %s' % (
                method_names.get(self.CoefficientMethod, self.CoefficientMethod),
                origin_names.get(self.OriginFlag, self.OriginFlag),
                ml_state))

    def _current_tab_name(self):
        try:
            return self.notebook.tab(self.notebook.select(), 'text')
        except Exception:
            return ''

    def set_busy(self, busy, msg='正在计算...'):
        """长任务忙指示：等待光标 + 状态栏提示（计算入口/出口成对调用）。"""
        try:
            if busy:
                self.root.config(cursor='watch')
                if hasattr(self, 'var_status'):
                    self.var_status.set(msg)
            else:
                self.root.config(cursor='')
                if hasattr(self, 'var_status'):
                    self._refresh_statusbar()
            self.root.update_idletasks()
        except Exception:
            pass

    def _update_td_buttons(self):
        """更新 3D 曲面 Tab 内部按钮的 enable 状态（仅在 3D曲面 页启用）。

        与 MATLAB Tab_4ButtonDown 一致：只要进入 3D曲面 页即启用生成按钮，
        不要求左侧树必须选中"船型模型"节点（按钮状态由当前项目数据决定）。
        """
        if not hasattr(self, 'td_buttons') or not self.td_buttons:
            return
        # 当前是否为 3D曲面 逻辑页（不受 tab 拖拽重排影响）
        try:
            text = self.notebook.tab(self.notebook.select(), 'text') or ''
        except Exception:
            text = ''
        if text != '3D曲面':
            for btn in self.td_buttons.values():
                btn.config(state='disabled')
            return
        # 是否有可用的船型数据（水线面 / 横剖面）
        has_wl = bool(self.waterlines)
        has_data = bool(self.waterlines or self.bodyplans)
        for name, btn in self.td_buttons.items():
            if name in ('hull', 'export_stl'):
                btn.config(state='normal' if has_wl else 'disabled')
            elif name in ('pointcloud', 'lines'):
                btn.config(state='normal' if has_data else 'disabled')
            elif name == 'fill_bottom':
                btn.config(state='normal' if (has_data or self.SurfaceGenerationData) else 'disabled')
            elif name == 'export_pcd':
                btn.config(state='normal' if self.SurfaceGenerationData else 'disabled')
            elif name == 'hull_color':
                # 蒙皮颜色不依赖数据，始终可用（Qt 视窗或 matplotlib 回退下均可调色）
                btn.config(state='normal')
            elif name == 'qt_fit':
                btn.config(state='normal' if getattr(self, 'qt3d_host', None) is not None
                           else 'disabled')
        # 全屏按钮始终可用（视图操作不依赖数据），按钮文字根据状态切换
        if 'fullscreen' in self.td_buttons:
            self.td_buttons['fullscreen'].config(state='normal')
            try:
                host = self.qt3d_host
                if host is not None and host.fullscreen_active:
                    self.td_buttons['fullscreen'].config(text='退出全屏(F11)')
                else:
                    self.td_buttons['fullscreen'].config(text='全屏(F11)')
            except Exception:
                pass

    def _load_app_icon(self):
        try:
            icon_path = os.path.join(self.icon_dir, '船.png')
            if os.path.exists(icon_path):
                img = tk.PhotoImage(file=icon_path)
                self.root.iconphoto(True, img)
        except Exception:
            pass

    def _apply_modern_style(self):
        """现代化样式：表格清晰边框、行高、字体、配色；面板与分隔线"""
        style = ttk.Style(self.root)
        # 工业软件：使用 Windows 原生主题，不做自定义配色
        for _theme in ('vista', 'winnative', 'xpnative', 'default'):
            try:
                style.theme_use(_theme)
                break
            except Exception:
                continue
        # 全局字体
        style.configure('.', font=('Microsoft YaHei', 9))
        # 表格：Excel 风格（原生白底 + 行高，不设斑马纹/自定义选中色）
        style.configure('Treeview', rowheight=22)
        style.configure('Treeview.Heading', font=('Microsoft YaHei', 9))
        # Tab 标签更"饱满"，按文字宽度自适应，每个 tab 占更多空间
        style.configure('TNotebook.Tab', padding=(18, 6), font=('Microsoft YaHei', 9))

    def _icon(self, name):
        """加载工具栏图标，失败返回 None（图像会被持有到 self._icon_cache 中防止被 GC 回收）"""
        try:
            path = os.path.join(self.icon_dir, name + '.png')
            if os.path.exists(path):
                if path in self._icon_cache:
                    return self._icon_cache[path]
                img = tk.PhotoImage(file=path)
                self._icon_cache[path] = img
                return img
        except Exception:
            pass
        return None

    # ---------------- 菜单 ----------------
    def _build_menu(self):
        menubar = tk.Menu(self.root)
        self.root.config(menu=menubar)
        # 供 3D曲面 区域全屏切换使用
        self.menubar = menubar

        m_file = tk.Menu(menubar, tearoff=0)
        m_file.add_command(label='导入项目', command=self.menu_import_project, accelerator='Ctrl+O')
        m_file.add_command(label='保存项目', command=self.menu_save_project, accelerator='Ctrl+S')
        # 最近打开的项目
        self.m_recent = tk.Menu(m_file, tearoff=0)
        m_file.add_cascade(label='最近打开', menu=self.m_recent)
        m_file.add_separator()
        m_file.add_command(label='导入型值表(Excel/CSV)', command=self.import_table_clicked)
        m_file.add_command(label='导出表格数据', command=self.menu_export)
        m_file.add_separator()
        m_file.add_command(label='退出', command=self.root.destroy)
        menubar.add_cascade(label='文件', menu=m_file)
        self._rebuild_recent_menu()

        m_setting = tk.Menu(menubar, tearoff=0)
        m_method = tk.Menu(m_setting, tearoff=0)
        m_method.add_command(label='梯形法', command=lambda: self.set_method('trapezoidal'))
        m_method.add_command(label='辛普森 1/3', command=lambda: self.set_method('simp1'))
        m_method.add_command(label='辛普森 3/8', command=lambda: self.set_method('simp2'))
        m_setting.add_cascade(label='积分方法', menu=m_method)
        m_origin = tk.Menu(m_setting, tearoff=0)
        m_origin.add_command(label='船中 (amidship)', command=lambda: self.set_origin('amidship'))
        m_origin.add_command(label='船尾 (stern)', command=lambda: self.set_origin('stern'))
        m_origin.add_command(label='船首 (bow)', command=lambda: self.set_origin('bow'))
        m_setting.add_cascade(label='原点位置', menu=m_origin)
        m_setting.add_separator()
        m_setting.add_command(label='首选项...', command=self.set_preferences_clicked)
        m_setting.add_command(label='设置主尺度...', command=self.set_principal_clicked)
        menubar.add_cascade(label='设置', menu=m_setting)

        m_view = tk.Menu(menubar, tearoff=0)
        m_view.add_command(label='主尺度信息', command=self.view_principal_dim)
        m_view.add_command(label='静水力数据', command=self.view_hydrostatics)
        m_view.add_command(label='邦戎曲线数据', command=self.view_bonjean)
        m_view.add_command(label='稳性数据', command=self.view_stability)
        m_view.add_command(label='数据汇总报告', command=self.view_data_summary)
        m_view.add_separator()
        m_view.add_command(label='重置缩放', command=self.zoom_reset)
        m_view.add_command(label='刷新图表', command=self.refresh_plots)
        menubar.add_cascade(label='查看', menu=m_view)

        m_3d = tk.Menu(menubar, tearoff=0)
        m_wire = tk.Menu(m_3d, tearoff=0)
        m_wire.add_command(label='实体曲面', command=lambda: self.set_wiremode('实体曲面'))
        m_wire.add_command(label='高光边缘', command=lambda: self.set_wiremode('高光边缘'))
        m_wire.add_command(label='纯线框', command=lambda: self.set_wiremode('纯线框'))
        m_3d.add_cascade(label='线框模式', menu=m_wire)
        m_3d.add_command(label='三维型线视图...', command=self.menu_half_section)
        m_3d.add_command(label='导出船体STL...', command=self.export_stl)
        menubar.add_cascade(label='三维显示', menu=m_3d)

        m_help = tk.Menu(menubar, tearoff=0)
        m_help.add_command(label='诊断信息...', command=self.show_diagnostics_clicked)
        m_help.add_command(label='关于 SCS...', command=self.about_clicked)
        menubar.add_cascade(label='帮助', menu=m_help)

    # ---------------- 工具栏 ----------------
    def _build_toolbar(self):
        bar = ttk.Frame(self.root, padding=(4, 4, 4, 2))
        bar.pack(fill='x')
        # 供 3D曲面 区域全屏切换使用
        self._toolbar = bar

        # 按图片分组排列按钮（与 MATLAB 工具栏按钮顺序一致，分组靠拢以视觉对齐）
        # groups: list of (group_label, [(name, icon_name, callback, tip_text), ...])
        groups = [
            ('数据', [
                ('导入表格', '导入', self.import_table_clicked, '导入型值表 (Excel/CSV/TXT)'),
                ('模型', '机器学习', self.add_ml_model_clicked, '加载/训练机器学习模型'),
                ('特征提取', '提取', self.extract_clicked, '从表格提取特征并预测列角色'),
            ]),
            ('设置', [
                ('主尺度', '输入', self.set_principal_clicked, '设置主尺度（Lpp/型宽/型深/站号）'),
                ('拟合', '函数-曲线拟合', self.curve_fitting_clicked, '曲线拟合 (多项式/PCHIP)'),
                ('分段', '分段栏', self.subsection_clicked, '分段统计与面积/力矩'),
                ('对称', '对称', self.symmetry_clicked, '对称/半宽显示切换'),
            ]),
            ('编辑', [
                ('站号', '站号', self.add_station_num_clicked, '快速生成站号（区间+显式）'),
                ('半宽', '提取', self.add_half_clicked, '从粘贴板快速导入半宽'),
                ('系数', '系数', self.add_coefficient_clicked, '生成积分系数（梯形/Simpson））'),
                ('矩臂', '输入', self.add_moment_arm_clicked, '生成相对矩臂列'),
                ('增行', '新行', self.add_row_clicked, '新增一行到半宽表'),
                ('删行', '删行', self.delete_row_clicked, '删除半宽表最后一行'),
            ]),
            ('工具', [
                ('锁定', 'lock', self.lock_edit_clicked, '锁定/解锁半宽表编辑'),
                ('删列', '删除', self.delete_col_clicked, '清零水线面计算结果'),
                ('计算', '船', self.cal_clicked, '水线面核心计算（分段累加）'),
            ]),
        ]

        # 按钮 enable 规则（与 MATLAB 各 TabButtonDown 一致）
        self.tool_button_specs = {
            '导入表格': {'taps': {1, 2, 3, 4, 5, 6, 7, 8}},
            '模型': {'taps': {1, 2, 3, 4, 5, 6, 7, 8}},
            '特征提取': {'taps': {1, 2, 3, 4, 5, 6, 7, 8}, 'node_type': 'table'},
            '主尺度': {'taps': {1, 2, 3, 4, 5, 6, 7, 8}},
            '站号': {'taps': {2}, 'needs_lock_off': True},
            '半宽': {'taps': {2}, 'needs_lock_off': True},
            '系数': {'taps': {2}, 'needs_lock_off': True},
            '矩臂': {'taps': {2}, 'needs_lock_off': True},
            '对称': {'taps': {2, 3}},
            '拟合': {'taps': {2}},
            '锁定': {'taps': {1, 2, 3, 4, 5, 6, 7, 8}},
            '删列': {'taps': {2}},
            '分段': {'taps': {2}, 'needs_lock_off': True},
            '计算': {'taps': {2}, 'needs_lock_off': True},
            '增行': {'taps': {2}, 'needs_lock_off': True},
            '删行': {'taps': {2}, 'needs_lock_off': True},
        }

        self.tool_buttons = {}
        from src.ui.ui_widgets import Tooltip
        # 组装每个按钮组（SOLIDWORKS Ribbon 风格：图标行 + 底部灰色小组名）
        for gi, (gname, gbtns) in enumerate(groups):
            if gi > 0:
                ttk.Separator(bar, orient='vertical').pack(side='left', fill='y',
                                                           padx=4, pady=8)
            gframe = ttk.Frame(bar)
            gframe.pack(side='left', padx=2, pady=1)
            brow = ttk.Frame(gframe)
            brow.pack(side='top')
            for name, icon_name, cmd, tip in gbtns:
                icon = self._small_icon(icon_name, max_size=16)
                b = ttk.Button(brow,
                              image=icon if icon else '',
                              compound='none' if icon else 'text',
                              text='' if icon else name,
                              command=cmd,
                              width=3 if icon else 10,
                              style='Toolbutton' if icon else 'TButton')
                b.image = icon  # 防止 PhotoImage 被回收
                b.pack(side='left', padx=2, pady=1)
                Tooltip(b, tip)
                self.tool_buttons[name] = b
            # 小组名（Ribbon 底部灰字）
            ttk.Label(gframe, text=gname,
                      font=('Microsoft YaHei', 7)).pack(side='top', pady=(0, 2))

        # 3D曲面 Tab 内部按钮字典（绘图生成、补齐底部、导出）
        self.td_buttons = {}

    def _log_text(self, parent, height=6):
        """创建日志/只读文本域：原生外观 + 可撤销"""
        w = tk.Text(parent, height=height, wrap='none', undo=True, maxundo=0)
        w.configure(font=('Microsoft YaHei', 9))
        return w

    def _small_icon(self, name, max_size=16):
        """加载并按比例缩小图标（使用 PIL 平滑缩放，保持纵横比，长边不超过 max_size）"""
        try:
            path = os.path.join(self.icon_dir, name + '.png')
            if not os.path.exists(path):
                return None
            cache_key = '%s#%d' % (path, max_size)
            if cache_key in self._icon_cache:
                return self._icon_cache[cache_key]
            from PIL import Image, ImageTk
            im = Image.open(path)
            im = im.convert('RGBA')
            w, h = im.size
            if w > max_size or h > max_size:
                scale = max_size / max(w, h)
                im = im.resize((max(1, int(w * scale)), max(1, int(h * scale))),
                               Image.LANCZOS)
            img = ImageTk.PhotoImage(im)
            self._icon_cache[cache_key] = img
            return img
        except Exception:
            return None

    # ---------------- 树 ----------------
    def _build_tree(self, parent):
        frame = ttk.Frame(parent)
        frame.pack(fill='both', expand=True, padx=2, pady=2)
        self.tree = ttk.Treeview(frame, show='tree', style='Treeview')
        vsb = ttk.Scrollbar(frame, orient='vertical', command=self.tree.yview)
        self.tree.configure(yscrollcommand=vsb.set)
        self.tree.pack(side='left', fill='both', expand=True)
        vsb.pack(side='right', fill='y')
        self.tree_meta = {}
        self._current_project = None
        self.tree_root = self._create_project_node('项目')
        self._switch_project(self.tree_root)
        self.tree.bind('<<TreeviewSelect>>', self.tree_selection_changed)
        self.tree.bind('<Double-1>', self.tree_double_click)
        self.tree.bind('<Button-3>', self.tree_right_click)

    def _tree_add(self, parent, text, meta=None):
        iid = self.tree.insert(parent, 'end', text=text)
        self.tree_meta[iid] = meta or {}
        return iid

    def _create_project_node(self, name):
        """创建项目节点（含 Table/Model/Face 三个分组），返回项目 iid。"""
        root = self.tree.insert('', 'end', text=name, open=True)
        self.tree_meta[root] = {'type': 'project'}
        self._tree_add(root, 'Table', {'type': 'table_root'})
        self._tree_add(root, 'Model', {'type': 'model_root'})
        self._tree_add(root, 'Face', {'type': 'face_root'})
        return root

    def _new_project(self):
        """右键空白新建项目；新项目成为当前项目。"""
        existing = [self.tree.item(c, 'text') for c in self.tree.get_children('')]
        n = 1
        name = '项目'
        while name in existing:
            n += 1
            name = '项目 %d' % n
        root = self._create_project_node(name)
        self._switch_project(root)
        self.tree.selection_set(root)
        self._update_button_state()
        self._refresh_statusbar()
        self.log('已新建项目：%s' % name)
        return root

    def _find_project_child(self, proj, text):
        for c in self.tree.get_children(proj):
            if self.tree.item(c, 'text') == text:
                return c
        return None

    def _node_project(self, iid):
        """返回 iid 所属的项目节点（含 iid 自身），找不到返回 None。"""
        cur = iid
        while cur:
            if self.tree_meta.get(cur, {}).get('type') == 'project':
                return cur
            cur = self.tree.parent(cur)
        return None

    def _switch_project(self, proj):
        """切换当前项目（新数据挂载到该项目分组下）。"""
        self._current_project = proj
        self.tree_root = proj
        self.table_root = self._find_project_child(proj, 'Table') or self.table_root
        self.model_root = self._find_project_child(proj, 'Model') or self.model_root
        self.face_root = self._find_project_child(proj, 'Face') or self.face_root

    def _rename_tree_node(self, iid):
        """行内重命名节点（项目/分组/普通节点均可）。"""
        x, y, w, h = self.tree.bbox(iid)
        if not x:
            self.tree.see(iid)
            self.tree.update_idletasks()
            x, y, w, h = self.tree.bbox(iid) or (0, 0, 120, 20)
        entry = tk.Entry(self.tree)
        entry.place(x=x, y=y, width=max(w, 40), height=h)
        entry.insert(0, self.tree.item(iid, 'text'))
        entry.select_range(0, 'end')
        entry.focus_set()

        def commit(_evt=None):
            new = entry.get().strip()
            entry.destroy()
            if new:
                self.tree.item(iid, text=new)
                self._refresh_statusbar()

        entry.bind('<Return>', commit)
        entry.bind('<FocusOut>', commit)
        entry.bind('<Escape>', lambda _e: entry.destroy())

    # ---------------- Tab 页面 ----------------
    def _build_tabs(self, parent):
        # 使用 Windows 原生 Notebook（不做自定义配色/自绘 Tab）
        self.notebook = ttk.Notebook(parent)
        self.notebook.pack(fill='both', expand=True)
        # Tab 拖拽重排（按住拖动 tab 标签到目标位置松手即可）
        self._tab_drag_idx = None
        self._tab_drag_origin = (0, 0)
        self.notebook.bind('<ButtonPress-1>', self._on_notebook_tab_press)
        self.notebook.bind('<B1-Motion>', self._on_notebook_tab_motion)
        self.notebook.bind('<ButtonRelease-1>', self._on_notebook_tab_release)

        tab1 = ttk.Frame(self.notebook)
        self.notebook.add(tab1, text='原表格')
        self._build_tab1(tab1)

        tab2 = ttk.Frame(self.notebook)
        self.notebook.add(tab2, text='半宽')
        self._build_tab2(tab2)

        tab3 = ttk.Frame(self.notebook)
        self.notebook.add(tab3, text='横剖面')
        self._build_tab3(tab3)

        tab4 = ttk.Frame(self.notebook)
        self.notebook.add(tab4, text='3D曲面')
        self._build_tab4(tab4)

        tab5 = ttk.Frame(self.notebook)
        self.notebook.add(tab5, text='浮心')
        self._build_tab5(tab5)

        tab6 = ttk.Frame(self.notebook)
        self.notebook.add(tab6, text='静力曲线')
        self._build_tab6(tab6)

        tab7 = ttk.Frame(self.notebook)
        self.notebook.add(tab7, text='邦戎曲线')
        self._build_tab7(tab7)

        tab8 = ttk.Frame(self.notebook)
        self.notebook.add(tab8, text='稳性')
        self._build_tab8(tab8)

        self.notebook.bind('<<NotebookTabChanged>>', self._on_tab_changed, add='+')

    def _build_tab1(self, parent):
        paned = ClampedPanedWindow(parent, orient='vertical', min_sizes=[120, 50])
        paned.pack(fill='both', expand=True)
        self.original_table = EditableTable(paned, columns=['列'], editable=True)
        paned.add(self.original_table, weight=3)
        f = ttk.Frame(paned)
        paned.add(f, weight=1)
        self.TextArea_debug = self._log_text(f, 6)
        self.TextArea_debug.pack(fill='both', expand=True, padx=2, pady=2)

    def _build_tab2(self, parent):
        paned = ClampedPanedWindow(parent, orient='vertical', min_sizes=[75, 200, 60])
        paned.pack(fill='both', expand=True)

        res = ttk.LabelFrame(paned, text='水线面计算结果')
        paned.add(res, weight=0)
        self.var_A = tk.StringVar(value='')
        self.var_M = tk.StringVar(value='')
        self.var_Segment = tk.StringVar(value='')
        self.var_Half_A = tk.StringVar(value='')
        self.var_Half_M = tk.StringVar(value='')
        self.var_Ful_A = tk.StringVar(value='')
        self.var_Full_M = tk.StringVar(value='')
        self.var_LCF = tk.StringVar(value='')
        labels = [('面积A', self.var_A), ('力矩M', self.var_M), ('分段', self.var_Segment),
                  ('半船面积', self.var_Half_A), ('半船力矩', self.var_Half_M),
                  ('全船面积', self.var_Ful_A), ('全船力矩', self.var_Full_M),
                  ('漂心LCF', self.var_LCF)]
        for i, (t, v) in enumerate(labels):
            tk.Label(res, text=t).grid(row=i // 4, column=(i % 4) * 2, padx=4, pady=2)
            tk.Label(res, textvariable=v, width=14, relief='sunken',
                     anchor='e').grid(row=i // 4, column=(i % 4) * 2 + 1, padx=4, pady=2)

        mid = ClampedPanedWindow(paned, orient='horizontal', min_sizes=[240, 300])
        paned.add(mid, weight=4)
        left = ttk.Frame(mid)
        mid.add(left, weight=2)
        self.Half_table = EditableTable(left, columns=['列', '站号', '半宽', '系数', '相对矩臂'],
                                        editable=True)
        self.Half_table.pack(fill='both', expand=True)
        # on_before_edit 在写入前触发，用于保存"变更前"的撤销快照
        self.Half_table.on_before_edit(self._on_half_table_edit)
        self.Half_table.on_edit(self._on_half_table_plot)

        right = ttk.Frame(mid)
        mid.add(right, weight=3)
        self.plot_half_area = PlotCanvas(right, toolbar=True)
        self.plot_half_area.pack(fill='both', expand=True)
        self.plot_fitting = PlotCanvas(right, toolbar=True)
        self.plot_fitting.pack(fill='both', expand=True, pady=(4, 0))

        f = ttk.LabelFrame(paned, text='曲线拟合')
        paned.add(f, weight=1)
        self.TextArea_curve_fitting = tk.Text(f, height=6, wrap='none')
        self.TextArea_curve_fitting.pack(fill='both', expand=True)

    def _build_tab3(self, parent):
        paned = ClampedPanedWindow(parent, orient='vertical', min_sizes=[85, 200, 50])
        paned.pack(fill='both', expand=True)
        res = ttk.LabelFrame(paned, text='横剖面计算结果')
        paned.add(res, weight=0)
        self.var_Z_HalfArea = tk.StringVar(value='')
        self.var_Z_FullArea = tk.StringVar(value='')
        self.var_Z_HalfCentroidX = tk.StringVar(value='')
        self.var_Z_CentroidZ = tk.StringVar(value='')
        vals = [('半船面积', self.var_Z_HalfArea), ('全船面积', self.var_Z_FullArea),
                ('剖面X坐标', self.var_Z_HalfCentroidX), ('垂向形心Z', self.var_Z_CentroidZ)]
        for i, (t, v) in enumerate(vals):
            tk.Label(res, text=t).grid(row=i // 2, column=(i % 2) * 2, padx=4, pady=2)
            tk.Label(res, textvariable=v, width=16, relief='sunken',
                     anchor='e').grid(row=i // 2, column=(i % 2) * 2 + 1, padx=4, pady=2)
        ttk.Button(res, text='计算横剖面面积与形心',
                   command=self.calc_transverse_section_clicked).grid(row=2, column=0, columnspan=4, pady=4)

        mid = ClampedPanedWindow(paned, orient='horizontal', min_sizes=[200, 250])
        paned.add(mid, weight=4)
        left = ttk.Frame(mid)
        mid.add(left, weight=1)
        self.Z_table = EditableTable(left, columns=['列', '高度', '半宽', '系数'], editable=True)
        self.Z_table.pack(fill='both', expand=True)
        self.Z_table.on_before_edit(self._on_z_table_edit)
        self.Z_table.on_edit(self._on_z_table_plot)
        right = ttk.Frame(mid)
        mid.add(right, weight=2)
        self.plot_z_area = PlotCanvas(right, toolbar=True)
        self.plot_z_area.pack(fill='both', expand=True)

        f = ttk.Frame(paned)
        paned.add(f, weight=1)
        self.TextArea_debug_3 = self._log_text(f, 6)
        self.TextArea_debug_3.pack(fill='both', expand=True, padx=2, pady=2)

    def _build_tab4(self, parent):
        paned = ClampedPanedWindow(parent, orient='vertical', min_sizes=[40, 200, 40])
        paned.pack(fill='both', expand=True)
        tools = ttk.Frame(paned)
        paned.add(tools, weight=0)
        self.td_buttons = {
            'pointcloud': ttk.Button(tools, text='1.生成点云', command=self.gen_pointcloud_clicked),
            'lines': ttk.Button(tools, text='2.绘制型线', command=self.gen_lines_clicked),
            'hull': ttk.Button(tools, text='3.生成蒙皮', command=self.gen_hull_clicked),
            'fill_bottom': ttk.Button(tools, text='补齐底部', command=self.fill_bottom_points),
            'export_pcd': ttk.Button(tools, text='导出点云', command=self.export_pointcloud),
            'export_stl': ttk.Button(tools, text='导出STL', command=self.export_stl),
        }
        for btn in self.td_buttons.values():
            btn.pack(side='left', padx=2)
        tk.Label(tools, text='线框:').pack(side='left', padx=(10, 2))
        self.var_wiremode = tk.StringVar(value='实体曲面')
        self.cb_wiremode = ttk.Combobox(tools, textvariable=self.var_wiremode, width=8,
                                        values=['实体曲面', '高光边缘', '纯线框'], state='readonly')
        self.cb_wiremode.pack(side='left')
        tk.Label(tools, text='蒙皮质量:').pack(side='left', padx=(10, 2))
        self.var_mesh_quality = tk.StringVar(value='标准')
        self.cb_mesh_quality = ttk.Combobox(tools, textvariable=self.var_mesh_quality, width=6,
                                            values=['流畅', '标准', '精细'], state='readonly')
        self.cb_mesh_quality.pack(side='left')
        self.var_azimuth = tk.DoubleVar(value=-135)
        self.var_elevation = tk.DoubleVar(value=25)

        # ---- Qt SolidWorks 风格 3D 视窗控件 ----
        tk.Label(tools, text='视角:').pack(side='left', padx=(10, 2))
        self.var_qt_view = tk.StringVar(value='等轴测')
        self.cb_qt_view = ttk.Combobox(
            tools, textvariable=self.var_qt_view, width=10, state='readonly',
            values=['等轴测', '正视图(艏)', '侧视图(右舷)', '后视图(艉)', '顶视图', '底部视图'])
        self.cb_qt_view.pack(side='left')
        self.cb_qt_view.bind('<<ComboboxSelected>>', self._on_qt_view_change)
        self.td_buttons['qt_fit'] = ttk.Button(tools, text='适合视图', command=self._on_qt_fit)
        self.td_buttons['qt_fit'].pack(side='left', padx=2)
        self.var_qt_grid = tk.IntVar(value=1)
        self.chk_qt_grid = ttk.Checkbutton(tools, text='地面网格',
                                            variable=self.var_qt_grid,
                                            command=self._on_qt_grid_toggle)
        self.chk_qt_grid.pack(side='left', padx=(10, 2))
        # ---- 显示层开关：点云 / 型线 / 蒙皮 ----
        self.var_show_pc = tk.BooleanVar(value=True)
        self.var_show_lines = tk.BooleanVar(value=True)
        self.var_show_hull = tk.BooleanVar(value=True)
        ttk.Checkbutton(tools, text='点云', variable=self.var_show_pc,
                        command=self._on_show_pc).pack(side='left', padx=(10, 2))
        ttk.Checkbutton(tools, text='型线', variable=self.var_show_lines,
                        command=self._on_show_lines).pack(side='left', padx=2)
        ttk.Checkbutton(tools, text='蒙皮', variable=self.var_show_hull,
                        command=self._on_show_hull).pack(side='left', padx=2)
        # ---- 蒙皮颜色 ----
        self.td_buttons['hull_color'] = ttk.Button(tools, text='蒙皮颜色…',
                                                   command=self._pick_hull_color)
        self.td_buttons['hull_color'].pack(side='left', padx=(6, 2))
        # 区域全屏：让 Qt 3D 视窗脱离嵌入铺满全屏（SOLIDWORKS 风格）
        self.td_buttons['fullscreen'] = ttk.Button(tools, text='全屏(F11)',
                                                   command=self.toggle_fullscreen)
        self.td_buttons['fullscreen'].pack(side='left', padx=(10, 2))

        canvas_frame = ttk.Frame(paned)
        paned.add(canvas_frame, weight=4)
        self._td_canvas_frame = canvas_frame
        # matplotlib 画布仍生成（测试/回退用）；可视可见态会被 Qt 视窗覆盖
        self.plot_face_area = PlotCanvas(canvas_frame, three_d=True, toolbar=True)
        self.plot_face_area.pack(fill='both', expand=True)
        # Qt 视窗占位（首次切到本页时懒加载）
        self.qt_host_frame = ttk.Frame(canvas_frame)
        self.qt3d_host = None
        # 线框选择同时驱动 Qt 显示模式
        self.cb_wiremode.bind('<<ComboboxSelected>>', self._on_wiremode_change, add='+')
        self.notebook.bind('<<NotebookTabChanged>>', self._on_notebook_tab_changed, add='+')

        f = ttk.Frame(paned)
        paned.add(f, weight=1)
        self._td_log_frame = f
        self.TextArea_debug_4 = self._log_text(f, 5)
        self.TextArea_debug_4.pack(fill='both', expand=True, padx=2, pady=2)
        # 区域全屏所需的关键引用
        self._td_paned = paned
        self._td_tools = tools

    # ---------- Qt SolidWorks 风格 3D 视窗 ----------

    def _on_notebook_tab_changed(self, _evt=None):
        try:
            sel = self.notebook.select()
            if sel and self.notebook.tab(sel, 'text') == '3D曲面':
                self._ensure_qt3d()
        except Exception:
            pass

    # ---- Tab 拖拽重排（直接 insert 自动移动，安全 + 逐格碰撞让位动效） ----
    def _on_notebook_tab_press(self, e):
        try:
            idx = self.notebook.index('@%d,%d' % (e.x, e.y))
        except Exception:
            idx = None
        n = len(self.notebook.tabs())
        if idx is None or idx < 0 or idx >= n:
            self._tab_drag_idx = None
            return
        self._tab_drag_idx = idx
        self._tab_drag_origin = (e.x, e.y)

    def _on_notebook_tab_motion(self, e):
        cur = getattr(self, '_tab_drag_idx', None)
        if cur is None:
            return
        n = len(self.notebook.tabs())
        if n <= 1:
            return
        target = self._tab_drop_index(e, cur, n)
        if target == cur:
            return
        try:
            moving = self.notebook.tabs()[cur]
            # ttk.Notebook.insert 会把已存在的子页自动移动到 target 位置，
            # 无需 forget（不会因坐标错乱而消失），文字等选项保留。
            self.notebook.insert(target, moving)
            self.notebook.select(moving)
            self._tab_drag_idx = self.notebook.index(moving)
            self._tab_drag_origin = (e.x, e.y)
        except Exception:
            pass

    def _tab_drop_index(self, e, cur, n):
        """鼠标位置 -> 目标 tab 序号（0..n-1）。

        index('@x,y') 在 tab 标签之外的空白区会抛异常，此时按鼠标相对
        notebook 的水平位置猜测：偏右 → 放最末；偏左 → 放最前。
        """
        x, y = e.x, e.y
        try:
            raw = self.notebook.index('@%d,%d' % (x, y))
            if raw is None:
                raw = cur
            return max(0, min(int(raw), n - 1))
        except Exception:
            pass
        # 空白区：y 大致在标签头高度内才处理（防止拖动到内容区误触发）
        try:
            if y < 0 or y > 40:
                return cur
        except Exception:
            pass
        # 相对 notebook 宽度判断靠左还是靠右
        try:
            w = max(self.notebook.winfo_width(), 1)
            return n - 1 if x > w / 2 else 0
        except Exception:
            return cur

    def _on_notebook_tab_release(self, _e=None):
        self._tab_drag_idx = None

    def _ensure_qt3d(self):
        """首次切到 3D曲面页时创建 Qt 视窗；失败自动回退 matplotlib。"""
        from src.core import dbg
        if self.qt3d_host is not None:
            return
        try:
            from src.viewer.qt_3d_viewer import Qt3DHost, qt_available
            if not qt_available():
                return
            self.qt3d_host = Qt3DHost(self.qt_host_frame)
            dbg.log('qt3d host created')
            self.plot_face_area.pack_forget()
            self.qt_host_frame.pack(fill='both', expand=True)
            self._sync_qt3d_display_mode()
            self._sync_qt3d_view()
            self._sync_qt3d_grid()
            self._apply_qt3d_prefs()
            # 若此前已生成过蒙皮，把网格补推给 Qt 视窗
            try:
                d = getattr(self, 'SurfaceGenerationData', None) or {}
                if d.get('Vertices') is not None and d.get('Faces') is not None:
                    self.qt3d_host.set_mesh(d['Vertices'], d['Faces'])
            except Exception:
                pass
        except Exception as e:
            self.qt3d_host = None
            self.log('Qt 3D 视窗不可用，已回退 matplotlib 3D：%s' % e)

    def _sync_qt3d_display_mode(self):
        if self.qt3d_host is None:
            return
        mode = {'实体曲面': 0, '高光边缘': 1, '纯线框': 2}.get(self.var_wiremode.get(), 1)
        self.qt3d_host.set_display_mode(mode)

    def _sync_qt3d_view(self):
        if self.qt3d_host is not None:
            self.qt3d_host.set_view(self.var_qt_view.get())

    def _sync_qt3d_grid(self):
        if self.qt3d_host is not None:
            self.qt3d_host.set_show_grid(bool(self.var_qt_grid.get()))

    def _on_qt_view_change(self, _evt=None):
        self._sync_qt3d_view()

    def _on_qt_fit(self):
        if self.qt3d_host is not None:
            self.qt3d_host.fit_view()

    def _on_qt_grid_toggle(self):
        self._sync_qt3d_grid()

    def _on_wiremode_change(self, _evt=None):
        self._sync_qt3d_display_mode()

    # ---- 显示层开关（Qt 视窗） ----
    def _qt_set_layer(self, layer, on):
        if self.qt3d_host is not None:
            try:
                self.qt3d_host.set_layer_visible(layer, bool(on))
            except Exception as e:
                self.log('Qt 显示层切换失败：%s' % e)

    def _on_show_pc(self):
        self._qt_set_layer('pointcloud', self.var_show_pc.get())

    def _on_show_lines(self):
        self._qt_set_layer('lines', self.var_show_lines.get())

    def _on_show_hull(self):
        self._qt_set_layer('hull', self.var_show_hull.get())

    def _pick_hull_color(self):
        """选择蒙皮颜色：Qt 视窗可用时立即生效；不可用时同步记忆便于蒙皮生成。"""
        try:
            from tkinter import colorchooser
            cur = getattr(self, 'HullColor', (0.18, 0.42, 0.78))
            # 16 进制 -> RGB(0~255)
            hex0 = '#%02x%02x%02x' % tuple(int(max(0, min(1, c)) * 255) for c in cur[:3])
            rgb, hexc = colorchooser.askcolor(color=hex0, title='选择蒙皮颜色', parent=self.root)
            if rgb is None:
                return
            r, g, b = (x / 255.0 for x in rgb)
            self.HullColor = (r, g, b)
            self.SurfaceColor = hexc   # matplotlib 回退视图同步（重新生成/恢复显示用）
            if self.qt3d_host is not None:
                try:
                    self.qt3d_host.set_hull_color(self.HullColor)
                except Exception as e:
                    self.log('蒙皮颜色更新失败：%s' % e)
            # matplotlib 回退视图已有蒙皮时即时改色
            try:
                artist = getattr(self, '_hull_mesh_artist', None)
                if artist is not None and getattr(self, 'plot_face_area', None) is not None:
                    artist.set_facecolor(self.SurfaceColor)
                    self.plot_face_area.refresh()
            except Exception:
                pass
            self.log('蒙皮颜色已设为 %s' % hexc)
        except Exception:
            pass

    def toggle_fullscreen(self):
        """3D曲面 区域全屏切换（按钮 / F11 / Esc）。

        进入：root.attributes('-fullscreen') 最大化；
隐藏菜单栏 / 工具栏 / 状态栏 / 左侧项目树 / tab4 内的日志行，
让 canvas_frame（含 Qt 视窗）在 tab4 paned 中占满；按钮工具行保留。
退出时恢复。
        """
        try:
            if not getattr(self, '_fs_on', False):
                self._enter_fullscreen()
            else:
                self._exit_fullscreen()
        except Exception:
            import traceback
            try:
                self.root.attributes('-fullscreen', False)
            except Exception:
                pass

    def _enter_fullscreen(self):
        # 1) 切换到 3D曲面 页（如果不在）
        try:
            for i in range(self.notebook.index('end')):
                if self.notebook.tab(i, 'text') == '3D曲面':
                    self.notebook.select(i)
                    break
        except Exception:
            pass

        # 2) 记录布局状态并隐藏 chrome
        self._fs_pack_info = {}
        self._fs_sash0 = None
        try:
            # 菜单栏
            self._fs_menu_backup = self.root.cget('menu')
            self.root.config(menu='')
        except Exception:
            self._fs_menu_backup = ''
        # 工具栏 / 状态栏
        for name, w in (('_toolbar', self._toolbar),
                        ('_statusbar', self._statusbar)):
            if w is None:
                continue
            try:
                self._fs_pack_info[name] = w.pack_info()
                w.pack_forget()
            except Exception:
                pass
        # 左侧项目树：把 main paned 第一个 sash 拉到 0（隐藏左侧）
        try:
            if getattr(self, '_main_paned', None) is not None:
                self._fs_sash0 = int(self._main_paned.sashpos(0))
                self._main_paned.sashpos(0, 0)
        except Exception:
            pass
        # 3) 隐藏 tab4 paned 的日志行（保留 tools + canvas）
        try:
            if getattr(self, '_td_log_frame', None) is not None \
                    and self._td_log_frame in self._td_paned.panes():
                self._td_paned.forget(self._td_log_frame)
        except Exception:
            pass
        # 4) 全屏 root
        try:
            self.root.attributes('-fullscreen', True)
        except Exception:
            self.root.state('zoomed')
        self._fs_on = True
        try:
            self.td_buttons['fullscreen'].config(text='退出全屏(F11)')
        except Exception:
            pass
        # 5) 让 Qt widget 立即按新尺寸刷新
        try:
            self.root.update_idletasks()
            self._ensure_qt3d()
            if self.qt3d_host is not None:
                self.qt3d_host.widget.update()
        except Exception:
            pass

    def _exit_fullscreen(self):
        # 1) 退出系统全屏
        try:
            self.root.attributes('-fullscreen', False)
        except Exception:
            try:
                self.root.state('normal')
            except Exception:
                pass
        # 2) 恢复 tab4 paned 日志行
        try:
            if getattr(self, '_td_log_frame', None) is not None \
                    and self._td_log_frame not in self._td_paned.panes():
                self._td_paned.add(self._td_log_frame, weight=1)
        except Exception:
            pass
        # 3) 恢复左侧项目树 sash 位置
        try:
            if getattr(self, '_fs_sash0', None) is not None \
                    and getattr(self, '_main_paned', None) is not None:
                self._main_paned.sashpos(0, int(self._fs_sash0))
        except Exception:
            pass
        # 4) 恢复工具栏 / 状态栏（恢复原 pack 信息）
        for name in ('_toolbar', '_statusbar'):
            w = getattr(self, name, None)
            if w is None:
                continue
            info = self._fs_pack_info.get(name)
            try:
                if info:
                    w.pack(**info)
                else:
                    w.pack()
            except Exception:
                try:
                    w.pack(fill='x')
                except Exception:
                    pass
        # 5) 恢复菜单栏
        try:
            mb = getattr(self, '_fs_menu_backup', '') or getattr(self, 'menubar', None)
            self.root.config(menu=mb)
        except Exception:
            pass
        self._fs_on = False
        try:
            self.td_buttons['fullscreen'].config(text='全屏(F11)')
        except Exception:
            pass
        # 6) 让 Qt widget 立即按恢复后尺寸刷新
        try:
            self.root.update_idletasks()
            if self.qt3d_host is not None:
                self.qt3d_host.widget.update()
        except Exception:
            pass

    def _on_escape(self, _evt=None):
        """Esc 退出全屏（仅在全屏时响应）"""
        if getattr(self, '_fs_on', False):
            self._exit_fullscreen()

    def push_qt_mesh(self, vertices, faces):
        """生成蒙皮后把全精度网格推给 Qt 视窗（无 Qt 时静默忽略）。"""
        if self.qt3d_host is not None:
            try:
                self.qt3d_host.set_mesh(vertices, faces)
            except Exception as e:
                self.log('Qt 3D 更新失败：%s' % e)

    # ---------- 首选项 / 文件关联 ----------

    def _register_scs_file_association(self):
        """把 .scs 项目文件注册为 SCS 类型并关联船 logo 图标（HKCU 用户级）。

        只写当前用户注册表（无需管理员权限）；任何一步失败都静默忽略。
        """
        import ctypes
        try:
            import winreg
        except Exception:
            return
        try:
            icon_dir = os.path.abspath(self.icon_dir or 'icon')
            png = os.path.join(icon_dir, '船.png')
            ico = os.path.join(icon_dir, '船.ico')
            if not os.path.exists(ico) and os.path.exists(png):
                try:
                    from PIL import Image
                    im = Image.open(png)
                    im.save(ico, sizes=[(16, 16), (24, 24), (32, 32),
                                        (48, 48), (64, 64), (128, 128), (256, 256)])
                except Exception:
                    ico = png
            if not os.path.exists(ico):
                return
            with winreg.CreateKey(winreg.HKEY_CURRENT_USER, r'Software\Classes\.scs') as k:
                winreg.SetValueEx(k, '', 0, winreg.REG_SZ, 'SCS.ShipProject')
            with winreg.CreateKey(winreg.HKEY_CURRENT_USER,
                                  r'Software\Classes\SCS.ShipProject') as k:
                winreg.SetValueEx(k, '', 0, winreg.REG_SZ, 'SCS 船舶静水力计算项目')
                winreg.SetValueEx(k, 'DefaultIcon', 0, winreg.REG_SZ, ico)
            # 双击 .scs 用本应用打开
            open_cmd = '"%s" "%s" "%%1"' % (
                sys.executable,
                os.path.abspath(os.path.join(os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))),
                                             'main.py')))
            with winreg.CreateKey(winreg.HKEY_CURRENT_USER,
                                  r'Software\Classes\SCS.ShipProject\shell\open\command') as k2:
                winreg.SetValueEx(k2, '', 0, winreg.REG_SZ, open_cmd)
            # 通知 Shell 刷新图标/关联缓存
            try:
                ctypes.windll.shell32.SHChangeNotify(0x08000000, 0, None, None)
            except Exception:
                pass
        except Exception:
            pass

    def _prefs_path(self):
        return os.path.join(os.path.expanduser('~'), 'scs_prefs.json')

    def _load_prefs(self):
        default = {
            'qt3d_background': 'dark',     # dark / gray / light
            'qt3d_invert_rotate': False,
            'qt3d_invert_zoom': False,
            'qt3d_show_axes': True,
            'qt3d_show_grid': True,
            'ui_font_size': 10,            # 9 / 10 / 11 / 12
            'autosave_enabled': True,
            'autosave_interval': 5,        # 分钟
            'recent_projects': [],
        }
        try:
            with open(self._prefs_path(), 'r', encoding='utf-8') as f:
                data = json.load(f)
            if isinstance(data, dict):
                # 允许持久化的扩展键（最近文件列表）被读回，避免“关闭再打开记录消失”
                for k, v in data.items():
                    if k in default or k == 'recent_projects':
                        default[k] = v
        except Exception:
            pass
        return default

    def _save_prefs(self):
        try:
            with open(self._prefs_path(), 'w', encoding='utf-8') as f:
                json.dump(self.prefs, f, ensure_ascii=False, indent=2)
        except Exception:
            pass

    # ---------- 最近打开的项目 ----------

    def _recent_projects(self):
        recent = self.prefs.get('recent_projects', [])
        return [p for p in recent if isinstance(p, str) and p]

    def _add_recent_project(self, path):
        try:
            path = os.path.abspath(path)
            recent = self._recent_projects()
            if path in recent:
                recent.remove(path)
            recent.insert(0, path)
            self.prefs['recent_projects'] = recent[:10]
            self._save_prefs()
            self._rebuild_recent_menu()
        except Exception:
            pass

    def _remove_recent_project(self, path):
        try:
            recent = self._recent_projects()
            if path in recent:
                recent.remove(path)
            self.prefs['recent_projects'] = recent
            self._save_prefs()
            self._rebuild_recent_menu()
        except Exception:
            pass

    def _clear_recent_projects(self):
        try:
            self.prefs['recent_projects'] = []
            self._save_prefs()
            self._rebuild_recent_menu()
        except Exception:
            pass

    def _rebuild_recent_menu(self):
        """重建"文件 > 最近打开"子菜单。"""
        if not hasattr(self, 'm_recent'):
            return
        try:
            self.m_recent.delete(0, 'end')
            recent = self._recent_projects()
            if not recent:
                self.m_recent.add_command(label='（无最近文件）', state='disabled')
            else:
                for p in recent:
                    name = os.path.basename(p) or p
                    self.m_recent.add_command(
                        label=name,
                        command=lambda path=p: self._open_recent(path))
                self.m_recent.add_separator()
                self.m_recent.add_command(label='清空记录',
                                          command=self._clear_recent_projects)
        except Exception:
            pass

    def _apply_qt3d_prefs(self):
        """把首选项应用到 Qt 3D 视窗（未创建时静默）。"""
        if self.qt3d_host is None:
            return
        try:
            self.qt3d_host.set_background_style(self.prefs.get('qt3d_background', 'dark'))
            self.qt3d_host.set_mouse_invert(self.prefs.get('qt3d_invert_rotate', False),
                                            self.prefs.get('qt3d_invert_zoom', False),
                                            self.prefs.get('qt3d_invert_pan', False))
            self.qt3d_host.set_show_axes(bool(self.prefs.get('qt3d_show_axes', True)))
            self.qt3d_host.set_show_grid(bool(self.prefs.get('qt3d_show_grid', True)))
            try:
                self.var_qt_grid.set(1 if self.prefs.get('qt3d_show_grid', True) else 0)
            except Exception:
                pass
        except Exception:
            pass

    def _apply_ui_prefs(self):
        """应用界面偏好：字体大小。保持 Windows 原生外观，仅调整字体与行高。"""
        try:
            size = int(self.prefs.get('ui_font_size', 10))
            size = max(8, min(size, 14))
            font = ('Microsoft YaHei', size)
            style = ttk.Style(self.root)
            style.configure('.', font=font)
            style.configure('Treeview', font=font, rowheight=max(22, size + 11))
            style.configure('Treeview.Heading', font=('Microsoft YaHei', max(size, 10)))
            style.configure('TCombobox', font=font)
            # tk 菜单字体（递归应用，保持菜单清晰）
            self._apply_menu_font(self.root.cget('menu'), size)
        except Exception:
            pass

    def _apply_menu_font(self, menu_name, size):
        try:
            menu = self.root.nametowidget(menu_name) if isinstance(menu_name, str) else menu_name
            menu.configure(font=('Microsoft YaHei', size))
            for i in range(menu.index('end') + 1):
                try:
                    if menu.type(i) == 'cascade':
                        sub = menu.nametowidget(menu.entrycget(i, 'menu'))
                        self._apply_menu_font(sub, size)
                except Exception:
                    continue
        except Exception:
            pass

    # ---------- 帮助 / 诊断 ----------

    def _env_info_text(self):
        import platform
        here = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
        log_dir = os.path.join(here, 'logs')
        L = ['SCS 船舶静水力计算软件', 'Python: %s' % platform.python_version(),
             '系统: %s' % platform.platform()]
        try:
            from src.viewer.qt_3d_viewer import qt_available
            L.append('Qt 3D 视窗: %s' % ('可用' if qt_available() else '不可用(回退 matplotlib)'))
        except Exception:
            L.append('Qt 3D 视窗: 不可用')
        for name, mod in [('numpy', 'numpy'), ('scipy', 'scipy'), ('pandas', 'pandas'),
                          ('sklearn', 'sklearn'), ('matplotlib', 'matplotlib'),
                          ('Pillow', 'PIL'), ('PyQt5', 'PyQt5')]:
            try:
                m = __import__(mod)
                L.append('%s: %s' % (name, getattr(m, '__version__', '?')))
            except Exception:
                L.append('%s: 未安装' % name)
        try:
            import winreg
            with winreg.OpenKey(winreg.HKEY_CURRENT_USER, r'Software\Classes\.scs') as k:
                v, _ = winreg.QueryValueEx(k, '')
            L.append('.scs 文件关联: %s' % v)
        except Exception:
            L.append('.scs 文件关联: 未注册')
        crash = os.path.join(log_dir, 'scs_crash.log')
        L.append('崩溃日志: %s (%s)' % (crash, '存在' if os.path.exists(crash) else '不存在'))
        L.append('调试日志: %s' % os.path.join(log_dir, 'scs_debug.log'))
        return '\n'.join(L)

    def show_diagnostics_clicked(self):
        """诊断信息对话框：环境信息 + 日志查看/导出（稳定对话框模式）。"""
        qt = getattr(self, 'qt3d_host', None)
        if qt is not None:
            try:
                qt.pause()
            except Exception:
                pass
        dlg = None
        try:
            dlg = tk.Toplevel(self.root)
            dlg.title('诊断信息')
            dlg.transient(self.root)
            dlg.geometry('560x460')
            dlg.resizable(True, True)

            text = tk.Text(dlg, wrap='none', font=('Consolas', 9),
                           relief='solid', borderwidth=1)
            sb = ttk.Scrollbar(dlg, orient='vertical', command=text.yview)
            text.configure(yscrollcommand=sb.set)
            text.pack(side='top', fill='both', expand=True, padx=8, pady=(8, 2))
            sb.place(in_=text, relx=1.0, rely=0.0, relheight=1.0, anchor='ne')

            content = self._env_info_text()
            content += '\n\n---- 运行日志 (最近 %d 条) ----\n' % min(len(self.LogBuffer), 200)
            content += '\n'.join(self.LogBuffer[-200:])
            text.insert('1.0', content)
            text.configure(state='disabled')

            btn_row = ttk.Frame(dlg)
            btn_row.pack(fill='x', padx=8, pady=6)

            def _export_log():
                import tkinter.filedialog as filedialog
                path = filedialog.asksaveasfilename(
                    title='导出诊断日志', defaultextension='.txt',
                    filetypes=[('文本文件', '*.txt')], parent=dlg)
                if not path:
                    return
                try:
                    with open(path, 'w', encoding='utf-8') as f:
                        f.write(content)
                    messagebox.showinfo('导出成功', '诊断日志已导出到:\n%s' % path, parent=dlg)
                except Exception as e:
                    messagebox.showerror('导出失败', '导出失败: %s' % e, parent=dlg)

            def _open_crash_log():
                try:
                    root_dir = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
                    crash = os.path.join(root_dir, 'logs', 'scs_crash.log')
                    if not os.path.exists(crash):
                        messagebox.showinfo('提示', '暂无崩溃日志（scs_crash.log）。', parent=dlg)
                        return
                    os.startfile(crash)
                except Exception as e:
                    messagebox.showerror('错误', '打开失败: %s' % e, parent=dlg)

            def _close():
                if qt is not None:
                    try:
                        qt.resume()
                    except Exception:
                        pass
                dlg.destroy()

            ttk.Button(btn_row, text='导出日志', command=_export_log).pack(side='left')
            ttk.Button(btn_row, text='打开崩溃日志', command=_open_crash_log).pack(side='left', padx=6)
            ttk.Button(btn_row, text='关闭', command=_close).pack(side='right')
            dlg.protocol('WM_DELETE_WINDOW', _close)
            self._center_dialog(dlg)
        except Exception as e:
            self.log('诊断信息打开失败：%s' % e)
            if dlg is not None:
                try:
                    dlg.destroy()
                except Exception:
                    pass
            if qt is not None:
                try:
                    qt.resume()
                except Exception:
                    pass

    def about_clicked(self):
        """关于对话框：logo + 版本信息。"""
        try:
            dlg = tk.Toplevel(self.root)
            dlg.title('关于 SCS')
            dlg.transient(self.root)
            dlg.resizable(False, False)
            frame = tk.Frame(dlg, padx=24, pady=18)
            frame.pack()
            try:
                icon_path = os.path.join(self.icon_dir, '船.png')
                if os.path.exists(icon_path):
                    img = tk.PhotoImage(file=icon_path)
                    tk.Label(frame, image=img).pack()
                    dlg._about_img = img  # 防 GC
            except Exception:
                pass
            tk.Label(frame, text='SCS 船舶静水力计算软件',
                     font=('Microsoft YaHei', 13, 'bold')).pack(pady=(8, 2))
            tk.Label(frame, text='Python 移植版 · 与 MATLAB 版同源公式').pack()
            import platform
            tk.Label(frame, text='Python %s' % platform.python_version()).pack(pady=(6, 0))
            tk.Button(frame, text='确定', width=10, command=dlg.destroy).pack(pady=(12, 0))
            self._center_dialog(dlg)
        except Exception:
            pass

    def set_preferences_clicked(self):
        """菜单入口：先暂停 Qt 事件泵，再延迟到菜单回调栈外创建对话框。

        关键：不直接在 Tcl 菜单 command 回调内创建 Toplevel——在 Qt 嵌入
        子窗口存在时，菜单处理栈内新建窗口可能触发重入导致原生崩溃；
        改为 root.after 延迟到菜单完全关闭后再构建，规避该竞态。
        """
        from src.core import dbg
        dbg.log('prefs: clicked')
        qt = getattr(self, 'qt3d_host', None)
        if qt is not None:
            try:
                qt.pause()
                dbg.log('prefs: qt paused')
            except Exception:
                pass
        try:
            self.root.after(30, self._build_preferences_dialog)
            dbg.log('prefs: deferred build scheduled')
        except Exception:
            pass

    def _build_preferences_dialog(self):
        """在菜单回调栈外构建首选项对话框。

        稳定性设计（针对 Qt 嵌入环境下的闪退）：
        - 全部使用 tk 原生控件（不用 ttk.Combobox 的 popdown 下拉窗，
          Tk+Qt 混合下是已知崩溃源；不用 grab_set / wait_visibility）；
        - 确定/取消/关闭都会恢复 Qt 事件泵；任何异常都会兜底恢复。
        """
        from src.core import dbg
        qt = getattr(self, 'qt3d_host', None)
        if getattr(self, '_prefs_dlg_open', False):
            return
        dlg = None
        try:
            dbg.log('prefs: building dlg')
            bg_map = {'深色': 'dark', '中灰': 'gray', '浅色': 'light'}
            bg_rev = {v: k for k, v in bg_map.items()}

            dlg = tk.Toplevel(self.root)
            dbg.log('prefs: toplevel created')
            dlg.title('首选项')
            dlg.transient(self.root)
            dlg.resizable(False, False)
            self._prefs_dlg_open = True
            dbg.log('prefs: building controls')

            pad = {'padx': 10, 'pady': 4}
            frame = tk.Frame(dlg, padx=10, pady=10)
            frame.pack(fill='both', expand=True)

            row = 0
            tk.Label(frame, text='3D曲面背景:').grid(row=row, column=0, sticky='w', **pad)
            bg_var = tk.StringVar(
                value=bg_rev.get(self.prefs.get('qt3d_background', 'dark'), '深色'))
            tk.OptionMenu(frame, bg_var, *list(bg_map.keys())).grid(
                row=row, column=1, sticky='w', **pad)
            row += 1

            rot_var = tk.BooleanVar(value=bool(self.prefs.get('qt3d_invert_rotate', False)))
            tk.Checkbutton(frame, text='旋转方向反转（左键拖动旋转）',
                           variable=rot_var).grid(row=row, column=0, columnspan=2,
                                                  sticky='w', **pad)
            row += 1
            zoom_var = tk.BooleanVar(value=bool(self.prefs.get('qt3d_invert_zoom', False)))
            tk.Checkbutton(frame, text='缩放方向反转（滚轮）',
                           variable=zoom_var).grid(row=row, column=0, columnspan=2,
                                                  sticky='w', **pad)
            row += 1
            pan_var = tk.BooleanVar(value=bool(self.prefs.get('qt3d_invert_pan', False)))
            tk.Checkbutton(frame, text='平移方向反转（中键拖动平移）',
                           variable=pan_var).grid(row=row, column=0, columnspan=2,
                                                  sticky='w', **pad)
            row += 1
            axes_var = tk.BooleanVar(value=bool(self.prefs.get('qt3d_show_axes', True)))
            tk.Checkbutton(frame, text='显示坐标轴',
                           variable=axes_var).grid(row=row, column=0, columnspan=2,
                                                   sticky='w', **pad)
            row += 1
            grid_var = tk.BooleanVar(value=bool(self.prefs.get('qt3d_show_grid', True)))
            tk.Checkbutton(frame, text='显示地面网格',
                           variable=grid_var).grid(row=row, column=0, columnspan=2,
                                                   sticky='w', **pad)
            row += 1

            # ---- 界面 ----
            tk.Label(frame, text='界面字体大小:').grid(row=row, column=0, sticky='w', **pad)
            font_var = tk.StringVar(value=str(int(self.prefs.get('ui_font_size', 10))))
            tk.OptionMenu(frame, font_var, '9', '10', '11', '12').grid(
                row=row, column=1, sticky='w', **pad)
            row += 1

            # ---- 自动保存 ----
            autosave_var = tk.BooleanVar(value=bool(self.prefs.get('autosave_enabled', True)))
            tk.Checkbutton(frame, text='自动保存（保存到独立备份，不覆盖原文件）',
                           variable=autosave_var).grid(row=row, column=0, columnspan=2,
                                                       sticky='w', **pad)
            row += 1
            tk.Label(frame, text='自动保存间隔（分钟）:').grid(
                row=row, column=0, sticky='w', **pad)
            interval_var = tk.StringVar(value=str(int(self.prefs.get('autosave_interval', 5))))
            tk.OptionMenu(frame, interval_var, '1', '2', '5', '10', '15', '30').grid(
                row=row, column=1, sticky='w', **pad)
            row += 1

            btn_row = tk.Frame(frame)
            btn_row.grid(row=row, column=0, columnspan=2, sticky='e', pady=(8, 0))

            closed = {'done': False}

            def _finish():
                if closed['done']:
                    return False
                closed['done'] = True
                try:
                    dlg.destroy()
                except Exception:
                    pass
                try:
                    self._prefs_dlg_open = False
                except Exception:
                    pass
                if qt is not None:
                    try:
                        qt.resume()
                    except Exception:
                        pass
                return True

            def apply(_evt=None):
                if closed['done']:
                    return
                try:
                    self.prefs['qt3d_background'] = bg_map.get(bg_var.get(), 'dark')
                    self.prefs['qt3d_invert_rotate'] = bool(rot_var.get())
                    self.prefs['qt3d_invert_zoom'] = bool(zoom_var.get())
                    self.prefs['qt3d_invert_pan'] = bool(pan_var.get())
                    self.prefs['qt3d_show_axes'] = bool(axes_var.get())
                    self.prefs['qt3d_show_grid'] = bool(grid_var.get())
                    try:
                        self.prefs['ui_font_size'] = int(font_var.get())
                    except Exception:
                        pass
                    self.prefs['autosave_enabled'] = bool(autosave_var.get())
                    try:
                        self.prefs['autosave_interval'] = int(interval_var.get())
                    except Exception:
                        pass
                    self._save_prefs()
                    self._apply_qt3d_prefs()
                    self._apply_ui_prefs()
                except Exception:
                    pass
                finally:
                    _finish()

            def cancel(_evt=None):
                _finish()

            tk.Button(btn_row, text='确定', command=apply, width=8).pack(side='left', padx=(0, 8))
            tk.Button(btn_row, text='取消', command=cancel, width=8).pack(side='left')
            dlg.bind('<Return>', apply)
            dlg.bind('<Escape>', cancel)
            dlg.protocol('WM_DELETE_WINDOW', cancel)

            self._center_dialog(dlg)
            try:
                dlg.lift()
                dlg.focus_force()
            except Exception:
                pass
        except Exception as e:
            self.log('首选项对话框打开失败：%s' % e)
            if dlg is not None:
                try:
                    dlg.destroy()
                except Exception:
                    pass
            try:
                self._prefs_dlg_open = False
            except Exception:
                pass
            if qt is not None:
                try:
                    qt.resume()
                except Exception:
                    pass

    def _center_dialog(self, dlg):
        try:
            self.root.update_idletasks()
            x = self.root.winfo_rootx() + (self.root.winfo_width() - dlg.winfo_reqwidth()) // 2
            y = self.root.winfo_rooty() + (self.root.winfo_height() - dlg.winfo_reqheight()) // 2
            dlg.geometry('+%d+%d' % (max(x, 0), max(y, 0)))
        except Exception:
            pass

    def _build_tab5(self, parent):
        paned = ClampedPanedWindow(parent, orient='vertical', min_sizes=[60, 50, 200])
        paned.pack(fill='both', expand=True)
        ctrl = ttk.LabelFrame(paned, text='浮心计算')
        paned.add(ctrl, weight=0)
        tk.Label(ctrl, text='计算方法:').grid(row=0, column=0, padx=4, pady=2)
        self.var_buoyancy_method = tk.StringVar(value='正浮态(基于水线面)')
        ttk.Combobox(ctrl, textvariable=self.var_buoyancy_method, width=22, state='readonly',
                     values=['正浮态(基于水线面)', '任意浮态(基于横剖面)']).grid(row=0, column=1, padx=4)
        tk.Label(ctrl, text='吃水(m):').grid(row=0, column=2, padx=4)
        self.var_draft = tk.DoubleVar(value=1.0)
        ttk.Spinbox(ctrl, from_=0, to=50, increment=0.1, textvariable=self.var_draft,
                    width=7).grid(row=0, column=3, padx=4)
        tk.Label(ctrl, text='横倾角(°):').grid(row=0, column=4, padx=4)
        self.var_heel = tk.DoubleVar(value=0)
        ttk.Spinbox(ctrl, from_=-90, to=90, textvariable=self.var_heel, width=6).grid(row=0, column=5, padx=4)
        tk.Label(ctrl, text='纵倾角(°):').grid(row=0, column=6, padx=4)
        self.var_trim = tk.DoubleVar(value=0)
        ttk.Spinbox(ctrl, from_=-30, to=30, textvariable=self.var_trim, width=6).grid(row=0, column=7, padx=4)
        ttk.Button(ctrl, text='计算浮心', command=self.buoyancy_calc_clicked).grid(row=0, column=8, padx=6)

        res = ttk.LabelFrame(paned, text='计算结果')
        paned.add(res, weight=0)
        self.var_vol = tk.StringVar(value='')
        self.var_xB = tk.StringVar(value='')
        self.var_yB = tk.StringVar(value='')
        self.var_zB = tk.StringVar(value='')
        for i, (t, v) in enumerate([('排水体积(m³)', self.var_vol), ('浮心X(m)', self.var_xB),
                                    ('浮心Y(m)', self.var_yB), ('浮心Z(m)', self.var_zB)]):
            tk.Label(res, text=t).grid(row=0, column=i * 2, padx=4, pady=2)
            tk.Label(res, textvariable=v, width=16, relief='sunken',
                     anchor='e').grid(row=0, column=i * 2 + 1, padx=4)

        mid = ClampedPanedWindow(paned, orient='horizontal', min_sizes=[300, 150])
        paned.add(mid, weight=4)
        right = ttk.Frame(mid)
        mid.add(right, weight=3)
        self.plot_buoyancy = PlotCanvas(right, toolbar=True)
        self.plot_buoyancy.pack(fill='both', expand=True)
        left = ttk.Frame(mid)
        mid.add(left, weight=1)
        self.TextArea_buoyancy = self._log_text(left, 20)
        self.TextArea_buoyancy.pack(fill='both', expand=True, padx=2, pady=2)

    def _build_tab6(self, parent):
        paned = ClampedPanedWindow(parent, orient='vertical', min_sizes=[60, 50, 200])
        paned.pack(fill='both', expand=True)
        ctrl = ttk.LabelFrame(paned, text='静水力曲线计算')
        paned.add(ctrl, weight=0)
        tk.Label(ctrl, text='最小吃水:').grid(row=0, column=0, padx=4, pady=2)
        self.var_draft_min = tk.DoubleVar(value=0.0)
        ttk.Spinbox(ctrl, from_=0, to=50, increment=0.1, textvariable=self.var_draft_min,
                    width=7).grid(row=0, column=1)
        tk.Label(ctrl, text='最大吃水:').grid(row=0, column=2, padx=4)
        self.var_draft_max = tk.DoubleVar(value=5.0)
        ttk.Spinbox(ctrl, from_=0, to=50, increment=0.1, textvariable=self.var_draft_max,
                    width=7).grid(row=0, column=3)
        tk.Label(ctrl, text='点数:').grid(row=0, column=4, padx=4)
        self.var_draft_steps = tk.IntVar(value=20)
        ttk.Spinbox(ctrl, from_=2, to=200, textvariable=self.var_draft_steps,
                    width=5).grid(row=0, column=5)
        self.var_outlier = tk.BooleanVar(value=False)
        ttk.Checkbutton(ctrl, text='剔除异常点', variable=self.var_outlier).grid(row=0, column=6, padx=4)
        tk.Label(ctrl, text='阈值:').grid(row=0, column=7, padx=4)
        self.var_outlier_th = tk.DoubleVar(value=3.0)
        ttk.Spinbox(ctrl, from_=0.1, to=10, increment=0.1, textvariable=self.var_outlier_th,
                    width=5).grid(row=0, column=8)
        ttk.Button(ctrl, text='计算静水力曲线', command=self.calc_curves_clicked).grid(row=0, column=9, padx=6)

        f = ttk.Frame(paned)
        paned.add(f, weight=0)
        self.TextArea_curves = self._log_text(f, 3)
        self.TextArea_curves.pack(fill='both', expand=True, padx=2, pady=2)

        sub = ttk.Notebook(paned)
        paned.add(sub, weight=5)
        self.curve_plots = {}
        for name in ['水线面面积', '横剖面面积', '排水量', 'TPC', 'MCT', '浮心X', '漂心X',
                     '浮心Z', '稳心高度KM', '船型系数', '综合曲线']:
            page = ttk.Frame(sub)
            sub.add(page, text=name)
            p = PlotCanvas(page, toolbar=True)
            p.pack(fill='both', expand=True)
            self.curve_plots[name] = p

    def _build_tab7(self, parent):
        paned = ClampedPanedWindow(parent, orient='vertical', min_sizes=[60, 50, 200])
        paned.pack(fill='both', expand=True)
        ctrl = ttk.LabelFrame(paned, text='邦戎曲线计算')
        paned.add(ctrl, weight=0)
        tk.Label(ctrl, text='最小吃水:').grid(row=0, column=0, padx=4, pady=2)
        self.var_bonjean_min = tk.DoubleVar(value=0.0)
        ttk.Spinbox(ctrl, from_=0, to=50, textvariable=self.var_bonjean_min, width=7).grid(row=0, column=1)
        tk.Label(ctrl, text='最大吃水:').grid(row=0, column=2, padx=4)
        self.var_bonjean_max = tk.DoubleVar(value=5.0)
        ttk.Spinbox(ctrl, from_=0, to=50, textvariable=self.var_bonjean_max, width=7).grid(row=0, column=3)
        tk.Label(ctrl, text='步数:').grid(row=0, column=4, padx=4)
        self.var_bonjean_steps = tk.IntVar(value=20)
        ttk.Spinbox(ctrl, from_=2, to=200, textvariable=self.var_bonjean_steps, width=5).grid(row=0, column=5)
        self.var_bonjean_all = tk.BooleanVar(value=True)
        ttk.Checkbutton(ctrl, text='全部站号', variable=self.var_bonjean_all,
                        command=self._on_bonjean_all_changed).grid(row=0, column=6, padx=4)
        tk.Label(ctrl, text='指定站号:').grid(row=0, column=7, padx=4)
        self.var_bonjean_station = tk.StringVar(value='0,1,2,3,4,5,6,7,8,9,10')
        ttk.Entry(ctrl, textvariable=self.var_bonjean_station, width=20).grid(row=0, column=8)
        ttk.Button(ctrl, text='计算邦戎曲线', command=self.calc_bonjean_clicked).grid(row=0, column=9, padx=6)

        f = ttk.Frame(paned)
        paned.add(f, weight=0)
        self.TextArea_bonjean = self._log_text(f, 3)
        self.TextArea_bonjean.pack(fill='both', expand=True, padx=2, pady=2)

        sub = ttk.Notebook(paned)
        paned.add(sub, weight=5)
        self.bonjean_plots = {}
        for name in ['面积曲线', '力矩Mz', '形心Z', '综合图']:
            page = ttk.Frame(sub)
            sub.add(page, text=name)
            p = PlotCanvas(page)
            p.pack(fill='both', expand=True)
            self.bonjean_plots[name] = p
        page = ttk.Frame(sub)
        sub.add(page, text='数据表')
        self.Bonjean_table = EditableTable(page, columns=['站号', '吃水', '面积', '形心Y', '形心Z'])
        self.Bonjean_table.pack(fill='both', expand=True)

    def _build_tab8(self, parent):
        paned = ClampedPanedWindow(parent, orient='vertical', min_sizes=[60, 80, 200])
        paned.pack(fill='both', expand=True)
        ctrl = ttk.LabelFrame(paned, text='稳性计算')
        paned.add(ctrl, weight=0)
        tk.Label(ctrl, text='横倾角(如 0:10:90):').grid(row=0, column=0, padx=4, pady=2)
        self.var_stab_heels = tk.StringVar(value='0:10:90')
        ttk.Entry(ctrl, textvariable=self.var_stab_heels, width=14).grid(row=0, column=1)
        tk.Label(ctrl, text='吃水(如 1:1:5):').grid(row=0, column=2, padx=4)
        self.var_stab_drafts = tk.StringVar(value='1:1:5')
        ttk.Entry(ctrl, textvariable=self.var_stab_drafts, width=14).grid(row=0, column=3)
        ttk.Button(ctrl, text='计算KN曲线', command=self.calc_kn_clicked).grid(row=0, column=4, padx=4)
        ttk.Button(ctrl, text='计算GZ曲线', command=self.calc_gz_clicked).grid(row=0, column=5, padx=4)
        ttk.Button(ctrl, text='计算动稳性', command=self.calc_dynamic_clicked).grid(row=0, column=6, padx=4)
        ttk.Button(ctrl, text='导出稳性报告', command=self.export_stability).grid(row=0, column=7, padx=4)
        # 与 MATLAB 一致：单独导出 KN 数据 / GZ 数据
        ttk.Button(ctrl, text='导出KN数据', command=self.export_kn).grid(row=1, column=4, padx=4)
        ttk.Button(ctrl, text='导出GZ数据', command=self.export_gz).grid(row=1, column=5, padx=4)
        tk.Label(ctrl, text='稳性衡准数K:').grid(row=0, column=8, padx=(12, 2))
        self.var_stab_k = tk.StringVar(value='未计算')
        tk.Label(ctrl, textvariable=self.var_stab_k, fg='gray').grid(row=0, column=9, padx=4)

        f = ttk.Frame(paned)
        paned.add(f, weight=0)
        self.TextArea_stability = self._log_text(f, 5)
        self.TextArea_stability.pack(fill='both', expand=True, padx=2, pady=2)

        sub = ttk.Notebook(paned)
        paned.add(sub, weight=5)
        self.stability_plots = {}
        for name in ['KN曲线', 'GZ曲线', '动稳性', '3D稳性曲面']:
            page = ttk.Frame(sub)
            sub.add(page, text=name)
            p = PlotCanvas(page, three_d=(name == '3D稳性曲面'), toolbar=True)
            p.pack(fill='both', expand=True)
            self.stability_plots[name] = p

    # =====================================================================
    # 日志 / 撤销
    # =====================================================================
    def log(self, msg, level='info'):
        self.LogBuffer.append(str(msg))
        if len(self.LogBuffer) > 500:
            self.LogBuffer.pop(0)
        try:
            self.TextArea_debug.insert('end', str(msg) + '\n')
            self.TextArea_debug.see('end')
        except Exception:
            pass
        try:
            if self.isTap == 3:
                self.TextArea_debug_3.insert('end', str(msg) + '\n')
                self.TextArea_debug_3.see('end')
            elif self.isTap == 4:
                self.TextArea_debug_4.insert('end', str(msg) + '\n')
                self.TextArea_debug_4.see('end')
        except Exception:
            pass
        try:
            print(msg)
        except UnicodeEncodeError:
            # 控制台编码（如 GBK）无法显示部分 Unicode 字符时的兜底
            import sys
            try:
                if hasattr(sys.stdout, 'reconfigure'):
                    sys.stdout.reconfigure(errors='replace')
                    print(msg)
                else:
                    print(str(msg).encode('ascii', errors='replace').decode('ascii'))
            except Exception:
                pass

    def clear_logs(self):
        for w in [self.TextArea_debug, self.TextArea_debug_3, self.TextArea_debug_4]:
            try:
                w.delete('1.0', 'end')
            except Exception:
                pass

    def _on_tab_changed(self, event):
        # isTap 采用"逻辑页编号"而非物理索引：用户可拖拽重排 tab，
        # 只有按标题识别功能页，工具栏/页内按钮启用逻辑才始终正确。
        try:
            text = self.notebook.tab(self.notebook.select(), 'text') or ''
        except Exception:
            text = ''
        order = ['原表格', '半宽', '横剖面', '3D曲面', '浮心', '静力曲线', '邦戎曲线', '稳性']
        if text in order:
            self.isTap = order.index(text) + 1
        else:
            try:
                self.isTap = self.notebook.index(self.notebook.select()) + 1
            except Exception:
                self.isTap = 1
        self._update_button_state()
        self._refresh_statusbar()
        # 模拟 MATLAB 各 Tab ButtonDown 的初始绘图刷新
        if self.isTap == 2:
            self.update_half_width_plot()
        elif self.isTap == 3:
            self.update_transverse_section_plot()

    def _save_undo(self, table, desc):
        state = {'table': table, 'desc': desc}
        if table == 'Half_table':
            state['data'] = self.Half_table.get_data()
            state['columns'] = self.Half_table.get_columns()
        elif table == 'Z_table':
            state['data'] = self.Z_table.get_data()
            state['columns'] = self.Z_table.get_columns()
        self.UndoStack.append(state)
        if len(self.UndoStack) > self.UndoMaxSize:
            self.UndoStack.pop(0)
        self._mark_dirty()

    def _mark_dirty(self):
        """标记项目有未保存更改"""
        self._dirty = True
        try:
            if not str(self.root.title()).endswith(' *'):
                self.root.title(str(self.root.title()) + ' *')
        except Exception:
            pass
        self._refresh_statusbar()

    def _clear_dirty(self):
        """保存/加载成功后清除未保存标记"""
        self._dirty = False
        try:
            t = str(self.root.title())
            if t.endswith(' *'):
                self.root.title(t[:-2])
        except Exception:
            pass
        self._refresh_statusbar()

    def _on_close(self):
        """窗口关闭前检查未保存更改"""
        if self._dirty:
            ans = messagebox.askyesnocancel(
                '未保存的更改',
                '当前项目有未保存的更改，是否先保存？\n'
                '（是=保存；否=不保存直接退出；取消=返回）',
                parent=self.root)
            if ans is None:
                return
            if ans:
                self.menu_save_project()
                if self._dirty:
                    return  # 用户取消保存或保存失败
        self.root.destroy()

    def undo(self):
        if not self.UndoStack:
            messagebox.showinfo('提示', '没有可撤销的操作。', parent=self.root)
            return
        state = self.UndoStack.pop()
        if state['table'] == 'Half_table':
            self.Half_table.set_columns(state['columns'])
            self.Half_table.set_data(state['data'])
        elif state['table'] == 'Z_table':
            self.Z_table.set_columns(state['columns'])
            self.Z_table.set_data(state['data'])
        self.log('[撤销] %s - 已恢复' % state['desc'])

    # =====================================================================
    # 设置类动作
    # =====================================================================
    def set_method(self, method):
        self.CoefficientMethod = method
        names = {'trapezoidal': '梯形法', 'simp1': '辛普森1/3', 'simp2': '辛普森3/8'}
        self.log('已选择系数法：%s' % names.get(method, method))
        self._refresh_statusbar()
        messagebox.showinfo('系数法选择', '已选择%s。将根据此方法在计算时应用。' % names.get(method, method),
                            parent=self.root)

    def set_origin(self, origin):
        self.OriginFlag = origin
        names = {'amidship': '船中', 'stern': '船尾', 'bow': '船首'}
        self.log('原点已设为%s' % names.get(origin, origin))
        self._refresh_statusbar()
        messagebox.showinfo('设置成功', '原点已设为%s' % names.get(origin, origin), parent=self.root)

    def set_wiremode(self, mode):
        self.WireframeMode = mode
        self.var_wiremode.set(mode)
        self.log('线框模式已设为：%s' % mode)

    # =====================================================================
    # 查看类动作
    # =====================================================================
    def _info_dialog(self, title, lines):
        from src.ui.ui_widgets import ask_multiline_input
        dlg = tk.Toplevel(self.root)
        dlg.title(title)
        dlg.geometry('520x400')
        txt = tk.Text(dlg, wrap='none', font=('Consolas', 10))
        txt.pack(fill='both', expand=True, padx=6, pady=6)
        txt.insert('1.0', '\n'.join(str(x) for x in lines))
        txt.configure(state='disabled')
        ttk.Button(dlg, text='关闭', command=dlg.destroy).pack(pady=4)

    def view_principal_dim(self):
        lines = ['========== 船舶主尺度 ==========', '']
        lines.append('垂线间长 Lpp: %.3f m' % self.Lpp if math.isfinite(self.Lpp) else '垂线间长 Lpp: 未设置')
        lines.append('型宽 B: %.3f m' % self.Breadth if math.isfinite(self.Breadth) else '型宽 B: 未设置')
        lines.append('型深 D: %.3f m' % self.Depth if math.isfinite(self.Depth) else '型深 D: 未设置')
        if math.isfinite(self.LppStartStation) and math.isfinite(self.LppEndStation):
            lines.append('Lpp始末站号: %.1f ~ %.1f' % (self.LppStartStation, self.LppEndStation))
        else:
            lines.append('Lpp始末站号: 未设置')
        lines += ['', '原点位置: %s' % self.OriginFlag, '系数方法: %s' % self.CoefficientMethod]
        self._info_dialog('主尺度信息', lines)

    def view_hydrostatics(self):
        if self.Hydrostatics is None or len(self.Hydrostatics.get('drafts', [])) == 0:
            messagebox.showinfo('数据缺失', '尚未计算静水力数据，请先在"静力曲线"标签页进行计算。',
                                parent=self.root)
            return
        hs = self.Hydrostatics
        lines = ['吃水(m)\t排水量(t)\t排水体积(m³)\tTPC(t/cm)\tMCT(t·m/cm)\tVCB(m)\tLCB(m)\tLCF(m)\tKMT(m)\tKML(m)\tCb\tCp\tCm\tCw']
        for i, d in enumerate(hs['drafts']):
            def g(k, i=i):
                arr = hs.get(k)
                return '' if arr is None else ('%.4f' % arr[i])
            lines.append('\t'.join(['%.3f' % d, g('dispMass'), g('dispVolume'), g('TPC'),
                                    g('MCT'), g('VCB'), g('LCB'), g('LCF'), g('KMT'),
                                    g('KML'), g('CB'), g('CP'), g('CM'), g('CW')]))
        self._info_dialog('静水力数据表', lines)

    def view_bonjean(self):
        if self.BonjeanCurves is None:
            messagebox.showinfo('数据缺失', '尚未计算邦戎曲线数据，请先在"邦戎曲线"标签页进行计算。',
                                parent=self.root)
            return
        self.notebook.select(6)  # 邦戎曲线 Tab
        self.log('已切换到邦戎曲线数据表视图')

    def view_stability(self):
        if self.GZ_CurveData is None:
            messagebox.showinfo('数据缺失', '尚未计算稳性数据，请先在"稳性计算"标签页进行计算。',
                                parent=self.root)
            return
        g = self.GZ_CurveData
        lines = ['========== 稳性计算结果 ==========', '']
        lines.append('排水量: %.2f t' % g.get('Displacement', 0))
        lines.append('重心高度 KG: %.3f m' % g.get('KG', 0))
        lines.append('')
        lines.append('--- GZ曲线数据 ---')
        heels = np.asarray(g['HeelAngles'])
        gz = np.asarray(g['GZ_Values'])
        lines.append('横倾角范围: %.1f° ~ %.1f°' % (np.min(heels), np.max(heels)))
        lines.append('最大GZ值: %.4f m' % np.max(gz))
        lines.append('最大GZ对应角度: %.1f°' % heels[int(np.argmax(gz))])
        self._info_dialog('稳性数据', lines)

    def view_data_summary(self):
        lines = ['╔══════════════════════════════════════╗',
                 '║          船舶数据汇总报告            ║',
                 '╚══════════════════════════════════════╝', '']
        lines.append('【主尺度】')
        if math.isfinite(self.Lpp):
            lines.append('  Lpp = %.3f m' % self.Lpp)
        if math.isfinite(self.Breadth):
            lines.append('  B = %.3f m' % self.Breadth)
        if math.isfinite(self.Depth):
            lines.append('  D = %.3f m' % self.Depth)
        lines.append('')
        lines.append('【静水力数据】')
        if self.Hydrostatics and len(self.Hydrostatics.get('drafts', [])):
            lines.append('  ✓ 已计算 (%d 个吃水点)' % len(self.Hydrostatics['drafts']))
        else:
            lines.append('  ✗ 未计算')
        lines.append('')
        lines.append('【邦戎曲线】')
        if self.BonjeanCurves is not None:
            lines.append('  ✓ 已计算')
        else:
            lines.append('  ✗ 未计算')
        lines.append('')
        lines.append('【稳性数据】')
        if self.GZ_CurveData is not None:
            lines.append('  ✓ GZ曲线已计算')
        else:
            lines.append('  ✗ 未计算')
        lines.append('')
        lines.append('【型值数据】')
        lines.append('  水线面数据: %d 条' % len(self.waterlines))
        lines.append('  横剖面数据: %d 条' % len(self.bodyplans))
        self._info_dialog('数据汇总报告', lines)

    def zoom_reset(self):
        self.log('已重置所有图表的缩放')
        messagebox.showinfo('操作完成', '已重置所有图表的缩放范围', parent=self.root)

    def refresh_plots(self):
        self.update_half_width_plot()
        self.update_transverse_section_plot()
        self.log('已刷新所有图表')
