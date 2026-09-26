#!/usr/bin/env bash
# One-command deployment (INF-001).
#
#   ./infra/deploy/deploy.sh <image-tag>
#   ./infra/deploy/deploy.sh v1.4.2 --no-rollback     # keep a broken deploy for inspection
#   ./infra/deploy/deploy.sh --rollback               # go back to the previous release, now
#
# Pull → migrate → deploy → verify → smoke test → roll back if any of those
# fail. The rollback is AUTOMATIC and on by default, because the alternative
# is a half-deployed platform sitting broken for as long as it takes someone
# to notice and decide.
#
# What it will NOT do automatically is roll back the SCHEMA. Rolling code back
# is safe when the migration was expand-only and unsafe when it contracted,
# and no script can tell the difference from the outside. DEPLOYMENT.md §5 has
# the compatibility matrix; this script pins the previous release and says
# clearly when the schema moved.
set -euo pipefail

RELEASES="${RELEASES_DIR:-/opt/lacteva/releases}"
CURRENT="${CURRENT_LINK:-/opt/lacteva/current}"
ENV_FILE="${ENV_FILE:-/etc/lacteva/.env.production}"
LOG="${DEPLOY_LOG:-/var/log/lacteva/deploy.log}"
# DEMO-010: ABSOLUTE, resolved from where this script lives.
#
# It was a bare filename, so every `compose` call before step 3 depended on
# the caller's working directory — and step 3 is where `cd "${CURRENT}"`
# happens. Running `sudo /opt/lacteva/staging/infra/deploy/deploy.sh` from a
# home directory therefore made step 2's `compose ps` fail, which the check
# read as "no API is running" and reported as
#
#     no running API (first deployment) — skipping pre-deployment backup
#
# on a platform serving every request. The one safety net that makes an
# unrecoverable migration recoverable was quietly not there, and the deploy
# said so in a line that reads like a decision rather than a failure.
# It is ABSOLUTE, and it points at the RELEASE — never at the tree this script
# happens to have been run from.
#
# Both halves matter, and getting the second one wrong is how the running
# stack came to bind-mount its nginx configuration out of a scratch staging
# directory: compose resolves relative bind mounts against the compose file's
# own directory, so pointing it at the checkout means an `rsync --delete` into
# that checkout silently rewrites what production is serving. Copying each
# release into its own directory exists precisely to stop that.
#
# Until step 3, the subject is the CURRENTLY RUNNING stack, so the current
# release's compose file is the right one. After step 3 it is the new release.
# The script's own tree is the fallback for a first deployment, when there is
# no current release to speak of.
SOURCE_TREE="$(cd "$(dirname "$0")/../.." && pwd)"
if [ -f "${CURRENT}/docker-compose.production.yml" ]; then
  COMPOSE_FILE="$(readlink -f "${CURRENT}")/docker-compose.production.yml"
else
  COMPOSE_FILE="${SOURCE_TREE}/docker-compose.production.yml"
fi
AUTO_ROLLBACK=1

log()  { printf '%s  %s\n' "$(date -u +%FT%TZ)" "$*" | tee -a "${LOG}"; }
step() { printf '\n\033[1m==> %s\033[0m\n' "$*" | tee -a "${LOG}"; }
die()  { printf '\n\033[31m%s\033[0m\n' "$*" | tee -a "${LOG}" >&2; exit 1; }

compose() {
  docker compose -f "${COMPOSE_FILE}" --env-file "${ENV_FILE}" "$@"
}

previous_tag() {
  # The tag recorded when the CURRENT release was deployed — not "the second
  # newest directory", which is wrong the moment a release is re-deployed.
  [ -f "${CURRENT}/.deployed-tag" ] && cat "${CURRENT}/.deployed-tag" || true
}

running_tag() {
  grep -E '^LACTEVA_IMAGE_TAG=' "${ENV_FILE}" | cut -d= -f2- || true
}

set_tag() {
  local tag="$1"
  # Written atomically: an interrupted sed leaves the env file half-edited,
  # and every subsequent compose command then fails on a file nobody suspects.
  local tmp
  tmp="$(mktemp)"
  sed "s|^LACTEVA_IMAGE_TAG=.*|LACTEVA_IMAGE_TAG=${tag}|" "${ENV_FILE}" > "${tmp}"
  grep -q "^LACTEVA_IMAGE_TAG=${tag}$" "${tmp}" || { rm -f "${tmp}"; die "could not set image tag in ${ENV_FILE}"; }
  cat "${tmp}" > "${ENV_FILE}"   # preserves ownership and mode, unlike mv
  rm -f "${tmp}"
}

