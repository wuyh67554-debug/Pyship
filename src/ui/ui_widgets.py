# -*- coding: utf-8 -*-
"""
ui_widgets.py —— 可复用 UI 组件
- EditableTable：Excel 风格可编辑表格（ttk.Treeview + 双击编辑）
- PlotCanvas：matplotlib 内嵌绘图画布（2D/3D）
- 通用对话框辅助函数
"""

import copy
import os
import time
import tkinter as tk
from tkinter import ttk, filedialog, messagebox
import math
import numpy as np

import matplotlib
matplotlib.use('TkAgg')
from matplotlib.backends.backend_tkagg import FigureCanvasTkAgg, NavigationToolbar2Tk
from matplotlib.figure import Figure
from matplotlib import rcParams

# 中文字体支持
rcParams['font.sans-serif'] = ['Microsoft YaHei', 'SimHei', 'Arial Unicode MS', 'DejaVu Sans']
rcParams['axes.unicode_minus'] = False
# 工业软件：坐标轴使用朴素样式（不额外上色）
rcParams['axes.facecolor'] = 'white'
rcParams['axes.edgecolor'] = 'black'
rcParams['axes.labelcolor'] = 'black'
rcParams['xtick.color'] = 'black'
rcParams['ytick.color'] = 'black'
rcParams['text.color'] = 'black'
rcParams['axes.grid'] = True
rcParams['grid.color'] = '#b0b0b0'
rcParams['grid.linestyle'] = ':'
rcParams['grid.linewidth'] = 0.7


# =====================================================================
# 输入撤销支持（Ctrl+Z 撤销 / Ctrl+Y、Ctrl+Shift+Z 重做）
# =====================================================================
# Tk 的 tk.Text 自带撤销栈（默认关闭，需 undo=True）；
# 但 tk.Entry / ttk.Entry 既没有 -undo 选项也没有 edit_undo()，
# 因此这里为每个 Entry 自行维护快照式撤销/重做栈。

_UNDO_DEPTH = 200        # 每个控件最多保留的撤销步数
_UNDO_MERGE_SEC = 0.8    # 连续输入在该时间窗内合并为一步

_entry_states = {}


def _set_entry_value(widget, value):
    """写入 Entry / Spinbox / Combobox 的值"""
    if isinstance(widget, ttk.Combobox):
        widget.set(value)
    else:
        widget.delete(0, 'end')
        widget.insert(0, value)


def _entry_state(widget):
    """取（必要时创建）某个 Entry 的撤销状态"""
    st = _entry_states.get(widget)
    if st is not None:
        return st
    try:
        cur = widget.get()
    except Exception:
        cur = ''
    st = {'undo': [], 'redo': [], 'last': cur, 'ts': 0.0, 'busy': False}
    _entry_states[widget] = st

    def _on_destroy(_event):
        _entry_states.pop(widget, None)

    try:
        widget.bind('<Destroy>', _on_destroy)
    except Exception:
        pass
    return st


def _entry_snapshot(widget):
    """值发生变化时记录一个撤销点"""
    st = _entry_state(widget)
    if st['busy']:
        return
    try:
        cur = widget.get()
    except Exception:
        return
    prev = st['last']
    if cur == prev:
        return
    now = time.time()
    # 连续单字符输入合并为一步，避免"敲一个字符要撤销一次"
    merge = (now - st['ts'] < _UNDO_MERGE_SEC and
             abs(len(cur) - len(prev)) == 1 and
             (cur.startswith(prev) or prev.startswith(cur)))
    if not merge:
        st['undo'].append(prev)
        if len(st['undo']) > _UNDO_DEPTH:
            st['undo'].pop(0)
    st['redo'].clear()
    st['last'] = cur
    st['ts'] = now


def _entry_undo(widget):
    st = _entry_state(widget)
    if not st['undo']:
        return False
    st['redo'].append(widget.get())
    val = st['undo'].pop()
    st['busy'] = True
    try:
        _set_entry_value(widget, val)
        st['last'] = val
    except Exception:
        return False
    finally:
        st['busy'] = False
    st['ts'] = 0.0
    return True


def _entry_redo(widget):
    st = _entry_state(widget)
    if not st['redo']:
        return False
    st['undo'].append(widget.get())
    val = st['redo'].pop()
    st['busy'] = True
    try:
        _set_entry_value(widget, val)
        st['last'] = val
    except Exception:
        return False
    finally:
        st['busy'] = False
    st['ts'] = 0.0
    return True


def install_undo_support(root):
    """为所有输入控件启用 Ctrl+Z / Ctrl+Y 撤销重做。

    基于 bind_class 类级绑定，对调用之后动态创建的控件（含各模态对话框）同样生效。
    应在构建界面之前调用。
    """
    try:
        root.option_add('*Text.undo', 1)      # tk.Text 启用内置撤销栈
        root.option_add('*Text.maxundo', 0)   # 0 = 不限步数
    except Exception:
        pass

    # option_add 在部分 Tk 构建中对 Text.undo 不生效，这里在首次映射时兜底开启
    def _enable_text_undo(event):
        w = event.widget
        try:
            if isinstance(w, tk.Text) and not w.cget('undo'):
                w.configure(undo=True, maxundo=0)
        except Exception:
            pass

    root.bind_class('Text', '<Map>', _enable_text_undo, add='+')
    root.bind_class('Text', '<FocusIn>', _enable_text_undo, add='+')

    def _undo(event):
        w = event.widget
        try:
            if isinstance(w, tk.Text):
                w.edit_undo()
            else:
                _entry_undo(w)
        except Exception:
            pass
        return 'break'

    def _redo(event):
        w = event.widget
        try:
            if isinstance(w, tk.Text):
                w.edit_redo()
            else:
                _entry_redo(w)
        except Exception:
            pass
        return 'break'

    def _mark(event):
        _entry_snapshot(event.widget)

    # Text 用内置栈，Entry/Spinbox/Combobox 用自定义栈
    for cls in ('Entry', 'TEntry', 'Text', 'Spinbox', 'TSpinbox',
                'TCombobox'):
        root.bind_class(cls, '<Control-z>', _undo)
        root.bind_class(cls, '<Control-Z>', _undo)
        root.bind_class(cls, '<Control-y>', _redo)
        root.bind_class(cls, '<Control-Y>', _redo)
        root.bind_class(cls, '<Control-Shift-Z>', _redo)

    for cls in ('Entry', 'TEntry', 'Spinbox', 'TSpinbox', 'TCombobox'):
        root.bind_class(cls, '<KeyRelease>', _mark, add='+')
        root.bind_class(cls, '<<Paste>>', _mark, add='+')
        root.bind_class(cls, '<FocusIn>', _mark, add='+')


