import 'dart:async';
import 'dart:math';

import '../api.dart';
import 'queue.dart';
import 'sync_engine.dart';

/// An [ApiClient] that keeps working when the network does not (OFF-001).
///
/// Offline is an implementation detail: the collection wizard calls the same
/// methods it always did. When a call cannot reach the platform, the
/// operation is appended to the durable queue and the screen is answered from
/// a local projection of that queue, so the operator's flow never breaks.
///
/// Two things this client deliberately does NOT do:
///
/// * **Decide anything.** It never prices milk, never validates a supplier,
///   never advances a state the server would refuse. It records what the
///   operator did and lets the platform judge it on sync (BR-0021). Fields
///   the server owns are reported as pending, not guessed.
/// * **Swallow business errors.** A 409 from the platform is an answer, not a
///   connectivity problem: it is rethrown exactly as online. Only transport
///   failures fall back to the queue.
class OfflineApiClient extends ApiClient {
  OfflineApiClient({
    required this.queue,
    required this.deviceId,
    SyncEngine? engine,
    this.forceOffline = false,
  }) {
    this.engine =
        engine ?? SyncEngine(client: this, queue: queue, deviceId: deviceId);
  }

  final SyncQueue queue;
  final String deviceId;
  late final SyncEngine engine;

  /// Test/demo switch: pretend the network is gone.
  bool forceOffline;

  bool _believedOnline = true;

  bool get isOnline => !forceOffline && _believedOnline;

  final _random = Random();

  String _localId(String prefix) =>
      'local-$prefix-${DateTime.now().toUtc().microsecondsSinceEpoch}-'
      '${_random.nextInt(1 << 20)}';

  String _operationId() {
    // A UUIDv4-shaped identifier: the server uses it as the idempotency key,
    // so it must be unique per captured operation and stable across retries.
    final bytes = List<int>.generate(16, (_) => _random.nextInt(256));
    bytes[6] = (bytes[6] & 0x0f) | 0x40;
    bytes[8] = (bytes[8] & 0x3f) | 0x80;
    final hex = bytes.map((b) => b.toRadixString(16).padLeft(2, '0')).join();
    return '${hex.substring(0, 8)}-${hex.substring(8, 12)}-${hex.substring(12, 16)}-'
        '${hex.substring(16, 20)}-${hex.substring(20)}';
  }

  // --- intercepted collection calls ---------------------------------------

  @override
  Future<Map<String, dynamic>> openCollectionSession(String centerId) async {
    if (isOnline) {
      try {
        return await super.openCollectionSession(centerId);
      } on ApiException {
        rethrow; // the platform answered; that answer stands
      } catch (_) {
        _believedOnline = false;
      }
    }
    final reference = _localId('session');
    await queue.enqueue(
      operationId: _operationId(),
      kind: 'open_session',
      clientReference: reference,
      payload: {'center_id': centerId, 'label': 'mobile-offline'},
    );
    return {
      'id': reference,
      'center_id': centerId,
      'status': 'open',
      'label': 'mobile-offline',
      'offline': true,
    };
  }

  @override
  Future<Map<String, dynamic>> txStep(String path, {Object? body}) async {
    final step = _OfflineStep.parse(path);
    if (step == null) {
      return super.txStep(path, body: body); // not a collection step
    }
    if (isOnline) {
      try {
        return await super.txStep(path, body: body);
      } on ApiException {
        rethrow;
      } catch (_) {
        _believedOnline = false;
      }
    }
    return _record(step, (body as Map?)?.cast<String, dynamic>() ?? const {});
  }

  Future<Map<String, dynamic>> _record(
    _OfflineStep step,
    Map<String, dynamic> payload,
  ) async {
    await queue.load();
    String? target = step.target;
    String? reference;
    if (step.kind == 'create_transaction') {
      // The session this transaction belongs to travels in the body, and may
      // itself be a local id created earlier while offline.
      final session = payload['session_id']?.toString();
      target = session == null ? null : (queue.resolve(session) ?? session);
      reference = _localId('tx');
    } else if (target != null) {
      // A reference the server already knows keeps its server id; a local one
      // stays local until sync learns the mapping.
      target = queue.resolve(target) ?? target;
    }
    await queue.enqueue(
      operationId: _operationId(),
      kind: step.kind,
      clientReference: reference,
      targetRef: target,
      payload: payload,
    );
    return _project(reference ?? target ?? 'unknown');
  }

