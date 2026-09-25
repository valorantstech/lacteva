// WO-75: the build says which commit it came from, and a developer build
// says so rather than pretending.
import 'package:flutter_test/flutter_test.dart';
import 'package:lacteva_mobile/src/build_info.dart';

void main() {
  test('a stamped build reads commit and time', () {
    expect(
      buildLabel(commit: 'abc1234', time: '2026-09-25T14:00Z'),
      'abc1234 · 2026-09-25T14:00Z',
    );
    expect(buildLabel(commit: 'abc1234', time: ''), 'abc1234');
  });

  test('an unstamped build says so', () {
    expect(buildLabel(commit: '', time: ''), 'unstamped (developer build)');
    // This test run carries no --dart-define, so the compiled-in stamp is the
    // bare prefix the verifier greps for, and nothing pretends otherwise.
    expect(buildStamp, 'lacteva-build::');
    expect(buildLabel(), 'unstamped (developer build)');
  });
}