repoint_nginx() {
  # PILOT-F03: nginx resolves `upstream lacteva_api`/`lacteva_portal` — plain
  # container names — ONCE, at startup, and caches the address forever. Every
  # deployment recreates api and portal, Docker hands them new addresses, and
  # nginx keeps proxying to the old ones: eleven healthy containers behind a
  # 502. `up -d` will not fix it, because nginx's own image and config have
  # not changed, so Compose correctly leaves it alone.
  #
  # This bit the FIRST real deployment after the script was written. Worse, the
  # rollback path recreated api again and hit exactly the same wall, so the
  # automatic recovery could not recover — it reported "ROLLBACK ALSO FAILED
  # VERIFICATION" on a platform whose only problem was a stale address in
  # nginx. Restarting nginx after the app containers move is the whole fix.
  step "repointing nginx at the new containers"
  compose restart nginx || die "nginx would not restart — the platform is DOWN, page someone"
}

rollback_to() {
  local tag="$1"
  step "ROLLING BACK to ${tag}"
  set_tag "${tag}"
  # WO-102: `current` goes back too. It named the FAILED release after every
  # rollback since the portal and marketing services were added — and so did
  # those two containers, because only api and nginx were restored. A
  # rollback restores every image-tagged application service; `migrate` is
  # deliberately excluded — see the header, and DEPLOYMENT.md §5.
  if [ -d "${RELEASES}/${tag}" ]; then
    ln -sfn "${RELEASES}/${tag}" "${CURRENT}"
    COMPOSE_FILE="${RELEASES}/${tag}/docker-compose.production.yml"
    cd "${CURRENT}"
  else
    log "no staged release directory for ${tag} — containers roll back, current stays where it is"
  fi
  compose up -d --no-deps api portal marketing nginx || die "rollback failed to start — the platform is DOWN, page someone"
  repoint_nginx
  # Every app container on the restored tag, or say so loudly: a half-rollback
  # is the failure this function exists to prevent.
  COMPOSE="docker compose -f ${COMPOSE_FILE} --env-file ${ENV_FILE}" "${CURRENT}/infra/deploy/verify-release.sh" "${tag}" \
    || die "ROLLBACK LEFT A CONTAINER ON THE WRONG RELEASE (see above). The platform is in a mixed state: DEPLOYMENT.md §12."
  if "${CURRENT}/infra/deploy/verify-deployment.sh"; then
    log "rollback verified: running ${tag}"
    return 0
  fi
  die "ROLLBACK ALSO FAILED VERIFICATION. The platform is not serving. This is an incident: DEPLOYMENT.md §12."
}

# --- live release trees -------------------------------------------------------
# A release directory that `current` points at, or that a RUNNING container
# bind-mounts anything out of, is live, and nothing here may rm or re-stage it.
#
# Staging used to begin with `rm -rf "${RELEASE}"`. Re-deploying the tag that
# `current` already named — exactly what the pre-WO-102 half-rollback left
# behind, since it never moved `current` back — emptied the directory that
# nginx, promtail, Loki, Grafana, Prometheus and postgres were all mounted out
# of, and when that attempt then died (a pull that failed, an extraction that
# did not happen, a hand on Ctrl-C) nothing refilled it. Production kept
# serving only because every process had already loaded its configuration; the
# next reload would have taken all three sites down and the nightly backup
# would have failed on a missing script. So: stage into a directory nobody
# references, prove it complete, and only then swap it in — retiring a live
# tree by rename (running containers keep their mounted inodes) instead of
# deleting it.
release_is_live() {
  local dir="$1" resolved
  resolved="$(readlink -f "${dir}" 2>/dev/null || true)"
  [ -n "${resolved}" ] && [ -e "${resolved}" ] || return 1
  [ "$(readlink -f "${CURRENT}" 2>/dev/null || true)" = "${resolved}" ] && return 0
  docker ps -q 2>/dev/null \
    | xargs -r docker inspect --format '{{range .Mounts}}{{.Source}}{{"\n"}}{{end}}' 2>/dev/null \
    | grep -q "^${resolved}\(/\|$\)"
}

