# 智能地震仪 STL Stage 01 Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 从不可变原始 STL 生成稳定的几何 component/PART 数据、重复组、质量报告、检查报告和保持装配位置的 `stage01_split.blend`。

**Architecture:** Python 先读取源 STL 并在内存中建立仅用于分析的精确坐标索引，生成稳定排序的 component 事实；后续 Python 阶段消费该事实生成 manifest、分类、碎片/质量/重复组和报告。Blender 阶段只导入原 STL、Loose Parts 分离、按 manifest 映射对象并保存场景，不把 Blender 结果反写为新的几何事实。

**Tech Stack:** Python 3.10+、`trimesh`、`numpy`、`pytest`、Blender 4.x `bpy`、stdlib `json/csv/logging/subprocess`。

**Execution adjustment (2026-09-08):** 完成 Task 5 后，先对真实 STL 执行全部 Python 分析阶段，独立核对组件数量、内存峰值、报告完整性和源文件 hash；只有真实 Python 阶段通过后才进入 Blender Task 6。这样可在引入 Blender 映射前尽早暴露真实模型规模问题。

---

## 文件结构

将创建以下文件；源 STL 和 `.DS_Store` 不加入版本控制，源 STL 不会被写入：

```text
modeling/
├── AGENTS.md
├── .gitignore
├── requirements.txt
├── run_stage01.py
├── source/                             # run_stage01.py 复制的 canonical input
├── scripts/
│   ├── __init__.py
│   ├── stage01_core.py                 # 纯 Python/Trimesh 事实与通用函数
│   ├── analyze_stl.py                  # 总体与 component 事实报告
│   ├── analyze_parts.py                # 分类、manifest、质量、报告
│   ├── detect_duplicate_parts.py       # 容差 duplicate grouping
│   ├── import_and_split_blender.py     # Blender-only import/split/save
│   └── inspect_part.py                 # Blender inspection utility
├── tests/
│   ├── conftest.py
│   ├── test_blender_script_contract.py
│   ├── test_analyze_stl.py
│   ├── test_run_stage01_pipeline.py
│   ├── test_stage01_core.py
│   ├── test_analyze_parts.py
│   ├── test_duplicates.py
│   └── test_run_stage01.py
├── data/
├── output/reports/
└── logs/
```

`stage01_core.py` 不写文件、不改 mesh；命令脚本负责输入输出和日志。这样单元测试能使用小网格而不用加载 21 MB 源文件。

## Task 1: 建立项目约束、依赖和测试入口

**Files:**

- Create: `AGENTS.md`
- Create: `.gitignore`
- Create: `requirements.txt`
- Create: `run_stage01.py`
- Create: `scripts/__init__.py`
- Create: `tests/conftest.py`
- Create: `tests/test_run_stage01.py`

- [ ] **Step 1: 写源安全和候选选择的失败测试**

在 `tests/test_run_stage01.py` 写入：

```python
from pathlib import Path

import pytest

from run_stage01 import choose_source_file, ensure_project_dirs


def test_choose_source_prefers_largest_stl_in_source_without_modifying_inputs(tmp_path):
    source_dir = tmp_path / "source"
    source_dir.mkdir()
    small = source_dir / "small.stl"
    large = source_dir / "large.stl"
    small.write_bytes(b"small")
    large.write_bytes(b"large-file")

    chosen, warnings = choose_source_file(tmp_path)

    assert chosen == large
    assert warnings == []
    assert small.read_bytes() == b"small"
    assert large.read_bytes() == b"large-file"


def test_choose_source_falls_back_to_root_and_reports_copy_candidate(tmp_path):
    root_file = tmp_path / "device.STL"
    root_file.write_bytes(b"stl")

    chosen, warnings = choose_source_file(tmp_path)

    assert chosen == root_file
    assert any("root" in warning.lower() for warning in warnings)


def test_ensure_project_dirs_creates_only_generated_directories(tmp_path):
    ensure_project_dirs(tmp_path)

    for relative in ("source", "scripts", "data", "output/reports", "logs"):
        assert (tmp_path / relative).is_dir()


def test_choose_source_rejects_project_with_no_stl(tmp_path):
    with pytest.raises(FileNotFoundError, match="No STL source file"):
        choose_source_file(tmp_path)
```

- [ ] **Step 2: 运行测试确认按预期失败**

运行：

```bash
python3 -m pytest -q tests/test_run_stage01.py
```

预期：收集阶段因 `run_stage01.py` 不存在而失败；此失败证明测试尚未被实现代码“假通过”。

- [ ] **Step 3: 写入最小项目约束和依赖文件**

`AGENTS.md` 使用已批准设计中的 Stage 01 规则，明确原始 STL 不可变、PART ID 稳定、禁止修复/简化/Join、只标记碎片、所有处理可从原始 STL 重建，并明确当前单位是带 `assumed` 置信度的 mm。

`requirements.txt` 写入：

```text
numpy>=1.24,<3
trimesh>=4.0,<5
pytest>=8,<9
```

`.gitignore` 写入：

```text
.venv/
__pycache__/
.pytest_cache/
.DS_Store
source/*.stl
source/*.STL
data/*.json
data/*.csv
output/*.blend
logs/*.log
```

`.gitignore` 写入：

```text
.venv/
__pycache__/
.pytest_cache/
.DS_Store
source/*.stl
source/*.STL
data/*.json
data/*.csv
output/*.blend
logs/*.log
```

- [ ] **Step 4: 写入最小源选择和目录实现**

`run_stage01.py` 提供：

