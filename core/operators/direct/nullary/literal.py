"""nullary.literal 算符模型。"""

from datetime import datetime
import re
from typing import ClassVar, Literal

from pydantic import Field, model_validator

from core.dolphindb import DolphinDBFunction
from core.dolphindb.common import (
    CAST_VALUE,
)

from core.operators.base import DirectOperator
from core.operators.fields import NullaryFields
from core.operators.schema import (
    JsonScalar,
    OutputKind,
    StrictModel,
)


class DirectNullaryLiteralParams(StrictModel):
    """nullary.literal 参数。"""

    value: JsonScalar = Field(..., description="需要广播的 JSON 标量。")
    dtype: Literal[
        "bool", "int", "long", "float", "double", "string", "symbol", "date", "timestamp"
    ] | None = Field(default=None, description="显式 DolphinDB 类型；字符串日期和 NULL 建议指定。")

    @model_validator(mode="after")
    def validate_literal(self) -> "DirectNullaryLiteralParams":
        """校验 NULL 和日期字面量具有可确定类型。"""
        if self.value is None and self.dtype is None:
            raise ValueError("NULL 字面量必须指定 params.dtype")
        if (
            self.value is not None
            and self.dtype in {"date", "timestamp"}
            and not isinstance(self.value, str)
        ):
            raise ValueError(f"dtype={self.dtype!r} 时 params.value 必须是字符串")
        if self.dtype == "date" and self.value is not None:
            try:
                datetime.strptime(self.value, "%Y-%m-%d")
            except ValueError as error:
                raise ValueError("dtype='date' 时 params.value 必须为 YYYY-MM-DD") from error
        if self.dtype == "timestamp" and self.value is not None:
            if re.fullmatch(
                r"\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}(?:\.\d{3})?"
                r"(?:Z|[+-]\d{2}:\d{2})?",
                self.value,
            ) is None:
                raise ValueError(
                    "dtype='timestamp' 时 params.value 必须为 "
                    "YYYY-MM-DDTHH:MM:SS 或带三位毫秒"
                )
            try:
                parsed = datetime.fromisoformat(self.value)
            except ValueError as error:
                raise ValueError("dtype='timestamp' 时 params.value 必须为 ISO 8601 时间") from error
            if parsed.tzinfo is not None:
                raise ValueError("DolphinDB TIMESTAMP 字面量不能包含时区")
        return self


class DirectNullaryLiteralOperator(DirectOperator):
    """广播一个显式类型的字面量。"""

    op: Literal['nullary.literal'] = Field(..., description='广播一个显式类型的字面量。')
    fields: NullaryFields = Field(..., description="该算符严格定义的输入字段。")
    params: DirectNullaryLiteralParams = Field(
        default_factory=DirectNullaryLiteralParams,
        description="该算符严格定义的参数。",
    )
    output_kind: ClassVar[OutputKind] = 'ANY'
    function: ClassVar[DolphinDBFunction] = DolphinDBFunction(
        """
        def direct_nullary_literal(value, dtype) {
            /*
            把 JSON 标量转换为可选的 DolphinDB 类型并返回。

            dtype 为 NULL 时保留 value 的推断类型。NULL、DATE 和 TIMESTAMP 字面量必须显式给出
            dtype，日期时间字符串在进入函数前已由模型校验格式。

            Parameters
            ----------
            value : str or int or float or bool or NULL
                待转换的 JSON 标量。
            dtype : {"bool", "int", "long", "float", "double", "string", "symbol", "date", "timestamp"} or NULL, default NULL
                目标 DolphinDB 数据类型。DATE 和 TIMESTAMP 字符串必须分别符合 yyyy-MM-dd 和 ISO 日期时间格式。

            Returns
            -------
            result : Any
                一个推断类型或 dtype 指定类型的 DolphinDB 标量。

            Notes
            -----
            NULL 处理：value 为 NULL 时必须显式指定 dtype，结果是该 DolphinDB
            类型的空标量；dtype 为 NULL 只适用于可由 value 推断类型的非空字面量。

            类型与形状：该函数返回一个标量且不负责广播。数值转换可能发生精度收窄，DATE/TIMESTAMP 字符串格式在
            Python 模型构造阶段校验。

            Examples
            --------
            整数字面量：
            >>> direct_nullary_literal(42, "int")
            42

            双精度浮点字面量：
            >>> direct_nullary_literal(3.5, "double")
            3.5

            布尔字面量：
            >>> direct_nullary_literal(true, "bool")
            true

            字符串字面量：
            >>> direct_nullary_literal("bank", "string")
            "bank"

            SYMBOL 字面量：
            >>> direct_nullary_literal("bank", "symbol")
            "bank"

            DATE 字面量：
            >>> direct_nullary_literal("2024-01-02", "date")
            2024.01.02

            TIMESTAMP 字面量：
            >>> direct_nullary_literal("2024-01-02T09:30:00", "timestamp")
            2024.01.02T09:30:00

            显式类型的 NULL：
            >>> direct_nullary_literal(NULL, "double")
            NULL
            */
            if (isNull(dtype)) return value
            return cast_value(value, dtype)
        }
        """,
        dependencies=(CAST_VALUE,)
    )
