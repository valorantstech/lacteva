#!/usr/bin/env bash
# The single command (VER-001).
#
#     ./infra/ci/verify-postgres.sh
#
# Runs the entire PostgreSQL verification pipeline — all nine proof steps —
# against a real engine, finding one in this order:
#
#   1. a PostgreSQL you already have, if PGHOST is set
#   2. Docker, via docker-compose.proof.yml (the same path CI uses)
#   3. a cluster from the `pgserver` wheel: no Docker, no daemon, no root
#
# Option 3 is why this file exists. The proof was written in CI-001 and could
# not be run in the development environment, so it never was — and three
# defects lived through four subsequent work orders because of it, including
# a binding statement that raised a syntax error on every single request. A
# verification pipeline nobody can execute is documentation.
#
# Every path runs infra/ci/postgres-proof.sh. There is one proof.
set -euo pipefail

REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
cd "${REPO_ROOT}"

note() { printf '\033[1m%s\033[0m\n' "$*"; }

# --- 1. A server that already exists -----------------------------------------
if [ -n "${PGHOST:-}" ]; then
  note "Using the PostgreSQL at PGHOST=${PGHOST}"
  exec ./infra/ci/postgres-proof.sh "$@"
fi

# --- 2. Docker ---------------------------------------------------------------
# Preferred when available: it pins the server version, so a local run and the
# CI matrix leg are the same run.
if [ "${USE_DOCKER:-auto}" != "no" ] && command -v docker >/dev/null 2>&1 \
   && docker info >/dev/null 2>&1; then
  note "Using Docker (postgres:${POSTGRES_VERSION:-16})"
  exec docker compose -f docker-compose.proof.yml run --rm proof
fi

# --- 3. The pgserver wheel ---------------------------------------------------
# Real PostgreSQL binaries from PyPI, on a unix socket in a temporary
# directory. Unprivileged, and nothing is left listening on a port.
note "No PGHOST and no usable Docker — starting a local PostgreSQL from the pgserver wheel"

PYTHON="${PYTHON:-services/platform-core/.venv/bin/python}"
[ -x "${PYTHON}" ] || PYTHON="$(command -v python3)"

if ! "${PYTHON}" -c "import pgserver" >/dev/null 2>&1; then
  echo "pgserver is not installed. Install it with:" >&2
  echo "    ${PYTHON} -m pip install pgserver" >&2
  echo "or set PGHOST to a PostgreSQL you already have." >&2
  exit 2
fi

# `--print-env` starts the cluster and emits the assignments to reach it.
eval "$("${PYTHON}" infra/ci/local_postgres.py --print-env)"
note "PostgreSQL ready on ${PGHOST}"

# The wheel's cluster has no `lacteva` role and needs none: `postgres` owns
# the schema and runs the migrations, and the proof creates the unprivileged
# ${APP_USER} it runs the isolation tests as. That separation is the point —
# see the APP_USER comment in postgres-proof.sh.
export PGUSER="${PGUSER:-postgres}"

# `uv run` is not necessarily present, and the venv above already has the
# dependencies. Let the proof call the interpreter directly.
if ! command -v uv >/dev/null 2>&1; then
  export RUN=""
  export PATH="${REPO_ROOT}/services/platform-core/.venv/bin:${PATH}"
fi

exec ./infra/ci/postgres-proof.sh "$@"