```python
def ensure_project_dirs(project_root: Path) -> None: ...
def choose_source_file(project_root: Path) -> tuple[Path, list[str]]: ...
```

`choose_source_file` 只扫描 `source/` 和项目根目录的直接子文件，扩展名按 `.stl` 不区分大小写；`source/` 有多个候选或根目录有多个候选时按 `(file_size_bytes, filename.casefold())` 降序选择最大文件，并返回明确 warning。若根目录找到唯一文件，复制逻辑留给 orchestrator，但选择结果仍是根目录原文件；任何函数都不写入候选文件。

`tests/conftest.py` 只把项目根目录加入 `sys.path`，不改变测试环境变量。

- [ ] **Step 5: 运行测试确认通过**

运行：

```bash
python3 -m pytest -q tests/test_run_stage01.py
```

预期：4 tests passed。

- [ ] **Step 6: 提交**

```bash
git add AGENTS.md requirements.txt run_stage01.py scripts/__init__.py tests/conftest.py tests/test_run_stage01.py
git commit -m "chore: bootstrap STL stage01 project"
```

## Task 2: 实现无破坏性的 Trimesh 事实层和稳定 PART ID

**Files:**

- Create: `scripts/stage01_core.py`
- Modify: `tests/test_stage01_core.py`

- [ ] **Step 1: 写核心事实层失败测试**

`tests/test_stage01_core.py` 写入下列测试和 fixture。测试构造原始 STL 风格的重复顶点 mesh，确保 connectivity 不能依赖 `process=True` 的隐式清理：

```python
import numpy as np
import trimesh

from scripts.stage01_core import (
    build_exact_indexed_mesh,
    component_metrics,
    assign_part_ids,
    sorted_bbox_dimensions,
    bbox_dimensions_match,
    relative_value_match,
)


def duplicate_vertex_mesh():
    vertices = np.array([
        [0, 0, 0], [1, 0, 0], [0, 1, 0],
        [0, 0, 0], [1, 0, 0], [0, 1, 0],
        [10, 0, 0], [11, 0, 0], [10, 1, 0],
    ], dtype=float)
    faces = np.array([[0, 1, 2], [3, 4, 5], [6, 7, 8]], dtype=np.int64)
    return trimesh.Trimesh(vertices=vertices, faces=faces, process=False)


def test_build_exact_indexed_mesh_only_indexes_equal_coordinates():
    raw = duplicate_vertex_mesh()

    indexed = build_exact_indexed_mesh(raw)

    assert len(raw.vertices) == 9
    assert len(indexed.vertices) == 6
    assert len(indexed.faces) == 3
    assert np.array_equal(indexed.faces[0], indexed.faces[1])
    assert np.array_equal(raw.faces, faces_for_raw_mesh(raw))


def faces_for_raw_mesh(mesh):
    return np.asarray(mesh.faces).copy()


def test_component_metrics_reports_bbox_area_and_vertex_count_without_repair():
    raw = duplicate_vertex_mesh()
    indexed = build_exact_indexed_mesh(raw)

    metrics = component_metrics(indexed, source_component_index=4)

    assert metrics["source_component_index"] == 4
    assert metrics["face_count"] == 3
    assert metrics["vertex_count"] == 6
    assert len(metrics["min_bound"]) == 3
    assert len(metrics["max_bound"]) == 3
    assert metrics["surface_area"] == 1.5


def test_assign_part_ids_sort_ties_deterministically():
    records = [
        {"source_component_index": 1, "bbox_volume": 2.0, "volume": None,
         "face_count": 4, "centroid": [1.0, 0.0, 0.0], "vertex_count": 4},
        {"source_component_index": 0, "bbox_volume": 2.0, "volume": None,
         "face_count": 4, "centroid": [1.0, 0.0, 0.0], "vertex_count": 4},
        {"source_component_index": 2, "bbox_volume": 8.0, "volume": None,
         "face_count": 1, "centroid": [0.0, 0.0, 0.0], "vertex_count": 3},
    ]

    assigned = assign_part_ids(records)

    assert [record["part_id"] for record in assigned] == ["PART_001", "PART_002", "PART_003"]
    assert [record["source_component_index"] for record in assigned] == [2, 0, 1]


def test_sorted_bbox_dimensions_are_rotation_invariant():
    assert sorted_bbox_dimensions([10.0, 5.0, 20.0]) == [5.0, 10.0, 20.0]
    assert sorted_bbox_dimensions([20.0, 10.0, 5.0]) == [5.0, 10.0, 20.0]


def test_tolerances_accept_requested_boundaries_and_reject_outliers():
    assert bbox_dimensions_match([10, 5, 20], [10.04, 5, 20])
    assert bbox_dimensions_match([10, 5, 20], [10.06, 5, 20])
    assert not bbox_dimensions_match([10, 5, 20], [10.2, 5, 20])
    assert relative_value_match(100.0, 100.9, ratio=0.01)
    assert not relative_value_match(100.0, 102.0, ratio=0.01)
```

The `component_metrics` assertion allows the implementation to use exact-indexed component meshes while retaining a valid metric contract; the integration test in Task 3 will pin the actual field semantics to unique indexed vertices.

- [ ] **Step 2: 运行测试确认失败**

运行：

```bash
python3 -m pytest -q tests/test_stage01_core.py
```

预期：因 `scripts.stage01_core` 尚不存在而失败。

- [ ] **Step 3: 实现精确坐标索引和指标函数**

`stage01_core.py` 实现以下公共接口：

