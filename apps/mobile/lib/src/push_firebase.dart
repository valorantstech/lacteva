/// Firebase Cloud Messaging as the app's [PushRuntime] (WO-77 Part B).
///
/// The only file in `lib/` that imports Firebase. It is installed once, in
/// `main.dart`, after `Firebase.initializeApp()` succeeded; if that fails —
/// no `google-services.json`, no Play services, an emulator without them —
/// the app keeps [NoPushConfigured] and runs exactly as before. Push is an
/// extra, and this file must never be the reason a screen does not open.
///
/// What FCM gives the app: a registration token (the address of this
/// installation, useless for reading anything), rotation of that token, the
/// Android 13+ notification permission question, and the three doors a
/// message comes through — foreground (the system shows nothing, the app says
/// one line), background tap, and the notification that launched the app.
///
/// What it does NOT hold: any credential that can SEND. That is the
/// service-account key on the server, which no build of this app contains.
library;

import 'package:firebase_messaging/firebase_messaging.dart';

import 'push.dart';

class FirebasePushRuntime implements PushRuntime {
  FirebasePushRuntime([FirebaseMessaging? messaging])
    : _messaging = messaging ?? FirebaseMessaging.instance;

  final FirebaseMessaging _messaging;

  @override
  Future<String?> token() async {
    try {
      return await _messaging.getToken();
    } catch (_) {
      // No token is a degraded state, not a broken one.
      return null;
    }
  }

  @override
  Stream<String> get tokenRefreshes => _messaging.onTokenRefresh;

  @override
  Future<bool> requestPermission() async {
    try {
      final settings = await _messaging.requestPermission(
        alert: true,
        badge: true,
        sound: true,
      );
      return settings.authorizationStatus == AuthorizationStatus.authorized ||
          settings.authorizationStatus == AuthorizationStatus.provisional;
    } catch (_) {
      return false;
    }
  }

  @override
  Future<bool?> permissionState() async {
    try {
      final settings = await _messaging.getNotificationSettings();
      return switch (settings.authorizationStatus) {
        AuthorizationStatus.notDetermined => null,
        AuthorizationStatus.denied => false,
        _ => true,
      };
    } catch (_) {
      return false;
    }
  }

  @override
  Stream<PushMessage> get foreground =>
      FirebaseMessaging.onMessage.map(_convert);

  @override
  Stream<PushMessage> get opened =>
      FirebaseMessaging.onMessageOpenedApp.map(_convert);

  @override
  Future<PushMessage?> initialMessage() async {
    try {
      final message = await _messaging.getInitialMessage();
      return message == null ? null : _convert(message);
    } catch (_) {
      return null;
    }
  }

  static PushMessage _convert(RemoteMessage message) => PushMessage(
    title: message.notification?.title,
    body: message.notification?.body,
    // FCM guarantees string values (the platform's adapter asserts it too);
    // the map is copied so nothing downstream can mutate the vendor's.
    data: {
      for (final entry in message.data.entries)
        entry.key: entry.value?.toString() ?? '',
    },
  );
}
