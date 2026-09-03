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

size_bytes="$(stat -c %s "$apk")"
echo "OK: $apk"
echo "    signer:  $dn"
echo "    sha256:  $sha"
printf '    size:    %s bytes (%.1f MiB)\n' "$size_bytes" "$(echo "$size_bytes / 1048576" | bc -l)"
