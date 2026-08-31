/// Parsing an instrument's frame, as DATA rather than as code.
///
/// WO-49 · LACTEVA-DEVICE-001.
///
/// WHY A PROFILE AND NOT A DRIVER PER MODEL. Collection centres in India run
/// whatever analyzer the dairy could afford, and the field is long-tailed: a
/// per-model Dart class means every new centre needs an app release. A profile
/// is a row — delimiters, a field map, a checksum rule — so a device that
/// speaks a new ASCII dialect is a configuration change against its registered
/// Device, not a build.
///
/// WHAT IS DELIBERATELY ABSENT: profiles for named commercial analyzers.
///
/// The approved architecture forbids it twice. The integration spec §14 lists
/// "no protocol guessed from memory — every adapter starts from captured raw
/// output of the pilot's actual device" under **What must NOT be built**, and
/// the discovery document's §29 makes captured raw output for ≥5 real samples
/// a hard gate: "If any Required item is missing, P0-HW-003 does not start."
/// D-15 restates it — per-model drivers are proven only against captured raw
/// output from a real device.
///
/// So this ships the MECHANISM and exactly one profile: the simulator's, which
/// is the only device whose frames anyone here has actually captured. Writing
/// an "Ekomilk-class" profile from memory would be inventing a delimiter, a
/// field order and a checksum for a device nobody has seen, and marking it
/// UNVERIFIED does not make the numbers it would silently mis-parse any less
/// wrong. Profiles for real models land when D-16 puts one on a bench.
library;

import 'dart:convert';

/// Where a value sits in a parsed frame, and what it means to the platform.
///
/// The keys are the platform's own field names (`fat`, `snf`, `clr`,
/// `density`, `temperature_c`, `gross`, `tare`) so a profile cannot invent a
/// measurement the capture endpoints do not accept.
const analyzerFields = {'fat', 'snf', 'clr', 'density', 'temperature_c'};
const scaleFields = {'gross', 'tare'};

class FrameProfileError implements Exception {
  FrameProfileError(this.message);
  final String message;
  @override
  String toString() => 'FrameProfileError: $message';
}

/// How a frame is checked before anything in it is believed.
enum ChecksumRule {
  /// The device sends no checksum. The frame is accepted on structure alone.
  none,

  /// The last field is the sum of every preceding byte, modulo 256, in hex.
  /// Common in the ASCII line protocols this class of instrument uses — and
  /// still unverified against any real device, which is why no real profile
  /// selects it yet.
  sumOfBytesMod256Hex,
}

/// One instrument dialect, as data.
class FrameProfile {
  const FrameProfile({
    required this.key,
    required this.label,
    required this.fieldDelimiter,
    required this.fieldMap,
    this.recordTerminator = '\n',
    this.checksum = ChecksumRule.none,
    this.verified = false,
  });

  /// Stable identifier, stored against the registered Device.
  final String key;
  final String label;
  final String fieldDelimiter;
  final String recordTerminator;

  /// Position in the split frame → platform field name.
  final Map<int, String> fieldMap;
  final ChecksumRule checksum;

  /// Whether this profile has been proven against captured output from the
  /// device it claims to describe. **A profile that has not is not shipped**
  /// (see the library docstring); the flag exists so that the moment one is
  /// added from a bench capture, the UI can say which it is rather than
  /// implying every profile is equally trustworthy.
  final bool verified;

  Map<String, double> parse(String frame) {
    final trimmed = frame.trim();
    if (trimmed.isEmpty) {
      throw FrameProfileError('empty frame');
    }
    var parts = trimmed.split(fieldDelimiter).map((p) => p.trim()).toList();

    if (checksum == ChecksumRule.sumOfBytesMod256Hex) {
      if (parts.length < 2) {
        throw FrameProfileError('frame too short to carry a checksum');
      }
      final claimed = parts.removeLast();
      final body = parts.join(fieldDelimiter);
      final actual = utf8
              .encode(body)
              .fold<int>(0, (sum, byte) => sum + byte) %
          256;
      final expected = actual.toRadixString(16).padLeft(2, '0').toUpperCase();
      if (claimed.toUpperCase() != expected) {
        // A frame that fails its own checksum is not a reading to fall back
        // from — it is a reading that must never reach the operator's screen.
        throw FrameProfileError('checksum $claimed does not match $expected');
      }
    }

    final values = <String, double>{};
    fieldMap.forEach((index, field) {
      if (index >= parts.length) {
        throw FrameProfileError('frame has ${parts.length} fields, needs index $index for $field');
      }
      final raw = parts[index];
      final parsed = double.tryParse(raw);
      if (parsed == null) {
        throw FrameProfileError('field $field at $index is not a number: "$raw"');
      }
      values[field] = parsed;
    });
    if (values.isEmpty) {
      throw FrameProfileError('profile ${profileKeyOf(this)} maps no fields');
    }
    return values;
  }
}

String profileKeyOf(FrameProfile p) => p.key;

/// The one profile with captured output behind it: the development simulator's.
///
/// Its frames are `LACTEVA,fat,snf,clr,density,temp` — a shape chosen here,
/// emitted by `tools/device_simulator.dart`, and therefore the only dialect in
/// this repository that anybody can honestly claim to have parsed correctly.
const simulatorAnalyzerProfile = FrameProfile(
  key: 'lacteva-sim-analyzer-v1',
  label: 'Lacteva development simulator (analyzer)',
  fieldDelimiter: ',',
  fieldMap: {1: 'fat', 2: 'snf', 3: 'clr', 4: 'density', 5: 'temperature_c'},
  verified: true,
);

const simulatorScaleProfile = FrameProfile(
  key: 'lacteva-sim-scale-v1',
  label: 'Lacteva development simulator (scale)',
  fieldDelimiter: ',',
  fieldMap: {1: 'gross', 2: 'tare'},
  verified: true,
);

/// Every profile the app can assign to a device today.
///
/// Two entries, both the simulator's, and that is the honest length of this
/// list until a real instrument has been on a bench (D-16).
const shippedProfiles = <FrameProfile>[
  simulatorAnalyzerProfile,
  simulatorScaleProfile,
];

FrameProfile? profileByKey(String key) {
  for (final profile in shippedProfiles) {
    if (profile.key == key) return profile;
  }
  return null;
}
