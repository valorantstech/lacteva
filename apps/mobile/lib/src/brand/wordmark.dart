/// The owner's wordmark, drawn (LACTEVA-BRAND-004 Amendment 1).
///
/// **Never set in a font.** Amendment 1 is explicit that no committed surface
/// may carry a font-rendered approximation of LACTEVA, and until WO-33 three
/// of them did: the sign-in screen, the password-reset screen and the splash
/// all wrote the word in whatever the UI typeface happened to be. The
/// letterforms are the owner's artwork — flat-terminal, extra-bold, with a
/// drop seated in the final A — and a grotesque that happened to be installed
/// agrees with none of it.
///
/// The outlines come from `mark.g.dart`, traced from the binding reference by
/// `tools/brand/trace_wordmark.py` and checked by `check_inline.py`. Nothing
/// here draws a letter; this decides only how the artwork is COLOURED and how
/// big it is.
///
/// **The reduction rule.** The VA gradient runs about eighty units down an
/// artwork drawn at 646 wide. Below roughly twenty logical pixels of cap
/// height there is no room for it to be a gradient — it is two greens
/// arguing — so small sizes get the flat brand green, and an ink ground gets
/// the one-colour cream derivation Amendment 1 defines. Same outlines every
/// time; only the fill changes.
library;

import 'package:flutter/material.dart';

import 'mark.g.dart';
import 'path_data.dart';

/// Below this cap height the VA gradient stops being a gradient.
const double kWordmarkGradientFloor = 20.0;

/// The LACTEVA wordmark, optionally with its tagline and rules.
class LactevaWordmark extends StatelessWidget {
  const LactevaWordmark({
    super.key,
    this.height = 28,
    this.onInk = false,
    this.withTagline = false,
  });

  /// The CAP height in logical pixels — the height of the letters
  /// themselves, which is the measurement a layout is actually reasoning
  /// about, rather than the artwork's box.
  final double height;

  /// Draw the one-colour derivation for a dark ground: the same outlines,
  /// filled cream.
  final bool onInk;

  /// Include "Smart Dairy. Stronger Tomorrow." and its two flanking rules,
  /// in the reference's own spacing.
  final bool withTagline;

  @override
  Widget build(BuildContext context) {
    final scale = height / kWordmarkCapsBounds.height;
    // With the tagline the drawn box is the whole artwork; without it, the
    // caps' own box — so a caller asking for caps does not get forty units of
    // empty artwork underneath them.
    final box = withTagline
        ? Size(
            kWordmarkBounds.width * scale,
            (kWordmarkBounds.height - kWordmarkCapsBounds.top) * scale,
          )
        : Size(kWordmarkCapsBounds.width * scale, height);
    return ExcludeSemantics(
      child: SizedBox(
        width: box.width,
        height: box.height,
        child: CustomPaint(
          painter: _WordmarkPainter(
            scale: scale,
            onInk: onInk,
            withTagline: withTagline,
          ),
        ),
      ),
    );
  }
}

class _WordmarkPainter extends CustomPainter {
  const _WordmarkPainter({
    required this.scale,
    required this.onInk,
    required this.withTagline,
  });

  final double scale;
  final bool onInk;
  final bool withTagline;

  @override
  void paint(Canvas canvas, Size size) {
    canvas.save();
    // The artwork is drawn in its own coordinates under one scale, so every
    // internal proportion — letter spacing, the gap under the caps, the
    // length of the rules — is the reference's rather than arithmetic done
    // here. Only the origin moves.
    canvas.translate(
      -(withTagline ? 0.0 : kWordmarkCapsBounds.left) * scale,
      -kWordmarkCapsBounds.top * scale,
    );
    canvas.scale(scale, scale);

    final capHeight = kWordmarkCapsBounds.height * scale;
    final navy = Paint()
      ..color = onInk ? const Color(kLogoCream) : const Color(kLogoNavy);
    canvas.drawPath(lactevaPathData(kWordmarkNavyData), navy);

    final Paint va;
    if (onInk) {
      va = Paint()..color = const Color(kLogoCream);
    } else if (capHeight < kWordmarkGradientFloor) {
      // Too small for a ramp to read as one. The gradient's own top stop is
      // the honest single colour — not a third green invented for the case.
      va = Paint()..color = const Color(kLogoVaTop);
    } else {
      va = Paint()
        ..shader = const LinearGradient(
          begin: Alignment.topCenter,
          end: Alignment.bottomCenter,
          colors: [Color(kLogoVaTop), Color(kLogoVaBottom)],
        ).createShader(
          Rect.fromLTRB(
            0,
            kWordmarkGradientTop,
            kWordmarkBounds.width,
            kWordmarkGradientBottom,
          ),
        );
    }
    canvas.drawPath(lactevaPathData(kWordmarkGreenData), va);

    if (withTagline) {
      canvas.drawPath(
        lactevaPathData(kWordmarkRuleData),
        Paint()
          ..color = onInk
              ? const Color(kLogoCream).withValues(alpha: 0.55)
              : const Color(kLogoRule),
      );
      canvas.drawPath(
        lactevaPathData(kWordmarkTaglineData),
        Paint()
          ..color = onInk
              ? const Color(kLogoCream).withValues(alpha: 0.8)
              : const Color(kLogoTaglineInk),
      );
    }
    canvas.restore();
  }

  @override
  bool shouldRepaint(_WordmarkPainter old) =>
      old.scale != scale ||
      old.onInk != onInk ||
      old.withTagline != withTagline;
}
