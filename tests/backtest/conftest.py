"""提供 DolphinDB Backtest 集成测试共用连接。"""

from collections.abc import Iterator
import os

import dolphindb
import pandas as pd
import pytest


@pytest.fixture(scope="session")
def ddb_session() -> Iterator[dolphindb.session]:
    """连接本机 DolphinDB，并确保回测插件按依赖顺序加载。"""
    session = dolphindb.session()
    connected = session.connect(
        os.getenv("DOLPHIN_HOST", "127.0.0.1"),
        int(os.getenv("DOLPHIN_PORT", "8848")),
        os.getenv("DOLPHIN_USERNAME", "admin"),
        os.getenv("DOLPHIN_PASSWORD", "123456"),
    )
    if not connected:
        pytest.fail("无法连接 DolphinDB，不能执行 Backtest 集成测试")

    loaded = session.run("getLoadedPlugins()")
    loaded_names = (
        set(loaded["plugin"].astype(str))
        if isinstance(loaded, pd.DataFrame) and "plugin" in loaded
        else set()
    )
    for plugin in ("MatchingEngineSimulator", "Backtest"):
        if plugin not in loaded_names:
            session.run(f'loadPlugin("{plugin}")')

    yield session
    session.close()
