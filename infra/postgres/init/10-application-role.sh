#!/bin/bash
# Create the unprivileged role the application connects as (VER-001).
#
# THE FINDING THIS EXISTS FOR
#
# A PostgreSQL SUPERUSER ignores row-level security completely. Not "unless
# forced" — `FORCE ROW LEVEL SECURITY` closes the loophole for the table
# OWNER and says nothing whatsoever about superusers.
#
# The official `postgres` image creates `POSTGRES_USER` as a superuser, and
# the application connected as it. So every policy SEC-001, SEC-002 and MT-001
# built was inert in production: enabled, forced, listed in `pg_policies`, and
# enforcing nothing. Tenant isolation was application-level only — precisely
# the dependency row-level security was introduced to remove.
#
# Nothing would have failed. `verify-deployment.sh` checked that the policies
# EXIST, and they did.
#
# THE SPLIT
#
#   ${POSTGRES_USER}       owns the schema. Runs migrations, backups, restores.
#                          Superuser, and stays that way — DDL needs it.
#   ${LACTEVA_APP_USER}    what the API and workers connect as. NOSUPERUSER,
#                          NOBYPASSRLS, and no DDL: it reads and writes rows,
#                          which is all the application ever does.
#
# The platform refuses to start in prod/staging if it finds itself connected
# as a role that bypasses RLS (`assert_rls_is_enforceable`), so a deployment
# that skips this script fails loudly instead of silently losing isolation.
#
# initdb runs this ONCE, on an empty data directory. For an EXISTING database
# see DEPLOYMENT.md §Database roles, which has the same statements to run by
# hand — an upgrade will not re-run this file.
set -euo pipefail

: "${LACTEVA_APP_USER:?the application role must be named}"
: "${LACTEVA_APP_PASSWORD:?the application role needs a password}"

psql -v ON_ERROR_STOP=1 --username "${POSTGRES_USER}" --dbname "${POSTGRES_DB}" <<-SQL
	DO \$\$ BEGIN
	  IF NOT EXISTS (SELECT 1 FROM pg_roles WHERE rolname = '${LACTEVA_APP_USER}') THEN
	    CREATE ROLE ${LACTEVA_APP_USER} LOGIN PASSWORD '${LACTEVA_APP_PASSWORD}';
	  END IF;
	END \$\$;

	-- Explicit, not merely default. A role that can be ALTERed into a
	-- superuser later is one policy change away from the original defect.
	ALTER ROLE ${LACTEVA_APP_USER}
	  NOSUPERUSER NOBYPASSRLS NOCREATEDB NOCREATEROLE NOREPLICATION;

	GRANT CONNECT ON DATABASE ${POSTGRES_DB} TO ${LACTEVA_APP_USER};
	GRANT USAGE ON SCHEMA public TO ${LACTEVA_APP_USER};

	-- No CREATE on the schema: the application never issues DDL. Alembic
	-- does, as ${POSTGRES_USER}, and that is the only place DDL belongs.
	REVOKE CREATE ON SCHEMA public FROM ${LACTEVA_APP_USER};

	-- The tables do not exist yet — migrations run after this. DEFAULT
	-- PRIVILEGES apply to what ${POSTGRES_USER} creates from here on, so a
	-- table added by a future migration is reachable without another grant.
	ALTER DEFAULT PRIVILEGES FOR ROLE ${POSTGRES_USER} IN SCHEMA public
	  GRANT SELECT, INSERT, UPDATE, DELETE ON TABLES TO ${LACTEVA_APP_USER};
	ALTER DEFAULT PRIVILEGES FOR ROLE ${POSTGRES_USER} IN SCHEMA public
	  GRANT USAGE, SELECT ON SEQUENCES TO ${LACTEVA_APP_USER};

	-- And anything that somehow already exists.
	GRANT SELECT, INSERT, UPDATE, DELETE ON ALL TABLES IN SCHEMA public
	  TO ${LACTEVA_APP_USER};
	GRANT USAGE, SELECT ON ALL SEQUENCES IN SCHEMA public TO ${LACTEVA_APP_USER};
SQL

echo "VER-001: ${LACTEVA_APP_USER} created NOSUPERUSER NOBYPASSRLS — RLS is enforceable."
