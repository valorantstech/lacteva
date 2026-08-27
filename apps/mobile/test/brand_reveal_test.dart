/// The reveal, and the promise it must not break (LACTEVA-BRAND-003).
///
/// A brand animation over a sign-in screen is the easiest place in a product
/// to do harm: it is the first thing a person meets and the last thing they
/// want when they came to type a password. So the tests here are mostly about
/// what it must NOT do — hold up the form, play twice, or run for somebody who
/// asked for no animation — and only then about the three beats.
///
/// The input-readiness test is the WO-17 discipline restated: it pumps one
/// frame, proves the reveal is on screen, and types into the email field
/// THROUGH it.
library;

import 'dart:io';

import 'package:flutter/material.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:lacteva_mobile/src/brand/mark.dart';
import 'package:lacteva_mobile/src/brand/reveal.dart';
import 'package:lacteva_mobile/src/centers.dart';
import 'package:lacteva_mobile/src/offline/offline_client.dart';
import 'package:lacteva_mobile/src/offline/queue.dart';
import 'package:lacteva_mobile/src/offline/store.dart';
import 'package:lacteva_mobile/src/theme.dart';

OfflineApiClient _client() => OfflineApiClient(
  queue: SyncQueue(MemoryOfflineStore()),
  deviceId: 'test-device',
);

Future<void> _pumpLogin(
  WidgetTester tester, {
  required RevealGate gate,
  String today = '2026-08-27',
  bool reducedMotion = false,
}) async {
  await tester.pumpWidget(
    MaterialApp(
      theme: lactevaTheme(),
      home: MediaQuery(
        data: MediaQueryData(disableAnimations: reducedMotion),
        child: LoginScreen(client: _client(), gate: gate, today: today),
      ),
    ),
  );
  // One frame to build, one for the gate's future to resolve. NEVER
  // pumpAndSettle before the reveal has been observed — settling would run it
  // to its end and prove nothing about what was on screen during it.
  await tester.pump();
  await tester.pump();
}

/// The reveal's own layer, by the gradient ground only it draws.
Finder _reveal() => find.byWidgetPredicate(
  (w) =>
      w is DecoratedBox &&
      (w.decoration as BoxDecoration?)?.gradient != null &&
      ((w.decoration as BoxDecoration).gradient as LinearGradient?)
              ?.colors
              .first ==
          LactevaColors.dairy,
);

