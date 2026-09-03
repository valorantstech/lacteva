/// The Lacteva design system, for the operator's hand (Design System V1).
///
/// The same palette as the portal and the marketing site — one product, one
/// colour — but NOT the same layout thinking. A portal is read at a desk with
/// a mouse; this is used one-handed, at a collection counter, often outdoors
/// in daylight, sometimes by someone wearing gloves. So the tokens below are
/// shared and the ergonomics are not.
///
/// What is deliberately different from the portal:
///
///   * `minTouchTarget` is 48dp and applies to everything tappable. The
///     platform minimum is 44; a counter is not a desk.
///   * Type is a step larger throughout. Bright daylight on a cheap screen
///     costs more legibility than any font choice recovers.
///   * Contrast is pushed higher than the portal's, for the same reason.
///
/// Colours are the sRGB rendering of the portal's OKLCH tokens. They are
/// pinned by `theme_parity_test.dart`, so the two clients cannot drift into
/// being two products.
library;

import 'package:flutter/material.dart';

/// The Lacteva palette. One source, shared with the portal.
abstract final class LactevaColors {
  /// Deep dairy green — the brand. The product's one chromatic decision,
  /// carried since the first mobile build (#1B5E20) and now everywhere.
  static const dairy = Color(0xFF1B5E20);
  static const dairyDeep = Color(0xFF0E3D14);

  /// Milk and cream: the ground. Cards are milk, pages are cream.
  static const milk = Color(0xFFFFFFFF);
  static const cream = Color(0xFFFBF9F3);

  /// Ink — a deep green-black, so even the darkest text is in the family.
  static const ink = Color(0xFF17251C);

  /// Fresh green: an accent for movement and affirmation.
  static const fresh = Color(0xFF3FA55C);

  /// Water blue: strictly controlled, used for sync and flow.
  static const water = Color(0xFF3E7EA6);

  /// Warm amber: attention, never alarm.
  static const amber = Color(0xFFD08A2C);

  /// Semantics. Never the only signal — the word is always rendered too.
  static const success = Color(0xFF2E7D45);
  static const warning = Color(0xFFB4711F);
  static const danger = Color(0xFFB3261E);
  static const info = Color(0xFF2F6E93);

  /// Intelligence: a hue used nowhere else, so a computed signal is never
  /// mistaken for success, warning or brand.
  static const intelligence = Color(0xFF5B4FA8);

  // ---------------------------------------------------------------------
  // On the brand ground (LACTEVA-MOBILE-005, from the approved board).
  //
  // The hero band is deep green, and the supporting colours tuned for a milk
  // ground effectively disappear on it — the same correctness problem the
  // portal's `Metric.onBrand` switch exists to solve. These are their
  // measured counterparts, taken from the artboard's own values.
  // ---------------------------------------------------------------------

  /// Text on the brand ground. Warmer than pure white, so it reads as milk
  /// rather than as a hole in the green.
  static const onBrand = Color(0xFFFDFBF4);

  /// The greeting above the centre's name, and other secondary lines on brand.
  static const onBrandMuted = Color(0xFFE5EDD9);

  /// A metric's caption on brand — quieter again than [onBrandMuted].
  static const onBrandFaint = Color(0xFFC9D8BE);

  /// The dot on the session pill. Lighter than [fresh], which is tuned for
  /// cream and goes muddy against deep green.
  static const onBrandLive = Color(0xFF7FD495);

  /// Good news ON the brand ground — "nothing due". [success] is measured for
  /// cream and disappears into deep green; this is its counterpart, and the
  /// reason `Metric.onBrand` exists in the portal.
  static const onBrandPositive = Color(0xFF90E0A5);

  /// The far corner of the household hero. The band is deep enough that a
  /// two-stop gradient banded visibly across 390px, so the boards give it a
  /// third, slightly warmer stop to land on.
  static const dairyNight = Color(0xFF123A18);

  /// Milk with a shadow in it — the bottom of a filled vessel, where [milk]
  /// is its lit surface.
  static const milkFill = Color(0xFFF1EDDD);

  /// The lit edge of the enriched mark (LACTEVA-BRAND-003) — the one place
  /// this product uses pure white, and only where a highlight has to be
  /// brighter than milk to read as light rather than as paint.
  static const milkLit = Color(0xFFFFFFFF);

  // ---------------------------------------------------------------------
  // Structure on cream.
  // ---------------------------------------------------------------------

  /// The line around a quiet card. Warm, so it belongs to the cream page
  /// rather than sitting on it as grey.
  static const hairline = Color(0xFFEDEAE0);

  /// A rule INSIDE a card, one step quieter than [hairline].
  static const divider = Color(0xFFF0EDE3);

  /// Supporting text. The palette owns no grey, and this is not one: it is a
  /// desaturated green, which is why captions here look related to the brand.
  static const muted = Color(0xFF5F6B5C);

  /// The quietest text the product uses — a footer fact, present but never
  /// competing.
  static const faint = Color(0xFF8A937F);

  // ---------------------------------------------------------------------
  // Tints. A state is a tinted ground with a matching foreground, never a
  // fill: a chip must not read as a button.
  // ---------------------------------------------------------------------

