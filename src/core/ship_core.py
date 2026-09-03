# -*- coding: utf-8 -*-
"""
ship_core.py —— 船舶静水力计算核心算法模块
完整移植自 MATLAB 版 SCS (Ship Static Calculate) 的 ship.m

包含：
- 数值/字符串转换工具
- 多边形面积/形心（Shoelace 公式）
- 水线面计算（分段累加 / 吃水插值）
- 横剖面计算
- 浮心计算（正浮态/任意浮态）
- 静水力曲线
- 邦戎曲线
- 稳性计算（KN / GZ / 动稳性）
- 异常点剔除
"""

import math
import numpy as np


# =====================================================================
# 通用工具
# =====================================================================

def cumulative_trapezoid(y, x, initial=0.0):
    """兼容 np.cumulative_trapezoid / MATLAB cumtrapz 的累积梯形积分。

    部分 numpy 发行版（如无特殊构建的 2.x）缺失 cumulative_trapezoid，
    这里手写等效实现：第 1 个元素 = initial，其后逐段累加梯形面积。
    """
    x = np.asarray(x, dtype=float)
    y = np.asarray(y, dtype=float)
    if y.size == 0:
        return np.array([])
    if y.size == 1:
        return np.array([initial])
    dx = np.diff(x)
    if np.any(dx <= 0):
        # 与 cumtrapz 一样要求 x 单调递增；异常时退化为按单位间距
        dx = np.ones_like(dx)
    seg = 0.5 * dx * (y[:-1] + y[1:])
    return np.concatenate(([initial], initial + np.cumsum(seg)))


def pchip_interp(xp, fp, x):
    """MATLAB interp1(xp, fp, x, 'pchip') 的等价实现。

    使用 scipy PCHIP；点太少（<4）时回退线性插值（np.interp）。
    """
    xp = np.asarray(xp, dtype=float)
    fp = np.asarray(fp, dtype=float)
    x = np.asarray(x, dtype=float)
    if xp.size < 4 or fp.size != xp.size:
        return np.interp(x, xp, fp)
    try:
        from scipy.interpolate import PchipInterpolator
        p = PchipInterpolator(xp, fp)
        return p(x)
    except Exception:
        return np.interp(x, xp, fp)


def is_finite(v):
    """判断数值是否有限，兼容 None / 非数值"""
    try:
        return math.isfinite(float(v))
    except (TypeError, ValueError):
        return False


def col_to_double(col):
    """
    兼容 MATLAB colToDouble：
    将 数值 / 字符串 / 单元格 列 统一转为 float 列向量，
    空值、非法值、NaN、Inf 转为 numpy.nan。
    """
    if col is None:
        return np.array([])
    # numpy 数值数组
    if isinstance(col, (np.ndarray, list, tuple)):
        arr = np.asarray(col)
        if arr.dtype.kind in 'fiu':
            out = arr.astype(float).ravel()
            out[~np.isfinite(out)] = np.nan
            return out
        # 字符串 / 对象数组
        out = np.full(arr.size, np.nan)
        flat = arr.ravel()
        for i, x in enumerate(flat):
            out[i] = _parse_scalar(x)
        return out
    return np.array([_parse_scalar(col)])


def cell_val_to_double(x):
    """
    兼容 MATLAB cellValToDouble：
    递归地将任意单元格值转换为 double，非法值转为 NaN。
    """
    if x is None:
        return np.nan
    if isinstance(x, (np.ndarray, list, tuple)):
        arr = np.asarray(x, dtype=object)
        out = np.full(arr.shape, np.nan)
        it = np.nditer(arr, flags=['multi_index', 'refs_ok'])
        for item in it:
            v = item.item()
            if isinstance(v, (list, tuple, np.ndarray)):
                sub = cell_val_to_double(v)
                if isinstance(sub, np.ndarray) and sub.size == 1:
                    out[it.multi_index] = sub.ravel()[0]
            else:
                out[it.multi_index] = _parse_scalar(v)
        if out.size == 1:
            return float(out.ravel()[0])
        return out
    return _parse_scalar(x)


def _parse_scalar(x):
    """将单个标量解析为 float，失败返回 NaN"""
    if isinstance(x, (bool,)):
        return float(x)
    if isinstance(x, (int, float, np.integer, np.floating)):
        v = float(x)
        return v if math.isfinite(v) else math.nan
    if isinstance(x, (str, np.str_)):
        s = str(x).strip()
        s = s.replace('，', ',').replace('\u3000', ' ')
        s = ''.join(ch for ch in s if ch not in ' \t,')
        if s == '' or s.lower() == 'nan':
            return math.nan
        try:
            v = float(s)
            return v if math.isfinite(v) else math.nan
        except ValueError:
            return math.nan
    return math.nan


def num2trimstr(x, tol=1e-10):
    """
    兼容 MATLAB num2trimstr：
    数值转字符串，整数不带小数，非整数去尾随0与末尾小数点。
    """
    try:
        x = float(x)
    except (TypeError, ValueError):
        return ''
    if not math.isfinite(x):
        return ''
    if abs(x - round(x)) < tol:
        return str(int(round(x)))
    s = '%.10f' % x
    if '.' in s:
        s = s.rstrip('0').rstrip('.')
    return s


def num2trimstr_local(v, decimals=12):
    """友好数字字符串（2位小数版用于分段统计等）"""
    try:
        v = float(v)
    except (TypeError, ValueError):
        return ''
    if not math.isfinite(v):
        return ''
    if abs(v - round(v)) < 1e-12:
        return str(int(round(v)))
    s = ('%.*f' % (decimals, v)).rstrip('0').rstrip('.')
    return s


def fullwidth2halfwidth(lines):
    """全角数字/符号转半角（MATLAB fullwidth2halfwidth）"""
    pairs = {
        '０': '0', '１': '1', '２': '2', '３': '3', '４': '4',
        '５': '5', '６': '6', '７': '7', '８': '8', '９': '9',
        '．': '.', '－': '-', '＋': '+', '，': ',', 'ｅ': 'e', 'Ｅ': 'E',
    }
    out = []
    for line in lines:
        s = line
        for k, v in pairs.items():
            s = s.replace(k, v)
        out.append(s)
    return out


def parse_pasted_numbers(lines):
    """宽松解析粘贴的多行数值（MATLAB parsePastedNumbers）"""
    lines = fullwidth2halfwidth(lines)
    vals = []
    for i, line in enumerate(lines):
        s = ''.join(ch for ch in line.strip() if ch not in ' \t,')
        if s == '' or s.lower() == 'nan':
            raise ValueError('第 %d 行为空或非法。' % (i + 1))
        try:
            x = float(s)
        except ValueError:
            raise ValueError('第 %d 行不是有效数值：%s' % (i + 1, s))
        if not math.isfinite(x):
            raise ValueError('第 %d 行不是有效数值：%s' % (i + 1, s))
        vals.append(x)
    return np.array(vals)


def parse_number_loose(x):
    """宽松解析数值字符串（MATLAB parseNumberLoose）"""
    if isinstance(x, (int, float, np.integer, np.floating)):
        v = float(x)
        return v if math.isfinite(v) else math.nan
    s = str(x).strip().replace(' ', '').replace(',', '')
    if s == '' or s.lower() == 'nan':
        return math.nan
    try:
        v = float(s)
        return v if math.isfinite(v) else math.nan
    except ValueError:
        return math.nan


