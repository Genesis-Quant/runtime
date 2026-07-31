from __future__ import annotations

import os
import subprocess
import sys
from pathlib import Path

RUNTIME_ROOT = Path(__file__).resolve().parents[1]

LOG_SCRIPT = """
import warnings
from core.utils.logging import logger

warnings.warn("warning-must-be-hidden")
logger.info("visible-log-message")
"""


def run_logging_script(*, prod: bool) -> subprocess.CompletedProcess[str]:
    environment = os.environ.copy()
    environment["PROD"] = "true" if prod else "false"
    return subprocess.run(
        [sys.executable, "-c", LOG_SCRIPT],
        cwd=RUNTIME_ROOT,
        env=environment,
        check=True,
        capture_output=True,
        text=True,
    )


def test_prod_disables_color_and_ignores_python_warnings():
    result = run_logging_script(prod=True)

    assert "visible-log-message" in result.stdout
    assert "\x1b[" not in result.stdout
    assert "warning-must-be-hidden" not in result.stderr


def test_non_prod_keeps_colored_log_output():
    result = run_logging_script(prod=False)

    assert "visible-log-message" in result.stdout
    assert "\x1b[" in result.stdout
    assert "warning-must-be-hidden" in result.stderr
