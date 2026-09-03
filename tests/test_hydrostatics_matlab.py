# -*- coding: utf-8 -*-
import os as _os
import sys as _sys
_sys.path.insert(0, _os.path.dirname(_os.path.dirname(_os.path.abspath(__file__))))
"""验证 calc_hydrostatics / calc_bonjean 与 MATLAB ship.m 公式逐行一致。

测试方法：将 ship.m 的 CalculateCurvesButtonPushed / CalculateBonjeanButtonPushed
逐行翻译成参考实现（ref），输入同一套船体数据，比较输出。
"""
import numpy as np
from src.core import ship_core as core

ok = True


def check(name, a, b, rtol=1e-9, atol=1e-9):
    global ok
    a = np.asarray(a, dtype=float)
    b = np.asarray(b, dtype=float)
    same = a.shape == b.shape and np.allclose(a, b, rtol=rtol, atol=atol, equal_nan=True)
    print('[%s] %s  max|a-b|=%.3e' % ('PASS' if same else 'FAIL', name,
                                      np.nanmax(np.abs(a - b)) if a.size else 0))
    if not same:
        ok = False


# ================= 构造同一套船体数据 =================
st = np.linspace(0, 10, 11)
base = 6.0 * np.sin(np.pi * st / 10.0)
wls = [
    {'stations': st, 'halfWidths': base, 'height': 0.0},
    {'stations': st, 'halfWidths': base * 0.95, 'height': 2.0},
    {'stations': st, 'halfWidths': base * 0.88, 'height': 4.0},
    {'stations': st, 'halfWidths': base * 0.78, 'height': 6.0},
]
# 横剖面：各站剖面，高度 0..6，半宽随 z 收拢
z = np.linspace(0, 6, 13)
sections = {}
for s in st:
    b0 = 6.0 * np.sin(np.pi * s / 10.0)
    y = np.clip(b0 * (1.0 - (z / 6.0) ** 2 * 0.6), 0, None)
    sections[float(s)] = {'Y': y, 'Z': z}

LPP, S0, S1, BREADTH = 100.0, 0.0, 10.0, 12.0
DMIN, DMAX, NPOINTS = 0.2, 5.0, 15


# ================= MATLAB 参考实现（逐行翻译） =================
def ref_cumtrapz(x, y):
    """MATLAB cumtrapz(x, y)：首元素为 0"""
    dx = np.diff(np.asarray(x, dtype=float))
    yy = np.asarray(y, dtype=float)
    out = np.zeros_like(yy)
    if yy.size > 1:
        np.cumsum(0.5 * dx * (yy[:-1] + yy[1:]), out=out[1:])
    return out


def ref_pchip(xp, fp, x):
    """MATLAB interp1(xp, fp, x, 'pchip')"""
    from scipy.interpolate import PchipInterpolator
    return PchipInterpolator(np.asarray(xp), np.asarray(fp))(np.asarray(x))


