// WO-75: the build says which commit it came from, and a developer build
// says so rather than pretending.
import 'package:flutter_test/flutter_test.dart';
import 'package:lacteva_mobile/src/build_info.dart';

void main() {
  test('a stamped build reads commit and time out of the one literal', () {
    expect(
      parseBuildLabel('lacteva-build:abc1234:2026-09-25T14:00Z'),
      'abc1234 · 2026-09-25T14:00Z',
    );
    expect(parseBuildLabel('lacteva-build:abc1234:'), 'abc1234');
  });

  test('an unstamped build says so', () {
    expect(parseBuildLabel('lacteva-build::'), 'unstamped (developer build)');
    expect(parseBuildLabel(''), 'unstamped (developer build)');
    // This test run carries no --dart-define, so the compiled-in stamp is the
    // bare prefix the verifier greps for, and nothing pretends otherwise.
    expect(buildStamp, 'lacteva-build::');
    expect(buildLabel(), 'unstamped (developer build)');
  });
}