  /// Build the transaction view the UI expects by folding the queued
  /// operations for this local id — a projection over the queue, in the same
  /// spirit as the platform's read models. Nothing here is authoritative; the
  /// server's version replaces it on sync.
  Map<String, dynamic> _project(String localId) {
    final view = <String, dynamic>{
      'id': localId,
      'state': 'NEW',
      'offline': true,
      'pricing_status': 'pending_sync',
      'pricing_detail': 'Priced by the platform when this device syncs.',
      'rejected_reason': null,
      'net_weight': null,
      'fat': null,
      'snf': null,
      'clr': null,
      'gross_amount': null,
      'unit_price': null,
      'currency': null,
    };
    for (final op in queue.operations) {
      if (op.targetRef != localId && op.clientReference != localId) continue;
      switch (op.kind) {
        case 'create_transaction':
          view['state'] = 'NEW';
        case 'identify_supplier':
          view['state'] = 'SUPPLIER_IDENTIFIED';
          view['supplier_hint'] = op.payload['value'];
        case 'receive_milk':
          view['state'] = 'MILK_RECEIVED';
          view['milk_type'] = op.payload['milk_type'];
        case 'capture_weight':
          view['state'] = 'QUALITY_PENDING';
          // An echo of what the operator entered, not a computed payable:
          // the platform recomputes and owns the authoritative value.
          final gross = _toDouble(op.payload['gross']);
          final tare = _toDouble(op.payload['tare']);
          if (gross != null && tare != null) view['net_weight'] = gross - tare;
        case 'capture_quality':
          view['state'] = 'PRICING_PENDING';
          view['fat'] = _toDouble(op.payload['fat']);
          view['snf'] = _toDouble(op.payload['snf']);
          view['clr'] = _toDouble(op.payload['clr']);
        case 'accept':
          view['state'] = 'ACCEPTED';
        case 'reject':
          view['state'] = 'REJECTED';
          view['rejected_reason'] = op.payload['reason'];
        case 'complete':
          view['state'] = 'COMPLETED';
        case 'cancel':
          view['state'] = 'CANCELLED';
      }
    }
    return view;
  }

  static double? _toDouble(Object? value) =>
      value == null ? null : double.tryParse(value.toString());

  /// Try to drain the queue. Safe to call often — it no-ops while a run is in
  /// flight and when nothing is due.
  // --- DEMO-012: deliveries -------------------------------------------------
  //
  // A delivery is captured differently from a collection, on purpose.
  //
  // A collection is a multi-step state machine — open a session, identify a
  // supplier, weigh, test, accept — so it goes through the batch protocol at
  // `/v1/sync/collection`, which understands local ids and can stitch the
  // steps together on arrival. A delivery is ONE idempotent POST. Pushing it
  // through the batch protocol would mean teaching that endpoint a second
  // vocabulary for no benefit.
  //
  // Instead each queued delivery carries the idempotency key it was captured
  // with, and replay sends the SAME key. `delivery_router` is an
  // `IdempotentRoute`, so a delivery that was actually recorded before the
  // phone lost the reply is recognised as the same operation rather than
  // written twice. That is the whole answer to "prevent duplicate
  // submissions" (§9): it is the platform's guarantee, not a local guess.

  /// How many captured operations are still on this device.
  int get pendingCount => snapshot().outstanding;

