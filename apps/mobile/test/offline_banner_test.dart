/// The sign-in screen tells the operator their captured work is safe
/// (P1-MOBILE-COUNTER-001 §5.7).
///
/// After a restart while offline the operator cannot sign in — but the durable
/// queue is loaded before authentication and its COUNT (nothing more) is
/// shown, so nobody stands at a dead phone wondering whether the morning's
/// milk survived. Kept apart from restart_offline_test.dart deliberately:
/// widget tests initialize the test binding for their whole file, and real
/// file-IO tests under that binding time out intermittently.
library;

import 'package:flutter/material.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:lacteva_mobile/src/centers.dart';
import 'package:lacteva_mobile/src/offline/offline_client.dart';
import 'package:lacteva_mobile/src/offline/queue.dart';
import 'package:lacteva_mobile/src/offline/store.dart';

class _MemClient extends OfflineApiClient {
  _MemClient()
    : super(
        queue: SyncQueue(MemoryOfflineStore()),
        deviceId: 'test-device',
        forceOffline: true,
      );
}

void main() {
  testWidgets('the sign-in screen says the captured work is safe', (
    tester,
  ) async {
    final client = _MemClient();
    // A morning's capture sits in the queue; the operator is signed out.
    await client.recordDeliveryOffline(
      customerId: 'cus-1',
      deliveryDate: '2026-08-19',
      slot: 'morning',
      status: 'delivered',
    );

    await tester.pumpWidget(MaterialApp(home: LoginScreen(client: client)));
    await tester.pumpAndSettle();

    expect(
      find.textContaining('safe on this phone and will sync after you sign'),
      findsOneWidget,
    );
  });
}
