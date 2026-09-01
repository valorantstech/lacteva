/// Every catalog key has a caller (P1-LOCALE-I18N-001).
///
/// The "catalog without callers" defect has now been found THREE times in this
/// codebase: keys were written in all three languages, the screen retyped the
/// English beside them, and a Hindi operator read English from a screen whose
/// translation had existed for months. Reviews did not catch it because both
/// halves look correct in isolation.
///
/// So the property is executable: a key that exists must be looked up
/// somewhere in `lib/`. This is the mirror of the parity test — parity proves
/// every key is TRANSLATED, this proves every key is USED. Together they close
/// the loop that a language actually reaches a screen.
library;

import 'dart:io';

import 'package:flutter_test/flutter_test.dart';
import 'package:lacteva_mobile/src/l10n.dart';

/// Keys looked up through a computed expression rather than a literal — the
/// catalog families that exist precisely to map a server CODE to a word. Their
/// call site is `t('status.$code')`, so no literal appears in the source.
const _dynamicFamilies = <String>[
  'status.', // deliveries.dart: t('status.$status')
  'driver.outcome.', // driver.dart: t('driver.outcome.$outcome')
  'slot.', // record screens: t('slot.$slot')
  'milk.', // collection wizard: t('milk.$milkType')
  'driver.status.', // driver.dart: t('driver.status.${run['status']}')
  'invoice.', // customer_portal.dart: t('invoice.${bill['status']}')
  'schedule.', // customer_portal.dart: t('${plan['schedule_key']}')
  'day.', // customer_portal.dart: the week strip, by index
];

void main() {
  test('every catalog key is looked up somewhere in lib/', () {
    final source = Directory('lib')
        .listSync(recursive: true)
        .whereType<File>()
        .where((f) => f.path.endsWith('.dart'))
        .map((f) => f.readAsStringSync())
        .join('\n');

    final orphans = <String>[];
    for (final key in catalogs['en']!.keys) {
      if (_dynamicFamilies.any(key.startsWith)) continue;
      // The literal as it appears in a lookup: t('key') or t("key").
      if (source.contains("'$key'") || source.contains('"$key"')) continue;
      orphans.add(key);
    }

    expect(
      orphans,
      isEmpty,
      reason:
          'These keys are translated but never shown — either wire them to '
          'the screen that retypes their English, or delete them: $orphans',
    );
  });

  test('the dynamic families still resolve for the codes they serve', () {
    // A family is exempt from the caller check above, so its members must be
    // proven reachable here instead — otherwise the exemption becomes a hole.
    const en = 'en';
    for (final code in ['scheduled', 'delivered', 'skipped', 'returned', 'cancelled']) {
      expect(L10n(en).t('status.$code'), isNot('status.$code'));
    }
    for (final code in ['delivered', 'skipped', 'returned', 'cancelled']) {
      expect(L10n(en).t('driver.outcome.$code'), isNot('driver.outcome.$code'));
    }
    for (final code in ['morning', 'evening']) {
      expect(L10n(en).t('slot.$code'), isNot('slot.$code'));
    }
    // The milk types the collection wizard offers. WO-55 added `sheep`, and
    // the label must exist in every language the app ships, not only English:
    // an operator on the Hindi build seeing `milk.sheep` in the dropdown is
    // the same defect as no translation at all.
    for (final code in ['cow', 'buffalo', 'goat', 'sheep', 'mixed']) {
      for (final locale in ['en', 'hi', 'ar']) {
        expect(L10n(locale).t('milk.$code'), isNot('milk.$code'));
      }
    }
    // LACTEVA-MOBILE-006: every run status the platform can send
    // (`modules/logistics/models.py: RUN_STATUSES`). The driver header shows
    // this word where the board showed a wall-clock time.
    for (final code in ['planned', 'in_progress', 'completed', 'cancelled']) {
      expect(L10n(en).t('driver.status.$code'), isNot('driver.status.$code'));
    }
    // LACTEVA-MOBILE-007: every invoice status (`billing/models.py`), every
    // schedule mask the plan view can send (`customer/service.py`), and the
    // seven days the household's week strip is built from.
    for (final code in ['draft', 'issued', 'paid', 'cancelled']) {
      expect(L10n(en).t('invoice.$code'), isNot('invoice.$code'));
    }
    for (final code in ['daily', 'mon_sat', 'weekdays', 'custom']) {
      expect(L10n(en).t('schedule.$code'), isNot('schedule.$code'));
    }
    for (final code in ['mon', 'tue', 'wed', 'thu', 'fri', 'sat', 'sun']) {
      expect(L10n(en).t('day.$code'), isNot('day.$code'));
    }
  });
}