# =====================================================================
# 带尺寸限制的 PanedWindow
# =====================================================================

class ClampedPanedWindow(ttk.PanedWindow):
    """
    限制拖拽拉杆（sash）范围的 PanedWindow，避免窗格被拖到过小/过大导致布局错乱。

    用法：
        pw = ClampedPanedWindow(parent, orient='horizontal',
                                min_sizes=[150, 250],
                                init_sash=[260])
        pw.add(pane1); pw.add(pane2)
    min_sizes:  每个窗格的最小尺寸（横向为最小宽度，纵向为最小高度）
    init_sash:  启动后首次显示时各拉杆的初始位置（像素），
                留空则交给 Tk 默认（首格宽 0）。
                位置会被夹在 [min_pos, max_pos] 范围内，避免被钳制回 0。
    """

    def __init__(self, master, orient='horizontal', min_sizes=None,
                 init_sash=None, **kw):
        super().__init__(master, orient=orient, **kw)
        self._min_sizes = list(min_sizes or [])
        self._init_sash = list(init_sash or [])
        self._panes = []
        self._sash_initialized = False
        self.bind('<B1-Motion>', self._clamp)
        self.bind('<ButtonRelease-1>', self._clamp)
        # 首次映射到屏幕后再设置初始拉杆位置，
        # 避免构建期间因 winfo_width=0 导致 sashpos 静默失败
        self.bind('<Map>', self._on_first_map)

    def add(self, child, **kw):
        self._panes.append(child)
        return super().add(child, **kw)

    def clear_min_sizes(self):
        """清空最小尺寸限制（某些窗格内容动态变化时）"""
        self._min_sizes = []

    def _on_first_map(self, _event=None):
        if self._sash_initialized:
            return
        self._sash_initialized = True
        # 让 Tk 先完成一次几何计算
        self.update_idletasks()
        n = len(self._panes)
        for i, pos in enumerate(self._init_sash):
            if i >= n - 1:
                break
            try:
                p = max(0, int(pos))
                self.sashpos(i, p)
            except Exception:
                pass
        # 兜底：把任何被默认成 0 / 超界的拉杆夹回 min_sizes 范围内
        self._clamp()

    def _clamp(self, event=None):
        n = len(self._panes)
        if n < 2:
            return
        total = self.winfo_width() if str(self.cget('orient')) == 'horizontal' \
            else self.winfo_height()
        if total < 50:
            return
        for i in range(n - 1):
            min_pos = sum(self._min_sizes[:i + 1])
            max_pos = total - sum(self._min_sizes[i + 1:])
            if max_pos < min_pos:
                max_pos = min_pos
            try:
                pos = self.sashpos(i)
                if pos < min_pos:
                    self.sashpos(i, min_pos)
                elif pos > max_pos:
                    self.sashpos(i, max_pos)
            except Exception:
                pass


# 可编辑表格
# =====================================================================

class _CellOutline:
    """Excel 风格活动单元格边框：四条细线拼成矩形，不遮挡单元格内容。"""

    def __init__(self, master):
        self._parts = [tk.Frame(master, bg='black', bd=0, highlightthickness=0)
                       for _ in range(4)]

    def show(self, x, y, w, h, thick=2):
        top, bottom, left, right = self._parts
        top.place(x=x, y=y, width=w, height=thick)
        bottom.place(x=x, y=y + max(h - thick, 0), width=w, height=thick)
        left.place(x=x, y=y, width=thick, height=h)
        right.place(x=x + max(w - thick, 0), y=y, width=thick, height=h)

    def hide(self):
        for f in self._parts:
            f.place_forget()


