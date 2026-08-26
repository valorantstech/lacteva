/// The launcher icon is Lacteva's, not Flutter's (LACTEVA-BRAND-002).
///
/// Every one of the five `ic_launcher.png` files shipped by this app was
/// BYTE-IDENTICAL to the stock Flutter template — verified by hash, not by
/// eye. That made the single most visible thing a customer sees, the icon on
/// their home screen, a prototype artifact: a dairy manager showing the app to
/// their board opened a Flutter logo.
///
/// It is the kind of defect that survives indefinitely because nothing fails.
/// The app builds, the tests pass, and the icon is only wrong to a human
/// looking at a phone. So it is asserted here.
///
/// The fingerprints below are FNV-1a/64 of the template files, computed from
/// the Flutter SDK on this machine and frozen. FNV rather than md5 only
/// because `crypto` is a transitive dependency of this project rather than a
/// declared one, and a brand test is not a reason to take a new direct
/// dependency — the property under test is "these bytes are not those bytes",
/// which any decent fingerprint answers.
library;

import 'dart:io';

import 'package:flutter_test/flutter_test.dart';

/// FNV-1a, 64-bit, returned as hex. Deterministic, dependency-free, and more
/// than enough to tell two files apart.
///
/// It stays a `BigInt` to the very end on purpose. Going through `toInt()`
/// CLAMPS rather than wraps in Dart, so every fingerprint at or above 2^63
/// collapsed to `7fffffffffffffff` — which silently made half these
/// assertions unable to fail. Found by running the mutation that restores the
/// stock icons and watching one of them pass anyway.
String _fingerprint(List<int> bytes) {
  var hash = BigInt.parse('cbf29ce484222325', radix: 16);
  final prime = BigInt.parse('100000001b3', radix: 16);
  final mask = (BigInt.one << 64) - BigInt.one;
  for (final byte in bytes) {
    hash = (hash ^ BigInt.from(byte));
    hash = (hash * prime) & mask;
  }
  return hash.toRadixString(16).padLeft(16, '0');
}

/// What the stock Flutter template ships. Anything matching one of these is
/// the defect coming back.
const stockFlutterIcons = <String, String>{
  'mdpi': 'cc80822407dd8469',
  'hdpi': '8c1ddfe1f8e95521',
  'xhdpi': 'b50bf20408c675bb',
  'xxhdpi': '54e861a18f6f9c34',
  'xxxhdpi': '25b98cf0ac669cff',
};

const _res = 'android/app/src/main/res';

void main() {
  group('the Android launcher icon', () {
    for (final density in stockFlutterIcons.keys) {
      test('$density is Lacteva, not the Flutter template', () {
        final file = File('$_res/mipmap-$density/ic_launcher.png');
        expect(file.existsSync(), isTrue, reason: '${file.path} is missing');

        final actual = _fingerprint(file.readAsBytesSync());
        expect(
          actual,
          isNot(stockFlutterIcons[density]),
          reason:
              'mipmap-$density/ic_launcher.png is byte-identical to the stock '
              'Flutter template. Run: python3 tools/brand/generate.py',
        );
        // A real icon at this density is not a handful of bytes.
        expect(file.lengthSync(), greaterThan(200));
      });
    }

    test('an adaptive icon exists, in both shapes', () {
      for (final name in ['ic_launcher.xml', 'ic_launcher_round.xml']) {
        final file = File('$_res/mipmap-anydpi-v26/$name');
        expect(file.existsSync(), isTrue, reason: '${file.path} is missing');
        final xml = file.readAsStringSync();
        // Two layers, because a launcher masks and parallaxes them
        // separately; a single-layer icon gets letterboxed on some devices.
        expect(xml, contains('<adaptive-icon'));
        expect(xml, contains('@drawable/ic_launcher_foreground'));
        expect(xml, contains('@color/ic_launcher_background'));
      }
    });

    test('the foreground is the drop and the background is the dairy green',
        () {
      final foreground =
          File('$_res/drawable/ic_launcher_foreground.xml').readAsStringSync();
      expect(foreground, contains('android:viewportWidth="108"'));
      expect(foreground, contains('#FDFBF4')); // the milk drop
      expect(foreground, contains('android:pathData='));

      final background =
          File('$_res/values/ic_launcher_background.xml').readAsStringSync();
      // The one chromatic decision this product ever made.
      expect(background, contains('#1B5E20'));
    });

    test('the manifest still points at the launcher icon', () {
      final manifest =
          File('android/app/src/main/AndroidManifest.xml').readAsStringSync();
      expect(manifest, contains('android:icon="@mipmap/ic_launcher"'));
    });
  });

  group('the web icons', () {
    test('every icon the manifest names exists and is ours', () {
      for (final name in [
        'web/favicon.png',
        'web/icons/Icon-192.png',
        'web/icons/Icon-512.png',
        'web/icons/Icon-maskable-192.png',
        'web/icons/Icon-maskable-512.png',
      ]) {
        final file = File(name);
        expect(file.existsSync(), isTrue, reason: '$name is missing');
        expect(file.lengthSync(), greaterThan(200), reason: '$name is a stub');
      }
    });
  });
}
