/// Where the app points, and whether a RELEASE may point there.
///
/// Found by the owner on 2026-09-04: a release APK handed to the handset
/// answered every sign-in with "Could not reach the platform". The build had
/// been run without `--dart-define=LACTEVA_API_URL`, so `main.dart`'s
/// developer default — `http://localhost:8000`, the right address for
/// `flutter run` against a laptop — was compiled into a customer artifact,
/// and the phone tried to reach a server on itself. The device, the network
/// and the credentials were all fine; the build was the defect.
///
/// This is the third time a release fell back to a developer default in
/// silence: the debug signing key (FINAL-001) and the stale host tree in
/// deploy.sh (d3b0d08) were the first two. The rule each time is the same —
/// a release must REFUSE, visibly, rather than ship the fallback — and it
/// lives in the build, not in a document, so it cannot be forgotten by the
/// person typing the command. `apiUrlProblem` is that rule; `main.dart`
/// consults it before the first frame and `verify-release-apk.sh` reads the
/// finished artifact for the same addresses.
library;

/// Hosts that only ever mean "the developer's own machine".
const developerHosts = {'localhost', '127.0.0.1', '10.0.2.2', '0.0.0.0', '::1'};

/// Why a build must not run against [url], or `null` when it may.
///
/// A debug build (`release: false`) is never refused: pointing at a laptop is
/// what debug builds are for. A release build is refused when the address is
/// a developer host, is not `https`, or does not parse at all.
String? apiUrlProblem(String url, {required bool release}) {
  if (!release) return null;
  final parsed = Uri.tryParse(url);
  if (parsed == null || parsed.host.isEmpty) {
    return 'This release build was compiled with an unusable platform '
        'address ("$url"). Rebuild with '
        '--dart-define=LACTEVA_API_URL=https://api.lacteva.com.';
  }
  if (developerHosts.contains(parsed.host)) {
    return 'This release build points at a developer machine '
        '(${parsed.host}), not at the platform. It was built without '
        '--dart-define=LACTEVA_API_URL and must not be handed to anyone. '
        'Rebuild with --dart-define=LACTEVA_API_URL=https://api.lacteva.com.';
  }
  if (parsed.scheme != 'https') {
    return 'This release build would send sign-ins over ${parsed.scheme}, not '
        'https ("$url"). Rebuild with '
        '--dart-define=LACTEVA_API_URL=https://api.lacteva.com.';
  }
  return null;
}
