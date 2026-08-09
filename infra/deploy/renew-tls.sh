#!/usr/bin/env bash
# Renew the TLS certificate and reload nginx (TLS-001).
#
#   ./infra/deploy/renew-tls.sh            # renew if due, reload if renewed
#   ./infra/deploy/renew-tls.sh --dry-run  # exercise the whole path, issue nothing
#
# Run from a systemd timer twice a day (see INFRASTRUCTURE.md). Let's Encrypt
# certificates last 90 days; certbot renews only inside the last 30, so a
# twice-daily timer that usually does nothing is the intended shape.
#
# `--webroot` rather than `--standalone`: nginx keeps serving throughout, and
# the challenge is written into the `certbot_webroot` volume that
# `lacteva.conf` already serves `/.well-known/acme-challenge/` from. That
# location existed from the start; the volume behind it did not, so the
# documented certbot step could never have worked until TLS-001.
#
# nginx reads the certificate from ${TLS_CERT_DIR} (a read-only bind), NOT
# from certbot's live directory, so a renewal has to copy the new files across
# and reload. `-L` dereferences certbot's symlinks; copying the links would
# give nginx two dangling paths.

set -euo pipefail

ENV_FILE="${ENV_FILE:-/etc/lacteva/.env.production}"
LE_DIR="${LE_DIR:-/etc/lacteva/letsencrypt}"
CERT_DIR="${CERT_DIR:-/etc/lacteva/certs}"
CERT_NAME="${CERT_NAME:-lacteva}"
PROJECT="${COMPOSE_PROJECT:-lacteva-production}"
RELEASE="${CURRENT_LINK:-/opt/lacteva/current}"
DRY_RUN=""
[ "${1:-}" = "--dry-run" ] && DRY_RUN="--dry-run"

log() { printf '%s  %s\n' "$(date -u +%FT%TZ)" "$*"; }

BEFORE=""
[ -f "${CERT_DIR}/fullchain.pem" ] && BEFORE="$(openssl x509 -in "${CERT_DIR}/fullchain.pem" -noout -enddate)"

log "renewing (${DRY_RUN:-live})"
docker run --rm \
  -v "${LE_DIR}:/etc/letsencrypt" \
  -v "${PROJECT}_certbot_webroot:/var/www/certbot" \
  certbot/certbot:latest renew --webroot -w /var/www/certbot --non-interactive ${DRY_RUN}

[ -n "${DRY_RUN}" ] && { log "dry run complete — nothing installed"; exit 0; }

# Copy across only if certbot actually produced something newer, so a no-op
# renewal does not reload nginx twice a day for no reason.
AFTER="$(openssl x509 -in "${LE_DIR}/live/${CERT_NAME}/fullchain.pem" -noout -enddate)"
if [ "${BEFORE}" = "${AFTER}" ]; then
  log "not due for renewal (${AFTER}) — nginx untouched"
  exit 0
fi

install -m 0644 -T "$(readlink -f "${LE_DIR}/live/${CERT_NAME}/fullchain.pem")" "${CERT_DIR}/fullchain.pem"
install -m 0600 -T "$(readlink -f "${LE_DIR}/live/${CERT_NAME}/privkey.pem")"   "${CERT_DIR}/privkey.pem"
log "installed ${AFTER}"

cd "${RELEASE}" 2>/dev/null || cd "$(dirname "$0")/../.."
# `reload`, not restart: an in-flight request must not be dropped to pick up a
# certificate, and a config error should leave the old process serving.
docker compose -f docker-compose.production.yml --env-file "${ENV_FILE}" exec -T nginx nginx -t
docker compose -f docker-compose.production.yml --env-file "${ENV_FILE}" exec -T nginx nginx -s reload
log "nginx reloaded"
