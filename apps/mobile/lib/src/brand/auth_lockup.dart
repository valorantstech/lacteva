/// The face both auth screens wear (WO-36).
///
/// The can, the owner's traced letterforms and the tagline, in one
/// composition. Sign-in had this arrangement inline; the reset screen had a
/// plain app-bar title, so a locked-out operator left the product to get back
/// into it.
///
/// **One widget, not two arrangements of the same parts.** The pieces are
/// already single-source — `LactevaCanMark` and `LactevaWordmark` both draw
/// generated geometry — but the COMPOSITION was not, and a composition copied
/// to a second screen is exactly how the mark came to exist three times
/// before LACTEVA-BRAND-002. The sizes and the two gaps live here now, and
/// both screens get them by using this rather than by agreeing to.
///
/// Extracted from sign-in unchanged: same sizes, same paddings, same order,
/// so sign-in is pixel-identical to what it was and its own tests never had
/// to move.
library;

import 'package:flutter/material.dart';

import 'mark.dart';
import 'wordmark.dart';

/// The Lacteva lockup as the auth screens show it.
class AuthLockup extends StatelessWidget {
  const AuthLockup({super.key});

  /// The can's drawn height.
  static const double markHeight = 56;

  /// The wordmark's CAP height — the letters, not the artwork's box.
  static const double capHeight = 26;

  @override
  Widget build(BuildContext context) {
    // `stretch`, because sign-in's column stretches and these two Paddings
    // were its direct children: keeping the cross-axis behaviour is what
    // makes the extraction free of any visual change there.
    return const Column(
      mainAxisSize: MainAxisSize.min,
      crossAxisAlignment: CrossAxisAlignment.stretch,
      children: [
        Padding(
          padding: EdgeInsets.only(bottom: 10),
          child: Center(child: LactevaCanMark(size: markHeight)),
        ),
        Padding(
          padding: EdgeInsets.only(bottom: 24),
          child: Center(
            child: LactevaWordmark(height: capHeight, withTagline: true),
          ),
        ),
      ],
    );
  }
}