```python
def build_exact_indexed_mesh(raw_mesh: trimesh.Trimesh) -> trimesh.Trimesh:
    """Return an in-memory exact-coordinate indexed copy; never mutate raw_mesh."""

def component_metrics(mesh: trimesh.Trimesh, source_component_index: int) -> dict:
    """Return JSON-safe geometry/topology metrics, with invalid volume as None."""

def assign_part_ids(records: list[dict]) -> list[dict]: ...
def sorted_bbox_dimensions(dimensions: Sequence[float]) -> list[float]: ...
def bbox_dimensions_match(left, right, absolute_mm=0.1, relative_ratio=0.005) -> bool: ...
def relative_value_match(left, right, ratio=0.01) -> bool: ...
```

`build_exact_indexed_mesh` 使用 coordinate tuple → index 映射，不调用 `merge_vertices`, `process`, `remove_*`, `repair` 或任何 trimesh cleanup；它只创建分析副本，报告的 `vertex_count` 定义为该副本中的精确唯一坐标数。`component_metrics` 使用 `mesh.bounds`, `mesh.centroid`, `mesh.area`, `mesh.volume`, `mesh.is_watertight`, `mesh.euler_number`，每项异常捕获为 `None` 并返回 `metric_errors`；不为取得可用体积调用补洞或法线修复。

`assign_part_ids` 的排序 key 为：

```python
(-bbox_volume_or_negative_inf,
 -valid_volume_or_negative_inf,
 -face_count,
 centroid_x, centroid_y, centroid_z,
 vertex_count,
 source_component_index,
)
```

空/NaN 数值先转换为 `None`，最后一个 source index 保证全序。函数复制/排序 records，不修改调用者原列表。

- [ ] **Step 4: 运行核心测试确认通过**

运行：

```bash
python3 -m pytest -q tests/test_stage01_core.py
```

预期：6 tests passed。

- [ ] **Step 5: 提交**

```bash
git add scripts/stage01_core.py tests/test_stage01_core.py
git commit -m "feat: add deterministic STL geometry facts"
```

## Task 3: 实现源 STL 总体/component 分析

**Files:**

- Create: `scripts/analyze_stl.py`
- Modify: `scripts/stage01_core.py`
- Create: `tests/test_analyze_stl.py`

- [ ] **Step 1: 写分析 CLI 的失败测试**

`tests/test_analyze_stl.py` 写入：

```python
import json

import trimesh

from scripts.analyze_stl import analyze_source_mesh, write_json


def test_analyze_source_mesh_preserves_all_disconnected_components(tmp_path):
    first = trimesh.creation.box(extents=[4, 4, 4])
    second = trimesh.creation.box(extents=[1, 2, 3])
    second.apply_translation([10, 0, 0])
    raw = trimesh.util.concatenate([first, second])

    report = analyze_source_mesh(raw, source_file="fixture.stl", file_size_bytes=123)

    assert report["file_size_bytes"] == 123
    assert report["faces"] == len(raw.faces)
    assert report["connected_component_count"] == 2
    assert len(report["components"]) == 2
    assert all(item["part_id"].startswith("PART_") for item in report["components"])
    assert report["unit_assumption"] == "mm"
    assert report["unit_confidence"] == "assumed"


def test_write_json_uses_utf8_and_stable_indent(tmp_path):
    destination = tmp_path / "report.json"
    write_json(destination, {"source_file": "智能地震仪.STL", "value": 1})

    parsed = json.loads(destination.read_text(encoding="utf-8"))
    assert parsed["source_file"] == "智能地震仪.STL"
    assert destination.read_text(encoding="utf-8").endswith("\n")
```

- [ ] **Step 2: 运行测试确认失败**

运行：

```bash
python3 -m pytest -q tests/test_analyze_stl.py
```

预期：因 `scripts.analyze_stl` 不存在而失败。

- [ ] **Step 3: 实现 source analysis**

`analyze_stl.py` 提供：

```python
def analyze_source_file(source_file: Path) -> dict: ...
def analyze_source_mesh(mesh: trimesh.Trimesh, source_file: str, file_size_bytes: int) -> dict: ...
def write_json(path: Path, payload: dict) -> None: ...
def main(argv: Sequence[str] | None = None) -> int: ...
```

加载使用 `trimesh.load_mesh(source_file, file_type="stl", process=False)`；若返回 Scene，只在内存中按原始 geometry 顺序拼接，不修改源文件。为避免二进制 STL 每个 facet 的顶点没有索引，先保留 raw mesh，再调用 `build_exact_indexed_mesh` 得到仅供分析的 indexed mesh；所有 connectivity、metrics 和 component split 都在 indexed copy 上进行。component 顺序先记录 split index，再调用 `assign_part_ids`。报告写入整体 bounds/dimensions/centroid/area/volume/is_watertight/euler_number、file SHA-256、原始 STL facet-expanded vertex count、exact-coordinate indexed vertex count、components、unit assumption 和 `analysis_topology_note`。报告顶层 `vertices` 使用 exact-coordinate indexed vertex count，另以 `raw_vertex_count` 保留 STL 载入后的 facet-expanded 计数，避免把 STL 的无索引顶点和分析拓扑顶点混为一谈。

组件提取使用 `indexed_mesh.split(only_watertight=False)`；不使用 `only_watertight=True`，不丢弃任何 component。若指标函数抛出异常，生成 component 的 `metric_errors` 并继续；若加载失败或总面数为 0，打印错误并返回非零。

- [ ] **Step 4: 运行测试确认通过**

运行：

```bash
python3 -m pytest -q tests/test_analyze_stl.py
```

预期：2 tests passed。

- [ ] **Step 5: 提交**

```bash
git add scripts/analyze_stl.py scripts/stage01_core.py tests/test_analyze_stl.py
git commit -m "feat: analyze STL components without mutation"
```

