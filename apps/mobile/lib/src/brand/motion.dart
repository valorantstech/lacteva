/// The milk motion language, applied (LACTEVA-MOBILE-008; board:
/// MotionStoryboard).
///
/// Five moments, and one place that has none. The storyboard's sixth panel is
/// the important one: the capture path — weigh, quality, price, accept — runs
/// at 160ms or less and carries no animation at all, because a queue of
/// farmers never waits for a flourish. That restraint is what earns the rest.
/// `capture_motion_test.dart` enforces it by driving the wizard and asserting
/// no frame is still scheduled 160ms after each step settles.
///
/// **One gate.** Every moment here asks [motionAllowed] and, when the answer
/// is no, builds no controller at all rather than running one at zero — the
/// pattern LACTEVA-MOBILE-007's shimmer and BRAND-003's reveal already use. A
/// person who asked not to have animation should not pay for one.
///
/// **Tokens only, no new curves.** Every easing here is
/// `LactevaMotion.easeOutLiquid`. The two durations the board specifies that
/// are not already tokens are named below with the panel they come from, the
/// same way BRAND-003 named the reveal's three beats.
library;

import 'dart:async';

import 'package:flutter/material.dart';

import '../theme.dart';
import 'mark.dart';

/// The one gate.
///
/// `MediaQuery.disableAnimationsOf` is the platform's own accessibility
/// switch, set by "Remove animations" on Android and "Reduce Motion" on iOS.
bool motionAllowed(BuildContext context) =>
    !MediaQuery.disableAnimationsOf(context);

/// Durations the storyboard names that the token scale does not already carry.
abstract final class MilkMoments {
  /// Panel 2 — the parchi moment. The one celebration in the app: a drop
  /// falls into place as the slip is minted, and then it is over.
  static const parchi = Duration(milliseconds: 600);

  /// Panel 4 — the stagger between rows settling in. The total is
  /// [LactevaMotion.base]; this is the gap between one row and the next.
  static const stagger = Duration(milliseconds: 40);

  /// Panel 4 — how far a row rises as it arrives.
  static const rise = 4.0;

  /// Panel 4 — how many rows may stagger before the rest simply appear. Past
  /// this the last row would arrive later than a person would wait, which is
  /// the moment a flourish becomes a delay.
  static const maxStaggered = 6;
}

// =====================================================================
// Panel 2 · the parchi moment
// =====================================================================

/// A drop falls into place as the parchi is minted.
///
/// 600ms, once, and never again — the queue moves on. It plays when the slip
/// ARRIVES, which is why the trigger is the child appearing rather than a
/// screen being built: an offline completion has no parchi and gets no
/// celebration, honestly.
class ParchiMint extends StatefulWidget {
  const ParchiMint({super.key, required this.child});

  final Widget child;

  @override
  State<ParchiMint> createState() => _ParchiMintState();
}

class _ParchiMintState extends State<ParchiMint>
    with SingleTickerProviderStateMixin {
  AnimationController? _controller;
  bool _started = false;

  @override
  void didChangeDependencies() {
    super.didChangeDependencies();
    if (_started || !motionAllowed(context)) return;
    _started = true;
    _controller =
        AnimationController(vsync: this, duration: MilkMoments.parchi)
          ..forward();
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
        return Stack(
          alignment: Alignment.topCenter,
          clipBehavior: Clip.none,
          children: [
            Opacity(opacity: t, child: child),
            // The drop that falls into it. It leaves at the end of the beat
            // rather than resting on the card: this is a moment, not a badge.
            if (controller.value < 1)
              Positioned(
                top: -28 + 28 * t,
                child: Opacity(
                  opacity: (1 - t).clamp(0.0, 1.0),
                  child: const LactevaMark(size: 26),
                ),
              ),
          ],
        );
      },
      child: widget.child,
    );
  }
}

// =====================================================================
// Panel 3 · sync droplets
// =====================================================================

/// Work leaving the phone, as droplets — with the word and the count beside.
///
/// The metaphor an operator needs: their morning is GOING somewhere. The
/// droplets travel only while a run is actually in flight and the queue
/// actually holds something; the sentence is always there, because colour and
/// movement are never the only signal and a count is the thing somebody
/// repeats to the dairy.
class SyncDroplets extends StatefulWidget {
  const SyncDroplets({
    super.key,
    required this.sending,
    required this.pending,
    required this.label,
  });

  /// A run is in flight right now.
  final bool sending;

  /// What the queue holds. Zero stops the droplets whatever [sending] says —
  /// an empty queue has nothing to send.
  final int pending;

