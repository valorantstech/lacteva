import 'package:flutter/material.dart';

import 'theme.dart';

/// One status chip for the whole app (LACTEVA-MOBILE-003).
///
/// There were two, and they did not agree about what a status IS. The centres
/// screen drew a six-pixel coloured dot with no word beside it — so a person
/// who cannot separate green from orange was told nothing at all, which is the
/// exact failure the design system's "never colour alone" rule exists to
/// prevent. The rate-card screen drew a proper labelled chip, but coloured it
/// from the Material scheme, so the two surfaces disagreed on what "archived"
/// looks like.
///
/// This is the one both become. It always renders the word, and the colour is
/// chosen by MEANING from the semantic tokens rather than by whichever hue was
/// nearest to hand.
///
/// **Neutral comes from the scheme, not from the palette.** `LactevaColors`
/// has no grey, deliberately — the palette is the product's chromatic
/// decisions, and "this is dormant" is not one of them. So a muted state takes
/// `colorScheme.outline`, which is what the rate-card chip already did and
/// what the theme is for.
class StatusChip extends StatelessWidget {
  const StatusChip({super.key, required this.status});

  /// The platform's own status token — `active`, `published`, `pricing_
  /// unavailable`. Rendered as written (underscores opened out), because
  /// inventing prettier words here would put a second vocabulary in front of
  /// the operator; the glossary is settled elsewhere.
  final String status;

  /// What this status MEANS, in the product's own semantic colours.
  ///
  /// Grouped by meaning, not by module: a centre that is `active` and a rate
  /// card that is `published` are both "this is live and in use", and there is
  /// no reason for an operator to learn two colours for one idea.
  static Color colorFor(String status, ColorScheme scheme) =>
      switch (status.toLowerCase()) {
        // Live, done, agreed.
        'active' ||
        'published' ||
        'approved' ||
        'completed' ||
        'delivered' ||
        'sent' ||
        'ready' ||
        'healthy' ||
        'ok' ||
        'succeeded' ||
        'paid' ||
        'finalized' =>
          LactevaColors.success,
        // Wants attention, but nothing is wrong yet.
        'maintenance' ||
        'warning' ||
        'pending' ||
        'processing' ||
        'draft' ||
        'submitted' ||
        'conflict' ||
        'skipped' ||
        'pricing_unavailable' =>
          LactevaColors.warning,
        // Wrong, and somebody has to act.
        'failed' || 'rejected' || 'error' || 'dead' || 'unhealthy' =>
          LactevaColors.danger,
        // Over. Not a failure, just no longer in play — and not a colour the
        // palette owns.
        'archived' || 'inactive' || 'cancelled' || 'closed' || 'superseded' =>
          scheme.outline,
        _ => scheme.outline,
      };

  @override
  Widget build(BuildContext context) {
    final scheme = Theme.of(context).colorScheme;
    final colour = colorFor(status, scheme);
    return Chip(
      // The word is not decoration. It is the accessible signal, and the
      // colour is the fast one — both, always.
      label: Text(status.replaceAll('_', ' ')),
      // A tint rather than a fill: the same 0.12 the readiness card already
      // uses, so a chip reads as a state and not as a button.
      backgroundColor: colour.withValues(alpha: 0.12),
      side: BorderSide(color: colour.withValues(alpha: 0.35)),
      visualDensity: VisualDensity.compact,
    );
  }
}
