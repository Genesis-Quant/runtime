"""验证生成 DOS 的固定章节结构。"""

import re
from pathlib import Path

import pytest

from core.dolphindb.script import OUTPUT_DIR, SCRIPT_PATH, build_script, write_script
from core.operators import Derivative


ORDER_CASES = (
    ("use ta", "// 工具函数"),
    ("// 工具函数", "// DIRECT operators"),
    ("// DIRECT operators", "// TS operators"),
    ("// TS operators", "// CS operators"),
    ("// CS operators", "// derive"),
    ("def divide_or_null(", "def direct_binary_div("),
    ("def rolling_min_periods(", "def ts_unary_rolling_mean("),
    ("def cross_section_rank(", "def cs_unary_rank("),
    ("def direct_binary_add(", "def direct_unary_year("),
    ("def ts_binary_cross_above(", "def ts_unary_shift("),
    ("def cs_binary_alpha(", "def cs_unary_zscore("),
    ("def evaluate_definition(", "def evaluate_operand("),
    ("def evaluate_operand(", "def evaluate_fields("),
    ("def evaluate_fields(", "def evaluate_direct("),
    ("def evaluate_direct(", "def evaluate_time_series("),
    ("def evaluate_time_series(", "def evaluate_cross_section("),
    ("def evaluate_cross_section(", "def evaluate_node("),
    ("def evaluate_node(", "def parse_definitions("),
    ("def parse_definitions(", "def compute_factors("),
)

SECTION_COMMENTS = (
    "// 提供数据形态、数值、窗口、截面及执行上下文使用的共享函数。",
    "// 仅根据 fields 与 params 逐行计算，不读取 code、time 或 on。",
    "// 在单个 code 的有序时序内计算，分组、筛选和回填由 derive 负责。",
    "// 在单个交易日的截面内计算，筛选、分组和回填由 derive 负责。",
    "// 递归解析 DSL、缓存命名因子，并统一处理 on、分组、排序及结果回填。",
)

COMPLEX_OPERATOR_EXAMPLE_MINIMUMS = {
    "controls.neutralize_by": 7,
    "talib.aroon": 6,
    "talib.bBands": 7,
    "talib.ma": 10,
    "talib.macd": 5,
    "unary.cast": 9,
    "unary.decay_linear": 4,
    "unary.ewm_mean": 8,
    "unary.ewm_std": 10,
    "unary.ewm_var": 10,
    "unary.rank": 6,
    "unary.rolling_rank": 7,
    "unary.rolling_rank_pct": 7,
}


@pytest.mark.parametrize(("earlier", "later"), ORDER_CASES)
def test_generated_script_order(earlier: str, later: str) -> None:
    """章节和章节内函数必须按可读且可执行的顺序生成。"""
    script = build_script()

    assert script.index(earlier) < script.index(later)


FUNCTION_PREFIXES = (
    "direct_",
    "ts_",
    "cs_",
    "evaluate_",
    "compute_",
    "apply_",
    "require_",
    "rolling_",
    "cross_section_",
    "cast_",
)


@pytest.mark.parametrize("prefix", FUNCTION_PREFIXES)
def test_generated_script_has_no_forward_declaration(prefix: str) -> None:
    """每类函数都只能出现带函数体的完整定义。"""
    lines = [
        line.strip()
        for line in build_script().splitlines()
        if line.startswith(f"def {prefix}")
    ]

    assert lines
    assert all(line.endswith("{") for line in lines)


@pytest.mark.parametrize("comment", SECTION_COMMENTS)
def test_generated_script_describes_each_section(comment: str) -> None:
    """每个 DOS 章节标题后都必须包含用途说明。"""
    assert comment in build_script()


def test_generated_script_uses_named_form_predicates() -> None:
    """数据形态判断不得直接比较 DolphinDB 的数字编号。"""
    pattern = re.compile(r"form\([^\r\n]+\)\s*(?:==|!=)\s*\d+")

    assert pattern.search(build_script()) is None


def test_every_generated_function_has_a_body_comment() -> None:
    """生成到 DOS 的每个函数都必须在函数体开头说明用途。"""
    script = build_script()
    functions = tuple(
        re.finditer(r"^def\s+([A-Za-z_][A-Za-z0-9_]*)\s*\([^)]*\)\s*\{", script, re.MULTILINE)
    )

    assert functions
    for function in functions:
        body = script[function.end() :].lstrip()
        assert body.startswith(("//", "/*")), function.group(1)


def test_generated_script_documents_every_operator() -> None:
    """每个算符函数体都必须直接维护完整的 DataFrame API 风格文档。"""
    script = build_script()

    for operation, model in Derivative.operators.items():
        definition = model.function.definition
        body = definition[definition.index("{") + 1 :].lstrip()
        documentation = body[2 : body.index("*/")]

        assert body.startswith("/*"), operation
        assert "Parameters\n" in documentation, operation
        assert "----------\n" in documentation, operation
        assert "Returns\n" in documentation, operation
        assert "-------\n" in documentation, operation
        assert "Examples\n" in documentation, operation
        assert ">>> " in documentation, operation
        for name in model.function.parameters:
            assert re.search(rf"^\s*{re.escape(name)}\s*:", documentation, re.MULTILINE), operation
        assert definition in script, operation


def test_complex_operators_have_enough_examples() -> None:
    """多参数、多模式算符必须用足量示例覆盖主要行为分支。"""
    for operation, minimum in COMPLEX_OPERATOR_EXAMPLE_MINIMUMS.items():
        definition = Derivative.operators[operation].function.definition
        function_name = Derivative.operators[operation].function.name
        calls = re.findall(rf"^\s*>>>.*\b{re.escape(function_name)}\(", definition, re.MULTILINE)

        assert len(calls) >= minimum, operation


def test_operator_docs_are_not_generated_outside_functions() -> None:
    """生成脚本不得在函数外另行拼接算符文档。"""
    script = build_script()

    for operation in Derivative.operators:
        assert f"// {operation}\n" not in script


def test_generated_script_file_is_current() -> None:
    """仓库中的 DOS 文件必须与当前生成结果一致。"""
    assert Path(SCRIPT_PATH).read_text(encoding="utf-8") == build_script()


def test_default_script_path_uses_output_directory() -> None:
    """默认生成文件必须位于项目根目录的 output 文件夹。"""
    assert SCRIPT_PATH == OUTPUT_DIR / "operators.dos"
    assert OUTPUT_DIR == Path(__file__).parents[1] / "output"


def test_write_script_creates_parent_directory(tmp_path: Path) -> None:
    """写入自定义位置时应自动创建尚不存在的父目录。"""
    path = tmp_path / "nested" / "operators.dos"

    assert write_script(path) == path
    assert path.read_text(encoding="utf-8") == build_script()
