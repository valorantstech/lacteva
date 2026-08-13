/// PORTAL-001 / F-05 — a release build must never be signed with debug keys.
///
/// There is no release keystore on this machine — correctly, since the signing
/// material is supplied from outside the repository — so `flutter build apk
/// --release` cannot produce an APK here and this cannot be proven by making
/// one. What CAN be proven, and is what actually regressed, is the Gradle
/// contract: the release build type must not select the debug signing config,
/// and it must FAIL rather than fall back when no keystore is configured.
///
/// The original defect was one line — `signingConfig =
/// signingConfigs.getByName("debug")` under a TODO — so a test that reads the
/// build file is aimed exactly at how it will come back.
///
/// DEMO-012 found the SECOND defect this file is now aimed at. The guard was
/// written inside `buildTypes.release { }`, which is a CONFIGURATION block
/// Gradle evaluates on every invocation — so it refused `assembleDebug` too,
/// and on any machine without `key.properties` the app could not be built at
/// all. `flutter build apk --debug` failed with "Release build requested".
/// The guard was right to exist and was looking in a place that could not see
/// the question it was asking; it now fires from the task graph.
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
    expect(
      release.contains('signingConfigs.getByName("release")') ||
          release.contains('signingConfigs.findByName("release")'),
      isTrue,
      reason: 'the release build type must bind to the release signing config',
    );
  });

  test('a release build with no keystore fails instead of falling back', () {
    expect(
      gradle.contains('throw GradleException'),
      isTrue,
      reason: 'a silent fallback is how a debug-signed build reaches a phone',
    );
    expect(gradle.contains('key.properties'), isTrue);
  });

  test('the guard refuses release builds, not every build', () {
    // DEMO-012. A check inside `buildTypes.release { }` runs while Gradle
    // CONFIGURES the project, which it does identically for assembleDebug,
    // `flutter test` and assembleRelease — so the guard blocked every build
    // on every machine without a keystore. Only the task graph knows what was
    // actually requested.
    final buildTypes = gradle.substring(gradle.indexOf('buildTypes'));
    final afterBuildTypes = buildTypes.substring(
      buildTypes.indexOf('flutter {'),
    );
    expect(
      buildTypes
          .substring(0, buildTypes.indexOf('flutter {'))
          .contains('throw GradleException'),
      isFalse,
      reason:
          'a throw inside the release configuration block fires for '
          'assembleDebug as well, and blocks every build',
    );
    expect(
      afterBuildTypes.contains('gradle.taskGraph'),
      isTrue,
      reason: 'the guard must decide from the requested tasks',
    );
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