def make_seq_prealloc(s, e, st, tol=1e-10):
    """
    兼容 MATLAB makeSeqPrealloc：
    从 s 以步长 st 生成序列，必要时包含终点 e。
    """
    total_steps = (e - s) / st if st > 0 else 0
    n = math.floor(total_steps + tol)
    if n < 0:
        return np.array([s])
    base = s + np.arange(n + 1) * st
    last_val = base[-1]
    need_end = (e - last_val) > tol
    if need_end:
        return np.append(base, e)
    return base


def make_unique_strings(names):
    """兼容 MATLAB makeUniqueStrings：对重复名称追加后缀去重"""
    seen = {}
    out = []
    for n in names:
        n = str(n)
        if n in seen:
            seen[n] += 1
            out.append('%s_%d' % (n, seen[n]))
        else:
            seen[n] = 1
            out.append(n)
    return out


# =====================================================================
# 面积 / 形心 / 面积矩
# =====================================================================

def calculate_area_centroid_trapezoidal(x, y):
    """
    兼容 MATLAB calculateAreaAndCentroidTrapezoidal：
    梯形法（Shoelace 叉积）计算多边形面积和形心。
    返回 (area, centroid)，centroid=[cx, cy]，数据不足时 area=NaN。
    """
    x = np.asarray(x, dtype=float).ravel()
    y = np.asarray(y, dtype=float).ravel()
    if x.size < 3:
        return math.nan, [math.nan, math.nan]
    if x[0] != x[-1] or y[0] != y[-1]:
        x = np.append(x, x[0])
        y = np.append(y, y[0])
    n = x.size
    area = 0.0
    for i in range(n - 1):
        area += x[i] * y[i + 1] - x[i + 1] * y[i]
    area = abs(area) / 2.0
    cx = 0.0
    cy = 0.0
    for i in range(n - 1):
        factor = x[i] * y[i + 1] - x[i + 1] * y[i]
        cx += (x[i] + x[i + 1]) * factor
        cy += (y[i] + y[i + 1]) * factor
    if area < np.finfo(float).eps:
        centroid = [math.nan, math.nan]
    else:
        cx = cx / (6 * area)
        cy = cy / (6 * area)
        centroid = [cx, cy]
    return abs(area), centroid


def calculate_section_area_and_moments(y, z):
    """
    兼容 MATLAB calculateSectionAreaAndMoments / calculateShoelaceAreaAndMoments：
    Shoelace 公式计算面积及对 Y / Z 轴的一阶矩。
    返回 (area, My, Mz)。
    """
    y = np.asarray(y, dtype=float).ravel()
    z = np.asarray(z, dtype=float).ravel()
    n = y.size
    if n < 3:
        return 0.0, 0.0, 0.0
    if y[0] != y[-1] or z[0] != z[-1]:
        y = np.append(y, y[0])
        z = np.append(z, z[0])
        n = y.size
    area = 0.0
    my = 0.0
    mz = 0.0
    for i in range(n - 1):
        cross = y[i] * z[i + 1] - y[i + 1] * z[i]
        area += cross
        my += (y[i] + y[i + 1]) * cross
        mz += (z[i] + z[i + 1]) * cross
    area = abs(area) / 2.0
    my = my / 6.0
    mz = mz / 6.0
    return area, my, mz


def calculate_polygon_area_and_centroid(y, z):
    """
    兼容 MATLAB calculatePolygonAreaAndCentroid：
    计算多边形面积和形心。
    返回 (area, centroidY, centroidZ)。
    """
    y = np.asarray(y, dtype=float).ravel()
    z = np.asarray(z, dtype=float).ravel()
    if y.size < 3:
        return 0.0, math.nan, math.nan
    if y[0] != y[-1] or z[0] != z[-1]:
        y = np.append(y, y[0])
        z = np.append(z, z[0])
    n = y.size - 1
    area_signed = 0.0
    my = 0.0
    mz = 0.0
    for i in range(n):
        cross = y[i] * z[i + 1] - y[i + 1] * z[i]
        area_signed += cross
        my += (y[i] + y[i + 1]) * cross
        mz += (z[i] + z[i + 1]) * cross
    area = abs(area_signed) / 2.0
    my = my / 6.0
    mz = mz / 6.0
    if area > 0:
        return area, my / area, mz / area
    return area, math.nan, math.nan


# =====================================================================
# 横剖面构造 / 水下截取
# =====================================================================

def construct_symmetric_section(half_y, z):
    """
    兼容 MATLAB constructSymmetricSection：
    从右舷半宽数据构造对称全船横剖面。
    """
    half_y = np.asarray(half_y, dtype=float).ravel()
    z = np.asarray(z, dtype=float).ravel()
    if z.size > 0 and np.min(z) > 0.01:
        if np.min(z) <= 2:
            baseline_y = float(np.interp(0.0, z, half_y))
            if not math.isfinite(baseline_y) or baseline_y < 0:
                baseline_y = 0.0
        else:
            baseline_y = 0.0
        half_y = np.concatenate(([baseline_y], half_y))
        z = np.concatenate(([0.0], z))
    full_y = np.concatenate((-np.flip(half_y), half_y))
    full_z = np.concatenate((np.flip(z), z))
    return full_y, full_z


def extract_underwater_section(full_y, full_z, draft):
    """
    兼容 MATLAB extractUnderwaterSection：
    截取吃水以下的多边形部分（保留与水平面的交点）。
    """
    full_y = np.asarray(full_y, dtype=float).ravel()
    full_z = np.asarray(full_z, dtype=float).ravel()
    n = full_y.size
    if n < 3:
        return np.array([]), np.array([])
    water_y = []
    water_z = []
    for i in range(n):
        j = i
        k = (i + 1) % n
        zj = full_z[j]
        zk = full_z[k]
        below_j = zj <= draft
        below_k = zk <= draft
        if below_j:
            water_y.append(full_y[j])
            water_z.append(full_z[j])
        if below_j != below_k:
            if zk != zj:
                t = (draft - zj) / (zk - zj)
                water_y.append(full_y[j] + t * (full_y[k] - full_y[j]))
                water_z.append(draft)
    if not water_y:
        return np.array([]), np.array([])
    water_y = np.array(water_y)
    water_z = np.array(water_z)
    if water_y[0] != water_y[-1] or water_z[0] != water_z[-1]:
        water_y = np.append(water_y, water_y[0])
        water_z = np.append(water_z, water_z[0])
    return water_y, water_z


# =====================================================================
# 分段相关
# =====================================================================

def detect_segments_by_station(sta, tol=1e-9):
    """
    兼容 MATLAB detectSegmentsByStation：
    根据站号自动检测"等距段"，返回 [startIdx, endIdx, estStep]。
    索引为 1 基。
    """
    sta = np.asarray(sta, dtype=float).ravel()
    n = sta.size
    if n < 2:
        return []
    d = np.diff(sta)
    i0 = 0  # 0基
    segs = []
    for i in range(1, n - 1):  # MATLAB: 2:nLoc-1
        if abs(d[i - 1] - d[i]) > tol:
            est_step = float(np.median(d[i0:i]))
            segs.append([i0 + 1, i + 1, est_step])  # 段 [i0+1 .. i+1] (1基)
            i0 = i
    # 收尾段
    if i0 <= n - 1:
        est_step = float(np.median(d[i0:]))
        segs.append([i0 + 1, n, est_step])
    return segs


