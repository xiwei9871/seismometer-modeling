# 智能地震仪 STL Stage 01 设计

## 目标

把 `/Users/xiwei/modeling/智能地震仪-221128(1).STL`（或 `source/` 中的同一源文件）转换为可重复生成的几何分析数据、独立 PART manifest、重复几何分组、网格质量记录和保持原始装配位置的 Blender 场景。Stage 01 只恢复和记录几何，不猜测语义名称，不修改源 STL 或其几何形状。

## 已确认的上下文与边界

- 当前扫描到一个主要 STL：`智能地震仪-221128(1).STL`，约 21.2 MB，二进制 STL；文件头含 `solid` 不能作为 ASCII/Binary 判断依据。
- STL 没有可靠单位元数据。报告将数值单位标记为 `mm`，但同时写入 `unit_confidence: "assumed"`，不把它声明为事实。
- 根目录原始 STL 保留不动；如 `source/` 为空，流程可用 `shutil.copy2` 将它复制到 `source/`，根目录原文件仍作为只读源保留。
- 不执行 merge by distance、remove doubles、decimate、remesh、repair、boolean、补洞、平滑、法线重建或任何会改变世界空间几何的操作。
- 每个 connected component 保留为独立 PART，即使只有 1–3 个面；疑似碎片只标记，不删除。
- 相同几何只建立 `duplicate_group`，不把不同位置的物理对象 Join。
- Stage 01 不建立 `ENCLOSURE`、`PCB`、`SENSOR`、`SCREWS` 等语义集合，不制作爆炸动画、材质、灯光或渲染。

## 方案选择

采用方案 A：Python 几何分析为事实来源，Blender 只负责从原始 STL 导入、Loose Parts 分离和场景保存。

方案 B（完全由 Blender 统计）对 Blender 版本和 headless importer 的依赖更强，无法在 Blender 不可用时生成完整数据。方案 C（先由 Python 导出每个组件 STL 再逐个导入）虽容易映射，但会引入额外中间几何并偏离 Loose Parts 验收路径。方案 A 可以先独立完成报告，再把 Blender 拆出的对象通过几何特征映射到稳定 PART ID。

## 目录与模块职责

```text
modeling/
├── AGENTS.md
├── requirements.txt
├── source/                         # canonical copied input, never edited
├── scripts/
│   ├── analyze_stl.py              # load source, components, global report
│   ├── analyze_parts.py            # classification, manifest, quality, report data
│   ├── detect_duplicate_parts.py  # tolerant duplicate grouping and manifest update
│   ├── import_and_split_blender.py# Blender-only import, loose split, save .blend
│   └── inspect_part.py             # optional Blender inspection utility
├── data/
├── output/reports/
├── logs/
└── run_stage01.py                 # reproducible orchestrator
```

`analyze_stl.py` 输出原始总体和 component 事实；`analyze_parts.py` 消费该事实并生成分类、manifest、疑似碎片、网格质量和 Stage 01 报告；`detect_duplicate_parts.py` 消费 manifest 并只更新分组字段；Blender 脚本消费 manifest 和原 STL，不反向修改分析事实。

## 数据流与稳定身份

1. `run_stage01.py` 从 `source/*.stl` 选择唯一主要 STL；若没有则扫描项目根目录；若存在多个候选则按文件大小选择最大者并在日志中发出警告。首次运行时可把根目录唯一主要 STL复制到 `source/`。
2. `trimesh.load_mesh(..., process=False)` 读取网格，避免分析阶段主动进行 mesh cleanup。按 `mesh.split(only_watertight=False)` 得到所有连通组件，不过滤组件。
3. 对每个组件计算面数、顶点数、包围盒、包围盒体积、质心、表面积、体积可用性、watertight、Euler number 和网格质量诊断。所有组件按确定性 key 排序：包围盒体积降序、合法实际体积降序、面数降序、质心 x/y/z 升序，再用稳定特征和原始 split index 作为并列决胜项。
4. 排序后的第 N 个组件得到 `PART_{N:03d}`。`source_component_index` 仍记录 trimesh 原始 split 顺序；在相同源文件、相同 trimesh 版本和相同数值输入下，ID 可重复生成。几何特征完全相同且质心也完全相同的不可区分对象会依靠 source component index 保持顺序，并在日志中记录该限制。
5. Blender 导入原 STL 后对导入的 mesh 对象执行 `Separate by Loose Parts`。拆分对象用面数、顶点数、排序后的 bbox 尺寸、表面积、体积可用性/体积和质心与 manifest 匹配；重复几何再用质心和确定性顺序区分。匹配失败或一对多歧义会写入日志并让 Blender 步骤显式失败，不静默改名。

## 分析与分类规则

### 单位与尺寸

所有原始数值原样保存；`*_mm` 只是当前项目假设下的字段名。总体报告写入 `unit_assumption: "mm"` 和 `unit_confidence: "assumed"`，并记录包围盒是否大致接近 190×170×180 的提示性比较，不对几何做缩放。

### Size class

`FRAGMENT` 优先表示命中疑似碎片规则。其余组件使用相对、数据驱动的综合分数，不只依赖 bbox volume：对 log 缩放后的 bbox 对角线、bbox 体积、表面积和面数分别计算在本模型组件集合中的 percentile rank，权重为 0.30、0.20、0.25、0.25。分数区间为 `>=0.75 MAJOR`、`>=0.40 MEDIUM`、`>=0.15 SMALL`、其余 `TINY`。组件数量很少时仍使用同一确定性规则，并把各分量/阈值写入报告，方便人工复核；薄板件可因面积、对角线或面数保留在较高类别。

