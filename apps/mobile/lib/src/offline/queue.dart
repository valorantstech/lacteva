import 'dart:math';

import 'store.dart';

/// Lifecycle of one queued operation (OFF-001).
///
/// PENDING  — captured, waiting for connectivity
/// SYNCING  — handed to the server, outcome unknown (a crash here is safe:
///            the operation id makes the retry idempotent)
/// SYNCED   — the platform applied it
/// FAILED   — transient failure; retried on an exponential backoff
/// CONFLICT — the world moved on; needs a human, never a silent overwrite
enum SyncState { pending, syncing, synced, failed, conflict }

SyncState _stateFrom(String name) => SyncState.values.firstWhere(
  (s) => s.name == name,
  orElse: () => SyncState.pending,
);

/// One captured operation, durably queued.
class QueuedOperation {
  QueuedOperation({
    required this.operationId,
    required this.kind,
    required this.sequence,
    this.clientReference,
    this.targetRef,
    Map<String, dynamic>? payload,
    this.state = SyncState.pending,
    this.attempts = 0,
    this.nextAttemptAt,
    this.serverId,
    this.conflictReason,
    this.conflictDetail,
    this.error,
    required this.recordedAt,
  }) : payload = payload ?? <String, dynamic>{};

  factory QueuedOperation.fromJson(Map<String, dynamic> json) =>
      QueuedOperation(
        operationId: json['operation_id'] as String,
        kind: json['kind'] as String,
        sequence: json['sequence'] as int,
        clientReference: json['client_reference'] as String?,
        targetRef: json['target_ref'] as String?,
        payload:
            (json['payload'] as Map?)?.cast<String, dynamic>() ??
            <String, dynamic>{},
        state: _stateFrom(json['state'] as String? ?? 'pending'),
        attempts: json['attempts'] as int? ?? 0,
        nextAttemptAt: json['next_attempt_at'] == null
            ? null
            : DateTime.parse(json['next_attempt_at'] as String),
        serverId: json['server_id'] as String?,
        conflictReason: json['conflict_reason'] as String?,
        conflictDetail: json['conflict_detail'] as String?,
        error: json['error'] as String?,
        recordedAt: DateTime.parse(json['recorded_at'] as String),
      );

  final String operationId;
  final String kind;
  final int sequence;
  final String? clientReference;
  final String? targetRef;
  final Map<String, dynamic> payload;
  final DateTime recordedAt;

  SyncState state;
  int attempts;
  DateTime? nextAttemptAt;
  String? serverId;
  String? conflictReason;
  String? conflictDetail;
  String? error;

  bool get isTerminal => state == SyncState.synced;

  Map<String, dynamic> toJson() => {
    'operation_id': operationId,
    'kind': kind,
    'sequence': sequence,
    'client_reference': clientReference,
    'target_ref': targetRef,
    'payload': payload,
    'state': state.name,
    'attempts': attempts,
    'next_attempt_at': nextAttemptAt?.toIso8601String(),
    'server_id': serverId,
    'conflict_reason': conflictReason,
    'conflict_detail': conflictDetail,
    'error': error,
    'recorded_at': recordedAt.toIso8601String(),
  };

  /// The wire shape the sync endpoint expects.
  Map<String, dynamic> toOperation() => {
    'operation_id': operationId,
    'kind': kind,
    'sequence': sequence,
    'client_reference': clientReference,
    'target_ref': targetRef,
    'payload': payload,
    'recorded_at': recordedAt.toIso8601String(),
  };
}

/// A snapshot of the queue for the UI — cheap to build, safe to rebuild on.
class SyncSnapshot {
  const SyncSnapshot({
    required this.pending,
    required this.syncing,
    required this.synced,
    required this.failed,
    required this.conflicts,
    required this.lastSyncAt,
    required this.online,
    required this.syncing0,
  });

  final int pending;
  final int syncing;
  final int synced;
  final int failed;
  final int conflicts;
  final DateTime? lastSyncAt;
  final bool online;

  /// True while a sync run is in flight (distinct from per-item SYNCING).
  final bool syncing0;

  int get outstanding => pending + syncing + failed;

  bool get hasWork => outstanding > 0;
}

/// The durable queue: the device's memory of work the platform has not
/// acknowledged yet.
///
/// Backoff mirrors the platform's own consumer retry schedule so an operator
/// and an engineer are looking at the same behaviour on both sides of the
/// connection.
class SyncQueue {
  SyncQueue(this._store, {this.maxAttempts = 5});

  static const _version = 1;

  final OfflineStore _store;
  final int maxAttempts;

  final List<QueuedOperation> _operations = [];
  final Map<String, String> _idMap = {}; // local reference -> server id
  DateTime? _lastSyncAt;
  bool _loaded = false;

  List<QueuedOperation> get operations => List.unmodifiable(_operations);

  DateTime? get lastSyncAt => _lastSyncAt;

  Map<String, String> get idMap => Map.unmodifiable(_idMap);

  /// Exponential backoff with a ceiling: 2s, 4s, 8s, 16s, … capped at 5 min.
  static Duration backoff(int attempt) {
    final seconds = min(pow(2, attempt.clamp(1, 20)).toInt(), 300);
    return Duration(seconds: seconds);
  }