  /// The word and the count, already composed by the catalog.
  final String label;

  @override
  State<SyncDroplets> createState() => _SyncDropletsState();
}

class _SyncDropletsState extends State<SyncDroplets>
    with SingleTickerProviderStateMixin {
  AnimationController? _controller;

  bool get _travelling => widget.sending && widget.pending > 0;

  @override
  void didChangeDependencies() {
    super.didChangeDependencies();
    _sync();
  }

  @override
  void didUpdateWidget(SyncDroplets old) {
    super.didUpdateWidget(old);
    _sync();
  }

  void _sync() {
    if (!_travelling || !motionAllowed(context)) {
      _controller?.dispose();
      _controller = null;
      return;
    }
    // `flow` is the token for something genuinely in progress — a queue
    // draining is exactly what it was written for.
    _controller ??=
        AnimationController(vsync: this, duration: LactevaMotion.flow)
          ..repeat();
  }

  @override
  void dispose() {
    _controller?.dispose();
    super.dispose();
  }

  @override
  Widget build(BuildContext context) {
    final controller = _controller;
    return Column(
      mainAxisSize: MainAxisSize.min,
      children: [
        SizedBox(
          height: 26,
          child: Row(
            mainAxisAlignment: MainAxisAlignment.center,
            children: [
              const Icon(
                Icons.smartphone_outlined,
                size: 22,
                color: LactevaColors.muted,
              ),
              SizedBox(
                width: 70,
                height: 26,
                child: controller == null
                    ? null
                    : AnimatedBuilder(
                        animation: controller,
                        builder: (context, _) => CustomPaint(
                          painter: _DropletsPainter(controller.value),
                        ),
                      ),
              ),
              const Icon(
                Icons.cloud_outlined,
                size: 22,
                color: LactevaColors.muted,
              ),
            ],
          ),
        ),
        const SizedBox(height: 5),
        // Always. The droplets are the fast signal and this is the accessible
        // one, and a count is what an operator repeats to the dairy.
        Text(
          widget.label,
          textAlign: TextAlign.center,
          style: const TextStyle(
            fontSize: 12,
            fontWeight: FontWeight.w700,
            color: LactevaColors.info,
          ),
        ),
      ],
    );
  }
}

/// Three droplets in convoy, fading as they go.
class _DropletsPainter extends CustomPainter {
  _DropletsPainter(this.phase);

  final double phase;

  @override
  void paint(Canvas canvas, Size size) {
    for (var i = 0; i < 3; i++) {
      final t = (phase + i / 3) % 1.0;
      final x = size.width * t;
      // Fades in at the phone and out at the cloud, so nothing pops.
      final fade = (t < 0.15 ? t / 0.15 : t > 0.85 ? (1 - t) / 0.15 : 1.0)
          .clamp(0.0, 1.0);
      canvas.drawOval(
        Rect.fromCenter(
          center: Offset(x, size.height / 2),
          width: 6,
          height: 8,
        ),
        Paint()..color = LactevaColors.water.withValues(alpha: fade),
      );
    }
  }

  @override
  bool shouldRepaint(_DropletsPainter old) => old.phase != phase;
}

// =====================================================================
// Panel 4 · lists settle in
// =====================================================================

/// Arms the settle-in for one screen's FIRST paint, then disarms.
///
/// This is what makes "never on refresh or pagination" true rather than
/// intended. A row built while the scope is armed rises; a row built after —
/// the next page, or the same list after a pull-to-refresh — finds the scope
/// closed and simply appears. Without a scope, every newly-constructed row
/// would animate, and paginating would look like the screen reloading.
class SettleInScope extends StatefulWidget {
  const SettleInScope({super.key, required this.child});

  final Widget child;

  @override
  State<SettleInScope> createState() => _SettleInScopeState();

  /// Whether rows built right now may settle in. False outside a scope, so a
  /// stray `SettleIn` is inert rather than surprising.
  static bool armedIn(BuildContext context) =>
      context
          .dependOnInheritedWidgetOfExactType<_SettleInMarker>()
          ?.armed ??
      false;
}

class _SettleInScopeState extends State<SettleInScope> {
  bool _armed = true;
  Timer? _timer;

  @override
  void initState() {
    super.initState();
    // Open for exactly as long as the first paint's own animation lasts.
    _timer = Timer(
      LactevaMotion.base + MilkMoments.stagger * MilkMoments.maxStaggered,
      () {
        if (mounted) setState(() => _armed = false);
      },
    );
  }

