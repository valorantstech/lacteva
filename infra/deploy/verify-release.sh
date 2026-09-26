#!/usr/bin/env bash
# WO-102 — every application container is on the tag we think it is.
#
# The automatic rollback used to restore api and nginx ONLY, so a failed
# deploy left portal and marketing on the failed release and `current` naming
# it — a half-rollback nobody would notice until the day it mattered. This
# asserts what the deploy and the rollback both promise: the app containers
# run the given tag, and fails loudly naming any that does not.
#
#   COMPOSE="docker compose …" ./verify-release.sh <tag>
set -uo pipefail
COMPOSE="${COMPOSE:?set COMPOSE to the compose command for this stack}"
tag="${1:?usage: verify-release.sh <tag>}"

bad=0
for svc in api portal marketing; do
  expect="${tag}"
  [ "${svc}" = "marketing" ] && expect="marketing-${tag}"
  ids="$(${COMPOSE} ps -q "${svc}" 2>/dev/null || true)"
  if [ -z "${ids}" ]; then
    printf '  \033[31m✗ %s: no running container\033[0m\n' "${svc}" >&2
    bad=1
    continue
  fi
  for id in ${ids}; do
    image="$(docker inspect --format '{{.Config.Image}}' "${id}" 2>/dev/null || echo '?')"
    case "${image}" in
      *":${expect}") printf '  \033[32m✓\033[0m %s is on %s\n' "${svc}" "${image}" ;;
      *) printf '  \033[31m✗ %s is on %s, not :%s — the release is not what is running\033[0m\n' "${svc}" "${image}" "${expect}" >&2; bad=1 ;;
    esac
  done
done
exit "${bad}"
