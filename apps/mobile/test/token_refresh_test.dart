/// WO-69 — the app must not log people out every fifteen minutes.
///
/// The platform issues a `TokenPair`: an access token that lives 900 seconds
/// and a refresh token that lives fourteen days, with `POST /v1/auth/refresh`
/// to trade the second for a new first. The mobile client kept only the
/// access token and treated its expiry as the end of the session — so an
/// operator collecting from forty farmers across a ninety-minute morning was
/// signed out about six times, mid-queue. What is pinned here:
///
/// 1. 401 → refresh → the ORIGINAL request is retried and succeeds, and the
///    caller never learns anything happened.
/// 2. A refused refresh (revoked, or the fourteen days are up) ends the
///    session EXACTLY once, however many requests were waiting on it.
/// 3. Six concurrent 401s produce ONE refresh — the platform rate-limits that
///    route, and six would punish the operator for the app's enthusiasm.
/// 4. A queued offline capture survives an expiry: it stays queued through a
///    refused refresh and replays, with its original idempotency key, once
///    somebody signs in again.
/// 5. A login that returned no refresh token keeps the pre-WO-69 behaviour —
///    the first 401 ends the session — because there is nothing to refresh
///    with.
library;

import 'dart:async';
import 'dart:convert';

import 'package:flutter_test/flutter_test.dart';
import 'package:http/http.dart' as http;
import 'package:http/testing.dart';
import 'package:lacteva_mobile/src/api.dart';
import 'package:lacteva_mobile/src/offline/offline_client.dart';
import 'package:lacteva_mobile/src/offline/queue.dart';
import 'package:lacteva_mobile/src/offline/store.dart';

http.Response _json(Object body, int status) => http.Response(
  jsonEncode(body),
  status,
  headers: {'content-type': 'application/json'},
);

/// A platform with a fifteen-minute access token, scripted by the test.
class _Platform {
  _Platform({this.refreshSucceeds = true, this.issueRefreshToken = true});

  bool refreshSucceeds;
  final bool issueRefreshToken;

  /// The access tokens the platform currently honours.
  final Set<String> live = {};
  int issued = 0;
  int refreshes = 0;
  int authenticatedCalls = 0;
  final List<String> idempotencyKeys = [];

  /// Let the test hold a refresh open so several 401s pile up behind it.
  Completer<void>? holdRefresh;

  String _issue() {
    issued++;
    final token = 'access-$issued';
    live.add(token);
    return token;
  }

  void expireAll() => live.clear();

  Future<http.Response> handle(http.Request request) async {
    final path = request.url.path;
    if (path.endsWith('/v1/auth/token')) {
      return _json({
        'access_token': _issue(),
        if (issueRefreshToken) 'refresh_token': 'refresh-1',
        'token_type': 'bearer',
      }, 200);
    }
    if (path.endsWith('/v1/auth/refresh')) {
      refreshes++;
      // The route authenticates by the body, never by a bearer.
      expect(request.headers.containsKey('Authorization'), isFalse);
      expect(jsonDecode(request.body)['refresh_token'], 'refresh-1');
      if (holdRefresh != null) await holdRefresh!.future;
      if (!refreshSucceeds) {
        return _json({'detail': 'Refresh token is invalid or expired'}, 401);
      }
      return _json({
        'access_token': _issue(),
        'refresh_token': 'refresh-1',
        'token_type': 'bearer',
      }, 200);
    }
    final bearer = request.headers['Authorization']?.replaceFirst(
      'Bearer ',
      '',
    );
    authenticatedCalls++;
    if (bearer == null || !live.contains(bearer)) {
      return _json({'detail': 'Not authenticated'}, 401);
    }
    final key = request.headers['Idempotency-Key'];
    if (key != null) idempotencyKeys.add(key);
    if (path.endsWith('/v1/deliveries')) {
      return _json({'id': 'd-${idempotencyKeys.length}'}, 201);
    }
    return _json({'items': [], 'total': 0}, 200);
  }
}

