import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import Mock

import pandas as pd

from runtime.apps.factor.result import FactorAnalysisResult
from runtime.database.compile.factor.scripts import build_script
from runtime.manage.apps.factor import OUTPUT_FILENAMES


class FactorDiagnosticsTests(unittest.TestCase):
    def test_deployable_factor_module_matches_the_compiler(self) -> None:
        self.assertEqual(
            Path("output/factor.dos").read_text(encoding="utf-8"),
            build_script(),
        )

    def test_result_downloads_only_server_aggregated_diagnostics(self) -> None:
        expected = pd.DataFrame(
            {
                "time": pd.to_datetime(["2026-01-05"]),
                "factor": ["alpha"],
                "return_column": ["ret1"],
                "universe_count": [100],
                "factor_valid_count": [95],
                "return_valid_count": [90],
                "paired_valid_count": [88],
                "group_valid_count": [95],
                "group_min": [0],
                "group_max": [4],
                "occupied_group_count": [5],
                "min_group_size": [19],
                "max_group_size": [19],
            }
        )
        session = Mock()
        session.run.return_value = expected
        parameters = SimpleNamespace(
            factor_columns=["alpha"],
            return_columns=["ret1"],
        )
        result = FactorAnalysisResult(
            session=session,
            parameters=parameters,
            processed_ref="coreFactorProcessedData",
        )

        actual = result.diagnostics

        self.assertIs(actual, expected)
        session.run.assert_called_once()
        script = session.run.call_args.args[0]
        self.assertIn("factor::factorDiagnostics(", script)
        self.assertIn("coreFactorProcessedData", script)
        self.assertNotIn("select *", script.lower())

    def test_factor_cli_exposes_diagnostics_parquet(self) -> None:
        self.assertEqual(
            OUTPUT_FILENAMES["diagnostics"],
            "factor_diagnostics.parquet",
        )

    def test_factor_module_validates_every_non_null_group_value(self) -> None:
        script = build_script()

        self.assertIn("def factorValidateGroups(", script)
        self.assertIn(
            "numericValues != floor(numericValues)",
            script,
        )
        self.assertIn(
            "numericValues < 0 || numericValues >= nGroups",
            script,
        )
        group_returns = script.index("def factorGroupReturns(")
        validation_call = script.index(
            "factorValidateGroups(",
            group_returns,
        )
        group_loop = script.index(
            "for (factorCol in factorColNames)",
            group_returns,
        )
        self.assertLess(validation_call, group_loop)

    def test_factor_diagnostics_schema_is_stable_and_server_side(self) -> None:
        script = build_script()
        diagnostics = script[script.index("def factorDiagnostics("):]
        for column in (
            "time",
            "factor",
            "return_column",
            "universe_count",
            "factor_valid_count",
            "return_valid_count",
            "paired_valid_count",
            "group_valid_count",
            "group_min",
            "group_max",
            "occupied_group_count",
            "min_group_size",
            "max_group_size",
        ):
            self.assertIn(f"as {column}", diagnostics)
        self.assertIn("from processedFactorTable", diagnostics)
        self.assertIn(
            "eligibleGroup = groupValid && returnValid && weightValid",
            diagnostics,
        )
        self.assertGreater(
            diagnostics.index("for (retCol in returnColNames)"),
            diagnostics.index("groupValid = !isNull(groupValues)"),
        )
        self.assertGreater(
            diagnostics.index("groupValidCount = long(sum(eligibleGroup))"),
            diagnostics.index("for (retCol in returnColNames)"),
        )
        self.assertIn("result.append!(table(", diagnostics)


if __name__ == "__main__":
    unittest.main()
