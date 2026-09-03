# SCS 船舶静水力计算软件（Python 移植版）

本工程是对 MATLAB 版 **SCS (Ship Static Calculate)** 船舶静水力计算软件的 **功能对等** 移植。
原始 MATLAB 源码为 `../ship.m`（14236 行，MATLAB App Designer 应用），本 Python 版本完整复刻了
其页面结构、使用逻辑、船舶计算公式、数据处理流程与特征工程方法，并保持计算口径一致。

## 快速开始

```bash
# 安装依赖（Python 3.8+）
pip install -r requirements.txt

# 启动软件（根目录 main.py 为薄启动器，逻辑在 src/app/main.py）
python main.py
```

### 目录结构

```
Pyship/
├── main.py              # 根启动器（python main.py）
├── requirements.txt
├── README.md
├── icon/                # 应用 / .scs 文件图标
├── logs/                # 运行日志（scs_debug.log / scs_crash.log）
├── src/                 # 按功能分层（v3 起）
│   ├── app/             #   应用组合（ship_app.py）与入口（main.py）
│   ├── core/            #   业务计算 / 操作 / 机器学习 / 日志
│   ├── ui/              #   tkinter 界面与控件
│   ├── viewer/          #   Qt SolidWorks 风格 3D 视窗（qt_3d_viewer / glc）
│   └── data/            #   示例数据（示例 .scs 项目、默认 ML 模型等）
└── tests/               # 全部回归测试（test_*.py，含 sys.path 引导）
```

## 功能模块

| 页面/Tab | 对应 MATLAB 组件 | 功能说明 |
|----------|-----------------|----------|
| 原表格 | `Tab_2` / `original_table` | 显示导入的原始型值表数据与调试日志 |
| 半宽 | `Tab` / `Half_table` | 水线面半宽数据编辑、水线面曲线绘制、水线面面积/漂心计算、曲线拟合 |
| 横剖面 | `Tab_3` / `Z_table` | 横剖面（站剖面）数据编辑、面积与形心计算、剖面图绘制 |
| 3D曲面 | `Tab_4` / `UIAxes_Face_area` | 生成点云 → 绘制型线 → 插值生成船体蒙皮；Qt SolidWorks 风格 3D 视窗（无 Qt 时回退 matplotlib），支持 STL 导出 |
| 浮心 | `Tab_5` / `Buoyancy*` | 正浮态（基于水线面）/ 任意浮态（基于横剖面，含横倾纵倾）浮心计算 |
| 静力曲线 | `Tab_6` / `CurvesTabGroup` | 水线面面积/排水量/TPC/MCT/浮心位置/稳心高度KM/船型系数等静水力曲线 |
| 邦戎曲线 | `Tab_7` / `Bonjean*` | 各站横剖面面积/面积矩/形心随吃水变化的邦戎曲线 |
| 稳性 | `Tab_Stability` | KN 稳性横截曲线、GZ 静稳性曲线、动稳性曲线、稳性衡准数 K 校核 |

### 菜单
- **文件**：导入项目(.scs)、保存项目(.scs)、导入型值表(Excel/CSV/TXT)、导出表格数据
- **设置**：积分方法（梯形 / 辛普森1/3 / 辛普森3/8）、原点位置（船中/船尾/船首）、主尺度设置
- **查看**：主尺度信息、静水力数据、邦戎曲线数据、稳性数据、数据汇总报告、重置缩放、刷新图表
- **三维显示**：线框模式（实体曲面/高光边缘/纯线框）、三维型线视图、导出船体 STL

### 工具栏
导入表格 · 加载模型 · 特征提取 · 设置主尺度 · 快速站号 · 导入半宽 · 生成系数 ·
相对矩臂 · 对称显示 · 曲线拟合 · 锁定编辑 · 删除 · 分段统计 · 水线面计算 · 增删行

## 机器学习模块