void main() {
  test('401 → refresh → the original request is retried transparently', () async {
    final platform = _Platform();
    final client = ApiClient(inner: MockClient(platform.handle));
    var expiries = 0;
    client.onAuthExpired = () => expiries++;

    await client.login('op@x.example', 'pw');
    platform.expireAll(); // fifteen minutes pass

    final page = await client.listCenters();

    expect(page.items, isEmpty, reason: 'the caller got its answer');
    expect(platform.refreshes, 1);
    expect(platform.issued, 2, reason: 'login, then one refresh');
    expect(expiries, 0, reason: 'nobody was signed out');
    expect(client.isAuthenticated, isTrue);
    // And the new token is the one in use from now on: no second refresh.
    await client.listCenters();
    expect(platform.refreshes, 1);
  });

  test('a refused refresh ends the session exactly once', () async {
    final platform = _Platform(refreshSucceeds: false);
    final client = ApiClient(inner: MockClient(platform.handle));
    var expiries = 0;
    client.onAuthExpired = () => expiries++;

    await client.login('op@x.example', 'pw');
    platform.expireAll();

    await expectLater(
      client.listCenters(),
      throwsA(isA<AuthExpiredException>()),
    );
    expect(platform.refreshes, 1);
    expect(expiries, 1);
    expect(client.isAuthenticated, isFalse);

    // Signed out means signed out: nothing keeps sending dead tokens, and
    // nothing tells the app a second time.
    await expectLater(client.listCenters(), throwsA(isA<ApiException>()));
    expect(platform.refreshes, 1, reason: 'no refresh token left to try');
    expect(expiries, 1);
  });

  test('six concurrent 401s produce ONE refresh', () async {
    final platform = _Platform()..holdRefresh = Completer<void>();
    final client = ApiClient(inner: MockClient(platform.handle));
    var expiries = 0;
    client.onAuthExpired = () => expiries++;

    await client.login('op@x.example', 'pw');
    platform.expireAll();

    // A screen opening fires everything at once.
    final burst = List.generate(6, (_) => client.listCenters());
    // Let all six reach their 401 and queue behind the held refresh.
    await Future<void>.delayed(Duration.zero);
    await Future<void>.delayed(Duration.zero);
    platform.holdRefresh!.complete();
    final pages = await Future.wait(burst);

    expect(pages, hasLength(6));
    expect(platform.refreshes, 1, reason: 'single-flight');
    expect(platform.issued, 2);
    expect(expiries, 0);
    // Six originals, six retries; no seventh anything.
    expect(platform.authenticatedCalls, 12);
  });

  test('six concurrent 401s and a refused refresh sign out ONCE', () async {
    final platform = _Platform(refreshSucceeds: false)
      ..holdRefresh = Completer<void>();
    final client = ApiClient(inner: MockClient(platform.handle));
    var expiries = 0;
    client.onAuthExpired = () => expiries++;

    await client.login('op@x.example', 'pw');
    platform.expireAll();

    final burst = List.generate(
      6,
      (_) => client.listCenters().then<Object>((p) => p, onError: (e) => e),
    );
    await Future<void>.delayed(Duration.zero);
    await Future<void>.delayed(Duration.zero);
    platform.holdRefresh!.complete();
    final outcomes = await Future.wait(burst);

    expect(outcomes, everyElement(isA<AuthExpiredException>()));
    expect(platform.refreshes, 1);
    expect(expiries, 1, reason: 'the app is told once, not six times');
  });

  test('a queued capture survives an expiry and replays after sign-in', () async {
    final platform = _Platform(refreshSucceeds: false);
    final client = OfflineApiClient(
      queue: SyncQueue(MemoryOfflineStore()),
      deviceId: 'handset-1',
      inner: MockClient(platform.handle),
    );
    var expiries = 0;
    client.onAuthExpired = () => expiries++;

    await client.login('op@x.example', 'pw');
    // Captured while the network was gone...
    client.forceOffline = true;
    final echo = await client.recordDeliveryOffline(
      customerId: 'c-1',
      deliveryDate: '2026-09-04',
      slot: 'morning',
      status: 'delivered',
      quantity: '2.000',
    );
    expect(echo['_queued'], isTrue);
    expect(client.pendingCount, 1);

    // ...and by the time the network is back, the session is over and the
    // refresh is refused.
    client.forceOffline = false;
    platform.expireAll();
    final first = await client.syncNow();
    expect(first.applied, 0);
    expect(client.pendingCount, 1, reason: 'the capture waits for a session');
    expect(expiries, 1);
    expect(platform.idempotencyKeys, isEmpty);

    // The next operator signs in; the same capture goes through, once, under
    // the key it was captured with.
    platform.refreshSucceeds = true;
    await client.login('next@x.example', 'pw');
    // The failed attempt put the capture on its retry backoff (real time, 2s
    // floor); a test does not sleep through it.
    for (final op in client.queue.due(
      now: DateTime.now().toUtc().add(const Duration(minutes: 10)),
    )) {
      op.nextAttemptAt = null;
    }
    final second = await client.syncNow();
    expect(second.applied, 1);
    expect(client.pendingCount, 0);
    expect(platform.idempotencyKeys, hasLength(1));
  });

  test('a queued capture replays through a refresh without anyone noticing', () async {
    final platform = _Platform();
    final client = OfflineApiClient(
      queue: SyncQueue(MemoryOfflineStore()),
      deviceId: 'handset-1',
      inner: MockClient(platform.handle),
    );
    var expiries = 0;
    client.onAuthExpired = () => expiries++;

    await client.login('op@x.example', 'pw');
    client.forceOffline = true;
    await client.recordDeliveryOffline(
      customerId: 'c-1',
      deliveryDate: '2026-09-04',
      slot: 'morning',
      status: 'delivered',
    );
    client.forceOffline = false;
    platform.expireAll();

    final result = await client.syncNow();
    expect(result.applied, 1);
    expect(client.pendingCount, 0);
    expect(platform.refreshes, 1);
    expect(expiries, 0);
  });

  test('no refresh token: the first 401 still ends the session', () async {
    // The pre-WO-69 contract (P0-PRODUCT-008 D-2), preserved for a platform
    // — or a test fake — that hands back only an access token.
    final platform = _Platform(issueRefreshToken: false);
    final client = ApiClient(inner: MockClient(platform.handle));
    var expiries = 0;
    client.onAuthExpired = () => expiries++;

    await client.login('op@x.example', 'pw');
    platform.expireAll();
    await expectLater(
      client.listCenters(),
      throwsA(isA<AuthExpiredException>()),
    );
    expect(platform.refreshes, 0);
    expect(expiries, 1);
  });
}