def preprocess_segments(segs_in, n_total):
    """
    兼容 MATLAB preprocessSegments：
    将分段标准化为 4 列 [s, e, step, scale]，裁剪、排序、去重叠。
    索引为 1 基。
    """
    if segs_in is None or len(segs_in) == 0:
        return np.zeros((0, 4))
    segs = np.asarray(segs_in, dtype=float)
    if segs.ndim == 1:
        segs = segs.reshape(1, -1)
    if segs.shape[1] < 2:
        return np.zeros((0, 4))
    if segs.shape[1] == 2:
        segs = np.hstack([segs, np.full((segs.shape[0], 2), np.nan)])
    elif segs.shape[1] == 3:
        segs = np.hstack([segs, np.full((segs.shape[0], 1), np.nan)])
    elif segs.shape[1] > 4:
        segs = segs[:, :4]
    # 裁剪
    s_col = np.clip(np.round(segs[:, 0]), 1, n_total)
    e_col = np.clip(np.round(segs[:, 1]), 1, n_total)
    segs = np.column_stack([s_col, e_col, segs[:, 2], segs[:, 3]])
    # 只保留 e > s
    segs = segs[segs[:, 1] > segs[:, 0]]
    if segs.size == 0:
        return np.zeros((0, 4))
    # 按起点排序
    segs = segs[np.argsort(segs[:, 0])]
    # 去重叠
    cleaned = []
    prev_end = 0
    for row in segs:
        s = int(row[0])
        e = int(row[1])
        stp = row[2]
        sc = row[3]
        if s <= prev_end:
            s = prev_end + 1
        if e > s:
            cleaned.append([s, e, stp, sc])
            prev_end = e
    if not cleaned:
        return np.zeros((0, 4))
    return np.asarray(cleaned, dtype=float)


def method_scale(coeff_method):
    """积分方法比例因子（MATLAB 中的 scaleGlobal）"""
    m = coeff_method or ''
    if m in ('trapezoidal', '梯形', 'trap'):
        return 1, '梯形(1)'
    if m in ('simp1', 'Simpson1/3', '1/3'):
        return 1 / 3, 'Simpson 1/3 (1/3)'
    if m in ('simp2', 'Simpson3/8', '3/8'):
        return 3 / 8, 'Simpson 3/8 (3/8)'
    return 1, '未指明(按1)'


# =====================================================================
# 水线面计算
# =====================================================================

def calc_waterplane_segments(station_numbers, half_widths, coeff_vec, moment_arms,
                             segments, scale_global, lpp, lpp_start, lpp_end):
    """
    兼容 MATLAB PushTool_calClicked 的分段累加计算。
    返回 dict(half_A, half_M, full_A, full_M, lcf, debug_lines)。
    """
    half_a = 0.0
    half_m = 0.0
    n = len(station_numbers)
    total_station_span = lpp_end - lpp_start
    debug = []
    for k in range(segments.shape[0]):
        i0 = int(segments[k, 0]) - 1  # 转0基
        i1 = int(segments[k, 1]) - 1
        seg_scale = segments[k, 3] if segments.shape[1] >= 4 else np.nan
        if i1 <= i0:
            debug.append('段#%d 区间无效，跳过。' % (k + 1))
            continue
        station_start = station_numbers[i0]
        station_end = station_numbers[i1]
        station_range = station_end - station_start
        point_count = i1 - i0
        h_station_seg = station_range / point_count if point_count > 0 else 0.0
        if total_station_span > 0:
            h_len = h_station_seg * (lpp / total_station_span)
        else:
            h_len = 0.0
        if math.isfinite(seg_scale) and seg_scale > 0:
            scale_k = seg_scale
        else:
            scale_k = scale_global
        idx = np.arange(i0, i1 + 1)
        sum_ac = float(np.sum(half_widths[idx] * coeff_vec[idx]))
        sum_am = float(np.sum(half_widths[idx] * coeff_vec[idx] * moment_arms[idx]))
        half_a += scale_k * h_len * sum_ac
        half_m += scale_k * h_len * h_len * sum_am
        debug.append('段#%d: i=[%d..%d], h_station=%.6f, h_len=%.6f, scale=%g'
                     % (k + 1, i0 + 1, i1 + 1, h_station_seg, h_len, scale_k))
    full_a = 2 * half_a
    full_m = 2 * half_m
    lcf = full_m / full_a if abs(full_a) > 1e-12 else math.nan
    return dict(half_a=half_a, half_m=half_m, full_a=full_a, full_m=full_m,
                lcf=lcf, debug=debug)


# =====================================================================
# 横剖面面积/形心
# =====================================================================

def calc_transverse_section(heights, half_widths, coefficients, coeff_method):
    """
    兼容 MATLAB calculateTransverseSectionCentroid：
    计算横剖面半船面积/全船面积/形心。
    返回 dict(halfArea, fullArea, half_centroid_y, full_centroid_y, centroid_z)
    """
    heights = np.asarray(heights, dtype=float).ravel()
    half_widths = np.asarray(half_widths, dtype=float).ravel()
    coefficients = np.asarray(coefficients, dtype=float).ravel()
    # 按高度排序
    order = np.argsort(heights)
    heights = heights[order]
    half_widths = half_widths[order]
    coefficients = coefficients[order]
    n = heights.size
    scale, _ = method_scale(coeff_method)
    h = np.diff(heights)
    half_area = 0.0
    for i in range(n - 1):
        segment_integral = h[i] * (half_widths[i] + half_widths[i + 1]) / 2
        c_avg = (coefficients[i] + coefficients[i + 1]) / 2
        half_area += segment_integral * c_avg
    half_area *= scale
    full_area = 2 * half_area
    moment_y2 = 0.0
    moment_yz = 0.0
    for i in range(n - 1):
        y1 = half_widths[i]
        y2 = half_widths[i + 1]
        z1 = heights[i]
        z2 = heights[i + 1]
        c_avg = (coefficients[i] + coefficients[i + 1]) / 2
        dz = h[i]
        d_moment_y2 = dz * (y1 * y2 + (y2 - y1) ** 2 / 3) * c_avg
        d_moment_yz = (y1 * z1 + y2 * z2) * c_avg * dz / 2
        moment_y2 += d_moment_y2
        moment_yz += d_moment_yz
    moment_y2 *= scale
    moment_yz *= scale
    if half_area > 1e-10:
        half_centroid_y = moment_y2 / half_area
        centroid_z = moment_yz / half_area
        full_centroid_y = 0.0
    else:
        half_centroid_y = 0.0
        centroid_z = 0.0
        full_centroid_y = 0.0
    return dict(halfArea=half_area, fullArea=full_area,
                half_centroid_y=half_centroid_y,
                full_centroid_y=full_centroid_y, centroid_z=centroid_z)


# =====================================================================
# 水线面在指定吃水处插值
# =====================================================================