软件支持机器学习分类模型，用于自动识别型值表各列的**角色**（`station` 站号 / `z` 纵坐标 / `half` 半宽）：

1. **加载模型**：支持加载 MATLAB Classification Learner 导出的 `.mat` 模型（提取
   `RequiredVariables` 特征清单等元数据）以及 Python 训练好的 `.pkl` 模型。
2. **特征提取**：为每列数据计算 12 个统计特征（与 MATLAB `extractPredictionFeatures`
   完全一致）：单调性、唯一值比例、最大/最小值、均值、标准差、偏度、峰度、Q25/Q50/Q75、众数。
3. **训练模型**：由于 MATLAB 内部训练对象（`ClassificationKNN` 等）无法在 Python 中直接解码，
   可在"模型"节点右键选择 **训练模型**，使用 scikit-learn 重新训练功能对等的
   KNN / SVM / 决策树分类器，保存为 `.pkl` 复用。
4. **特征提取流程**：选择表格节点 → 点击工具栏"特征提取" → 模型预测各列角色 →
   人工修正 → **逐条输入水线(WL)固定高度** → 生成"识别结果"节点 → 从识别结果导入水线面/甲板线/Body Plan。

### 水线高度是强制输入项

水线高度（距基线的垂向位置，m）是**水线面计算 / 静水力曲线 / 浮心（水线面法）/ 三维型线与蒙皮**的必需输入，
识别流程对此做严格校验：

- 特征提取的"配置固定高度"步骤对每条 `half_wl` 列强制询问高度；**非数字、负数、非有限值或与已有水线重复的高度会被拒绝并要求重输**；
- 用户在此处取消/留空 → 弹出确认框；确认取消则**中止本次识别**（不生成"识别结果"节点）；
- 若识别结果不含任何 `half_wl` 列 → 警告上述计算将不可用，并要求确认后才会继续；
- 从"识别结果"导入时**再次校验**：水线高度缺失则拒绝导入，并提示先补高度；
- 已生成的"识别结果"可右键 **编辑水线高度...** 随时修正，无需重新识别。

### 从识别结果导入型线（按 Tab 决定导入目标）

在"识别结果"节点上右键 → **从offset导入...**。与 MATLAB `PushTool_import_from_offsetClicked`
一致，导入目标由**当前所在 Tab** 决定：

| 当前 Tab | 导入内容 | 生成节点 |
|----------|---------|---------|
| 半宽 (isTap=2) | 水线面 / 甲板线 | `Face → 船型模型 → Half` |
| 横剖面 (isTap=3) | 横剖面 (Body Plan) | `Face → 船型模型 → Body Plan` |
| 其它 Tab | 提示切换 Tab，不执行导入 | — |

> 注意：选中"识别结果"节点**不会**切换 Tab（与 MATLAB `Tree_tableSelectionChanged` 一致），
> 因此可以先切到目标 Tab，再右键导入。半宽值统一按 mm → m（`/1000`）换算。

### classifier.py —— 独立列角色分类模块

`Pyship/classifier.py` 提供独立可调用的分类 API（不依赖 GUI）：

```python
from classifier import ShipColumnClassifier

clf = ShipColumnClassifier()
clf.load_matlab_model('KNN_model.mat')        # 提取 12 特征 + 模型元数据
clf.train_from_columns(column_data_list,     # 原始列数据 list
                       ['station','z','half'],  # 对应角色
                       model_type='KNN')      # 或 'SVM' / 'Tree'
result = clf.classify_excel('型值表.xlsx')     # 一键读取并分类
# result.headers / result.predicted_labels / result.column_roles
clf.save_sklearn_model('clf.pkl')              # 保存训练好的模型
```

方法列表：
- `load_matlab_model(path)` — 加载 .mat 提取特征清单
- `train_from_columns(columns, labels, model_type)` — 原始列直接训练
- `train_from_labeled(features, labels, model_type)` — 已提取特征训练
- `classify_columns(matrix, label_filter=None)` — 矩阵预测
- `classify_excel(path)` — 一键读取 Excel + 预测
- `save_sklearn_model(path)` / `load_sklearn_model(path)` — pickle 持久化

