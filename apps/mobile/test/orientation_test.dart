/// The app does not rotate (WO-110 §8).
///
/// The owner's moto g57 came up sideways: nothing locked orientation — not
/// the manifest, not `lib/`, not the iOS plist. A delivery boy holds the
/// phone one-handed while pouring milk, so all three say portrait now, and
/// this test refuses a build where any of them stops saying it. WO-96's
/// responsive matrix still exercises landscape sizes as a layout-robustness
/// check (split screen and foldables present a wide window); that is about
/// surviving a shape, not offering it.
library;

import 'dart:io';

import 'package:flutter/services.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:lacteva_mobile/main.dart' as app;

void main() {
  TestWidgetsFlutterBinding.ensureInitialized();

  test('start-up asks the platform for portrait, and nothing else', () async {
    final calls = <MethodCall>[];
    TestDefaultBinaryMessengerBinding.instance.defaultBinaryMessenger.setMockMethodCallHandler(
      SystemChannels.platform,
      (call) async {
        calls.add(call);
        return null;
      },
    );
    addTearDown(
      () => TestDefaultBinaryMessengerBinding.instance.defaultBinaryMessenger
          .setMockMethodCallHandler(SystemChannels.platform, null),
    );
    await app.lockOrientation();
    final orientation = calls.where((c) => c.method == 'SystemChrome.setPreferredOrientations');
    expect(orientation, hasLength(1));
    expect(orientation.single.arguments, ['DeviceOrientation.portraitUp']);
    expect(app.lockedOrientations, [DeviceOrientation.portraitUp]);
  });

  test('main() locks orientation before the first frame', () {
    final source = File('lib/main.dart').readAsStringSync();
    final lock = source.indexOf('await lockOrientation();');
    final run = source.indexOf('runApp(');
    expect(lock, greaterThan(-1), reason: 'main.dart no longer locks orientation');
    expect(lock, lessThan(run), reason: 'the lock must come before runApp');
  });

  test('Android: MainActivity is portrait before Flutter even starts', () {
    final manifest = File('android/app/src/main/AndroidManifest.xml').readAsStringSync();
    final activity = RegExp(r'<activity[\s\S]*?android:name="\.MainActivity"[\s\S]*?>').firstMatch(manifest);
    expect(activity, isNotNull);
    expect(activity!.group(0), contains('android:screenOrientation="portrait"'));
  });

  test('iOS: portrait only, on iPhone and on iPad', () {
    final plist = File('ios/Runner/Info.plist').readAsStringSync();
    for (final key in ['UISupportedInterfaceOrientations', 'UISupportedInterfaceOrientations~ipad']) {
      final array = RegExp('<key>$key</key>\\s*<array>([\\s\\S]*?)</array>').firstMatch(plist);
      expect(array, isNotNull, reason: '$key is missing');
      final values = RegExp(r'<string>(.*?)</string>').allMatches(array!.group(1)!).map((m) => m.group(1)).toList();
      expect(values, ['UIInterfaceOrientationPortrait'], reason: '$key allows rotation');
    }
  });
}
