#!/usr/bin/env bash
# Off-site backup replication proof (BKP-003).
#
#     ./infra/ci/offsite-proof.sh
#
# Stands up a real S3-compatible object store as a SEPARATE PROCESS with its own
# credentials and its own directory, takes a real backup of a real PostgreSQL
# seeded through the platform's own API, replicates it, then DESTROYS the local
# backup directory and recovers from the object store alone.
#
# The distinction this proves is the only one that matters for off-site backup:
# the recovery path does not touch the volume the backup came from. What it does
# NOT prove is independence from the host or the disk — same machine — and that
# limitation is stated in BACKUP.md rather than glossed.
#
# Requires a MinIO binary. Set MINIO_BIN, or drop one at
# ${OFFSITE_PROOF_DIR:-/tmp/lacteva-offsite-proof}/bin/minio:
#     curl -sSL -o bin/minio https://dl.min.io/server/minio/release/linux-amd64/minio
set -euo pipefail

REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
cd "${REPO_ROOT}"

PROOF_DIR="${OFFSITE_PROOF_DIR:-/tmp/lacteva-offsite-proof}"
MINIO_BIN="${MINIO_BIN:-${PROOF_DIR}/bin/minio}"
PYTHON="${PYTHON:-services/platform-core/.venv/bin/python}"
[ -x "${PYTHON}" ] || PYTHON="$(command -v python3)"

if [ ! -x "${MINIO_BIN}" ]; then
  echo "No MinIO binary at ${MINIO_BIN}." >&2
  echo "Set MINIO_BIN, or:" >&2
  echo "  mkdir -p ${PROOF_DIR}/bin && curl -sSL -o ${PROOF_DIR}/bin/minio \\" >&2
  echo "    https://dl.min.io/server/minio/release/linux-amd64/minio && chmod +x ${PROOF_DIR}/bin/minio" >&2
  exit 2
fi

export OFFSITE_PROOF_DIR="${PROOF_DIR}" MINIO_BIN
exec "${PYTHON}" infra/ci/offsite_proof.py
