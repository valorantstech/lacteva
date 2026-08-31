// Binding a registered instrument to this handset (WO-54).
//
// `DeviceBinding` was constructed nowhere at runtime before this screen: the
// wizard's read-assist path was reachable only from a test. These pin the
// screen that closes that, and the two things it must never do — offer a link
// that is not built, or list a profile nobody has proven.
import 'dart:io';

import 'package:flutter/material.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:lacteva_mobile/src/api.dart';
import 'package:lacteva_mobile/src/devices/binding_store.dart';
import 'package:lacteva_mobile/src/devices/frame_profile.dart';
import 'package:lacteva_mobile/src/devices/instruments_screen.dart';
import 'package:lacteva_mobile/src/offline/store.dart';

const _devices = [
  {
    'id': 'dev-analyzer',
    'category': 'milk_analyzer',
    'name': 'Bay analyzer',
    'serial_number': 'AN-1',
    'status': 'active',
  },
  {
    'id': 'dev-scale',
    'category': 'scale',
    'name': 'Bay scale',
    'serial_number': 'SC-1',
    'status': 'active',
  },
  {
    'id': 'dev-retired',
    'category': 'milk_analyzer',
    'name': 'Old analyzer',
    'serial_number': 'AN-0',
    'status': 'retired',
  },
];

class _Fake extends ApiClient {
  _Fake([this._rows = _devices]);
  final List<Map<String, dynamic>> _rows;
  @override
  Future<List<dynamic>> listCenterDevices(String centerId) async => _rows;
}

Future<void> _pump(WidgetTester tester, {ApiClient? client, BindingStore? store}) async {
  // Tall enough that the whole screen renders: a ListView builds lazily, and
  // a card below the fold is absent from the tree rather than merely unseen.
  tester.view.physicalSize = const Size(500, 2400);
  tester.view.devicePixelRatio = 1.0;
  addTearDown(tester.view.reset);
  await tester.pumpWidget(
    MaterialApp(
      home: InstrumentsScreen(
        client: client ?? _Fake(),
        centerId: 'c1',
        bindings: store ?? BindingStore(MemoryOfflineStore()),
      ),
    ),
  );
  await tester.pumpAndSettle();
}

void main() {
  testWidgets('lists the centre\'s active instruments, not the retired one', (tester) async {
    await _pump(tester);
    expect(find.text('Bay analyzer'), findsOneWidget);
    expect(find.text('Bay scale'), findsOneWidget);
    // A retired device must not be bindable: retiring one is how a dairy
    // stops trusting its readings.
    expect(find.text('Old analyzer'), findsNothing);
  });

  testWidgets('names the links that are not built, as words rather than dead buttons', (tester) async {
    await _pump(tester);
    expect(find.textContaining('Bluetooth Classic'), findsOneWidget);
    expect(find.textContaining('USB-OTG serial'), findsOneWidget);
    expect(find.textContaining('not built yet'), findsOneWidget);
    // A greyed-out Bluetooth button is a promise with a date nobody has set.
    for (final label in ['Bluetooth Classic (SPP)', 'USB-OTG serial']) {
      expect(
        find.byWidgetPredicate(
          (w) => (w is ButtonStyleButton) && w.child is Text && (w.child! as Text).data == label,
        ),
        findsNothing,
      );
    }
  });

  testWidgets('offers only profiles that have been proven against a capture', (tester) async {
    await _pump(tester);
    await tester.tap(find.byType(DropdownButtonFormField<String>).at(1));
    await tester.pumpAndSettle();
    // Today that is the simulator's, labelled as such — the unverified-profile
    // guard in frame_profile.dart is what keeps this list honest.
    for (final profile in shippedProfiles) {
      expect(profile.verified, isTrue);
    }
    expect(find.textContaining('simulator').hitTestable(), findsWidgets);
  });

  testWidgets('a saved binding survives a restart', (tester) async {
    final store = BindingStore(MemoryOfflineStore());
    await _pump(tester, store: store);

    await tester.enterText(find.widgetWithText(TextField, 'Host').first, '10.0.0.5');
    await tester.tap(find.widgetWithText(FilledButton, 'Save').first);
    await tester.pumpAndSettle();

    final reloaded = await store.load();
    expect(reloaded.analyzer, isNotNull);
    expect(reloaded.analyzer!.host, '10.0.0.5');
    expect(reloaded.analyzer!.deviceId, 'dev-analyzer');
    expect(reloaded.hasAnalyzer, isTrue);
  });

  testWidgets('a failed test read says so, and captures nothing', (tester) async {
    // WHY THIS ASSERTS THE FAILURE AND NOT THE READING. `testWidgets` runs
    // under TestWidgetsFlutterBinding, which sandboxes real sockets — a
    // connection here times out no matter what is listening. The successful
    // read is proven over a REAL socket in `device_bridge_test.dart`, at the
    // layer that owns it; what this screen owns is what the operator is told
    // when it does not work, and that nothing is recorded either way.
    await _pump(tester);
    await tester.enterText(find.widgetWithText(TextField, 'Host').first, '127.0.0.1');
    await tester.enterText(find.widgetWithText(TextField, 'Port').first, '1');
    await tester.tap(find.widgetWithText(OutlinedButton, 'Test read').first);
    for (var i = 0; i < 60 && find.textContaining('could not reach').evaluate().isEmpty; i++) {
      await tester.pump(const Duration(milliseconds: 200));
    }

    // Named host and port, because the answer is usually "it is switched off".
    expect(find.textContaining('could not reach 127.0.0.1:1'), findsOneWidget);
    // "Is the cable right" is a different question from "record this milk";
    // answering it against a transaction would put a test reading into a
    // farmer's payment. A failed test changes nothing at all.
    expect(find.textContaining('Saved'), findsNothing);
  });

  testWidgets('a centre with no instruments says capture by hand still works', (tester) async {
    await _pump(tester, client: _Fake(const []));
    expect(find.textContaining('capture by hand works either way'), findsWidgets);
  });

  testWidgets('an unreadable registry is not a centre with no instruments', (tester) async {
    await _pump(tester, client: _Failing());
    expect(find.textContaining('Could not load'), findsOneWidget);
  });
}

class _Failing extends ApiClient {
  @override
  Future<List<dynamic>> listCenterDevices(String centerId) async =>
      throw const SocketException('no route to host');
}