  static const successTint = Color(0xFFE9F0EA);
  static const onSuccessTint = Color(0xFF2E5C38);
  static const warningTint = Color(0xFFF7ECE0);
  static const warningHairline = Color(0xFFEDE4D2);

  /// A bar that is context rather than subject — the quiet columns behind the
  /// one being read.
  static const quietBar = Color(0xFFDCE7D6);

  /// The darker foreground the round's amber chips take. [warning] is tuned to
  /// sit on cream; on the amber tint it loses too much separation to be read
  /// at a gate in sunlight.
  static const onWarningTint = Color(0xFF8A5410);

  /// Water, tinted. Wayfinding — a map pin, an invoice — never money and never
  /// success.
  static const waterTint = Color(0xFFEAF1F5);

  /// A FAILURE, and the only tint that means one (WO-64).
  ///
  /// The round showed "Pending" — nothing done yet, the normal state of every
  /// stop at 5am — in the same amber as a delivery that had come back. The two
  /// read as siblings, so the eye learned to skim both. A failure gets its own
  /// ground so that the one row a roundsman must act on is the one row that
  /// looks different.
  static const dangerTint = Color(0xFFF7E7E6);

  /// [danger] darkened for the tint, the same reason [onWarningTint] exists:
  /// the pure hue loses separation on its own ground in sunlight.
  static const onDangerTint = Color(0xFF8C2019);

  /// NOT YET, which is not a problem (WO-64).
  ///
  /// A stop nobody has reached is the expected state of a round that has just
  /// started. It is context, not subject — so it takes the quietest ground in
  /// the palette and a muted foreground, and the colour is spent on the rows
  /// that need a decision instead.
  static const neutralTint = Color(0xFFEFEFEC);
  static const onNeutralTint = Color(0xFF5B5F58);

  // ---------------------------------------------------------------------
  // On ink (LACTEVA-MOBILE-006, from the Driver board).
  //
  // The on-board band is the one dark surface in the product. It is dark
  // because it is a FACT about the van rather than a control — the eye should
  // pass over it unless it is looking for it — and the two foregrounds below
  // are the measured pair for that ground.
  // ---------------------------------------------------------------------

  static const onInk = Color(0xFFF7F5EC);
  static const onInkMuted = Color(0xFF9DAB99);

  // ---------------------------------------------------------------------
  // Controls and quiet grounds.
  // ---------------------------------------------------------------------

  /// The outline of a control a thumb operates — a stepper, a secondary
  /// action. Heavier than [hairline], which merely separates.
  static const controlBorder = Color(0xFFD8D3C6);

  /// Not a colour — the absence of one.
  ///
  /// Named here so a surface that must let what is BEHIND it show through
  /// (WO-33's auth ground runs under the app bar) does not have to reach for
  /// a Material literal and trip the palette guard. Adding it to the palette
  /// rather than exempting the files keeps that guard strict everywhere else.
  static const transparent = Color(0x00000000);

  /// The round's figures sit on a barely-there wash rather than on plain milk,
  /// so a strip of numbers reads as one object.
  static const paleTint = Color(0xFFF3F7EE);
  static const paleTintBorder = Color(0xFFE4EADA);
}

/// The pale wash under a strip of figures, at the boards' 150° (see
/// [kBrandGradientBegin] for why these alignments and not an angle).
LinearGradient paleGradient() => const LinearGradient(
  begin: kBrandGradientBegin,
  end: kBrandGradientEnd,
  colors: [LactevaColors.milk, LactevaColors.paleTint],
);

/// The household hero's ground: the brand gradient with a third stop, because
/// two stops banded visibly across a band this deep.
LinearGradient deepBrandGradient() => const LinearGradient(
  begin: kBrandGradientBegin,
  end: kBrandGradientEnd,
  colors: [
    LactevaColors.dairy,
    LactevaColors.dairyDeep,
    LactevaColors.dairyNight,
  ],
  stops: [0, 0.78, 1],
);

/// Progress, left to right — a run draining rather than a state.
/// The corner light every brand band carries (WO-33).
///
/// A flat gradient band reads as printed. One soft light in the top corner
/// gives it depth, and putting it HERE rather than in each screen is the
/// LACTEVA-BRAND-002 lesson applied to lighting: the operator home, the
/// household header, the portal dashboard and the store banner are all
/// supposed to look lit from the same place, and three copies of a radius
/// drift into three different rooms.
///
/// Used as a `foregroundDecoration`, so it lies over the band's own gradient
/// without either of them having to know about the other.
const BoxDecoration kBrandBandLight = BoxDecoration(
  gradient: RadialGradient(
    center: Alignment(0.86, -1.1),
    radius: 1.25,
    colors: [Color(0x24FDFBF4), Color(0x00FDFBF4)],
  ),
);

const LinearGradient kProgressGradient = LinearGradient(
  begin: Alignment.centerLeft,
  end: Alignment.centerRight,
  colors: [LactevaColors.success, LactevaColors.fresh],
);

