# -*- coding: utf-8 -*-
import os as _os
import sys as _sys
_sys.path.insert(0, _os.path.dirname(_os.path.dirname(_os.path.abspath(__file__))))
"""ML 模块测试：12 维特征提取 + sklearn 训练/预测/保存加载"""
import os
import numpy as np
from src.core import ml_utils

print('=' * 60)
print('特征提取（6行 × 6列）')
print('=' * 60)
X = np.array([[1, 2, 3, 4, 5, 6],
              [4, 3, 2, 1, 8, 9],
              [1, 1, 1, 1, 1, 1],
              [10, 20, 30, 40, 50, 60],
              [5, 5, 5, 5, 5, 5],
              [2, 4, 6, 8, 10, 12]], dtype=float)
feats, warns = ml_utils.extract_prediction_features(X)
print('特征矩阵形状:', feats.shape, '(应为 6列 × 12特征)')

# 特征提取（6行 × 6列）
X = np.array([[1, 2, 3, 4, 5, 6],
              [4, 3, 2, 1, 8, 9],
              [1, 1, 1, 1, 1, 1],
              [10, 20, 30, 40, 50, 60],
              [5, 5, 5, 5, 5, 5],
              [2, 4, 6, 8, 10, 12]], dtype=float)
feats, warns = ml_utils.extract_prediction_features(X)
print('特征矩阵形状:', feats.shape, '(应为 6列 × 12特征)')

# 训练模型（每列一个样本，特征表 6 行 → 6 个标签）
y = np.array(['station', 'half', 'z', 'station', 'half', 'z'])
model = ml_utils.train_model(feats, y, 'KNN')
pred = model.predict(feats)
print('KNN 自预测:', pred.tolist())

model2 = ml_utils.train_model(feats, y, 'SVM')
print('SVM 自预测:', model2.predict(feats).tolist())

model3 = ml_utils.train_model(feats, y, 'Tree')
print('Tree 自预测:', model3.predict(feats).tolist())

# 保存/加载
tmp = 'test_model.pkl'
ml_utils.save_model(model, ml_utils.DEFAULT_FEATURES, tmp)
m, rv = ml_utils.load_model(tmp)
os.remove(tmp)
print('模型保存/加载 OK, required_variables=%d' % len(rv))
print('ALL ML TESTS DONE')