def calculate_waterplane_at_draft(waterlines, lpp, lpp_start, lpp_end, draft):
    """
    兼容 MATLAB calculateWaterplaneAtDraft：
    从多高度水线面型值（Half 节点数据）插值计算给定吃水处的水线面参数。

    waterlines: list of dict(stations: ndarray, halfWidths: ndarray, height: float)
    返回 dict(area, LCF, halfWidths, stations, IT, IL, LWL, BWL)
    """
    all_stations = []
    all_half_widths = []
    all_heights = []
    for wl in waterlines:
        stations = np.asarray(wl['stations'], dtype=float).ravel()
        half_widths = np.asarray(wl['halfWidths'], dtype=float).ravel()
        height = float(wl['height'])
        n = min(stations.size, half_widths.size)
        if n > 0:
            all_stations.append(stations[:n])
            all_half_widths.append(half_widths[:n])
            all_heights.append(np.full(n, height))
    if not all_stations:
        raise ValueError('没有找到有效的水线面数据')
    all_stations = np.concatenate(all_stations)
    all_half_widths = np.concatenate(all_half_widths)
    all_heights = np.concatenate(all_heights)

    station_to_meter_ratio = lpp / (lpp_end - lpp_start)
    unique_stations = np.unique(all_stations)
    half_widths_at_draft = np.zeros(unique_stations.size)
    for i, station in enumerate(unique_stations):
        mask = all_stations == station
        heights_at_station = all_heights[mask]
        half_widths_at_station = all_half_widths[mask]
        order = np.argsort(heights_at_station)
        sorted_heights = heights_at_station[order]
        sorted_half_widths = half_widths_at_station[order]
        # 去重
        uniq_h, idx = np.unique(sorted_heights, return_index=True)
        uniq_w = sorted_half_widths[idx]
        if uniq_h.size < 2:
            half_widths_at_draft[i] = 0.0
            continue
        # 与 MATLAB interp1(...,'linear','extrap') 一致：范围内线性，范围外线性外推
        if draft < uniq_h[0]:
            h0, h1 = uniq_h[0], uniq_h[1]
            w0, w1 = uniq_w[0], uniq_w[1]
            val = w0 + (draft - h0) * (w1 - w0) / (h1 - h0) if h1 != h0 else w0
        elif draft > uniq_h[-1]:
            h0, h1 = uniq_h[-2], uniq_h[-1]
            w0, w1 = uniq_w[-2], uniq_w[-1]
            val = w0 + (draft - h0) * (w1 - w0) / (h1 - h0) if h1 != h0 else w1
        else:
            val = float(np.interp(draft, uniq_h, uniq_w))
        if val < 0:
            val = 0.0
        half_widths_at_draft[i] = val

    longitudinal = (unique_stations - lpp_start) * station_to_meter_ratio
    midship = lpp / 2.0
    longitudinal = longitudinal - midship
    order = np.argsort(longitudinal)
    longitudinal = longitudinal[order]
    half_widths_at_draft = half_widths_at_draft[order]

    x = longitudinal
    y = half_widths_at_draft
    area_half = float(np.trapezoid(y, x))
    waterplane_area = 2 * area_half
    moment_half = float(np.trapezoid(x * y, x))
    if abs(area_half) > 1e-6:
        lcf = moment_half / area_half
    else:
        lcf = 0.0
    it_half = (1 / 3) * float(np.trapezoid(y ** 3, x))
    it = 2 * it_half
    il_midship_half = float(np.trapezoid((x ** 2) * y, x))
    il_midship = 2 * il_midship_half
    il = il_midship - waterplane_area * lcf ** 2
    if x.size >= 2:
        lwl = float(np.max(x) - np.min(x))
    else:
        lwl = 0.0
    bwl = 2 * float(np.max(y)) if y.size else 0.0
    return dict(area=waterplane_area, LCF=lcf, halfWidths=half_widths_at_draft,
                stations=unique_stations, IT=it, IL=il, LWL=lwl, BWL=bwl)


# =====================================================================
# 浮心计算
# =====================================================================

def calc_buoyancy_from_waterplane(waterlines, lpp, lpp_start, lpp_end, draft):
    """
    兼容 MATLAB calculateBuoyancyFromWaterplane：
    基于水线面数值积分计算正浮态浮心。
    返回 dict(volume, xB, yB, zB, n_segments)
    """
    # 先算设计吃水处的水线面参数
    base = calculate_waterplane_at_draft(waterlines, lpp, lpp_start, lpp_end, draft)
    n_segments = min(50, max(20, round(draft * 20)))
    dz = draft / n_segments if n_segments > 0 else 0.0
    total_volume = 0.0
    total_moment = 0.0
    weighted_z = 0.0
    for i in range(1, n_segments + 1):
        z = (i - 0.5) * dz
        try:
            wp = calculate_waterplane_at_draft(waterlines, lpp, lpp_start, lpp_end, z)
            current_area = wp['area']
            current_lcf = wp['LCF']
        except Exception:
            alpha = 1.8
            ratio = (z / draft) ** alpha if draft > 0 else 0
            current_area = base['area'] * ratio
            current_lcf = base['LCF'] * (1 - (z / draft) * 0.1) if draft > 0 else 0
        total_volume += current_area * dz
        total_moment += current_lcf * current_area * dz
        weighted_z += z * current_area * dz
    eps = 1e-6
    if abs(total_volume) > eps:
        xb = total_moment / total_volume
    else:
        xb = math.nan
    yb = 0.0
    if abs(total_volume) > eps:
        zb = weighted_z / total_volume
    else:
        alpha = 1.8
        zb = draft * (1 - 1 / (2 * alpha))
    return dict(volume=total_volume, xB=xb, yB=yb, zB=zb, n_segments=n_segments)


def calc_buoyancy_from_sections(sections, x_coords, heel_angle, trim_angle,
                                midship_draft, lpp, breadth, depth):
    """
    兼容 MATLAB calculateBuoyancyFromSections：
    基于横剖面计算任意浮态浮心。

    sections: list of dict(Y, Z) 各站横剖面半宽/高度
    x_coords: 各站纵向坐标（船中为0）
    返回 dict(volume, xB, yB, zB, valid_idx, section_areas, section_my, section_mz)
    """
    heel_rad = -math.radians(heel_angle)
    trim_rad = math.radians(trim_angle)
    num_stations = len(x_coords)
    section_areas = np.zeros(num_stations)
    section_my = np.zeros(num_stations)
    section_mz = np.zeros(num_stations)
    valid_count = 0
    for i in range(num_stations):
        half_y = np.asarray(sections[i]['Y'], dtype=float).ravel()
        z = np.asarray(sections[i]['Z'], dtype=float).ravel()
        if half_y.size < 3:
            continue
        current_draft = midship_draft - x_coords[i] * math.tan(trim_rad)
        current_draft = max(current_draft, -depth * 0.2)
        current_draft = min(current_draft, depth * 1.2)
        if current_draft <= 0:
            continue
        # 补充基线点
        if z.size > 0 and np.min(z) > 0.01:
            z_sorted = np.sort(z)
            idx = np.argsort(z)
            half_y_sorted = half_y[idx]
            if z_sorted.size >= 2:
                p = np.polyfit(z_sorted[:2], half_y_sorted[:2], 1)
                baseline_y = float(np.polyval(p, 0))
            else:
                baseline_y = float(half_y_sorted[0])
            baseline_y = max(baseline_y, 0)
            half_y = np.concatenate(([baseline_y], half_y))
            z = np.concatenate(([0.0], z))
        full_y = np.concatenate((-np.flip(half_y), half_y))
        full_z = np.concatenate((np.flip(z), z))
        if abs(heel_angle) > 0.01:
            rotated_z = full_y * math.sin(heel_rad) + full_z * math.cos(heel_rad)
        else:
            rotated_z = full_z
        # 截取水下部分
        water_y = []
        water_z = []
        n = full_y.size
        for j in range(n):
            k = (j + 1) % n
            below_j = rotated_z[j] <= current_draft
            below_k = rotated_z[k] <= current_draft
            if below_j:
                water_y.append(full_y[j])
                water_z.append(full_z[j])
            if below_j != below_k:
                if abs(rotated_z[k] - rotated_z[j]) > 1e-9:
                    t = (current_draft - rotated_z[j]) / (rotated_z[k] - rotated_z[j])
                    water_y.append(full_y[j] + t * (full_y[k] - full_y[j]))
                    water_z.append(full_z[j] + t * (full_z[k] - full_z[j]))
        if len(water_y) < 3:
            continue
        water_y = np.array(water_y)
        water_z = np.array(water_z)
        center_y = np.mean(water_y)
        center_z = np.mean(water_z)
        angles = np.arctan2(water_z - center_z, water_y - center_y)
        order = np.argsort(angles)
        water_y = water_y[order]
        water_z = water_z[order]
        area, my, mz = calculate_section_area_and_moments(water_y, water_z)
        if area <= 0:
            continue
        section_areas[i] = area
        section_my[i] = my
        section_mz[i] = mz
        valid_count += 1
    valid = section_areas > 0
    xc = np.asarray(x_coords, dtype=float)[valid]
    sa = section_areas[valid]
    smy = section_my[valid]
    smz = section_mz[valid]
    volume = 0.0
    x_moment = 0.0
    y_moment = 0.0
    z_moment = 0.0
    for i in range(len(xc) - 1):
        dx = xc[i + 1] - xc[i]
        dv = 0.5 * (sa[i] + sa[i + 1]) * dx
        volume += dv
        x_center = 0.5 * (xc[i] + xc[i + 1])
        x_moment += x_center * dv
        y_moment += 0.5 * (smy[i] + smy[i + 1]) * dx
        z_moment += 0.5 * (smz[i] + smz[i + 1]) * dx
    if volume > 1e-6:
        xb = x_moment / volume
        yb = y_moment / volume
        zb = z_moment / volume
        if abs(yb) < 1e-10:
            yb = 0.0
    else:
        xb = yb = zb = math.nan
    return dict(volume=volume, xB=xb, yB=yb, zB=zb, valid_idx=valid,
                section_areas=sa, section_my=smy, section_mz=smz,
                x_coords=xc)