class EditableTable(ttk.Frame):
    """Excel 模式可编辑表格。

    - 左侧行号列 + 顶部列标题（Excel 外观）
    - 单击选中单元格；方向键 / Tab / Enter / Home / End / PageUp / PageDown 移动活动单元格
    - 双击、F2 或直接键入进入编辑
    - Ctrl+C / Ctrl+X / Ctrl+V：以 TSV 与 Excel 互通复制、剪切、粘贴
    - Delete 清空选区、Ctrl+D 向下填充、右键菜单
    - Ctrl+Z 撤销 / Ctrl+Y、Ctrl+Shift+Z 重做
    """

    def __init__(self, master, columns=None, editable=True, height=10, **kw):
        super().__init__(master, **kw)
        self._columns = list(columns) if columns else []
        self._editable = editable
        self._data = []  # list[list]
        self._on_edit_callback = None       # 变更后：func(row, col, old, new)
        self._on_before_edit_callback = None  # 变更前：func(row, col, old, new)
        self._on_selection_callback = None

        self._cur = None      # 活动单元格 (row, col)
        self._anchor = None   # 选区锚点 (row, col)
        self._undo_stack = []
        self._redo_stack = []
        self._undo_depth = 100
        self._edit_entry = None
        self._editing = None  # 正在编辑的 (row, col)

        self.tree = ttk.Treeview(self, show='tree headings', height=height,
                                 selectmode='browse')
        self.vsb = ttk.Scrollbar(self, orient='vertical', command=self.tree.yview)
        self.hsb = ttk.Scrollbar(self, orient='horizontal', command=self.tree.xview)
        self.tree.configure(yscrollcommand=self.vsb.set, xscrollcommand=self.hsb.set)
        self.tree.grid(row=0, column=0, sticky='nsew')
        self.vsb.grid(row=0, column=1, sticky='ns')
        self.hsb.grid(row=1, column=0, sticky='ew')
        self.grid_rowconfigure(0, weight=1)
        self.grid_columnconfigure(0, weight=1)

        self._outline = _CellOutline(self.tree)

        self._refresh_columns()
        self._bind_events()

    # ---------- 列标识 ----------
    @staticmethod
    def _cid(col):
        return 'c%d' % col

    @staticmethod
    def _col_from_display(disp):
        """'#1' -> 0（#0 为行号列，不参与数据列）"""
        try:
            return int(disp[1:]) - 1
        except (ValueError, IndexError, TypeError):
            return 0

    # ---------- 列管理 ----------
    def _refresh_columns(self):
        self.tree.delete(*self.tree.get_children())
        n = len(self._columns)
        self.tree['columns'] = [self._cid(i) for i in range(n)]
        # '#0' 为 Excel 风格行号列
        self.tree.heading('#0', text='')
        self.tree.column('#0', width=48, minwidth=40, anchor='center', stretch=False)
        for i, col in enumerate(self._columns):
            self.tree.heading(self._cid(i), text=str(col))
            self.tree.column(self._cid(i), width=100, anchor='center', stretch=True)

    def set_columns(self, columns):
        self._columns = list(columns)
        self._refresh_columns()

    def get_columns(self):
        return list(self._columns)

    # ---------- 数据管理 ----------
    def set_data(self, data):
        """程序化装载数据（不进撤销栈；用户编辑才记撤销点）"""
        self._data = []
        for row in data or []:
            vals = list(row)
            while len(vals) < len(self._columns):
                vals.append('')
            self._data.append(vals)
        self._reload()

    def get_data(self):
        return [list(r) for r in self._data]

    def get_data_as_columns(self):
        """返回按列组织的 dict: colname -> list"""
        cols = {}
        for c in range(len(self._columns)):
            cols[self._columns[c]] = [row[c] if c < len(row) else '' for row in self._data]
        return cols

    def add_row(self, values=None):
        n = len(self._columns)
        vals = list(values) if values is not None else [''] * n
        while len(vals) < n:
            vals.append('')
        self._data.append(vals)
        self._reload()

    def delete_last_row(self):
        if self._data:
            self._data.pop()
            self._reload()

    def clear(self):
        self.set_data([])

    def row_count(self):
        return len(self._data)

    def column_count(self):
        return len(self._columns)

    def set_cell(self, row, col, value):
        """程序化写单元格（不进撤销栈）"""
        if 0 <= row < len(self._data) and 0 <= col < len(self._columns):
            self._data[row][col] = value
            self._refresh_row(row)

    def get_cell(self, row, col):
        if 0 <= row < len(self._data) and 0 <= col < len(self._columns):
            return self._data[row][col]
        return ''

    def set_editable(self, editable):
        self._editable = editable

    def set_row_index_column(self, col_index=0):
        """将指定列设置为行号（1..n）"""
        for i, row in enumerate(self._data):
            if col_index < len(row):
                self._data[i][col_index] = i + 1
        self._reload()

    # ---------- 内部：行渲染 ----------
    def _iid(self, row):
        return 'r%d' % row

    def _reload(self):
        """按 self._data 重建所有行"""
        self.tree.delete(*self.tree.get_children())
        ncol = len(self._columns)
        for i, row in enumerate(self._data):
            vals = list(row) + [''] * (ncol - len(row))
            self.tree.insert('', 'end', iid=self._iid(i), text=str(i + 1),
                             values=[self._fmt(v) for v in vals[:ncol]])
        self._update_outline()

    def _refresh_row(self, row):
        iid = self._iid(row)
        if not self.tree.exists(iid):
            self._reload()
            return
        ncol = len(self._columns)
        vals = list(self._data[row]) + [''] * (ncol - len(self._data[row]))
        for c in range(ncol):
            self.tree.set(iid, self._cid(c), self._fmt(vals[c]))
        self.tree.item(iid, text=str(row + 1))

    # ---------- 显示格式 ----------
    @staticmethod
    def _fmt(v):
        if isinstance(v, (int, np.integer)):
            return str(int(v))
        if isinstance(v, (float, np.floating)):
            if math.isnan(v) or not math.isfinite(v):
                return ''
            if abs(v - round(v)) < 1e-10:
                return str(int(round(v)))
            return ('%.10f' % v).rstrip('0').rstrip('.')
        if v is None:
            return ''
        return str(v)

    # ---------- 事件绑定 ----------
    def _bind_events(self):
        t = self.tree
        t.bind('<Button-1>', self._on_click)
        t.bind('<Double-1>', self._on_double_click)
        t.bind('<Button-3>', self._on_right_click)
        t.bind('<Key>', self._on_key)
        t.bind('<F2>', self._on_f2)
        t.bind('<Delete>', lambda e: self.clear_selection())
        t.bind('<Control-c>', self._copy)
        t.bind('<Control-C>', self._copy)
        t.bind('<Control-x>', self._cut)
        t.bind('<Control-X>', self._cut)
        t.bind('<Control-v>', self._paste)
        t.bind('<Control-V>', self._paste)
        t.bind('<Control-d>', self._fill_down)
        t.bind('<Control-D>', self._fill_down)
        t.bind('<Control-z>', self._undo)
        t.bind('<Control-Z>', self._undo)
        t.bind('<Control-y>', self._redo)
        t.bind('<Control-Y>', self._redo)
        t.bind('<Control-Shift-Z>', self._redo)
        t.bind('<<TreeviewSelect>>', self._on_select)
        t.bind('<FocusOut>', self._on_focus_out)
        t.bind('<Configure>', lambda e: self._update_outline())
        self.vsb.configure(command=self._on_scroll)
        self.hsb.configure(command=self._on_xscroll)

    def _on_scroll(self, *args):
        self.tree.yview(*args)
        self._update_outline()

    def _on_xscroll(self, *args):
        self.tree.xview(*args)
        self._update_outline()

    def _on_select(self, event):
        if self._on_selection_callback:
            self._on_selection_callback(event)

    def _on_focus_out(self, event):
        self._end_edit(commit=True)

    # ---------- 活动单元格 ----------
    def _set_current(self, row, col):
        n = len(self._data)
        m = len(self._columns)
        if n == 0 or m == 0:
            self._cur = None
            self._outline.hide()
            return
        row = max(0, min(row, n - 1))
        col = max(0, min(col, m - 1))
        self._cur = (row, col)
        iid = self._iid(row)
        if self.tree.exists(iid):
            self.tree.see(iid)
        self._update_outline()

    def _update_outline(self):
        if self._cur is None:
            self._outline.hide()
            return
        row, col = self._cur
        iid = self._iid(row)
        if not self.tree.exists(iid) or col >= len(self._columns):
            self._outline.hide()
            return
        try:
            bbox = self.tree.bbox(iid, self._cid(col))
        except Exception:
            bbox = None
        if not bbox:
            self._outline.hide()
            return
        x, y, w, h = bbox
        self._outline.show(x, y, w, h)

    def _move(self, dr, dc, extend=False):
        if self._cur is None:
            self._set_current(0, 0)
            return
        row, col = self._cur
        if not extend:
            self._anchor = (row, col)
        self._set_current(row + dr, col + dc)

    # ---------- 选区 ----------
    def _selection_range(self):
        """返回规范化的选区 (r0, c0, r1, c1)，无数据返回 None"""
        if self._cur is None or not self._data or not self._columns:
            return None
        a = self._anchor or self._cur
        r0, r1 = sorted((a[0], self._cur[0]))
        c0, c1 = sorted((a[1], self._cur[1]))
        return (max(0, r0), max(0, c0),
                min(r1, len(self._data) - 1), min(c1, len(self._columns) - 1))

    def _iter_range(self):
        rng = self._selection_range()
        if not rng:
            return
        r0, c0, r1, c1 = rng
        for r in range(r0, r1 + 1):
            for c in range(c0, c1 + 1):
                yield r, c

    # ---------- 编辑 ----------
    def _on_click(self, event):
        region = self.tree.identify('region', event.x, event.y)
        if region not in ('cell', 'tree'):
            return
        row_id = self.tree.identify_row(event.y)
        if not row_id:
            return
        row = self.tree.index(row_id)
        disp = self.tree.identify_column(event.x)
        if disp == '#0':
            # 点击行号列：整行选中（Excel 行为）
            self._anchor = (row, 0)
            self._cur = (row, len(self._columns) - 1)
            self._set_current(row, 0)
        else:
            col = self._col_from_display(disp)
            if not (event.state & 0x0001):   # 未按 Shift：重置锚点
                self._anchor = (row, col)
            self._set_current(row, col)
        self.tree.selection_set(row_id)
        self.tree.focus_set()

    def _on_double_click(self, event):
        if not self._editable:
            return
        if self._cur is None:
            return
        row, col = self._cur
        self._begin_edit(row, col)

    def _on_f2(self, event):
        if not self._editable or self._cur is None:
            return
        row, col = self._cur
        self._begin_edit(row, col)
        return 'break'

    def _on_key(self, event):
        """键盘导航与"直接键入即编辑"（Excel 行为）"""
        if self._editing is not None:
            return None
        # 带 Ctrl/Alt 的组合键交给专门的绑定处理
        if event.state & 0x0004 or event.state & 0x0008 or event.state & 0x20000:
            return None
        if not self._data or not self._columns:
            return None
        if self._cur is None:
            self._set_current(0, 0)
        row, col = self._cur
        shift = bool(event.state & 0x0001)
        ks = event.keysym
        nav = {'Up': (-1, 0), 'Down': (1, 0), 'Left': (0, -1), 'Right': (0, 1)}
        if ks in nav:
            dr, dc = nav[ks]
            self._move(dr, dc, extend=shift)
            return 'break'
        if ks == 'Return':
            self._move(1 if not shift else -1, 0)
            return 'break'
        if ks == 'Tab':
            self._move(0, -1 if shift else 1)
            return 'break'
        if ks == 'Home':
            self._set_current(0 if not shift else row, 0)
            return 'break'
        if ks == 'End':
            self._set_current(len(self._data) - 1 if not shift else row,
                              len(self._columns) - 1)
            return 'break'
        if ks in ('Prior', 'Next'):
            step = max(1, self._visible_rows() - 1)
            self._move(-step if ks == 'Prior' else step, 0, extend=shift)
            return 'break'
        # 可打印字符 / 退格：直接进入编辑
        if event.char and event.char.isprintable():
            self._begin_edit(row, col, initial=event.char)
            return 'break'
        return None

    def _visible_rows(self):
        try:
            h = self.tree.winfo_height()
            return max(1, int(h / 26))
        except Exception:
            return 10

    def _begin_edit(self, row, col, initial=None):
        if not self._editable:
            return
        if not (0 <= row < len(self._data) and 0 <= col < len(self._columns)):
            return
        self._end_edit(commit=True)
        self.tree.see(self._iid(row))
        self.tree.update_idletasks()
        bbox = self.tree.bbox(self._iid(row), self._cid(col))
        if not bbox:
            return
        x0, y0, w, h = bbox
        old_val = self._data[row][col]
        self._edit_entry = tk.Entry(self.tree, justify='center')
        self._edit_entry.place(x=x0, y=y0, width=max(w, 40), height=h)
        if initial is not None:
            self._edit_entry.insert(0, initial)
        else:
            self._edit_entry.insert(0, '' if old_val is None else str(old_val))
            self._edit_entry.select_range(0, 'end')
        self._edit_entry.focus_set()
        self._editing = (row, col)
        self._outline.hide()
        e = self._edit_entry
        e.bind('<Return>', lambda ev: self._end_edit(commit=True))
        e.bind('<KP_Enter>', lambda ev: self._end_edit(commit=True))
        e.bind('<Escape>', lambda ev: self._end_edit(commit=False))
        e.bind('<FocusOut>', lambda ev: self._end_edit(commit=True))
        e.bind('<Tab>', lambda ev: self._commit_and_move(0, 1))
        e.bind('<Up>', lambda ev: self._commit_and_move(-1, 0))
        e.bind('<Down>', lambda ev: self._commit_and_move(1, 0))

    def _commit_and_move(self, dr, dc):
        self._end_edit(commit=True)
        if self._cur:
            self._anchor = self._cur
            self._set_current(self._cur[0] + dr, self._cur[1] + dc)
        return 'break'

    def _end_edit(self, commit=True):
        """结束单元格编辑；commit=True 时写入新值并记录撤销点"""
        if self._edit_entry is None:
            return
        row, col = self._editing if self._editing else (None, None)
        text = self._edit_entry.get()
        self._edit_entry.destroy()
        self._edit_entry = None
        self._editing = None
        self._update_outline()
        if not commit or row is None:
            return
        if not (0 <= row < len(self._data) and 0 <= col < len(self._columns)):
            return
        old_val = self._data[row][col]
        parsed = self._parse(text)
        if str(old_val) == str(parsed):
            return
        self._push_undo()
        self._data[row][col] = parsed
        self._refresh_row(row)
        if self._on_before_edit_callback:
            self._on_before_edit_callback(row, col, old_val, parsed)
        if self._on_edit_callback:
            self._on_edit_callback(row, col, old_val, parsed)

    @staticmethod
    def _parse(text):
        parsed = str(text).strip()
        if parsed == '':
            return ''
        try:
            return float(parsed)
        except ValueError:
            return parsed

    # ---------- 剪贴板 / 填充 / 清空 ----------
    def copy_selection(self):
        """把选区内容导出为 TSV（可直接粘到 Excel）"""
        rng = self._selection_range()
        if not rng:
            return ''
        r0, c0, r1, c1 = rng
        lines = []
        for r in range(r0, r1 + 1):
            row = self._data[r]
            lines.append('\t'.join(
                self._fmt(row[c]) if c < len(row) else '' for c in range(c0, c1 + 1)))
        return '\n'.join(lines)

    def paste_text(self, text):
        """把 TSV 文本粘贴到以活动单元格为左上角的区域，返回写入的单元格数"""
        if not self._editable or self._cur is None or not text:
            return 0
        rows_in = [ln.split('\t') for ln in
                   text.replace('\r\n', '\n').replace('\r', '\n').split('\n')]
        while rows_in and rows_in[-1] == ['']:
            rows_in.pop()
        if not rows_in:
            return 0
        self._push_undo()
        r0, c0 = self._cur
        n = 0
        for i, cells in enumerate(rows_in):
            r = r0 + i
            while len(self._data) <= r:
                self._data.append([''] * len(self._columns))
            for j, raw in enumerate(cells):
                c = c0 + j
                while len(self._columns) <= c:
                    self._columns.append('列%d' % (len(self._columns) + 1))
                    self._refresh_columns()
                while len(self._data[r]) <= c:
                    self._data[r].append('')
                self._data[r][c] = self._parse(raw)
                n += 1
        self._reload()
        self._notify_bulk(r0, c0)
        return n

    def clear_selection(self):
        """清空选区（Delete），返回清空的单元格数"""
        if not self._editable or self._cur is None:
            return 0
        cells = list(self._iter_range())
        if not cells:
            return 0
        self._push_undo()
        for r, c in cells:
            if c < len(self._data[r]):
                self._data[r][c] = ''
        self._reload()
        self._notify_bulk(cells[0][0], cells[0][1])
        return len(cells)

    def fill_down(self):
        """Ctrl+D：用选区首行填充选区其余行"""
        if not self._editable or self._cur is None:
            return 0
        rng = self._selection_range()
        if not rng or rng[0] == rng[2]:
            return 0
        r0, c0, r1, c1 = rng
        self._push_undo()
        src = self._data[r0]
        n = 0
        for r in range(r0 + 1, r1 + 1):
            for c in range(c0, c1 + 1):
                val = src[c] if c < len(src) else ''
                while len(self._data[r]) <= c:
                    self._data[r].append('')
                self._data[r][c] = val
                n += 1
        self._reload()
        self._notify_bulk(r0, c0)
        return n

    def _copy(self, event=None):
        text = self.copy_selection()
        if text:
            try:
                self.clipboard_clear()
                self.clipboard_append(text)
            except Exception:
                pass
        return 'break'

    def _cut(self, event=None):
        self._copy()
        self.clear_selection()
        return 'break'

    def _paste(self, event=None):
        try:
            text = self.clipboard_get()
        except Exception:
            text = ''
        if text:
            self.paste_text(text)
        return 'break'

    def _fill_down(self, event=None):
        self.fill_down()
        return 'break'

    def _on_right_click(self, event):
        row_id = self.tree.identify_row(event.y)
        if row_id:
            disp = self.tree.identify_column(event.x)
            col = 0 if disp == '#0' else self._col_from_display(disp)
            self._anchor = (self.tree.index(row_id), col)
            self._set_current(self.tree.index(row_id), col)
            self.tree.selection_set(row_id)
        menu = tk.Menu(self, tearoff=0)
        menu.add_command(label='复制\tCtrl+C', command=self._copy)
        menu.add_command(label='剪切\tCtrl+X', command=self._cut)
        menu.add_command(label='粘贴\tCtrl+V', command=self._paste)
        menu.add_separator()
        menu.add_command(label='清空\tDelete', command=self.clear_selection)
        menu.add_command(label='向下填充\tCtrl+D', command=self.fill_down)
        menu.add_separator()
        menu.add_command(label='撤销\tCtrl+Z', command=self._undo)
        menu.add_command(label='重做\tCtrl+Y', command=self._redo)
        try:
            menu.tk_popup(event.x_root, event.y_root)
        finally:
            menu.grab_release()

    # ---------- 撤销 / 重做 ----------
    def _push_undo(self):
        self._undo_stack.append((copy.deepcopy(self._data), list(self._columns)))
        if len(self._undo_stack) > self._undo_depth:
            self._undo_stack.pop(0)
        self._redo_stack.clear()

    def _restore(self, data, columns):
        self._data = copy.deepcopy(data)
        if columns != self._columns:
            self._columns = list(columns)
            self._refresh_columns()
        self._reload()
        if self._cur:
            self._cur = (min(self._cur[0], max(len(self._data) - 1, 0)),
                         min(self._cur[1], max(len(self._columns) - 1, 0)))
        self._anchor = self._cur
        self._notify_bulk(0, 0)

    def _undo(self, event=None):
        if not self._undo_stack:
            return 'break'
        self._redo_stack.append((copy.deepcopy(self._data), list(self._columns)))
        data, columns = self._undo_stack.pop()
        self._restore(data, columns)
        return 'break'

    def _redo(self, event=None):
        if not self._redo_stack:
            return 'break'
        self._undo_stack.append((copy.deepcopy(self._data), list(self._columns)))
        data, columns = self._redo_stack.pop()
        self._restore(data, columns)
        return 'break'

    def clear_undo(self):
        self._undo_stack.clear()
        self._redo_stack.clear()

    # ---------- 回调 ----------
    def _notify_bulk(self, row, col):
        """批量变更（粘贴/清空/填充/撤销）后统一通知一次"""
        if self._on_before_edit_callback:
            self._on_before_edit_callback(row, col, None, None)
        if self._on_edit_callback:
            self._on_edit_callback(row, col, None, None)

    def on_edit(self, callback):
        """注册"变更后"回调 callback(row, col, old_value, new_value)"""
        self._on_edit_callback = callback

    def on_before_edit(self, callback):
        """注册"变更前"回调——用于在此刻保存撤销快照"""
        self._on_before_edit_callback = callback

    def on_selection(self, callback):
        self._on_selection_callback = callback

    def select_row(self, row):
        children = self.tree.get_children()
        if 0 <= row < len(children):
            self.tree.selection_set(children[row])
            self.tree.focus(children[row])
            self.tree.see(children[row])
            if self._cur is None:
                self._set_current(row, 0)

    def selected_row(self):
        if self._cur:
            return self._cur[0]
        sel = self.tree.selection()
        if sel:
            return self.tree.index(sel[0])
        return -1


