/// Where a signed-in session lives between launches.
///
/// Owner, 2026-09-04: "when I restart the app it is always asking for login;
/// once I logged in it should always be logged in till I logout." Until now
/// both halves of the platform's `TokenPair` lived only in the client's
/// memory (WO-69 said so deliberately: "never a preference file"), so every
/// process death — a reboot, Android reclaiming memory overnight, the owner
/// swiping the app away — was a sign-out. The platform's session is fourteen
/// days long; the app was throwing it away.
///
/// The decision is the owner's; the engineering is that the pair is kept in
/// the platform's ENCRYPTED store — Android Keystore-backed
/// EncryptedSharedPreferences, the iOS Keychain — never a plain file, and
/// forgotten the moment the session ends: explicit sign-out, or the platform
/// refusing a refresh. Nothing here decides whether a session is valid; the
/// platform does that on the first request, and a stale pair simply fails
/// forward into the sign-in screen through the D-2 flow.
///
/// A port with two implementations, like every other piece of
/// infrastructure in this app: [SecureSessionStore] on a device,
/// [MemorySessionStore] in tests.
library;

import 'package:flutter_secure_storage/flutter_secure_storage.dart';

/// The two halves of a platform session, as the platform issued them.
class StoredSession {
  const StoredSession({required this.accessToken, required this.refreshToken});

  final String accessToken;
  final String refreshToken;
}

abstract class SessionStore {
  /// The session saved by the last sign-in or refresh, or `null` when there
  /// is none — including when the store itself cannot be read, because a
  /// store that throws at startup would take the app down with it.
  Future<StoredSession?> read();

  Future<void> write(StoredSession session);

  Future<void> clear();
}

/// Tests, and a device whose secure storage is unavailable.
class MemorySessionStore implements SessionStore {
  StoredSession? _session;
  int writes = 0;
  int clears = 0;

  @override
  Future<StoredSession?> read() async => _session;

  @override
  Future<void> write(StoredSession session) async {
    writes++;
    _session = session;
  }

  @override
  Future<void> clear() async {
    clears++;
    _session = null;
  }
}

/// The device's encrypted store. Both tokens under two keys; a half-written
/// pair reads as no session.
class SecureSessionStore implements SessionStore {
  SecureSessionStore({FlutterSecureStorage? storage})
    // 9.x is pinned: 10+ compiles against Android SDK 37, which neither this
    // machine nor CI has yet. Encrypted preferences are opt-in here, and on.
    : _storage =
          storage ??
          const FlutterSecureStorage(
            aOptions: AndroidOptions(encryptedSharedPreferences: true),
          );

  final FlutterSecureStorage _storage;

  static const _accessKey = 'lacteva.session.access';
  static const _refreshKey = 'lacteva.session.refresh';

  @override
  Future<StoredSession?> read() async {
    try {
      final access = await _storage.read(key: _accessKey);
      final refresh = await _storage.read(key: _refreshKey);
      if (access == null || refresh == null || access.isEmpty || refresh.isEmpty) {
        return null;
      }
      return StoredSession(accessToken: access, refreshToken: refresh);
    } catch (_) {
      // Keystore trouble (a restored backup, a changed lock screen) must
      // cost one sign-in, not the app.
      return null;
    }
  }

  @override
  Future<void> write(StoredSession session) async {
    try {
      await _storage.write(key: _accessKey, value: session.accessToken);
      await _storage.write(key: _refreshKey, value: session.refreshToken);
    } catch (_) {
      // The session still works for this launch; the next one signs in.
    }
  }

  @override
  Future<void> clear() async {
    try {
      await _storage.delete(key: _accessKey);
      await _storage.delete(key: _refreshKey);
    } catch (_) {}
  }
}
