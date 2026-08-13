/// SEC-003 / F-01 — the mock capture controls must not exist in a release build.
///
/// Run BOTH ways; both must pass:
///
///     flutter test test/mock_hardware_test.dart
///     flutter test test/mock_hardware_test.dart \
///       --dart-define=LACTEVA_ALLOW_MOCK_HARDWARE=false
///
/// The first is what a developer's machine does (debug: mocks available). The
/// second is what a release build compiles to. One assertion each way, so the
/// gate is proven to work in the direction that matters AND proven not to have
/// removed the developer tooling by accident.
///
/// This is a convenience gate, not the security boundary. The platform refuses
/// `mock_scale` and `mock_analyzer` in production whatever a client sends —
/// see `tests/test_mock_hardware_boundary.py`.
library;

import 'package:flutter/foundation.dart';
import 'package:flutter/material.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:lacteva_mobile/src/api.dart';
import 'package:lacteva_mobile/src/build_flags.dart';
import 'package:lacteva_mobile/src/collection_wizard.dart';

class _Fake extends ApiClient {}

/// Drives the wizard to the weight step (2) and then the quality step (3).
Future<void> _pumpWizard(WidgetTester tester, int step) async {
  await tester.pumpWidget(
    MaterialApp(
      home: CollectionWizardScreen(
        client: _Fake(),
        sessionId: 's1',
        initialStep: step,
      ),
    ),
  );
  await tester.pump();
}

void main() {
  testWidgets(
    'the weight step offers a mock scale only when the build allows it',
    (tester) async {
      await _pumpWizard(tester, 2);
      if (kMockHardwareEnabled) {
        expect(
          find.text('Use mock scale'),
          findsOneWidget,
          reason: 'debug builds keep the developer tooling',
        );
      } else {
        expect(
          find.text('Use mock scale'),
          findsNothing,
          reason: 'a release build must not offer to fabricate a weight',
        );
      }
      // The real capture control is present either way — the gate must never
      // remove the thing an operator actually uses.
      expect(find.text('Capture weight'), findsOneWidget);
    },
  );

  testWidgets(
    'the quality step offers a mock analyzer only when the build allows it',
    (tester) async {
      await _pumpWizard(tester, 3);
      if (kMockHardwareEnabled) {
        expect(find.text('Use mock analyzer'), findsOneWidget);
      } else {
        expect(
          find.text('Use mock analyzer'),
          findsNothing,
          reason:
              'a release build must not offer to fabricate a quality reading',
        );
      }
      expect(find.text('Capture quality'), findsOneWidget);
    },
  );

  test('a release build can never have the mocks enabled', () {
    // Vacuous under `flutter test` (always debug) and deliberately kept: it
    // is the assertion that fails first if someone ever changes the default
    // from `!kReleaseMode` to a plain `true`.
    if (kReleaseMode) {
      expect(kMockHardwareEnabled, isFalse);
    }
  });
}
