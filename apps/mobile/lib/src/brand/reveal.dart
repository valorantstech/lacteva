/// The reveal (LACTEVA-BRAND-003).
///
/// Three beats over 1.4 seconds — the drop falls, milk ripples, the wordmark
/// settles — played over the sign-in screen, which is the moment between
/// launch and work and the only place in this product where an entrance is
/// appropriate.
///
/// **It never stands in front of the form.** This is the WO-17 discipline
/// applied to a brand animation: the login screen is built, its controllers
/// are live and its fields are focusable from the first frame, and the reveal
/// mounts ON TOP of them without capturing a single pointer. A tap anywhere
/// both dismisses the reveal AND reaches whatever was underneath it, so a
/// person who came to sign in never pays for the animation — they tap the
/// email field, the reveal goes, and the keyboard opens.
///
/// **Once a day.** An entrance that plays every time an operator reopens the
/// app between two farmers is not a welcome, it is an obstacle. The gate is
/// persisted, and the day it compares against is the HANDSET's — the same
/// judgement the greeting on the collection home records: this is a courtesy
/// for the person holding the phone, not a business fact, and no ledger moves
/// if a border crossing costs somebody one extra reveal.
///
/// **Reduced motion plays nothing at all.** The static rich mark already sits
/// in the sign-in screen's own header, so a person who asked not to have
/// animation gets the same mark, still, with nothing to dismiss — rather than
/// a motionless layer they have to tap through.
library;

import 'dart:async';
import 'dart:convert';
import 'dart:io';

import 'package:flutter/material.dart';

import '../theme.dart';
import 'mark.dart';
import 'motion.dart';

/// The three beats, and what the last one waits for.
abstract final class RevealBeats {
  /// 1 · the drop falls.
  static const drop = Duration(milliseconds: 420);

  /// 2 · it lands, milk ripples. Two rings, the second trailing.
  static const ripple = Duration(milliseconds: 600);
  static const secondRing = Duration(milliseconds: 200);

  /// 3 · the wordmark settles in — a fade and a four-pixel rise.
  static const word = Duration(milliseconds: 380);
  static const wordRise = 4.0;

  static const total = Duration(milliseconds: 1400);

  /// Where each beat begins, as a fraction of [total].
  static double get dropEnd => drop.inMilliseconds / total.inMilliseconds;
  static double get rippleEnd =>
      (drop + ripple).inMilliseconds / total.inMilliseconds;
}

/// Whether the reveal has already played today.
///
/// An interface, because the gate is the only part of this worth testing
/// without a filesystem — and because a test that had to write to the app's
/// documents directory would be testing `path_provider`.
abstract class RevealGate {
  /// True at most once per calendar day.
  Future<bool> claim(String today);
}

/// Remembers nothing. The reveal plays every launch.
class AlwaysReveal implements RevealGate {
  const AlwaysReveal();

  @override
  Future<bool> claim(String today) async => true;
}

/// Remembers in memory — a single run of the app, and the tests.
class MemoryRevealGate implements RevealGate {
  MemoryRevealGate([this._last]);

  String? _last;

  String? get lastPlayed => _last;

  @override
  Future<bool> claim(String today) async {
    if (_last == today) return false;
    _last = today;
    return true;
  }
}

/// Remembers in a file beside the offline queue.
///
/// One line of JSON. Deliberately NOT the sync queue's own store: that file
/// holds a rider's captured work, and putting a cosmetic preference in it
/// would put the two on the same fsync.
class FileRevealGate implements RevealGate {
  const FileRevealGate(this.path);

  final String path;

  @override
  Future<bool> claim(String today) async {
    final file = File(path);
    try {
      if (await file.exists()) {
        final data = jsonDecode(await file.readAsString());
        if (data is Map && data['played'] == today) return false;
      }
    } catch (_) {
      // A corrupt or unreadable gate means "play it" — the failure mode of a
      // decoration must never be a screen that will not come up.
    }
    try {
      await file.writeAsString(jsonEncode({'played': today}));
    } catch (_) {
      // A read-only filesystem costs one repeated reveal, and nothing else.
    }
    return true;
  }
}

/// Today, as the HANDSET reckons it. See the note in this library's docs on
/// why a courtesy may read the phone's clock when a business fact may not.
String handsetDay([DateTime? now]) {
  final d = (now ?? DateTime.now()).toLocal();
  return '${d.year.toString().padLeft(4, '0')}-'
      '${d.month.toString().padLeft(2, '0')}-'
      '${d.day.toString().padLeft(2, '0')}';
}

/// Plays the reveal over [child], if it may.
class LactevaReveal extends StatefulWidget {
  const LactevaReveal({
    super.key,
    required this.child,
    required this.gate,
    this.today,
  });

  /// The screen underneath — built, live and interactive from frame one.
  final Widget child;

  final RevealGate gate;

  /// Injected by the tests; null reads the handset clock.
  final String? today;

  @override
  State<LactevaReveal> createState() => _LactevaRevealState();
}

