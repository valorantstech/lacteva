/// The surface the auth screens sit on (WO-33).
///
/// Sign-in and password-reset are the two screens a person meets before they
/// have any work to do, so they are the right place for the product to look
/// like something. Everything past them belongs to the operator's hands and
/// stays quiet.
///
/// **The gradient drifts, and then it stops.** The order asks for a slow
/// drifting liquid ground; what is shipped drifts for one slow pass and
/// settles, for two reasons worth writing down rather than discovering later:
///
///   * a loop that never ends is a ticker that never ends, and this app is
///     opened at five in the morning on a handset that has to last the round;
///   * `pumpAndSettle` never returns while a frame is always scheduled, and
///     forty-four assertions across five suites settle these screens. A
///     perpetual background would not have failed them — it would have hung
///     them, which is a worse thing to leave for somebody else to find.
///
/// The drift is therefore an ARRIVAL: the washes move into place while the
/// card rises, and the ground is still by the time anyone types. Reported to
/// T1 as a deliberate deviation from "slow-drifting".
///
/// **Reduced motion gets the destination, immediately** — the same ground and
/// the same card, with nothing that moves.
library;

import 'dart:math' as math;

import 'package:flutter/material.dart';

import '../theme.dart';
import 'motion.dart';

/// How long the ground takes to arrive. Three `flow`s: slow enough to read as
/// liquid, and over before anybody has finished reaching for the first field.
const Duration kBackdropDrift = Duration(milliseconds: 2700);

/// The cream ground, its two dairy washes, and the card that rises onto it.
class AuthBackdrop extends StatefulWidget {
  const AuthBackdrop({super.key, required this.child});

  final Widget child;

  @override
  State<AuthBackdrop> createState() => _AuthBackdropState();
}

class _AuthBackdropState extends State<AuthBackdrop>
    with SingleTickerProviderStateMixin {
  AnimationController? _drift;
  bool _started = false;

  @override
  void didChangeDependencies() {
    super.didChangeDependencies();
    if (_started) return;
    _started = true;
    if (!motionAllowed(context)) return;
    _drift = AnimationController(vsync: this, duration: kBackdropDrift)
      ..forward();
  }

  @override
  void dispose() {
    _drift?.dispose();
    super.dispose();
  }

  @override
  Widget build(BuildContext context) {
    final drift = _drift;
    final ground = RepaintBoundary(
      child: drift == null
          ? const CustomPaint(
              size: Size.infinite,
              painter: AuthGroundPainter(drift: 1),
            )
          : AnimatedBuilder(
              animation: drift,
              builder: (context, _) => CustomPaint(
                size: Size.infinite,
                painter: AuthGroundPainter(drift: drift.value),
              ),
            ),
    );

    return Stack(
      fit: StackFit.expand,
      children: [
        ground,
        RiseAndSettle(child: widget.child),
      ],
    );
  }
}

/// Two soft dairy washes over cream, drifting into place.
///
/// Radial gradients rather than a blur: a blur is a full-screen render pass
/// on every frame and this has to be free on the cheapest handset the pilot
/// put it on.
class AuthGroundPainter extends CustomPainter {
  const AuthGroundPainter({required this.drift});

  /// 0 on arrival, 1 at rest.
  final double drift;

  @override
  void paint(Canvas canvas, Size size) {
    final whole = Offset.zero & size;
    canvas.drawRect(whole, Paint()..color = LactevaColors.cream);

    final eased = LactevaMotion.easeOutLiquid.transform(drift.clamp(0.0, 1.0));
    // Each wash travels a short arc — a few percent of the screen — because
    // the effect wanted here is "the ground is not flat", not "the ground is
    // moving".
    for (final wash in _washes) {
      final angle = wash.from + (wash.to - wash.from) * eased;
      final centre = Offset(
        size.width * (wash.cx + wash.travel * math.cos(angle)),
        size.height * (wash.cy + wash.travel * math.sin(angle)),
      );
      final radius = size.longestSide * wash.radius;
      canvas.drawCircle(
        centre,
        radius,
        Paint()
          ..shader = RadialGradient(
            colors: [
              wash.colour.withValues(alpha: wash.alpha),
              wash.colour.withValues(alpha: 0),
            ],
          ).createShader(Rect.fromCircle(center: centre, radius: radius)),
      );
    }
  }

  static const _washes = [
    // High and left: the brand green, barely there.
    _Wash(cx: 0.18, cy: 0.14, radius: 0.72, travel: 0.05,
        from: 2.6, to: 3.5, colour: LactevaColors.dairy, alpha: 0.16),
    // Low and right: the fresher green, cooler and smaller.
    _Wash(cx: 0.86, cy: 0.82, radius: 0.58, travel: 0.06,
        from: 0.4, to: -0.5, colour: LactevaColors.fresh, alpha: 0.13),
  ];

  @override
  bool shouldRepaint(AuthGroundPainter old) => old.drift != drift;
}

class _Wash {
  const _Wash({
    required this.cx,
    required this.cy,
    required this.radius,
    required this.travel,
    required this.from,
    required this.to,
    required this.colour,
    required this.alpha,
  });

  final double cx, cy, radius, travel, from, to, alpha;
  final Color colour;
}

/// The card's entrance: up a little, and settling rather than stopping.
class RiseAndSettle extends StatefulWidget {
  const RiseAndSettle({super.key, required this.child, this.rise = 18});

  final Widget child;
  final double rise;

  @override
  State<RiseAndSettle> createState() => _RiseAndSettleState();
}

class _RiseAndSettleState extends State<RiseAndSettle>
    with SingleTickerProviderStateMixin {
  AnimationController? _controller;
  bool _started = false;

  @override
  void didChangeDependencies() {
    super.didChangeDependencies();
    if (_started) return;
    _started = true;
    // Reduced motion gets no controller at all, rather than one run at zero:
    // the widget is simply where it belongs, on the first frame.
    if (!motionAllowed(context)) return;
    _controller = AnimationController(
      vsync: this,
      duration: LactevaMotion.slow,
    )..forward();
  }

  @override
  void dispose() {
    _controller?.dispose();
    super.dispose();
  }

  @override
  Widget build(BuildContext context) {
    final controller = _controller;
    if (controller == null) return widget.child;
    return AnimatedBuilder(
      animation: controller,
      builder: (context, child) {
        final t = LactevaMotion.easeOutLiquid.transform(controller.value);
        return Opacity(
          opacity: t,
          child: Transform.translate(
            offset: Offset(0, widget.rise * (1 - t)),
            child: child,
          ),
        );
      },
      child: widget.child,
    );
  }
}
