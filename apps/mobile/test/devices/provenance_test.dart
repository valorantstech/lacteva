// A device reading is the device's only until somebody changes it (WO-49).
//
// This is the rule that decides what the platform is TOLD about where a number
// came from, so it is the rule most worth attacking.
import 'package:flutter_test/flutter_test.dart';
import 'package:lacteva_mobile/src/devices/device_bridge.dart';

const _reading = DeviceReading(
  values: {'fat': 4.2, 'snf': 8.45, 'clr': 27.5},
  deviceId: 'device-1',
  frameHash: 'sha256:abc',
  profileKey: 'lacteva-sim-analyzer-v1',
);

void main() {
  test('an untouched reading is attributed to the analyzer', () {
    final body = provenanceFor(
      reading: _reading,
      filled: const {'fat': '4.2', 'snf': '8.45', 'clr': '27.5'},
      current: const {'fat': '4.2', 'snf': '8.45', 'clr': '27.5'},
      instrumentSource: 'analyzer',
    );
    expect(body['source'], 'analyzer');
    expect(body['device_id'], 'device-1');
    expect(body['frame_hash'], 'sha256:abc');
  });

  test('editing ONE field drops the whole attribution to manual', () {
    // Fat from the device and SNF from the operator is one reading with two
    // authors, and no single source name tells that truth.
    final body = provenanceFor(
      reading: _reading,
      filled: const {'fat': '4.2', 'snf': '8.45', 'clr': '27.5'},
      current: const {'fat': '4.4', 'snf': '8.45', 'clr': '27.5'},
      instrumentSource: 'analyzer',
    );
    expect(body['source'], 'manual');
    expect(body.containsKey('device_id'), isFalse,
        reason: 'a hand-corrected number must not name a device');
  });

  test('clearing a field is an edit too', () {
    final body = provenanceFor(
      reading: _reading,
      filled: const {'fat': '4.2'},
      current: const {'fat': ''},
      instrumentSource: 'analyzer',
    );
    expect(body['source'], 'manual');
  });

  test('with no reading at all the capture is manual', () {
    final body = provenanceFor(
      reading: null,
      filled: const {},
      current: const {'fat': '4.2'},
      instrumentSource: 'analyzer',
    );
    expect(body['source'], 'manual');
    expect(body.length, 1);
  });

  test('whitespace is not an edit', () {
    final body = provenanceFor(
      reading: _reading,
      filled: const {'fat': '4.2'},
      current: const {'fat': ' 4.2 '},
      instrumentSource: 'analyzer',
    );
    expect(body['source'], 'analyzer');
  });
}