stage_release() {
  # Fills ${RELEASES}/<tag> with the release tree at <tag> and never leaves it
  # empty: the work happens in a sibling staging directory and the swap is two
  # renames. Needs IMAGE, PREVIOUS and SOURCE_TREE.
  # One assignment per line: `local a="$1" b="${a}"` expands every word BEFORE
  # any of them is assigned, so b would see the caller's (empty) a.
  local tag release stage release_image extract
  tag="$1"
  release="${RELEASES}/${tag}"
  stage="${RELEASES}/.staging-${tag}-$$"
  rm -rf "${RELEASES}/.staging-${tag}-"*   # an interrupted earlier attempt; never referenced
  mkdir -p "${stage}"
  release_image="${IMAGE}:release-${tag}"
  if docker pull "${release_image}" > /dev/null 2>&1; then
    log "release tree from ${release_image}"
    extract="lacteva-release-extract-$$"
    docker rm -f "${extract}" > /dev/null 2>&1 || true
    docker create --name "${extract}" "${release_image}" > /dev/null \
      || { rm -rf "${stage}"; die "could not create a container from ${release_image}"; }
    # `/release/.` copies the CONTENTS: `docker cp /release` would nest it.
    if ! docker cp "${extract}:/release/." "${stage}/"; then
      docker rm -f "${extract}" > /dev/null 2>&1 || true
      rm -rf "${stage}"
      die "could not extract the release tree from ${release_image}"
    fi
    docker rm -f "${extract}" > /dev/null 2>&1 || true
    # An empty or partial extraction would leave compose bind-mounting missing
    # files, which surfaces much later as an unexplained nginx failure.
    for required in docker-compose.production.yml infra/nginx/nginx.conf \
                    infra/nginx/conf.d infra/deploy/verify-deployment.sh; do
      [ -e "${stage}/${required}" ] \
        || { rm -rf "${stage}"; die "the release image is missing ${required} — refusing to deploy an incomplete release"; }
    done
  else
    # WO-70 deploy incident: the fallback ran when a transient pull failure met
    # a STALE host tree, and shipped an August compose file over a September
    # platform — the marketing service vanished and lacteva.com served the
    # portal's login page. A tree this script cannot vouch for is not a release.
    # The fallback now needs to be ASKED for, by name, for the one case it
    # exists for: rolling back to a tag published before WO-44, which has no
    # release image. Everything since has one, and a missing image is a reason
    # to stop, not to guess.
    if [ "${ALLOW_HOST_TREE:-}" != "1" ]; then
      rm -rf "${stage}"
      die "no ${release_image} in the registry (or the pull failed). Refusing to deploy from the host tree at ${SOURCE_TREE}: it may be stale. Re-run once the image pulls, or set ALLOW_HOST_TREE=1 for a pre-WO-44 tag."
    fi
    log "no ${release_image} — ALLOW_HOST_TREE=1: falling back to the host tree at ${SOURCE_TREE} (pre-WO-44 tag)"
    rsync -a --delete --exclude '.git' "${SOURCE_TREE}/" "${stage}/" \
      || { rm -rf "${stage}"; die "could not copy the host tree into the release"; }
  fi
  echo "${PREVIOUS}" > "${stage}/.deployed-tag"   # what to go BACK to
  # The swap. A live tree is retired by rename, never deleted: the containers
  # mounted out of it keep their inodes, and `current` is re-pointed by the
  # caller a moment later.
  if [ -e "${release}" ] || [ -L "${release}" ]; then
    if release_is_live "${release}"; then
      local retired="${RELEASES}/.retired-${tag}-$(date -u +%Y%m%dT%H%M%SZ)"
      log "${release} is LIVE (current or a running container references it) — retiring it to ${retired}, not deleting it"
      mv "${release}" "${retired}"
    else
      rm -rf "${release}"
    fi
  fi
  mv "${stage}" "${release}"
}

retire_unreferenced_releases() {
  # Retired trees go once nothing mounts them any more — checked, not assumed.
  local d
  for d in "${RELEASES}"/.retired-*; do
    [ -e "${d}" ] || continue
    if release_is_live "${d}"; then
      log "keeping ${d}: a running container still mounts it"
    else
      rm -rf "${d}" && log "removed retired release tree ${d}"
    fi
  done
}

# --- arguments -------------------------------------------------------------
TAG=""
ROLLBACK_ONLY=0
while [ $# -gt 0 ]; do
  case "$1" in
    --rollback)    ROLLBACK_ONLY=1 ;;
    --no-rollback) AUTO_ROLLBACK=0 ;;
    -*)            die "unknown option: $1" ;;
    *)             TAG="$1" ;;
  esac
  shift
