/// The small motions of the auth screens (WO-33).
///
/// Three of them, and each answers a question the person is actually asking:
/// which field am I in, did that button take my tap, and is anything
/// happening now that I have signed in.
///
/// Every one of them is removed entirely — not run at zero — when the OS asks
/// for reduced motion, which is the rule this app has held since
/// LACTEVA-MOBILE-008: a controller that exists and ticks to nowhere is still
/// a controller waking the device.
library;

import 'package:flutter/material.dart';

import '../theme.dart';
import 'mark.g.dart';
import 'motion.dart';

/// A soft brand glow under whichever field has the caret.
///
/// The Material underline already says which field is focused; on a 5 a.m.
/// handset held at arm's length, a two-pixel line is not much of an answer.
/// This puts a low, wide green light under the focused field so the eye finds
/// it without reading.
class FocusGlow extends StatefulWidget {
  const FocusGlow({super.key, required this.child});

  final Widget child;

  @override
  State<FocusGlow> createState() => _FocusGlowState();
}

class _FocusGlowState extends State<FocusGlow> {
  bool _has = false;

  @override
  Widget build(BuildContext context) {
    final animate = motionAllowed(context);
    return Focus(
      // It must never take the caret itself; it only wants to know where the
      // caret went. `hasFocus` on a Focus node covers its whole subtree.
      canRequestFocus: false,
      skipTraversal: true,
      onFocusChange: (has) {
        if (has != _has) setState(() => _has = has);
      },
      child: AnimatedContainer(
        duration: animate ? LactevaMotion.base : Duration.zero,
        curve: LactevaMotion.easeOutLiquid,
        decoration: BoxDecoration(
          borderRadius: BorderRadius.circular(12),
          boxShadow: _has
              ? [
                  BoxShadow(
                    color: LactevaColors.dairy.withValues(alpha: 0.16),
                    blurRadius: 18,
                    spreadRadius: -4,
                    offset: const Offset(0, 4),
                  ),
                ]
              : const [],
        ),
        child: widget.child,
      ),
    );
  }
}

/// A press that answers back.
///
/// Material's ink ripple is already under the finger; this adds the small
/// dip that makes a large button feel like a physical one. It is scale only —
/// no colour changes, because the semantic tokens say what a button MEANS and
/// a press is not a change of meaning.
class PressDip extends StatefulWidget {
  const PressDip({super.key, required this.child, this.enabled = true});

  final Widget child;
  final bool enabled;

  @override
  State<PressDip> createState() => _PressDipState();
}

class _PressDipState extends State<PressDip> {
  bool _down = false;

  void _set(bool down) {
    if (!widget.enabled || down == _down) return;
    setState(() => _down = down);
  }

  @override
  Widget build(BuildContext context) {
    final animate = motionAllowed(context);
    return Listener(
      // A listener, not a gesture detector: the button underneath keeps its
      // own tap, its own ripple and its own semantics, and this only watches.
      behavior: HitTestBehavior.deferToChild,
      onPointerDown: (_) => _set(true),
      onPointerUp: (_) => _set(false),
      onPointerCancel: (_) => _set(false),
      child: AnimatedScale(
        scale: _down && animate ? 0.975 : 1.0,
        duration: animate ? LactevaMotion.instant : Duration.zero,
        curve: LactevaMotion.easeStandard,
        child: widget.child,
      ),
    );
  }
}

/// The pour: milk fills the screen, and the next one is behind it.
///
/// Played once, on a successful sign-in, between the form and the persona
/// home. It is deliberately SHORT — this is the moment somebody has just
/// proved who they are and wants their work, and a transition they can feel
/// waiting through is a transition that has failed.
///
/// It does not gate the navigation on itself: the caller pours and pushes,
/// so a slow route build happens underneath the sheet rather than after it.
class MilkPour extends StatefulWidget {
  const MilkPour({super.key, this.onDone});

  /// Called once the screen is covered. Optional: the sign-in path pours and
  /// navigates at the same time, so the route is built underneath the sheet
  /// rather than after it, and there is nothing left for a callback to do.
  final VoidCallback? onDone;

  @override
  State<MilkPour> createState() => _MilkPourState();
}

class _MilkPourState extends State<MilkPour>
    with SingleTickerProviderStateMixin {
  late final AnimationController _controller = AnimationController(
    vsync: this,
    duration: LactevaMotion.slow,
  );
  bool _called = false;

  @override
  void initState() {
    super.initState();
    _controller.addListener(() {
      // Hand over as the sheet closes rather than when the curve ends: the
      // last tenth of an ease is invisible, and the person gets their screen
      // forty milliseconds sooner.
      if (!_called && _controller.value >= 0.9) {
        _called = true;
        widget.onDone?.call();
      }
    });
    _controller.forward();
  }

  @override
  void dispose() {
    _controller.dispose();
    super.dispose();
  }

  @override
  Widget build(BuildContext context) {
    return IgnorePointer(
      child: AnimatedBuilder(
        animation: _controller,
        builder: (context, _) => CustomPaint(
          size: Size.infinite,
          painter: _PourPainter(
            LactevaMotion.easeOutLiquid.transform(_controller.value),
          ),
        ),
      ),
    );
  }
}