  @override
  void dispose() {
    _timer?.cancel();
    super.dispose();
  }

  @override
  Widget build(BuildContext context) =>
      _SettleInMarker(armed: _armed, child: widget.child);
}

class _SettleInMarker extends InheritedWidget {
  const _SettleInMarker({required this.armed, required super.child});

  final bool armed;

  @override
  bool updateShouldNotify(_SettleInMarker old) => old.armed != armed;
}

/// One row arriving: a 4px rise over 240ms, staggered by its position.
class SettleIn extends StatefulWidget {
  const SettleIn({super.key, required this.index, required this.child});

  final int index;
  final Widget child;

  @override
  State<SettleIn> createState() => _SettleInState();
}

class _SettleInState extends State<SettleIn>
    with SingleTickerProviderStateMixin {
  AnimationController? _controller;
  bool _decided = false;

  @override
  void didChangeDependencies() {
    super.didChangeDependencies();
    if (_decided) return;
    _decided = true;
    if (!motionAllowed(context) || !SettleInScope.armedIn(context)) return;
    final delay =
        MilkMoments.stagger *
        widget.index.clamp(0, MilkMoments.maxStaggered);
    _controller = AnimationController(
      vsync: this,
      duration: LactevaMotion.base,
    );
    // The first row starts NOW, not on the next turn of the event loop. A
    // zero-length timer is still a round trip, and the row a person is
    // looking at should not be the one that waits.
    if (delay == Duration.zero) {
      _controller!.forward();
    } else {
      Timer(delay, () {
        if (mounted) _controller?.forward();
      });
    }
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
            offset: Offset(0, MilkMoments.rise * (1 - t)),
            child: child,
          ),
        );
      },
      child: widget.child,
    );
  }
}

// =====================================================================
// Panel 5 · success ripples once
// =====================================================================

/// A tick inside one milk ripple. 420ms, one ring, never a loop.
///
/// A confirmation that loops stops being a confirmation and becomes a state,
/// and an operator who has already read it should not still be watching it
/// when they look back.
class SuccessRipple extends StatefulWidget {
  const SuccessRipple({super.key, this.size = 64, this.label});

  final double size;

  /// What succeeded, for a screen reader — the ring and the tick are the fast
  /// signal, this is the one that survives not being able to see them.
  final String? label;

  @override
  State<SuccessRipple> createState() => _SuccessRippleState();
}

class _SuccessRippleState extends State<SuccessRipple>
    with SingleTickerProviderStateMixin {
  AnimationController? _controller;
  bool _started = false;

  @override
  void didChangeDependencies() {
    super.didChangeDependencies();
    if (_started || !motionAllowed(context)) return;
    _started = true;
    _controller =
        AnimationController(vsync: this, duration: LactevaMotion.slow)
          ..forward();
  }

  @override
  void dispose() {
    _controller?.dispose();
    super.dispose();
  }

  @override
  Widget build(BuildContext context) {
    final controller = _controller;
    final tick = Icon(
      Icons.check,
      size: widget.size * 0.42,
      color: LactevaColors.success,
    );
    final body = controller == null
        ? SizedBox(
            width: widget.size,
            height: widget.size,
            child: Center(child: tick),
          )
        : AnimatedBuilder(
            animation: controller,
            builder: (context, child) {
              final t = LactevaMotion.easeOutLiquid.transform(
                controller.value,
              );
              return SizedBox(
                width: widget.size,
                height: widget.size,
                child: Stack(
                  alignment: Alignment.center,
                  children: [
                    // ONE ring, leaving once.
                    Opacity(
                      opacity: 0.45 * (1 - t),
                      child: Transform.scale(
                        scale: 0.4 + 0.6 * t,
                        child: Container(
                          decoration: BoxDecoration(
                            shape: BoxShape.circle,
                            border: Border.all(
                              color: LactevaColors.success.withValues(
                                alpha: 0.35,
                              ),
                              width: 1.5,
                            ),
                          ),
                        ),
                      ),
                    ),
                    Container(
                      margin: EdgeInsets.all(widget.size * 0.14),
                      decoration: const BoxDecoration(
                        shape: BoxShape.circle,
                        color: LactevaColors.successTint,
                      ),
                    ),
                    Transform.scale(scale: 0.6 + 0.4 * t, child: child),
                  ],
                ),
              );
            },
            child: tick,
          );
    final label = widget.label;
    return label == null
        ? ExcludeSemantics(child: body)
        : Semantics(label: label, child: ExcludeSemantics(child: body));
  }
}
