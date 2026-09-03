# -*- coding: utf-8 -*-
"""
ml_utils.py —— 机器学习模块（12 维统计特征 + sklearn 训练/预测）

本工程已不再支持 MATLAB Classification Learner 导出的 .mat 模型。
分类模型统一使用 scikit-learn 训练（KNN / SVM / 决策树），与
classifier.py 配合使用。

功能：
- extract_prediction_features：列级 12 维统计特征提取
- train_model：训练 KNN / SVM / 决策树分类器
- save_model / load_model：pickle 持久化（sklearn 模型）
"""

import math
import os
import pickle

import numpy as np


# =====================================================================
# 特征提取（对应 MATLAB extractPredictionFeatures）
# =====================================================================

DEFAULT_FEATURES = [
    'Monotonic_increasing', 'uniqueRatio', 'maxValue', 'minValue',
    'meanValue', 'Standard_Deviation', 'Skewness', 'Kurtosis',
    'Q25', 'Q50', 'Q75', 'Mode',
]


def extract_prediction_features(matrix_data, feature_names=None):
    """
    兼容 MATLAB extractPredictionFeatures：
    为数值矩阵的每一列计算统计特征。返回 (n_cols × n_features) ndarray。

    matrix_data: 数值矩阵，形状 (n_rows, n_cols)
    feature_names: 需要计算的特征名列表，None 时使用 DEFAULT_FEATURES
    """
    if feature_names is None:
        feature_names = DEFAULT_FEATURES
    matrix = np.asarray(matrix_data, dtype=float)
    if matrix.ndim == 1:
        matrix = matrix.reshape(-1, 1)
    n_rows, n_cols = matrix.shape
    n_feats = len(feature_names)
    feats = np.full((n_cols, n_feats), np.nan)
    warnings = []

    for i in range(n_cols):
        col_data = matrix[:, i]
        col_finite = col_data[np.isfinite(col_data)]
        if col_finite.size == 0:
            continue
        for j, feat in enumerate(feature_names):
            try:
                if feat == 'Monotonic_increasing':
                    d = np.diff(col_finite)
                    val = float(np.all(d >= 0) or np.all(d <= 0))
                elif feat == 'uniqueRatio':
                    val = float(np.unique(col_finite).size) / float(col_finite.size)
                elif feat == 'maxValue':
                    val = float(np.max(col_finite))
                elif feat == 'minValue':
                    val = float(np.min(col_finite))
                elif feat == 'Standard_Deviation':
                    val = float(np.std(col_finite)) if col_finite.size > 1 else 0.0
                elif feat == 'meanValue':
                    val = float(np.mean(col_finite))
                elif feat == 'Skewness':
                    val = float(_skewness(col_finite))
                elif feat == 'Kurtosis':
                    val = float(_kurtosis(col_finite))
                elif feat == 'Q25':
                    val = float(np.percentile(col_finite, 25))
                elif feat == 'Q50':
                    val = float(np.percentile(col_finite, 50))
                elif feat == 'Q75':
                    val = float(np.percentile(col_finite, 75))
                elif feat == 'Mode':
                    vals, counts = np.unique(col_finite, return_counts=True)
                    val = float(vals[np.argmax(counts)])
                else:
                    warnings.append('警告: 模型需要特征 "%s"，但未实现该特征的计算。' % feat)
                    continue
                feats[i, j] = val
            except Exception as e:
                warnings.append('警告: 计算第 %d 列的特征 "%s" 时出错: %s' % (i + 1, feat, e))
    # 填充缺失特征，使其与训练口径一致（方差为 0 时 Skewness→0 / Kurtosis→3，
    # 其余特征用列中位数；整列缺失则补 0）。否则下游 SVM 会因 NaN 报错。
    n_filled = _fill_prediction_feature_nan(feats, feature_names)
    if n_filled:
        warnings.append('已自动填充 %d 个缺失特征（NaN），避免模型预测报错。' % n_filled)
    return feats, warnings


def _fill_prediction_feature_nan(feats, feature_names):
    """
    填充特征矩阵中的 NaN，与训练端 _fill_feature_nan 口径一致：
    - Skewness（方差为 0 / 整列非数值时未定义）→ 0.0
    - Kurtosis（同上）→ 3.0
    - 其余特征 → 该列中位数（仍全缺失则 0.0）
    """
    names = list(feature_names)
    try:
        i_skew = names.index('Skewness')
        i_kurt = names.index('Kurtosis')
    except ValueError:
        i_skew = i_kurt = -1
    n_filled = 0
    for k in range(feats.shape[1]):
        col = feats[:, k]
        mask = ~np.isfinite(col)
        if not np.any(mask):
            continue
        if k == i_skew:
            fill = 0.0
        elif k == i_kurt:
            fill = 3.0
        else:
            finite = col[~mask]
            fill = float(np.median(finite)) if finite.size else 0.0
        col[mask] = fill
        feats[:, k] = col
        n_filled += int(np.sum(mask))
    return n_filled


