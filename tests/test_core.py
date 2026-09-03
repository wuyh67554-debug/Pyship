# -*- coding: utf-8 -*-
import os as _os
import sys as _sys
_sys.path.insert(0, _os.path.dirname(_os.path.dirname(_os.path.abspath(__file__))))
"""核心算法自检脚本"""
import numpy as np
import math
from src.core import ship_core as core

ok = True


def check(name, cond, detail=''):
    global ok
    status = 'PASS' if cond else 'FAIL'
    if not cond:
        ok = False
    print('[%s] %s %s' % (status, name, detail))


# 1. 水线面分段计算
station = np.arange(0, 11, dtype=float)
half = 10 * np.sin(station / 10 * np.pi)
coeff = np.ones(11)
arm = station - 5
segs = np.array([[1, 11, 1.0, np.nan]])
res = core.calc_waterplane_segments(station, half, coeff, arm, segs, 1.0, 100, 0, 10)
# 物理间距：Lpp=100m 分布在 10 个站号上 → 每站 10m
x_phys = station * 10.0
expected_half = np.trapezoid(half, x_phys)
check('水线面半船面积', abs(res['half_a'] - expected_half) < 1e-6,
      'got=%.4f expected=%.4f' % (res['half_a'], expected_half))
expected_lcf = np.trapezoid(x_phys * half, x_phys) / expected_half - 50
check('水线面漂心LCF', abs(res['lcf'] - expected_lcf) < 1e-6,
      'got=%.4f expected=%.4f' % (res['lcf'], expected_lcf))

# 2. 横剖面面积与形心
h = np.array([0, 2, 4, 6], dtype=float)
b = np.array([0, 8, 9, 5], dtype=float)
c = np.ones(4)
sec = core.calc_transverse_section(h, b, c, 'trapezoidal')
exp_area = np.trapezoid(b, h)
check('横剖面半船面积', abs(sec['halfArea'] - exp_area) < 1e-6,
      'got=%.4f expected=%.4f' % (sec['halfArea'], exp_area))
exp_mz = np.trapezoid(b * h, h)
check('横剖面形心Z', abs(sec['centroid_z'] - exp_mz / exp_area) < 1e-6,
      'got=%.4f expected=%.4f' % (sec['centroid_z'], exp_mz / exp_area))

# 3. 水下截取 + Shoelace
fy = np.array([-8, -8, 8, 8], dtype=float)
fz = np.array([0, 6, 6, 0], dtype=float)
wy, wz = core.extract_underwater_section(fy, fz, 3.0)
a, my, mz = core.calculate_section_area_and_moments(wy, wz)
check('水下矩形面积@draft3', abs(a - 48.0) < 1e-6, 'got=%.4f' % a)

# 4. 吃水插值水线面
wls = [{'stations': np.array([0, 5, 10]), 'halfWidths': np.array([0, 10, 0]), 'height': 2.0},
       {'stations': np.array([0, 5, 10]), 'halfWidths': np.array([0, 12, 0]), 'height': 4.0}]
wp = core.calculate_waterplane_at_draft(wls, 100, 0, 10, 3.0)
# draft3: 中间站半宽=11, 端部=0, 物理x=站号*10 → 面积=2*0.5*50*11*2=1100
check('吃水3处水线面面积', abs(wp['area'] - 1100.0) < 1e-6, 'got=%.4f' % wp['area'])
check('吃水3处LCF=0', abs(wp['LCF']) < 1e-9, 'got=%.4f' % wp['LCF'])

# 5. 异常点剔除（与MATLAB一致：需>=2个策略同时判定才剔除，单策略不剔除）
data = np.array([1, 2, 3, 50, 5, 6, 7, 8, 9, 10.], dtype=float)
x = np.arange(10, dtype=float)
clean, valid = core.remove_outliers_robust(data, x, 3.0)
check('异常点剔除-保守策略与MATLAB一致', valid[3] == True and clean.size == data.size,
      'valid=%s' % valid.tolist())

# 6. 浮心（基于水线面）
res_b = core.calc_buoyancy_from_waterplane(wls, 100, 0, 10, 4.0)
check('浮心体积>0', res_b['volume'] > 0, 'V=%.4f' % res_b['volume'])

# 7. 邦戎曲线
sections = [{'Y': np.array([0, 8, 8, 0.]), 'Z': np.array([0, 0, 6, 6.])}]
bj = core.calc_bonjean(sections, [0], np.linspace(0, 4, 5))
check('邦戎面积>0', np.all(np.isfinite(bj['areas'][0, 1:])), str(bj['areas'][0, 1:]))

# 8. 动稳性
heels = np.arange(0, 61, 10, dtype=float)
gz = 0.5 * np.sin(np.deg2rad(heels))
dyn = core.calc_dynamic_stability(heels, gz, 1000, 3.0)
check('动稳性GM>0', math.isfinite(dyn['GM']) and dyn['GM'] > 0, 'GM=%.4f' % dyn['GM'])
check('动稳性lq/lf计算', math.isfinite(dyn['lq']) and math.isfinite(dyn['lf']),
      'lq=%.4f lf=%.4f' % (dyn['lq'], dyn['lf']))

# 9. 特征提取
feats, warns = __import__('src.core.ml_utils', fromlist=['ml_utils']).extract_prediction_features(
    np.arange(16, dtype=float).reshape(4, 4))
check('特征提取12列', feats.shape == (4, 12), str(feats.shape))

# 10. 分段检测
segs = core.detect_segments_by_station(np.array([0, 1, 2, 3, 5, 7, 9.]), 1e-9)
check('分段检测', len(segs) == 2, str(segs))

print()
print('ALL PASS' if ok else 'SOME FAILED')
