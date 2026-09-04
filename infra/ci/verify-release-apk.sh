#!/usr/bin/env bash
# WO-67 — is this APK the one we would hand to a customer?
#
# A release build that compiles is not a release build that is distributable.
# Three things have to be true of the file, and none of them is visible from
# a green `flutter build`: it is signed (an unsigned APK will not install), it
# is signed by PHOENIX SOFTWARE's key and not the publicly-known Android debug
# key (a debug-signed APK cannot be upgraded by a properly signed one, so every
# install would have to be uninstalled first), and it is the SAME key as last
# time (a new key is a new app to Android). This script is that check, and it
# is the same check whether run by the release workflow or by a person at a
# terminal — the manual gate in DEPLOYMENT.md is this file.
#
#   infra/ci/verify-release-apk.sh build/app/outputs/flutter-apk/app-release.apk
#
# The expected certificate fingerprint lives in
# apps/mobile/android/release-certificate.sha256. A certificate fingerprint is
# public — it is the thing Android shows to anyone who asks — so it is safe in
# the repository, and pinning it is what turns "signed" into "signed by us".
set -euo pipefail

apk="${1:?usage: verify-release-apk.sh <apk>}"
here="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
expected_file="${here}/../../apps/mobile/android/release-certificate.sha256"

fail() { echo "FAIL: $*" >&2; exit 1; }

[ -f "$apk" ] || fail "no such file: $apk"

# apksigner ships with the Android build-tools, wherever they are on this
# machine or runner. Newest first: older ones predate the v3 scheme.
sdk="${ANDROID_HOME:-${ANDROID_SDK_ROOT:-}}"
if [ -z "$sdk" ] && [ -f "${here}/../../apps/mobile/android/local.properties" ]; then
  sdk="$(sed -n 's/^sdk.dir=//p' "${here}/../../apps/mobile/android/local.properties")"
fi
apksigner="$(ls -1 "${sdk}"/build-tools/*/apksigner 2>/dev/null | sort -V | tail -1 || true)"
[ -n "$apksigner" ] || fail "apksigner not found under ${sdk:-\$ANDROID_HOME}/build-tools"

certs="$("$apksigner" verify --print-certs "$apk")" || fail "apksigner rejected the APK (unsigned, or a broken signature)"

dn="$(printf '%s\n' "$certs" | sed -n 's/^Signer #1 certificate DN: //p')"
sha="$(printf '%s\n' "$certs" | sed -n 's/^Signer #1 certificate SHA-256 digest: //p')"
[ -n "$dn" ] && [ -n "$sha" ] || fail "could not read the signer certificate from apksigner output"

case "$dn" in
  *"CN=Android Debug"*) fail "signed with the ANDROID DEBUG KEY — not distributable: $dn" ;;
  *"NOT FOR DISTRIBUTION"*) fail "signed with a CI throwaway key — not distributable: $dn" ;;
esac
# The owner's certificate spells it "Phoenix software"; match the name, not
# its capitalisation.
case "$(printf '%s' "$dn" | tr 'A-Z' 'a-z')" in
  *"phoenix software"*) ;;
  *) fail "signer is not Phoenix Software: $dn" ;;
esac

if [ -f "$expected_file" ]; then
  expected="$(tr -d '[:space:]' < "$expected_file" | tr 'A-F' 'a-f')"
  [ "$(printf '%s' "$sha" | tr 'A-F' 'a-f')" = "$expected" ] \
    || fail "certificate fingerprint changed: got ${sha}, expected ${expected} — a different key is a different app to Android"
else
  echo "WARN: ${expected_file} missing; the signer's identity was checked but not pinned" >&2
fi

# Found 2026-09-04: a release APK handed to the handset had been built without
# `--dart-define=LACTEVA_API_URL`, so `main.dart`'s developer default —
# http://localhost:8000 — was compiled in and every sign-in said "Could not
# reach the platform". The signature was perfect. So the same script that
# proves WHO signed the file proves WHERE it points: Dart string literals
# survive AOT compilation and `strings` finds them, which is exactly how the
# defect was found. The app refuses such a build at startup as well
# (apps/mobile/lib/src/api_url.dart); this is the check before it ships.
command -v strings >/dev/null 2>&1 || fail "'strings' (binutils) is needed to read the platform address out of the APK"
api_hits="$(strings "$apk" | grep -c 'https://api\.' || true)"
dev_hits="$(strings "$apk" | grep -cE 'https?://(localhost|127\.0\.0\.1|10\.0\.2\.2|0\.0\.0\.0)(:|/|$)' || true)"
[ "$api_hits" -gt 0 ] || fail "the APK carries no https://api… address — built without --dart-define=LACTEVA_API_URL=https://api.lacteva.com"
[ "$dev_hits" -eq 0 ] || fail "the APK carries a developer address (localhost / 127.0.0.1 / 10.0.2.2) ${dev_hits} time(s) — it would try to reach a server on the phone itself"
api_url="$(strings "$apk" | grep -oE 'https://api\.[A-Za-z0-9.-]+' | sed 's/\.$//' | sort | uniq -c | sort -rn | head -1 | awk '{print $2}')"

size_bytes="$(stat -c %s "$apk")"
echo "OK: $apk"
echo "    signer:  $dn"
echo "    sha256:  $sha"
echo "    api:     $api_url (no developer address present)"
printf '    size:    %s bytes (%.1f MiB)\n' "$size_bytes" "$(echo "$size_bytes / 1048576" | bc -l)"