class _LactevaRevealState extends State<LactevaReveal>
    with SingleTickerProviderStateMixin {
  AnimationController? _controller;
  bool _playing = false;
  bool _asked = false;

  @override
  void didChangeDependencies() {
    super.didChangeDependencies();
    if (_asked) return;
    _asked = true;
    // Reduced motion is decided before the gate is even claimed: a person who
    // will never see the reveal should not have "today" spent on their behalf.
    if (!motionAllowed(context)) return;
    unawaited(_maybePlay());
  }

  Future<void> _maybePlay() async {
    final allowed = await widget.gate.claim(widget.today ?? handsetDay());
    if (!allowed || !mounted) return;
    setState(() {
      _playing = true;
      _controller =
          AnimationController(vsync: this, duration: RevealBeats.total)
            ..addStatusListener((status) {
              if (status == AnimationStatus.completed) _end();
            })
            ..forward();
    });
  }

  /// Take the overlay down.
  ///
  /// The controller is NOT disposed here. This runs from a status callback —
  /// from inside the controller's own tick — and tearing it down there is
  /// disposing something mid-frame. It is stopped instead, and `dispose()`
  /// owns its end, which is the one place that can be sure nothing else is
  /// holding it.
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
    return Stack(
      children: [
        widget.child,
        if (_playing && controller != null)
          Positioned.fill(
            // TRANSLUCENT, and the visuals ignore pointers entirely: the tap
            // that dismisses the reveal also reaches the field it was aimed
            // at. The form underneath is the point of the screen.
            child: Listener(
              behavior: HitTestBehavior.translucent,
              onPointerDown: (_) => _end(),
              child: IgnorePointer(
                child: _RevealVisuals(controller: controller),
              ),
            ),
          ),
      ],
    );
  }
}

class _RevealVisuals extends StatelessWidget {
  const _RevealVisuals({required this.controller});

  final AnimationController controller;

  @override
  Widget build(BuildContext context) {
    return AnimatedBuilder(
      animation: controller,
      builder: (context, _) {
        final t = controller.value;
        return DecoratedBox(
          decoration: BoxDecoration(gradient: deepBrandGradient()),
          child: Center(
            child: Column(
              mainAxisSize: MainAxisSize.min,
              children: [
                SizedBox(
                  width: 160,
                  height: 160,
                  child: Stack(
                    alignment: Alignment.center,
                    children: [
                      _ring(t, delay: Duration.zero, inset: 24, width: 1.5),
                      _ring(
                        t,
                        delay: RevealBeats.secondRing,
                        inset: 40,
                        width: 1,
                      ),
                      _drop(t),
                    ],
                  ),
                ),
                const SizedBox(height: 18),
                _word(t),
              ],
            ),
          ),
        );
      },
    );
  }

  /// 1 · the drop falls, and settles rather than stopping.
  Widget _drop(double t) {
    final p = (t / RevealBeats.dropEnd).clamp(0.0, 1.0);
    final eased = LactevaMotion.easeOutLiquid.transform(p);
    return Opacity(
      opacity: eased,
      child: Transform.translate(
        offset: Offset(0, -40 * (1 - eased)),
        child: const LactevaMark(size: 96),
      ),
    );
  }

  /// 2 · it lands, milk ripples.
  Widget _ring(
    double t, {
    required Duration delay,
    required double inset,
    required double width,
  }) {
    final start =
        (RevealBeats.drop + delay).inMilliseconds /
        RevealBeats.total.inMilliseconds;
    final span =
        RevealBeats.ripple.inMilliseconds / RevealBeats.total.inMilliseconds;
    final p = ((t - start) / span).clamp(0.0, 1.0);
    if (p <= 0) return const SizedBox.shrink();
    final eased = LactevaMotion.easeOutLiquid.transform(p);
    return Opacity(
      opacity: 0.5 * (1 - eased),
      child: Transform.scale(
        scale: 0.75 + 0.85 * eased,
        child: Container(
          margin: EdgeInsets.all(inset),
          decoration: BoxDecoration(
            shape: BoxShape.circle,
            border: Border.all(
              color: LactevaColors.onBrandPositive.withValues(alpha: 0.35),
              width: width,
            ),
          ),
        ),
      ),
    );
  }

  /// 3 · the wordmark settles in.
  Widget _word(double t) {
    final start = RevealBeats.rippleEnd;
    final span =
        RevealBeats.word.inMilliseconds / RevealBeats.total.inMilliseconds;
    final p = ((t - start) / span).clamp(0.0, 1.0);
    final eased = LactevaMotion.easeOutLiquid.transform(p);
    return Opacity(
      opacity: eased,
      child: Transform.translate(
        offset: Offset(0, RevealBeats.wordRise * (1 - eased)),
        child: const Column(
          children: [
            Text(
              'Lacteva',
              style: TextStyle(
                color: LactevaColors.onBrand,
                fontSize: 34,
                fontWeight: FontWeight.w700,
                letterSpacing: -0.68,
              ),
            ),
            SizedBox(height: 4),
            Text(
              'EVERY DROP, ACCOUNTED FOR',
              style: TextStyle(
                color: LactevaColors.onInkMuted,
                fontSize: 13,
                letterSpacing: 1.82,
              ),
            ),
          ],
        ),
      ),
    );
  }
}
