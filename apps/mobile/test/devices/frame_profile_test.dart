// The parser is the part that can silently be wrong (WO-49).
//
// A transport that fails is obvious — nothing arrives. A parser that
// mis-reads is not: it produces a number of the right magnitude, in the right
// field, and it gets priced, settled and paid. FINAL-001 is the precedent in
// this repository, and it is why every test here is about a frame that is
// WRONG rather than one that is right.
import 'package:flutter_test/flutter_test.dart';
import 'package:lacteva_mobile/src/devices/frame_profile.dart';

void main() {
  group('a well-formed frame', () {
    test('reads the fields the platform actually accepts', () {
      final values = simulatorAnalyzerProfile.parse('LACTEVA,4.2,8.45,27.5,1.029,4.0\n');
      expect(values['fat'], 4.2);
      expect(values['snf'], 8.45);
      expect(values['clr'], 27.5);
      expect(values['density'], 1.029);
      expect(values['temperature_c'], 4.0);
    });

    test('every mapped field is one the capture endpoint knows', () {
      for (final profile in shippedProfiles) {
        for (final field in profile.fieldMap.values) {
          expect(
            analyzerFields.contains(field) || scaleFields.contains(field),
            isTrue,
            reason: '$field is not a measurement the platform accepts',
          );
        }
      }
    });
  });

  group('a frame that must not become a reading', () {
    test('a short frame is refused, not padded', () {
      expect(
        () => simulatorAnalyzerProfile.parse('LACTEVA,4.2,8.45'),
        throwsA(isA<FrameProfileError>()),
      );
    });

    test('a non-numeric field is refused rather than coerced to zero', () {
      // A silent 0.0 fat is a farmer paid nothing for good milk.
      expect(
        () => simulatorAnalyzerProfile.parse('LACTEVA,ERR,8.45,27.5,1.029,4.0'),
        throwsA(isA<FrameProfileError>()),
      );
    });

    test('an empty frame is refused', () {
      expect(() => simulatorAnalyzerProfile.parse('   '), throwsA(isA<FrameProfileError>()));
    });

    test('a frame failing its own checksum never reaches the operator', () {
      const checked = FrameProfile(
        key: 'test-checksum',
        label: 'checksum probe',
        fieldDelimiter: ',',
        fieldMap: {1: 'fat'},
        checksum: ChecksumRule.sumOfBytesMod256Hex,
      );
      expect(() => checked.parse('X,4.2,00'), throwsA(isA<FrameProfileError>()));
    });

    test('a frame passing its checksum is read', () {
      const checked = FrameProfile(
        key: 'test-checksum',
        label: 'checksum probe',
        fieldDelimiter: ',',
        fieldMap: {1: 'fat'},
        checksum: ChecksumRule.sumOfBytesMod256Hex,
      );
      const body = 'X,4.2';
      final sum = body.codeUnits.fold<int>(0, (a, b) => a + b) % 256;
      final hex = sum.toRadixString(16).padLeft(2, '0').toUpperCase();
      expect(checked.parse('$body,$hex')['fat'], 4.2);
    });
  });

  group('what this repository is allowed to claim', () {
    test('every shipped profile has been proven against a real capture', () {
      // The architecture's hard rule, as a test. Integration spec §14: "no
      // protocol guessed from memory — every adapter starts from captured raw
      // output of the pilot's actual device." Discovery §29 makes ≥5 captured
      // samples a gate. If someone adds an "Ekomilk-class" profile from
      // memory, this fails, and it should.
      for (final profile in shippedProfiles) {
        expect(
          profile.verified,
          isTrue,
          reason: 'profile "${profile.key}" ships unverified — §29 requires captured raw output '
              'from the device it claims to describe before it can be trusted',
        );
      }
    });

    test('the shipped list is only the simulator, until a bench proves more', () {
      expect(shippedProfiles.map((p) => p.key).toList(),
          ['lacteva-sim-analyzer-v1', 'lacteva-sim-scale-v1']);
    });
  });
}