# =====================================================================
# 绘图画布
# =====================================================================

class PlotCanvas(ttk.Frame):
    """matplotlib 内嵌绘图画布，支持 2D/3D。

    对于表示"实际几何形状"的图（水线面半宽图、横剖面图、3D 船体），
    应调用 set_true_aspect() / set_true_box_aspect() 让各坐标轴按真实
    长度比例显示，避免出现「6 m 与 200 m 画得一样长」的失真。
    对于横纵轴量纲不同的曲线图（静水力、邦戎、稳性等）保持 auto。
    """

    def __init__(self, master, three_d=False, toolbar=False, **kw):
        super().__init__(master, **kw)
        self.figure = Figure(figsize=(5, 4), dpi=100)
        self.three_d = three_d
        self._true_aspect = False
        if three_d:
            from mpl_toolkits.mplot3d import Axes3D  # noqa
            self.ax = self.figure.add_subplot(111, projection='3d')
        else:
            self.ax = self.figure.add_subplot(111)
        self.canvas = FigureCanvasTkAgg(self.figure, master=self)
        self.canvas.get_tk_widget().pack(fill='both', expand=True)
        if toolbar:
            self.toolbar = NavigationToolbar2Tk(self.canvas, self)
            self.toolbar.update()
        self._bind_wheel_zoom()

    # ---------- 滚轮缩放 ----------
    def _bind_wheel_zoom(self):
        try:
            w = self.canvas.get_tk_widget()
            w.bind('<MouseWheel>', self._on_wheel, add='+')
            w.bind('<Button-4>', self._on_wheel, add='+')  # Linux 上滚
            w.bind('<Button-5>', self._on_wheel, add='+')  # Linux 下滚
        except Exception:
            pass

    def _on_wheel(self, event):
        delta = getattr(event, 'delta', 0)
        if delta == 0:
            if getattr(event, 'num', None) == 4:
                delta = 120
            elif getattr(event, 'num', None) == 5:
                delta = -120
            else:
                return
        # 滚轮上滚(delta>0) = 放大（范围收窄）
        step = 1.0 / 1.12 if delta > 0 else 1.12
        try:
            if self.three_d:
                x0, x1 = self.ax.get_xlim3d()
                y0, y1 = self.ax.get_ylim3d()
                z0, z1 = self.ax.get_zlim3d()
                cx, cy, cz = (x0 + x1) / 2, (y0 + y1) / 2, (z0 + z1) / 2
                self.ax.set_xlim3d(cx + (x0 - cx) * step, cx + (x1 - cx) * step)
                self.ax.set_ylim3d(cy + (y0 - cy) * step, cy + (y1 - cy) * step)
                self.ax.set_zlim3d(cz + (z0 - cz) * step, cz + (z1 - cz) * step)
            else:
                x0, x1 = self.ax.get_xlim()
                y0, y1 = self.ax.get_ylim()
                cx, cy = (x0 + x1) / 2, (y0 + y1) / 2
                self.ax.set_xlim(cx + (x0 - cx) * step, cx + (x1 - cx) * step)
                self.ax.set_ylim(cy + (y0 - cy) * step, cy + (y1 - cy) * step)
        except Exception:
            return
        self.refresh()
        return 'break'

    # ---------- 真实比例 ----------
    def set_true_aspect(self, enabled=True):
        """2D：X/Y 按真实长度比例显示（1 m 在两轴上长度相同）。

        adjustable='box' —— 缩放绘图框而不是拉伸数据，
        因此图形不会被压扁，也不会出现两个方向比例不一致。
        """
        if self.three_d:
            return
        self._true_aspect = bool(enabled)
        try:
            self.ax.set_aspect('equal' if enabled else 'auto', adjustable='box')
        except Exception:
            pass

    def set_true_box_aspect(self):
        """3D：按 X/Y/Z 的实际数据跨度设置包围盒比例，保证三向等比例。"""
        if not self.three_d:
            return
        try:
            xl = self.ax.get_xlim3d()
            yl = self.ax.get_ylim3d()
            zl = self.ax.get_zlim3d()
            ext = [abs(xl[1] - xl[0]), abs(yl[1] - yl[0]), abs(zl[1] - zl[0])]
            if min(ext) <= 0:
                return
            # 归一化到最长轴，避免极端比例导致绘图框塌陷
            m = max(ext)
            self.ax.set_box_aspect(tuple(e / m for e in ext))
        except Exception:
            pass

    def clear(self):
        self.figure.clear()
        if self.three_d:
            from mpl_toolkits.mplot3d import Axes3D  # noqa
            self.ax = self.figure.add_subplot(111, projection='3d')
        else:
            self.ax = self.figure.add_subplot(111)
        if self._true_aspect and not self.three_d:
            try:
                self.ax.set_aspect('equal', adjustable='box')
            except Exception:
                pass
        self.canvas.draw_idle()

    def refresh(self):
        self.canvas.draw_idle()

    def show_message(self, text, xlabel='', ylabel=''):
        """在画布中央显示消息"""
        self.clear()
        self.ax.text(0.5, 0.5, text, transform=self.ax.transAxes,
                     ha='center', va='center', fontsize=11)
        self.ax.set_xlabel(xlabel)
        self.ax.set_ylabel(ylabel)
        self.ax.set_xticks([])
        self.ax.set_yticks([])
        self.ax.grid(False)
        self.refresh()


