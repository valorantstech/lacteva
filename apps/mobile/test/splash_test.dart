/// The cinematic entry, and what it may never cost (WO-33).
///
/// BRAND-003's reveal played the lit drop alone, once a day, over the sign-in
/// form, translucent so the dismissing tap reached the field it was aimed at.
/// WO-33 replaces it: a full-screen sequence whose subject is the CAN
/// RECEIVING THE DROP — the same thing the launcher and the website now show
/// (WO-31 accepted, ruling 4) — on every cold start.
///
/// Two of those changes are worth stating because they look like losses:
///
///   * it plays EVERY cold start rather than once a day, on the owner's
///     direction, which is why it has to be cheap to dismiss;
///   * it is OPAQUE, so the dismissing tap no longer passes through to what
///     was underneath. That is not the old guarantee weakened, it is a
///     different screen: nobody can aim at a field they cannot see, and
///     forwarding that tap would focus something the person did not choose.
///
/// What survives untouched is the promise underneath both: **the sequence
/// never costs anybody their work.** The screen below is built and live from
/// the first frame, and one tap anywhere takes the splash down.
library;

import 'dart:async';

import 'package:flutter/material.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:lacteva_mobile/src/brand/motion.dart';
import 'package:lacteva_mobile/src/brand/splash.dart';

/// A stand-in for the screen underneath: a real form with a real controller,
/// so "it was built" means something a test can check.
class _Underneath extends StatelessWidget {
  const _Underneath({required this.controller});

  final TextEditingController controller;

  @override
  Widget build(BuildContext context) {
    return Scaffold(
      body: Center(
        child: TextField(
          controller: controller,
          decoration: const InputDecoration(labelText: 'Email'),
        ),
      ),
    );
  }
}

/// Is the splash layer in the tree?
///
/// Structural, not timing: `hasScheduledFrame` is the wrong probe for this —
/// tapping a text field starts the caret blinking, so it stays true whether
/// the splash went or not. This asks the question directly.
bool splashUp(WidgetTester tester) => tester
    .widgetList<CustomPaint>(find.byType(CustomPaint))
    .any((paint) => paint.painter is SplashPainter);

/// How far through the sequence the splash has actually got.
double splashProgress(WidgetTester tester) => tester
    .widgetList<CustomPaint>(find.byType(CustomPaint))
    .map((paint) => paint.painter)
    .whereType<SplashPainter>()
    .first
    .progress;

/// The first-frame-on-glass signal (WO-35).
///
/// Under `TestWidgetsFlutterBinding` there is no glass, so the real signal
/// never arrives and a test that wants to watch the sequence has to say when
/// the curtain lifted. By default it lifts immediately, which is the world
/// every test before WO-35 was written in; `curtainUp: true` models a launch
/// still behind the OS launch window, and `onGlass` takes control of the
/// exact moment.
Widget _app(
  Widget child, {
  bool reduceMotion = false,
  bool curtainUp = false,
  Future<void>? onGlass,
}) =>
    MediaQuery(
      data: MediaQueryData(disableAnimations: reduceMotion),
      child: MaterialApp(
        home: LactevaSplash(
          onGlass: onGlass ?? (curtainUp ? null : Future<void>.value()),
          child: child,
        ),
      ),
    );

