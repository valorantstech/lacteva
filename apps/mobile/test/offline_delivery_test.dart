/// Capturing the delivery round with no signal (DEMO-012 §9).
///
/// The requirement that actually matters here is not "works offline" — it is
/// **do not silently lose captured delivery data, and do not submit it
/// twice.** A rider walking a round in a valley has no way to tell whether a
/// tap reached the platform, so the app has to be able to answer that later,
/// truthfully, and the replay has to be safe.
///
/// The safety comes from the platform, not from cleverness here: each queued
/// delivery carries the idempotency key it was captured with, and
/// `delivery_router` is an `IdempotentRoute`. A delivery that WAS recorded
/// before the phone lost the reply is recognised as the same operation rather
/// than written a second time.
library;

import 'dart:io';

import 'package:flutter_test/flutter_test.dart';
import 'package:lacteva_mobile/src/api.dart';
import 'package:lacteva_mobile/src/offline/offline_client.dart';
import 'package:lacteva_mobile/src/offline/queue.dart';
import 'package:lacteva_mobile/src/offline/store.dart';

/// A platform that can be unplugged, and that remembers every idempotency key
/// it was shown — which is the whole point of the exercise.
class _FakePlatform extends ApiClient {
  _FakePlatform({this.offline = false, this.refuseWith});

  bool offline;

  /// A considered refusal from the platform (4xx), as opposed to a dead
  /// network. The two must be handled differently and this is how the test
  /// tells them apart.
  ApiException? refuseWith;

  final List<Map<String, dynamic>> recorded = [];
  final List<String> keys = [];

  @override
  Future<dynamic> sendIdempotent(
    String method,
    String path, {
    required String idempotencyKey,
    Object? body,
  }) async {
    if (offline) throw const SocketException('no route to host');
    if (refuseWith != null) throw refuseWith!;
    keys.add(idempotencyKey);
    // The platform's own idempotency: a key it has seen returns the first
    // result rather than writing again.
    final already = keys.where((k) => k == idempotencyKey).length > 1;
    if (!already) recorded.add((body as Map).cast<String, dynamic>());
    return {'id': 'srv-${recorded.length}', 'status': 'delivered'};
  }

  @override
  Future<Map<String, dynamic>> recordDelivery({
    required String customerId,
    required String deliveryDate,
    required String slot,
    required String status,
    String? quantity,
    String? notes,
  }) async {
    if (offline) throw const SocketException('no route to host');
    if (refuseWith != null) throw refuseWith!;
    final row = {
      'customer_id': customerId,
      'delivery_date': deliveryDate,
      'slot': slot,
      'status': status,
      if (quantity != null && quantity.isNotEmpty) 'quantity': quantity,
    };
    recorded.add(row);
    return {'id': 'srv-${recorded.length}', ...row};
  }

  @override
  Future<Map<String, dynamic>> pushSyncBatch({
    required String deviceId,
    required List<Map<String, dynamic>> operations,
  }) async {
    if (offline) throw const SocketException('no route to host');
    return {'results': []};
  }
}

OfflineApiClient _client(_FakePlatform platform, {bool forceOffline = false}) {
  // The fake IS the transport; the offline client wraps its own queue around
  // it. `forceOffline` is the switch the round uses to stop trying.
  return _TestOfflineClient(platform, forceOffline: forceOffline);
}

/// Delegates every network call to the fake platform while keeping the real
/// queue, so what is under test is the queueing and replay, not http.
class _TestOfflineClient extends OfflineApiClient {
  _TestOfflineClient(this.platform, {super.forceOffline})
    : super(queue: SyncQueue(MemoryOfflineStore()), deviceId: 'test-device');

  final _FakePlatform platform;

  @override
  Future<dynamic> sendIdempotent(
    String method,
    String path, {
    required String idempotencyKey,
    Object? body,
  }) => platform.sendIdempotent(
    method,
    path,
    idempotencyKey: idempotencyKey,
    body: body,
  );

  @override
  Future<Map<String, dynamic>> recordDelivery({
    required String customerId,
    required String deliveryDate,
    required String slot,
    required String status,
    String? quantity,
    String? notes,
  }) => platform.recordDelivery(
    customerId: customerId,
    deliveryDate: deliveryDate,
    slot: slot,
    status: status,
    quantity: quantity,
    notes: notes,
  );

  @override
  Future<Map<String, dynamic>> pushSyncBatch({
    required String deviceId,
    required List<Map<String, dynamic>> operations,
  }) => platform.pushSyncBatch(deviceId: deviceId, operations: operations);
}

