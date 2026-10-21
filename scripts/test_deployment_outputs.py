#!/usr/bin/env python3
"""Regression tests for deploy.sh output extraction."""

import unittest

from deployment_outputs import extract_deployment_outputs


class TestDeploymentOutputs(unittest.TestCase):
    def test_extracts_hashes_without_trailing_parenthesis(self):
        alert_id = "C" + "A" * 55
        watcher_id = "C" + "B" * 55
        alert_hash = "a" * 64
        watcher_hash = "b" * 64
        output = f"""\
Alert Registry deployed: {alert_id}
Watcher Registry deployed: {watcher_id}
Watcher Registry deployed: {watcher_id}
Alert Registry:   {alert_id} (WASM: {alert_hash})
Watcher Registry: {watcher_id} (WASM: {watcher_hash})
"""

        self.assertEqual(
            extract_deployment_outputs(output),
            {
                "alert_id": alert_id,
                "alert_hash": alert_hash,
                "watcher_id": watcher_id,
                "watcher_hash": watcher_hash,
            },
        )

    def test_rejects_missing_hash(self):
        with self.assertRaisesRegex(ValueError, "Alert Registry WASM hash"):
            extract_deployment_outputs(
                f"Alert Registry deployed: {'C' + 'A' * 55}\n"
                f"Watcher Registry deployed: {'C' + 'B' * 55}\n"
                f"Watcher Registry: {'C' + 'B' * 55} (WASM: {'b' * 64})\n"
            )


if __name__ == "__main__":
    unittest.main()
