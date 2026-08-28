/// The cinematic entry (WO-33).
///
/// Two and a half seconds of milk, drawn — no video asset anywhere. A video
/// would add megabytes to the APK, decode on the launch path and pick exactly
/// one resolution to look right at; this is vector arithmetic on the GPU, so
/// it is sharp on a 720p handset and on a tablet, weighs nothing, and starts
/// on the first frame.
///
/// THE SEQUENCE
///
///   1 · deep ink opens;
///   2 · the dairy gradient RISES from the bottom the way a vessel fills,
///       with a real meniscus at its edge and a slow wave across it;
///   3 · the can DRAWS ITSELF IN — the outline strokes on, then the body
///       blooms into it;
///   4 · the drop falls, lands, and throws a ripple and a few splash
///       particles;
///   5 · the wordmark and the tagline settle up into place.
///
/// The subject is the CAN RECEIVING THE DROP. BRAND-003's reveal showed the
/// lit drop alone, which stopped being the mark when BRAND-004 made the can
/// the outer shape; the launcher, the website's nav and this now show one
/// thing (WO-31 accepted, ruling 4).
///
/// WHAT IT MAY NOT DO
///
/// **It may never cost anybody their work.** The screen underneath is built,
/// live and laid out from the first frame — the splash is a layer ON TOP of a
/// finished screen, never a gate in front of an unbuilt one — and the FIRST
/// tap anywhere takes it down. An operator who opened the app to record a
/// collection loses one tap, and never a second of waiting.
///
/// **It is opaque, so unlike BRAND-003's reveal it does not pass that first
/// tap through.** That is deliberate rather than a regression: a person
/// cannot aim at a field they cannot see, and forwarding the dismissing tap
/// to whatever happened to be underneath would focus something nobody chose.
///
/// **Reduced motion gets a 300ms crossfade** — the finished frame, faded in
/// and faded out, with nothing that moves. Not nothing at all: the brand
/// moment survives, the animation does not.
///
/// **It never fronts a capture resume.** The splash mounts once, around the
/// app's root, and the collection wizard is not below it — the ≤160ms
/// capture-path budget is untouched by anything in this file.
library;

import 'dart:async';
import 'dart:math' as math;

import 'package:flutter/material.dart';

import '../theme.dart';
import 'mark.g.dart';
import 'motion.dart';
import 'path_data.dart';

/// The sequence's beats, in milliseconds from the first frame.
///
/// They OVERLAP on purpose. Beats that begin only when the last one ends read
/// as a list of things happening; milk fills while the can is still arriving,
/// and the wordmark starts up before the ripple has finished.
abstract final class SplashBeats {
  /// The whole sequence.
  static const total = Duration(milliseconds: 2400);

  /// 1 · deep ink opens.
  static const inkFrom = 0, inkTo = 260;

  /// 2 · the gradient rises like a vessel filling.
  static const fillFrom = 160, fillTo = 1080;

  /// 3 · the can draws itself in, then blooms.
  static const strokeFrom = 820, strokeTo = 1440;
  static const bloomFrom = 1280, bloomTo = 1620;

  /// 4 · the drop falls, lands, ripples, splashes.
  static const dropFrom = 1420, dropTo = 1820;
  static const rippleFrom = 1780, rippleTo = 2220;
  static const splashFrom = 1780, splashTo = 2160;

  /// 5 · the wordmark and tagline settle.
  static const wordFrom = 1900, wordTo = 2340;

  /// What a person who asked for no animation gets instead.
  static const reduced = Duration(milliseconds: 300);

  /// How far the wordmark rises into place.
  static const wordRise = 10.0;

  /// How many droplets the landing throws. The board says a few; five reads
  /// as a splash and eleven reads as a firework.
  static const splashCount = 5;
}

/// Progress through a beat, 0 at [from] ms and 1 at [to] ms.
double splashBeat(double elapsedMs, int from, int to) {
  if (to <= from) return elapsedMs >= to ? 1 : 0;
  return ((elapsedMs - from) / (to - from)).clamp(0.0, 1.0);
}

