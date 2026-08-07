"""Stand up a real PostgreSQL with no Docker and no root (VER-001).

The PostgreSQL proof was written in CI-001 and could not be executed here:
the guidance was "install PostgreSQL or run Docker", and neither was
available. So the proof stayed a well-written script that had never run, and
the guarantees it checks stayed claims. That is exactly the condition VER-001
exists to end — and it is how three defects survived (`SET LOCAL` with a bind
parameter, the superuser bypass, and a suite of RLS tests that reimplemented
the binding they were supposed to be testing).

`pgserver` ships genuine PostgreSQL binaries — server AND client — inside a
PyPI wheel. It initialises a cluster in a directory and listens on a unix
socket, so no port, no daemon, and no privileges are involved.

    python infra/ci/local_postgres.py --print-env

prints shell assignments for PGHOST/PGUSER/PATH. `infra/ci/verify-postgres.sh`
consumes them; nothing else should need this module directly.

This is a DEVELOPMENT and VERIFICATION tool. It is not a deployment target:
there is no durability configuration, no backup schedule and no supervision
here. Production runs the server in docker-compose.production.yml.
"""

from __future__ import annotations

import argparse
import pathlib
import shlex
import sys

# Kept out of the repository tree: it holds a database cluster, not source.
DEFAULT_DATADIR = pathlib.Path("/tmp/lacteva-proof-pgdata")


def start(datadir: pathlib.Path):
    """Start (or reuse) a cluster and return the server handle.

    `cleanup_mode=None` leaves the cluster running when this process exits,
    which is what lets a shell script start the server in one command and use
    it in the next.
    """
    import pgserver

    datadir.mkdir(parents=True, exist_ok=True)
    return pgserver.get_server(datadir, cleanup_mode=None)


def bindir() -> pathlib.Path:
    import pgserver

    return pathlib.Path(pgserver.__file__).parent / "pginstall" / "bin"


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--datadir", type=pathlib.Path, default=DEFAULT_DATADIR)
    parser.add_argument(
        "--print-env",
        action="store_true",
        help="emit shell assignments for the running cluster",
    )
    args = parser.parse_args()

    try:
        server = start(args.datadir)
    except ImportError:
        print(
            "pgserver is not installed — `uv pip install pgserver`, or point\n"
            "PGHOST at a PostgreSQL you already have.",
            file=sys.stderr,
        )
        return 2

    # The socket directory IS the host: libpq treats a leading '/' as a unix
    # socket path, so nothing has to be published on a TCP port.
    socket_dir = str(args.datadir)
    # `psql()` returns the formatted table, not a bare value.
    version = server.psql("SHOW server_version").split("\n")[2].strip()

    if args.print_env:
        # The wheel's bin/ goes FIRST: the proof calls psql, pg_dump and
        # pg_restore, and those must be the client that matches this server.
        print(f"export PATH={shlex.quote(str(bindir()))}:$PATH")
        print(f"export PGHOST={shlex.quote(socket_dir)}")
        print("export PGUSER=postgres")
        print("unset PGPASSWORD")  # unix socket, trust auth — there is none
        print(f"# PostgreSQL {version} at {socket_dir}", file=sys.stderr)
    else:
        print(f"PostgreSQL {version} listening on {socket_dir}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