测试 `test_classifier.py` 覆盖 22 项断言（加载元数据 / 训练 / 预测 / label_filter / 保存加载 / 三个 .mat 全部）。

## 计算算法（与 MATLAB 一致）

- 水线面：分段（等距段自动检测）累加，支持多段独立站距；`A = Σ scale·h·Σ(B·C)`，
  `M = Σ scale·h²·Σ(B·C·M)`；梯形 scale=1，辛普森1/3 scale=1/3，辛普森3/8 scale=3/8。
- 横剖面：分段梯形积分 `A=∫y·dz`，形心 `y_c=∫y²dz/∫ydz`、`z_c=∫y·z·dz/∫ydz`。
- 浮心（水线面法）：`V=∫Aw(z)dz`，`xB=∫LCF·Aw·dz/V`，`zB=∫z·Aw·dz/V`。
- 浮心（横剖面法）：对称剖面构造 → 横倾旋转 → 吃水截取（保留交点）→ Shoelace 面积矩 →
  沿船长梯形积分。
- 静水力：`V=∫Aw dz`，`VCB=∫Aw·z dz/V`，`BMT=IT/V`，`KMT=VCB+BMT`，
  `TPC=Aw·ρ/100`，`MCT=ρ·IL/(100·Lpp)`，船型系数 Cb/Cp/Cm/Cw；支持鲁棒异常点剔除。
  与 MATLAB `CalculateCurvesButtonPushed` 逐行一致：`cumtrapz` 累积积分（内置兼容实现，
  不依赖 `np.cumulative_trapezoid`）、水线半宽插值含线性外推（同 `interp1 'linear','extrap'`）、
  最终结果按 `interp1 'pchip'`（PCHIP）插值回目标吃水。
- 稳性：KN = yB·cosφ + zB·sinφ；GZ = KN − KG·sinφ − YG·cosφ；动稳性 `l_d=∫GZ dφ`；
  最小倾覆力臂 lq（切线法）、最大风倾力臂 lf（等面积法）、稳性衡准数 K=lq/lf，
  并依据《国内航行海船法定检验技术规则》(2011) 自动校核 GM / 极限静倾角 / K。
- 3D 蒙皮：型线 PCHIP 加密点云 → `(X,Z)→Y` 散点插值 → 规则网格 → 三角面片 → 左右舷镜像。

## 文件说明

```
Pyship/
├── main.py             # 启动入口
├── ship_app.py         # 主应用类（组合）
├── ship_app_ui.py      # 界面布局（菜单/工具栏/树/Tab/日志/撤销）
├── ship_app_actions.py # 业务操作（导入/ML/水线面/横剖面/拟合/导出）
├── ship_app_calc.py    # 高级计算（浮心/静水力/邦戎/稳性/3D）
├── ship_core.py        # 核心算法（公式移植自 ship.m）
├── ml_utils.py         # 机器学习（特征提取/模型加载/训练）
├── ui_widgets.py       # 可复用组件（可编辑表格/绘图画布/对话框）
├── qt_3d_viewer.py     # Qt SolidWorks 风格 3D 视窗（渲染器 + tkinter 嵌入）
├── glc.py              # opengl32.dll 最小 GL 绑定（固定管线）
├── icon/               # 界面图标（与 MATLAB 版共用）
├── test_core.py        # 核心算法自检
└── requirements.txt
```

## 与 MATLAB 版的差异说明

1. **UI 框架**：MATLAB App Designer → Tkinter + matplotlib（页面结构与操作逻辑保持一致）。
2. **ML 模型**：MATLAB 内部模型对象无法在 Python 中解码，加载 `.mat` 模型时提取特征清单等
   元数据；预测后端通过 sklearn 重新训练获得（详见"机器学习模块"第 3 条）。
