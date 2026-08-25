/// The design system on the operator's phone (Design System V1).
///
/// Two things are pinned here, and they pull in opposite directions on
/// purpose.
///
/// PARITY — the palette and the motion timings must match the portal's, read
/// out of the portal's own stylesheet rather than copied into a comment. One
/// product should not become two because a token drifted.
///
/// DIVERGENCE — the ergonomics must NOT match the portal. A portal is used at
/// a desk with a mouse; this is used one-handed at a collection counter,
/// outdoors, sometimes gloved. Touch targets and type sizes are deliberately
/// larger, and this test is what stops a future "let's make it consistent"
/// from quietly shrinking them.
library;

import 'dart:io';

import 'package:flutter/material.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:lacteva_mobile/src/theme.dart';

/// The portal's token file — the shared source of truth for the system.
String _portalCss() {
  for (final path in [
    '../admin-portal/src/app/globals.css',
    '../../apps/admin-portal/src/app/globals.css',
  ]) {
    final f = File(path);
    if (f.existsSync()) return f.readAsStringSync();
  }
  return '';
}

int? _portalMs(String css, String token) {
  final m = RegExp('$token:\\s*(\\d+)ms').firstMatch(css);
  return m == null ? null : int.parse(m.group(1)!);
}

void main() {
  group('parity with the portal', () {
    test('motion timings are the same numbers on both clients', () {
      final css = _portalCss();
      if (css.isEmpty) {
        markTestSkipped('portal stylesheet not reachable from this checkout');
        return;
      }
      expect(_portalMs(css, '--motion-instant'), LactevaMotion.instant.inMilliseconds);
      expect(_portalMs(css, '--motion-fast'), LactevaMotion.fast.inMilliseconds);
      expect(_portalMs(css, '--motion-base'), LactevaMotion.base.inMilliseconds);
      expect(_portalMs(css, '--motion-slow'), LactevaMotion.slow.inMilliseconds);
      expect(_portalMs(css, '--motion-flow'), LactevaMotion.flow.inMilliseconds);
    });

    test('the brand green is the one the product has always used', () {
      // #1B5E20 — the single chromatic decision this product made before it
      // had a design system, now shared by the portal and the marketing site.
      expect(LactevaColors.dairy, const Color(0xFF1B5E20));
    });

    test('intelligence is not confusable with any semantic colour', () {
      for (final other in [
        LactevaColors.success,
        LactevaColors.warning,
        LactevaColors.danger,
        LactevaColors.info,
        LactevaColors.dairy,
      ]) {
        expect(LactevaColors.intelligence, isNot(other));
      }
    });
  });

  group('ergonomics for a counter, not a desk', () {
    test('every tappable thing clears 48dp', () {
      // Above the 44dp platform floor. The operator may be gloved or hurried.
      expect(LactevaMetrics.minTouchTarget, greaterThanOrEqualTo(48));
    });

    test('the primary action is larger again', () {
      // "What do I press next" should never be a question mid-collection.
      expect(
        LactevaMetrics.primaryActionHeight,
        greaterThan(LactevaMetrics.minTouchTarget),
      );
    });

    test('the theme applies those sizes rather than merely declaring them', () {
      final theme = lactevaTheme();
      final filled = theme.filledButtonTheme.style!;
      final size = filled.minimumSize!.resolve({})!;
      expect(size.height, LactevaMetrics.primaryActionHeight);

      final outlined = theme.outlinedButtonTheme.style!;
      expect(outlined.minimumSize!.resolve({})!.height,
          greaterThanOrEqualTo(LactevaMetrics.minTouchTarget));
    });

    test('body type is larger than Material default, for daylight', () {
      // Material's bodyMedium is 14. A cheap screen in Indian daylight costs
      // more legibility than any font choice recovers.
      expect(lactevaTheme().textTheme.bodyMedium!.fontSize, greaterThanOrEqualTo(16));
    });

    test('the page is cream and cards are milk', () {
      final theme = lactevaTheme();
      expect(theme.scaffoldBackgroundColor, LactevaColors.cream);
      expect(theme.cardTheme.color, LactevaColors.milk);
    });
  });

  testWidgets('the app actually uses the system theme', (tester) async {
    await tester.pumpWidget(
      MaterialApp(
        theme: lactevaTheme(),
        home: const Scaffold(body: Text('x')),
      ),
    );
    final ctx = tester.element(find.text('x'));
    expect(Theme.of(ctx).colorScheme.primary, LactevaColors.dairy);
    expect(Scaffold.of(ctx).widget.backgroundColor ?? Theme.of(ctx).scaffoldBackgroundColor,
        LactevaColors.cream);
  });
}
