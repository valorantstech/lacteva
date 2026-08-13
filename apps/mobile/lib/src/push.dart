/// Being reachable when the app is closed (DEMO-012 §10).
///
/// The platform already has one notification system — templates, channels,
/// idempotency, retry, dead-lettering, a delivery history an operator can
/// read. `push` is a CHANNEL on that system, and this file is the phone's
/// half of it: hand the platform the delivery token for this installation,
/// and give it back on sign-out.
///
/// **What is deliberately absent: a vendor.** Delivering a push needs a
/// messaging service (FCM, APNs, or an operator's own relay), which needs a
/// project somebody owns and, past its free tier, pays for. That is a
/// decision for whoever runs the deployment, not something to assume — so the
/// token SOURCE is an interface, the default implementation supplies no
/// token, and the platform's push provider defaults to `disabled` so a
/// deployment that has not made the choice fails a push visibly rather than
/// recording it as delivered.
///
/// Wiring a real one is: add `firebase_messaging` to `pubspec.yaml`, drop the
/// `google-services.json` / `GoogleService-Info.plist` from that project into
/// the platform folders, implement `PushTokenSource` over
/// `FirebaseMessaging.instance.getToken()`, and set
/// `LACTEVA_NOTIFICATION_PUSH_PROVIDER` / `LACTEVA_PUSH_API_URL` /
/// `LACTEVA_PUSH_API_KEY` on the server. Nothing else here changes.
///
/// **No credential lives in this app.** The server credential that authorises
/// sending is server-side configuration. What the phone holds is its own
/// delivery token — an address for this one installation, useless for reading
/// anything and revoked on sign-out.
library;

import 'package:flutter/foundation.dart';

import 'api.dart';

/// Where the delivery token for this installation comes from.
abstract class PushTokenSource {
  /// The token, or null when push is not configured on this build.
  Future<String?> token();
}

/// The default: no messaging vendor is wired, so there is no token.
///
/// Not a stub that fabricates one. A fake token would register a device the
/// platform can never reach, and every notification for that user would then
/// fail against a gateway instead of resolving to "this person has no phone
/// registered" — which is the distinction an operator needs.
class NoPushConfigured implements PushTokenSource {
  const NoPushConfigured();

  @override
  Future<String?> token() async => null;
}

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
}) async {
  try {
    final token = await source.token();
    if (token == null || token.isEmpty) return null;
    final device = await client.registerDevice(
      token: token,
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
