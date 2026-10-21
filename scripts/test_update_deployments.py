#!/usr/bin/env python3
"""
Unit tests for update_deployments.py.
"""

import shutil
import tempfile
import unittest
from pathlib import Path

from update_deployments import update_deployments_content

REAL_DEPLOYMENTS = Path(__file__).resolve().parent.parent / "DEPLOYMENTS.md"
CLI_VERSION = "v28.0.0"

class TestUpdateDeployments(unittest.TestCase):
    def update_copy(self, network, **kwargs):
        with tempfile.TemporaryDirectory() as temporary_directory:
            copy_path = Path(temporary_directory) / "DEPLOYMENTS.md"
            shutil.copyfile(REAL_DEPLOYMENTS, copy_path)
            content = copy_path.read_text(encoding="utf-8")
            return update_deployments_content(
                content,
                network=network,
                date_str="2026-09-24",
                cli_version=CLI_VERSION,
                **kwargs,
            )

    def assert_history_row(self, content, expected):
        self.assertIn(expected, content.splitlines())
        cells = [cell.strip() for cell in expected.strip("|").split("|")]
        self.assertEqual(len(cells), 7)

    def test_update_testnet(self):
        updated = self.update_copy(
            "testnet",
            alert_id="CALERTTESTNET123",
            watcher_id="CWATCHERTESTNET123",
            alert_hash="hash_alert_1",
            watcher_hash="hash_watcher_1",
            tag="v0.2.0",
        )
        self.assertIn("| Alert Registry | `CALERTTESTNET123` | `hash_alert_1` |", updated.splitlines())
        self.assertIn("| Watcher Registry | `CWATCHERTESTNET123` | `hash_watcher_1` |", updated.splitlines())
        self.assert_history_row(
            updated,
            "| 2026-09-24 | Testnet | Alert Registry | `CALERTTESTNET123` | `hash_alert_1` | v28.0.0 | v0.2.0 |",
        )
        self.assert_history_row(
            updated,
            "| 2026-09-24 | Testnet | Watcher Registry | `CWATCHERTESTNET123` | `hash_watcher_1` | v28.0.0 | v0.2.0 |",
        )
        self.assertIn("| — | — | — | — | — | — | Initial placeholder |", updated.splitlines())

    def test_update_mainnet(self):
        updated = self.update_copy(
            "mainnet",
            alert_id="CALERTMAINNET123",
            watcher_id="CWATCHERMAINNET123",
            alert_hash="mainnet_hash_1",
            watcher_hash="mainnet_hash_2",
            notes="Production release",
        )
        self.assertIn("| Alert Registry | `CALERTMAINNET123` | `mainnet_hash_1` |", updated.splitlines())
        self.assertIn("| Watcher Registry | `CWATCHERMAINNET123` | `mainnet_hash_2` |", updated.splitlines())
        self.assert_history_row(
            updated,
            "| 2026-09-24 | Mainnet | Alert Registry | `CALERTMAINNET123` | `mainnet_hash_1` | v28.0.0 | Production release |",
        )
        self.assert_history_row(
            updated,
            "| 2026-09-24 | Mainnet | Watcher Registry | `CWATCHERMAINNET123` | `mainnet_hash_2` | v28.0.0 | Production release |",
        )

if __name__ == "__main__":
    unittest.main()