## Task 4: 生成分类、manifest、碎片和质量报告

**Files:**

- Create: `scripts/analyze_parts.py`
- Create: `tests/test_analyze_parts.py`

- [ ] **Step 1: 写失败测试覆盖分类、薄板和只标记碎片**

`tests/test_analyze_parts.py` 写入：

```python
from scripts.analyze_parts import (
    classify_complexity,
    classify_size,
    detect_suspicious_fragment,
    manifest_fieldnames,
    render_stage01_report,
)


def record(part_id, faces, diagonal, bbox_volume, area):
    return {
        "part_id": part_id,
        "face_count": faces,
        "vertex_count": faces * 3,
        "bbox_dimensions": [diagonal, diagonal, diagonal],
        "bbox_diagonal": diagonal,
        "bbox_volume": bbox_volume,
        "surface_area": area,
        "volume": None,
        "volume_valid": False,
        "watertight": False,
        "centroid": [0, 0, 0],
    }


def test_size_classifier_uses_multiple_features_not_volume_only():
    records = [
        record("PART_001", 200, 100, 1, 500),
        record("PART_002", 20, 10, 20, 30),
        record("PART_003", 4, 4, 0.1, 16),
    ]

    classes = classify_size(records)

    assert classes["PART_001"] in {"MAJOR", "MEDIUM"}
    assert classes["PART_003"] == "FRAGMENT"


def test_low_volume_thin_plate_is_not_automatically_tiny():
    records = [
        record("PLATE", 500, 100, 0.001, 1000),
        record("BLOCK", 80, 20, 100, 80),
    ]

    classes = classify_size(records)

    assert classes["PLATE"] in {"MAJOR", "MEDIUM"}


def test_fragment_detection_marks_without_delete_instruction():
    tiny = record("PART_010", 3, 0.2, 0.001, 0.1)
    result = detect_suspicious_fragment(tiny, median_faces=100, median_diagonal=20)

    assert result["suspected_fragment"] is True
    assert result["part_id"] == "PART_010"
    assert result["reason"]


def test_complexity_thresholds_are_explicit():
    assert classify_complexity(10, 100, 200) == "TRIVIAL"
    assert classify_complexity(100, 100, 200) == "SIMPLE"
    assert classify_complexity(150, 100, 200) == "MODERATE"
    assert classify_complexity(201, 100, 200) == "COMPLEX"


def test_report_contains_required_sections_and_manual_checks():
    text = render_stage01_report(
        {"source_file": "fixture.stl", "faces": 12, "vertices": 8},
        [{"part_id": "PART_001", "size_class": "MAJOR", "face_count": 12}],
        {"groups": [], "group_count": 0},
        {"component_count": 1, "watertight_count": 0, "issues": []},
    )

    assert "## Source" in text
    assert "## Component recovery" in text
    assert "## Duplicate analysis" in text
    assert "## Mesh quality" in text
    assert "人工" in text
    assert set(["part_id", "source_component_index", "size_class"]).issubset(manifest_fieldnames())
```

- [ ] **Step 2: 运行测试确认失败**

运行：

```bash
python3 -m pytest -q tests/test_analyze_parts.py
```

预期：因 `scripts.analyze_parts` 不存在而失败。

- [ ] **Step 3: 实现纯分类和检测函数**

`analyze_parts.py` 提供：

```python
def classify_complexity(face_count: int, median_faces: float, p90_faces: float) -> str: ...
def classify_size(records: list[dict]) -> dict[str, str]: ...
def detect_suspicious_fragment(record: dict, median_faces: float, median_diagonal: float) -> dict: ...
def manifest_fieldnames() -> list[str]: ...
def render_stage01_report(source_report, records, duplicate_report, quality_report) -> str: ...
```

`classify_size` 对 bbox diagonal、bbox volume、surface area、face count 做 log1p 后的 percentile rank，权重分别 0.30、0.20、0.25、0.25；若某特征缺失则把该权重按可用特征重新归一化。先运行碎片检测，疑似碎片的 size class 固定为 `FRAGMENT`；其他分数按 0.75/0.40/0.15 分为 MAJOR/MEDIUM/SMALL/TINY。至少把 thresholds 和 feature weights 保存到报告 metadata。

`detect_suspicious_fragment` 实现 `face_count <= 10` 或“低于 `max(10, round(0.01*median_faces))` 且 diagonal 不超过 `0.01*median_diagonal`”两条理由；返回 record 的浅副本和 reason，不删除原记录。

- [ ] **Step 4: 运行测试确认通过**

运行：

```bash
python3 -m pytest -q tests/test_analyze_parts.py
```

预期：5 tests passed。

- [ ] **Step 5: 实现文件生成和质量诊断**

加入以下 CLI/写入函数：

```python
def build_part_records(source_report: dict) -> tuple[list[dict], dict]: ...
def build_mesh_quality_report(source_report: dict) -> dict: ...
def write_manifest_csv(path: Path, records: list[dict]) -> None: ...
def write_manifest_json(path: Path, records: list[dict]) -> None: ...
def write_suspicious_fragments(path: Path, records: list[dict]) -> None: ...
def write_mesh_quality_report(path: Path, report: dict) -> None: ...
def main(argv: Sequence[str] | None = None) -> int: ...
```

