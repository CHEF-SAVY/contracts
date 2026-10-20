#!/usr/bin/env bash
# Generate the watcher client without overwriting the curated npm package.
set -euo pipefail

if [[ $# -lt 1 || $# -gt 2 ]]; then
    echo "Usage: $0 WASM_FILE [CONTRACT_ID]" >&2
    exit 2
fi

WASM_FILE="$1"
CONTRACT_ID="${2:-}"
OUTPUT_DIR="$(mktemp -d)"
trap 'rm -rf -- "$OUTPUT_DIR"' EXIT

args=(
    stellar contract bindings typescript
    --wasm "$WASM_FILE"
    --output-dir "$OUTPUT_DIR"
    --overwrite
)
if [[ -n "$CONTRACT_ID" ]]; then
    args+=(--contract-id "$CONTRACT_ID")
fi
"${args[@]}"

GENERATED_CLIENT="$OUTPUT_DIR/src/watcher_registry.ts"
if [[ ! -f "$GENERATED_CLIENT" ]]; then
    echo "Error: Stellar CLI did not generate $GENERATED_CLIENT." >&2
    exit 1
fi

cp "$GENERATED_CLIENT" bindings/watcher-registry/src/watcher_registry.ts
