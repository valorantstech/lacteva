/// The session outlives the process (owner, 2026-09-04).
///
/// "When I restart the app it is always asking for login; once I logged in
/// it should always be logged in till I logout." The pair the platform issues
/// is saved to the device's encrypted store on sign-in and on every refresh,
/// picked up at the next launch, and forgotten on sign-out or when the
/// platform refuses a refresh — and at no other time.
library;

import 'dart:convert';

import 'package:flutter/material.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:http/http.dart' as http;
import 'package:http/testing.dart';
import 'package:lacteva_mobile/src/api.dart';
import 'package:lacteva_mobile/src/centers.dart' show LoginScreen;
import 'package:lacteva_mobile/src/home.dart';
import 'package:lacteva_mobile/src/offline/offline_client.dart';
import 'package:lacteva_mobile/src/offline/queue.dart';
import 'package:lacteva_mobile/src/offline/store.dart';
import 'package:lacteva_mobile/src/session_store.dart';
import 'package:lacteva_mobile/src/startup.dart';

http.Response _json(Object body, int status) =>
    http.Response(jsonEncode(body), status, headers: {'content-type': 'application/json'});

/// A platform that rotates refresh tokens and remembers which are live.
class _Platform {
  int issued = 0;
  int refreshes = 0;
  int meCalls = 0;
  final Set<String> liveAccess = {};
  String liveRefresh = 'refresh-1';
  bool refuseRefresh = false;

  String _issue() {
    issued++;
    final token = 'access-$issued';
    liveAccess.add(token);
    return token;
  }

  Future<http.Response> handle(http.Request request) async {
    final path = request.url.path;
    if (path.endsWith('/v1/auth/token')) {
      return _json({'access_token': _issue(), 'refresh_token': liveRefresh, 'token_type': 'bearer'}, 200);
    }
    if (path.endsWith('/v1/auth/refresh')) {
      refreshes++;
      final presented = jsonDecode(request.body)['refresh_token'];
      if (refuseRefresh || presented != liveRefresh) {
        return _json({'detail': 'Refresh token is invalid'}, 401);
      }
      liveRefresh = 'refresh-${refreshes + 1}';
      return _json({'access_token': _issue(), 'refresh_token': liveRefresh, 'token_type': 'bearer'}, 200);
    }
    final bearer = request.headers['Authorization']?.replaceFirst('Bearer ', '');
    if (bearer == null || !liveAccess.contains(bearer)) {
      return _json({'detail': 'Not authenticated'}, 401);
    }
    if (path.endsWith('/v1/auth/me')) {
      meCalls++;
      return _json({
        'user': {'id': 'u1', 'email': 'priya@dairy.example', 'full_name': 'Priya'},
        'tenant_id': 'org-1',
        'permissions': ['collection.session.manage', 'supplier.read'],
      }, 200);
    }
    return _json({'items': [], 'total': 0}, 200);
  }
}

OfflineApiClient _client(_Platform platform, SessionStore store) => OfflineApiClient(
  queue: SyncQueue(MemoryOfflineStore()),
  deviceId: 'test-device',
  inner: MockClient(platform.handle),
  store: store,
);