def ref_curves(wls, sections, lpp, lpp_start, lpp_end, breadth, dmin, dmax, n_points,
               outlier_removal=False, outlier_threshold=3.0):
    n1 = max(50, round(n_points * (dmax / (dmax - dmin + 0.1))))
    calc = np.sort(np.unique(np.concatenate([
        np.linspace(0, dmax, n1), np.linspace(dmin, dmax, n_points)])))
    n = len(calc)
    Aw = np.zeros(n); LCF = np.zeros(n); IT = np.zeros(n); IL = np.zeros(n)
    Am = np.zeros(n); LWL = np.zeros(n); BWL = np.zeros(n)
    mid = (lpp_start + lpp_end) / 2
    mid_key = None
    if sections:
        for k in sections:
            if abs(float(k) - mid) < 0.01:
                mid_key = k
                break
    for i, d in enumerate(calc):
        if d < 1e-4:
            continue
        wp = core.calculate_waterplane_at_draft(wls, lpp, lpp_start, lpp_end, d)
        Aw[i] = wp['area']; LCF[i] = wp['LCF']; IT[i] = wp['IT']; IL[i] = wp['IL']
        LWL[i] = wp['LWL']; BWL[i] = wp['BWL']
        if mid_key is not None:
            fy, fz = core.construct_symmetric_section(sections[mid_key]['Y'],
                                                      sections[mid_key]['Z'])
            wy, wz = core.extract_underwater_section(fy, fz, d)
            if wy.size >= 3:
                a, _, _ = core.calculate_section_area_and_moments(wy, wz)
                Am[i] = a
    DV = ref_cumtrapz(calc, Aw)
    MZ = ref_cumtrapz(calc, Aw * calc)
    MX = ref_cumtrapz(calc, Aw * LCF)
    rho = 1.025
    DM = DV * rho
    vv = DV > 1e-6
    VCB = np.zeros(n); LCB = np.zeros(n)
    VCB[vv] = MZ[vv] / DV[vv]; LCB[vv] = MX[vv] / DV[vv]
    BMT = np.zeros(n); BML = np.zeros(n)
    BMT[vv] = IT[vv] / DV[vv]; BML[vv] = IL[vv] / DV[vv]
    KMT = VCB + BMT; KML = VCB + BML
    TPC = Aw * rho / 100
    MCT = (rho * IL) / (100 * lpp)
    bm = breadth if breadth and np.isfinite(breadth) else 1.0
    lm = lpp
    CB = np.zeros(n); CP = np.zeros(n); CM = np.zeros(n); CW = np.zeros(n)
    idx = calc > 1e-4
    for i in np.nonzero(idx)[0]:
        if LWL[i] > 1e-4 and BWL[i] > 1e-4 and calc[i] > 1e-4:
            CB[i] = DV[i] / (LWL[i] * BWL[i] * calc[i])
            CM[i] = Am[i] / (BWL[i] * calc[i])
            CW[i] = Aw[i] / (LWL[i] * BWL[i])
        else:
            CB[i] = DV[i] / (lm * bm * calc[i])
            CM[i] = Am[i] / (bm * calc[i])
            CW[i] = Aw[i] / (lm * bm)
    idx_cp = idx & (Am > 1e-6)
    for i in np.nonzero(idx_cp)[0]:
        if LWL[i] > 1e-4 and Am[i] > 1e-6:
            CP[i] = DV[i] / (Am[i] * LWL[i])
        else:
            CP[i] = DV[i] / (Am[i] * lm)
    f = idx & (~idx_cp) & (CM > 1e-9)
    CP[f] = CB[f] / CM[f]
    # 异常点剔除（与 MATLAB CalculateCurvesButtonPushed 第 7 步完全一致）
    if outlier_removal:
        for key in ('Aw', 'DispVol', 'DispMass', 'TPC', 'MCT', 'VCB', 'LCB', 'LCF',
                    'KMT', 'KML', 'BMT', 'BML', 'CB', 'CP', 'CM', 'CW', 'Am',
                    'LWL_actual', 'BWL_actual'):
            v = {'Aw': Aw, 'DispVol': DV, 'DispMass': DM, 'TPC': TPC, 'MCT': MCT,
                 'VCB': VCB, 'LCB': LCB, 'LCF': LCF, 'KMT': KMT, 'KML': KML,
                 'BMT': BMT, 'BML': BML, 'CB': CB, 'CP': CP, 'CM': CM, 'CW': CW,
                 'Am': Am, 'LWL_actual': LWL, 'BWL_actual': BWL}[key]
            clean, _ = core.remove_outliers_robust(v, calc, outlier_threshold)
            if key == 'Aw':
                Aw = clean
            elif key == 'DispVol':
                DV = clean
            elif key == 'DispMass':
                DM = clean
            elif key == 'TPC':
                TPC = clean
            elif key == 'MCT':
                MCT = clean
            elif key == 'VCB':
                VCB = clean
            elif key == 'LCB':
                LCB = clean
            elif key == 'LCF':
                LCF = clean
            elif key == 'KMT':
                KMT = clean
            elif key == 'KML':
                KML = clean
            elif key == 'BMT':
                BMT = clean
            elif key == 'BML':
                BML = clean
            elif key == 'CB':
                CB = clean
            elif key == 'CP':
                CP = clean
            elif key == 'CM':
                CM = clean
            elif key == 'CW':
                CW = clean
            elif key == 'Am':
                Am = clean
            elif key == 'LWL_actual':
                LWL = clean
            elif key == 'BWL_actual':
                BWL = clean
    tgt = np.linspace(dmin, dmax, n_points)
    R = {'drafts': tgt}
    for key, src in [('dispVolume', DV), ('dispMass', DM), ('TPC', TPC), ('MCT', MCT),
                     ('KMT', KMT), ('KML', KML), ('CB', CB), ('CP', CP), ('CM', CM),
                     ('CW', CW), ('LCB', LCB), ('LCF', LCF), ('VCB', VCB), ('Aw', Aw),
                     ('Am', Am), ('BMT', BMT), ('BML', BML),
                     ('LWL_actual', LWL), ('BWL_actual', BWL)]:
        R[key] = ref_pchip(calc, src, tgt)
    return R


