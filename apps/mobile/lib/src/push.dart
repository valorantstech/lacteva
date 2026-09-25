/// Being reachable when the app is closed (DEMO-012 §10, wired by WO-77).
///
/// The platform already has one notification system — templates, channels,
/// idempotency, retry, dead-lettering, a delivery history an operator can
/// read. `push` is a CHANNEL on that system, and this file is the phone's
/// half of it: hand the platform the delivery token for this installation,
/// give it back on sign-out, and open the right screen when a notification
/// is tapped.
///
/// **The vendor is behind an interface.** `PushRuntime` is what the app
/// needs from a messaging service: a token, token rotation, a permission
/// question, and the messages that arrive. `NoPushConfigured` answers all of
/// it with nothing, and is what every test and every build without a project
/// gets. `FirebasePushRuntime` (`push_firebase.dart`) answers it with FCM, and
/// is installed once, in `main.dart`, into [installedPush] — so no screen
/// imports Firebase and the whole app works exactly the same when the
/// messaging service is absent, refused, or down. Push is an extra. Nothing
/// waits for it and nothing degrades without it.
///
/// **No credential lives in this app.** The server credential that authorises
/// sending is server-side configuration. What the phone holds is its own
/// delivery token — an address for this one installation, useless for reading
/// anything and revoked on sign-out.
library;

import 'package:flutter/foundation.dart';

import 'api.dart';
import 'session.dart';

/// Where the delivery token for this installation comes from.
abstract class PushTokenSource {
  /// The token, or null when push is not configured on this build.
  Future<String?> token();
}

/// A notification as the app sees it, whichever door it came through.
///
/// Only what the platform's push provider puts in `data`: a template key and
/// a notification id. Never a figure — a lock screen is a public surface and
/// the platform's adapter deliberately sends none (WO-77 Part A).
@immutable
class PushMessage {
  const PushMessage({this.title, this.body, this.data = const {}});

  final String? title;
  final String? body;
  final Map<String, String> data;

  String? get template => data['template'];
}

/// Everything the app needs from a messaging service, vendor-free.
abstract class PushRuntime implements PushTokenSource {
  /// The messaging service handed out a new token: re-register it.
  Stream<String> get tokenRefreshes;

  /// Ask the person, once, after sign-in. True when notifications may be
  /// shown. A refusal is an answer, not an error: the app carries on whole.
  Future<bool> requestPermission();

  /// true = allowed, false = refused, null = never asked. The one sentence
  /// explaining what notifications are for is shown only in the null case:
  /// a person who already answered is not asked to read it again.
  Future<bool?> permissionState();

  /// A message that arrived while the app was open. The system shows nothing
  /// for these, so the app says one line itself.
  Stream<PushMessage> get foreground;

  /// The person tapped a notification while the app was in the background.
  Stream<PushMessage> get opened;

  /// The notification that launched the app from a terminated state, if any.
  Future<PushMessage?> initialMessage();
}

/// The default: no messaging vendor is wired, so there is no token.
///
/// Not a stub that fabricates one. A fake token would register a device the
/// platform can never reach, and every notification for that user would then
/// fail against a gateway instead of resolving to "this person has no phone
/// registered" — which is the distinction an operator needs.
class NoPushConfigured implements PushRuntime {
  const NoPushConfigured();

  @override
  Future<String?> token() async => null;

  @override
  Stream<String> get tokenRefreshes => const Stream.empty();

  @override
  Future<bool> requestPermission() async => false;

  @override
  Future<bool?> permissionState() async => false;

  @override
  Stream<PushMessage> get foreground => const Stream.empty();

  @override
  Stream<PushMessage> get opened => const Stream.empty();

  @override
  Future<PushMessage?> initialMessage() async => null;
}

/// The runtime this process runs with. `main.dart` installs Firebase when the
/// project initialises; everything else — tests, a build without a project,
/// a device where Firebase failed to start — keeps the silent default.
PushRuntime installedPush = const NoPushConfigured();

/// What this build calls itself to the platform.
String currentDevicePlatform() {
  if (kIsWeb) return 'web';
  return defaultTargetPlatform == TargetPlatform.iOS ? 'ios' : 'android';
}

/// Register this handset, if there is anything to register.
///
/// Idempotent by token on the platform side, which is why calling it on every
/// start is correct rather than wasteful: the messaging service hands out the
/// same token until it rotates, and the platform moves rather than duplicates.
///
/// Failure is deliberately swallowed. Not being reachable by push is a
/// degraded state, not a broken one — a rider whose round is waiting must not
/// be stopped at the door because a notification gateway is unavailable.
/// Returns the registered device id, or null if nothing was registered.
Future<String?> registerForPush(
  ApiClient client, {
  PushTokenSource source = const NoPushConfigured(),
  String label = '',
  String? token,
}) async {
  try {
    final value = token ?? await source.token();
    if (value == null || value.isEmpty) return null;
    final device = await client.registerDevice(
      token: value,
      platform: currentDevicePlatform(),
      label: label,
    );
    return device['id']?.toString();
  } catch (_) {
    // Never logged: the token is capability-like, and an error string from an
    // HTTP client is exactly where a request body ends up.
    return null;
  }
}

/// Give the token back on sign-out.
///
/// Without this, the next person to sign in on a shared handset — a real
/// situation in a dairy, where one phone serves a round — keeps receiving the
/// previous user's notifications until their token happens to rotate.
Future<void> revokePush(ApiClient client, String? deviceId) async {
  if (deviceId == null) return;
  try {
    await client.revokeDevice(deviceId);
  } catch (_) {
    // Best effort. The platform also moves a token when the same handset
    // registers under another account, so a missed revocation is corrected by
    // the next sign-in rather than left forever.
  }
}

/// Where a tapped notification should take this session (WO-77 Part B).
///
/// `bills` for a household's bill or payment; `round` for anything a staff
/// session receives; null when the message names nothing the app has a
/// screen for. A pure function so the routing rule is testable without a
/// vendor — the same reason `groupRound` and `receiptsFor` are.
String? pushTargetFor(PushMessage message, Session session) {
  final template = message.template;
  if (template == null) return null;
  const household = {'invoice_issued', 'customer_payment_recorded'};
  if (session.isCustomer) return household.contains(template) ? 'bills' : null;
  return 'round';
}
