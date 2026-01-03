#!/bin/bash
set -e

# Default Evidence Path structure
EVIDENCE_DIR="/workspace/src/forensics/evidence"
MOUNT_POINT="/mnt/evidence"

echo "=== Container Boot: Starting Application ==="

# Create Local Evidence Directory
mkdir -p "$EVIDENCE_DIR"
echo "Created local evidence directory: $EVIDENCE_DIR"

echo "=== Boot Complete. Starting Application ==="
exec "$@"
