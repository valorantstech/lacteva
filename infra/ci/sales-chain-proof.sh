#!/usr/bin/env bash
# The receivable chain, on a real engine (DEMO-015).
#
#     ./infra/ci/sales-chain-proof.sh
#
# Finds a PostgreSQL the same way `verify-postgres.sh` does — PGHOST if you
# have one, otherwise a cluster from the `pgserver` wheel with no Docker and
# no root — migrates a throwaway database from empty, and drives
# `sales_chain_proof.py` through it.
#
# It is a separate entry point rather than a tenth step of the nine-step proof
# because it answers a different question. That proof asks whether the
# platform can be deployed and recovered; this one asks whether a dairy can
# bill a customer for a month of milk and be right about the money. Both run
# in CI; only this one leaves an Indian dairy behind to look at.
#
# KEEP_DATABASE=1 leaves it standing for inspection.
set -euo pipefail

REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
cd "${REPO_ROOT}"

note() { printf '\033[1m%s\033[0m\n' "$*"; }

PYTHON="${PYTHON:-services/platform-core/.venv/bin/python}"
[ -x "${PYTHON}" ] || PYTHON="$(command -v python3)"
PYTHON="$(cd "$(dirname "${PYTHON}")" && pwd)/$(basename "${PYTHON}")"

if [ -z "${PGHOST:-}" ]; then
  if ! "${PYTHON}" -c "import pgserver" >/dev/null 2>&1; then
    echo "no PGHOST and no pgserver wheel — install it or point PGHOST at a server" >&2
    exit 2
  fi
  note "starting a local PostgreSQL from the pgserver wheel"
  eval "$("${PYTHON}" infra/ci/local_postgres.py --print-env)"
  export PGUSER="${PGUSER:-postgres}"
fi

DB="${SALES_CHAIN_DB:-lacteva_sales_chain}"
PSQL="$(dirname "${PYTHON}")/psql"
[ -x "${PSQL}" ] || PSQL="$("${PYTHON}" -c "import pathlib,pgserver;print(pathlib.Path(pgserver.__file__).parent/'pginstall'/'bin'/'psql')")"

# A leading '/' in PGHOST is a unix SOCKET directory, not a hostname. libpq
# takes it directly; a SQLAlchemy URL has to carry it as a query parameter,
# since the authority section cannot hold a path.
if [ "${PGHOST:0:1}" = "/" ]; then
  URL_BASE="postgresql+asyncpg://${PGUSER}@/${DB}?host=${PGHOST}"
else
  URL_BASE="postgresql+asyncpg://${PGUSER}@${PGHOST}:${PGPORT:-5432}/${DB}"
fi

cleanup() {
  if [ "${KEEP_DATABASE:-0}" != "1" ]; then
    "${PSQL}" -X -q -d postgres -c "DROP DATABASE IF EXISTS ${DB}" >/dev/null 2>&1 || true
  else
    note "database ${DB} left standing (KEEP_DATABASE=1)"
  fi
}
trap cleanup EXIT

note "==> migrating ${DB} from empty"
"${PSQL}" -X -q -d postgres -c "DROP DATABASE IF EXISTS ${DB}" >/dev/null
"${PSQL}" -X -q -d postgres -c "CREATE DATABASE ${DB}" >/dev/null

cd services/platform-core
# `staging`, so the app does NOT create tables itself: the schema must come
# from Alembic, because applying the migrations from empty is part of what is
# being proven here too.
export LACTEVA_ENV=staging
export LACTEVA_DATABASE_URL="${URL_BASE}"
export LACTEVA_RELAY_ENABLED=0
export LACTEVA_CONSUMERS_ENABLED=0
"${PYTHON}" -m alembic upgrade head >/dev/null
note "    schema at head"

cd "${REPO_ROOT}"
note "==> driving the chain"
exec "${PYTHON}" infra/ci/sales_chain_proof.py "${1:-}"