/// Plays the entry over [child].
class LactevaSplash extends StatefulWidget {
  const LactevaSplash({super.key, required this.child, this.onGlass});

  /// The screen underneath — built, live and laid out from frame one.
  final Widget child;

  /// Completes when the first frame is actually ON THE GLASS.
  ///
  /// Defaults to the binding's own first-rasterized-frame signal, which is
  /// what a launcher waits for before it takes its window down. Injectable
  /// because that signal never completes under `TestWidgetsFlutterBinding` —
  /// there is no glass — so a test that wants to watch the sequence has to
  /// say when the curtain lifted.
  final Future<void>? onGlass;

  @override
  State<LactevaSplash> createState() => _LactevaSplashState();
}

class _LactevaSplashState extends State<LactevaSplash>
    with SingleTickerProviderStateMixin {
  AnimationController? _controller;
  bool _playing = true;
  bool _started = false;
  bool _armed = false;

  @override
  void didChangeDependencies() {
    super.didChangeDependencies();
    if (_started) return;
    _started = true;
    // Reduced motion is read here rather than in `initState` because the
    // MediaQuery it comes from is not available that early.
    final duration = motionAllowed(context)
        ? SplashBeats.total
        : SplashBeats.reduced;
    _controller = AnimationController(vsync: this, duration: duration)
      ..addStatusListener((status) {
        if (status == AnimationStatus.completed) _end();
      });

    // WO-35, found on glass: the controller is BUILT here and started
    // somewhere else entirely.
    //
    // `didChangeDependencies` runs while the tree is first built — at engine
    // boot, behind the OS launch window. Frames are produced throughout that
    // boot and an AnimationController advances on WALL CLOCK between frame
    // callbacks, so a three-second debug boot spent the whole 2.4-second
    // sequence before a single beat reached anybody. The handset showed the
    // launch window and then a settled sign-in; the phone was right and the
    // 392 green tests were measuring the wrong thing, because `pumpWidget`
    // has no boot gap.
    //
    // So the clock waits for the first frame that is actually on the glass.
    // Until then the controller sits at zero, which means the splash is
    // already painting BEAT ZERO while the curtain is still up: the launch
    // window hands over to the opening frame rather than to a flash of the
    // sign-in screen underneath.
    unawaited(_armWhenVisible());
  }

  Future<void> _armWhenVisible() async {
    await (widget.onGlass ??
        WidgetsBinding.instance.waitUntilFirstFrameRasterized);
    if (!mounted || _armed || !_playing) return;
    _armed = true;
    _controller?.forward();
  }

  /// Take the splash down.
  ///
  /// The controller is NOT disposed here. This can run from a status callback
  /// — from inside the controller's own tick — and tearing it down there is
  /// disposing something mid-frame. It is stopped instead, and `dispose()`
  /// owns its end.
  void _end() {
    if (!mounted || !_playing) return;
    _controller?.stop();
    setState(() => _playing = false);
  }

  @override
  void dispose() {
    _controller?.dispose();
    super.dispose();
  }

  @override
  Widget build(BuildContext context) {
    final controller = _controller;
    final reduced = !motionAllowed(context);
    return Stack(
      children: [
        widget.child,
        if (_playing && controller != null)
          Positioned.fill(
            child: Semantics(
              // A brand animation is not content. It is announced as a label
              // so a screen-reader user knows what the tap does, and nothing
              // underneath is described twice.
              label: 'Lacteva',
              button: true,
              child: GestureDetector(
                behavior: HitTestBehavior.opaque,
                onTap: _end,
                child: RepaintBoundary(
                  child: AnimatedBuilder(
                    animation: controller,
                    builder: (context, _) => CustomPaint(
                      size: Size.infinite,
                      painter: SplashPainter(
                        progress: controller.value,
                        reduced: reduced,
                      ),
                    ),
                  ),
                ),
              ),
            ),
          ),
      ],
    );
  }
}

/// The whole sequence, drawn.
///
/// One painter rather than a stack of animated widgets: every element shares
/// the same clock and the same canvas, the splash is a single layer to
/// composite, and the milk's surface — which several of the other elements sit
/// against — is computed once.
class SplashPainter extends CustomPainter {
  const SplashPainter({required this.progress, required this.reduced});

