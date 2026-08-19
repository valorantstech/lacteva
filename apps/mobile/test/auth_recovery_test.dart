/// Session expiry and sign-out (P0-PRODUCT-008 D-2, fixed in P0-PRODUCT-009).
///
/// Before the fix the token lived only in memory with no way out: a 401
/// mid-shift showed a raw problem-detail as if it were a business error, and
/// the only "recovery" was killing the app. What is pinned here:
///
/// 1. An authenticated call answered 401 throws the distinguishable
///    [AuthExpiredException], forgets the dead token, and tells the app
///    exactly once — while a 401 on the login call itself stays an ordinary
///    refusal (wrong credentials are not an expired session).
/// 2. The app-level wiring (main.dart's shape) lands the person back on the
///    sign-in screen with an honest notice.
/// 3. Explicit sign-out exists, forgets the session, and — deliberately —
///    leaves the offline queue untouched: captured work survives a shared
///    handset changing hands.
library;

import 'dart:convert';

import 'package:flutter/material.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:http/http.dart' as http;
import 'package:http/testing.dart';
import 'package:lacteva_mobile/src/api.dart';
import 'package:lacteva_mobile/src/centers.dart';
import 'package:lacteva_mobile/src/offline/offline_client.dart';
import 'package:lacteva_mobile/src/offline/queue.dart';
import 'package:lacteva_mobile/src/offline/store.dart';
import 'package:lacteva_mobile/src/sign_out.dart';

http.Response _json(Object body, int status) => http.Response(
  jsonEncode(body),
  status,
  headers: {'content-type': 'application/json'},
);

void main() {
  group('the 401 contract in ApiClient', () {
    test('an authenticated 401 expires the session exactly once', () async {
      var respondWith401 = false;
      final client = ApiClient(
        inner: MockClient((request) async {
          if (request.url.path.endsWith('/v1/auth/token')) {
            return _json({'access_token': 't-1'}, 200);
          }
          if (respondWith401) {
            return _json({'detail': 'Not authenticated'}, 401);
          }
          return _json({'items': [], 'total': 0}, 200);
        }),
      );
      var expiries = 0;
      client.onAuthExpired = () => expiries++;

      await client.login('op@x.example', 'pw');
      expect(client.isAuthenticated, isTrue);

      respondWith401 = true;
      await expectLater(
        client.listCenters(),
        throwsA(isA<AuthExpiredException>()),
      );
      expect(client.isAuthenticated, isFalse, reason: 'dead token forgotten');
      expect(expiries, 1);

      // A second call carries no token: an ordinary 401, no second alarm.
      await expectLater(
        client.listCenters(),
        throwsA(
          predicate<Object>(
            (e) => e is ApiException && e is! AuthExpiredException,
          ),
        ),
      );
      expect(expiries, 1);
    });

    test('a 401 on login itself is a refusal, not an expiry', () async {
      final client = ApiClient(
        inner: MockClient(
          (request) async => _json({'detail': 'Invalid credentials'}, 401),
        ),
      );
      var expiries = 0;
      client.onAuthExpired = () => expiries++;

      await expectLater(
        client.login('op@x.example', 'wrong'),
        throwsA(
          predicate<Object>(
            (e) => e is ApiException && e is! AuthExpiredException,
          ),
        ),
      );
      expect(expiries, 0);
    });
  });

  testWidgets('expiry lands the person on sign-in with an honest notice', (
    tester,
  ) async {
    // The exact wiring main.dart uses: navigatorKey + onAuthExpired.
    var respondWith401 = false;
    final offline = OfflineApiClient(
      queue: SyncQueue(MemoryOfflineStore()),
      deviceId: 'test-device',
    );
    final client = ApiClient(
      inner: MockClient((request) async {
        if (request.url.path.endsWith('/v1/auth/token')) {
          return _json({'access_token': 't-1'}, 200);
        }
        if (respondWith401) return _json({'detail': 'Not authenticated'}, 401);
        return _json({'items': [], 'total': 0}, 200);
      }),
    );
    final navigatorKey = GlobalKey<NavigatorState>();
    client.onAuthExpired = () {
      navigatorKey.currentState?.pushAndRemoveUntil(
        MaterialPageRoute(
          builder: (_) => LoginScreen(
            client: offline,
            notice: 'Your session expired — sign in again to continue',
          ),
        ),
        (route) => false,
      );
    };

    await tester.pumpWidget(
      MaterialApp(
        navigatorKey: navigatorKey,
        home: const Scaffold(body: Text('somewhere mid-shift')),
      ),
    );

    await client.login('op@x.example', 'pw');
    respondWith401 = true;
    await expectLater(
      client.listCenters(),
      throwsA(isA<AuthExpiredException>()),
    );
    await tester.pumpAndSettle();

    expect(find.byType(LoginScreen), findsOneWidget);
    expect(
      find.text('Your session expired — sign in again to continue'),
      findsOneWidget,
    );
  });

  testWidgets('sign-out forgets the session and keeps the captured work', (
    tester,
  ) async {
    final client = _SignOutProbe();
    // A shift's captured work sits in the queue.
    await client.recordDeliveryOffline(
      customerId: 'cus-1',
      deliveryDate: '2026-08-19',
      slot: 'morning',
      status: 'delivered',
    );
    expect(client.pendingCount, 1);

    await tester.pumpWidget(
      MaterialApp(
        home: Scaffold(
          appBar: AppBar(actions: [SignOutButton(client: client)]),
        ),
      ),
    );
    await tester.tap(find.byIcon(Icons.logout));
    await tester.pumpAndSettle();

    expect(find.byType(LoginScreen), findsOneWidget);
    expect(client.isAuthenticated, isFalse);
    expect(client.revoked, isTrue, reason: 'push token handed back');
    expect(
      client.pendingCount,
      1,
      reason: 'the queue survives the sign-out; replay is re-authorized',
    );
  });
}

/// An offline client whose transport is cut and whose push revocation is
/// observable — everything sign-out touches, nothing more.
class _SignOutProbe extends OfflineApiClient {
  _SignOutProbe()
    : super(
        queue: SyncQueue(MemoryOfflineStore()),
        deviceId: 'test-device',
        forceOffline: true,
      );

  bool revoked = false;

  @override
  Future<void> revokeDevice(String deviceId) async {
    revoked = true;
  }
}
