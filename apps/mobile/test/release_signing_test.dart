/// PORTAL-001 / F-05 — a release build must never be signed with debug keys.
///
/// The Android SDK on this machine has no BuildTools, so `flutter build apk
/// --release` cannot run here and this cannot be proven by producing an APK.
/// What CAN be proven, and is what actually regressed, is the Gradle contract:
/// the release build type must not select the debug signing config, and it
/// must FAIL rather than fall back when no keystore is configured.
///
/// The original defect was one line — `signingConfig =
/// signingConfigs.getByName("debug")` under a TODO — so a test that reads the
/// build file is aimed exactly at how it will come back.
library;

import 'dart:io';

import 'package:flutter_test/flutter_test.dart';

File _find(String relative) {
  // `flutter test` runs from the package root; walk up if invoked elsewhere.
  for (final base in [Directory.current, Directory.current.parent]) {
    final candidate = File('${base.path}/$relative');
    if (candidate.existsSync()) return candidate;
  }
  fail('could not find $relative from ${Directory.current.path}');
}

void main() {
  late String gradle;

  setUpAll(() {
    // Comments stripped first: the release block explains the defect by
    // quoting the line it replaced, and a naive search finds its own
    // explanation. Only executable Gradle is inspected below.
    gradle = _find('android/app/build.gradle.kts')
        .readAsLinesSync()
        .where((line) => !line.trimLeft().startsWith('//'))
        .join('\n');
  });

  test('the release build type does not use the debug signing config', () {
    final release = gradle.substring(gradle.indexOf('buildTypes'));
    expect(
      release.contains('signingConfigs.getByName("debug")'),
      isFalse,
      reason:
          'a release build signed with the public Android debug key is not '
          'distributable and cannot be upgraded',
    );
    expect(release.contains('signingConfigs.getByName("release")'), isTrue);
  });

  test('a release build with no keystore fails instead of falling back', () {
    expect(
      gradle.contains('throw GradleException'),
      isTrue,
      reason: 'a silent fallback is how a debug-signed build reaches a phone',
    );
    expect(gradle.contains('key.properties'), isTrue);
  });

  test('the signing material is supplied from outside the repository', () {
    expect(gradle.contains('rootProject.file("key.properties")'), isTrue);
    // The example exists so nobody has to guess the shape...
    expect(_find('android/key.properties.example').existsSync(), isTrue);
    // ...and the real file is not here.
    final real = File('${Directory.current.path}/android/key.properties');
    expect(
      real.existsSync(),
      isFalse,
      reason:
          'android/key.properties is gitignored and must never be committed',
    );
  });

  test('the example carries no real credential', () {
    final example = _find('android/key.properties.example').readAsStringSync();
    for (final line in example.split('\n')) {
      if (line.startsWith('storePassword=') ||
          line.startsWith('keyPassword=')) {
        expect(
          line.contains('CHANGEME'),
          isTrue,
          reason: 'the example must be obviously a placeholder: $line',
        );
      }
    }
  });
}