/// The brand gradient, as the boards draw it.
///
/// CSS measures a gradient angle clockwise from "to top", so `150deg` points
/// down and to the right. Flutter takes two [Alignment]s instead, which are
/// BOX-RELATIVE — the same pair renders a different visual angle in a tall box
/// than in a wide one, where CSS's degrees are absolute. This is the closest
/// faithful translation: the unit vector for 150° is (sin 150°, −cos 150°) =
/// (0.5, 0.866), and the alignments are that vector and its negative.
const Alignment kBrandGradientBegin = Alignment(-0.5, -0.866);
const Alignment kBrandGradientEnd = Alignment(0.5, 0.866);

LinearGradient brandGradient() => const LinearGradient(
  begin: kBrandGradientBegin,
  end: kBrandGradientEnd,
  colors: [LactevaColors.dairy, LactevaColors.dairyDeep],
);

/// The milk motion language, in the same timings as the portal.
///
/// Motion may express state; it must never delay work. Anything on the
/// operator's critical path uses [fast] or less — a queue of farmers does not
/// wait for an animation.
abstract final class LactevaMotion {
  static const instant = Duration(milliseconds: 90);
  static const fast = Duration(milliseconds: 160);
  static const base = Duration(milliseconds: 240);
  static const slow = Duration(milliseconds: 420);

  /// The liquid timing, for things genuinely in progress — a queue draining,
  /// a collection completing.
  static const flow = Duration(milliseconds: 900);

  /// Milk settles rather than stopping. This is the curve that makes Lacteva
  /// motion recognisable, and it is the default for anything that arrives.
  static const easeOutLiquid = Cubic(0.22, 1, 0.36, 1);
  static const easeStandard = Cubic(0.2, 0, 0, 1);
}

/// Ergonomics for a counter, not a desk.
abstract final class LactevaMetrics {
  /// Every tappable thing. 48dp, above the 44dp platform floor, because the
  /// operator may be gloved, hurried, or both.
  static const double minTouchTarget = 48;

  /// The primary action on a workflow screen is deliberately larger again —
  /// "what do I press next" should never be a question.
  static const double primaryActionHeight = 56;

  static const double radius = 12;
  static const double gutter = 16;
}

/// The operator's theme.
ThemeData lactevaTheme() {
  final scheme = ColorScheme.fromSeed(
    seedColor: LactevaColors.dairy,
    // Explicit overrides where the generated scheme would drift off-brand.
    primary: LactevaColors.dairy,
    secondary: LactevaColors.fresh,
    error: LactevaColors.danger,
    surface: LactevaColors.milk,
  );

  return ThemeData(
    useMaterial3: true,
    colorScheme: scheme,
    scaffoldBackgroundColor: LactevaColors.cream,

    // A step larger than Material's defaults, for daylight and cheap screens.
    textTheme: const TextTheme(
      headlineSmall: TextStyle(fontSize: 26, fontWeight: FontWeight.w600),
      titleLarge: TextStyle(fontSize: 22, fontWeight: FontWeight.w600),
      titleMedium: TextStyle(fontSize: 18, fontWeight: FontWeight.w600),
      bodyLarge: TextStyle(fontSize: 17),
      bodyMedium: TextStyle(fontSize: 16),
      labelLarge: TextStyle(fontSize: 16, fontWeight: FontWeight.w600),
    ),

    filledButtonTheme: FilledButtonThemeData(
      style: FilledButton.styleFrom(
        minimumSize: const Size.fromHeight(LactevaMetrics.primaryActionHeight),
        shape: RoundedRectangleBorder(
          borderRadius: BorderRadius.circular(LactevaMetrics.radius),
        ),
        textStyle: const TextStyle(fontSize: 17, fontWeight: FontWeight.w600),
      ),
    ),
    outlinedButtonTheme: OutlinedButtonThemeData(
      style: OutlinedButton.styleFrom(
        minimumSize: const Size(0, LactevaMetrics.minTouchTarget),
        shape: RoundedRectangleBorder(
          borderRadius: BorderRadius.circular(LactevaMetrics.radius),
        ),
      ),
    ),
    textButtonTheme: TextButtonThemeData(
      style: TextButton.styleFrom(
        minimumSize: const Size(0, LactevaMetrics.minTouchTarget),
      ),
    ),

    // Generous fields: typing is the slowest thing an operator does, so the
    // target for starting is large and the label never collapses out of view.
    inputDecorationTheme: InputDecorationTheme(
      filled: true,
      fillColor: LactevaColors.milk,
      contentPadding: const EdgeInsets.symmetric(horizontal: 16, vertical: 18),
      border: OutlineInputBorder(
        borderRadius: BorderRadius.circular(LactevaMetrics.radius),
      ),
    ),

    cardTheme: CardThemeData(
      color: LactevaColors.milk,
      elevation: 0,
      margin: EdgeInsets.zero,
      shape: RoundedRectangleBorder(
        borderRadius: BorderRadius.circular(LactevaMetrics.radius),
        side: BorderSide(color: LactevaColors.ink.withValues(alpha: 0.08)),
      ),
    ),

    snackBarTheme: const SnackBarThemeData(
      behavior: SnackBarBehavior.floating,
    ),
  );
}
