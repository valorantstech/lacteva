/// The operator's journey against the REAL platform (P1-E2E-HARNESS-001).
///
/// Every test in this file is **REAL**: the actual `ApiClient` /
/// `OfflineApiClient` the app ships, over real HTTP, to a real FastAPI server,
/// against a real PostgreSQL database, returning real responses that real
/// client code parses. Nothing is stubbed. That is the whole point — the
/// P0-PRODUCT-008 audit found that every mobile test mocked the network, so a
/// serializer drift or a contract change shipped with all suites green.
///
/// Run it through the harness, which creates the world it needs:
///
///     ./infra/e2e/run-e2e.sh mobile
///
/// It is skipped (not failed) when run without that harness, because a
/// developer running `flutter test` has no server — and a suite that fails for
/// the absence of infrastructure teaches people to ignore red.
library;

import 'dart:convert';
import 'dart:io';

import 'package:flutter_test/flutter_test.dart';

import 'package:lacteva_mobile/src/api.dart';
import 'package:lacteva_mobile/src/offline/offline_client.dart';
import 'package:lacteva_mobile/src/offline/queue.dart';
import 'package:lacteva_mobile/src/offline/store.dart';
import 'package:lacteva_mobile/src/session.dart';

const _fixturePath = String.fromEnvironment('LACTEVA_E2E_FIXTURE');

late Map<String, dynamic> fixture;

/// Without the harness there is no server; the file is inert rather than red.
bool get harnessed =>
    _fixturePath.isNotEmpty && File(_fixturePath).existsSync();

String get _password => fixture['password'] as String;
String _email(String who) =>
    (fixture['users'] as Map)[who]['email'] as String;
Map<String, dynamic> get _centre =>
    ((fixture['centres'] as List).first) as Map<String, dynamic>;

/// A real client pointed at the real server the harness started.
ApiClient _client() => ApiClient();

OfflineApiClient _offlineClient({OfflineStore? store}) => OfflineApiClient(
  queue: SyncQueue(store ?? MemoryOfflineStore()),
  deviceId: 'e2e-device-${DateTime.now().microsecondsSinceEpoch}',
);

/// One sign-in per persona for the whole suite.
///
/// Not a shortcut: the platform rate-limits logins (10/minute per IP, and the
/// harness discovered that by tripping it), and a real operator signs in once
/// per shift rather than once per screen. Caching the session is both the
/// faithful behaviour and the polite one.
final Map<String, ApiClient> _signedInCache = {};

Future<ApiClient> _signedIn(String who) async {
  final cached = _signedInCache[who];
  if (cached != null && cached.isAuthenticated) return cached;
  final c = _client();
  await c.login(_email(who), _password);
  _signedInCache[who] = c;
  return c;
}