def ref_bonjean(sections, station_positions, drafts):
    ns = len(sections); nd = len(drafts)
    areas = np.full((ns, nd), np.nan)
    my = np.full((ns, nd), np.nan); mz = np.full((ns, nd), np.nan)
    cy = np.full((ns, nd), np.nan); cz = np.full((ns, nd), np.nan)
    for s in range(ns):
        fy, fz = core.construct_symmetric_section(sections[s]['Y'], sections[s]['Z'])
        for d in range(nd):
            wy, wz = core.extract_underwater_section(fy, fz, drafts[d])
            if wy.size < 3:
                continue
            a, My, Mz = core.calculate_section_area_and_moments(wy, wz)
            areas[s, d] = a; my[s, d] = My; mz[s, d] = Mz
            if a > 1e-6:
                cy[s, d] = My / a; cz[s, d] = Mz / a
    return dict(areas=areas, momentsY=my, momentsZ=mz, centroidsY=cy, centroidsZ=cz)


# ================= 对比 =================
print('=' * 60)
print('静水力曲线：Python vs MATLAB 公式参考')
print('=' * 60)
py = core.calc_hydrostatics(wls, sections, LPP, S0, S1, BREADTH, DMIN, DMAX, NPOINTS)
ref = ref_curves(wls, sections, LPP, S0, S1, BREADTH, DMIN, DMAX, NPOINTS)

check('drafts', py['drafts'], ref['drafts'])
check('dispVolume', py['dispVolume'], ref['dispVolume'])
check('dispMass', py['dispMass'], ref['dispMass'])
check('TPC', py['TPC'], ref['TPC'])
check('MCT', py['MCT'], ref['MCT'])
check('KMT', py['KMT'], ref['KMT'])
check('KML', py['KML'], ref['KML'])
check('CB', py['CB'], ref['CB'])
check('CP', py['CP'], ref['CP'])
check('CM', py['CM'], ref['CM'])
check('CW', py['CW'], ref['CW'])
check('LCB', py['LCB'], ref['LCB'])
check('LCF', py['LCF'], ref['LCF'])
check('VCB', py['VCB'], ref['VCB'])
check('Aw', py['Aw'], ref['Aw'])
check('Am', py['Am'], ref['Am'])
check('BMT', py['BMT'], ref['BMT'])
check('BML', py['BML'], ref['BML'])
check('LWL_actual', py['LWL_actual'], ref['LWL_actual'])
check('BWL_actual', py['BWL_actual'], ref['BWL_actual'])

# 异常点剔除路径也对比一次
py2 = core.calc_hydrostatics(wls, sections, LPP, S0, S1, BREADTH, DMIN, DMAX, NPOINTS,
                             outlier_removal=True, outlier_threshold=3.0)
ref2 = ref_curves(wls, sections, LPP, S0, S1, BREADTH, DMIN, DMAX, NPOINTS,
                  outlier_removal=True, outlier_threshold=3.0)
for key in ('dispVolume', 'dispMass', 'TPC', 'MCT', 'KMT', 'KML', 'CB', 'CP', 'CM',
            'CW', 'VCB', 'LCB', 'LCF', 'Aw', 'Am', 'BMT', 'BML',
            'LWL_actual', 'BWL_actual'):
    check('outlier:' + key, py2[key], ref2[key], rtol=1e-9, atol=1e-9)

print()
print('=' * 60)
print('邦戎曲线：Python vs MATLAB 公式参考')
print('=' * 60)
drafts = np.linspace(DMIN, DMAX, 9)
sec_list = [sections[float(s)] for s in sorted(sections)]
pos = [(float(s) - S0) * LPP / (S1 - S0) - LPP / 2 for s in sorted(sections)]
pb = core.calc_bonjean(sec_list, pos, drafts)
rb = ref_bonjean(sec_list, pos, drafts)
check('areas', pb['areas'], rb['areas'])
check('momentsY', pb['momentsY'], rb['momentsY'])
check('momentsZ', pb['momentsZ'], rb['momentsZ'])
check('centroidsY', pb['centroidsY'], rb['centroidsY'], atol=1e-9)
check('centroidsZ', pb['centroidsZ'], rb['centroidsZ'], atol=1e-9)

print()
print('HYDROSTATICS/BONJEAN MATLAB-CONSISTENCY %s' % ('PASS' if ok else 'FAIL'))