# =====================================================================
# Tooltip（鼠标悬浮提示）
# =====================================================================

class Tooltip:
    """
    简单 Tooltip：鼠标进入时显示、离开时隐藏、鼠标移动时跟随。
    使用方法：tooltip = Tooltip(widget, "提示文本")
    """

    def __init__(self, widget, text):
        self.widget = widget
        self.text = text
        self.tipwindow = None
        widget.bind('<Enter>', self._show, add='+')
        widget.bind('<Leave>', self._hide, add='+')
        widget.bind('<ButtonPress>', self._hide, add='+')

    def _show(self, event=None):
        if self.tipwindow is not None:
            return
        x = self.widget.winfo_rootx() + self.widget.winfo_width() // 2
        y = self.widget.winfo_rooty() + self.widget.winfo_height() + 4
        self.tipwindow = tw = tk.Toplevel(self.widget)
        tw.wm_overrideredirect(True)
        tw.wm_geometry('+%d+%d' % (x, y))
        label = tk.Label(tw, text=self.text, justify='left',
                         background='#ffffe0', foreground='#222',
                         relief='solid', borderwidth=1,
                         font=('Microsoft YaHei', 9), padx=6, pady=3)
        label.pack(ipadx=1)

    def _hide(self, event=None):
        if self.tipwindow is not None:
            self.tipwindow.destroy()
            self.tipwindow = None