  Future<void> load() async {
    if (_loaded) return;
    final data = await _store.read();
    _operations.clear();
    _idMap.clear();
    if (data != null) {
      for (final raw in (data['operations'] as List? ?? const [])) {
        _operations.add(
          QueuedOperation.fromJson((raw as Map).cast<String, dynamic>()),
        );
      }
      _idMap.addAll(
        ((data['id_map'] as Map?) ?? const {}).map(
          (k, v) => MapEntry('$k', '$v'),
        ),
      );
      final last = data['last_sync_at'] as String?;
      _lastSyncAt = last == null ? null : DateTime.tryParse(last);
    }
    // A process that died mid-flight leaves SYNCING rows behind. They are
    // safe to retry — the operation id makes replay idempotent — so recover
    // them rather than stranding an operator's morning.
    for (final op in _operations) {
      if (op.state == SyncState.syncing) op.state = SyncState.pending;
    }
    _loaded = true;
  }

  Future<void> save() async {
    await _store.write({
      'version': _version,
      'operations': _operations.map((o) => o.toJson()).toList(),
      'id_map': _idMap,
      'last_sync_at': _lastSyncAt?.toIso8601String(),
    });
  }

  Future<QueuedOperation> enqueue({
    required String operationId,
    required String kind,
    String? clientReference,
    String? targetRef,
    Map<String, dynamic>? payload,
    DateTime? recordedAt,
  }) async {
    final op = QueuedOperation(
      operationId: operationId,
      kind: kind,
      sequence: _nextSequence(),
      clientReference: clientReference,
      targetRef: targetRef,
      payload: payload,
      recordedAt: recordedAt ?? DateTime.now().toUtc(),
    );
    _operations.add(op);
    await save();
    return op;
  }

  int _nextSequence() => _operations.isEmpty
      ? 1
      : _operations.map((o) => o.sequence).reduce(max) + 1;

  /// Operations eligible for the next push, in capture order.
  List<QueuedOperation> due({DateTime? now}) {
    final at = now ?? DateTime.now().toUtc();
    final ready = _operations.where((op) {
      if (op.state == SyncState.pending) return true;
      if (op.state == SyncState.failed && op.attempts < maxAttempts) {
        return op.nextAttemptAt == null || !op.nextAttemptAt!.isAfter(at);
      }
      return false;
    }).toList();
    ready.sort((a, b) => a.sequence.compareTo(b.sequence));
    return ready;
  }

  void markSyncing(Iterable<QueuedOperation> ops) {
    for (final op in ops) {
      op.state = SyncState.syncing;
      op.attempts += 1;
    }
  }

  /// Apply one server result to its operation.
  void applyResult(
    QueuedOperation op,
    Map<String, dynamic> result, {
    DateTime? now,
  }) {
    final status = result['status'] as String? ?? 'failed';
    op.serverId = result['server_id'] as String?;
    final conflict = (result['conflict'] as Map?)?.cast<String, dynamic>();
    switch (status) {
      case 'applied':
      case 'duplicate':
        op.state = SyncState.synced;
        op.error = null;
        op.conflictReason = null;
        op.conflictDetail = null;
      case 'conflict':
        // A conflict that still applied (a flagged rate-card change) is done
        // with the platform but must stay visible to the operator.
        op.state = SyncState.conflict;
        op.conflictReason = conflict?['reason'] as String?;
        op.conflictDetail = conflict?['detail'] as String?;
      default:
        op.state = SyncState.failed;
        op.error = result['error'] as String? ?? 'sync failed';
        op.nextAttemptAt = (now ?? DateTime.now().toUtc()).add(
          backoff(op.attempts),
        );
    }
    if (op.clientReference != null && op.serverId != null) {
      _idMap[op.clientReference!] = op.serverId!;
    }
  }

  /// The whole push failed (no connectivity, server unreachable): every
  /// operation in it goes back to FAILED with a backoff, never lost.
  void markBatchFailed(
    Iterable<QueuedOperation> ops,
    String error, {
    DateTime? now,
  }) {
    final at = now ?? DateTime.now().toUtc();
    for (final op in ops) {
      op.state = SyncState.failed;
      op.error = error;
      op.nextAttemptAt = at.add(backoff(op.attempts));
    }
  }

  /// Cancellation puts in-flight work back, untouched, for the next run.
  void releaseSyncing() {
    for (final op in _operations) {
      if (op.state == SyncState.syncing) {
        op.state = SyncState.pending;
        op.attempts = (op.attempts - 1).clamp(0, 1 << 30);
      }
    }
  }

  void recordSyncTime(DateTime at) => _lastSyncAt = at;

  /// Retry everything that failed or exhausted its attempts (the operator's
  /// "try again" button).
  void retryAll() {
    for (final op in _operations) {
      if (op.state == SyncState.failed) {
        op.attempts = 0;
        op.nextAttemptAt = null;
        op.state = SyncState.pending;
      }
    }
  }

  /// Resolve a local reference to a server id, if sync has learned one.
  String? resolve(String reference) => _idMap[reference];

  /// Drop synced history older than [keep] entries — the queue is a work
  /// list, not an archive; the platform holds the record of truth.
  Future<void> prune({int keep = 200}) async {
    final synced = _operations
        .where((o) => o.state == SyncState.synced)
        .toList();
    if (synced.length <= keep) return;
    final drop = synced.take(synced.length - keep).toSet();
    _operations.removeWhere(drop.contains);
    await save();
  }

  SyncSnapshot snapshot({required bool online, bool running = false}) =>
      SyncSnapshot(
        pending: _count(SyncState.pending),
        syncing: _count(SyncState.syncing),
        synced: _count(SyncState.synced),
        failed: _count(SyncState.failed),
        conflicts: _count(SyncState.conflict),
        lastSyncAt: _lastSyncAt,
        online: online,
        syncing0: running,
      );

  int _count(SyncState state) =>
      _operations.where((o) => o.state == state).length;
}
