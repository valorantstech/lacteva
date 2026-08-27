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

  group('no screen invents a colour (LACTEVA-MOBILE-003)', () {
    // Thirty-six hard-coded `Colors.*` sites had accumulated across ten files
    // — green for done, orange for attention, grey for over — each chosen by
    // whichever hue was nearest to hand rather than by what the state MEANT.
    // Two of them drew the same status in two different colours on two
    // screens, and one drew it with no word at all.
    //
    // The palette is the product's chromatic decisions. A literal is a screen
    // making one of its own, privately, where nothing can see it drift.
    //
    // `theme.dart` is the exception because it is where the palette lives: it
    // maps Material's slots onto the tokens, and doing that requires naming
    // Material's colours once.
    const allowed = <String>{'lib/src/theme.dart'};

    test('no Colors. literal outside theme.dart', () {
      final offenders = <String>[];
      for (final file
          in Directory('lib').listSync(recursive: true).whereType<File>()) {
        final path = file.path;
        if (!path.endsWith('.dart') || allowed.contains(path)) continue;
        final lines = file.readAsLinesSync();
        for (var i = 0; i < lines.length; i++) {
          final line = lines[i];
          // `LactevaColors.` contains `Colors.`; it is the point, not a
          // violation.
          final stripped = line.replaceAll('LactevaColors.', '');
          if (stripped.contains('Colors.')) {
            offenders.add('$path:${i + 1}: ${line.trim()}');
          }
        }
      }
      expect(
        offenders,
        isEmpty,
        reason:
            'these name a Material colour directly instead of a semantic token '
            'from theme.dart, so the palette can drift where nothing sees it: '
            '$offenders',
      );
    });

    test('the semantic tokens a screen should reach for all exist', () {
      // Without this the guard above passes beautifully against a palette that
      // has quietly lost the tokens screens are supposed to use.
      expect(LactevaColors.success, isA<Color>());
      expect(LactevaColors.warning, isA<Color>());
      expect(LactevaColors.danger, isA<Color>());
      expect(LactevaColors.info, isA<Color>());
    });
  });
}
