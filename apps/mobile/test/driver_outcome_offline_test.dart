/// A driver's outcomes survive a dead network (P0-MOB-002).
///
/// Same requirement as the operator round, same mechanism, different door: a
/// driver in a valley records "delivered" at three gates, and the outcomes
/// must reach the platform later — once each. The queue kind is `run_outcome`
/// and the replay path is the RUN-scoped endpoint, carried on the operation's
/// `targetRef`, with the captured operation id as the idempotency key the
/// platform will recognise.
///
/// Also under test: a considered refusal (4xx) surfaces to the driver when
/// online and marks the operation as a conflict when replayed — a rejected
/// outcome must not be retried nightly forever.
library;

import 'dart:io';

import 'package:flutter_test/flutter_test.dart';
import 'package:lacteva_mobile/src/api.dart';
import 'package:lacteva_mobile/src/offline/offline_client.dart';
import 'package:lacteva_mobile/src/offline/queue.dart';
import 'package:lacteva_mobile/src/offline/store.dart';

class _FakePlatform extends ApiClient {
  _FakePlatform({this.offline = false, this.refuseWith});

  bool offline;
  ApiException? refuseWith;

  final List<String> paths = [];
  final List<String> keys = [];
  final List<Map<String, dynamic>> recorded = [];

  @override
  Future<dynamic> sendIdempotent(
    String method,
    String path, {
    required String idempotencyKey,
    Object? body,
  }) async {
    if (offline) throw const SocketException('no route to host');
    if (refuseWith != null) throw refuseWith!;
    paths.add(path);
    final already = keys.contains(idempotencyKey);
    keys.add(idempotencyKey);
    if (!already) recorded.add((body as Map).cast<String, dynamic>());
    return {'customer_id': 'cus', 'delivery_status': 'delivered'};
  }

  @override
  Future<Map<String, dynamic>> recordRunOutcome({
    required String runId,
    required String customerId,
    required String status,
    String? quantity,
    String? notes,
    String? idempotencyKey,
  }) async {
    if (offline) throw const SocketException('no route to host');
    if (refuseWith != null) throw refuseWith!;
    final row = {'run': runId, 'customer_id': customerId, 'status': status};
    recorded.add(row);
    return {'customer_id': customerId, 'delivery_status': status};
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
  Future<Map<String, dynamic>> recordRunOutcome({
    required String runId,
    required String customerId,
    required String status,
    String? quantity,
    String? notes,
    String? idempotencyKey,
  }) => platform.recordRunOutcome(
    runId: runId,
    customerId: customerId,
    status: status,
    quantity: quantity,
    notes: notes,
    idempotencyKey: idempotencyKey,
  );

  @override
  Future<Map<String, dynamic>> pushSyncBatch({
    required String deviceId,
    required List<Map<String, dynamic>> operations,
  }) => platform.pushSyncBatch(deviceId: deviceId, operations: operations);
}

void main() {
  test('outcomes captured with no signal reach the platform later, once each', () async {
    final platform = _FakePlatform(offline: true);
    final client = _TestOfflineClient(platform, forceOffline: true);

    for (final customer in ['cus-1', 'cus-2', 'cus-3']) {
      final result = await client.recordRunOutcomeOffline(
        runId: 'run-1',
        customerId: customer,
        status: 'delivered',
      );
      expect(result['_queued'], isTrue);
      // NO amount on the optimistic result — the phone must not price milk.
      expect(result.containsKey('amount'), isFalse);
    }
    expect(client.pendingCount, 3);

    platform.offline = false;
    client.forceOffline = false;
    final synced = await client.syncNow();

    expect(synced.applied, 3);
    expect(client.pendingCount, 0);
    // Replayed to the RUN-scoped door, not the operator's endpoint.
    expect(
      platform.paths,
      everyElement(startsWith('/v1/delivery-runs/run-1/stops/')),
    );
    expect(platform.recorded, hasLength(3));
  });

  test('a second sync replays nothing — the keys are remembered', () async {
    final platform = _FakePlatform(offline: true);
    final client = _TestOfflineClient(platform, forceOffline: true);
    await client.recordRunOutcomeOffline(
      runId: 'run-1',
      customerId: 'cus-1',
      status: 'delivered',
    );

    platform.offline = false;
    client.forceOffline = false;
    await client.syncNow();
    final again = await client.syncNow();

    expect(again.applied, 0);
    expect(platform.recorded, hasLength(1));
  });

  test('online, a considered refusal reaches the driver instead of the queue', () async {
    final platform = _FakePlatform(
      refuseWith: ApiException(409, 'a completed run cannot record outcomes'),
    );
    final client = _TestOfflineClient(platform);

    expect(
      () => client.recordRunOutcomeOffline(
        runId: 'run-1',
        customerId: 'cus-1',
        status: 'delivered',
      ),
      throwsA(isA<ApiException>()),
    );
    expect(client.pendingCount, 0, reason: 'a refusal must not be queued');
  });

  test('a refusal on replay parks the outcome as a conflict, not a retry loop', () async {
    final platform = _FakePlatform(offline: true);
    final client = _TestOfflineClient(platform, forceOffline: true);
    await client.recordRunOutcomeOffline(
      runId: 'run-1',
      customerId: 'cus-1',
      status: 'delivered',
    );

    platform.offline = false;
    platform.refuseWith = ApiException(404, 'that customer is not a stop on this run');
    client.forceOffline = false;
    final synced = await client.syncNow();

    expect(synced.applied, 0);
    expect(client.pendingCount, 0, reason: 'a 4xx is parked, not left pending');
  });
}