3. **项目文件**：MATLAB 项目保存为 `.mat`，Python 版保存为 `.scs`（pickle 格式）。
4. **按钮 enable 移植**：工具栏按钮按 Tab 与树节点切换启用/禁用，与 MATLAB 各 TabButtonDown
   （`Tab_2ButtonDown` / `TabButtonDown` / `Tab_3ButtonDown` / `Tab_4ButtonDown`）一致；锁定状态下
   仅启用"锁定"按钮；3D 曲面 Tab 内部按钮根据选中船型节点与点云数据启用。

## 附加功能

- **Windows 原生界面**：使用系统原生主题（vista/winnative），原生 Notebook / 工具栏 / 表格，
  不做自定义配色，符合工业软件习惯。
- **坐标轴真实比例**：水线面半宽图、横剖面图启用 1:1 等比例（`set_true_aspect`），
  3D 船体按 X/Y/Z 实际跨度设置包围盒（`set_true_box_aspect`），避免"6 m 与 200 m 画得一样长"；
  静水力/邦戎/稳性等曲线图横纵轴量纲不同，保持 auto。
- **缩放与导出**：每个绘图画布均带 matplotlib 工具栏（放大框选 / 平移 / 还原 / 保存图片），
  并支持**滚轮缩放**（上滚放大、下滚缩小，2D/3D 均可）；"查看"菜单含"重置缩放 / 刷新图表"。
- **Qt SolidWorks 风格 3D 曲面**（`qt_3d_viewer.py` + `glc.py`）：
  - **启动即预加载**：应用运行后立即创建 **PyQt5 QOpenGLWidget** 渲染视窗
    （`QOpenGLWidget` + `opengl32.dll` 固定管线 GL，兼容 profile，不依赖 Qt3D 模块，
    无 GPU 环境自动走 ANGLE/软渲染）；宿主页未显示时保持隐藏（不弹独立窗口），
    切到 3D曲面 页即嵌入显示，无需等待创建；
  - **SOLIDWORKS 观感**：渐变背景、地面网格、坐标轴、双方向光 + 高光金属材质，
    实体 / 实体+边缘 / 纯线框 三种显示模式；全精度网格（STL 级 2.8 万面片）毫秒级绘制；
  - **交互**：左键旋转 / 中键(或Shift+左键)平移 / 滚轮缩放 / 双击适合视图；
    页面上提供"视角"预设（等轴测/正视图/侧视图/后视图/顶视图/底部视图）、适合视图、
    地面网格开关；"线框"下拉同步控制 Qt 显示模式；
  - **点云与型线实时显示**：生成点云（红点）与绘制型线（水线蓝 / 横剖面红 / 底部与龙骨绿）
    会直接叠加显示在 Qt 视窗中，无需切换页签即可看到结果；
  - **首选项**（设置→首选项...，持久化到 `~/scs_prefs.json`）：3D曲面背景（深色/中灰/浅色）、
    鼠标旋转方向反转、滚轮缩放方向反转、坐标轴与地面网格显示开关；
  - 通过 Windows `SetParent` 嵌入 tkinter 页面，用 tk 事件泵驱动 Qt 重绘；
    Qt 不可用时自动回退 matplotlib 3D（环境变量 `SCS_DISABLE_QT3D=1` 可强制关闭）。
- **多项目工作树**：树顶层支持**多个项目节点**（默认"项目"），右键空白处可**新建项目**；
  所有节点（含项目、Table/Model/Face 分组、水线面/横剖面/识别结果等）均可**重命名**
  （右键菜单或双击行内编辑）；项目可删除（至少保留一个），选中某项目即切换当前挂载项目。
