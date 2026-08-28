/// The Lacteva mark, drawn (LACTEVA-BRAND-003).
///
/// The geometry is not here. It is generated into `mark.g.dart` from
/// `tools/brand/mark.py`, the same source the favicon, the launcher and the
/// portal draw from, and `tools/brand/check_inline.py` regenerates and
/// compares it — so this file decides how the mark is LIT and never what
/// shape it is.
///
/// **Why a painter and not an SVG.** Adding `flutter_svg` to draw one shape
/// would be a dependency, a licence and a parser on the launch path of an app
/// that already ships. The mark's outline is cubics and a Flutter `Path` is
/// cubics, so the generator emits the same numbers in Dart.
///
/// **Flat and rich are two voices of one mark.** The flat silhouette keeps
/// the 16px jobs — the launcher, the favicon — where a gradient is a smudge.
/// This rendering owns the surfaces where the mark is large: sign-in, and the
/// reveal that plays over it.
library;

import 'package:flutter/material.dart';

import '../theme.dart';
import 'mark.g.dart';

/// The enriched drop: a lit body, one warm highlight, one meniscus.
class LactevaMark extends StatelessWidget {
  const LactevaMark({super.key, this.size = 96});

  /// The drawn HEIGHT. The drop is taller than it is wide, and a caller
  /// thinking about a hero band is thinking about how tall it is.
  final double size;

  @override
  Widget build(BuildContext context) {
    final width = size * (kMarkBounds.width / kMarkBounds.height);
    return ExcludeSemantics(
      child: SizedBox(
        width: width,
        height: size,
        child: CustomPaint(painter: LactevaMarkPainter()),
      ),
    );
  }
}

/// The mark's three layers, in the order light lands on them.
class LactevaMarkPainter extends CustomPainter {
  @override
  void paint(Canvas canvas, Size size) {
    // The geometry is authored in a 64 grid and cropped to the drop; scale so
    // the drop fills whatever box the caller gave, and translate the crop's
    // origin to it.
    final scale = size.height / kMarkBounds.height;
    canvas.save();
    canvas.translate(-kMarkBounds.left * scale, -kMarkBounds.top * scale);

    final drop = lactevaDropPath(scale);
    final bounds = drop.getBounds();

    // 1 · the body: milk on the lit side, cream shadow on the belly. The axis
    // is the board's, expressed as fractions of the drop's own box.
    canvas.drawPath(
      drop,
      Paint()
        ..shader = const LinearGradient(
          begin: Alignment(-0.6, -1),
          end: Alignment(0.6, 1),
          colors: [
            LactevaColors.milkLit,
            LactevaColors.milk,
            LactevaColors.milkFill,
          ],
          stops: [0, 0.55, 1],
        ).createShader(bounds),
    );

    // 2 · the highlight: a soft radial that fades to nothing, so it cannot
    // become the hard bright dot the interim mark's did.
    final highlight = Rect.fromCenter(
      center: Offset(
        kMarkHighlight.center.dx * scale,
        kMarkHighlight.center.dy * scale,
      ),
      width: kMarkHighlight.width * scale,
      height: kMarkHighlight.height * scale,
    );
    canvas.save();
    canvas.clipPath(drop);
    canvas.drawOval(
      highlight,
      Paint()
        ..shader = RadialGradient(
          colors: [
            LactevaColors.milkLit.withValues(alpha: 0.9),
            LactevaColors.milkLit.withValues(alpha: 0),
          ],
        ).createShader(highlight),
    );

    // 3 · the meniscus: the inside surface of the liquid, clipped to the drop
    // for the reason the SVG clips it — mapped faithfully from the board the
    // arc runs a little past the bulb, and an unclipped tail is a green
    // whisker hanging off the mark.
    final from = kMarkMeniscusFrom * scale;
    final to = kMarkMeniscusTo * scale;
    final r = kMarkMeniscusRadius * scale;
    canvas.drawPath(
      Path()
        ..moveTo(from.dx, from.dy)
        ..arcToPoint(to, radius: Radius.circular(r), clockwise: false),
      Paint()
        ..style = PaintingStyle.stroke
        ..strokeWidth = kMarkMeniscusWidth * scale
        ..strokeCap = StrokeCap.round
        ..color = LactevaColors.dairy.withValues(
          alpha: kMarkMeniscusOpacity,
        ),
    );
    canvas.restore();
    canvas.restore();
  }

  @override
  bool shouldRepaint(LactevaMarkPainter oldDelegate) => false;
}

/// The flat mark: the can, with the drop knocked out of it.
///
/// This is what the launcher wears, what the website's nav shows and what the
/// splash draws — so it is what a light surface in the app should show too.
///
/// [LactevaMark] above is BRAND-003's LIT DROP, and it is explicitly a
/// dark-ground rendering: white milk with a cream shadow, which on the auth
/// screens' cream ground is a pale shape on a pale ground. WO-33 moved
/// sign-in onto this instead, which also settles the coherence question
/// WO-31 raised — the mark on the sign-in screen is now the same object as
/// the mark on the home screen icon.
class LactevaCanMark extends StatelessWidget {
  const LactevaCanMark({super.key, this.size = 54, this.onInk = false});

  /// The drawn HEIGHT of the can.
  final double size;

  /// Cream body and a deep drop, for a dark ground.
  final bool onInk;

  @override
  Widget build(BuildContext context) {
    final width = size * (kCanBounds.width / kCanBounds.height);
    return ExcludeSemantics(
      child: SizedBox(
        width: width,
        height: size,
        child: CustomPaint(painter: LactevaCanPainter(onInk: onInk)),
      ),
    );
  }
}

/// Two fills: the body, then the drop knocked back out of it.
class LactevaCanPainter extends CustomPainter {
  const LactevaCanPainter({required this.onInk});

  final bool onInk;

  @override
  void paint(Canvas canvas, Size size) {
    final scale = size.height / kCanBounds.height;
    final can = lactevaCanPath(scale);
    final offset = -can.getBounds().topLeft;
    canvas.drawPath(
      can.shift(offset),
      Paint()..color = onInk ? const Color(kLogoCream) : const Color(kLogoDairy),
    );
    canvas.drawPath(
      lactevaDropPath(scale).shift(offset),
      Paint()..color = onInk ? const Color(kLogoDeep) : const Color(kLogoCream),
    );
  }

  @override
  bool shouldRepaint(LactevaCanPainter old) => old.onInk != onInk;
}
