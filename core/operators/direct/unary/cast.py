"""unary.cast 算符模型。"""

from typing import ClassVar, Literal

from pydantic import Field

from core.dolphindb import DolphinDBFunction
from core.dolphindb.common import (
    CAST_VALUE,
)

from core.operators.base import DirectOperator
from core.operators.fields import UnaryFields
from core.operators.schema import (
    OutputKind,
    StrictModel,
)


class DirectUnaryCastParams(StrictModel):
    """unary.cast 参数。"""

    dtype: Literal[
        "bool", "int", "long", "float", "double", "string", "symbol", "date", "timestamp"
    ] = Field(..., description="目标 DolphinDB 数据类型。")


class DirectUnaryCastOperator(DirectOperator):
    """转换 DolphinDB 数据类型。"""

    op: Literal['unary.cast'] = Field(..., description='转换 DolphinDB 数据类型。')
    fields: UnaryFields = Field(..., description="该算符严格定义的输入字段。")
    params: DirectUnaryCastParams = Field(
        default_factory=DirectUnaryCastParams,
        description="该算符严格定义的参数。",
    )
    output_kind: ClassVar[OutputKind] = 'ANY'
    function: ClassVar[DolphinDBFunction] = DolphinDBFunction(
        """
        def direct_unary_cast(col, dtype) {
            /*
            把输入值显式转换为指定的 DolphinDB 数据类型。

            转换失败时 DolphinDB 抛出类型错误。DATE 使用 yyyy-MM-dd 字符串，TIMESTAMP 使用 ISO 日期时间字符串。

            Parameters
            ----------
            col : scalar or vector
                待计算的标量或向量。
            dtype : {"bool", "int", "long", "float", "double", "string", "symbol", "date", "timestamp"}
                目标 DolphinDB 数据类型。DATE 和 TIMESTAMP 字符串必须分别符合 yyyy-MM-dd 和 ISO 日期时间格式。

            Returns
            -------
            result : scalar or vector
                与 col 同形状、元素转换为 dtype 指定 DolphinDB 类型的结果。

            Notes
            -----
            NULL 处理：NULL 会转换为目标 dtype 的 typed NULL，不会被转换为 0、false
            或空字符串。

            转换边界：整数转换可能截断小数，窄类型转换可能损失精度；不支持的 dtype
            会抛出异常，DATE/TIMESTAMP 不负责时区转换。

            Examples
            --------
            >>> col = 1.2 2.8 3.5

            转换为布尔值，0 为 false，非 0 为 true：
            >>> direct_unary_cast(0 1 2, "bool")
            [false, true, true]

            转换为整数：
            >>> direct_unary_cast(col, "int")
            [1, 3, 4]

            转换为长整数：
            >>> direct_unary_cast(col, "long")
            [1, 3, 4]

            转换为单精度浮点数：
            >>> direct_unary_cast(col, "float")
            [1.2, 2.8, 3.5]

            转换为双精度浮点数：
            >>> direct_unary_cast(col, "double")
            [1.2, 2.8, 3.5]

            转换为字符串：
            >>> direct_unary_cast(col, "string")
            ["1.2", "2.8", "3.5"]

            转换字符串向量为 SYMBOL：
            >>> direct_unary_cast(["bank", "tech", "bank"], "symbol")
            ["bank", "tech", "bank"]

            >>> text = ["2024-01-02", "2024-12-31"]

            解析日期字符串：
            >>> direct_unary_cast(text, "date")
            [2024.01.02, 2024.12.31]

            解析时间戳字符串：
            >>> direct_unary_cast(["2024-01-02T09:30:00", "2024-01-02T15:00:00"], "timestamp")
            [2024.01.02T09:30:00, 2024.01.02T15:00:00]
            */
            return cast_value(col, dtype)
        }
        """,
        dependencies=(CAST_VALUE,)
    )