# =====================================================================
# 静水力曲线
# =====================================================================

def calc_hydrostatics(waterlines, sections, lpp, lpp_start, lpp_end,
                      breadth, draft_min, draft_max, n_points,
                      outlier_removal=False, outlier_threshold=3.0):
    """
    兼容 MATLAB CalculateCurvesButtonPushed：
    计算静水力曲线。
    sections: dict, 站号->横剖面(dict(Y,Z)) 或 None
    """
    # 计算吃水序列
    n1 = max(50, round(n_points * (draft_max / (draft_max - draft_min + 0.1))))
    calc_drafts1 = np.linspace(0, draft_max, n1)
    calc_drafts2 = np.linspace(draft_min, draft_max, n_points)
    calc_drafts = np.unique(np.concatenate([calc_drafts1, calc_drafts2]))
    calc_drafts = np.sort(calc_drafts)
    n_calc = len(calc_drafts)

    Aw = np.zeros(n_calc)
    LCF = np.zeros(n_calc)
    IT = np.zeros(n_calc)
    IL = np.zeros(n_calc)
    Am = np.zeros(n_calc)
    LWL_actual = np.zeros(n_calc)
    BWL_actual = np.zeros(n_calc)
    mid_station = (lpp_start + lpp_end) / 2
    # 中横剖面：与 MATLAB getSectionData 一致，按站号容差(±0.01)查找
    mid_key = None
    if sections is not None:
        for k in sections:
            if abs(float(k) - mid_station) < 0.01:
                mid_key = k
                break

    for i, d in enumerate(calc_drafts):
        if d < 1e-4:
            Aw[i] = LCF[i] = IT[i] = IL[i] = Am[i] = LWL_actual[i] = BWL_actual[i] = 0
            continue
        try:
            wp = calculate_waterplane_at_draft(waterlines, lpp, lpp_start, lpp_end, d)
        except Exception:
            raise
        Aw[i] = wp['area']
        LCF[i] = wp['LCF']
        IT[i] = wp['IT']
        IL[i] = wp['IL']
        LWL_actual[i] = wp['LWL']
        BWL_actual[i] = wp['BWL']
        # 中横剖面面积
        if mid_key is not None:
            sec = sections[mid_key]
            half_y = np.asarray(sec['Y'], dtype=float).ravel()
            z = np.asarray(sec['Z'], dtype=float).ravel()
            if half_y.size >= 2:
                full_y, full_z = construct_symmetric_section(half_y, z)
                water_y, water_z = extract_underwater_section(full_y, full_z, d)
                if water_y.size >= 3:
                    area, _, _ = calculate_section_area_and_moments(water_y, water_z)
                    Am[i] = area

    # 积分（与 MATLAB cumtrapz 一致：首元素为 0）
    DispVol = cumulative_trapezoid(Aw, calc_drafts, initial=0.0)
    MomentZ = cumulative_trapezoid(Aw * calc_drafts, calc_drafts, initial=0.0)
    MomentX = cumulative_trapezoid(Aw * LCF, calc_drafts, initial=0.0)
    rho = 1.025
    DispMass = DispVol * rho
    VCB = np.zeros(n_calc)
    LCB = np.zeros(n_calc)
    valid_vol = DispVol > 1e-6
    VCB[valid_vol] = MomentZ[valid_vol] / DispVol[valid_vol]
    LCB[valid_vol] = MomentX[valid_vol] / DispVol[valid_vol]
    BMT = np.zeros(n_calc)
    BML = np.zeros(n_calc)
    BMT[valid_vol] = IT[valid_vol] / DispVol[valid_vol]
    BML[valid_vol] = IL[valid_vol] / DispVol[valid_vol]
    KMT = VCB + BMT
    KML = VCB + BML
    TPC = Aw * rho / 100
    MCT = (rho * IL) / (100 * lpp)

    b_molded = breadth if breadth and math.isfinite(breadth) else 1.0
    l_molded = lpp
    CB = np.zeros(n_calc)
    CP = np.zeros(n_calc)
    CM = np.zeros(n_calc)
    CW = np.zeros(n_calc)
    idx = calc_drafts > 1e-4
    for i in np.nonzero(idx)[0]:
        if LWL_actual[i] > 1e-4 and BWL_actual[i] > 1e-4 and calc_drafts[i] > 1e-4:
            CB[i] = DispVol[i] / (LWL_actual[i] * BWL_actual[i] * calc_drafts[i])
            CM[i] = Am[i] / (BWL_actual[i] * calc_drafts[i])
            CW[i] = Aw[i] / (LWL_actual[i] * BWL_actual[i])
        else:
            CB[i] = DispVol[i] / (l_molded * b_molded * calc_drafts[i])
            CM[i] = Am[i] / (b_molded * calc_drafts[i])
            CW[i] = Aw[i] / (l_molded * b_molded)
    idx_cp = idx & (Am > 1e-6)
    for i in np.nonzero(idx_cp)[0]:
        if LWL_actual[i] > 1e-4 and Am[i] > 1e-6:
            CP[i] = DispVol[i] / (Am[i] * LWL_actual[i])
        else:
            CP[i] = DispVol[i] / (Am[i] * l_molded)
    idx_fallback = idx & (~idx_cp) & (CM > 1e-9)
    CP[idx_fallback] = CB[idx_fallback] / CM[idx_fallback]

    data = dict(calcDrafts=calc_drafts, Aw=Aw, LCF=LCF, IT=IT, IL=IL,
                DispVol=DispVol, DispMass=DispMass, VCB=VCB, LCB=LCB,
                BMT=BMT, BML=BML, KMT=KMT, KML=KML, TPC=TPC, MCT=MCT,
                CB=CB, CP=CP, CM=CM, CW=CW, Am=Am,
                LWL_actual=LWL_actual, BWL_actual=BWL_actual)

    # 异常点剔除
    if outlier_removal:
        for key in ('Aw', 'DispVol', 'DispMass', 'TPC', 'MCT', 'VCB', 'LCB', 'LCF',
                    'KMT', 'KML', 'BMT', 'BML', 'CB', 'CP', 'CM', 'CW', 'Am',
                    'LWL_actual', 'BWL_actual'):
            clean, valid = remove_outliers_robust(data[key], calc_drafts, outlier_threshold)
            data[key] = clean
            if key == 'Aw':
                n_removed = int(np.sum(~valid))
                data['nRemoved'] = n_removed

    # 插值回用户请求吃水（与 MATLAB interp1(...,'pchip') 一致）
    target = np.linspace(draft_min, draft_max, n_points)
    result = {'drafts': target}
    _SRC = {'dispVolume': 'DispVol', 'dispMass': 'DispMass'}
    for key in ('dispVolume', 'dispMass', 'TPC', 'MCT', 'KMT', 'KML', 'CB', 'CP',
                'CM', 'CW', 'LCB', 'LCF', 'VCB', 'Aw', 'Am', 'BMT', 'BML',
                'LWL_actual', 'BWL_actual'):
        src = _SRC.get(key, key)
        if src in data:
            result[key] = pchip_interp(data['calcDrafts'], data[src], target)
    result['calcDrafts'] = data['calcDrafts']
    return result