  /// Record a delivery, online or not.
  ///
  /// Returns the platform's response when it went through, or a local echo
  /// marked `_queued` when it did not. The caller shows the difference; it
  /// never pretends the queued one is confirmed.
  Future<Map<String, dynamic>> recordDeliveryOffline({
    required String customerId,
    required String deliveryDate,
    required String slot,
    required String status,
    String? quantity,
    String? notes,
  }) async {
    if (isOnline) {
      try {
        return await recordDelivery(
          customerId: customerId,
          deliveryDate: deliveryDate,
          slot: slot,
          status: status,
          quantity: quantity,
          notes: notes,
        );
      } on ApiException {
        // The platform ANSWERED — a refusal is a real answer and must reach
        // the rider, not be hidden in a queue that will replay it forever.
        rethrow;
      } catch (_) {
        _believedOnline = false;
      }
    }
    await queue.load();
    await queue.enqueue(
      operationId: _operationId(),
      kind: 'record_delivery',
      clientReference: _localId('delivery'),
      payload: {
        'customer_id': customerId,
        'delivery_date': deliveryDate,
        'slot': slot,
        'status': status,
        if (quantity != null && quantity.isNotEmpty) 'quantity': quantity,
        if (notes != null && notes.isNotEmpty) 'notes': notes,
      },
    );
    return {
      'customer_id': customerId,
      'delivery_date': deliveryDate,
      'slot': slot,
      'status': status,
      // NO amount. The phone does not know what this is worth and must not
      // guess: the rate lives on the plan and the arithmetic is the
      // platform's. An optimistic figure here would be a number a customer
      // could be shown and later contradicted.
      '_queued': true,
    };
  }

  /// Replay queued deliveries, each with the key it was captured with.
  ///
  /// Returns (sent, failed). A refusal that is the platform's considered
  /// answer — 4xx — is not retried forever: it is marked failed so a person
  /// sees it, because replaying a rejected delivery nightly is how a queue
  /// becomes a haunted house.
  /// A driver's stop outcome, captured durably (P0-MOB-002).
  ///
  /// Same contract as `recordDeliveryOffline`: online, the platform answers
  /// now and a refusal reaches the driver; offline, the outcome goes into the
  /// SAME durable queue with the operation id that will be its idempotency
  /// key, so a replay after signal returns is recognised rather than recorded
  /// twice. `targetRef` carries the run-scoped path, because unlike a plain
  /// delivery the endpoint is addressed per run and stop.
  Future<Map<String, dynamic>> recordRunOutcomeOffline({
    required String runId,
    required String customerId,
    required String status,
    String? quantity,
    String? notes,
  }) async {
    if (isOnline) {
      try {
        return await recordRunOutcome(
          runId: runId,
          customerId: customerId,
          status: status,
          quantity: quantity,
          notes: notes,
        );
      } on ApiException {
        // The platform ANSWERED — a refusal (closed run, off-route customer)
        // is a real answer and must reach the driver now, not haunt a queue.
        rethrow;
      } catch (_) {
        _believedOnline = false;
      }
    }
    await queue.load();
    await queue.enqueue(
      operationId: _operationId(),
      kind: 'run_outcome',
      clientReference: _localId('outcome'),
      targetRef: '/v1/delivery-runs/$runId/stops/$customerId/outcome',
      payload: {
        'status': status,
        if (quantity != null && quantity.isNotEmpty) 'quantity': quantity,
        if (notes != null && notes.isNotEmpty) 'notes': notes,
      },
    );
    return {
      'customer_id': customerId,
      'status': status,
      // NO amount, for the operator round's reason: the phone must not guess
      // what milk is worth.
      '_queued': true,
    };
  }

