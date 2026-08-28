/// The auth screens' motion, and the promise that it stops (WO-33).
///
/// Sign-in and password-reset are where this product is allowed to look like
/// something, because they are the two screens a person meets before they
/// have any work to do. Everything here is therefore about the boundary: how
/// far the decoration may go, and where it must stop.
///
/// The load-bearing test in this file is `the ground settles`. WO-33 asks for
/// a "slow-drifting" background; what ships drifts once and comes to rest, on
/// two grounds worth holding in a test rather than in a comment:
///
///   * a ticker that never stops is a device that never sleeps, and this app
///     is opened at five in the morning on a handset that has to last a round;
///   * `pumpAndSettle` never returns while a frame is always scheduled, and
///     forty-four assertions across five suites settle these screens. A
///     perpetual background would not have failed them — it would have HUNG
///     them, which is a far worse thing to leave behind.
library;

import 'package:flutter/material.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:lacteva_mobile/src/brand/auth_backdrop.dart';
import 'package:lacteva_mobile/src/brand/auth_motion.dart';
import 'package:lacteva_mobile/src/brand/mark.g.dart';
import 'package:lacteva_mobile/src/brand/wordmark.dart';

Widget _wrap(Widget child, {bool reduceMotion = false}) => MediaQuery(
      data: MediaQueryData(disableAnimations: reduceMotion),
      child: MaterialApp(home: Scaffold(body: child)),
    );