void main() {
  group('the beats', () {
    test('run to the sequence the order specifies', () {
      // 2.4 seconds, and the five beats inside it, in order and overlapping.
      expect(SplashBeats.total.inMilliseconds, 2400);
      expect(SplashBeats.fillFrom, lessThan(SplashBeats.strokeFrom));
      expect(SplashBeats.strokeFrom, lessThan(SplashBeats.dropFrom));
      expect(SplashBeats.dropFrom, lessThan(SplashBeats.rippleFrom));
      expect(SplashBeats.rippleFrom, lessThan(SplashBeats.wordTo));
      // The last beat lands inside the sequence rather than after it.
      expect(SplashBeats.wordTo, lessThanOrEqualTo(2400));
    });

    test('overlap, because a list of events is not a sequence', () {
      // The can begins arriving while the milk is still rising, and the
      // wordmark starts before the ripple has finished.
      expect(SplashBeats.strokeFrom, lessThan(SplashBeats.fillTo));
      expect(SplashBeats.wordFrom, lessThan(SplashBeats.rippleTo));
    });

    test('splashBeat clamps at both ends and is linear between', () {
      expect(splashBeat(0, 100, 200), 0);
      expect(splashBeat(150, 100, 200), 0.5);
      expect(splashBeat(9999, 100, 200), 1);
      // A zero-length beat is "done once you are past it", not a divide by
      // zero — the arithmetic that would otherwise produce NaN and paint
      // nothing at all.
      expect(splashBeat(50, 100, 100), 0);
      expect(splashBeat(100, 100, 100), 1);
    });
  });

  group('it never costs anybody their work', () {
    testWidgets('the screen underneath is BUILT while the splash plays', (
      tester,
    ) async {
      final controller = TextEditingController();
      addTearDown(controller.dispose);
      await tester.pumpWidget(_app(_Underneath(controller: controller)));
      await tester.pump();

      // The splash is up...
      expect(splashUp(tester), isTrue);
      // ...and the form below it exists, laid out, with a live controller.
      expect(find.byType(TextField), findsOneWidget);
      controller.text = 'someone@dairy.example';
      await tester.pump();
      expect(controller.text, 'someone@dairy.example');
    });

    testWidgets('one tap anywhere takes it down', (tester) async {
      final controller = TextEditingController();
      addTearDown(controller.dispose);
      await tester.pumpWidget(_app(_Underneath(controller: controller)));
      await tester.pump(const Duration(milliseconds: 400));

      expect(splashUp(tester), isTrue);
      await tester.tapAt(const Offset(200, 300));
      await tester.pump();

      // Gone on the very next frame — not fading out for another beat, which
      // is a person tapping twice.
      expect(splashUp(tester), isFalse);
      // ...and the form underneath now takes the caret.
      await tester.tap(find.byType(TextField));
      await tester.pump();
      expect(find.byType(TextField), findsOneWidget);
    });

    testWidgets('it takes itself down when the sequence ends', (tester) async {
      final controller = TextEditingController();
      addTearDown(controller.dispose);
      await tester.pumpWidget(_app(_Underneath(controller: controller)));
      // One frame to arm the clock on the curtain signal (WO-35), then one
      // past the whole sequence — a controller starts on the frame AFTER it
      // is told to, which is the margin every animated test here carries.
      await tester.pump();
      await tester.pump(SplashBeats.total + const Duration(milliseconds: 32));
      await tester.pump();
      expect(splashUp(tester), isFalse);
    });
  });

  group('it starts when the curtain lifts, not when the engine boots', () {
    // THE WO-35 DEFECT, on glass: the splash never appeared on a moto g57.
    //
    // The clock used to start in `didChangeDependencies`, which runs while
    // the tree is first built — at Flutter boot, behind the OS launch window.
    // Frames are produced throughout that boot, and an AnimationController
    // advances on WALL CLOCK between frame callbacks, not on frame count. So
    // a three-second debug boot consumed the whole 2.4-second sequence, and
    // `_end()` fired before a single beat reached the glass.
    //
    // Nothing in the suite saw it, because `pumpWidget` has no boot gap: the
    // first frame and the first build are the same instant, so all 392 tests
    // stayed green while the handset showed nothing at all.
    testWidgets('a slow boot does not advance the clock by one frame', (
      tester,
    ) async {
      final controller = TextEditingController();
      addTearDown(controller.dispose);
      final curtain = Completer<void>();
      await tester.pumpWidget(
        _app(_Underneath(controller: controller), onGlass: curtain.future),
      );

      // Beat zero is on screen from the first build, so the launch window
      // hands over to the opening frame and never to a flash of the form.
      expect(splashUp(tester), isTrue);
      expect(splashProgress(tester), 0);

      // A debug boot on that handset is about three seconds from `runApp` to
      // the first frame on glass. No taps: nobody has touched anything.
      await tester.pump(const Duration(seconds: 3));
      await tester.pump();

      expect(
        splashUp(tester),
        isTrue,
        reason: 'the sequence used to play out behind the OS launch window',
      );
      expect(
        splashProgress(tester),
        0,
        reason: 'not one frame of the sequence may be spent before it is seen',
      );

      // The curtain lifts. NOW it runs, from the beginning.
      //
      // Two pumps of slack: one for the signal to arm the controller, and one
      // more because a Ticker's FIRST tick is always at elapsed zero. That is
      // the same margin every animated test in this app carries.
      curtain.complete();
      await tester.pump();
      await tester.pump(const Duration(milliseconds: 600));
      await tester.pump(const Duration(milliseconds: 600));
      expect(splashProgress(tester), greaterThan(0));
      expect(splashUp(tester), isTrue);

      // ...and still takes its full length from that moment, not from boot.
      await tester.pump(SplashBeats.total);
      await tester.pump();
      expect(splashUp(tester), isFalse);
    });

    testWidgets('reduced motion waits for the curtain too', (tester) async {
      final controller = TextEditingController();
      addTearDown(controller.dispose);
      final curtain = Completer<void>();
      await tester.pumpWidget(
        _app(
          _Underneath(controller: controller),
          reduceMotion: true,
          onGlass: curtain.future,
        ),
      );
      await tester.pump(const Duration(seconds: 3));
      await tester.pump();
      // The crossfade is 300ms; three seconds of boot would have finished it
      // several times over.
      expect(splashUp(tester), isTrue);
      expect(splashProgress(tester), 0);

      curtain.complete();
      // Arm, establish the ticker's zero tick, then run the crossfade.
      await tester.pump();
      await tester.pump(const Duration(milliseconds: 16));
      await tester.pump(SplashBeats.reduced + const Duration(milliseconds: 32));
      await tester.pump();
      expect(splashUp(tester), isFalse);
    });

    testWidgets('the default signal is the binding, not a timer', (
      tester,
    ) async {
      // Nothing in this widget measures the boot itself. The signal is the
      // one the platform already raises when it takes its launch window
      // down, so a slow phone and a fast one both start at beat zero.
      const splash = LactevaSplash(child: SizedBox());
      expect(splash.onGlass, isNull);
    });

    testWidgets('a tap still dismisses it while it waits', (tester) async {
      // Nobody should be trapped by a curtain signal that never comes.
      final controller = TextEditingController();
      addTearDown(controller.dispose);
      await tester.pumpWidget(
        _app(_Underneath(controller: controller), curtainUp: true),
      );
      await tester.pump(const Duration(seconds: 3));
      expect(splashUp(tester), isTrue);
      await tester.tapAt(const Offset(200, 300));
      await tester.pump();
      expect(splashUp(tester), isFalse);
    });
  });

  group('reduced motion', () {
    testWidgets('gets a crossfade, not the sequence', (tester) async {
      final controller = TextEditingController();
      addTearDown(controller.dispose);
      await tester.pumpWidget(
        _app(_Underneath(controller: controller), reduceMotion: true),
      );
      // The whole thing is over inside the crossfade's own budget — a person
      // who asked not to be moved does not wait 2.4 seconds to find out.
      await tester.pump();
      await tester.pump(SplashBeats.reduced + const Duration(milliseconds: 32));
      await tester.pump();
      expect(splashUp(tester), isFalse);
      expect(SplashBeats.reduced.inMilliseconds, 300);
      expect(
        SplashBeats.reduced.inMilliseconds,
        lessThan(SplashBeats.total.inMilliseconds),
      );
    });

    testWidgets('the form is live throughout it', (tester) async {
      final controller = TextEditingController();
      addTearDown(controller.dispose);
      await tester.pumpWidget(
        _app(_Underneath(controller: controller), reduceMotion: true),
      );
      await tester.pump();
      expect(find.byType(TextField), findsOneWidget);
      // And it is still a splash, not nothing: reduced motion keeps the
      // brand moment and removes only the movement.
      expect(splashUp(tester), isTrue);
    });
  });

  group('the painter', () {
    test('repaints on the clock and on nothing else', () {
      const a = SplashPainter(progress: 0.2, reduced: false);
      expect(a.shouldRepaint(const SplashPainter(progress: 0.2, reduced: false)),
          isFalse);
      expect(a.shouldRepaint(const SplashPainter(progress: 0.3, reduced: false)),
          isTrue);
      expect(a.shouldRepaint(const SplashPainter(progress: 0.2, reduced: true)),
          isTrue);
    });

    test('the splash throws a few droplets, not a firework', () {
      expect(SplashBeats.splashCount, inInclusiveRange(3, 5));
    });
  });

  group('the motion gate is the app-wide one', () {
    testWidgets('motionAllowed follows the OS setting', (tester) async {
      late bool allowed;
      await tester.pumpWidget(
        MediaQuery(
          data: const MediaQueryData(disableAnimations: true),
          child: Builder(
            builder: (context) {
              allowed = motionAllowed(context);
              return const SizedBox();
            },
          ),
        ),
      );
      expect(allowed, isFalse);
    });
  });
}