- **scs 项目文件品牌**：保存项目时把应用 logo（`icon/船.png`）以 base64 **内嵌进 .scs 文件**，
  导入时恢复为窗口图标；启动/保存时注册 HKCU 用户级 `.scs` 文件关联（含 `DefaultIcon` 与
  双击打开命令），资源管理器中的 `.scs` 文件显示船 logo 图标（`icon/船.ico`）。
  若首次关联后资源管理器仍显示旧图标，属图标缓存：重启资源管理器或运行
  `ie4uinit.exe -show` 即可刷新。
- **matplotlib 3D 回退**：若未安装 PyQt5 或嵌入失败，3D曲面页保持原 matplotlib 3D：
  蒙皮**显示/导出分离**（STL 用全精度网格，交互显示用降采样网格），"蒙皮质量"档位
  流畅≈700 / 标准≈1500 / 精细≈3500 面片，`antialiased=False` 保证旋转跟手。
- **补齐底部**（仿 MATLAB `Button_FillBottomPointsClicked`）：
  - **点云**：逐站取该站最低点 (minY, minZ)，底部未闭合（|minY|>0.001）时在 Y=0→minY 间
    插值生成 3~8 个底部点（Z=minZ），合并去重后更新镜像点云与站号数组，并重绘
    （原始点红色、新增底部点蓝色，标题标注）；
  - **二维线**：型线视图额外绘制各站底部轮廓线与沿船的**龙骨线**（绿色），使型线图含船底；
  - **蒙皮面**：生成蒙皮时直接用**边界曲面封底**（`_hull_mesh_with_bottom`）——侧面按有效
    半宽构面，逐列取底部边界并连到龙骨线（y=0）构造闭合三角带，首尾阶梯自动补缝，
    不再依赖 `nan→0` 的平底，船底贴合真实型线且网格闭合（STL 为封闭实体）；
  - 底部已闭合的船体重复执行时会提示"无需补齐"。
- **邦戎曲线综合视图**：模仿 MATLAB `plotBonjeanComprehensiveView`——X 轴为**站位纵向位置
  （船中为0, m）**，每个站位处将横剖面面积（蓝色实线）与对基线面积矩（橙色虚线）按站距归一化
  展开，并绘制站位中心线与站号标注。
- **可靠的保存/加载**：
  - 项目保存（Ctrl+S / 文件→保存项目）**原子写入**：先写临时文件并 `fsync`，回读校验通过后才
    `os.replace` 覆盖正式文件，中途崩溃/磁盘写满不会损坏原有文件；
  - payload **版本化**（当前 `version=3`，v2/v3 均可加载），旧版本文件可平滑加载（缺省字段用默认值）；
  - `.scs` 文件**内嵌应用 logo**（base64），导入时恢复窗口图标；`.scs` 关联船 logo 图标与
    "用本应用打开"命令（HKCU 用户级，见下方"自动保存/最近文件/诊断"一节）；
  - 保存内容补全：除主尺度/水线面/横剖面/半宽与横剖面表/静水力/邦戎/稳性数据外，新增
    **ML 模型、锁定/对称/线框模式等 UI 状态**；ML 模型不可序列化时不阻塞保存；
  - 加载后**树重建按船型分组**（同一船型的水线面/横剖面归入同一"船型模型"节点，修复原先
    每条水线面各建一个船型模型的 bug），并重建原表格节点与模型节点；
  - **脏标记 + 关闭提示**：任何修改都会在窗口标题加 `*`，关闭时有未保存更改会弹出
    "保存/不保存/取消"三选一；保存或加载成功后清除；
  - 表格导出（CSV/TXT/Excel）同样原子写入；xlsx 一次导出 半宽表/横剖面表/原表格 三个工作表；
    CSV 默认 `utf-8-sig`（Excel 可直接打开）；顺带修复了 `menu_export` 中 `EditableTable` 未导入
    导致的潜在 NameError。
