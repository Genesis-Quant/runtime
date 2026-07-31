"""定义算符可复用的操作数字段模型。"""

from typing import Union

from pydantic import Field, SerializeAsAny

from .types import StrictModel
from .derivative import Derivative

Operand = Union[str, int, float, bool, SerializeAsAny[Derivative]]
BoolOperand = Union[str, SerializeAsAny[Derivative]]


class NullaryFields(StrictModel):
    """不接收操作数。"""


class UnaryFields(StrictModel):
    """包含一个操作数。"""

    col: Operand = Field(..., description="列名、命名因子、嵌套 DSL 或数值/布尔常量。")


class BinaryFields(StrictModel):
    """包含左右两个操作数。"""

    left: Operand = Field(
        ...,
        description="左侧列名、命名因子、嵌套 DSL 或数值/布尔常量。",
    )
    right: Operand = Field(
        ...,
        description="右侧列名、命名因子、嵌套 DSL 或数值/布尔常量。",
    )


class TernaryFields(StrictModel):
    """包含条件、真值和假值三个操作数。"""

    condition: Operand = Field(..., description="必须计算为 BOOL 的条件操作数。")
    if_true: Operand = Field(..., description="条件为 true 时返回的操作数。")
    if_false: Operand = Field(..., description="条件为 false 时返回的操作数。")


class MultiaryFields(StrictModel):
    """包含至少一个操作数。"""

    cols: list[Operand] = Field(..., min_length=1, description="参与逐行归约的操作数列表。")


class GroupedFields(StrictModel):
    """包含待计算值和截面分类键。"""

    col: Operand = Field(..., description="待执行组内截面操作的值。")
    by: Operand = Field(..., description="BOOL、SYMBOL、STRING 或离散整数分类键。")


class ControlsFields(StrictModel):
    """包含回归目标和一个或多个控制变量。"""

    target: Operand = Field(..., description="需要中性化的数值目标。")
    controls: list[Operand] = Field(..., min_length=1, description="分类或连续控制变量列表。")


class OHLCFields(StrictModel):
    """包含最高价、最低价和收盘价。"""

    high: Operand = Field(..., description="最高价。")
    low: Operand = Field(..., description="最低价。")
    close: Operand = Field(..., description="收盘价。")


class OHLCVFields(OHLCFields):
    """包含最高价、最低价、收盘价和成交量。"""

    volume: Operand = Field(..., description="成交量。")


class FullOHLCFields(StrictModel):
    """包含开盘价、最高价、最低价和收盘价。"""

    open: Operand = Field(..., description="开盘价。")
    high: Operand = Field(..., description="最高价。")
    low: Operand = Field(..., description="最低价。")
    close: Operand = Field(..., description="收盘价。")


class HighLowFields(StrictModel):
    """包含最高价和最低价。"""

    high: Operand = Field(..., description="最高价。")
    low: Operand = Field(..., description="最低价。")


class CloseVolumeFields(StrictModel):
    """包含收盘价和成交量。"""

    close: Operand = Field(..., description="收盘价。")
    volume: Operand = Field(..., description="成交量。")