# =====================================================================
# 简单对话框辅助
# =====================================================================

def _center_over(parent, win, dx=0, dy=-40):
    """将 win 居中于 parent 上方（SOLIDWORKS 风格）"""
    try:
        win.update_idletasks()
        parent.update_idletasks()
        px = parent.winfo_rootx()
        py = parent.winfo_rooty()
        pw = parent.winfo_width()
        ph = parent.winfo_height()
        ww = win.winfo_reqwidth()
        wh = win.winfo_reqheight()
        x = px + (pw - ww) // 2 + dx
        y = py + (ph - wh) // 3 + dy
        win.geometry('+%d+%d' % (x, y))
    except Exception:
        try:
            win.geometry('+%d+%d' % (parent.winfo_rootx() + 80,
                                      parent.winfo_rooty() + 80))
        except Exception:
            pass


def _make_dialog(parent, title, width=None, height=None, grab=True):
    """创建标准模态对话框：置顶、聚焦、等待可见"""
    dlg = tk.Toplevel(parent)
    dlg.title(title)
    dlg.transient(parent)
    dlg.resizable(False, False)
    if width:
        dlg.geometry('%dx%d' % (width, height or 200))
    if grab:
        dlg.grab_set()
    dlg.wait_visibility()
    dlg.lift()
    dlg.focus_force()
    return dlg