- **Excel 模式表格**（`EditableTable`）：左侧行号列、网格线、活动单元格高亮边框；
  方向键 / Tab / Enter / Home / End / PageUp / PageDown 导航；双击、F2 或直接键入编辑；
  Ctrl+C / Ctrl+X / Ctrl+V 以 TSV 与 Excel 互通；Delete 清空、Ctrl+D 向下填充、右键菜单；
  表格内置撤销/重做。
- **全局 Ctrl+Z / Ctrl+Y**：所有输入区域均可撤销重做——
  `tk.Text` 用内置撤销栈，Entry / Spinbox / Combobox 由 `install_undo_support` 维护快照栈
  （类级绑定，对后续动态创建的对话框同样生效）；连续输入自动合并为一步。
  焦点不在输入控件上时，Ctrl+Z 回退到应用级操作撤销。
- **拉杆尺寸限制**：所有可拖拽分栏（PanedWindow）均带最小尺寸钳制（`ClampedPanedWindow`），
  防止拉杆拖过头导致布局错乱；横向/纵向分栏各有合理默认比例。
- **底部状态栏**：实时显示**当前项目名与未保存标记(*)**、当前 Tab、主尺度、积分方法、
  原点位置、机器学习模型状态、本地时间；脏标记在编辑/保存时自动刷新。
- **撤销机制**：表格编辑在写入前保存撤销快照（栈深 50）；增删行、添加列等操作同样可撤销。
- **稳健模态对话框**：所有输入对话框支持 Enter/Esc、自动居中于主窗口、grab 置顶聚焦。
- **稳健的表格文件导入**（xlsx/xls/csv/txt）：
  - 表头智能识别：按"非空占比 + 文本占比 + 表头特征词（站号/半宽/高度/系数/station/z/half 等）"给前 20 行打分，
    并校验其下方存在数值数据行；可正确跳过**标题行**（合并单元格"XX船型值表"）、自动丢弃表头下方的**单位行**（如 m/m/m）；
    列数取全表最大宽度，不再因标题行只有 1 格而截断。
  - `.xlsx` 用 openpyxl（`data_only=True`）；`.xls` 旧版二进制格式经 xlrd 读取（requirements 已含 `xlrd>=2.0`，
    未安装时给出明确提示）；CSV/TXT 按 `utf-8-sig → gbk → gb18030 → latin-1` 自动探测编码（兼容 Excel 另存的 GBK/ANSI）；
    TXT 自动识别制表符/逗号分隔。
  - 自动裁剪尾部全空行与右侧全空列；行长度不足自动补齐，保证后续 ML 特征提取的矩阵形状一致。
- **全局导航增强**：
  - **页签快捷键**：`Ctrl+Tab` / `Ctrl+Shift+Tab` 循环切换工作页签，`Ctrl+1..8` 直达对应页签；
  - **最近打开的项目**：文件菜单"最近打开"记录最近 10 个 `.scs`（持久化于 `~/scs_prefs.json`），
    一键打开（文件缺失自动从列表移除）；`Ctrl+O` 打开、`Ctrl+N` 新建项目；
  - **状态栏增强**：左侧显示当前项目名与未保存标记 `*`。
- **自动保存与崩溃恢复**：
  - 默认每 **5 分钟**（首选项可配 1~30 分钟/可关闭）把当前项目**原子保存到独立备份文件**
    （已命名项目 → 同目录 `xx.autosave.scs`；未命名 → `~/scs_autosave.scs`），**不覆盖原文件**；
  - 启动时若检测到上次崩溃遗留的备份，提示一键恢复（恢复后仍标记未保存，需手动保存主文件）。
- **偏好设置中心（扩展）**：首选项对话框新增——**界面字体大小**（9~12）、**自动保存开关与间隔**；
  保持 Windows 原生外观，不换肤；所有偏好持久化到 `~/scs_prefs.json`。
- **加载与边界状态**：点云/型线/蒙皮/浮心/静水力/邦戎/KN/GZ/动稳性/STL 导出等长任务统一
  **忙指示**（等待光标 + 状态栏提示，try/finally 保证复位）；数据缺失的入口均有明确提示对话框。