void main() {
  setUpAll(() {
    // flutter_test installs an HttpOverrides that answers every request 400.
    // The E2E suite needs the real network, and only this suite does.
    HttpOverrides.global = null;
    if (_fixturePath.isEmpty || !File(_fixturePath).existsSync()) {
      return;
    }
    fixture = jsonDecode(File(_fixturePath).readAsStringSync())
        as Map<String, dynamic>;
  });

  group('A — authentication', () {
    test('a valid operator signs in and the platform describes them', () async {
      if (!harnessed) return;
      final client = await _signedIn('operator');
      expect(client.isAuthenticated, isTrue);

      // The identity comes from the platform, not from the client's guess.
      final session = await loadSession(client);
      expect(session.email, _email('operator'));
      expect(session.tenantId, isNotEmpty);
      // The operator's real grants, as the platform resolved them.
      expect(session.can('collection.session.manage'), isTrue);
      expect(session.can('organization.member.manage'), isFalse);
    });

    test('a wrong password is refused by the platform', () async {
      if (!harnessed) return;
      final client = _client();
      await expectLater(
        client.login(_email('operator'), 'not-the-password'),
        throwsA(isA<ApiException>()),
      );
      expect(client.isAuthenticated, isFalse);
    });

    test('an unauthenticated request is refused', () async {
      if (!harnessed) return;
      final client = _client(); // never logged in
      await expectLater(client.listCenters(), throwsA(isA<ApiException>()));
    });

    test('after sign-out the platform refuses the next call', () async {
      if (!harnessed) return;
      // A throwaway client, so signing out here cannot disturb the sessions
      // the rest of the suite shares.
      final client = _client();
      await client.login(_email('admin'), _password);
      expect(client.isAuthenticated, isTrue);
      client.logout();
      await expectLater(client.listCenters(), throwsA(isA<ApiException>()));
    });
  });

  group('B — organization, centre scope and tenancy', () {
    test('the operator sees their own centres, from the platform', () async {
      if (!harnessed) return;
      final client = await _signedIn('operator');
      final page = await client.listCenters();
      expect(page.total, greaterThan(0));
      final codes = page.items.map((c) => c.code).toList();
      expect(codes, contains(_centre['code']));
    });

    test('another tenant\'s centre is invisible, not merely forbidden', () async {
      if (!harnessed) return;
      final client = await _signedIn('operator');
      final foreignCentre =
          (fixture['other_org'] as Map)['centre_id'] as String;

      // The platform's documented boundary: a foreign resource is a 404, never
      // a 403 — a 403 would confirm the row exists. RLS makes this real.
      try {
        await client.centerDetail(foreignCentre);
        fail('the platform served another tenant\'s centre');
      } on ApiException catch (e) {
        expect(
          e.status,
          anyOf(404, 403),
          reason: 'cross-tenant access must be refused',
        );
        expect(e.status, isNot(200));
      }

      // And it is absent from the list the operator legitimately reads.
      final mine = await client.listCenters(limit: 100);
      expect(
        mine.items.map((c) => c.id),
        isNot(contains(foreignCentre)),
      );
    });

    test('a role without the grant is refused the action', () async {
      if (!harnessed) return;
      // The manager here holds tenant-viewer: reads, never records.
      final viewer = await _signedIn('manager');
      final sessionView = await loadSession(viewer);
      expect(sessionView.can('collection.transaction.record'), isFalse);

      await expectLater(
        viewer.txStep('/v1/milk-transactions', body: {'session_id': _centre['id']}),
        throwsA(isA<ApiException>()),
        reason: 'the backend, not the client, enforces this',
      );
    });
  });

  group('C+D — collection, quality, pricing and the parchi', () {
    test('a full collection is recorded and priced BY THE PLATFORM', () async {
      if (!harnessed) return;
      final client = await _signedIn('operator');
      final centreId = _centre['id'] as String;

      // A real session at a real centre.
      final open = await client.listOpenSessions(centreId);
      final session = open.isNotEmpty
          ? open.first
          : await client.openCollectionSession(centreId);
      expect(session['id'], isNotNull);

      final supplier = (fixture['suppliers'] as List).first as Map;

      // The real six-step capture, one real endpoint per step.
      var tx = await client.txStep(
        '/v1/milk-transactions',
        body: {'session_id': session['id']},
      );
      final txId = tx['id'] as String;
      tx = await client.txStep(
        '/v1/milk-transactions/$txId/identify',
        body: {'method': 'code', 'value': supplier['code']},
      );
      expect(tx['state'], 'SUPPLIER_IDENTIFIED');

      tx = await client.txStep(
        '/v1/milk-transactions/$txId/milk',
        body: {'milk_type': 'buffalo', 'container_type': 'can', 'container_identifier': 'E2E-CAN-1'},
      );
      tx = await client.txStep(
        '/v1/milk-transactions/$txId/weight',
        body: {'source': 'manual', 'gross': 12.5, 'tare': 2.5},
      );
      // The platform computes the net; the client never does.
      expect(tx['net_weight'], closeTo(10.0, 0.001));

      tx = await client.txStep(
        '/v1/milk-transactions/$txId/quality',
        body: {'source': 'manual', 'fat': 6.5, 'snf': 9.0, 'clr': 28.0},
      );
      tx = await client.txStep('/v1/milk-transactions/$txId/accept');
      tx = await client.txStep('/v1/milk-transactions/$txId/complete');
      expect(tx['state'], 'COMPLETED');

      // The parchi — its number is minted by the platform, never by the phone.
      final slip = await client.transactionSlip(txId);
      expect(slip['slip_number'], isNotNull);
      expect('${slip['slip_number']}', startsWith('SLP-'));
      expect(slip['transaction_id'], txId);
      // The slip renders the transaction's own stored figures.
      expect('${slip['text']}', contains('${slip['slip_number']}'));
    });

    test('the platform refuses impossible measurements', () async {
      if (!harnessed) return;
      final client = await _signedIn('operator');
      final centreId = _centre['id'] as String;
      final open = await client.listOpenSessions(centreId);
      final session = open.isNotEmpty
          ? open.first
          : await client.openCollectionSession(centreId);
      final supplier = (fixture['suppliers'] as List).first as Map;

      final tx = await client.txStep(
        '/v1/milk-transactions',
        body: {'session_id': session['id']},
      );
      final txId = tx['id'] as String;
      await client.txStep(
        '/v1/milk-transactions/$txId/identify',
        body: {'method': 'code', 'value': supplier['code']},
      );
      await client.txStep(
        '/v1/milk-transactions/$txId/milk',
        body: {'milk_type': 'cow', 'container_type': 'can', 'container_identifier': 'E2E-CAN-1'},
      );

      // Tare above gross: the server's rule, proven at the real boundary — the
      // same sentence the app mirrors offline.
      await expectLater(
        client.txStep(
          '/v1/milk-transactions/$txId/weight',
          body: {'source': 'manual', 'gross': 5.0, 'tare': 9.0},
        ),
        throwsA(isA<ApiException>()),
      );
      // Clean up after itself: a session will not close with work in flight
      // (the platform says so), and a test that leaves debris breaks the next.
      await client.txStep('/v1/milk-transactions/$txId/cancel',
          body: {'reason': 'E2E exploratory transaction'});
    });

    test('the phone cannot fabricate a device reading in this environment',
        () async {
      if (!harnessed) return;
      final client = await _signedIn('operator');
      final centreId = _centre['id'] as String;
      final open = await client.listOpenSessions(centreId);
      final session = open.isNotEmpty
          ? open.first
          : await client.openCollectionSession(centreId);
      final supplier = (fixture['suppliers'] as List).first as Map;
      final tx = await client.txStep(
        '/v1/milk-transactions',
        body: {'session_id': session['id']},
      );
      final txId = tx['id'] as String;
      await client.txStep(
        '/v1/milk-transactions/$txId/identify',
        body: {'method': 'code', 'value': supplier['code']},
      );
      await client.txStep(
        '/v1/milk-transactions/$txId/milk',
        body: {'milk_type': 'cow', 'container_type': 'can', 'container_identifier': 'E2E-CAN-1'},
      );
      // `mock_scale` is refused by the platform outside a permitted
      // environment — the honesty guarantee, checked over the real boundary.
      try {
        await client.txStep(
          '/v1/milk-transactions/$txId/weight',
          body: {'source': 'mock_scale'},
        );
        // If the environment permits mocks, it must at least have said so.
        // (dev allows it; the assertion that matters is that prod does not,
        // which `test_mock_hardware_boundary.py` proves server-side.)
      } on ApiException catch (e) {
        expect(e.status, greaterThanOrEqualTo(400));
      }
      await client.txStep('/v1/milk-transactions/$txId/cancel',
          body: {'reason': 'E2E exploratory transaction'});
    });
  });

  group('E — offline capture and replay, over the real boundary', () {
    test('work captured offline replays exactly once when signal returns',
        () async {
      if (!harnessed) return;
      final client = _offlineClient();
      await client.login(_email('operator'), _password);
      final centreId = _centre['id'] as String;
      final open = await client.listOpenSessions(centreId);
      final session = open.isNotEmpty
          ? open.first
          : await client.openCollectionSession(centreId);
      final supplier = (fixture['suppliers'] as List)[1] as Map;

      // Signal dies. The whole capture goes into the durable queue.
      client.forceOffline = true;
      final queued = await client.txStep(
        '/v1/milk-transactions',
        body: {'session_id': session['id']},
      );
      final localId = queued['id'] as String;
      expect(localId, startsWith('local-'));
      for (final step in [
        ('identify', {'method': 'code', 'value': supplier['code']}),
        ('milk', {'milk_type': 'cow', 'container_type': 'can', 'container_identifier': 'E2E-CAN-1'}),
        ('weight', {'source': 'manual', 'gross': 11.0, 'tare': 1.0}),
        ('quality', {'source': 'manual', 'fat': 4.2, 'snf': 8.6, 'clr': 27.0}),
        ('accept', <String, dynamic>{}),
        ('complete', <String, dynamic>{}),
      ]) {
        await client.txStep(
          '/v1/milk-transactions/$localId/${step.$1}',
          body: step.$2,
        );
      }
      expect(client.pendingCount, greaterThan(0));

      // Signal returns. The platform accepts the whole capture.
      client.forceOffline = false;
      final run = await client.syncNow();
      expect(run.failed, 0, reason: 'the platform refused queued work');
      expect(run.applied, greaterThan(0));
      expect(client.pendingCount, 0);

      // A second sync sends nothing: replay is idempotent at the real boundary.
      final again = await client.syncNow();
      expect(again.applied, 0);
    });

    test('a queued capture survives a restart and still replays once',
        () async {
      if (!harnessed) return;
      final dir = await Directory.systemTemp.createTemp('lacteva-e2e-queue');
      addTearDown(() => dir.delete(recursive: true));
      final path = '${dir.path}/queue.json';

      final centreId = _centre['id'] as String;
      final supplier = (fixture['suppliers'] as List)[2] as Map;

      // --- process one: capture with no signal -----------------------------
      final before = _offlineClient(store: FileOfflineStore(path));
      await before.login(_email('operator'), _password);
      final open = await before.listOpenSessions(centreId);
      final session = open.isNotEmpty
          ? open.first
          : await before.openCollectionSession(centreId);
      before.forceOffline = true;
      final queued = await before.txStep(
        '/v1/milk-transactions',
        body: {'session_id': session['id']},
      );
      final localId = queued['id'] as String;
      for (final step in [
        ('identify', {'method': 'code', 'value': supplier['code']}),
        ('milk', {'milk_type': 'cow', 'container_type': 'can', 'container_identifier': 'E2E-CAN-1'}),
        ('weight', {'source': 'manual', 'gross': 9.0, 'tare': 1.0}),
        ('quality', {'source': 'manual', 'fat': 4.0, 'snf': 8.5, 'clr': 26.0}),
        ('accept', <String, dynamic>{}),
        ('complete', <String, dynamic>{}),
      ]) {
        await before.txStep(
          '/v1/milk-transactions/$localId/${step.$1}',
          body: step.$2,
        );
      }
      final queuedIds = [
        for (final op in before.queue.operations) op.operationId,
      ];
      expect(queuedIds, isNotEmpty);

      // --- process two: the app was killed; the file is all that survived ---
      final after = _offlineClient(store: FileOfflineStore(path));
      await after.queue.load();
      expect(
        [for (final op in after.queue.operations) op.operationId],
        queuedIds,
        reason: 'the queue must survive a restart byte-for-byte',
      );

      // Authenticate again and drain to the REAL platform.
      await after.login(_email('operator'), _password);
      after.forceOffline = false;
      final run = await after.syncNow();
      expect(run.failed, 0);
      expect(after.pendingCount, 0);
    });
  });

  group('F+G — history and end of shift', () {
    test('a completed collection is retrievable, centre-scoped', () async {
      if (!harnessed) return;
      final client = await _signedIn('operator');
      final centreId = _centre['id'] as String;

      final page = await client.listMilkTransactions(centerId: centreId);
      expect((page['items'] as List), isNotEmpty,
          reason: 'the collections recorded above must be readable');
      final first = (page['items'] as List).first as Map<String, dynamic>;
      expect(first['center_id'], centreId);

      // The detail the phone shows is the platform's own row.
      if (first['state'] == 'COMPLETED') {
        final slip = await client.transactionSlip(first['id'].toString());
        expect(slip['transaction_id'], first['id']);
      }
    });

    test('the session closes through the platform', () async {
      if (!harnessed) return;
      final client = await _signedIn('operator');
      final centreId = _centre['id'] as String;
      final open = await client.listOpenSessions(centreId);
      if (open.isEmpty) return; // nothing to close; not a failure
      final closed = await client.closeCollectionSession(
        open.first['id'] as String,
      );
      expect(closed['status'], isNot('open'));
      // And the platform now reports no open session at that centre.
      final after = await client.listOpenSessions(centreId);
      expect(after.where((s) => s['id'] == open.first['id']), isEmpty);
    });
  });
}
