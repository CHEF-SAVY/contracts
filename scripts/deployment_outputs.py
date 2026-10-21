#!/usr/bin/env python3
"""Extract and validate contract IDs and WASM hashes from deploy.sh output."""

import re
import sys

CONTRACTS = {
    "alert": "Alert Registry",
    "watcher": "Watcher Registry",
}


def extract_deployment_outputs(output: str) -> dict[str, str]:
    """Return GitHub output values from the human-readable deploy summary."""
    values = {}
    for key, contract in CONTRACTS.items():
        deployed_ids = re.findall(
            rf"^{re.escape(contract)} deployed: (C[A-Z2-7]{{55}})$",
            output,
            re.MULTILINE,
        )
        wasm_hashes = re.findall(
            rf"^{re.escape(contract)}:\s+C[A-Z2-7]{{55}} \(WASM: ([0-9a-f]{{64}})\)$",
            output,
            re.MULTILINE,
        )
        if not deployed_ids or len(set(deployed_ids)) != 1:
            raise ValueError(f"Expected one consistent {contract} contract ID")
        if len(wasm_hashes) != 1:
            raise ValueError(f"Expected one {contract} WASM hash")
        values[f"{key}_id"] = deployed_ids[0]
        values[f"{key}_hash"] = wasm_hashes[0]
    return values


def main() -> None:
    values = extract_deployment_outputs(sys.stdin.read())
    for key, value in values.items():
        print(f"{key}={value}")


if __name__ == "__main__":
    main()
