"""Unit tests for testnet deployment liveness checks."""

import base64
import io
import struct
import tempfile
import unittest
from contextlib import redirect_stderr
from pathlib import Path
from unittest.mock import patch

from check_testnet_deployments import (
    LivenessError,
    contract_instance_ledger_key,
    decode_contract_id,
    inactive_reason,
    main,
)


ALERT_ID = "CDSO4GGZH7KBUQYKOIQDCMCFSRYEPOVDUX7Z4IB5TWNTLT2GDRKDQOYR"
WATCHER_ID = "CCSHRYACRNVSLC5NP3V2DL6LGID57TQT2TJXVUVXBBZX6SED6N3F7X6J"


def deployment_file(path):
    path.write_text(
        "## Stellar Testnet\n"
        f"| Alert Registry | `{ALERT_ID}` | `TODO` |\n"
        f"| Watcher Registry | `{WATCHER_ID}` | `TODO` |\n",
        encoding="utf-8",
    )


class TestContractInstanceLedgerKey(unittest.TestCase):
    def test_builds_persistent_contract_instance_ledger_key(self):
        xdr = base64.b64decode(contract_instance_ledger_key(ALERT_ID))
        contract_hash = decode_contract_id(ALERT_ID)

        self.assertEqual(len(xdr), 48)
        self.assertEqual(struct.unpack(">I", xdr[:4])[0], 6)
        self.assertEqual(struct.unpack(">I", xdr[4:8])[0], 1)
        self.assertEqual(xdr[8:40], contract_hash)
        self.assertEqual(struct.unpack(">II", xdr[40:]), (20, 1))

    def test_rejects_invalid_contract_id_checksum(self):
        with self.assertRaisesRegex(LivenessError, "checksum"):
            decode_contract_id(ALERT_ID[:-1] + ("A" if ALERT_ID[-1] != "A" else "B"))

    def test_requires_instance_entry_to_be_active(self):
        self.assertIsNone(inactive_reason({"liveUntilLedgerSeq": 105}, 100))
        self.assertIn("missing or archived", inactive_reason(None, 100))
        self.assertIn("expired", inactive_reason({"liveUntilLedgerSeq": 99}, 100))
        self.assertIn("no longer live", inactive_reason({"liveUntilLedgerSeq": 0}, 100))

    def test_rpc_health_failure_fails_the_check(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "DEPLOYMENTS.md"
            deployment_file(path)
            with patch(
                "check_testnet_deployments.rpc_call",
                return_value={"status": "offline"},
            ) as rpc:
                with redirect_stderr(io.StringIO()):
                    self.assertEqual(main([str(path)]), 1)
                rpc.assert_called_once_with(
                    "https://soroban-testnet.stellar.org", "getHealth"
                )

    def test_live_contract_instance_passes_rpc_check(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "DEPLOYMENTS.md"
            deployment_file(path)
            alert_key = contract_instance_ledger_key(ALERT_ID)
            watcher_key = contract_instance_ledger_key(WATCHER_ID)
            with patch(
                "check_testnet_deployments.rpc_call",
                side_effect=[
                    {"status": "healthy", "latestLedger": 100},
                    {
                        "latestLedger": 100,
                        "entries": [
                            {"key": alert_key, "liveUntilLedgerSeq": 105},
                            {"key": watcher_key, "liveUntilLedgerSeq": 105},
                        ],
                    },
                ],
            ) as rpc:
                self.assertEqual(main([str(path)]), 0)
                self.assertEqual(rpc.call_count, 2)


if __name__ == "__main__":
    unittest.main()
