import json
import unittest
from copy import deepcopy
from pathlib import Path

from pydantic import ValidationError

from runtime import BacktestParameters
from runtime.apps import BacktestParameters as AppsBacktestParameters
from runtime.apps.backtest import BacktestParameters as BacktestAppParameters


CALLBACKS = {
    "initialize": "def initialize(mutable context) { return NULL }",
    "beforeTrading": "def beforeTrading(mutable context) { return NULL }",
    "onBar": "def onBar(mutable context, message, indicator) { return NULL }",
    "onSnapshot": "def onSnapshot(mutable context, message, indicator) { return NULL }",
    "onOrder": "def onOrder(mutable context, event) { return NULL }",
    "onTrade": "def onTrade(mutable context, event) { return NULL }",
    "afterTrading": "def afterTrading(mutable context) { return NULL }",
    "finalize": "def finalize(mutable context) { return NULL }",
}


def query(codes: list[str]) -> dict:
    return {
        "start_date": "2020-01-01",
        "end_date": "2020-01-31",
        "codes": codes,
        "factors": ["close"],
    }


def parameters() -> dict:
    return {
        "codes_query": None,
        "dataset_query": query(["000001.SZ"]),
        "callbacks": deepcopy(CALLBACKS),
    }


class BacktestParametersTests(unittest.TestCase):
    def test_public_packages_export_the_same_model(self) -> None:
        self.assertIs(AppsBacktestParameters, BacktestParameters)
        self.assertIs(BacktestAppParameters, BacktestParameters)

    def test_static_stock_pool_requires_dataset_codes(self) -> None:
        payload = parameters()
        payload["dataset_query"]["codes"] = []

        with self.assertRaisesRegex(ValidationError, "dataset_query.codes 不能为空"):
            BacktestParameters.model_validate(payload)

    def test_dynamic_stock_pool_allows_empty_dataset_codes(self) -> None:
        payload = parameters()
        payload["codes_query"] = query([])
        payload["dataset_query"]["codes"] = []

        result = BacktestParameters.model_validate(payload)

        self.assertEqual(result.dataset_query.codes, [])

    def test_all_fixed_callbacks_are_required(self) -> None:
        for callback in CALLBACKS:
            with self.subTest(callback=callback):
                payload = parameters()
                del payload["callbacks"][callback]

                with self.assertRaisesRegex(ValidationError, "callbacks 缺少固定函数"):
                    BacktestParameters.model_validate(payload)

    def test_callback_definition_cannot_be_empty(self) -> None:
        payload = parameters()
        payload["callbacks"]["finalize"] = ""

        with self.assertRaisesRegex(ValidationError, "完整的 DolphinDB def 函数定义"):
            BacktestParameters.model_validate(payload)

    def test_callbacks_cannot_be_null(self) -> None:
        payload = parameters()
        payload["callbacks"] = None

        with self.assertRaisesRegex(ValidationError, "callbacks 不能为空"):
            BacktestParameters.model_validate(payload)

    def test_callbacks_are_normalized_in_lifecycle_order(self) -> None:
        payload = parameters()
        payload["callbacks"] = dict(reversed(CALLBACKS.items()))

        result = BacktestParameters.model_validate(payload)

        self.assertEqual(list(result.callbacks), list(CALLBACKS))

    def test_runtime_only_parameters_are_not_part_of_input_json(self) -> None:
        for name, value in {
            "name": "custom-engine",
            "source_ref": "customSource",
            "message_ref": "customMessage",
        }.items():
            with self.subTest(name=name):
                payload = parameters()
                payload[name] = value

                with self.assertRaises(ValidationError):
                    BacktestParameters.model_validate(payload)

    def test_benchmark_config_is_forbidden(self) -> None:
        payload = parameters()
        payload["config"] = {"benchmark": "000300.SH"}

        with self.assertRaisesRegex(
            ValidationError,
            r"当前回测不支持 config\['benchmark'\]",
        ):
            BacktestParameters.model_validate(payload)

    def test_packaged_backtest_example_matches_the_model(self) -> None:
        example = json.loads((Path(__file__).parents[1] / "examples" / "backtest.json").read_text(encoding="utf-8"))

        result = BacktestParameters.model_validate(example)

        self.assertEqual(list(result.callbacks), list(CALLBACKS))


if __name__ == "__main__":
    unittest.main()