CSV 字段固定为 `part_id`, `source_component_index`, `face_count`, `vertex_count`, `bbox_x_mm`, `bbox_y_mm`, `bbox_z_mm`, `bbox_volume_mm3`, `centroid_x_mm`, `centroid_y_mm`, `centroid_z_mm`, `surface_area_mm2`, `volume_mm3`, `volume_valid`, `watertight`, `euler_number`, `complexity_class`, `size_class`, `duplicate_group`, `duplicate_confidence`, `suspected_fragment`, `notes`；JSON 保留嵌套 bbox/centroid 并包含同样的数据。CSV/JSON 对 `None` 使用空单元格/null，不把无效体积写成 0。

`component_metrics` 同步计算并保留每个 component 的 `boundary_edge_count`、`non_manifold_edge_count`、`duplicate_face_count`、`winding_consistent`；`build_mesh_quality_report` 只聚合这些已经计算的事实，记录总组件数、watertight/non-watertight 数量、`metric_errors` 和逐 component 诊断。若某 API 不可用则写 null 和 error。任何检查都不得调用 repair。

Stage 01 markdown 报告包含源信息、class 数量、前 20 个 duplicate group 数据、quality 摘要、最大 15 个 PART（按 bbox volume/face count）和固定的 5 条人工确认问题。

- [ ] **Step 6: 运行模块测试确认通过**

运行：

```bash
python3 -m pytest -q tests/test_analyze_parts.py tests/test_analyze_stl.py
```

预期：7 tests passed。

- [ ] **Step 7: 提交**

```bash
git add scripts/analyze_parts.py tests/test_analyze_parts.py
git commit -m "feat: generate parts manifest and mesh quality reports"
```

## Task 5: 实现容差 duplicate grouping 并回写 manifest

**Files:**

- Create: `scripts/detect_duplicate_parts.py`
- Create: `tests/test_duplicates.py`

- [ ] **Step 1: 写失败测试覆盖旋转尺寸、容差和保留独立 PART**

`tests/test_duplicates.py` 写入：

```python
from scripts.detect_duplicate_parts import (
    geometry_signature,
    group_duplicate_parts,
    apply_duplicate_groups,
)


def part(part_id, dims, faces=100, vertices=80, area=50.0, volume=10.0):
    return {
        "part_id": part_id,
        "bbox_dimensions": dims,
        "face_count": faces,
        "vertex_count": vertices,
        "surface_area": area,
        "volume": volume,
        "volume_valid": True,
        "watertight": True,
        "centroid": [float(part_id[-3:]), 0.0, 0.0],
    }


def test_geometry_signature_sorts_bbox_dimensions():
    assert geometry_signature(part("PART_001", [10, 5, 20]))[0] == (5.0, 10.0, 20.0)
    assert geometry_signature(part("PART_002", [20, 10, 5]))[0] == (5.0, 10.0, 20.0)


def test_group_duplicate_parts_uses_requested_tolerances_and_keeps_members():
    records = [
        part("PART_001", [10, 5, 20]),
        part("PART_002", [10.04, 5, 20], area=50.4, volume=10.05),
        part("PART_003", [10.3, 5, 20]),
        part("PART_004", [2, 2, 2], faces=12, vertices=8, area=24, volume=8),
    ]

    groups = group_duplicate_parts(records)

    assert len(groups) == 1
    assert groups[0]["group_id"] == "DG_001"
    assert groups[0]["parts"] == ["PART_001", "PART_002"]
    assert groups[0]["quantity"] == 2
    assert groups[0]["confidence"] == "HIGH"
    assert "PART_003" not in groups[0]["parts"]


def test_apply_duplicate_groups_does_not_remove_or_join_records():
    records = [part("PART_001", [10, 5, 20]), part("PART_002", [10, 5, 20])]
    updated, report = apply_duplicate_groups(records)

    assert [record["part_id"] for record in updated] == ["PART_001", "PART_002"]
    assert {record["duplicate_group"] for record in updated} == {"DG_001"}
    assert report["group_count"] == 1


def test_missing_volume_cannot_receive_high_confidence():
    records = [part("PART_001", [10, 5, 20], volume=None), part("PART_002", [10, 5, 20], volume=None)]
    records[0]["volume_valid"] = False
    records[1]["volume_valid"] = False

    _, report = apply_duplicate_groups(records)

    assert report["groups"][0]["confidence"] == "MEDIUM"
```

- [ ] **Step 2: 运行测试确认失败**

运行：

```bash
python3 -m pytest -q tests/test_duplicates.py
```

预期：因 `scripts.detect_duplicate_parts` 不存在而失败。

- [ ] **Step 3: 实现 signature、容差匹配和分组**

接口：

```python
def geometry_signature(record: dict) -> tuple: ...
def records_match(left: dict, right: dict) -> tuple[bool, str, list[str]]: ...
def group_duplicate_parts(records: list[dict]) -> list[dict]: ...
def apply_duplicate_groups(records: list[dict]) -> tuple[list[dict], dict]: ...
```

尺寸使用 `sorted([x,y,z])`；单个尺寸判定为 `abs(a-b) <= max(0.1, 0.005*max(abs(a), abs(b), 1.0))`，面积和合法体积使用 1% relative tolerance，face/vertex count exact，watertight exact。先按 exact discrete fields（面、顶点、watertight）分桶，再做容差匹配，避免 O(n²) 扫完整模型；小桶内按 PART ID 顺序、连通分量方式建立组。只有至少两个成员的组输出。

`HIGH` 需要尺寸、面、顶点、面积、合法体积、watertight 全部满足；体积缺失或仅部分连续特征可匹配时为 `MEDIUM`。`DG_*` 按每组最小 PART 排序重新编号。更新后的 records 保持原顺序和原 object 数，不 Join、不删除。

- [ ] **Step 4: 运行测试确认通过**

运行：