# =====================================================================
# 邦戎曲线
# =====================================================================

def calc_bonjean(sections, station_positions, drafts):
    """
    兼容 MATLAB CalculateBonjeanButtonPushed：
    计算邦戎曲线。
    sections: list of dict(Y, Z) 与 stations 对应
    返回 dict(stations, stationPositions, drafts, areas, momentsY, momentsZ,
              centroidsY, centroidsZ)
    """
    n_stations = len(sections)
    n_drafts = len(drafts)
    areas = np.full((n_stations, n_drafts), np.nan)
    moments_y = np.full((n_stations, n_drafts), np.nan)
    moments_z = np.full((n_stations, n_drafts), np.nan)
    centroids_y = np.full((n_stations, n_drafts), np.nan)
    centroids_z = np.full((n_stations, n_drafts), np.nan)
    for s in range(n_stations):
        half_y = np.asarray(sections[s]['Y'], dtype=float).ravel()
        z = np.asarray(sections[s]['Z'], dtype=float).ravel()
        if half_y.size == 0 or z.size == 0:
            continue
        full_y, full_z = construct_symmetric_section(half_y, z)
        for d in range(n_drafts):
            draft = drafts[d]
            water_y, water_z = extract_underwater_section(full_y, full_z, draft)
            if water_y.size < 3:
                continue
            area, my, mz = calculate_section_area_and_moments(water_y, water_z)
            areas[s, d] = area
            moments_y[s, d] = my
            moments_z[s, d] = mz
            if area > 1e-6:
                centroids_y[s, d] = my / area
                centroids_z[s, d] = mz / area
    return dict(stations=station_positions if len(station_positions) == n_stations else None,
                stationPositions=np.asarray(station_positions),
                drafts=np.asarray(drafts), areas=areas, momentsY=moments_y,
                momentsZ=moments_z, centroidsY=centroids_y, centroidsZ=centroids_z)


# =====================================================================
# 稳性计算
# =====================================================================

def interp1_linear_extrap(x, xp, fp):
    """MATLAB interp1(..., 'linear', 'extrap') 兼容：线性插值 + 端部线性外插。

    xp/fp 按 xp 升序处理（内部排序，不修改原数组）。标量 x 返回标量。
    """
    xp = np.asarray(xp, dtype=float).ravel()
    fp = np.asarray(fp, dtype=float).ravel()
    x = np.asarray(x, dtype=float)
    scalar = x.ndim == 0
    x = np.atleast_1d(x)
    if xp.size < 2:
        out = np.full(x.shape, np.nan)
        return float(out[0]) if scalar else out
    order = np.argsort(xp)
    xp = xp[order]
    fp = fp[order]
    out = np.interp(x, xp, fp)  # 区间内线性；区间外默认钳制到端点
    # 端部外插：线性延伸
    for side, (x0, y0, x1, y1) in (
            ('lo', (xp[0], fp[0], xp[1], fp[1])),
            ('hi', (xp[-2], fp[-2], xp[-1], fp[-1]))):
        if side == 'lo' and x1 - x0 > 1e-12:
            m = (y1 - y0) / (x1 - x0)
            mask = x < x0
            out[mask] = y0 + (x[mask] - x0) * m
        elif side == 'hi' and x1 - x0 > 1e-12:
            m = (y1 - y0) / (x1 - x0)
            mask = x > x1
            out[mask] = y1 + (x[mask] - x1) * m
    return float(out[0]) if scalar else out


def calc_kn_curves(section_data_fn, lpp, lpp_start, lpp_end, depth, heels, drafts):
    """
    兼容 MATLAB CalculateKNButtonPushed：
    计算稳性横截曲线 KN。
    section_data_fn(heel, draft) -> dict(volume, xB, yB, zB)（调用浮心计算）
    返回 dict(heels, drafts, KN, Displacement)
    """
    heels = np.sort(np.unique(heels))
    drafts = np.sort(np.unique(drafts))
    n_heels = len(heels)
    n_drafts = len(drafts)
    kn_data = np.full((n_drafts, n_heels), np.nan)
    disp_data = np.full((n_drafts, n_heels), np.nan)
    for i, phi in enumerate(heels):
        for j, t in enumerate(drafts):
            res = section_data_fn(phi, t)
            v = res['volume']
            c = [res['xB'], res['yB'], res['zB']]
            if not math.isfinite(v):
                continue
            y_b = c[1]
            z_b = c[2]
            phi_rad = math.radians(phi)
            kn = y_b * math.cos(phi_rad) + z_b * math.sin(phi_rad)
            kn_data[j, i] = kn
            disp_data[j, i] = v * 1.025
    return dict(heels=heels, drafts=drafts, KN=kn_data, Displacement=disp_data)


def calc_gz_curve(kn_curves, ship_weight, xg, yg, kg):
    """
    兼容 MATLAB CalculateGZButtonPushed：
    根据 KN 曲线插值计算 GZ 静稳性曲线。
    """
    heels = np.asarray(kn_curves['heels'], dtype=float).ravel()
    n_heels = len(heels)
    gz = np.full(n_heels, np.nan)
    for i in range(n_heels):
        disps = kn_curves['Displacement'][:, i]
        kns = kn_curves['KN'][:, i]
        valid = np.isfinite(disps) & np.isfinite(kns)
        if np.sum(valid) < 2:
            continue
        # MATLAB: interp1(..., 'linear', 'extrap') —— np.interp 在区间外只钳制，
        # 必须用带外插的线性插值，避免 KN 在排水量端点处被错误钳制。
        kn_val = float(interp1_linear_extrap(ship_weight, disps[valid], kns[valid]))
        phi_rad = math.radians(heels[i])
        gz[i] = kn_val - kg * math.sin(phi_rad) - yg * math.cos(phi_rad)
    return gz


