/// One reading, from a registered device, ready for the capture screen (WO-49).
///
/// This is the Centre Connector of the hardware spec §5 — living in the
/// operator's pocket rather than on a PC the centre may not own, which §17 of
/// the discovery document leaves open as a runtime choice.
///
/// It does exactly what the spec's §3 boundary allows and nothing else: it
/// turns bytes into a measurement and says which device produced them. No
/// price, no decision, no settlement figure. "Pricing or settlement logic
/// inside a device integration is a defect by definition."
library;

import 'dart:async';
import 'dart:convert';

import 'package:crypto/crypto.dart';

import 'device_transport.dart';
import 'frame_profile.dart';

/// A measurement plus the provenance the platform will refuse to accept it
/// without.
class DeviceReading {
  const DeviceReading({
    required this.values,
    required this.deviceId,
    required this.frameHash,
    required this.profileKey,
  });

  final Map<String, double> values;
  final String deviceId;

  /// A digest of the raw frame — never the frame itself, which can carry a
  /// serial or a calibration record the platform has no business storing.
  /// Enough to tie a disputed reading back to the bytes that produced it.
  final String frameHash;
  final String profileKey;
}

/// Binds a registered Device to a transport and a profile.
class DeviceBridge {
  DeviceBridge({
    required this.deviceId,
    required this.profile,
    required this.transport,
  });

  final String deviceId;
  final FrameProfile profile;
  final DeviceTransport transport;

  /// The first frame this device sends that parses cleanly.
  ///
  /// READ-ASSIST, not auto-capture (spec §5: hands-free is a later, Advanced
  /// profile increment). The operator asks for a reading, one arrives, and
  /// they confirm it — so a stale frame sitting in a buffer can never post
  /// itself against the wrong farmer.
  ///
  /// Frames that fail to parse are SKIPPED rather than thrown, because an
  /// instrument that streams until its weight settles emits partial records
  /// by design, and the first one is usually garbage. Frames that fail a
  /// checksum are skipped for the opposite reason: they are corrupt, and a
  /// corrupt reading must never reach the screen.
  Future<DeviceReading> read({Duration timeout = const Duration(seconds: 10)}) async {
    final completer = Completer<DeviceReading>();
    late final StreamSubscription<String> subscription;

    subscription = transport.frames().listen(
      (frame) {
        if (completer.isCompleted) return;
        try {
          final values = profile.parse(frame);
          completer.complete(DeviceReading(
            values: values,
            deviceId: deviceId,
            frameHash: 'sha256:${sha256.convert(utf8.encode(frame)).toString()}',
            profileKey: profile.key,
          ));
        } on FrameProfileError {
          // Not this frame. Wait for the next one.
        }
      },
      onError: (Object error) {
        if (!completer.isCompleted) completer.completeError(error);
      },
      onDone: () {
        if (!completer.isCompleted) {
          completer.completeError(
            DeviceTransportError('${transport.description} closed before sending a reading'),
          );
        }
      },
    );

    try {
      return await completer.future.timeout(
        timeout,
        onTimeout: () => throw DeviceTransportError(
          'no reading from ${transport.description} in ${timeout.inSeconds}s',
        ),
      );
    } finally {
      // ORDER MATTERS, and the silent-instrument test is what proved it.
      // Cancelling a subscription to a socket stream waits for that stream to
      // finish, and a connected-but-silent device never finishes one — so
      // cancelling first hangs for as long as the instrument stays quiet,
      // which is the exact failure spec §8 forbids. Tear the socket down, and
      // the cancel then completes on its own.
      await transport.close();
      unawaited(subscription.cancel());
    }
  }
}

/// What to send as the source, given a reading and what is now in the fields.
///
/// THE RULE THIS ENCODES. A device reading is the device's only until somebody
/// changes it. An operator who reads 4.2 from the analyzer and types 4.4 over
/// it has made a manual measurement, and calling it `analyzer` would attribute
/// a human's number to a machine — the exact fabrication provenance exists to
/// make visible (spec §7). So any edit, to any assisted field, drops the whole
/// attribution back to manual.
///
/// Deliberately all-or-nothing: there is no such thing as half an analyzer
/// reading. Fat from the device and SNF from the operator is one reading with
/// two authors, and no single source name tells that truth.
Map<String, Object?> provenanceFor({
  required DeviceReading? reading,
  required Map<String, String> filled,
  required Map<String, String> current,
  required String instrumentSource,
}) {
  if (reading == null || filled.isEmpty) return const {'source': 'manual'};
  for (final entry in filled.entries) {
    if (current[entry.key]?.trim() != entry.value.trim()) {
      return const {'source': 'manual'};
    }
  }
  return {
    'source': instrumentSource,
    'device_id': reading.deviceId,
    'frame_hash': reading.frameHash,
  };
}