def ask_multiline_input(parent, title, prompt, default='', width=60, height=8):
    """多行输入对话框，返回字符串或 None（取消）"""
    dlg = _make_dialog(parent, title)
    dlg.resizable(False, False)
    result = {'value': None}
    ttk.Label(dlg, text=prompt, anchor='w').pack(fill='x', padx=10, pady=(10, 2))
    text = tk.Text(dlg, width=width, height=height, relief='solid',
                   borderwidth=1, undo=True, maxundo=0, wrap='none',
                   font=('Microsoft YaHei', 9))
    text.pack(padx=10, pady=6, fill='both', expand=True)
    text.insert('1.0', default)
    frame = ttk.Frame(dlg)
    frame.pack(pady=8)
    ttk.Button(frame, text='确定', command=lambda: (result.__setitem__('value',
               text.get('1.0', 'end-1c')), dlg.destroy()), width=10).pack(side='right', padx=4)
    ttk.Button(frame, text='取消', command=dlg.destroy, width=10).pack(side='right', padx=4)
    dlg.bind('<Escape>', lambda e: dlg.destroy())
    _center_over(parent, dlg)
    text.focus_set()
    parent.wait_window(dlg)
    return result['value']


def ask_numeric_dialog(parent, title, prompts, defaults):
    """
    数值输入对话框（如主尺度设置）。
    prompts: list[str]; defaults: list[str]
    返回 list[float] 或 None（取消）
    """
    dlg = tk.Toplevel(parent)
    dlg.title(title)
    dlg.transient(parent)
    result = {'value': None}
    vars_ = []
    frame = ttk.Frame(dlg, padding=12)
    frame.pack(fill='both', expand=True)
    ttk.Label(frame, text=title, font=('Microsoft YaHei', 9, 'bold')
              ).grid(row=0, column=0, columnspan=2, sticky='w', pady=(0, 8))
    for i, (p, d) in enumerate(zip(prompts, defaults)):
        ttk.Label(frame, text=p, anchor='w').grid(row=i + 1, column=0,
                                                  sticky='w', pady=3)
        v = tk.StringVar(value=d)
        vars_.append(v)
        e = ttk.Entry(frame, textvariable=v, width=22, font=('Microsoft YaHei', 9))
        e.grid(row=i + 1, column=1, pady=3, padx=(8, 0), sticky='ew')
    frame.columnconfigure(1, weight=1)

    def ok(event=None):
        try:
            vals = [float(v.get()) for v in vars_]
        except ValueError:
            messagebox.showerror('输入错误', '请输入有效数值。', parent=dlg)
            return
        result['value'] = vals
        dlg.destroy()

    def cancel(event=None):
        dlg.destroy()

    btns = ttk.Frame(dlg, padding=12)
    btns.pack(fill='x')
    b_ok = ttk.Button(btns, text='确定', command=ok, width=10)
    b_ok.pack(side='right', padx=(6, 0))
    ttk.Button(btns, text='取消', command=cancel, width=10).pack(side='right', padx=6)
    dlg.bind('<Return>', ok)
    dlg.bind('<Escape>', cancel)
    # 让第一个输入框获得焦点
    if vars_:
        first_entry = frame.winfo_children()[-len(vars_):][0] if False else None
    _center_over(parent, dlg)
    dlg.lift()
    dlg.focus_force()
    try:
        first = None
        for c in frame.winfo_children():
            if isinstance(c, ttk.Entry):
                first = c
                break
        if first:
            first.focus_set()
    except Exception:
        pass
    parent.wait_window(dlg)
    return result['value']


