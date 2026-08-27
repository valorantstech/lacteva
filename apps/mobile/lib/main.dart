import 'dart:async';

import 'package:flutter/material.dart';
import 'package:path_provider/path_provider.dart';

import 'src/centers.dart';
import 'src/theme.dart';
import 'src/offline/offline_client.dart';
import 'src/offline/queue.dart';
import 'src/offline/store.dart';

/// Backend base URL. Override at run/build time:
///   flutter run --dart-define=LACTEVA_API_URL=http://10.0.2.2:8000
/// (10.0.2.2 reaches the host machine from the Android emulator.)
const apiUrl = String.fromEnvironment(
  'LACTEVA_API_URL',
  defaultValue: 'http://localhost:8000',
);

Future<void> main() async {
  WidgetsFlutterBinding.ensureInitialized();
  // P0-PILOT-004, found on the first physical handset: the queue file was a
  // RELATIVE path, which on Android resolves against '/' — a read-only
  // filesystem — so every offline write crashed and the "durable queue"
  // had never once persisted on a real device. The app's documents
  // directory is the writable, restart-surviving home the comment below
  // always promised.
  String? queuePath;
  try {
    final dir = await getApplicationDocumentsDirectory();
    queuePath = '${dir.path}/lacteva_sync_queue.json';
  } catch (_) {
    queuePath = null; // fall through to the in-memory stand-in
  }
  runApp(LactevaApp(queuePath: queuePath));
}

/// The app's single offline-capable client (OFF-001).
///
/// A file-backed queue in the app's own directory: it survives restart,
/// reboot, and crash. `MemoryOfflineStore` stands in when no writable
/// directory is available — a queue that forgets still beats an app that
/// cannot collect milk.
OfflineApiClient buildClient({
  OfflineStore? store,
  String? deviceId,
  String? queuePath,
}) {
  return OfflineApiClient(
    queue: SyncQueue(
      store ??
          (queuePath != null
              ? FileOfflineStore(queuePath)
              : MemoryOfflineStore()),
    ),
    deviceId: deviceId ?? 'mobile-device',
  );
}

class LactevaApp extends StatefulWidget {
  const LactevaApp({super.key, this.queuePath});

  final String? queuePath;

  @override
  State<LactevaApp> createState() => _LactevaAppState();
}

class _LactevaAppState extends State<LactevaApp> {
  final _navigatorKey = GlobalKey<NavigatorState>();
  late final OfflineApiClient _client;

  @override
  void initState() {
    super.initState();
    _client = buildClient(queuePath: widget.queuePath);
    // P0-PRODUCT-008 D-2: when the platform stops accepting the session, the
    // app returns to sign-in ONCE, app-wide, instead of every screen dying on
    // its own raw 401. The offline queue is untouched — captured work waits
    // for the next sign-in and replays idempotently.
    _client.onAuthExpired = _returnToSignIn;
  }

  void _returnToSignIn() {
    _navigatorKey.currentState?.pushAndRemoveUntil(
      MaterialPageRoute(
        builder: (_) => LoginScreen(
          client: _client,
          notice: 'Your session expired — sign in again to continue',
        ),
      ),
      (route) => false,
    );
  }

  @override
  Widget build(BuildContext context) {
    return MaterialApp(
      title: 'Lacteva',
      navigatorKey: _navigatorKey,
      // Design System V1: the shared Lacteva palette and the operator
      // ergonomics that go with it (48dp targets, larger type, milk-on-cream).
      theme: lactevaTheme(),
      home: LoginScreen(client: _client),
    );
  }
}