void main() {
  group('the gate', () {
    test('plays once a day and not twice', () async {
      final gate = MemoryRevealGate();
      expect(await gate.claim('2026-08-27'), isTrue);
      expect(await gate.claim('2026-08-27'), isFalse);
      expect(await gate.claim('2026-08-27'), isFalse);
      // A new day is a new welcome.
      expect(await gate.claim('2026-08-28'), isTrue);
    });

    test('a file remembers across a restart, and forgets nothing else',
        () async {
      final dir = await Directory.systemTemp.createTemp('lacteva-reveal');
      addTearDown(() => dir.delete(recursive: true));
      final path = '${dir.path}/reveal.json';

      // Two gates over one file is exactly what a restart looks like.
      expect(await FileRevealGate(path).claim('2026-08-27'), isTrue);
      expect(await FileRevealGate(path).claim('2026-08-27'), isFalse);
      expect(await FileRevealGate(path).claim('2026-08-28'), isTrue);
    });

    test('a corrupt gate plays rather than refusing to come up', () async {
      // The failure mode of a decoration must never be a screen that will not
      // open.
      final dir = await Directory.systemTemp.createTemp('lacteva-reveal');
      addTearDown(() => dir.delete(recursive: true));
      final path = '${dir.path}/reveal.json';
      await File(path).writeAsString('not json at all');
      expect(await FileRevealGate(path).claim('2026-08-27'), isTrue);
    });

    test('the day it compares against is the handset\'s', () {
      // A courtesy, not a business fact — see the note in `reveal.dart`.
      expect(handsetDay(DateTime(2026, 8, 27, 5, 12)), '2026-08-27');
      expect(handsetDay(DateTime(2026, 1, 3, 23, 59)), '2026-01-03');
    });
  });

  group('the three beats', () {
    testWidgets('plays on the first launch of the day', (tester) async {
      await _pumpLogin(tester, gate: MemoryRevealGate());
      expect(_reveal(), findsOneWidget);
      expect(find.text('Lacteva'), findsWidgets);
      expect(find.text('EVERY DROP, ACCOUNTED FOR'), findsOneWidget);

      // It ends on its own and takes its layer with it. Pumped a little past
      // 1.4s because the controller starts on the frame AFTER the gate
      // answers, so the wall clock and the animation clock differ by one.
      await tester.pump(RevealBeats.total + const Duration(milliseconds: 100));
      await tester.pump();
      expect(_reveal(), findsNothing);
      expect(tester.binding.hasScheduledFrame, isFalse);
    });

    testWidgets('does not play again the same day', (tester) async {
      final gate = MemoryRevealGate('2026-08-27');
      await _pumpLogin(tester, gate: gate);
      expect(_reveal(), findsNothing);
      // And the screen is otherwise exactly itself.
      expect(find.byType(LactevaMark), findsOneWidget);
      expect(find.byType(TextFormField), findsNWidgets(2));
    });

    test('the beats are the ones the board specifies', () {
      expect(RevealBeats.drop.inMilliseconds, 420);
      expect(RevealBeats.ripple.inMilliseconds, 600);
      expect(RevealBeats.word.inMilliseconds, 380);
      expect(RevealBeats.wordRise, 4.0);
      expect(
        RevealBeats.drop + RevealBeats.ripple + RevealBeats.word,
        RevealBeats.total,
      );
    });
  });

  group('it never stands in front of the form', () {
    testWidgets('the fields are live and typeable THROUGH the reveal', (
      tester,
    ) async {
      // The WO-17 discipline: built and armed on the first frame. The reveal
      // is on screen for every line of this test.
      await _pumpLogin(tester, gate: MemoryRevealGate());
      expect(_reveal(), findsOneWidget);

      final email = find.byType(TextFormField).first;
      expect(email, findsOneWidget);
      await tester.enterText(email, 'operator@dairy.example');
      await tester.pump();
      expect(find.text('operator@dairy.example'), findsOneWidget);

      // Still playing — the typing did not depend on it being gone.
      expect(_reveal(), findsOneWidget);
    });

    testWidgets('a tap anywhere ends it at once', (tester) async {
      await _pumpLogin(tester, gate: MemoryRevealGate());
      expect(_reveal(), findsOneWidget);

      await tester.tapAt(const Offset(200, 90));
      await tester.pump();
      expect(_reveal(), findsNothing);
      // And nothing was left running behind it.
      expect(tester.binding.hasScheduledFrame, isFalse);
    });

    testWidgets('the tap that dismisses it also reaches what it was aimed at', (
      tester,
    ) async {
      // The whole point of a translucent listener over pointer-ignoring
      // visuals: a person aiming at the email field gets the field, not a
      // wasted tap on a barrier.
      await _pumpLogin(tester, gate: MemoryRevealGate());
      expect(_reveal(), findsOneWidget);

      await tester.tap(find.byType(TextFormField).first, warnIfMissed: false);
      await tester.pump();
      expect(_reveal(), findsNothing);
      // The FIELD, named — not `primaryFocus`, which is the root scope and
      // reports focus whether or not the tap ever arrived.
      final email = tester.widget<EditableText>(
        find.byType(EditableText).first,
      );
      expect(
        email.focusNode.hasFocus,
        isTrue,
        reason: 'the field the tap was aimed at took focus',
      );
    });
  });

  group('reduced motion', () {
    testWidgets('plays nothing, and shows the same static mark', (
      tester,
    ) async {
      await _pumpLogin(
        tester,
        gate: MemoryRevealGate(),
        reducedMotion: true,
      );
      expect(_reveal(), findsNothing);
      expect(tester.binding.hasScheduledFrame, isFalse);
      // The mark is still there — it lives in the screen, not in the overlay.
      expect(find.byType(LactevaMark), findsOneWidget);
      expect(find.byType(TextFormField), findsNWidgets(2));
    });

    testWidgets('does not spend the day on somebody who will not see it', (
      tester,
    ) async {
      // The gate is claimed only when the reveal will actually play. A person
      // with reduced motion who later turns it off should still get a welcome.
      final gate = MemoryRevealGate();
      await _pumpLogin(tester, gate: gate, reducedMotion: true);
      expect(gate.lastPlayed, isNull);
    });
  });

  group('the mark itself', () {
    testWidgets('draws, at whatever height it is given', (tester) async {
      await tester.pumpWidget(
        const MaterialApp(home: Center(child: LactevaMark(size: 120))),
      );
      final box = tester.getSize(find.byType(LactevaMark));
      expect(box.height, 120);
      // Taller than it is wide — a drop, not a disc.
      expect(box.width, lessThan(box.height));
      expect(tester.takeException(), isNull);
    });
  });
}