```bash
python3 -m pytest -q tests/test_duplicates.py
```

预期：4 tests passed。

- [ ] **Step 5: 加入 CLI 和 manifest 回写**

CLI 读取 `data/parts_manifest.json`，生成 `data/duplicate_groups.json`，覆盖写入 JSON/CSV 的 `duplicate_group` 和 `duplicate_confidence` 字段；写入 `tolerances`、`group_count`、每组 representative signature。若 manifest 缺少必需字段，打印字段名和退出 2。

- [ ] **Step 6: 运行全 Python 单测并提交**

运行：

```bash
python3 -m pytest -q tests
```

预期：至少 17 tests passed，0 failed。

```bash
git add scripts/detect_duplicate_parts.py tests/test_duplicates.py
git commit -m "feat: detect tolerant duplicate geometry groups"
```

## Task 6: 实现 Blender 导入、Loose Parts 映射、Collection 和初始装配数据

**Files:**

- Create: `scripts/import_and_split_blender.py`
- Create: `scripts/inspect_part.py`
- Create: `tests/test_blender_script_contract.py`

- [ ] **Step 1: 写不依赖 Blender 的脚本契约测试**

`tests/test_blender_script_contract.py` 写入：

```python
from pathlib import Path


def test_blender_script_declares_required_stage01_markers():
    text = Path("scripts/import_and_split_blender.py").read_text(encoding="utf-8")

    for marker in ("DEVICE", "SUSPECTED_FRAGMENT", "source_component_index", "original_stl", "LOOSE"):
        assert marker in text


def test_inspection_script_accepts_part_id_argument():
    text = Path("scripts/inspect_part.py").read_text(encoding="utf-8")
    assert "PART_" in text
    assert "frame_selected" in text or "frame_set" in text
```

- [ ] **Step 2: 运行测试确认失败**

运行：

```bash
python3 -m pytest -q tests/test_blender_script_contract.py
```

预期：因两个 Blender 脚本不存在而失败。

- [ ] **Step 3: 实现 Blender 脚本**

脚本以命令行参数接收 `--source`, `--manifest`, `--output`, `--assembly-output`, `--log`。执行顺序固定为：清空当前场景 → 导入 STL（优先 `bpy.ops.wm.stl_import`, 回退 `bpy.ops.import_mesh.stl`）→ 找到导入对象 → `bpy.ops.mesh.separate(type='LOOSE')` → 读取每个新 object 的 mesh 事实 → 与 manifest 记录按 `(face_count, vertex_count, sorted bbox dimensions, area, valid volume)` 容差匹配，并用 centroid/原始对象 index 处理同几何多实例 → 显式歧义时报错并退出非零。

不调用 `bpy.ops.mesh.remove_doubles`、`bpy.ops.object.modifier_add`、decimate、remesh、boolean、fill holes、smooth 或任何 mesh repair。映射成功后：

```python
obj.name = record["part_id"]
obj["part_id"] = record["part_id"]
obj["source_component_index"] = record["source_component_index"]
obj["bbox_x"] = record["bbox_x_mm"]
obj["bbox_y"] = record["bbox_y_mm"]
obj["bbox_z"] = record["bbox_z_mm"]
obj["face_count"] = record["face_count"]
obj["vertex_count"] = record["vertex_count"]
obj["duplicate_group"] = record.get("duplicate_group", "")
obj["suspected_fragment"] = bool(record["suspected_fragment"])
obj["source"] = "original_stl"
```

创建 `DEVICE` 和五个子 Collection；每个 object 从导入 Collection unlink 后 link 到唯一分类 Collection。颜色通过 `sha256(part_id)` 的前 3 个 byte 产生稳定 RGBA，写入 `obj.color`/`show_transparent`，不创建 Material。

Origin 操作先保存 `matrix_world`，把 origin 设置到 mesh 的几何 centroid，再通过恢复 matrix 或等价的 local vertex translation 补偿，使每个顶点的世界坐标变化最大值低于 `1e-6`。输出 `assembly_initial.json` 包含 location/rotation_euler/scale、world_matrix、bbox、PART ID。即使 Blender 不可用，Python 阶段也必须先写该文件：每个 PART 使用 manifest 的 geometry centroid 和 identity rotation/scale，并标记 `transform_source: "stl_identity_inference"`；Blender 成功后用实际对象矩阵覆盖并标记 `transform_source: "blender_scene"`。保存 Blend 后重新统计对象总 bbox，并把 mismatch 写到日志。

`inspect_part.py --part PART_037` 在 Blender 内查找对象，选择并 frame selected，打印 custom properties、bbox、面数、duplicate group；`--isolate` 时只隐藏其他对象，不保存修改后的场景。

- [ ] **Step 4: 运行脚本契约测试确认通过**

运行：

```bash
python3 -m pytest -q tests/test_blender_script_contract.py
```

预期：2 tests passed。

- [ ] **Step 5: 提交**

```bash
git add scripts/import_and_split_blender.py scripts/inspect_part.py tests/test_blender_script_contract.py
git commit -m "feat: create Blender loose-parts stage01 scene"
```

## Task 7: 实现总 orchestrator、日志和报告闭环

**Files:**

- Modify: `run_stage01.py`
- Modify: `scripts/analyze_parts.py`
- Create: `tests/test_run_stage01_pipeline.py`

- [ ] **Step 1: 写失败测试覆盖 Blender 不可用时的明确部分成功**

`tests/test_run_stage01_pipeline.py` 写入：