  /// 0 to 1 across the sequence.
  final double progress;

  /// Draw the finished frame and crossfade it, rather than playing anything.
  final bool reduced;

  static const _cream = Color(kLogoCream);
  static const _deep = Color(kLogoDeep);

  double get _elapsed => progress * SplashBeats.total.inMilliseconds;

  @override
  void paint(Canvas canvas, Size size) {
    if (reduced) {
      // A crossfade of the SAME final frame: up over the first third, held,
      // and away at the end. Nothing moves, and the brand moment still
      // happens for somebody who asked not to be moved.
      final fade = progress < 0.35
          ? progress / 0.35
          : progress > 0.8
              ? (1 - progress) / 0.2
              : 1.0;
      canvas.saveLayer(
        Offset.zero & size,
        // Only the ALPHA of this paint is read — `saveLayer` uses it as the
        // layer's opacity — so the channels are deliberately meaningless.
        Paint()..color = Color.fromRGBO(0, 0, 0, fade.clamp(0.0, 1.0)),
      );
      _paintGround(canvas, size, 1.0);
      _paintCan(canvas, size, stroke: 1.0, bloom: 1.0);
      _paintDrop(canvas, size, 1.0);
      _paintWord(canvas, size, 1.0);
      canvas.restore();
      return;
    }

    final t = _elapsed;
    _paintGround(canvas, size, splashBeat(t, SplashBeats.fillFrom, SplashBeats.fillTo));
    _paintCan(
      canvas,
      size,
      stroke: splashBeat(t, SplashBeats.strokeFrom, SplashBeats.strokeTo),
      bloom: splashBeat(t, SplashBeats.bloomFrom, SplashBeats.bloomTo),
    );
    _paintRipple(canvas, size, splashBeat(t, SplashBeats.rippleFrom, SplashBeats.rippleTo));
    _paintDrop(canvas, size, splashBeat(t, SplashBeats.dropFrom, SplashBeats.dropTo));
    _paintSplash(canvas, size, splashBeat(t, SplashBeats.splashFrom, SplashBeats.splashTo));
    _paintWord(canvas, size, splashBeat(t, SplashBeats.wordFrom, SplashBeats.wordTo));
  }

  // --- 1 and 2 · deep ink, and the milk that rises through it ---------------

  /// Where the can is drawn, and how big.
  Rect _canRect(Size size) {
    final height = size.shortestSide * 0.34;
    final width = height * (kCanBounds.width / kCanBounds.height);
    return Rect.fromCenter(
      center: Offset(size.width / 2, size.height * 0.42),
      width: width,
      height: height,
    );
  }

  void _paintGround(Canvas canvas, Size size, double fill) {
    final whole = Offset.zero & size;
    // The ink the sequence opens on.
    canvas.drawRect(whole, Paint()..color = LactevaColors.ink);
    if (fill <= 0) return;

    final eased = LactevaMotion.easeOutLiquid.transform(fill);
    // The surface line, and the wave riding on it. The wave FLATTENS as the
    // vessel fills — milk settles, and a surface still rippling when the
    // pour has stopped reads as a loop rather than as liquid.
    final surfaceY = size.height * (1 - eased);
    final amplitude = 10.0 * (1 - eased) + 1.5;
    final phase = fill * 3.2;

    final milk = Path()..moveTo(0, size.height);
    milk.lineTo(0, surfaceY);
    const steps = 48;
    for (var i = 0; i <= steps; i++) {
      final x = size.width * i / steps;
      final y = surfaceY +
          amplitude *
              // Two waves of different lengths, so the surface never looks
              // like a single sine.
              (0.65 * math.sin(phase + i / steps * 3.6) +
                  0.35 * math.sin(phase * 1.7 + i / steps * 6.1));
      milk.lineTo(x, y);
    }
    milk.lineTo(size.width, size.height);
    milk.close();

    canvas.save();
    canvas.clipPath(milk);
    canvas.drawRect(
      whole,
      Paint()..shader = deepBrandGradient().createShader(whole),
    );
    canvas.restore();

    // The MENISCUS: liquid climbs where it meets a wall, and the light
    // catches that edge. It is what makes this read as milk and not as a
    // progress bar.
    if (eased < 0.999) {
      final edge = Path()..moveTo(0, surfaceY);
      for (var i = 0; i <= steps; i++) {
        final x = size.width * i / steps;
        final y = surfaceY +
            amplitude *
                (0.65 * math.sin(phase + i / steps * 3.6) +
                    0.35 * math.sin(phase * 1.7 + i / steps * 6.1));
        edge.lineTo(x, y);
      }
      canvas.drawPath(
        edge,
        Paint()
          ..style = PaintingStyle.stroke
          ..strokeWidth = 2.0
          ..color = _cream.withValues(alpha: 0.34 * (1 - eased * 0.4)),
      );
    }
  }

