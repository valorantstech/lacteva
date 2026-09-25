/// Being reachable when the app is closed (DEMO-012 §10).
///
/// The interesting cases here are all about what the app does when push is
/// NOT configured, because that is the state this deployment is actually in:
/// no messaging vendor has been chosen or paid for. A phone that registers a
/// fabricated token, or an app that refuses to start because a notification
/// gateway is unavailable, would both be worse than no push at all.
library;

import 'package:flutter_test/flutter_test.dart';
import 'package:lacteva_mobile/src/api.dart';
import 'package:lacteva_mobile/src/push.dart';
import 'package:lacteva_mobile/src/session.dart';

class _RecordingClient extends ApiClient {
  final List<Map<String, dynamic>> registered = [];
  final List<String> revoked = [];
  Object? failWith;

  @override
  Future<Map<String, dynamic>> registerDevice({
    required String token,
    required String platform,
    String label = '',
  }) async {
    if (failWith != null) throw failWith!;
    registered.add({'token': token, 'platform': platform, 'label': label});
    return {'id': 'dev-${registered.length}', 'platform': platform};
  }

  @override
  Future<void> revokeDevice(String deviceId) async {
    if (failWith != null) throw failWith!;
    revoked.add(deviceId);
  }
}

class _FixedToken implements PushTokenSource {
  const _FixedToken(this.value);
  final String? value;

  @override
  Future<String?> token() async => value;
}

Session _sessionWith({
  String? customerId,
  Set<String> permissions = const {},
}) => Session(
  userId: 'u1',
  email: 'someone@example.com',
  fullName: 'Someone',
  tenantId: 'org-1',
  customerId: customerId,
  locale: 'en',
  permissions: permissions,
  organization: null,
);

final _customer = _sessionWith(customerId: 'cust-1');
final _driver = _sessionWith(permissions: const {'logistics.run.execute'});

void main() {
  test('with no messaging vendor wired, nothing is registered', () async {
    // Not a stub that invents a token. A fabricated token registers a device
    // the platform can never reach, and every notification for that user then
    // fails against a gateway instead of resolving to "this person has no
    // phone registered" — which is the distinction an operator needs.
    final client = _RecordingClient();
    final id = await registerForPush(client);

    expect(id, isNull);
    expect(client.registered, isEmpty);
  });

  test('an empty token is not a token', () async {
    final client = _RecordingClient();
    await registerForPush(client, source: const _FixedToken(''));
    expect(client.registered, isEmpty);
  });

  test('a real token is handed over with the platform it came from', () async {
    final client = _RecordingClient();
    final id = await registerForPush(
      client,
      source: const _FixedToken('fcm-abc'),
      label: 'rider@dairy.example',
    );

    expect(id, 'dev-1');
    expect(client.registered.single['token'], 'fcm-abc');
    expect(
      client.registered.single['platform'],
      isIn(['android', 'ios', 'web']),
    );
  });

  test('a gateway that is down does not stop a rider signing in', () async {
    // Being reachable by push is a degraded state, not a broken one. A round
    // waiting at the door must not be held up by a notification service.
    final client = _RecordingClient()..failWith = ApiException(503, 'down');
    final id = await registerForPush(
      client,
      source: const _FixedToken('fcm-abc'),
    );
    expect(id, isNull);
  });

  test('signing out gives the token back', () async {
    // One phone often serves a whole round. Without this, the next person to
    // sign in keeps receiving the previous user's notifications until the
    // token happens to rotate.
    final client = _RecordingClient();
    await revokePush(client, 'dev-1');
    expect(client.revoked, ['dev-1']);
  });

  test('signing out with nothing registered does nothing', () async {
    final client = _RecordingClient();
    await revokePush(client, null);
    expect(client.revoked, isEmpty);
  });

  test('a failed revocation is not fatal', () async {
    final client = _RecordingClient()..failWith = ApiException(404, 'gone');
    await revokePush(client, 'dev-1');
    expect(client.revoked, isEmpty);
  });

  group('WO-77 — the vendor is behind an interface', () {
    test('the silent default answers everything with nothing', () async {
      const none = NoPushConfigured();
      expect(await none.token(), isNull);
      expect(await none.requestPermission(), isFalse);
      expect(await none.permissionState(), isFalse);
      expect(await none.initialMessage(), isNull);
      expect(await none.tokenRefreshes.isEmpty, isTrue);
      expect(await none.foreground.isEmpty, isTrue);
      expect(await none.opened.isEmpty, isTrue);
      // And it is what the process runs with until main.dart says otherwise.
      expect(installedPush, isA<NoPushConfigured>());
    });

    test('a rotated token is registered as given, not fetched again', () async {
      final client = _RecordingClient();
      final id = await registerForPush(
        client,
        source: const _FixedToken('old-token'),
        token: 'rotated-token',
      );
      expect(id, 'dev-1');
      expect(client.registered.single['token'], 'rotated-token');
    });

    test(
      'a tapped notification opens the bills for a household and the round for staff',
      () {
        const bill = PushMessage(
          data: {'template': 'invoice_issued', 'notification_id': 'n1'},
        );
        const paid = PushMessage(
          data: {'template': 'customer_payment_recorded'},
        );
        const nothing = PushMessage(title: 'Hello');
        expect(pushTargetFor(bill, _customer), 'bills');
        expect(pushTargetFor(paid, _customer), 'bills');
        expect(pushTargetFor(nothing, _customer), isNull);
        // A household is never sent to a staff screen by an unknown template.
        expect(
          pushTargetFor(
            const PushMessage(data: {'template': 'month_end_drafted'}),
            _customer,
          ),
          isNull,
        );
        expect(pushTargetFor(bill, _driver), 'round');
        expect(pushTargetFor(nothing, _driver), isNull);
      },
    );
  });
}