```python
import json

import trimesh

from run_stage01 import run_python_stage, write_stage_log


def test_python_stage_writes_reports_and_marks_blender_unavailable(tmp_path, monkeypatch):
    mesh = trimesh.creation.box(extents=[2, 2, 2])
    source = tmp_path / "device.stl"
    mesh.export(source)
    (tmp_path / "source").mkdir()
    source_in_source = tmp_path / "source" / "device.stl"
    source_in_source.write_bytes(source.read_bytes())

    monkeypatch.setattr("run_stage01.find_blender", lambda explicit=None: None)
    result = run_python_stage(tmp_path, blender_path=None)

    assert result["python_exit_code"] == 0
    assert result["blender_status"] == "not_found"
    assert (tmp_path / "data/source_model_report.json").exists()
    assert (tmp_path / "data/parts_manifest.csv").exists()
    assert (tmp_path / "data/duplicate_groups.json").exists()
    assert "BLENDER_NOT_FOUND" in (tmp_path / "logs/stage01.log").read_text(encoding="utf-8")


def test_write_stage_log_includes_part_and_stage_context(tmp_path):
    log = tmp_path / "logs/stage01.log"
    log.parent.mkdir()

    write_stage_log(log, "WARNING", "duplicate mapping", part_id="PART_007", stage="blender")

    text = log.read_text(encoding="utf-8")
    assert "PART_007" in text
    assert "blender" in text
    assert "duplicate mapping" in text
```

- [ ] **Step 2: 运行测试确认失败**

运行：

```bash
python3 -m pytest -q tests/test_run_stage01_pipeline.py
```

预期：因 orchestrator 函数尚未实现而失败。

- [ ] **Step 3: 实现 pipeline orchestration**

`run_stage01.py` 实现：

```python
def write_stage_log(path: Path, level: str, message: str, *, part_id: str | None = None, stage: str | None = None) -> None: ...
def copy_root_source_if_needed(project_root: Path, selected: Path) -> Path: ...
def run_python_stage(project_root: Path, blender_path: Path | None) -> dict: ...
def find_blender(explicit: str | None = None) -> Path | None: ...
def run_blender_stage(project_root: Path, blender_path: Path, source_file: Path) -> int: ...
def main(argv: Sequence[str] | None = None) -> int: ...
```

Python 阶段在 Blender 不可用时也写入 `data/assembly_initial.json`：每个 PART 使用其几何质心作为推定 origin/location、Euler rotation `[0, 0, 0]`、scale `[1, 1, 1]` 和 identity world matrix，并标记 `transform_source: "stl_identity_inference"`；Blender 可用时以实际保存场景的 world matrix 覆盖并验证该文件。这样无论 Blender 是否存在，都不会缺少装配基础数据，同时会明确区分推定值和 Blender 实测值。

流程严格调用：

```text
ensure dirs
→ choose source
→ copy root source to source/ if source/ has no equivalent
→ analyze_stl.py logic
→ analyze_parts.py logic
→ detect_duplicate_parts.py logic
→ render stage01_report.md
→ find Blender (BLENDER_PATH > explicit CLI > PATH > /Applications/Blender.app/Contents/MacOS/Blender)
→ if found run headless Blender script
→ if absent log BLENDER_NOT_FOUND and return status 2 only for the Blender substep
```

Python report steps失败时返回 1；Blender 缺失时保留 Python outputs、顶层返回 2，并且不创建 `.blend`。Blender subprocess 非零时把 stdout/stderr 和 output path 写入日志。日志每次运行写 UTC/本地开始时间、source SHA-256、依赖版本、每阶段耗时、组件数、重复组数、碎片数、Blender 状态和 warnings/errors；敏感路径之外不隐藏异常。

- [ ] **Step 4: 运行 pipeline 单测确认通过**

运行：

```bash
python3 -m pytest -q tests/test_run_stage01_pipeline.py
```

预期：2 tests passed。

- [ ] **Step 5: 运行全部 Python 测试确认通过**

运行：

```bash
python3 -m pytest -q tests
```

预期：至少 25 tests passed，0 failed。

- [ ] **Step 6: 提交**

```bash
git add run_stage01.py scripts/analyze_parts.py tests/test_run_stage01_pipeline.py
git commit -m "feat: orchestrate repeatable stage01 pipeline"
```

## Task 8: 安装依赖并对真实 STL 做 Stage 01 生成

**Files:**

- Create: `modeling/.venv/`（不提交）
- Create: `source/智能地震仪-221128(1).STL`（根文件只读副本）
- Generate: `data/*`, `output/reports/stage01_report.md`, `logs/stage01.log`
- Generate: `data/assembly_initial.json`; additionally generate `output/stage01_split.blend` when Blender is available

- [ ] **Step 1: 建立本地虚拟环境并安装固定依赖**

运行：

```bash
python3 -m venv /Users/xiwei/modeling/.venv
/Users/xiwei/modeling/.venv/bin/python -m pip install --upgrade pip
/Users/xiwei/modeling/.venv/bin/pip install -r /Users/xiwei/modeling/requirements.txt
```

安装失败时记录完整错误，先不触碰源 STL；网络/权限阻塞应按环境审批重新执行，不改用系统级安装。

- [ ] **Step 2: 先运行全部单测**

运行：

```bash
/Users/xiwei/modeling/.venv/bin/python -m pytest -q /Users/xiwei/modeling/tests
```

预期：所有 Python tests passed，0 failed。

- [ ] **Step 3: 用真实 STL 运行 Python 阶段**

运行：

```bash
cd /Users/xiwei/modeling
env -u BLENDER_PATH /Users/xiwei/modeling/.venv/bin/python run_stage01.py --skip-blender
```

检查：