def calc_dynamic_stability(heels, gz, displacement, kg, hydrostatics=None,
                           current_draft=None):
    """
    兼容 MATLAB CalculateDynamicButtonPushed：
    计算动稳性曲线、GM、最小倾覆力臂 lq、最大风倾力臂 lf、稳性衡准数 K。
    返回 dict(heels, GZ, dynamicArm, GM, lq, lq_angle, lf, theta_G, theta_K,
              stabilityK, stabilityKStatus, vanishAngle, maxGZ, angleMaxGZ)
    """
    heels = np.asarray(heels, dtype=float).ravel()
    gz = np.asarray(gz, dtype=float).ravel()
    heels_rad = np.deg2rad(heels)
    n = len(heels)
    dynamic_arm = np.zeros(n)
    for i in range(1, n):
        dynamic_arm[i] = np.trapezoid(gz[:i + 1], heels_rad[:i + 1])
    # GM
    gm = math.nan
    if hydrostatics is not None and 'KMT' in hydrostatics and len(hydrostatics.get('drafts', [])) > 0:
        if current_draft is not None and math.isfinite(current_draft) and current_draft > 0:
            try:
                # MATLAB: interp1(..., 'linear', 'extrap')
                kmt = float(interp1_linear_extrap(
                    current_draft, hydrostatics['drafts'], hydrostatics['KMT']))
                gm = kmt - kg
            except Exception:
                pass
    if not math.isfinite(gm) and n >= 2 and heels[0] == 0:
        gm = (gz[1] - gz[0]) / heels_rad[1]
    if not math.isfinite(gm) and n >= 2:
        small_idx = None
        for i in range(1, n):
            if heels[i] <= 15 and heels[i] > 0:
                small_idx = i
                break
        if small_idx is not None and heels[0] == 0:
            gm = gz[small_idx] / math.sin(heels_rad[small_idx])

    # 消失角
    vanish_idx = n - 1
    for i in range(1, n):
        if gz[i] <= 0 < gz[i - 1]:
            vanish_idx = i
            break
    vanish_angle_idx = vanish_idx + 1
    if vanish_angle_idx > n:
        vanish_angle_idx = n

    # lq：最小倾覆力臂（动稳性曲线切线法）
    # MATLAB: lq_candidates(i)=S(θ)/θ, i=2..vanishAngleIdx (0-based 1..vanish-1)
    lq_candidates = np.full(n, np.nan)
    for i in range(1, vanish_angle_idx):
        if heels_rad[i] > 0 and dynamic_arm[i] > 0:
            lq_candidates[i] = dynamic_arm[i] / heels_rad[i]
    # maxGZIdx_temp = max(GZ(1:vanishAngleIdx)) → 0-based max_gz_idx
    max_gz_idx = int(np.argmax(gz[:vanish_angle_idx]))
    # 方法1：在 GZ 最大值点之后至消失角范围内取 S(θ)/θ 最小者
    if max_gz_idx + 1 < vanish_angle_idx:   # MATLAB: maxGZIdx_temp < vanishAngleIdx
        search_range = lq_candidates[max_gz_idx:vanish_angle_idx]
        valid_range = search_range[np.isfinite(search_range)]
        if valid_range.size > 0:
            lq_min = float(np.min(valid_range))
            rel = int(np.argmax(search_range == lq_min))
            lq_angle_idx = max_gz_idx + rel
        else:
            lq_min = float(gz[max_gz_idx])
            lq_angle_idx = max_gz_idx
    else:  # MATLAB else: min(lq_candidates(2:vanishAngleIdx))
        search_range = lq_candidates[1:vanish_angle_idx]
        valid_range = search_range[np.isfinite(search_range)]
        if valid_range.size > 0:
            lq_min = float(np.min(valid_range))
            lq_angle_idx = int(np.argmax(search_range == lq_min)) + 1
        else:
            lq_min = float(np.max(gz))
            lq_angle_idx = int(np.argmax(gz))
    # 方法2：验证切点条件 |S(θ)/θ - GZ(θ)| 是否在 20% 内；否则重搜最接近 GZ 的点
    lq = lq_min
    if lq_angle_idx >= 1 and lq_angle_idx <= vanish_angle_idx - 1:
        slope_at = lq_candidates[lq_angle_idx]   # S(θ)/θ
        gz_at = gz[lq_angle_idx]                 # GZ(θ)=dS/dθ
        if (math.isfinite(slope_at) and math.isfinite(gz_at)
                and abs(slope_at - gz_at) / max(abs(gz_at), 0.001) > 0.2):
            diff_arr = np.full(n, np.inf)
            for i in range(max_gz_idx, vanish_angle_idx):
                if (heels_rad[i] > 0 and dynamic_arm[i] > 0
                        and math.isfinite(lq_candidates[i])):
                    diff_arr[i] = abs(lq_candidates[i] - gz[i])
            sub = diff_arr[max_gz_idx:vanish_angle_idx]
            rel = int(np.argmin(sub))
            lq_angle_idx = max_gz_idx + rel
            lq = float(lq_candidates[lq_angle_idx])
    if not math.isfinite(lq) or lq <= 0:
        lq = float(np.max(gz))
        lq_angle_idx = int(np.argmax(gz))
    lq_angle = float(heels[lq_angle_idx])

    # lf：等面积法
    max_gz_val = float(np.max(gz[:vanish_angle_idx]))
    lf = math.nan
    theta_g = math.nan
    theta_k = math.nan
    lf_low = 0.0
    lf_high = max_gz_val * 0.99
    if lf_high > 1e-9:
        for _ in range(100):
            lf_mid = (lf_low + lf_high) / 2
            crossings_up = []
            crossings_down = []
            for i in range(vanish_angle_idx - 1):
                if gz[i] < lf_mid <= gz[i + 1]:
                    t = (lf_mid - gz[i]) / (gz[i + 1] - gz[i])
                    crossings_up.append(heels_rad[i] + t * (heels_rad[i + 1] - heels_rad[i]))
                elif gz[i] >= lf_mid > gz[i + 1]:
                    t = (lf_mid - gz[i]) / (gz[i + 1] - gz[i])
                    crossings_down.append(heels_rad[i] + t * (heels_rad[i + 1] - heels_rad[i]))
            if not crossings_up or not crossings_down:
                if not crossings_up:
                    lf_high = lf_mid
                else:
                    lf_low = lf_mid
                continue
            g_rad = crossings_up[0]
            k_rad = crossings_down[0]
            if g_rad >= k_rad:
                lf_high = lf_mid
                continue
            area_ofg = lf_mid * g_rad
            idx_range = np.nonzero((heels_rad >= g_rad) & (heels_rad <= k_rad))[0]
            if idx_range.size < 2:
                theta_interp = np.linspace(g_rad, k_rad, 50)
                gz_interp = np.interp(theta_interp, heels_rad, gz)
                area_ghk = np.trapezoid(gz_interp - lf_mid, theta_interp)
            else:
                theta_range = np.concatenate([[g_rad], heels_rad[idx_range], [k_rad]])
                gz_range = np.concatenate([[lf_mid], gz[idx_range], [lf_mid]])
                u, o = np.unique(theta_range, return_index=True)
                gz_range = gz_range[o]
                area_ghk = np.trapezoid(gz_range - lf_mid, u)
            area_diff = area_ofg - area_ghk
            if abs(area_diff) < 0.0001 * g_rad:
                lf = lf_mid
                theta_g = math.degrees(g_rad)
                theta_k = math.degrees(k_rad)
                break
            elif area_diff > 0:
                lf_high = lf_mid
            else:
                lf_low = lf_mid
    if not math.isfinite(lf):
        lf = max_gz_val * 0.5

    # 稳性衡准数
    if math.isfinite(lq) and math.isfinite(lf) and lf > 0 and lq > 0:
        stability_k = lq / lf
        status = 'K = %.2f ≥ 1.0 (满足安全要求)' % stability_k if stability_k >= 1.0 else \
                 'K = %.2f < 1.0 (不满足要求!)' % stability_k
    else:
        stability_k = math.nan
        if not math.isfinite(lq) or lq <= 0:
            status = '最小倾覆力臂lq无法计算'
        else:
            status = '最大风倾力臂lf无法计算(检查船舶参数)'

    max_gz = float(np.max(gz))
    angle_max_gz = float(heels[int(np.argmax(gz))])
    # 消失角（精确插值）
    angle_vanish = float(heels[-1])
    for i in range(1, n):
        if gz[i] <= 0 < gz[i - 1]:
            x1, y1 = heels[i - 1], gz[i - 1]
            x2, y2 = heels[i], gz[i]
            angle_vanish = x1 - y1 * (x2 - x1) / (y2 - y1)
            break
    return dict(heels=heels, GZ=gz, dynamicArm=dynamic_arm, GM=gm,
                lq=lq, lq_angle=lq_angle, lf=lf, theta_G=theta_g, theta_K=theta_k,
                stabilityK=stability_k, stabilityKStatus=status,
                vanishAngle=angle_vanish, maxGZ=max_gz, angleMaxGZ=angle_max_gz,
                maxGZIdx=int(np.argmax(gz)), lq_angle_idx=lq_angle_idx)


