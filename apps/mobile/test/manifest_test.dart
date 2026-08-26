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