```bash
sha256sum "智能地震仪-221128(1).STL" source/"智能地震仪-221128(1).STL"
/Users/xiwei/modeling/.venv/bin/python -m json.tool data/source_model_report.json >/dev/null
/Users/xiwei/modeling/.venv/bin/python -m json.tool data/parts_manifest.json >/dev/null
```

源副本 hash 必须一致；报告的 component 总数、面数、bounds 和文件 hash 需与日志一致。

- [ ] **Step 4: 查找或安装 Blender CLI**

按顺序执行：

```bash
command -v blender
find /Applications /opt/homebrew/Caskroom -maxdepth 5 -type f -path '*Blender*/Contents/MacOS/Blender' -print 2>/dev/null
```

若没有可用 binary，按用户已授权范围尝试：

```bash
brew install --cask blender
```

再以 `blender --version` 验证；不下载或替换源 STL。

- [ ] **Step 5: 用 headless Blender 生成最终场景**

运行：

```bash
cd /Users/xiwei/modeling
BLENDER_PATH="<verified blender binary>" /Users/xiwei/modeling/.venv/bin/python run_stage01.py
```

验收命令：

```bash
test -s output/stage01_split.blend
/Users/xiwei/modeling/.venv/bin/python -m json.tool data/assembly_initial.json >/dev/null
rg -n "BLENDER|components|duplicate|fragment|ERROR|WARNING" logs/stage01.log output/reports/stage01_report.md
```

若 Blender 确实不可用，保留 Python 阶段全部 outputs，日志必须有 `BLENDER_NOT_FOUND`，最终报告明确 `.blend` 未生成；不得创建空壳 `.blend`。

- [ ] **Step 6: 做源安全和生成物一致性核对**

运行：

```bash
sha256sum "智能地震仪-221128(1).STL" source/"智能地震仪-221128(1).STL"
git status --short
```

源 hash 必须保持不变；生成 data/output/logs 可以是未跟踪产物，`.venv`、`.DS_Store` 加入 `.gitignore`，不得将 21 MB STL 或 `.blend` 强制加入 commit。

## Task 9: 真实结果审阅、代码复核和最终验证

**Files:**

- Modify if required: `scripts/*.py`, `tests/*.py`, `output/reports/stage01_report.md`
- Create: no new Stage 02 assets

- [ ] **Step 1: 逐项对照用户验收标准**

从 JSON/CSV/日志/Blend 读取并记录：

1. 源 STL hash/size/bounds/faces/vertices；
2. connected component 总数；
3. MAJOR/MEDIUM/SMALL/TINY/FRAGMENT 数量；
4. suspicious fragments 数量；
5. duplicate group 数量；
6. 最大 15 个 PART；
7. 最大 15 个 duplicate groups；
8. watertight/non-watertight 和主要质量问题；
9. `stage01_split.blend` 是否真实存在并可被 Blender headless 打开；
10. 进入 Stage 02 前最需要人工确认的 5 个问题。

- [ ] **Step 2: 对真实输出做独立只读核验**

运行：

```bash
/Users/xiwei/modeling/.venv/bin/python -m pytest -q /Users/xiwei/modeling/tests
/Users/xiwei/modeling/.venv/bin/python -m json.tool /Users/xiwei/modeling/data/source_model_report.json >/dev/null
/Users/xiwei/modeling/.venv/bin/python -m json.tool /Users/xiwei/modeling/data/parts_manifest.json >/dev/null
/Users/xiwei/modeling/.venv/bin/python -m json.tool /Users/xiwei/modeling/data/duplicate_groups.json >/dev/null
/Users/xiwei/modeling/.venv/bin/python -m json.tool /Users/xiwei/modeling/data/suspicious_fragments.json >/dev/null
/Users/xiwei/modeling/.venv/bin/python -m json.tool /Users/xiwei/modeling/data/mesh_quality_report.json >/dev/null
```

另外检查 CSV 行数等于 JSON records 数量、PART ID 唯一且连续、每个 duplicate member 存在于 manifest、fragment records 存在于 manifest、所有生成对象 custom property 与 manifest 一致。

- [ ] **Step 3: 请求代码复核并处理问题**

在最终声称完成前，按 `requesting-code-review` 流程读取当前 diff，重点复核：源 STL 是否只读、是否存在隐式 repair、PART 稳定性、Blender world matrix、重复组是否误合并、失败是否显式记录。Critical/Important 问题先修复并重跑受影响测试和真实管线；Minor 问题记录在最终报告。

- [ ] **Step 4: 使用 verification-before-completion 做最终验证**

运行完整命令：

```bash
cd /Users/xiwei/modeling
/Users/xiwei/modeling/.venv/bin/python -m pytest -q tests
/Users/xiwei/modeling/.venv/bin/python run_stage01.py
sha256sum "智能地震仪-221128(1).STL" source/"智能地震仪-221128(1).STL"
test -s output/reports/stage01_report.md
```

读取退出码和完整输出后，只有在证据满足对应断言时才汇报成功；若 Blender 不可用，按实际状态报告 Python 阶段完成、Blender 阶段未完成，并给出日志证据。

- [ ] **Step 5: 提交可复现脚本和文档**

```bash
git add AGENTS.md requirements.txt run_stage01.py scripts tests docs/superpowers/plans/2026-09-07-stl-stage01-implementation.md .gitignore
git commit -m "feat: complete STL stage01 recovery pipeline"
```

不要提交 `source/*.STL`、`.venv/`、`output/*.blend` 或 `.DS_Store`，除非后续明确要求把二进制产物纳入版本控制；最终交付仍提供这些文件的本地路径。
