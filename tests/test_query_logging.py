from __future__ import annotations

from runtime.apps.query import api


class ProfileSession:
    def __init__(self) -> None:
        self.scripts: list[str] = []

    def run(self, script: str):
        self.scripts.append(script)
        if script == "resultTable.rows()":
            return 240
        if script == "exec count(distinct code) from resultTable where not isNull(code)":
            return 3
        raise AssertionError(f"unexpected script: {script}")


def test_log_query_output_profile_reports_server_side_counts(monkeypatch) -> None:
    session = ProfileSession()
    messages: list[str] = []
    monkeypatch.setattr(api.logger, "info", messages.append)

    api.log_query_output_profile(session, "resultTable", label="最终截面")

    assert session.scripts == [
        "resultTable.rows()",
        "exec count(distinct code) from resultTable where not isNull(code)",
    ]
    assert messages == [
        '最终截面摘要：{"rows":240,"effective_codes":3}',
    ]


def test_log_query_output_profile_rejects_script_injection() -> None:
    session = ProfileSession()

    try:
        api.log_query_output_profile(session, "resultTable;undef all")
    except ValueError as error:
        assert "不是合法的 DolphinDB 标识符" in str(error)
    else:
        raise AssertionError("非法 DolphinDB 引用未被拒绝")
