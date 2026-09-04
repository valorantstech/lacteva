/// A release build must not point at a developer machine (2026-09-04).
///
/// The release APK handed to the handset had been built without
/// `--dart-define=LACTEVA_API_URL`; `main.dart`'s default of
/// `http://localhost:8000` was compiled in, and every sign-in on the phone
/// said "Could not reach the platform" while the platform was fine. The same
/// class as FINAL-001 (a release must not fall back to the debug key) and
/// d3b0d08 (a deploy must not fall back to a stale host tree): a release must
/// refuse the fallback, visibly, in the build itself. Three guards, three
/// pins — the rule, the startup screen that shows it, and the artifact check.
library;

import 'dart:io';

import 'package:flutter/foundation.dart';
import 'package:flutter/material.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:lacteva_mobile/main.dart';
import 'package:lacteva_mobile/src/api_url.dart';

File _find(String relative) {
  var base = Directory.current;
  for (var depth = 0; depth < 4; depth++) {
    final candidate = File('${base.path}/$relative');
    if (candidate.existsSync()) return candidate;
    base = base.parent;
  }
  fail('could not find $relative from ${Directory.current.path}');
}

String _withoutComments(File file, String marker) => file
    .readAsLinesSync()
    .where((line) => !line.trimLeft().startsWith(marker))
    .join('\n');

void main() {
  group('the rule', () {
    test('a release refuses every developer address', () {
      for (final url in [
        'http://localhost:8000',
        'https://localhost:8000',
        'http://127.0.0.1:8000',
        'http://10.0.2.2:8000',
        'http://0.0.0.0:8000',
      ]) {
        final problem = apiUrlProblem(url, release: true);
        expect(problem, isNotNull, reason: url);
        expect(problem, contains('--dart-define=LACTEVA_API_URL=https://api.lacteva.com'));
      }
    });

    test('a release refuses plain http and nonsense', () {
      expect(apiUrlProblem('http://api.lacteva.com', release: true), contains('https'));
      expect(apiUrlProblem('', release: true), isNotNull);
      expect(apiUrlProblem('not a url', release: true), isNotNull);
    });

    test('a release accepts the platform', () {
      expect(apiUrlProblem('https://api.lacteva.com', release: true), isNull);
      expect(apiUrlProblem('https://api.lacteva.com/', release: true), isNull);
    });

    test('a debug build keeps pointing wherever the developer says', () {
      expect(apiUrlProblem('http://localhost:8000', release: false), isNull);
      expect(apiUrlProblem('http://10.0.2.2:8000', release: false), isNull);
    });

    test("main.dart's default is a developer address, and main.dart asks the rule", () {
      // The default is what a forgotten flag compiles in. It must be one the
      // rule refuses, or the guard guards nothing.
      expect(apiUrlProblem(apiUrl, release: true), isNotNull);
      expect(apiUrlProblem(apiUrl, release: false), isNull);
      final main = _withoutComments(_find('lib/main.dart'), '//');
      expect(main, contains('apiUrlProblem(apiUrl, release: kReleaseMode)'));
      expect(main, contains('MisbuiltReleaseApp('));
      // This test runs in debug mode; a release build of it would refuse to
      // start, which is the point.
      expect(kReleaseMode, isFalse);
    });
  });

  group('the screen a misbuilt release shows', () {
    testWidgets('names the problem and offers no sign-in', (tester) async {
      await tester.pumpWidget(
        MisbuiltReleaseApp(problem: apiUrlProblem('http://localhost:8000', release: true)!),
      );
      expect(find.text('This build is not for distribution'), findsOneWidget);
      expect(find.textContaining('developer machine (localhost)'), findsOneWidget);
      expect(find.text('Sign in'), findsNothing);
      expect(find.byType(TextField), findsNothing);
    });
  });

  group('the artifact check', () {
    late String script;

    setUpAll(() {
      script = _withoutComments(_find('infra/ci/verify-release-apk.sh'), '#');
    });

    test('verify-release-apk.sh reads the address out of the APK', () {
      expect(script, contains('strings "\$apk"'));
      expect(script, contains(r"grep -c 'https://api\.'"));
      expect(script, contains('localhost|127'));
      expect(script, contains('10\\.0\\.2\\.2'));
      // Both halves fail the script, not warn.
      expect(script, contains('|| fail "the APK carries no https://api'));
      expect(script, contains('|| fail "the APK carries a developer address'));
    });

    test('every release build in CI passes the platform address', () {
      for (final workflow in ['.github/workflows/ci.yml', '.github/workflows/release-apk.yml']) {
        final yaml = _withoutComments(_find(workflow), '#');
        final releaseBuilds = yaml
            .split('\n')
            .where((l) => l.contains('flutter build apk --release'))
            .toList();
        expect(releaseBuilds, isNotEmpty, reason: workflow);
        for (final line in releaseBuilds) {
          expect(
            line,
            contains('--dart-define=LACTEVA_API_URL=https://api.lacteva.com'),
            reason: '$workflow: $line',
          );
        }
        expect(yaml, contains('verify-release-apk.sh'), reason: workflow);
      }
    });

    test('the documented release command carries the flag', () {
      // The README's first `--release` line shows the keystore refusal; the
      // distributable command is the one with the address on it.
      final readme = _find('README.md').readAsStringSync();
      expect(
        readme,
        contains('flutter build apk --release \\\n  --dart-define=LACTEVA_API_URL=https://api.lacteva.com'),
      );
    });
  });
}
