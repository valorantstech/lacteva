/// The first decision the app makes: is somebody already signed in?
///
/// Before 2026-09-04 the answer was always no, because the session lived in
/// memory. Now the client asks its [SessionStore]; a saved pair goes straight
/// to [HomeRouter] — where the platform's `/v1/auth/me` is the real judge,
/// and a stale access token refreshes itself on the first 401 — and no saved
/// pair goes to [LoginScreen]. Nothing is shown until the store has answered,
/// which takes a few milliseconds and never a network round-trip.
library;

import 'package:flutter/material.dart';

import 'centers.dart' show LoginScreen;
import 'home.dart';
import 'offline/offline_client.dart';
import 'push.dart';

class StartupGate extends StatefulWidget {
  const StartupGate({
    super.key,
    required this.client,
    this.pushTokens = const NoPushConfigured(),
  });

  final OfflineApiClient client;
  final PushTokenSource pushTokens;

  @override
  State<StartupGate> createState() => _StartupGateState();
}

class _StartupGateState extends State<StartupGate> {
  bool? _restored;

  @override
  void initState() {
    super.initState();
    widget.client.restoreSession().then((restored) {
      if (mounted) setState(() => _restored = restored);
    });
  }

  @override
  Widget build(BuildContext context) {
    return switch (_restored) {
      null => const Scaffold(body: SizedBox.expand()),
      true => HomeRouter(client: widget.client, pushTokens: widget.pushTokens),
      false => LoginScreen(client: widget.client),
    };
  }
}