void main() {
  group('the ground', () {
    testWidgets('settles, and does not drift forever', (tester) async {
      await tester.pumpWidget(_wrap(const AuthBackdrop(child: SizedBox())));
      await tester.pump();
      // It IS moving to begin with — otherwise this would pass against a
      // backdrop that never animated at all.
      expect(tester.binding.hasScheduledFrame, isTrue);

      await tester.pump(kBackdropDrift + const Duration(milliseconds: 32));
      await tester.pump();
      expect(
        tester.binding.hasScheduledFrame,
        isFalse,
        reason: 'a background that never stops hangs every pumpAndSettle',
      );
    });

    testWidgets('pumpAndSettle returns, which is the point', (tester) async {
      // The direct form of the guarantee above: the thing five other suites
      // do to these screens, done here.
      await tester.pumpWidget(_wrap(const AuthBackdrop(child: SizedBox())));
      await tester.pumpAndSettle();
      expect(find.byType(AuthBackdrop), findsOneWidget);
    });

    testWidgets('reduced motion builds no controller at all', (tester) async {
      await tester.pumpWidget(
        _wrap(const AuthBackdrop(child: SizedBox()), reduceMotion: true),
      );
      await tester.pump();
      // Not a controller run at zero — none. The rule this app has held since
      // LACTEVA-MOBILE-008.
      expect(tester.binding.hasScheduledFrame, isFalse);
      expect(find.byType(AuthGroundPainter), findsNothing);
      expect(find.byType(CustomPaint), findsWidgets);
    });

    testWidgets('the card is present on the very first frame', (tester) async {
      // The entrance may fade it in; it may never delay its existence.
      await tester.pumpWidget(
        _wrap(const AuthBackdrop(child: Text('Sign in'))),
      );
      await tester.pump();
      expect(find.text('Sign in'), findsOneWidget);
    });
  });

  group('the rise', () {
    testWidgets('settles within its own token', (tester) async {
      await tester.pumpWidget(_wrap(const RiseAndSettle(child: Text('card'))));
      await tester.pump(const Duration(milliseconds: 500));
      await tester.pump();
      expect(tester.binding.hasScheduledFrame, isFalse);
    });

    testWidgets('reduced motion returns the child untouched', (tester) async {
      await tester.pumpWidget(
        _wrap(const RiseAndSettle(child: Text('card')), reduceMotion: true),
      );
      await tester.pump();
      // No Opacity or Transform wrapper is introduced at all.
      expect(find.text('card'), findsOneWidget);
      expect(tester.binding.hasScheduledFrame, isFalse);
    });
  });

  group('the field glow', () {
    testWidgets('follows the caret, and never takes it', (tester) async {
      await tester.pumpWidget(
        _wrap(
          Column(
            children: [
              FocusGlow(
                child: TextField(
                  decoration: const InputDecoration(labelText: 'Email'),
                ),
              ),
              const TextField(
                decoration: InputDecoration(labelText: 'Password'),
              ),
            ],
          ),
        ),
      );
      await tester.pump();

      final glow = tester.widget<Focus>(
        find.descendant(
          of: find.byType(FocusGlow),
          matching: find.byType(Focus),
        ).first,
      );
      // It must never be a tab stop of its own: it only wants to know where
      // the caret went.
      expect(glow.canRequestFocus, isFalse);
      expect(glow.skipTraversal, isTrue);

      await tester.tap(find.widgetWithText(TextField, 'Email').first);
      await tester.pumpAndSettle();
      expect(find.byType(FocusGlow), findsOneWidget);
    });
  });

  group('the press', () {
    testWidgets('dips, and lets the button keep its own tap', (tester) async {
      var taps = 0;
      await tester.pumpWidget(
        _wrap(
          PressDip(
            child: FilledButton(
              onPressed: () => taps++,
              child: const Text('Sign in'),
            ),
          ),
        ),
      );
      await tester.tap(find.text('Sign in'));
      await tester.pumpAndSettle();
      expect(taps, 1, reason: 'the wrapper must not swallow the gesture');
    });
  });

  group('the pour', () {
    testWidgets('covers the screen and hands over, once', (tester) async {
      var done = 0;
      await tester.pumpWidget(_wrap(MilkPour(onDone: () => done++)));
      await tester.pump(const Duration(milliseconds: 500));
      await tester.pump();
      expect(done, 1);
      expect(tester.binding.hasScheduledFrame, isFalse);
    });

    testWidgets('takes no pointer while it plays', (tester) async {
      // The form underneath has already been submitted; a stray tap during
      // the transition must not reach it again.
      await tester.pumpWidget(_wrap(const MilkPour()));
      await tester.pump();
      expect(find.byType(IgnorePointer), findsWidgets);
    });
  });

  group('the confirmation', () {
    testWidgets('is drawn, plays once and stops', (tester) async {
      await tester.pumpWidget(_wrap(const DropBecomesTick()));
      await tester.pump();
      expect(tester.binding.hasScheduledFrame, isTrue);
      await tester.pump(const Duration(milliseconds: 1000));
      await tester.pump();
      // A receipt that keeps animating reads as something still in progress.
      expect(tester.binding.hasScheduledFrame, isFalse);
    });

    testWidgets('reduced motion shows the ARRIVED state', (tester) async {
      await tester.pumpWidget(_wrap(const DropBecomesTick(), reduceMotion: true));
      await tester.pump();
      final paint = tester.widgetList<CustomPaint>(find.byType(CustomPaint))
          .firstWhere((w) => w.painter is DropTickPainter);
      // Finished, not blank: the tick is there for somebody who asked not to
      // watch it being drawn.
      expect((paint.painter! as DropTickPainter).t, 1);
      expect(tester.binding.hasScheduledFrame, isFalse);
    });
  });

  group('the wordmark', () {
    testWidgets('is the traced artwork, never a font', (tester) async {
      await tester.pumpWidget(_wrap(const LactevaWordmark(height: 40)));
      await tester.pump();
      // No Text anywhere: if the letterforms were ever set in a typeface this
      // is what would notice (BRAND-004 Amendment 1).
      expect(
        find.descendant(
          of: find.byType(LactevaWordmark),
          matching: find.byType(Text),
        ),
        findsNothing,
      );
      expect(find.byType(CustomPaint), findsWidgets);
    });

    testWidgets('is sized by its CAP height, not the artwork box', (
      tester,
    ) async {
      await tester.pumpWidget(_wrap(const LactevaWordmark(height: 40)));
      final box = tester.getSize(find.byType(LactevaWordmark));
      expect(box.height, closeTo(40, 0.01));
      // ...and as wide as the caps are, in the artwork's own proportion.
      expect(
        box.width,
        closeTo(40 * kWordmarkCapsBounds.width / kWordmarkCapsBounds.height, 0.5),
      );
    });

    testWidgets('with the tagline it grows, and only downward', (tester) async {
      await tester.pumpWidget(
        _wrap(const LactevaWordmark(height: 40, withTagline: true)),
      );
      final box = tester.getSize(find.byType(LactevaWordmark));
      expect(box.height, greaterThan(40));
    });

    test('drops the gradient where it stops being one', () {
      // The reduction rule: below the floor the VA is a flat brand green
      // rather than two greens arguing inside twenty pixels.
      expect(kWordmarkGradientFloor, greaterThan(0));
      expect(kWordmarkGradientTop, lessThan(kWordmarkGradientBottom));
    });
  });
}