  // --- 3 · the can draws itself in -----------------------------------------

  void _paintCan(Canvas canvas, Size size, {required double stroke, required double bloom}) {
    if (stroke <= 0) return;
    final rect = _canRect(size);
    final scale = rect.height / kCanBounds.height;
    final can = lactevaCanPath(scale);
    final bounds = can.getBounds();
    final shifted = can.shift(rect.topLeft - bounds.topLeft);

    // The BLOOM first, so the outline sits on top of its own fill rather
    // than being swallowed by it.
    if (bloom > 0) {
      final eased = LactevaMotion.easeOutLiquid.transform(bloom);
      canvas.drawPath(
        shifted,
        Paint()..color = _cream.withValues(alpha: eased),
      );
    }

    // The DRAW-IN: the outline is revealed along its own length, which is
    // what makes it look drawn rather than faded up.
    final eased = LactevaMotion.easeOutLiquid.transform(stroke);
    final drawn = Path();
    for (final metric in shifted.computeMetrics()) {
      drawn.addPath(metric.extractPath(0, metric.length * eased), Offset.zero);
    }
    canvas.drawPath(
      drawn,
      Paint()
        ..style = PaintingStyle.stroke
        ..strokeWidth = 2.4
        ..strokeCap = StrokeCap.round
        ..color = _cream.withValues(alpha: 0.85 * (1 - bloom * 0.55)),
    );
  }

  /// Where the drop lands: the mouth of the can's belly.
  Offset _impact(Size size) {
    final rect = _canRect(size);
    final scale = rect.height / kCanBounds.height;
    return Offset(
      rect.center.dx,
      rect.top + (kMarkBounds.top - kCanBounds.top + kMarkBounds.height * 0.55) * scale,
    );
  }

  // --- 4 · the drop falls, and lands ---------------------------------------

  void _paintDrop(Canvas canvas, Size size, double fall) {
    if (fall <= 0) return;
    final rect = _canRect(size);
    final scale = rect.height / kCanBounds.height;
    final drop = lactevaDropPath(scale);
    final bounds = drop.getBounds();
    final resting = Offset(
      rect.center.dx - bounds.width / 2,
      rect.top + (kMarkBounds.top - kCanBounds.top) * scale,
    );

    final eased = LactevaMotion.easeOutLiquid.transform(fall);
    // It comes in from ABOVE and settles rather than stopping. The sign
    // matters and is easy to get backwards: a positive y offset here would
    // have the drop rise out of the can it is supposed to be falling into.
    final travel = rect.height * 0.9 * (1 - eased);
    canvas.drawPath(
      drop.shift(resting - bounds.topLeft - Offset(0, travel)),
      Paint()..color = fall >= 1 ? _deep : _deep.withValues(alpha: 0.35 + 0.65 * eased),
    );
  }

  void _paintRipple(Canvas canvas, Size size, double ripple) {
    if (ripple <= 0) return;
    final centre = _impact(size);
    final reach = _canRect(size).width * 0.62;
    // Two rings, the second trailing, both fading as they widen.
    for (final delay in const [0.0, 0.22]) {
      final p = ((ripple - delay) / (1 - delay)).clamp(0.0, 1.0);
      if (p <= 0) continue;
      final eased = LactevaMotion.easeOutLiquid.transform(p);
      // The ring TRAVELS on the eased curve and FADES on the linear one.
      // Fading on the eased curve spends the whole fade in the first few
      // frames, so the ripple is over before the eye has found it.
      canvas.drawCircle(
        centre,
        reach * (0.25 + 0.75 * eased),
        Paint()
          ..style = PaintingStyle.stroke
          ..strokeWidth = 1.8 * (1 - p) + 0.4
          ..color = _cream.withValues(alpha: 0.55 * (1 - p)),
      );
    }
  }

