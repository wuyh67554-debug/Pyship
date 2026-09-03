# -*- coding: utf-8 -*-
import os as _os
import sys as _sys
_sys.path.insert(0, _os.path.dirname(_os.path.dirname(_os.path.abspath(__file__))))
"""classifier.py 完整测试"""
import os
import tempfile
import numpy as np

from src.core.classifier import ShipColumnClassifier

ok = True


def check(name, cond, detail=''):
    global ok
    print('[%s] %s %s' % ('PASS' if cond else 'FAIL', name, detail))
    if not cond:
        ok = False


base = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

# === 0. 标签别名与标准化 ===
from src.core.classifier import normalize_label, LABEL_ALIASES
check('标签别名表非空', len(LABEL_ALIASES) > 10)
check('normalize_label("站号") = "station"',
      normalize_label('站号') == 'station', str(normalize_label('站号')))
check('normalize_label("高度") = "z"',
      normalize_label('高度') == 'z')
check('normalize_label("半宽") = "half"',
      normalize_label('半宽') == 'half')
check('normalize_label("Station") = "station"',
      normalize_label('Station') == 'station')
check('normalize_label("未知") = None',
      normalize_label('未知') is None)

# === 1. 分类器初始化 ===
clf = ShipColumnClassifier()
check('特征清单自动为 12 维', len(clf.required_variables) == 12)
check('特征名以 Monotonic_increasing 开头',
      clf.required_variables[0] == 'Monotonic_increasing')

# === 2. 训练 sklearn 模型 ===
# 构造标注数据：6 列原始序列 + 对应标签（模拟 station/z/half 数据特征）
np.random.seed(42)
n_rows = 50
station1 = np.linspace(0, 10, n_rows)
station2 = np.linspace(0, 5, n_rows)
z1 = (1 - (np.linspace(-1, 1, n_rows)) ** 2) * 3
z2 = (1 - (np.linspace(-1, 1, n_rows)) ** 2) * 4
half1 = (1 - (np.linspace(-1, 1, n_rows)) ** 2) * 5
half2 = (1 - (np.linspace(-1, 1, n_rows)) ** 2) * 4.5

columns_train = [station1, station2, z1, z2, half1, half2]
labels_train = ['station', 'station', 'z', 'z', 'half', 'half']
clf.train_from_columns(columns_train, labels_train, model_type='Tree')
check('train_from_columns 完成', clf.model is not None)
check('model_kind 已设置', clf.model_kind == 'TREE')

# === 3. 预测单个矩阵（每列一个样本） ===
# 3 列测试：1 station + 1 z + 1 half
station_test = np.linspace(2, 7, 30)
z_test = (1 - (np.linspace(-1, 1, 30)) ** 2) * 3.5
half_test = (1 - (np.linspace(-1, 1, 30)) ** 2) * 4.7

test_cols = [station_test, z_test, half_test]
# 构造矩阵（行=样本数最大，列=测试列数）
max_r = max(len(c) for c in test_cols)
test_matrix = np.full((max_r, 3), np.nan)
for j, c in enumerate(test_cols):
    test_matrix[:len(c), j] = c
result = clf.classify_columns(test_matrix)
check('classify_columns 返回 dict',
      'predicted_labels' in result and 'features' in result)
check('预测标签数 = 列数', len(result['predicted_labels']) == 3,
      '实际 %d' % len(result['predicted_labels']))
check('预测标签均在三角色内',
      set(result['predicted_labels']).issubset({'station', 'z', 'half'}),
      str(result['predicted_labels']))

# === 4. 一键分类 Excel ===
tmpdir = tempfile.mkdtemp()
xlsx = os.path.join(tmpdir, '型值表.xlsx')

# 写入测试 Excel（列序：half, station, z_long）
import openpyxl
wb = openpyxl.Workbook()
ws = wb.active
ws.append(['half_wl', 'station', 'z_long'])
for i in range(n_rows):
    ws.append([half1[i], station1[i], z1[i]])
wb.save(xlsx)

excel_result = clf.classify_excel(xlsx)
check('classify_excel 返回 headers',
      excel_result['headers'] == ['half_wl', 'station', 'z_long'])
check('classify_excel 预测 3 列', len(excel_result['predicted_labels']) == 3)
check('numeric_matrix 形状正确',
      excel_result['numeric_matrix'].shape == (n_rows, 3),
      'shape=%s' % str(excel_result['numeric_matrix'].shape))
check('column_roles 数量 = 列数', len(excel_result['column_roles']) == 3)
check('valid_indices 非空', len(excel_result['valid_indices']) > 0)

# === 5. 保存与加载 sklearn 模型 ===
pkl = os.path.join(tmpdir, 'clf.pkl')
clf.save_sklearn_model(pkl)
clf2 = ShipColumnClassifier()
clf2.load_sklearn_model(pkl)
check('save/load sklearn 模型成功', clf2.model is not None)
check('load 后 required_variables 已恢复',
      clf2.required_variables == clf.required_variables)
# 加载后的模型可预测
r = clf2.classify_columns(test_matrix)
check('load 后可预测', len(r['predicted_labels']) == 3)

# === 6. label_filter ===
r2 = clf.classify_columns(test_matrix, label_filter={'station', 'z'})
check('label_filter 过滤后保留列索引数 = 2 (station + z)',
      len(r2['valid_indices']) == 2, str(r2['valid_indices']))

print()
print('CLASSIFIER TEST %s' % ('PASS' if ok else 'FAIL'))