void main() {
  test('a round captured with no signal reaches the platform later', () async {
    final platform = _FakePlatform(offline: true);
    final client = _client(platform, forceOffline: true);

    for (final name in ['cus-1', 'cus-2', 'cus-3']) {
      final result = await client.recordDeliveryOffline(
        customerId: name,
        deliveryDate: '2026-08-13',
        slot: 'morning',
        status: 'delivered',
      );
      // The app is honest about what happened: queued, not confirmed.
      expect(result['_queued'], isTrue);
    }
    expect(platform.recorded, isEmpty, reason: 'still no signal');
    expect(client.pendingCount, 3);

    // The rider reaches the road.
    platform.offline = false;
    client.forceOffline = false;
    final run = await client.syncNow();

    expect(run.applied, 3);
    expect(run.failed, 0);
    expect(platform.recorded.length, 3);
    expect(client.pendingCount, 0);
    expect(
      platform.recorded.map((r) => r['customer_id']),
      containsAll(['cus-1', 'cus-2', 'cus-3']),
    );
  });

  test('a queued delivery carries NO amount', () async {
    // The phone does not know what the milk is worth and must not guess: the
    // rate lives on the customer's plan and the arithmetic is the platform's.
    // An optimistic figure here is a number a customer could be shown and
    // later contradicted.
    final platform = _FakePlatform(offline: true);
    final client = _client(platform, forceOffline: true);

    final echo = await client.recordDeliveryOffline(
      customerId: 'cus-1',
      deliveryDate: '2026-08-13',
      slot: 'morning',
      status: 'delivered',
      quantity: '2.500',
    );

    expect(echo.containsKey('amount'), isFalse);
    expect(echo.containsKey('unit_price'), isFalse);
    expect(echo['quantity'], isNull, reason: 'the echo is not a receipt');
  });

  test('replaying twice does not deliver twice', () async {
    final platform = _FakePlatform(offline: true);
    final client = _client(platform, forceOffline: true);
    await client.recordDeliveryOffline(
      customerId: 'cus-1',
      deliveryDate: '2026-08-13',
      slot: 'morning',
      status: 'delivered',
    );

    platform.offline = false;
    client.forceOffline = false;
    await client.syncNow();
    await client.syncNow(); // a second sync, e.g. the user tapped again

    expect(platform.recorded.length, 1);
    expect(client.pendingCount, 0);
  });

  test('each captured delivery gets its own idempotency key', () async {
    final platform = _FakePlatform(offline: true);
    final client = _client(platform, forceOffline: true);
    for (var i = 0; i < 5; i++) {
      await client.recordDeliveryOffline(
        customerId: 'cus-$i',
        deliveryDate: '2026-08-13',
        slot: 'morning',
        status: 'delivered',
      );
    }
    platform.offline = false;
    client.forceOffline = false;
    await client.syncNow();

    expect(platform.keys.length, 5);
    expect(platform.keys.toSet().length, 5, reason: 'keys must be unique');
  });

  test(
    'a refusal from the platform reaches the rider, not the queue',
    () async {
      // A 4xx is the platform's considered answer — "this slot is already
      // recorded", say. Hiding it in a queue that replays it nightly turns one
      // clear error into a haunting.
      final platform = _FakePlatform(
        refuseWith: ApiException(409, 'already recorded for this slot'),
      );
      final client = _client(platform);

      expect(
        () => client.recordDeliveryOffline(
          customerId: 'cus-1',
          deliveryDate: '2026-08-13',
          slot: 'morning',
          status: 'delivered',
        ),
        throwsA(isA<ApiException>()),
      );
      expect(client.pendingCount, 0, reason: 'a refusal is not queued work');
    },
  );

  test(
    'a delivery the platform rejects on replay stops being retried',
    () async {
      final platform = _FakePlatform(offline: true);
      final client = _client(platform, forceOffline: true);
      await client.recordDeliveryOffline(
        customerId: 'cus-1',
        deliveryDate: '2026-08-13',
        slot: 'morning',
        status: 'delivered',
      );

      // Signal returns, but the platform refuses this one for good.
      platform.offline = false;
      client.forceOffline = false;
      platform.refuseWith = ApiException(422, 'customer has no active plan');
      final run = await client.syncNow();

      expect(run.failed, 1);
      expect(platform.recorded, isEmpty);
      // It is out of the pending queue: a person has to look at it, rather than
      // the phone retrying a rejected delivery every night forever.
      final snapshot = client.snapshot();
      expect(snapshot.pending, 0);
    },
  );

  test('nothing is lost when the app is killed mid-round', () async {
    // The queue is file-backed in the real app; here the store is handed
    // between two clients, which is the same question: does a restart forget?
    final store = MemoryOfflineStore();
    final platform = _FakePlatform(offline: true);

    final first = _RestartableClient(platform, store, forceOffline: true);
    await first.recordDeliveryOffline(
      customerId: 'cus-1',
      deliveryDate: '2026-08-13',
      slot: 'morning',
      status: 'delivered',
    );
    expect(first.pendingCount, 1);

    // The app dies. A new one starts on the same store.
    final second = _RestartableClient(platform, store);
    platform.offline = false;
    final run = await second.syncNow();

    expect(run.applied, 1);
    expect(platform.recorded.length, 1);
  });
}

/// Same as `_TestOfflineClient` but sharing a caller-supplied store, so a
/// "restart" can be simulated.
class _RestartableClient extends OfflineApiClient {
  _RestartableClient(this.platform, OfflineStore store, {super.forceOffline})
    : super(queue: SyncQueue(store), deviceId: 'test-device');

  final _FakePlatform platform;

  @override
  Future<dynamic> sendIdempotent(
    String method,
    String path, {
    required String idempotencyKey,
    Object? body,
  }) => platform.sendIdempotent(
    method,
    path,
    idempotencyKey: idempotencyKey,
    body: body,
  );

  @override
  Future<Map<String, dynamic>> recordDelivery({
    required String customerId,
    required String deliveryDate,
    required String slot,
    required String status,
    String? quantity,
    String? notes,
  }) => platform.recordDelivery(
    customerId: customerId,
    deliveryDate: deliveryDate,
    slot: slot,
    status: status,
    quantity: quantity,
    notes: notes,
  );

  @override
  Future<Map<String, dynamic>> pushSyncBatch({
    required String deviceId,
    required List<Map<String, dynamic>> operations,
  }) => platform.pushSyncBatch(deviceId: deviceId, operations: operations);
}
