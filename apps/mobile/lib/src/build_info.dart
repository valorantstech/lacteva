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
///
/// Everything the screen shows is DERIVED from this one string, on purpose:
/// the first stamped build had `buildLabel()` read `buildCommit` and
/// `buildTime` directly, the AOT compiler tree-shook the unreferenced
/// `buildStamp`, and the verifier found no stamp in an APK that carried the
/// commit. A literal survives the snapshot only if something runs on it.
const buildStamp = 'lacteva-build:$buildCommit:$buildTime';

/// "abc1234 · 2026-09-25T14:00Z", or what a developer build must admit to.
String parseBuildLabel(String stamp) {
  final parts = stamp.split(':');
  final commit = parts.length > 1 ? parts[1] : '';
  final time = parts.length > 2 ? parts.sublist(2).join(':') : '';
  if (commit.isEmpty) return 'unstamped (developer build)';
  return time.isEmpty ? commit : '$commit · $time';
}

/// What the More screen prints beside "Build".
String buildLabel() => parseBuildLabel(buildStamp);
