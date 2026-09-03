# -*- coding: utf-8 -*-
"""
classifier.py —— 船舶型值表列角色自动分类模块

功能：
- 读取船舶型值表 Excel/CSV 文件
- 自动提取 12 个统计特征（与 MATLAB extractPredictionFeatures 完全一致）
- 使用 scikit-learn 模型预测每列的角色（station / z / half）
- 支持模型的训练、保存与加载（pickle 格式）
- 标签自动标准化：支持中文别名（站号/高度/半宽）与大小写不敏感

本工程已不再支持 MATLAB Classification Learner 导出的 .mat 模型，
分类模型统一使用 scikit-learn 训练（KNN / SVM / 决策树）。
"""

import os
import math
import pickle
import tkinter as tk
from tkinter import filedialog

import numpy as np

from src.core import ml_utils


# 标签别名表：任意用户输入都映射到 3 个标准标签（station / z / half）
LABEL_ALIASES = {
    # station
    'station': 'station', 'st': 'station', 'stn': 'station',
    'x': 'station', 'no': 'station', 'num': 'station', 'number': 'station',
    '站号': 'station', '站': 'station', '站点': 'station',
    # z (纵坐标 / 高度)
    'z': 'z', 'z_long': 'z', 'el': 'z', 'elev': 'z', 'elevation': 'z',
    'h': 'z', 'h_deck': 'z', 'ht': 'z', 'height': 'z',
    '高度': 'z', '高': 'z', '高程': 'z', '纵向': 'z', 'z值': 'z',
    # half (半宽)
    'half': 'half', 'hw': 'half', 'b': 'half', 'breadth': 'half', 'width': 'half',
    'y': 'half', '半宽': 'half', '半': 'half', '宽': 'half',
}


def normalize_label(value):
    """将任意标签值映射到 'station' / 'z' / 'half'，无法识别返回 None。"""
    if value is None:
        return None
    s = str(value).strip().lower()
    if not s:
        return None
    return LABEL_ALIASES.get(s)


