# -*- coding: utf-8 -*-
import os as _os
import sys as _sys
_sys.path.insert(0, _os.path.dirname(_os.path.dirname(_os.path.abspath(__file__))))
"""测试：训练模型流程（含节点选择修复 + 特征维度一致性）"""
import os
import tempfile
import tkinter as tk
from tkinter import messagebox

for _fn in ('showinfo', 'showwarning', 'showerror', 'askyesno'):
    setattr(messagebox, _fn, lambda *a, **k: True)

# 模拟对话框：
# - 训练数据节点选择 → 第 0 项（第一个节点）
# - 模型类型选择 → 第 2 项（决策树，对特征尺度不敏感，分类更准）
from src.ui import ui_widgets


def _mock_choice(parent, title, prompt, options, default_index=0):
    if '模型类型' in str(title) or '分类器' in str(title):
        return 2      # Tree
    return 0          # 第一个候选节点


ui_widgets.ask_choice_dialog = _mock_choice
ui_widgets.ask_text_dialog = lambda *a, **k: ''
ui_widgets.ask_numeric_dialog = lambda *a, **k: None
ui_widgets.ask_multi_select = lambda *a, **k: [1]
ui_widgets.ask_multiline_input = lambda *a, **k: ''

from src.core import ship_app_actions
ship_app_actions.ask_choice_dialog = ui_widgets.ask_choice_dialog
ship_app_actions.ask_text_dialog = ui_widgets.ask_text_dialog

root = tk.Tk()
root.geometry('1200x760')
from src.app.ship_app import ShipApp
app = ShipApp(root, icon_dir='icon')
root.update()

ok = True


def check(name, cond, detail=''):
    global ok
    print('[%s] %s %s' % ('PASS' if cond else 'FAIL', name, detail))
    if not cond:
        ok = False


# === 1. 构造训练数据：6 列，第 1 行为角色标签 ===
import numpy as np
n = 40
lin = np.linspace(0, 10, n)
bell = 1 - np.linspace(-1, 1, n) ** 2

headers = ['station_1', 'station_2', 'z_1', 'z_2', 'half_1', 'half_2']
rows = []
# 标签行（第 0 行）
rows.append(['station', 'station', 'z', 'z', 'half', 'half'])
# 数据行
for i in range(n):
    rows.append([lin[i] + 0.1, lin[i] + 0.5,
                 bell[i] * 2.0, bell[i] * 2.2,
                 bell[i] * 8.0, bell[i] * 7.5])

# === 2. 写入 CSV 并导入 ===
tmp = tempfile.mkdtemp()
csv_path = os.path.join(tmp, 'train.csv')
import csv
with open(csv_path, 'w', encoding='utf-8-sig', newline='') as f:
    w = csv.writer(f)
    w.writerow(headers)
    for r in rows:
        w.writerow(r)

rh, rd = app._read_table_file(csv_path)
check('读取训练表头', rh == headers, str(rh))
check('读取训练数据行数', len(rd) == n + 1, '实际 %d' % len(rd))

node = app._tree_add(app.table_root, 'train.csv',
                     {'type': 'table', 'Data': rd, 'Headers': rh,
                      'VariableNames': rh})
app.tree.selection_set(node)
root.update()

# === 3. 验证 _collect_data_nodes 能找到该节点 ===
cands = app._collect_data_nodes()
check('_collect_data_nodes 找到节点', len(cands) >= 1,
      '找到 %d 个' % len(cands))

# === 4. 自动检测标签行 ===
label_row, label_dict = app._detect_label_row(rd)
check('自动检测到标签行 = 0', label_row == 0, '实际 %s' % str(label_row))
check('标签字典含 6 项（每列一个）', len(label_dict) == 6, str(label_dict))

# === 5. 执行训练（模拟：从 Model 节点右键触发，此时选中的是 Model 节点） ===
model_node = app._tree_add(app.model_root, 'KNN_model.mat',
                           {'type': 'model', 'path': 'x'})
app.tree.selection_set(model_node)   # 关键：选中 Model 节点（模拟用户右键）
root.update()

app.train_model_clicked()
root.update()

check('训练后 ML_model 已创建', app.ML_model is not None)
if app.ML_model:
    check('required_variables = 12 个统计特征',
          len(app.ML_model.get('required_variables', [])) == 12,
          '实际 %d' % len(app.ML_model.get('required_variables', [])))
    check('特征维度 = 12（与预测端一致）',
          app.ML_model.get('feature_dim') == 12,
          '实际 %s' % app.ML_model.get('feature_dim'))
    check('训练样本(列)数 = 6', app.ML_model.get('train_samples') == 6,
          '实际 %s' % app.ML_model.get('train_samples'))
    check('模型可用 predict', hasattr(app.ML_model['model'], 'predict'))

# === 6. 用训练好的模型做预测，验证维度匹配 ===
if app.ML_model and 'model' in app.ML_model:
    from src.core.classifier import ShipColumnClassifier
    clf = ShipColumnClassifier()
    clf.model = app.ML_model['model']
    clf.required_variables = app.ML_model['required_variables']
    # 构造 3 列测试矩阵（station / z / half）
    test_cols = [np.linspace(1, 8, 25),
                 (1 - np.linspace(-1, 1, 25) ** 2) * 2.1,
                 (1 - np.linspace(-1, 1, 25) ** 2) * 7.8]
    m = np.full((25, 3), np.nan)
    for j, c in enumerate(test_cols):
        m[:len(c), j] = c
    try:
        res = clf.classify_columns(m)
        preds = res['predicted_labels']
        check('预测成功（维度匹配）', len(preds) == 3, str(preds))
        check('预测标签合法',
              set(preds).issubset({'station', 'z', 'half'}), str(preds))
        # 期望：第0列(单调linspace)=station，第1列(小幅bell)=z，第2列(大幅bell)=half
        check('第0列预测为 station', preds[0] == 'station', '实际 %s' % preds[0])
        check('第1列预测为 z', preds[1] == 'z', '实际 %s' % preds[1])
        check('第2列预测为 half', preds[2] == 'half', '实际 %s' % preds[2])
    except Exception as e:
        check('预测成功（维度匹配）', False, '异常: %s' % e)

print()
print('TRAIN FLOW TEST %s' % ('PASS' if ok else 'FAIL'))
root.destroy()