  /// Drain queued driver outcomes — the same loop shape as `_drainDeliveries`,
  /// with the path read from each operation's `targetRef`.
  Future<(int, int)> _drainRunOutcomes() async {
    await queue.load();
    final mine = queue
        .due()
        .where((op) => op.kind == 'run_outcome' && op.targetRef != null)
        .toList(growable: false);
    if (mine.isEmpty) return (0, 0);
    var sent = 0;
    var failed = 0;
    for (final op in mine) {
      try {
        await sendIdempotent(
          'POST',
          op.targetRef!,
          idempotencyKey: op.operationId,
          body: op.payload,
        );
        queue.applyResult(op, {
          'operation_id': op.operationId,
          'status': 'applied',
        });
        sent++;
      } on ApiException catch (e) {
        if (e.status >= 400 && e.status < 500 && e.status != 409) {
          queue.applyResult(op, {
            'operation_id': op.operationId,
            'status': 'conflict',
            'detail': e.detail,
          });
        } else {
          queue.markBatchFailed([op], e.detail);
        }
        failed++;
      } catch (e) {
        queue.markBatchFailed([op], 'offline');
        failed++;
      }
    }
    await queue.save();
    return (sent, failed);
  }

  Future<(int, int)> _drainDeliveries() async {
    await queue.load();
    final mine = queue
        .due()
        .where((op) => op.kind == 'record_delivery')
        .toList(growable: false);
    if (mine.isEmpty) return (0, 0);
    var sent = 0;
    var failed = 0;
    for (final op in mine) {
      try {
        await sendIdempotent(
          'POST',
          '/v1/deliveries',
          idempotencyKey: op.operationId,
          body: op.payload,
        );
        queue.applyResult(op, {
          'operation_id': op.operationId,
          'status': 'applied',
        });
        sent++;
      } on ApiException catch (e) {
        if (e.status >= 400 && e.status < 500 && e.status != 409) {
          queue.applyResult(op, {
            'operation_id': op.operationId,
            'status': 'conflict',
            'detail': e.detail,
          });
        } else {
          queue.markBatchFailed([op], e.detail);
        }
        failed++;
      } catch (e) {
        queue.markBatchFailed([op], 'offline');
        failed++;
      }
    }
    await queue.save();
    return (sent, failed);
  }

  Future<SyncRunResult> syncNow() async {
    await queue.load();
    final (deliverySent, deliveryFailed) = await _drainDeliveries();
    final (outcomeSent, outcomeFailed) = await _drainRunOutcomes();
    final result = await engine.sync();
    if (result.error == null && deliveryFailed == 0 && outcomeFailed == 0) {
      _believedOnline = true;
    }
    // Deliveries fold into the same tally the collection engine reports, so
    // one screen can say "12 sent, 1 queued" without knowing which protocol
    // carried which operation.
    return SyncRunResult(
      applied: result.applied + deliverySent + outcomeSent,
      duplicates: result.duplicates,
      conflicts: result.conflicts,
      failed: result.failed + deliveryFailed + outcomeFailed,
      batches: result.batches,
      cancelled: result.cancelled,
      error: result.error,
      skipped: result.skipped,
    );
  }

  SyncSnapshot snapshot() =>
      queue.snapshot(online: isOnline, running: engine.isRunning);
}

/// The collection endpoints that can be captured offline, and how each maps
/// onto a sync operation kind. Every one has an online equivalent — there is
/// no offline-only capability.
class _OfflineStep {
  const _OfflineStep(this.kind, this.target);

  final String kind;
  final String? target;

  static _OfflineStep? parse(String path) {
    if (path == '/v1/milk-transactions') {
      // The target (session) comes from the body; filled by the caller.
      return const _OfflineStep('create_transaction', null);
    }
    final tx = RegExp(
      r'^/v1/milk-transactions/([^/]+)/([a-z]+)$',
    ).firstMatch(path);
    if (tx != null) {
      const kinds = {
        'identify': 'identify_supplier',
        'milk': 'receive_milk',
        'weight': 'capture_weight',
        'quality': 'capture_quality',
        'accept': 'accept',
        'reject': 'reject',
        'complete': 'complete',
        'cancel': 'cancel',
      };
      final kind = kinds[tx.group(2)];
      if (kind == null) return null;
      return _OfflineStep(kind, tx.group(1));
    }
    final close = RegExp(
      r'^/v1/collection-sessions/([^/]+)/close$',
    ).firstMatch(path);
    if (close != null) return _OfflineStep('close_session', close.group(1));
    return null;
  }
}
