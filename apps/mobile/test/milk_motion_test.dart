/// The five moments (LACTEVA-MOBILE-008; board: MotionStoryboard).
///
/// One test per panel, plus the gate they all share. The sixth panel — the
/// capture path carrying no animation at all — has its own file, because it is
/// a guard over production screens rather than a property of these widgets.
///
/// What every one of these has in common, and what is really being pinned:
/// reduced motion builds NO controller, rather than running one at zero. A
/// person who asked not to have animation should not be paying a frame budget
/// for one they cannot see.
library;

import 'package:flutter/material.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:lacteva_mobile/src/brand/motion.dart';
import 'package:lacteva_mobile/src/theme.dart';

/// A controller starts on the frame AFTER its widget builds, so the wall
/// clock and the animation clock differ by one. Every "and then it is over"
/// assertion pumps a little past the beat rather than exactly to it.
const _margin = Duration(milliseconds: 50);

Future<void> _pump(
  WidgetTester tester,
  Widget child, {
  bool reducedMotion = false,
}) async {
  await tester.pumpWidget(
    MaterialApp(
      theme: lactevaTheme(),
      // COPIED from the ambient data, never constructed fresh: a bare
      // `MediaQueryData()` has `size: Size.zero`, and a list laid out in a
      // zero-height viewport relayouts forever — which reads exactly like an
      // animation that never stops.
      home: Builder(
        builder: (context) => MediaQuery(
          data: MediaQuery.of(
            context,
          ).copyWith(disableAnimations: reducedMotion),
          child: Scaffold(body: child),
        ),
      ),
    ),
  );
  await tester.pump();
}