def ask_multi_select(parent, title, prompt, items):
    """
    多选对话框，返回选中项索引列表（1基）或 None。
    items: list[str]
    """
    dlg = _make_dialog(parent, title, width=340, height=min(400, 80 + 22 * max(5, len(items))))
    result = {'value': None}
    ttk.Label(dlg, text=prompt, anchor='w').pack(fill='x', padx=10, pady=(10, 4))
    frame = ttk.Frame(dlg)
    frame.pack(fill='both', expand=True, padx=10, pady=4)
    listbox = tk.Listbox(frame, selectmode='multiple', height=min(15, max(5, len(items))),
                         relief='solid', borderwidth=1, font=('Microsoft YaHei', 9),
                         activestyle='dotbox', highlightthickness=0)
    scroll = ttk.Scrollbar(frame, orient='vertical', command=listbox.yview)
    listbox.configure(yscrollcommand=scroll.set)
    listbox.pack(side='left', fill='both', expand=True)
    scroll.pack(side='right', fill='y')
    for it in items:
        listbox.insert('end', it)

    def ok():
        sel = listbox.curselection()
        result['value'] = [i + 1 for i in sel]
        dlg.destroy()

    btns = ttk.Frame(dlg, padding=10)
    btns.pack(fill='x')
    ttk.Button(btns, text='确定', command=ok, width=10).pack(side='right', padx=4)
    ttk.Button(btns, text='取消', command=dlg.destroy, width=10).pack(side='right', padx=4)
    dlg.bind('<Escape>', lambda e: dlg.destroy())
    _center_over(parent, dlg)
    listbox.focus_set()
    parent.wait_window(dlg)
    return result['value']


def ask_choice_dialog(parent, title, prompt, options, default_index=0):
    """
    单选对话框（从列表中选择一项）。
    options: list[str]   选项文本列表
    返回: 选中项索引（0基）或 None（取消）
    """
    dlg = _make_dialog(parent, title, width=460,
                       height=min(460, 160 + 24 * max(3, len(options))))
    result = {'value': None}
    ttk.Label(dlg, text=prompt, anchor='w', justify='left',
              wraplength=430).pack(fill='x', padx=10, pady=(10, 6))
    frame = ttk.Frame(dlg)
    frame.pack(fill='both', expand=True, padx=10, pady=4)
    listbox = tk.Listbox(frame, height=min(14, max(4, len(options))),
                         relief='solid', borderwidth=1, font=('Microsoft YaHei', 9),
                         activestyle='dotbox', highlightthickness=0)
    scroll = ttk.Scrollbar(frame, orient='vertical', command=listbox.yview)
    listbox.configure(yscrollcommand=scroll.set)
    listbox.pack(side='left', fill='both', expand=True)
    scroll.pack(side='right', fill='y')
    for it in options:
        listbox.insert('end', it)
    if 0 <= default_index < len(options):
        listbox.selection_set(default_index)
        listbox.see(default_index)

    def ok(event=None):
        sel = listbox.curselection()
        if not sel:
            messagebox.showwarning('提示', '请选择一个选项。', parent=dlg)
            return
        result['value'] = int(sel[0])
        dlg.destroy()

    listbox.bind('<Double-1>', ok)
    btns = ttk.Frame(dlg, padding=10)
    btns.pack(fill='x')
    ttk.Button(btns, text='确定', command=ok, width=10).pack(side='right', padx=4)
    ttk.Button(btns, text='取消', command=dlg.destroy, width=10).pack(side='right', padx=4)
    dlg.bind('<Return>', ok)
    dlg.bind('<Escape>', lambda e: dlg.destroy())
    _center_over(parent, dlg)
    listbox.focus_set()
    parent.wait_window(dlg)
    return result['value']


def ask_text_dialog(parent, title, prompt, default=''):
    """单行文本输入对话框"""
    dlg = _make_dialog(parent, title, width=420)
    result = {'value': None}
    ttk.Label(dlg, text=prompt, anchor='w', justify='left',
              wraplength=400).pack(fill='x', padx=10, pady=(10, 6))
    v = tk.StringVar(value=default)
    e = ttk.Entry(dlg, textvariable=v, width=46)
    e.pack(padx=10, pady=4)

    def ok(event=None):
        result['value'] = v.get()
        dlg.destroy()

    btns = ttk.Frame(dlg, padding=10)
    btns.pack(fill='x')
    ttk.Button(btns, text='确定', command=ok, width=10).pack(side='right', padx=4)
    ttk.Button(btns, text='取消', command=dlg.destroy, width=10).pack(side='right', padx=4)
    dlg.bind('<Return>', ok)
    dlg.bind('<Escape>', lambda ev: dlg.destroy())
    _center_over(parent, dlg)
    e.focus_set()
    parent.wait_window(dlg)
    return result['value']