void main() {
  group('the pair is saved when the platform issues it', () {
    test('sign-in writes both halves', () async {
      final store = MemorySessionStore();
      final platform = _Platform();
      await _client(platform, store).login('priya@dairy.example', 'pw');
      final saved = await store.read();
      expect(saved?.accessToken, 'access-1');
      expect(saved?.refreshToken, 'refresh-1');
    });

    test('a refresh saves the ROTATED token before anything else runs', () async {
      // The platform treats a re-presented previous token as theft and kills
      // the session. A refresh that rotates in memory but not on disk would
      // therefore turn the next launch into a sign-out — so the write is
      // awaited inside the refresh, and this test would see the stale token
      // if it were not.
      final store = MemorySessionStore();
      final platform = _Platform();
      final client = _client(platform, store);
      await client.login('priya@dairy.example', 'pw');
      platform.liveAccess.clear(); // fifteen minutes pass
      await client.me();
      expect(platform.refreshes, 1);
      expect((await store.read())?.refreshToken, 'refresh-2');
      expect((await store.read())?.accessToken, 'access-2');
    });
  });

  group('a restart is not a sign-out', () {
    test('a new process picks the session up and carries on', () async {
      final store = MemorySessionStore();
      final platform = _Platform();
      await _client(platform, store).login('priya@dairy.example', 'pw');

      // The process dies; a new client is built over the same store.
      final relaunched = _client(platform, store);
      expect(relaunched.isAuthenticated, isFalse);
      expect(await relaunched.restoreSession(), isTrue);
      expect(relaunched.isAuthenticated, isTrue);
      await relaunched.me();
      expect(platform.meCalls, 1);
      expect(platform.refreshes, 0, reason: 'the access token was still good');
    });

    test('a night later the stale access token refreshes itself', () async {
      final store = MemorySessionStore();
      final platform = _Platform();
      await _client(platform, store).login('priya@dairy.example', 'pw');
      platform.liveAccess.clear();

      final relaunched = _client(platform, store);
      var expired = 0;
      relaunched.onAuthExpired = () => expired++;
      await relaunched.restoreSession();
      await relaunched.me();
      expect(platform.refreshes, 1);
      expect(platform.meCalls, 1);
      expect(expired, 0);
      expect((await store.read())?.refreshToken, 'refresh-2');
    });

    test('an empty store restores nothing', () async {
      final client = _client(_Platform(), MemorySessionStore());
      expect(await client.restoreSession(), isFalse);
      expect(client.isAuthenticated, isFalse);
    });

    test('a client with no store keeps the old behaviour', () async {
      final client = OfflineApiClient(
        queue: SyncQueue(MemoryOfflineStore()),
        deviceId: 'test-device',
        inner: MockClient(_Platform().handle),
      );
      await client.login('priya@dairy.example', 'pw');
      expect(await client.restoreSession(), isFalse);
    });
  });

  group('the pair is forgotten when the session ends, and only then', () {
    test('sign-out clears the store before it returns', () async {
      final store = MemorySessionStore();
      final client = _client(_Platform(), store);
      await client.login('priya@dairy.example', 'pw');
      await client.signOut();
      expect(await store.read(), isNull);
      expect(client.isAuthenticated, isFalse);
      // The next launch asks for a password.
      expect(await _client(_Platform(), store).restoreSession(), isFalse);
    });

    test('a refused refresh clears the store and tells the app once', () async {
      final store = MemorySessionStore();
      final platform = _Platform();
      final client = _client(platform, store);
      await client.login('priya@dairy.example', 'pw');
      platform.liveAccess.clear();
      platform.refuseRefresh = true;
      var expired = 0;
      client.onAuthExpired = () => expired++;
      await expectLater(client.me(), throwsA(isA<AuthExpiredException>()));
      await Future<void>.delayed(Duration.zero);
      expect(expired, 1);
      expect(await store.read(), isNull);
    });

    test('a transport failure clears nothing', () async {
      final store = MemorySessionStore();
      final platform = _Platform();
      final client = _client(platform, store);
      await client.login('priya@dairy.example', 'pw');
      final offline = OfflineApiClient(
        queue: SyncQueue(MemoryOfflineStore()),
        deviceId: 'test-device',
        inner: MockClient((_) async => throw http.ClientException('no network')),
        store: store,
      );
      await offline.restoreSession();
      await expectLater(offline.me(), throwsA(isA<http.ClientException>()));
      expect((await store.read())?.refreshToken, 'refresh-1');
      expect(offline.isAuthenticated, isTrue);
    });
  });

  group('the first screen', () {
    testWidgets('is sign-in when nobody is saved', (tester) async {
      final client = _client(_Platform(), MemorySessionStore());
      await tester.pumpWidget(MaterialApp(home: StartupGate(client: client)));
      await tester.pumpAndSettle();
      expect(find.byType(LoginScreen), findsOneWidget);
      expect(find.byType(HomeRouter), findsNothing);
    });

    testWidgets('is home when a session is saved, and the platform is asked, not trusted', (tester) async {
      final store = MemorySessionStore();
      final platform = _Platform();
      await _client(platform, store).login('priya@dairy.example', 'pw');

      final relaunched = _client(platform, store);
      await tester.pumpWidget(MaterialApp(home: StartupGate(client: relaunched)));
      await tester.pumpAndSettle();
      expect(find.byType(HomeRouter), findsOneWidget);
      expect(find.byType(LoginScreen), findsNothing);
      expect(platform.meCalls, 1);
    });
  });
}