def check_stability_regulations(dyn_result, breadth, depth):
    """
    兼容 MATLAB 稳性校核部分：
    依据《国内航行海船法定检验技术规则》(2011) 检查 GM / 极限静倾角 / 衡准数 K。
    返回 (checkResults, isPassed)
    """
    check_results = []
    is_passed = True
    gm = dyn_result['GM']
    # 1. GM
    if math.isfinite(gm):
        if gm >= 0.15:
            check_results.append('[√] GM=%.3fm (要求≥0.15m) 合格' % gm)
        else:
            check_results.append('[×] GM=%.3fm (要求≥0.15m) 不合格' % gm)
            is_passed = False
    else:
        check_results.append('[?] GM无法计算')
        is_passed = False
    # 2. 最大复原力臂对应角度
    req_angle = 25.0
    bd_msg = ''
    if breadth is not None and depth and depth > 0 and math.isfinite(breadth) and math.isfinite(depth):
        bd_ratio = breadth / depth
        if bd_ratio > 2.0:
            reduction = 20 * (bd_ratio - 2)
            reduction = min(reduction, 10)
            req_angle = 25.0 - reduction
            bd_msg = '(B/D=%.2f,要求放宽)' % bd_ratio
    if dyn_result['angleMaxGZ'] >= req_angle - 0.01:
        check_results.append('[√] GZmax角=%.1f° (要求≥%.1f°) %s 合格' % (
            dyn_result['angleMaxGZ'], req_angle, bd_msg))
    else:
        check_results.append('[×] GZmax角=%.1f° (要求≥%.1f°) %s 不合格' % (
            dyn_result['angleMaxGZ'], req_angle, bd_msg))
        is_passed = False
    # 3. 衡准数 K
    k = dyn_result['stabilityK']
    if math.isfinite(k):
        if k >= 1.0:
            check_results.append('[√] 衡准数K=%.2f (要求≥1.0) 合格' % k)
        else:
            check_results.append('[×] 衡准数K=%.2f (要求≥1.0) 不合格' % k)
            is_passed = False
    else:
        check_results.append('[?] K无法计算')
        is_passed = False
    return check_results, is_passed


# =====================================================================
# 异常点剔除
# =====================================================================

def remove_outliers_robust(data, x, threshold=3.0):
    """
    兼容 MATLAB removeOutliersRobust：
    综合局部中位数、一阶导数、二阶导数三种策略剔除异常点，
    并用插值填充。
    返回 (cleanData, validIdx)
    """
    data = np.asarray(data, dtype=float).ravel()
    x = np.asarray(x, dtype=float).ravel()
    n = data.size
    if n < 5:
        return data.copy(), np.ones(n, dtype=bool)
    window_size = max(5, round(n / 10))
    local_median = np.zeros(n)
    local_mad = np.zeros(n)
    for i in range(n):
        start = max(0, i - window_size // 2)
        end = min(n, i + window_size // 2 + 1)
        window = data[start:end]
        local_median[i] = np.median(window)
        local_mad[i] = np.median(np.abs(window - local_median[i]))
    local_std = local_mad * 1.4826
    local_std[local_std < 1e-10] = np.std(data)
    deviation = np.abs(data - local_median)
    outliers1 = deviation > threshold * local_std

    outliers2 = np.zeros(n, dtype=bool)
    if n >= 3:
        dx = np.diff(x)
        dx[dx < 1e-10] = 1e-10
        dy = np.diff(data)
        grad = dy / dx
        med_grad = np.median(grad)
        mad_grad = np.median(np.abs(grad - med_grad))
        std_grad = mad_grad * 1.4826
        if std_grad < 1e-10:
            std_grad = np.std(grad)
        grad_out = np.abs(grad - med_grad) > threshold * std_grad
        for i in range(len(grad_out)):
            if grad_out[i]:
                if 0 < i < len(grad_out) - 1 and grad_out[i + 1]:
                    outliers2[i + 1] = True
    outliers3 = np.zeros(n, dtype=bool)
    if n >= 4:
        second_diff = np.diff(np.diff(data))
        med_second = np.median(second_diff)
        mad_second = np.median(np.abs(second_diff - med_second))
        std_second = mad_second * 1.4826
        if std_second < 1e-10:
            std_second = np.std(second_diff)
        curv_out = np.abs(second_diff - med_second) > threshold * std_second
        for idx in np.nonzero(curv_out)[0]:
            if idx + 1 < n:
                outliers3[idx + 1] = True
    outlier_count = outliers1.astype(int) + outliers2.astype(int) + outliers3.astype(int)
    valid_idx = outlier_count < 2
    valid_idx[:min(2, n)] = True
    valid_idx[max(0, n - 1):n] = True
    is_monotonic = np.all(np.diff(data) >= -1e-6) or np.all(np.diff(data) <= 1e-6)
    if is_monotonic:
        valid_idx = valid_idx | (outlier_count < 1)
    clean = data.copy()
    invalid_idx = np.nonzero(~valid_idx)[0]
    valid_points = np.nonzero(valid_idx)[0]
    if invalid_idx.size > 0 and valid_points.size >= 2:
        clean[invalid_idx] = np.interp(x[invalid_idx], x[valid_points], data[valid_points])
    return clean, valid_idx


# =====================================================================
# 曲线拟合辅助
# =====================================================================

def polyfit_rmse(x, y, deg):
    """多项式拟合并返回 (系数, RMSE)"""
    coeff = np.polyfit(x, y, deg)
    yhat = np.polyval(coeff, x)
    rmse = float(np.sqrt(np.mean((y - yhat) ** 2)))
    return coeff, rmse


def poly_expr(coeff):
    """生成多项式表达字符串 f(x) = ..."""
    terms = []
    p = len(coeff) - 1
    for i, a in enumerate(coeff):
        if abs(a) < 1e-12:
            continue
        power = p - i
        if power == 0:
            term = '%.6g' % a
        elif power == 1:
            term = '%.6g*x' % a
        else:
            term = '%.6g*x^%d' % (a, power)
        terms.append(term)
    if not terms:
        return 'f(x) = 0'
    expr = 'f(x) = ' + ' + '.join(terms)
    expr = expr.replace('+ -', '- ')
    return expr