- **帮助与诊断**：新增"帮助"菜单——
  - **诊断信息...**：环境信息（Python/系统/Qt3D 可用性/各库版本/.scs 关联/日志路径）+ 最近 200 条
    运行日志；支持**导出诊断日志**、**直接打开崩溃日志**（`scs_crash.log`）；
  - **关于 SCS...**：应用 logo + 版本信息；
  - 配套 `dbg.py` 逐步追踪日志（`scs_debug.log`）+ `main.py` 内 faulthandler（崩溃回溯写入
    `scs_crash.log` 与 stderr）。

## 测试验证

`test_core.py` 验证核心算法（14 项）；`test_ml.py` 验证机器学习模型加载与训练；`test_data.py`
验证数据导入流程与项目保存/加载；`test_gui.py` 端到端 GUI 冒烟测试（16 项）；
`test_buttons.py` 验证工具栏按钮 enable 状态与 MATLAB TabButtonDown 一致（5 Tab × 16 按钮 = 80 项）；
`test_classifier.py` 验证 classifier.py 分类接口（22 项）；`test_train.py` 验证训练流程与特征维度一致性；
`test_sash.py` 验证各 Tab 分栏拉杆的最小尺寸钳制；`test_offset_import.py` 验证"识别结果"按 Tab
导入水线面/甲板线与横剖面的两条路径；`test_excel_undo.py` 验证 Excel 模式表格、Ctrl+Z 撤销、
坐标轴真实比例与原生主题；`test_waterline_height.py` 验证水线高度的强制输入与导入前校验；
`test_import_excel.py` 验证 xlsx/csv/txt 的表头识别、标题行/单位行处理、GBK 编码与空行裁剪；
`test_hydrostatics_matlab.py` 将 `ship.m` 的静水力/邦戎曲线公式逐行翻译为参考实现，
与 `calc_hydrostatics` / `calc_bonjean` 全键逐点对比（含异常点剔除路径，46 项）；
`test_save_load.py` 验证保存/加载的原子写入、版本化、脏标记、树重建分组与表格导出（23 项）；
`test_3d_bonjean.py` 验证 3D 蒙皮显示/STL 网格分离与质量档位面片数、邦戎综合视图 X 轴=站位（10 项）；
`test_fill_bottom.py` 验证"补齐底部"在点云/二维线/蒙皮面的协同（逐站插值、镜像、重绘、去重，13 项）；
`test_qt3d.py` 验证 Qt 3D 视窗的法线外翻、网格准备、视角预设、适合视图等纯逻辑（19 项，不依赖 GPU 渲染）；
`test_features.py` 验证多项目树/重命名、首选项持久化与应用、Qt 点云/型线推送、scs logo 内嵌、
日志去冗余（30 项）；
`test_ux.py` 验证状态栏脏标记、页签快捷键、最近文件、自动保存独立备份、首选项字体/自动保存、
诊断面板、忙指示（20 项）。

在项目根（含 `src/` 的目录）执行：

```
python tests\test_core.py
python tests\test_ml.py
python tests\test_data.py
python tests\test_buttons.py
python tests\test_gui.py
python tests\test_classifier.py
python tests\test_train.py
python tests\test_sash.py
python tests\test_offset_import.py
python tests\test_excel_undo.py
python tests\test_waterline_height.py
python tests\test_import_excel.py
python tests\test_hydrostatics_matlab.py
python tests\test_save_load.py
python tests\test_3d_bonjean.py
python tests\test_fill_bottom.py
python tests\test_qt3d.py
python tests\test_features.py
python tests\test_ux.py
```

或一次性运行全部：`for %%f in (tests\test_*.py) do python %%f`（PowerShell：`Get-ChildItem tests\test_*.py | ForEach-Object { python $_ }`）。

