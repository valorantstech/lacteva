/// The Android manifest a RELEASE build actually gets
/// (P1-PRODUCT-READINESS-001).
///
/// Android merges manifests per build type: a debug build gets
/// `src/debug/AndroidManifest.xml` merged over `src/main`, a release build
/// gets `src/main` alone. Flutter's template declares `INTERNET` in debug and
/// profile only — correct for an app that does not use the network, and wrong
/// for this one, which does nothing else.
///
/// The failure that made this worth a test: debug and profile builds worked
/// perfectly, so the gap was invisible to every hands-on check, and only the
/// release APK — the one a dairy would be handed — could not open a socket.
/// A permission that is present in the builds you test and absent from the
/// build you ship is exactly the kind of thing prose cannot hold.
library;

import 'dart:io';

import 'package:flutter_test/flutter_test.dart';

File _manifest(String flavour) {
  for (final base in ['android/app/src', '../android/app/src']) {
    final f = File('$base/$flavour/AndroidManifest.xml');
    if (f.existsSync()) return f;
  }
  fail('no $flavour AndroidManifest.xml found from ${Directory.current.path}');
}

/// A file of the app's own tree, from either working directory `flutter test`
/// is run in.
File _inApp(String relative) {
  for (final base in ['.', '..']) {
    final f = File('$base/$relative');
    if (f.existsSync()) return f;
  }
  fail('no $relative found from ${Directory.current.path}');
}

/// The company's application id (WO-78 · LACTEVA-MOBILE-014).
const applicationId = 'com.phoenix.lacteva';

void main() {
  group('the release manifest', () {
    test('grants INTERNET, because every screen in this app is a network call', () {
      final xml = _manifest('main').readAsStringSync();
      expect(
        xml,
        contains('android.permission.INTERNET'),
        reason: 'a release build without INTERNET cannot reach the platform at all',
      );
    });

    test('declares it at manifest level, not inside <application>', () {
      // `<uses-permission>` is only honoured as a direct child of <manifest>.
      // Nested inside <application> it is silently ignored, which would look
      // fixed and ship broken.
      final xml = _manifest('main').readAsStringSync();
      final permission = xml.indexOf('android.permission.INTERNET');
      final application = xml.indexOf('<application');
      expect(permission, greaterThan(-1));
      expect(
        permission,
        lessThan(application),
        reason: '<uses-permission> must precede <application> as a child of <manifest>',
      );
    });
  });

  test('the launcher caption is the product name, not the package', () {
    // LACTEVA-ADMIN-005 / D6. This read `lacteva_mobile` — the Flutter project
    // slug — so the home screen showed the refined Lacteva mark captioned with
    // a developer's directory name. It is the second half of the same sentence
    // the icon says, and a customer reads both at once.
    //
    // The application id is a DIFFERENT thing. When this was written it
    // stayed `com.lacteva.lacteva_mobile`, because changing it would orphan
    // every existing install. That reasoning was correct then and is the
    // reason the id moved WHEN it did: on 2026-09-04 the owner decided, as a
    // final decision, that the app carries the company's identity —
    // `com.phoenix.lacteva` — and WO-78 moved it once, on purpose, BEFORE
    // anything was published, while the only installs to orphan were demo
    // APKs on the owner's and the sales team's phones (reinstalls, not
    // customers). Once the app is on a store that door shuts permanently: a
    // published application id can never be changed, only abandoned with
    // its listing, its installs and its reviews. The signing identity is
    // not affected — a keystore is not bound to a package name.
    expect(
      _manifest('main').readAsStringSync(),
      contains('android:label="Lacteva"'),
      reason: 'the caption under the launcher icon is the product name',
    );
  });

  group("the application id is the company's (WO-78)", () {
    test('Android namespace and applicationId are com.phoenix.lacteva', () {
      final gradle = _inApp('android/app/build.gradle.kts').readAsStringSync();
      expect(gradle, contains('namespace = "$applicationId"'));
      expect(gradle, contains('applicationId = "$applicationId"'));
      expect(gradle, isNot(contains('com.lacteva')));
    });

    test('MainActivity lives in the matching package, and the old tree is gone', () {
      // A wrong `package` line compiles and then dies at runtime with a
      // missing-class error — exactly the failure a green build hides.
      final activity = _inApp(
        'android/app/src/main/kotlin/com/phoenix/lacteva/MainActivity.kt',
      ).readAsStringSync();
      expect(activity, startsWith('package $applicationId\n'));
      expect(activity, contains('class MainActivity : FlutterActivity()'));
      for (final base in ['.', '..']) {
        expect(
          Directory('$base/android/app/src/main/kotlin/com/lacteva').existsSync(),
          isFalse,
          reason: 'the old package directory must be deleted, not left behind',
        );
      }
      // The manifest names the activity relative to the namespace, so it
      // follows the rename without an edit — pinned so it stays that way.
      expect(_manifest('main').readAsStringSync(), contains('android:name=".MainActivity"'));
    });

    test('iOS carries the same identity, and only that one', () {
      // iOS does not ship yet; one identity, not a second one for someone to
      // discover later.
      final project = _inApp('ios/Runner.xcodeproj/project.pbxproj').readAsStringSync();
      expect(
        RegExp(r'PRODUCT_BUNDLE_IDENTIFIER = com\.phoenix\.lacteva;').allMatches(project).length,
        3,
      );
      expect(
        RegExp(
          r'PRODUCT_BUNDLE_IDENTIFIER = com\.phoenix\.lacteva\.RunnerTests;',
        ).allMatches(project).length,
        3,
      );
      expect(project, isNot(contains('com.lacteva')));
    });
  });

  group('the scaffold slug shows nowhere a person can see it (WO-78)', () {
    // WO-7 fixed the Android launcher caption and left the same defect on
    // iOS and the web: `lacteva_mobile`, the Flutter project slug, as the
    // name under the icon. The web build is not served anywhere today, so
    // these were latent rather than live — pinned the way the caption is.
    test('the iOS bundle name is Lacteva', () {
      final plist = _inApp('ios/Runner/Info.plist').readAsStringSync();
      expect(plist, contains('<key>CFBundleName</key>\n\t<string>Lacteva</string>'));
      expect(plist, isNot(contains('lacteva_mobile')));
    });

    test('the web title and home-screen name are Lacteva', () {
      final html = _inApp('web/index.html').readAsStringSync();
      expect(html, contains('<title>Lacteva</title>'));
      expect(html, contains('<meta name="apple-mobile-web-app-title" content="Lacteva">'));
      expect(html, isNot(contains('lacteva_mobile')));
      final manifest = _inApp('web/manifest.json').readAsStringSync();
      expect(manifest, contains('"name": "Lacteva"'));
      expect(manifest, contains('"short_name": "Lacteva"'));
      expect(manifest, isNot(contains('lacteva_mobile')));
    });
  });

  test('debug and profile keep their own INTERNET declaration', () {
    // They are merged over `main`, so a duplicate is harmless — and removing
    // them to "de-duplicate" would break `flutter run`, which needs the
    // permission to talk to the running app.
    for (final flavour in ['debug', 'profile']) {
      expect(
        _manifest(flavour).readAsStringSync(),
        contains('android.permission.INTERNET'),
        reason: '$flavour still needs it for the Flutter tooling',
      );
    }
  });
}
