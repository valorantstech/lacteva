/// Which commit this build came from (WO-75).
///
/// Twice in one day a build was wrong in a way its own verification could
/// not see — once pointing at localhost, once suspected stale — and the
/// answer to "which build is this?" took unzipping the APK. So the commit
/// and the build time are compiled in:
///
///   flutter build apk --release \
///     --dart-define=LACTEVA_API_URL=https://api.lacteva.com \
///     --dart-define=LACTEVA_BUILD_COMMIT=$(git rev-parse --short HEAD) \
///     --dart-define=LACTEVA_BUILD_TIME=$(date -u +%Y-%m-%dT%H:%MZ)
///
/// The More screen shows it, so support can ask a user to read it off their
/// phone, and `infra/ci/verify-release-apk.sh` reads the same literal out of
/// the APK (`strings` finds it: const interpolation folds to one string) and
/// says plainly when it differs from HEAD. A build without the defines says
/// "unstamped" rather than pretending: a mismatch is never fatal and never
/// silent.
library;

const buildCommit = String.fromEnvironment('LACTEVA_BUILD_COMMIT');
const buildTime = String.fromEnvironment('LACTEVA_BUILD_TIME');

/// The literal the verifier greps for. Keep the prefix in step with
/// `infra/ci/verify-release-apk.sh`.
const buildStamp = 'lacteva-build:$buildCommit:$buildTime';

/// What the More screen prints beside "Build".
String buildLabel({String commit = buildCommit, String time = buildTime}) {
  if (commit.isEmpty) return 'unstamped (developer build)';
  return time.isEmpty ? commit : '$commit · $time';
}