### Complexity class

复杂度只描述几何统计，不赋予零件语义：`TRIVIAL` 为不超过 10 面，`SIMPLE` 为不超过组件面数的中位数，`MODERATE` 为不超过 90 分位数，其他为 `COMPLEX`。面数分位点和边界值写入报告。

### Suspicious fragments

命中 `face_count <= 10`，或同时满足“面数不超过 `max(10, round(0.01 * median_face_count))` 且 bbox 对角线不超过正值组件对角线中位数的 1%”时写入 `suspicious_fragments.json`。每条记录包含 PART ID、完整理由、面数、bbox 和质心。该文件是审查清单，不是删除清单。

### Duplicate groups

几何签名包含排序后的 bbox 尺寸、面数、顶点数、表面积、体积和 watertight。尺寸比较使用 `abs(a-b) <= max(0.1 mm, 0.5% * max(abs(a), abs(b), 1))`；面积和合法体积使用 1% 相对容差；面数和顶点数优先完全相同。只有至少两个对象组成的组才得到 `DG_{N:03d}`，组内仍保留全部 PART。

`HIGH` 需要尺寸、面数、顶点数、表面积、合法体积、watertight 全部匹配；缺少合法体积或只有部分特征匹配时最高为 `MEDIUM`。组编号按组代表的稳定 PART 排序，成员按 PART ID 排序。输出 `duplicate_groups.json`，并把 `duplicate_group` 与 `duplicate_confidence` 写回 manifest。

## Blender 场景设计

- 新建空场景并删除默认 Cube、Camera、Light。
- 使用 Blender 4 的 `bpy.ops.wm.stl_import`，兼容回退到旧版 `bpy.ops.import_mesh.stl`。
- 通过 `bpy.ops.mesh.separate(type='LOOSE')` 恢复每个 disconnected component 为一个 Object；不对 mesh 做 cleanup。
- 建立 `DEVICE` 根 Collection 和 `MAJOR`、`MEDIUM`、`SMALL`、`TINY`、`SUSPECTED_FRAGMENT` 子 Collection。对象按 manifest 的纯几何分类进入集合。
- 每个对象命名为唯一稳定的 `PART_XXX`，写入 manifest 字段和 `source="original_stl"` 等 custom properties。
- Origin 优先设置到几何质心；通过局部坐标平移和对象世界矩阵补偿保持每个顶点的世界坐标不变。保存 `assembled_position`、`assembled_rotation`、`assembled_scale`，并额外保存 world matrix 以便核对。
- 使用由 PART ID 派生的确定性 viewport display color 作为检查辅助；不创建正式材质。
- 保存 `output/stage01_split.blend`。所有对象保持源 STL 的装配状态，因此整体外观可在 Blender 中直接复核。

## 输出文件契约

- `data/source_model_report.json`：源文件元信息、整体统计、单位假设、全部 component 统计和质量摘要。
- `data/parts_manifest.csv` / `.json`：稳定 PART ID、component index、尺寸、位置、拓扑、分类、duplicate group、fragment 状态和备注。
- `data/duplicate_groups.json`：重复组数量、成员、代表几何特征、置信度和容差。
- `data/suspicious_fragments.json`：所有疑似碎片及理由。
- `data/mesh_quality_report.json`：总体和逐 component 的 watertight、winding、边界/非流形/重复面等诊断；诊断失败也要记录错误而不是修复。
- `data/assembly_initial.json`：每个对象的 location、rotation_euler、scale 和 world matrix。
- `output/reports/stage01_report.md`：源信息、component/class 数量、前 20 个重复组、质量问题和下一阶段人工核对清单。
- `logs/stage01.log`：源文件、时间、依赖、组件、重复组、碎片、Blender 输出、警告、错误及具体 PART ID。

## 错误处理与可重复性

- 源文件不存在、无法解析或没有面时，Python 阶段以非零状态结束并记录明确错误。
- 单个 component 的指标计算异常时保留该 component，字段写为 `null`，记录 `stage/component/error`，不丢弃组件。
- Blender 未找到时先完成 Python 报告，日志写入 `BLENDER_NOT_FOUND`；若自动安装失败，整个流程以明确的部分成功状态结束，绝不生成伪造 `.blend`。
- 每次运行覆盖生成的 JSON/CSV/Blend/报告，不触碰源 STL；日志追加运行分隔和源文件 SHA-256，便于审计。
- 所有排序、颜色、分组和命名都使用确定性规则。源文件内容不变时，输出除时间字段外应稳定。

## 测试策略

使用小型临时 trimesh 盒体/薄板/低面数三角形网格测试纯 Python 函数，不把 21 MB 源文件作为单元测试输入。测试覆盖：

- 稳定排序和 `PART_001` 起始编号；
- bbox 旋转后排序尺寸不变；
- 0.1 mm/0.5% 尺寸、1% 面积/体积容差；
- 面数 1–10 的疑似碎片只标记；
- 薄板不因 bbox 体积小而必然降为 TINY；
- manifest CSV/JSON 字段一致、duplicate group 回写一致；
- Blender 不可用时日志和退出状态明确；
- 若 Blender 可用，headless 生成的对象数、PART 名称、Collection、custom properties、初始 world matrix 和源总 bbox 与 Python report 一致。

## 验收边界

Stage 01 只到 `stage01_split.blend` 和上述报告为止。完成后停止，不进入语义识别、照片对应、爆炸距离、动画、材质、灯光、渲染或 CAD 重建。
