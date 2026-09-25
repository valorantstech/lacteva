/// The size-and-text-scale matrix (WO-96 / owner decision D-45).
///
/// "Responsive" for the app means: every screen renders with no RenderFlex
/// overflow and nothing thrown on small phones, large phones, tablets and in
/// landscape, at system text scale 1.0, 1.3 and 2.0 — large text is common
/// among exactly the people who use this app. Flutter reports an overflow as
/// an error, and `takeException` is where the test framework hands it back,
/// so the harness is the loop and the assertion.
///
/// Each experience's own suite calls [pumpMatrix] with its own fixtures, so
/// the screen is pumped with the data it really shows, not an error state.
library;

import 'package:flutter/material.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:lacteva_mobile/src/theme.dart';

/// Small phone, the common Android, a large phone, a tablet — logical pixels.
const matrixSizes = <Size>[
  Size(320, 568),
  Size(360, 800),
  Size(412, 915),
  Size(800, 1280),
];

/// System text scales: default, "large", and accessibility "largest".
const matrixScales = <double>[1.0, 1.3, 2.0];

/// Pumps [build]'s screen at every size, both orientations, every text
/// scale, and fails on the first exception — with the cell named.
Future<void> pumpMatrix(
  WidgetTester tester,
  String label,
  Widget Function() build, {
  Duration settle = const Duration(milliseconds: 400),
}) async {
  addTearDown(tester.view.reset);
  addTearDown(tester.platformDispatcher.clearTextScaleFactorTestValue);
  for (final size in matrixSizes) {
    for (final portrait in const [true, false]) {
      final s = portrait ? size : Size(size.height, size.width);
      for (final scale in matrixScales) {
        tester.view.physicalSize = s;
        tester.view.devicePixelRatio = 1.0;
        tester.platformDispatcher.textScaleFactorTestValue = scale;
        // Catch the framework's own report, which names the widget and its
        // ancestors — `takeException` alone hands back only the one-line
        // summary, and "a Row overflowed" without a file is not a finding
        // anyone can act on.
        final caught = <FlutterErrorDetails>[];
        final previous = FlutterError.onError;
        FlutterError.onError = caught.add;
        await tester.pumpWidget(
          MaterialApp(
            theme: lactevaTheme(),
            home: Builder(
              builder: (context) => MediaQuery(
                // Animations off, so a shimmer or a droplet that repeats
                // forever does not keep the frame from settling.
                data: MediaQuery.of(context).copyWith(disableAnimations: true),
                child: build(),
              ),
            ),
          ),
        );
        await tester.pump();
        await tester.pump(settle);
        FlutterError.onError = previous;
        final error = tester.takeException();
        final where = caught
            .map((d) => d.toString())
            .where((t) => t.contains('creator:') || t.contains('error-causing'))
            .map(
              (t) => t
                  .split('\n')
                  .where((l) => l.contains('creator:') || l.contains('.dart:') || l.contains('←'))
                  .take(4)
                  .join(' '),
            )
            .join(' | ');
        expect(
          caught.isEmpty && error == null,
          isTrue,
          reason:
              '$label overflowed or threw at ${s.width.toInt()}x${s.height.toInt()} '
              '(${portrait ? "portrait" : "landscape"}), text scale $scale: '
              '${caught.isNotEmpty ? caught.first.exceptionAsString() : error} — $where',
        );
      }
    }
  }
  // A fresh tree for whatever the calling test does next.
  await tester.pumpWidget(const SizedBox.shrink());
}