  void _paintSplash(Canvas canvas, Size size, double splash) {
    if (splash <= 0 || splash >= 1) return;
    final rect = _canRect(size);
    // Droplets leave through the can's MOUTH and arc over it — which is both
    // what milk does and the only place they can be seen. Thrown from the
    // impact point they were cream drawn on the cream can body, and read as
    // nothing at all.
    final centre = Offset(rect.center.dx, rect.top);
    final reach = rect.width * 0.5;
    final eased = LactevaMotion.easeOutLiquid.transform(splash);
    for (var i = 0; i < SplashBeats.splashCount; i++) {
      // Fixed, not random: a splash that lands somewhere new on every launch
      // is a splash nobody can review, and a golden test cannot pin.
      final spread = (i - (SplashBeats.splashCount - 1) / 2) /
          ((SplashBeats.splashCount - 1) / 2);
      final dx = spread * reach * (0.55 + 0.45 * eased);
      // A parabola, so they rise and fall rather than sliding outward. It is
      // measured from the can's mouth, so they clear the lid before they
      // come back down.
      // The outer droplets carry less of the impact, so they do not reach as
      // high — without that they leave the mouth in a flat row, which reads
      // as five dots rather than as a splash.
      final arc = 1 - 0.5 * spread * spread;
      final rise =
          reach * 0.9 * arc * (1 - (2 * eased - 1) * (2 * eased - 1));
      final radius = (3.0 - 1.5 * splash) * (1 - 0.35 * spread.abs());
      if (radius <= 0) continue;
      // Same rule as the ripple: the droplet flies on the eased curve and
      // fades on the linear one, or it is invisible for most of its arc.
      canvas.drawCircle(
        Offset(centre.dx + dx, centre.dy - rise),
        radius,
        Paint()..color = _cream.withValues(alpha: (1 - splash) * 0.95),
      );
    }
  }

  // --- 5 · the wordmark settles --------------------------------------------

  void _paintWord(Canvas canvas, Size size, double word) {
    if (word <= 0) return;
    final eased = LactevaMotion.easeOutLiquid.transform(word);
    final rect = _canRect(size);

    // The owner's letterforms, TRACED — never set in a font (BRAND-004
    // Amendment 1). On this ground they take the one-colour derivation: the
    // same outlines, filled cream, because the artwork's navy cannot be read
    // on deep green.
    //
    // The whole artwork is drawn in ITS OWN coordinates under a single
    // scale, so the gap beneath the caps, the length of the two rules and
    // the tagline's tracking are the reference's own proportions rather than
    // numbers invented here.
    final artWidth = size.width * 0.74;
    final scale = artWidth / kWordmarkBounds.width;
    canvas.save();
    canvas.translate(
      (size.width - artWidth) / 2,
      rect.bottom +
          size.shortestSide * 0.07 +
          SplashBeats.wordRise * (1 - eased),
    );
    canvas.scale(scale, scale);

    final cream = Paint()..color = _cream.withValues(alpha: eased);
    canvas.drawPath(lactevaPathData(kWordmarkNavyData), cream);
    canvas.drawPath(lactevaPathData(kWordmarkGreenData), cream);
    canvas.drawPath(
      lactevaPathData(kWordmarkRuleData),
      Paint()..color = _cream.withValues(alpha: 0.55 * eased),
    );
    canvas.drawPath(
      lactevaPathData(kWordmarkTaglineData),
      Paint()..color = _cream.withValues(alpha: 0.8 * eased),
    );
    canvas.restore();
  }

  @override
  bool shouldRepaint(SplashPainter old) =>
      old.progress != progress || old.reduced != reduced;
}
