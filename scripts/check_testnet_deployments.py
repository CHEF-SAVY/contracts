#!/usr/bin/env python3
"""Check that testnet deployment contract instances are present in live RPC state."""

import argparse
import base64
import binascii
import json
import os
import re
import struct
import sys
from pathlib import Path
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen


DEFAULT_DEPLOYMENTS = Path(__file__).resolve().parent.parent / "DEPLOYMENTS.md"
CONTRACT_ID_RE = re.compile(r"^C[A-Z2-7]{55}$")


class LivenessError(Exception):
    """An RPC response or deployment entry could not be verified."""


def decode_contract_id(contract_id: str) -> bytes:
    if not CONTRACT_ID_RE.fullmatch(contract_id):
        raise LivenessError(f"Invalid Stellar contract ID: {contract_id}")

    try:
        decoded = base64.b32decode(contract_id)
    except binascii.Error as error:
        raise LivenessError(f"Invalid Stellar contract ID: {contract_id}") from error

    if (
        len(decoded) != 35
        or decoded[0] != 16
        or int.from_bytes(decoded[-2:], "little") != binascii.crc_hqx(decoded[:-2], 0)
    ):
        raise LivenessError(f"Invalid Stellar contract ID checksum: {contract_id}")
    return decoded[1:33]


def contract_instance_ledger_key(contract_id: str) -> str:
    contract_hash = decode_contract_id(contract_id)
    # LedgerKey.contractData(ScAddress.contract, SCV_LEDGER_KEY_CONTRACT_INSTANCE,
    # ContractDataDurability.persistent), encoded using XDR's big-endian integers.
    xdr = (
        struct.pack(">I", 6)
        + struct.pack(">I", 1)
        + contract_hash
        + struct.pack(">I", 20)
        + struct.pack(">I", 1)
    )
    return base64.b64encode(xdr).decode("ascii")


def load_testnet_contracts(path: Path) -> list[tuple[str, str]]:
    content = path.read_text(encoding="utf-8")
    section = re.search(
        r"^## Stellar Testnet\s*$([\s\S]*?)(?=^## |\Z)", content, re.MULTILINE
    )
    if section is None:
        raise LivenessError("No Stellar Testnet section found in deployments file")

    expected_names = {"Alert Registry", "Watcher Registry"}
    contracts = []
    for line in section.group(1).splitlines():
        row = re.match(r"^\|\s*([^|]+?)\s*\|\s*`([^`]+)`\s*\|", line)
        if row is None:
            continue
        name, contract_id = row.groups()
        name = name.strip()
        if name not in expected_names:
            continue
        if any(existing_name == name for existing_name, _ in contracts):
            raise LivenessError(f"Duplicate {name} row in testnet deployments")
        if "XXXX" in contract_id:
            continue
        decode_contract_id(contract_id)
        contracts.append((name, contract_id))
    missing_names = expected_names - {name for name, _ in contracts}
    if missing_names:
        raise LivenessError(
            "Missing valid testnet contract address(es): "
            + ", ".join(sorted(missing_names))
        )
    return contracts


def rpc_call(rpc_url: str, method: str, params: dict | None = None) -> dict:
    payload = {"jsonrpc": "2.0", "id": 1, "method": method}
    if params is not None:
        payload["params"] = params
    request = Request(
        rpc_url,
        data=json.dumps(payload).encode("utf-8"),
        headers={"Content-Type": "application/json"},
        method="POST",
    )
    with urlopen(request, timeout=30) as response:
        data = json.loads(response.read().decode("utf-8"))
    if not isinstance(data, dict):
        raise LivenessError(f"{method} returned an invalid JSON-RPC response")
    if "error" in data:
        error = data["error"]
        message = (
            error.get("message", str(error))
            if isinstance(error, dict)
            else str(error)
        )
        raise LivenessError(f"{method} RPC error: {message}")
    result = data.get("result")
    if not isinstance(result, dict):
        raise LivenessError(f"{method} returned no result")
    return result


def inactive_reason(entry: dict | None, current_ledger: int) -> str | None:
    if entry is None:
        return "instance entry is missing or archived"
    live_until = entry.get("liveUntilLedgerSeq")
    if live_until == 0:
        return "instance entry is no longer live"
    if isinstance(live_until, int) and live_until < current_ledger:
        return f"instance entry expired at ledger {live_until}"
    return None


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "deployments_file", nargs="?", type=Path, default=DEFAULT_DEPLOYMENTS
    )
    args = parser.parse_args(argv)
    rpc_url = os.environ.get("RPC_URL", "https://soroban-testnet.stellar.org")

    print("=======================================================")
    print("TxWatch Testnet Deployment Liveness Check")
    print("=======================================================")
    print(f"RPC URL:          {rpc_url}")
    print(f"Deployments File: {args.deployments_file}")
    print()

    try:
        if not args.deployments_file.is_file():
            raise LivenessError(f"Deployments file not found: {args.deployments_file}")
        contracts = load_testnet_contracts(args.deployments_file)
        if not contracts:
            raise LivenessError(
                f"No valid testnet contract addresses found in {args.deployments_file}"
            )

        print("--> Checking Soroban Testnet RPC health...")
        health = rpc_call(rpc_url, "getHealth")
        if health.get("status") != "healthy":
            raise LivenessError(f"Soroban RPC is not healthy: {health.get('status')}")
        latest_ledger = health.get("latestLedger")
        if not isinstance(latest_ledger, int) or latest_ledger <= 0:
            raise LivenessError("Soroban RPC health response has no valid latest ledger")
        print(f"    RPC is healthy. Latest ledger: {latest_ledger}")

        keys = [
            contract_instance_ledger_key(contract_id)
            for _, contract_id in contracts
        ]
        result = rpc_call(rpc_url, "getLedgerEntries", {"keys": keys})
        entries = result.get("entries")
        current_ledger = result.get("latestLedger")
        if not isinstance(entries, list) or not isinstance(current_ledger, int):
            raise LivenessError("getLedgerEntries returned an invalid result")
        entries_by_key = {
            entry.get("key"): entry for entry in entries if isinstance(entry, dict)
        }

        print(f"--> Verifying {len(contracts)} contract instance(s)...")
        failures = []
        for (name, contract_id), key in zip(contracts, keys):
            entry = entries_by_key.get(key)
            reason = inactive_reason(entry, current_ledger)
            if reason is None:
                print(f"    [LIVE] {name} ({contract_id})")
                continue
            print(f"    [STALE] {name} ({contract_id}): {reason}")
            failures.append((name, contract_id, reason))

        if failures:
            print()
            print("LIVENESS CHECK FAILED: stale or missing contract instance(s):")
            for name, contract_id, reason in failures:
                print(f"  - {name}: {contract_id} ({reason})")
            print("Redeploy the contracts and update DEPLOYMENTS.md.")
            return 1

        print()
        print("ALL TESTNET CONTRACT INSTANCES ARE LIVE")
        return 0
    except (
        LivenessError,
        HTTPError,
        URLError,
        TimeoutError,
        OSError,
        json.JSONDecodeError,
    ) as error:
        print(f"Error: {error}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    sys.exit(main())
