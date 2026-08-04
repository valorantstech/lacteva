import 'dart:async';
import 'dart:convert';

import 'package:flutter/foundation.dart';
import 'package:flutter/material.dart';
import 'package:http/http.dart' as http;

import 'src/centers.dart';
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

void main() {
  runApp(const LactevaApp());
}

/// The app's single offline-capable client (OFF-001).
///
/// A file-backed queue in the app's own directory: it survives restart,
/// reboot, and crash. `MemoryOfflineStore` stands in when no writable
/// directory is available — a queue that forgets still beats an app that
/// cannot collect milk.
OfflineApiClient buildClient({OfflineStore? store, String? deviceId}) {
  return OfflineApiClient(
    queue: SyncQueue(store ?? FileOfflineStore('lacteva_sync_queue.json')),
    deviceId: deviceId ?? 'mobile-device',
  );
}

class LactevaApp extends StatelessWidget {
  const LactevaApp({super.key});

  @override
  Widget build(BuildContext context) {
    return MaterialApp(
      title: 'Lacteva',
      theme: ThemeData(
        colorScheme: ColorScheme.fromSeed(seedColor: const Color(0xFF1B5E20)),
        useMaterial3: true,
      ),
      home: LoginScreen(client: buildClient()),
    );
  }
}

/// SPRINT-001 bootstrap screen: proves the app runs and can reach the
/// platform backend. Business features arrive with the Collect module.
class PlatformStatusScreen extends StatefulWidget {
  const PlatformStatusScreen({super.key});

  @override
  State<PlatformStatusScreen> createState() => _PlatformStatusScreenState();
}

class _PlatformStatusScreenState extends State<PlatformStatusScreen> {
  Map<String, bool>? _checks;
  String? _error;
  bool _loading = false;
  Timer? _timer;

  @override
  void initState() {
    super.initState();
    _refresh();
    _timer = Timer.periodic(const Duration(seconds: 10), (_) => _refresh());
  }

  @override
  void dispose() {
    _timer?.cancel();
    super.dispose();
  }

  Future<void> _refresh() async {
    setState(() => _loading = true);
    try {
      final response = await http
          .get(Uri.parse('$apiUrl/health/ready'))
          .timeout(const Duration(seconds: 5));
      final body = jsonDecode(response.body) as Map<String, dynamic>;
      final checks = (body['checks'] as Map<String, dynamic>).map(
        (key, value) => MapEntry(key, value == true),
      );
      if (!mounted) return;
      setState(() {
        _checks = checks;
        _error = null;
        _loading = false;
      });
    } catch (e) {
      if (!mounted) return;
      setState(() {
        _error = kDebugMode ? e.toString() : 'Backend unreachable';
        _loading = false;
      });
    }
  }

  @override
  Widget build(BuildContext context) {
    final checks = _checks;
    return Scaffold(
      appBar: AppBar(
        title: const Text('Lacteva — Platform Status'),
        actions: [
          IconButton(
            onPressed: _loading ? null : _refresh,
            icon: const Icon(Icons.refresh),
            tooltip: 'Refresh',
          ),
        ],
      ),
      body: Center(
        child: Padding(
          padding: const EdgeInsets.all(24),
          child: Column(
            mainAxisAlignment: MainAxisAlignment.center,
            crossAxisAlignment: CrossAxisAlignment.stretch,
            children: [
              Text(
                'platform-core',
                style: Theme.of(context).textTheme.titleLarge,
                textAlign: TextAlign.center,
              ),
              const SizedBox(height: 4),
              Text(
                apiUrl,
                style: Theme.of(context).textTheme.bodySmall,
                textAlign: TextAlign.center,
              ),
              const SizedBox(height: 24),
              if (_loading && checks == null)
                const Center(child: CircularProgressIndicator()),
              if (_error != null)
                Card(
                  child: ListTile(
                    leading: const Icon(Icons.cloud_off, color: Colors.red),
                    title: const Text('Unreachable'),
                    subtitle: Text(_error!),
                  ),
                ),
              if (checks != null)
                ...checks.entries.map(
                  (entry) => Card(
                    child: ListTile(
                      leading: Icon(
                        entry.value ? Icons.check_circle : Icons.error,
                        color: entry.value ? Colors.green : Colors.red,
                      ),
                      title: Text(entry.key),
                      trailing: Text(entry.value ? 'healthy' : 'down'),
                    ),
                  ),
                ),
            ],
          ),
        ),
      ),
    );
  }
}