void main() {
  group('the gate every moment shares', () {
    testWidgets('answers the platform switch, not a preference of our own', (
      tester,
    ) async {
      late bool allowed;
      await _pump(
        tester,
        Builder(
          builder: (context) {
            allowed = motionAllowed(context);
            return const SizedBox.shrink();
          },
        ),
      );
      expect(allowed, isTrue);

      await _pump(
        tester,
        Builder(
          builder: (context) {
            allowed = motionAllowed(context);
            return const SizedBox.shrink();
          },
        ),
        reducedMotion: true,
      );
      expect(allowed, isFalse);
    });
  });

  group('panel 2 · the parchi moment', () {
    testWidgets('runs 600ms, once, and then the queue moves on', (
      tester,
    ) async {
      await _pump(tester, const ParchiMint(child: Text('SLP-2026-000481')));
      // The parchi is on screen from the first frame — the celebration is
      // over it, never instead of it.
      expect(find.text('SLP-2026-000481'), findsOneWidget);
      expect(tester.binding.hasScheduledFrame, isTrue);

      await tester.pump(MilkMoments.parchi + _margin);
      await tester.pump();
      expect(tester.binding.hasScheduledFrame, isFalse);
      expect(find.text('SLP-2026-000481'), findsOneWidget);
    });

    testWidgets('reduced motion shows the parchi and nothing else', (
      tester,
    ) async {
      await _pump(
        tester,
        const ParchiMint(child: Text('SLP-2026-000481')),
        reducedMotion: true,
      );
      expect(find.text('SLP-2026-000481'), findsOneWidget);
      expect(tester.binding.hasScheduledFrame, isFalse);
    });

    test('the beat is the board\'s', () {
      expect(MilkMoments.parchi.inMilliseconds, 600);
    });
  });

  group('panel 3 · sync droplets', () {
    testWidgets('travel only while something is actually being sent', (
      tester,
    ) async {
      await _pump(
        tester,
        const SyncDroplets(sending: true, pending: 3, label: 'Sending 3…'),
      );
      expect(tester.binding.hasScheduledFrame, isTrue);
      expect(find.text('Sending 3…'), findsOneWidget);
    });

    testWidgets('stop when the queue is empty, whatever "sending" says', (
      tester,
    ) async {
      // An empty queue has nothing to send. A run that is technically in
      // flight over nothing must not show milk leaving the phone.
      await _pump(
        tester,
        const SyncDroplets(sending: true, pending: 0, label: 'All sent'),
      );
      expect(tester.binding.hasScheduledFrame, isFalse);
      expect(find.text('All sent'), findsOneWidget);
    });

    testWidgets('stop when nothing is in flight', (tester) async {
      await _pump(
        tester,
        const SyncDroplets(sending: false, pending: 3, label: '3 waiting'),
      );
      expect(tester.binding.hasScheduledFrame, isFalse);
      expect(find.text('3 waiting'), findsOneWidget);
    });

    testWidgets('the word and the count are there in every state', (
      tester,
    ) async {
      // Movement is not a signal a person who cannot see it can act on, and a
      // count is the thing somebody repeats to the dairy.
      for (final (sending, pending, label) in [
        (true, 3, 'Sending 3 collections…'),
        (false, 3, '3 waiting to send'),
        (false, 0, 'All sent'),
      ]) {
        await _pump(
          tester,
          SyncDroplets(sending: sending, pending: pending, label: label),
        );
        expect(find.text(label), findsOneWidget, reason: label);
      }
    });

    testWidgets('reduced motion keeps the words and drops the droplets', (
      tester,
    ) async {
      await _pump(
        tester,
        const SyncDroplets(sending: true, pending: 3, label: 'Sending 3…'),
        reducedMotion: true,
      );
      expect(tester.binding.hasScheduledFrame, isFalse);
      expect(find.text('Sending 3…'), findsOneWidget);
    });
  });

  group('panel 4 · lists settle in', () {
    Widget rows(int count) => SettleInScope(
      child: Column(
        children: [
          for (var i = 0; i < count; i++)
            SettleIn(index: i, child: Text('row $i')),
        ],
      ),
    );

    testWidgets('rows rise 4px over 240ms, staggered by 40ms', (tester) async {
      await _pump(tester, rows(3));
      expect(tester.binding.hasScheduledFrame, isTrue);
      // Every row is PRESENT from the first frame — settling in is how they
      // arrive, not whether they do.
      expect(find.text('row 0'), findsOneWidget);
      expect(find.text('row 2'), findsOneWidget);

      // Settled rather than pumped by hand: the stagger means several finite
      // animations overlap, and counting frames for all of them is a way to
      // be wrong. `pumpAndSettle` returning at all is itself the proof they
      // are finite.
      await tester.pumpAndSettle();
      expect(tester.binding.hasScheduledFrame, isFalse);
    });

    testWidgets('a row built after the first paint simply appears', (
      tester,
    ) async {
      // The whole point of the scope: this is what "never on refresh or
      // pagination" means. Without it, every appended page would animate and
      // paginating would look like the screen reloading.
      await _pump(tester, rows(2));
      await tester.pumpAndSettle();
      // The scope closes on its OWN clock, not when the last row happens to
      // finish: a list counts as first-painted for a fixed window, so a slow
      // page that arrives 300ms in is still part of the first paint. Settling
      // stops as soon as the rows are done, which is before that window ends.
      await tester.pump(
        LactevaMotion.base + MilkMoments.stagger * MilkMoments.maxStaggered,
      );
      await tester.pumpAndSettle();
      expect(tester.binding.hasScheduledFrame, isFalse);

      // The next page arrives — through the SAME tree, which is what a real
      // list does. Rebuilding a different shape would give the scope a fresh
      // State and prove nothing.
      await _pump(tester, rows(6));
      expect(
        tester.binding.hasScheduledFrame,
        isFalse,
        reason: 'appended rows must not re-animate the list',
      );
      expect(find.text('row 5'), findsOneWidget);
    });

    testWidgets('a SettleIn outside a scope is inert, not surprising', (
      tester,
    ) async {
      await _pump(tester, const SettleIn(index: 0, child: Text('stray')));
      expect(tester.binding.hasScheduledFrame, isFalse);
      expect(find.text('stray'), findsOneWidget);
    });

    testWidgets('reduced motion shows every row at once', (tester) async {
      await _pump(tester, rows(4), reducedMotion: true);
      expect(tester.binding.hasScheduledFrame, isFalse);
      for (var i = 0; i < 4; i++) {
        expect(find.text('row $i'), findsOneWidget);
      }
    });

    test('the figures are the board\'s', () {
      expect(LactevaMotion.base.inMilliseconds, 240);
      expect(MilkMoments.stagger.inMilliseconds, 40);
      expect(MilkMoments.rise, 4.0);
    });
  });

  group('panel 5 · success ripples once', () {
    testWidgets('one ring, 420ms, and it never comes back', (tester) async {
      await _pump(tester, const SuccessRipple(label: 'Saved'));
      expect(tester.binding.hasScheduledFrame, isTrue);

      await tester.pump(LactevaMotion.slow + _margin);
      await tester.pump();
      // A confirmation that loops stops being a confirmation and becomes a
      // state.
      expect(tester.binding.hasScheduledFrame, isFalse);
      // The tick stays; only the ring left.
      expect(find.byIcon(Icons.check), findsOneWidget);
    });

    testWidgets('says what succeeded, for somebody who cannot see the ring', (
      tester,
    ) async {
      await _pump(tester, const SuccessRipple(label: 'Transaction COMPLETED'));
      final labelled = tester
          .widgetList<Semantics>(find.byType(Semantics))
          .where((s) => s.properties.label == 'Transaction COMPLETED');
      expect(labelled, isNotEmpty);
    });

    testWidgets('reduced motion shows the tick, still', (tester) async {
      await _pump(tester, const SuccessRipple(label: 'Saved'), reducedMotion: true);
      expect(tester.binding.hasScheduledFrame, isFalse);
      expect(find.byIcon(Icons.check), findsOneWidget);
    });

    test('the beat is the token', () {
      expect(LactevaMotion.slow.inMilliseconds, 420);
    });
  });

  group('no new curves', () {
    test('every moment eases on the one Lacteva curve', () {
      // The motion language is recognisable because it is ONE curve. This
      // asserts the token still exists and is the liquid one; the widgets
      // reference it by name and nothing here invents a Cubic.
      expect(LactevaMotion.easeOutLiquid, const Cubic(0.22, 1, 0.36, 1));
    });
  });
}
