import 'dart:async';
import 'dart:convert';
import 'dart:io';

/// Durable key-value storage for the offline layer (OFF-001).
///
/// A port, not a database. The queue must survive an app restart, a device
/// reboot, and a crash mid-write — which is a small enough contract that a
/// JSON document written atomically satisfies it without dragging a database
/// engine (and its platform channels) into a codebase that tests on the Dart
/// VM. When the offline surface grows beyond one queue, this is the seam a
/// real database slides behind.
abstract class OfflineStore {
  Future<Map<String, dynamic>?> read();

  Future<void> write(Map<String, dynamic> data);
}

/// In-memory store — the test double, and the fallback when no writable
/// directory exists (a queue that forgets is better than an app that cannot
/// collect milk).
class MemoryOfflineStore implements OfflineStore {
  Map<String, dynamic>? _data;

  /// Copies on both sides so a caller mutating its map cannot corrupt state.
  @override
  Future<Map<String, dynamic>?> read() async => _data == null
      ? null
      : jsonDecode(jsonEncode(_data)) as Map<String, dynamic>;

  @override
  Future<void> write(Map<String, dynamic> data) async {
    _data = jsonDecode(jsonEncode(data)) as Map<String, dynamic>;
  }
}

/// File-backed store with atomic replacement.
///
/// The write goes to a temporary file and is then renamed over the target.
/// Rename is atomic on every platform we ship to, so a crash leaves either
/// the previous complete queue or the new one — never a half-written file
/// that would lose a morning's collections.
class FileOfflineStore implements OfflineStore {
  FileOfflineStore(this.path);

  final String path;

  @override
  Future<Map<String, dynamic>?> read() async {
    final file = File(path);
    if (!await file.exists()) return null;
    try {
      final content = await file.readAsString();
      if (content.trim().isEmpty) return null;
      return jsonDecode(content) as Map<String, dynamic>;
    } catch (_) {
      // A corrupt file must not brick the app. Start clean; the operator
      // sees an empty queue rather than a crash loop.
      return null;
    }
  }

  @override
  Future<void> write(Map<String, dynamic> data) async {
    final target = File(path);
    await target.parent.create(recursive: true);
    final temp = File('$path.tmp');
    await temp.writeAsString(jsonEncode(data), flush: true);
    await temp.rename(path);
  }
}