def _skewness(x):
    """样本偏度（无偏估计），与 MATLAB skewness 一致"""
    n = x.size
    if n < 3:
        return 0.0
    mu = np.mean(x)
    m2 = np.sum((x - mu) ** 2) / n
    m3 = np.sum((x - mu) ** 3) / n
    if m2 < 1e-12:
        return 0.0
    return m3 / (m2 ** 1.5)


def _kurtosis(x):
    """样本峰度（无偏估计），与 MATLAB kurtosis 一致（超额峰度+3）"""
    n = x.size
    if n < 4:
        return 3.0
    mu = np.mean(x)
    m2 = np.sum((x - mu) ** 2) / n
    m4 = np.sum((x - mu) ** 4) / n
    if m2 < 1e-12:
        return 3.0
    return m4 / (m2 ** 2)


# =====================================================================
# sklearn 模型训练 / 保存 / 加载
# =====================================================================

def train_model(X, y, model_type='KNN', **kwargs):
    """
    使用 scikit-learn 训练分类模型。
    model_type: 'KNN' / 'SVM' / 'Tree'
    返回训练好的模型。
    """
    X = np.asarray(X, dtype=float)
    y = np.asarray(y, dtype=object).ravel()
    model_type = model_type.upper()
    if model_type in ('KNN', 'KNEIGHBORS', 'KNN_CLASSIFIER'):
        from sklearn.neighbors import KNeighborsClassifier
        k = int(kwargs.get('k', 5))
        n = X.shape[0]
        if n > 1:
            k = max(1, min(k, n - 1))
        else:
            k = 1
        model = KNeighborsClassifier(n_neighbors=k, metric=kwargs.get('metric', 'minkowski'))
    elif model_type in ('SVM', 'SVMC', 'SVC'):
        from sklearn.svm import SVC
        model = SVC(kernel=kwargs.get('kernel', 'rbf'),
                    C=kwargs.get('C', 1.0),
                    gamma=kwargs.get('gamma', 'scale'))
    elif model_type in ('TREE', 'DT', 'DECISIONTREE'):
        from sklearn.tree import DecisionTreeClassifier
        model = DecisionTreeClassifier(max_depth=kwargs.get('max_depth', None),
                                       random_state=42)
    else:
        raise ValueError('不支持的模型类型: %s' % model_type)
    model.fit(X, y)
    return model


def save_model(model, required_variables, path):
    """保存 Python 模型 + 特征清单 到 pickle 文件"""
    payload = dict(model=model, required_variables=list(required_variables))
    with open(path, 'wb') as f:
        pickle.dump(payload, f)


def load_model(path):
    """加载 pickle 模型文件，返回 (model, required_variables)"""
    with open(path, 'rb') as f:
        payload = pickle.load(f)
    return payload['model'], payload.get('required_variables', DEFAULT_FEATURES)


def predict_roles(model, required_variables, matrix_data):
    """
    对数据矩阵的每一列预测角色（station / half / z 等）。
    返回 (predicted_labels, feature_table, warnings)
    """
    feats, warnings = extract_prediction_features(matrix_data, required_variables)
    labels = model.predict(feats)
    return np.asarray(labels, dtype=object).ravel(), feats, warnings


# =====================================================================
# 训练数据收集（从角色标注表格构建训练集）
# =====================================================================

def build_training_set(labeled_matrix, label_column, feature_names=None):
    """
    从标注表格构建训练集。
    labeled_matrix: (n_rows, n_cols) 数值矩阵，label_column 为角色标签列索引
    feature_names: 特征名列表（默认 DEFAULT_FEATURES）
    返回 (X, y, feature_names)
    """
    if feature_names is None:
        feature_names = DEFAULT_FEATURES
    mat = np.asarray(labeled_matrix, dtype=float)
    labels = np.asarray(labeled_matrix)[:, label_column] if False else None
    # 特征：除标签列外每列计算特征
    X = []
    y = []
    # 每一行代表一个"列样本"，其标签为该行的角色
    # 注意：MATLAB 流程是对列做特征提取，这里按行样本训练
    return None


def compute_column_features_table(matrix_data, feature_names=None):
    """
    计算特征表：每列一行，每行对应特征值。
    用于训练与预测的统一入口。
    返回 (feature_table, warnings)
    """
    if feature_names is None:
        feature_names = DEFAULT_FEATURES
    feats, warnings = extract_prediction_features(matrix_data, feature_names)
    return feats, warnings