class _PourPainter extends CustomPainter {
  const _PourPainter(this.t);

  final double t;

  @override
  void paint(Canvas canvas, Size size) {
    if (t <= 0) return;
    // A sheet coming down with a curved leading edge — milk poured, not a
    // rectangle wiped.
    final y = size.height * 1.12 * t;
    final belly = size.height * 0.06 * (1 - t);
    final path = Path()
      ..moveTo(0, 0)
      ..lineTo(size.width, 0)
      ..lineTo(size.width, y)
      ..quadraticBezierTo(size.width / 2, y + belly, 0, y)
      ..close();
    canvas.drawPath(path, Paint()..color = LactevaColors.cream);
  }

  @override
  bool shouldRepaint(_PourPainter old) => old.t != t;
}

/// The drop becomes a tick (WO-33).
///
/// Shown when the reset code has been sent. The product's own drop falls in,
/// spreads into a disc, and a tick strokes across it — so the confirmation is
/// made of the mark rather than of a stock check icon that could belong to
/// any application.
///
/// It says one thing and stops. There is no loop: this is a receipt, and a
/// receipt that keeps animating reads as something still in progress.
class DropBecomesTick extends StatefulWidget {
  const DropBecomesTick({super.key, this.size = 56});

  final double size;

  @override
  State<DropBecomesTick> createState() => _DropBecomesTickState();
}

class _DropBecomesTickState extends State<DropBecomesTick>
    with SingleTickerProviderStateMixin {
  AnimationController? _controller;
  bool _started = false;

  @override
  void didChangeDependencies() {
    super.didChangeDependencies();
    if (_started) return;
    _started = true;
    if (!motionAllowed(context)) return;
    _controller = AnimationController(
      vsync: this,
      duration: LactevaMotion.flow,
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
    return ExcludeSemantics(
      child: SizedBox.square(
        dimension: widget.size,
        child: controller == null
            // Reduced motion gets the ARRIVED state — the tick, finished —
            // rather than a blank square or a controller ticking to nowhere.
            ? const CustomPaint(painter: DropTickPainter(1))
            : AnimatedBuilder(
                animation: controller,
                builder: (context, _) =>
                    CustomPaint(painter: DropTickPainter(controller.value)),
              ),
      ),
    );
  }
}

/// Three overlapping beats: the drop falls, spreads, and is ticked.
class DropTickPainter extends CustomPainter {
  const DropTickPainter(this.t);

  final double t;

  @override
  void paint(Canvas canvas, Size size) {
    final centre = Offset(size.width / 2, size.height / 2);
    final radius = size.shortestSide / 2;

    final fall = ((t - 0.0) / 0.45).clamp(0.0, 1.0);
    final spread = ((t - 0.35) / 0.35).clamp(0.0, 1.0);
    final tick = ((t - 0.58) / 0.42).clamp(0.0, 1.0);

    // 1 · the drop arrives.
    if (fall > 0 && spread < 1) {
      final eased = LactevaMotion.easeOutLiquid.transform(fall);
      final drop = lactevaDropPath(size.shortestSide * 0.62 / kMarkBounds.height);
      final bounds = drop.getBounds();
      canvas.drawPath(
        drop.shift(
          Offset(
            centre.dx - bounds.center.dx,
            centre.dy - bounds.center.dy - radius * 1.4 * (1 - eased),
          ),
        ),
        Paint()..color = LactevaColors.dairy.withValues(alpha: 1 - spread),
      );
    }

    // 2 · it spreads into a disc.
    if (spread > 0) {
      final eased = LactevaMotion.easeOutLiquid.transform(spread);
      canvas.drawCircle(
        centre,
        radius * eased,
        Paint()..color = LactevaColors.dairy,
      );
    }

    // 3 · the tick strokes on, drawn rather than faded so it reads as a mark
    //     being made.
    if (tick > 0) {
      final eased = LactevaMotion.easeOutLiquid.transform(tick);
      final path = Path()
        ..moveTo(centre.dx - radius * 0.40, centre.dy + radius * 0.02)
        ..lineTo(centre.dx - radius * 0.10, centre.dy + radius * 0.32)
        ..lineTo(centre.dx + radius * 0.42, centre.dy - radius * 0.30);
      final drawn = Path();
      for (final metric in path.computeMetrics()) {
        drawn.addPath(metric.extractPath(0, metric.length * eased), Offset.zero);
      }
      canvas.drawPath(
        drawn,
        Paint()
          ..style = PaintingStyle.stroke
          ..strokeWidth = radius * 0.16
          ..strokeCap = StrokeCap.round
          ..strokeJoin = StrokeJoin.round
          ..color = LactevaColors.onBrand,
      );
    }
  }

  @override
  bool shouldRepaint(DropTickPainter old) => old.t != t;
}
