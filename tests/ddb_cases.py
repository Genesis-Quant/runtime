"""执行 DolphinDB 函数输入输出用例。"""

from dataclasses import dataclass
from typing import Any, Iterable


@dataclass(frozen=True, slots=True)
class DDBCase:
    """一个独立的 DolphinDB 输入输出场景。"""

    actual: str
    expected: str = "true"
    setup: str = ""


def assert_ddb_cases(
    session: Any,
    function_name: str,
    cases: Iterable[DDBCase],
) -> None:
    """逐个执行至少十个场景，并使用 eqObj 比较结果。"""
    cases = tuple(cases)
    assert len(cases) >= 10, f"{function_name} 只有 {len(cases)} 个用例"
    for index, case in enumerate(cases):
        script = "\n".join(
            part
            for part in (
                case.setup,
                f"eqObj(({case.actual}), ({case.expected}))",
            )
            if part
        )
        try:
            matched = session.run(script)
        except RuntimeError as error:
            message = str(error).split(" script:", 1)[0]
            raise AssertionError(
                f"{function_name} 用例 {index + 1} 执行失败：{message}\n{script}"
            ) from error
        assert bool(matched), (
            f"{function_name} 用例 {index + 1} 输出不符\n{script}"
        )


__all__ = ["DDBCase", "assert_ddb_cases"]