done

mkdir -p "$(dirname "${LOG}")"
[ -f "${ENV_FILE}" ] || die "no environment file at ${ENV_FILE} (see INFRASTRUCTURE.md §Provisioning)"

# DEMO-010: where to verify AGAINST.
#
# Both the verifier and the smoke test defaulted to `http://localhost`. nginx
# answers that with a 301 to HTTPS, the redirect is followed to
# `https://localhost`, and the certificate is for the real hostname — so TLS
# verification fails and BOTH declare a perfectly healthy deployment broken.
# The rollback then fails the same way, and the script reports an incident on
# a platform that is serving every request correctly. That happened here.
#
# The fix is to state the public URL once, in the environment file that every
# other deployment setting already lives in, instead of expecting whoever runs
# a deploy to know two undocumented variables. AWS-001 fixed the redirect and
# left the hostname; this is the other half.
PUBLIC_URL="$(grep -E '^LACTEVA_PUBLIC_URL=' "${ENV_FILE}" | cut -d= -f2- || true)"
if [ -n "${PUBLIC_URL}" ]; then
  API_URL="${API_URL:-${PUBLIC_URL}}"
  SMOKE_URL="${SMOKE_URL:-${PUBLIC_URL}}"
  export API_URL SMOKE_URL
  log "verifying against ${PUBLIC_URL}"
else
  log "LACTEVA_PUBLIC_URL is not set — verifying against http://localhost, which fails on any host with a real certificate"
fi

if [ "${ROLLBACK_ONLY}" = "1" ]; then
  PREV="$(previous_tag)"
  [ -n "${PREV}" ] || die "no previous release recorded — nothing to roll back to"
  rollback_to "${PREV}"
  exit 0
fi

[ -n "${TAG}" ] || die "usage: deploy.sh <image-tag> [--no-rollback] | deploy.sh --rollback"
# WO-93: the secrets directory the api mounts read-only at /run/lacteva-secrets.
# Created here, every deploy, so the mount never depends on cloud-init having
# run on this host or on somebody remembering. root:999 0750 — root places
# the files, the API (uid 999, pinned in the Dockerfile) reads them, nobody
# else enters. Files inside are the operator's: `chown root:999 && chmod 0640`.
install -d -m 0750 -o root -g 999 /etc/lacteva/secrets \
  || die "could not prepare /etc/lacteva/secrets (root:999 0750) — the api mounts it"

PREVIOUS="$(running_tag)"
log "deploying ${TAG} (currently running: ${PREVIOUS:-none})"

# --- 1. pull ---------------------------------------------------------------
# Before anything is changed. A tag that does not exist should fail here, with
# the old version still serving, rather than after the schema has moved.
#
# EVERY image the stack runs, not just the API's (WO-63). It pulled one, and
# `compose up` was left to fetch the rest — so a missing PORTAL or MARKETING
# image failed at step 5, AFTER the release tree had been staged and `current`
# repointed. The rollback then restored the old image tag beside the NEW
# nginx configuration, which referenced an upstream container that did not
# exist, and nginx refused to start: a five-minute outage caused by the deploy
# script's own recovery path. Pulling all three here makes that failure land
# where every other missing-image failure lands — before anything has moved.
step "1/6  pulling ${TAG}"
env_value() { grep -E "^$1=" "${ENV_FILE}" 2>/dev/null | tail -1 | cut -d= -f2- | tr -d '"'"'"'"'; }
IMAGE="$(env_value LACTEVA_IMAGE || true)"; IMAGE="${IMAGE:-lacteva/platform-core}"
PORTAL_IMAGE="$(env_value PORTAL_IMAGE || true)"; PORTAL_IMAGE="${PORTAL_IMAGE:-lacteva/admin-portal}"
MARKETING_IMAGE="$(env_value MARKETING_IMAGE || true)"; MARKETING_IMAGE="${MARKETING_IMAGE:-${PORTAL_IMAGE}}"
docker pull "${IMAGE}:${TAG}" || die "image ${IMAGE}:${TAG} could not be pulled — nothing has changed"
docker pull "${PORTAL_IMAGE}:${TAG}" \
  || die "image ${PORTAL_IMAGE}:${TAG} could not be pulled — nothing has changed"
