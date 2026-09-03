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
  // WO-67 walks as far as the repository root, because the release workflow
  // lives in `.github/` and is part of the contract this file checks.
  var base = Directory.current;
  for (var depth = 0; depth < 4; depth++) {
    final candidate = File('${base.path}/$relative');
    if (candidate.existsSync()) return candidate;
    base = base.parent;
  }
  fail('could not find $relative from ${Directory.current.path}');
}

/// Executable content of a Gradle / ProGuard / YAML file: comment lines
/// removed. Every guard here explains itself in a comment that quotes the
/// thing it forbids, and a naive search finds its own explanation — a trap
/// this repository has walked into three times before.
String _withoutComments(File file, String marker) => file
    .readAsLinesSync()
    .where((line) => !line.trimLeft().startsWith(marker))
    .join('\n');

/// Where `flutter test` was started from, as a path git understands.
String get _packageRoot => Directory.current.path;

void main() {
  late String gradle;

  setUpAll(() {
    // Comments stripped first: the release block explains the defect by
    // quoting the line it replaced, and a naive search finds its own
    // explanation. Only executable Gradle is inspected below.
    gradle = _withoutComments(_find('android/app/build.gradle.kts'), '//');
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
    // ...and the real file, and every keystore, are OUTSIDE version control.
    //
    // WO-67: this used to assert that `android/key.properties` does not
    // EXIST, which was true on every machine until the first release build
    // was attempted — the developer producing a signed APK necessarily has
    // the file on disk, and the test then failed on exactly the machine
    // doing the release. Presence was never the property; being tracked is.
    // So ask git: the path must be ignored, and it must not be in the index.
    // `check-ignore` also proves the ignore RULE is in force, which a
    // presence check on a machine without the file never did.
    for (final secret in [
      'android/key.properties',
      'android/lacteva-release.jks',
      'android/app/anything.keystore',
    ]) {
      final ignored = Process.runSync(
        'git',
        ['check-ignore', '-q', secret],
        workingDirectory: _packageRoot,
      );
      expect(
        ignored.exitCode,
        0,
        reason: '$secret must be covered by a .gitignore rule',
      );
    }
    final tracked = Process.runSync(
      'git',
      ['ls-files', '--', 'android/key.properties', 'android/*.jks'],
      workingDirectory: _packageRoot,
    );
    expect(
      (tracked.stdout as String).trim(),
      isEmpty,
      reason:
          'android/key.properties and the keystore must never be committed',
    );
  });

  test('the release build survives R8 without the Play Core library', () {
    // WO-67. The first release build this project ever ran failed at
    // `:app:minifyReleaseWithR8`: the Flutter engine references
    // `com.google.android.play.core.*` for deferred components, which this
    // app does not use and does not ship, and R8 refuses missing classes.
    // The rule is the package wildcard, not the eleven literal classes R8
    // listed — those change with the engine version; the package does not.
    final rules = _withoutComments(
      _find('android/app/proguard-rules.pro'),
      '#',
    );
    expect(
      rules.contains('-dontwarn com.google.android.play.core.**'),
      isTrue,
      reason:
          'without this rule `flutter build apk --release` does not compile',
    );
    // The Flutter engine keep rules the file has carried since PORTAL-001.
    expect(rules.contains('-keep class io.flutter.** { *; }'), isTrue);
    // The rule only matters because shrinking is ON, and shrinking must stay
    // on: turning it off would make the build pass and ship every unused
    // byte to a farmer's phone on a metered connection.
    final release = gradle.substring(gradle.indexOf('buildTypes'));
    expect(release.contains('isMinifyEnabled = true'), isTrue);
    expect(release.contains('isShrinkResources = true'), isTrue);
    expect(release.contains('"proguard-rules.pro"'), isTrue);
  });

  test('the example says what storeFile is relative to', () {
    // WO-67, failure 1. `storeFile` is resolved by `file()` inside the app
    // module, so a keystore at android/lacteva-release.jks must be written
    // `../lacteva-release.jks`; a bare filename sends Gradle into
    // android/app/. The example is where the next person copies from.
    final example = _find('android/key.properties.example').readAsStringSync();
    expect(example.contains('relative to android/app/'), isTrue);
    expect(example.contains('../lacteva-release.jks'), isTrue);
  });

  test('CI builds a release APK on every push, and signs the real one', () {
    // WO-67, the lesson: a guard proven only against a contract is a guard
    // nobody has walked past. The release path is now exercised twice —
    // every push builds a release APK with a throwaway keystore made on the
    // runner (which is what finds an R8 failure), and the signed,
    // distributable APK is produced by a dispatchable workflow from the
    // owner's keystore held in GitHub secrets. Both must compile in the
    // address a distributed build carries.
    final ci = _withoutComments(_find('.github/workflows/ci.yml'), '#');
    expect(ci.contains('flutter build apk --release'), isTrue);
    expect(ci.contains('keytool -genkeypair'), isTrue);
    expect(
      ci.contains('--dart-define=LACTEVA_API_URL=https://api.lacteva.com'),
      isTrue,
    );

    final release = _withoutComments(
      _find('.github/workflows/release-apk.yml'),
      '#',
    );
    expect(release.contains('workflow_dispatch'), isTrue);
    expect(release.contains('flutter build apk --release'), isTrue);
    expect(
      release.contains('--dart-define=LACTEVA_API_URL=https://api.lacteva.com'),
      isTrue,
    );
    // The keystore and its passwords arrive as secrets, never as text in the
    // repository or the log...
    expect(release.contains('secrets.LACTEVA_ANDROID_KEYSTORE_B64'), isTrue);
    expect(release.contains('secrets.LACTEVA_ANDROID_KEY_PROPERTIES'), isTrue);
    // ...a missing secret FAILS the run rather than skipping it, because a
    // skipped proof is green...
    expect(release.contains('exit 1'), isTrue);
    // ...and the artifact is checked against the Phoenix Software
    // certificate before it is uploaded, so a run that somehow signed with
    // anything else publishes nothing.
    expect(release.contains('infra/ci/verify-release-apk.sh'), isTrue);
    expect(release.contains('upload-artifact'), isTrue);
    // The verifier itself: the certificate is read from the APK, the debug
    // key and the CI throwaway key are refused by name, and the fingerprint
    // is compared with the pinned one.
    final verifier = _withoutComments(
      _find('infra/ci/verify-release-apk.sh'),
      '#',
    );
    expect(verifier.contains('verify --print-certs'), isTrue);
    expect(verifier.contains('CN=Android Debug'), isTrue);
    expect(verifier.contains('NOT FOR DISTRIBUTION'), isTrue);
    expect(verifier.contains('release-certificate.sha256'), isTrue);
    final pinned = _find('android/release-certificate.sha256')
        .readAsStringSync()
        .trim();
    expect(RegExp(r'^[0-9a-f]{64}$').hasMatch(pinned), isTrue);
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