class ShipColumnClassifier:
    """
    船舶型值表列角色分类器

    使用流程：
        clf = ShipColumnClassifier()
        clf.train_from_columns(column_data_list,
                               ['station','z','half'],
                               model_type='Tree')
        results = clf.classify_excel('型值表.xlsx')
    """

    # 三个标准分类标签
    TARGET_LABELS = ('station', 'z', 'half')
    # 12 个统计特征名（与 MATLAB extractPredictionFeatures 一致）
    FEATURE_NAMES = ml_utils.DEFAULT_FEATURES
    # 特征表中"标签列"的常见列名（用于自动识别，含常见拼写 lable）
    LABEL_COLUMN_NAMES = {
        'lable', 'label', 'labels', '角色', '类别', 'class', 'cls',
        'category', 'target', 'y', 'type', '标签',
    }

    def __init__(self):
        self.required_variables = list(self.FEATURE_NAMES)
        # sklearn 预测器
        self.model = None              # sklearn classifier
        self.model_kind = None         # 'KNN' / 'SVM' / 'Tree'
        self._feature_columns = None    # 训练时使用的源列名（可为 None）

    # ================================================================
    # 训练 / 加载 sklearn 预测器
    # ================================================================

    def train_from_labeled(self, features, labels, model_type='KNN', feature_columns=None, **kwargs):
        """
        使用**已提取的**特征训练 sklearn 分类器。

        参数:
            features: ndarray (n_samples, n_features)   每行对应一个标注列的 12 维特征
            labels:    list/ndarray (n_samples,)           每个列的角色（station/z/half）
            model_type: 'KNN' / 'SVM' / 'Tree'
            feature_columns: list[str]                   训练时的源列名（可 None）

        返回训练好的 sklearn 模型。

        如需直接从原始列数据训练，请使用 train_from_columns()。
        """
        X = np.asarray(features, dtype=float)
        y = np.asarray(labels, dtype=object).ravel()
        self.model = ml_utils.train_model(X, y, model_type, **kwargs)
        self.model_kind = model_type.upper()
        self._feature_columns = feature_columns
        return self.model

    def train_from_columns(self, columns_data, labels, model_type='KNN', **kwargs):
        """
        便捷方法：从**原始列数据**直接训练（自动提取 12 维特征）。

        参数:
            columns_data: list[list/np.ndarray]  每项为一个列的数据序列
            labels:        list[str]             与 columns_data 等长的角色列表
            model_type:    'KNN' / 'SVM' / 'Tree'

        返回训练好的 sklearn 模型。
        """
        # 构造数值矩阵：每列作为一个 "行"（转置后行=列）
        # 构造数值矩阵：每列作为一个 "行"（转置后行=列）
        cols = [np.asarray(c, dtype=float).ravel() for c in columns_data]
        n_rows = max(len(c) for c in cols)
        matrix = np.full((n_rows, len(cols)), np.nan)
        for j, c in enumerate(cols):
            matrix[:len(c), j] = c
        # 矩阵的每一列是一个样本；为提取"列级"特征，需转置后逐列统计
        # extract_prediction_features 的设计是 matrix (n_rows, n_cols) -> feats (n_cols, 12)
        feats, warnings = self.extract_features(matrix)
        for w in warnings:
            print('  训练警告:', w)
        return self.train_from_labeled(feats, labels, model_type, **kwargs)

    def save_sklearn_model(self, path):
        """保存 sklearn 模型 + 特征清单到 pickle 文件"""
        if self.model is None:
            raise RuntimeError('模型尚未训练或加载，无法保存')
        ml_utils.save_model(self.model, self.required_variables or self.FEATURE_NAMES, path)

    def load_sklearn_model(self, path):
        """从 pickle 文件加载 sklearn 模型"""
        self.model, req = ml_utils.load_model(path)
        self.required_variables = list(req)
        return self.model

    # ================================================================
    # 预测 / 分类
    # ================================================================

    def is_ready(self):
        """是否已准备好预测（已加载元数据且已训练 sklearn 模型）"""
        return self.model is not None

    def extract_features(self, matrix):
        """
        为数值矩阵的每一列提取 12 个统计特征。
        返回 (features, warnings)。
        """
        feature_names = self.required_variables or self.FEATURE_NAMES
        return ml_utils.extract_prediction_features(matrix, feature_names)

    def classify_columns(self, matrix, label_filter=None):
        """
        对数值矩阵的每一列进行分类。

        参数:
            matrix: 数值矩阵 (n_rows, n_cols)
            label_filter: 可选，只保留在 label_filter 中的标签
                          （如 {'station','z','half'}）

        返回 dict:
            - predicted_labels: list[str]    每列的预测标签
            - features: ndarray (n_cols, 12)   提取的特征
            - warnings: list[str]             警告信息
            - valid_indices: list[int]        保留标签有效的列索引
        """
        if not self.is_ready():
            raise RuntimeError('请先加载模型并训练 sklearn 预测器（train_from_labeled / load_sklearn_model）')

        feats, warnings = self.extract_features(matrix)
        raw_labels = self.model.predict(feats)
        labels = np.asarray(raw_labels, dtype=str).ravel()
        valid_indices = list(range(len(labels)))

        if label_filter is not None:
            mask = np.array([str(l).lower() in {x.lower() for x in label_filter}
                             for l in labels], dtype=bool)
            valid_indices = [i for i, m in enumerate(mask) if m]

        return dict(
            predicted_labels=labels.tolist(),
            features=feats,
            warnings=warnings,
            valid_indices=valid_indices,
        )

    # ================================================================
    # 从"已提取特征的训练集"（如 feature.xlsx）训练
    # ================================================================

    def train_from_feature_sheet(self, path, model_type='KNN', label_column=None,
                                 use_scaler=True):
        """
        从**已提取好 12 维特征的训练集**（Excel/CSV）直接训练模型。

        这是推荐的训练方式：训练集每行是一个已标注的列样本，
        包含 12 个特征列 + 1 个标签列。

        文件格式（以 feature.xlsx 为例）：
            Monotonic_increasing | uniqueRatio | maxValue | minValue | meanValue |
            Standard_Deviation | Skewness | Kurtosis | Q25 | Q50 | Q75 | Mode | lable
            1 | 1 | 20.5 | 0 | 10.16 | ... | station
            ...

        参数:
            path:         Excel/CSV 文件路径
            model_type:   'KNN' / 'SVM' / 'Tree'
            label_column: 标签列名（None 时自动识别 lable/label/角色/class/...）
            use_scaler:   是否对特征做标准化（KNN/SVM 建议 True）

        返回 dict:
            - model: 训练好的 sklearn 模型（含标准化流水线）
            - n_samples: 样本数
            - n_features: 特征数（应为 12）
            - label_counts: dict  各类别样本数
            - cv_accuracy: 5 折交叉验证准确率（样本充足时）
            - filled_na: 填充的缺失值数量
        """
        headers, rows = self.load_table_file(path)
        if not headers or not rows:
            raise ValueError('无法从 %s 读取有效表头或数据' % path)

        # ---- 1. 定位标签列 ----
        label_idx = None
        if label_column is not None:
            for j, h in enumerate(headers):
                if str(h).strip().lower() == str(label_column).strip().lower():
                    label_idx = j
                    break
            if label_idx is None:
                raise ValueError('找不到标签列 "%s"' % label_column)
        else:
            # 自动识别：优先取名为 lable/label/角色/... 的列，否则取最后一列
            for j, h in enumerate(headers):
                if str(h).strip().lower() in self.LABEL_COLUMN_NAMES:
                    label_idx = j
                    break
            if label_idx is None:
                label_idx = len(headers) - 1

        # ---- 2. 定位 12 个特征列（按 DEFAULT_FEATURES 名称匹配）----
        feat_idx = []
        for name in self.FEATURE_NAMES:
            found = None
            for j, h in enumerate(headers):
                if j == label_idx:
                    continue
                if str(h).strip().lower() == name.strip().lower():
                    found = j
                    break
            feat_idx.append(found)
        # 若未能按名称全部匹配，则退化为"除标签列外的前 12 列"
        if any(f is None for f in feat_idx):
            others = [j for j in range(len(headers)) if j != label_idx]
            if len(others) < len(self.FEATURE_NAMES):
                raise ValueError('列数不足：需要 12 个特征列 + 1 个标签列')
            feat_idx = others[:len(self.FEATURE_NAMES)]

        # ---- 3. 构造特征矩阵，缺失值按预测端口径填充 ----
        n = len(rows)
        X = np.full((n, len(feat_idx)), np.nan)
        for i, row in enumerate(rows):
            for k, j in enumerate(feat_idx):
                v = row[j] if j < len(row) else None
                if v is None or v == '':
                    continue
                try:
                    X[i, k] = float(v)
                except (ValueError, TypeError):
                    pass

        filled_na = self._fill_feature_nan(X)

        # ---- 4. 标签标准化 ----
        y_raw = [row[label_idx] if label_idx < len(row) else None for row in rows]
        y = np.array([normalize_label(v) for v in y_raw], dtype=object)

        # ---- 5. 丢弃无效行 ----
        valid = np.array([lab is not None for lab in y], dtype=bool)
        valid &= ~np.any(np.isnan(X), axis=1)
        X, y = X[valid], y[valid]
        if X.shape[0] < 2:
            raise ValueError('有效样本不足（需 ≥ 2 行），当前 %d 行' % X.shape[0])
        if len(set(y.tolist())) < 2:
            raise ValueError('至少需要 2 个不同类别才能训练，当前只有 %s'
                             % set(y.tolist()))

        # ---- 6. 训练（KNN/SVM 使用标准化流水线）----
        model = self._build_estimator(model_type, use_scaler=use_scaler)
        model.fit(X, y)
        self.model = model
        self.model_kind = model_type.upper()
        self._feature_columns = [headers[j] for j in feat_idx]

        # ---- 7. 交叉验证（类别样本 ≥ 2 时才能分层抽样）----
        cv_accuracy = None
        counts = {str(c): int(np.sum(y == c)) for c in set(y.tolist())}
        try:
            from sklearn.model_selection import cross_val_score, StratifiedKFold
            min_count = min(counts.values())
            n_splits = min(5, min_count)
            if n_splits >= 2 and X.shape[0] >= n_splits * 2:
                cv = StratifiedKFold(n_splits=n_splits, shuffle=True, random_state=42)
                scores = cross_val_score(
                    self._build_estimator(model_type, use_scaler=use_scaler),
                    X, y, cv=cv, scoring='accuracy')
                cv_accuracy = float(np.mean(scores))
        except Exception:
            cv_accuracy = None

        return dict(
            model=model,
            n_samples=int(X.shape[0]),
            n_features=int(X.shape[1]),
            label_counts=counts,
            cv_accuracy=cv_accuracy,
            filled_na=int(filled_na),
            feature_columns=self._feature_columns,
            label_column=str(headers[label_idx]),
        )

    @staticmethod
    def _fill_feature_nan(X):
        """
        填充特征矩阵中的 NaN，使其与 extract_prediction_features 的输出口径一致：
        - Skewness（方差为 0 时未定义）→ 0.0
        - Kurtosis（方差为 0 时未定义）→ 3.0
        - 其余特征 → 该列中位数（仍为空则 0）
        """
        names = list(ShipColumnClassifier.FEATURE_NAMES)
        try:
            i_skew = names.index('Skewness')
            i_kurt = names.index('Kurtosis')
        except ValueError:
            i_skew = i_kurt = -1
        n_filled = 0
        for k in range(X.shape[1]):
            col = X[:, k]
            mask = np.isnan(col)
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
            X[:, k] = col
            n_filled += int(np.sum(mask))
        return n_filled

    @staticmethod
    def _build_estimator(model_type, use_scaler=True):
        """构建 sklearn 估计器（可选 StandardScaler 流水线）"""
        mt = (model_type or 'KNN').upper()
        if mt in ('KNN', 'KNEIGHBORS'):
            from sklearn.neighbors import KNeighborsClassifier
            est = KNeighborsClassifier(n_neighbors=5)
        elif mt in ('SVM', 'SVC'):
            from sklearn.svm import SVC
            est = SVC(kernel='rbf', C=1.0, gamma='scale', class_weight='balanced')
        elif mt in ('TREE', 'DECISIONTREE'):
            from sklearn.tree import DecisionTreeClassifier
            est = DecisionTreeClassifier(random_state=42, class_weight='balanced')
        else:
            raise ValueError('不支持的模型类型: %s（可用 KNN/SVM/Tree）' % model_type)
        if use_scaler and mt in ('KNN', 'KNEIGHBORS', 'SVM', 'SVC'):
            from sklearn.preprocessing import StandardScaler
            from sklearn.pipeline import make_pipeline
            return make_pipeline(StandardScaler(), est)
        return est

    # ================================================================
    # Excel 读取 + 一键分类
    # ================================================================

    def load_table_file(self, file_path):
        """
        读取 Excel/CSV/TXT 型值表文件，返回 (headers, rows)。

        headers: list[str]   表头列名
        rows:    list[list]   每行为 list（元素为字符串或数值）
        """
        ext = os.path.splitext(file_path)[1].lower()
        if ext in ('.xlsx', '.xls'):
            return self._read_excel(file_path)
        elif ext == '.csv':
            return self._read_csv(file_path)
        else:
            return self._read_text(file_path)

    @staticmethod
    def _read_excel(path):
        import openpyxl
        wb = openpyxl.load_workbook(path, data_only=True)
        ws = wb.active
        rows = []
        for row in ws.iter_rows(values_only=True):
            rows.append([('' if v is None else v) for v in row])
        if not rows:
            return [], []
        headers = [str(x) if x != '' else f'col_{i + 1}'
                   for i, x in enumerate(rows[0])]
        return headers, rows[1:]

    @staticmethod
    def _read_csv(path):
        import csv
        with open(path, 'r', encoding='utf-8-sig', newline='') as f:
            reader = csv.reader(f)
            raw = list(reader)
        if not raw:
            return [], []
        headers = [h if h else f'col_{i + 1}' for i, h in enumerate(raw[0])]
        return headers, raw[1:]

    @staticmethod
    def _read_text(path):
        with open(path, 'r', encoding='utf-8-sig') as f:
            lines = [l.rstrip('\n') for l in f.readlines()]
        rows = []
        for line in lines:
            if '\t' in line:
                rows.append(line.split('\t'))
            elif ',' in line:
                rows.append(line.split(','))
            elif line.strip():
                rows.append(line.split())
        if not rows:
            return [], []
        headers = [h if h else f'col_{i + 1}' for i, h in enumerate(rows[0])]
        return headers, rows[1:]

    def _to_numeric_matrix(self, rows, n_cols):
        """将 rows（list[list]）转为 (n_rows, n_cols) 数值矩阵"""
        matrix = np.full((len(rows), n_cols), np.nan)
        for i, row in enumerate(rows):
            for j in range(n_cols):
                v = row[j] if j < len(row) else None
                if v is None or v == '':
                    continue
                try:
                    matrix[i, j] = float(v)
                except (ValueError, TypeError):
                    pass
        return matrix

    def classify_excel(self, excel_path, label_filter=None):
        """
        一键分类：读取 Excel 型值表 → 提取特征 → sklearn 预测 → 整理结果。

        返回 dict:
            - path: str
            - headers: list[str]
            - raw_data: list[list]          原始单元格内容
            - numeric_matrix: ndarray       数值化矩阵
            - predicted_labels: list[str]    每列预测标签
            - features: ndarray (n_cols, 12)
            - warnings: list[str]
            - valid_indices: list[int]
            - column_roles: dict             {col_index: {'header', 'label', 'is_valid'}}
        """
        headers, rows = self.load_table_file(excel_path)
        if not headers or not rows:
            raise ValueError(f'无法从 {excel_path} 读取有效表头或数据')
        n_cols = len(headers)
        matrix = self._to_numeric_matrix(rows, n_cols)
        result = self.classify_columns(matrix, label_filter=label_filter)
        column_roles = {}
        for i, h in enumerate(headers):
            column_roles[i] = dict(
                header=h,
                label=result['predicted_labels'][i],
                is_valid=(i in result['valid_indices']),
            )
        return dict(
            path=excel_path,
            headers=headers,
            raw_data=rows,
            numeric_matrix=matrix,
            predicted_labels=result['predicted_labels'],
            features=result['features'],
            warnings=result['warnings'],
            valid_indices=result['valid_indices'],
            column_roles=column_roles,
        )

    # ================================================================
    # 交互式对话框（GUI 辅助）
    # ================================================================

    @staticmethod
    def ask_excel_path(parent=None):
        """弹出文件对话框选择型值表文件"""
        path = filedialog.askopenfilename(
            title='选择船舶型值表文件',
            filetypes=[('表格文件', '*.xlsx;*.xls;*.csv;*.txt'),
                       ('Excel', '*.xlsx;*.xls'), ('CSV', '*.csv'),
                       ('所有文件', '*.*')],
            parent=parent)
        return path

    @staticmethod
    def ask_pickle_path(parent=None):
        """弹出文件对话框选择 sklearn 模型 .pkl"""
        path = filedialog.askopenfilename(
            title='选择 sklearn 模型文件',
            filetypes=[('Pickle 模型', '*.pkl *.pickle'), ('所有文件', '*.*')],
            parent=parent)
        return path


# ================================================================
# 命令行快速使用
# ================================================================

def _quick_demo():
    """无 GUI 演示用法：构造训练数据 → 训练 → 预测"""
    np.random.seed(42)
    n = 30
    station = np.linspace(0, 10, n)
    z = (1 - np.linspace(-1, 1, n) ** 2) * 3
    half = (1 - np.linspace(-1, 1, n) ** 2) * 8
    clf = ShipColumnClassifier()
    clf.train_from_columns([station, z, half],
                           ['station', 'z', 'half'],
                           model_type='Tree')
    print('训练完成。模型类型:', clf.model_kind, '/ 特征维度: 12')
    m = np.full((20, 3), np.nan)
    m[:, 0] = np.linspace(1, 5, 20)
    m[:, 1] = (1 - np.linspace(-1, 1, 20) ** 2) * 3
    m[:, 2] = (1 - np.linspace(-1, 1, 20) ** 2) * 7
    print('预测结果:', clf.classify_columns(m)['predicted_labels'])


if __name__ == '__main__':
    _quick_demo()