docker pull "${MARKETING_IMAGE}:marketing-${TAG}" \
  || die "image ${MARKETING_IMAGE}:marketing-${TAG} could not be pulled — nothing has changed"

# --- 2. pre-flight backup --------------------------------------------------
# The last cheap moment. If the migration in step 4 turns out to be a contract
# migration that cannot be rolled back, this is what recovery uses.
step "2/6  pre-deployment backup"
# Three outcomes, not two. "compose could not run at all" is a FAILURE, and
# used to be indistinguishable from "there is no API yet" — see COMPOSE_FILE.
if ! RUNNING="$(compose ps --status running --services 2>&1)"; then
  die "could not ask docker what is running (${RUNNING%%$'\n'*}) — refusing to deploy blind"
fi
if printf '%s\n' "${RUNNING}" | grep -qx api; then
  STAMP="$(date -u +%Y%m%dT%H%M%SZ)"
  compose exec -T api python -m platform_core.core.backup.cli backup "/backup/logical/predeploy-${STAMP}" \
    || die "pre-deployment backup failed — refusing to deploy without a way back"
  log "backed up to /backup/logical/predeploy-${STAMP}"
else
  log "no running API (first deployment) — skipping pre-deployment backup"
fi

# --- 3. record the release -------------------------------------------------
step "3/6  staging release ${TAG}"
RELEASE="${RELEASES}/${TAG}"
# WO-44: the release tree comes from the REGISTRY, at this tag.
#
# It used to come from `rsync "${SOURCE_TREE}/"` — the host's own current
# release. The code was pinned to a commit and everything it runs beside was
# not, so "the repository at this tag IS the release" was a claim the script
# could not keep: whatever was last placed on that disk by hand was the
# release, no matter which tag was named. `fe86d8c` fixed nginx's security
# headers, published its images, deployed green, and changed nothing on the
# live site, because no step carried the file. There was no route in but a
# manual rsync from an allow-listed address.
#
# Now the same CI run that builds the API publishes the tree as
# `<image>:release-<tag>`, and this pulls it and copies it out. Nothing on the
# host is a source of truth any more.
#
# The rsync remains as a FALLBACK, and deliberately so: tags published before
# this change have no release image, and a rollback to one of them must still
# work. A deploy that silently fell back would be the old bug wearing a new
# hat, so it says which path it took, every time.
# The same incident, other half: the command that started it ran
# /opt/lacteva/staging/infra/deploy/deploy.sh — a copy from before this
# script learned about release images. A stale copy of THIS script has no
# way to know it is stale, so the one thing it can do is say where it lives,
# and the documented invocation (DEPLOYMENT.md) is the current release's own
# copy: /opt/lacteva/current/infra/deploy/deploy.sh.
SELF="$(readlink -f "${BASH_SOURCE[0]}")"
case "${SELF}" in
  "$(readlink -f "${CURRENT}" 2>/dev/null)"/*|"${RELEASES}"/*) ;;
  *) log "WARNING: running ${SELF}, which is not a release's own copy — prefer ${CURRENT}/infra/deploy/deploy.sh" ;;
esac
# Staged beside the release and swapped in complete, or not at all — see
# release_is_live()/stage_release() above: this directory may be the one
# production is mounted out of right now.
stage_release "${TAG}"
ln -sfn "${RELEASE}" "${CURRENT}"
cd "${CURRENT}"
# From here the subject is the NEW release, and every container recreated
# below binds its configuration out of this directory rather than out of
# whatever tree this script was invoked from.
COMPOSE_FILE="${RELEASE}/docker-compose.production.yml"

# --- 4. migrate ------------------------------------------------------------
# Its own step, before the API starts. Compose enforces this too
# (service_completed_successfully), but running it explicitly means a failure
# is attributable to the migration rather than to "the stack did not come up".
step "4/6  applying migrations"
set_tag "${TAG}"
SCHEMA_BEFORE="$(compose exec -T postgres psql -U "${POSTGRES_USER:-lacteva}" -d "${POSTGRES_DB:-lacteva}" \
  -tAc 'SELECT version_num FROM alembic_version' 2>/dev/null | tr -d '[:space:]' || echo none)"
# AWS-001: the datastores FIRST, and the `migrate` service — not `api`.
#
# This step used to be `compose run --rm --no-deps -T api alembic upgrade
# head`, which had two faults that only a first deployment exposes. `--no-deps`
# meant nothing started PostgreSQL, so on an empty host alembic died on
# "Temporary failure in name resolution" trying to reach `postgres`. And the
# `api` service connects as the unprivileged application role, which
# deliberately cannot issue DDL — the `migrate` service exists precisely
# because migrations need the owner (see its comment in the compose file).
#
# `up -d` on the datastores is idempotent: on an upgrade they are already
# running and this returns immediately.
compose up -d postgres redis rabbitmq || die "datastores would not start — nothing has been migrated"
if ! compose run --rm -T migrate; then
  log "migration FAILED"
  set_tag "${PREVIOUS}"
  die "migration failed. The old version is still running and the schema is unchanged. Read the log above."
fi
SCHEMA_AFTER="$(compose exec -T postgres psql -U "${POSTGRES_USER:-lacteva}" -d "${POSTGRES_DB:-lacteva}" \
  -tAc 'SELECT version_num FROM alembic_version' 2>/dev/null | tr -d '[:space:]' || echo unknown)"
if [ "${SCHEMA_BEFORE}" != "${SCHEMA_AFTER}" ]; then
  log "SCHEMA MOVED: ${SCHEMA_BEFORE} -> ${SCHEMA_AFTER}"
  log "  A code rollback is safe only if that migration was expand-only."
  log "  DEPLOYMENT.md §5 has the compatibility matrix."
fi

# --- 5. deploy and verify --------------------------------------------------
step "5/6  starting ${TAG}"
compose up -d --remove-orphans || {
  log "compose up failed"
  [ "${AUTO_ROLLBACK}" = "1" ] && [ -n "${PREVIOUS}" ] && rollback_to "${PREVIOUS}"
  die "deployment failed to start"
}
repoint_nginx

# WO-102: before asking whether the platform is healthy, ask whether it is
# the release we meant — a partial `up` is caught here, not on rollback day.
if ! COMPOSE="docker compose -f ${COMPOSE_FILE} --env-file ${ENV_FILE}" ./infra/deploy/verify-release.sh "${TAG}"; then
  log "RELEASE CHECK FAILED — a container is not on ${TAG}"
  if [ "${AUTO_ROLLBACK}" = "1" ] && [ -n "${PREVIOUS}" ]; then
    rollback_to "${PREVIOUS}"
    die "deployment ${TAG} did not come up on its own tag and was rolled back to ${PREVIOUS}."
  fi
  die "deployment ${TAG} did not come up on its own tag. Left running for inspection (--no-rollback)."
fi

if ! ./infra/deploy/verify-deployment.sh; then
  log "VERIFICATION FAILED"
  if [ "${AUTO_ROLLBACK}" = "1" ] && [ -n "${PREVIOUS}" ]; then
    rollback_to "${PREVIOUS}"
    die "deployment ${TAG} failed verification and was rolled back to ${PREVIOUS}."
  fi
  die "deployment ${TAG} failed verification. Left running for inspection (--no-rollback)."
fi

# --- 6. smoke test ---------------------------------------------------------
# Verification says the platform is SERVING. This says it WORKS. A deployment
# that passes the first and fails the second is the more dangerous one,
# because every dashboard is green.
step "6/6  smoke test"
# AWS-001: `SMOKE_TLS=insecure` passes --insecure through, for a deployment
# whose certificate is self-signed because it has no DNS name yet. Default is
# unchanged and verifies normally.
SMOKE_ARGS=()
[ "${SMOKE_TLS:-}" = "insecure" ] && SMOKE_ARGS+=(--insecure)
if ! ./infra/deploy/smoke-test.py --base-url "${SMOKE_URL:-http://localhost}" "${SMOKE_ARGS[@]}"; then
  log "SMOKE TEST FAILED"
  if [ "${AUTO_ROLLBACK}" = "1" ] && [ -n "${PREVIOUS}" ]; then
    rollback_to "${PREVIOUS}"
    die "deployment ${TAG} passed verification but failed the smoke test, and was rolled back."
  fi
  die "deployment ${TAG} failed the smoke test. Left running for inspection (--no-rollback)."
fi

retire_unreferenced_releases
printf '\n\033[32mDEPLOYED %s\033[0m\n' "${TAG}" | tee -a "${LOG}"
log "previous release ${PREVIOUS:-none} — roll back with: $0 --rollback"
[ "${SCHEMA_BEFORE}" != "${SCHEMA_AFTER}" ] && \
  log "NOTE: the schema moved this deploy. Check DEPLOYMENT.md §5 before rolling back."
exit 0
