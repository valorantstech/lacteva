/// Numbers wear their units (WO-64 · the WO-61 lesson, applied to mobile).
///
/// WO-61 was a total labelled with the wrong currency on the portal: the
/// platform summed money and did not say what money it was, so the client
/// denominated it from the organization and got it wrong. The mobile app has
/// the same class of defect in a quieter form — a round header reading
/// "214.000 L" (three decimals a dairy never says) beside a value reading
/// "0.00" with no currency at all.
///
/// The rules here are the portal's, in Dart:
///
///   FORMAT, NEVER COMPUTE. Every figure arrives from the platform, exact,
///   as a string or a double it already rounded. Nothing here adds, converts
///   or rescales — a litre is not turned into a kilogram, because inventing a
///   density is arithmetic on a business fact.
///
///   A NUMBER WITHOUT ITS DENOMINATION IS NOT MONEY. `money()` refuses to
///   render an amount with no currency: it says so instead. An unlabelled
///   `0.00` is the defect WO-61 was written for.
///
///   ONE DECIMAL FOR A QUANTITY. The platform stores three because a scale
///   reads to three; a dairy SAYS one. Trailing precision on a phone screen
///   is noise that pushes the unit off the edge of a 360dp handset.
library;

import 'session.dart';

/// The symbol for a unit the platform stored (D-21 / WO-70).
///
/// `litre` → `L`, `kg` → `kg`; `mixed` — an aggregate across a change of
/// unit — and anything else is shown as sent, never guessed at.
String unitLabel(Object? unit) {
  switch ((unit ?? '').toString().trim().toLowerCase()) {
    case 'litre':
    case 'litres':
    case 'liter':
    case 'l':
      return 'L';
    case 'kg':
    case 'kilogram':
    case 'kilograms':
      return 'kg';
    default:
      return (unit ?? '').toString();
  }
}

/// The symbol of the unit THIS DAIRY measures in, for a label on a field the
/// operator is about to fill ("Gross (L)"). A figure that came from the
/// platform renders the unit it came WITH — see [recordUnit].
///
/// With no session there is no dairy to ask; `kg` is what every platform
/// before WO-70 measured, and is documented as that, not as a preference.
String orgUnit(Session? session) => session?.organization?.quantityUnitLabel ?? 'kg';

/// The unit a RECORD carries, as its symbol — a transaction's `weight_unit`,
/// a summary's `quantity_unit` — falling back to the dairy's own only when the
/// record has none (an offline projection, before the platform has seen it).
String recordUnit(Object? stored, Session? session) =>
    stored == null || stored.toString().isEmpty ? orgUnit(session) : unitLabel(stored);

/// A quantity as a dairy says it: one decimal, then the unit.
///
/// `214.000` → `214.0 L`. The rounding is presentational and one-way — the
/// value sent to the platform is never this string. The unit is REQUIRED:
/// this used to default to `L`, which is how the home screen said litres over
/// a total the platform had weighed (D-21 / WO-70).
String quantity(Object? value, {required String unit}) {
  final number = _asNumber(value);
  if (number == null) return '—';
  return '${number.toStringAsFixed(1)} $unit';
}

/// The same, without a unit — for a place that renders the unit itself.
String quantityValue(Object? value) {
  final number = _asNumber(value);
  return number == null ? '—' : number.toStringAsFixed(1);
}

/// Money as the ORGANIZATION counts it, and never without it.
///
/// The amount arrives as an exact decimal STRING and leaves as one: no
/// `double.parse`, no arithmetic. The symbol and code come from the session,
/// so an Indian dairy shows ₹ and a Kenyan one KSh without this function
/// knowing either country exists.
///
/// It lives here rather than in `l10n.dart` (WO-64) because there were two
/// money formatters in this app — this one, and a private `_money` on the
/// delivery round that rendered `v.toString()` with no currency at all. That
/// is how "0.00" came to be a day's value on screen. One formatter is the
/// point: a second is a second answer, and the second answer is the one that
/// gets it wrong.
String money(Object? amount, Session? session, {bool symbol = true}) {
  if (amount == null || amount.toString().trim().isEmpty) return '—';
  final text = amount.toString().trim();
  final org = session?.organization;
  if (org == null) return text;
  return symbol && org.currencySymbol.isNotEmpty
      ? '${org.currencySymbol}$text'
      : '$text ${org.currencyCode}';
}

/// A percentage as a dairy says it: one decimal and the sign.
String percent(Object? value) {
  final number = _asNumber(value);
  return number == null ? '—' : '${number.toStringAsFixed(1)}%';
}

/// A whole count. Separate from `quantity` because a farmer is not 24.0.
String count(Object? value) {
  final number = _asNumber(value);
  return number == null ? '—' : number.round().toString();
}

double? _asNumber(Object? value) {
  if (value == null) return null;
  if (value is num) return value.toDouble();
  final text = value.toString().trim();
  if (text.isEmpty || text == '—') return null;
  return double.tryParse(text);
}
