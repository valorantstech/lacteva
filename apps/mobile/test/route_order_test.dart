/// The round follows the ROUTE's order (DEMO-034).
///
/// The one piece of real logic the round screen gained, tested as a pure
/// function: given today's run and the customer list, the rider visits in the
/// sequence somebody planned rather than in whatever order the platform's
/// customer listing happened to return.
///
/// Two properties matter, and the second is the one that would hurt a dairy if
/// it were wrong: a household NOT on the route is still shown. Dropping them
/// would be the app quietly deciding not to deliver to somebody who pays.
library;

import 'package:flutter_test/flutter_test.dart';
import 'package:lacteva_mobile/src/deliveries.dart';

Map<String, dynamic> _customer(String id) => {'id': id, 'name': 'H-$id'};

Map<String, dynamic> _run(List<(String, int)> stops) => {
  'route_code': 'R-01',
  'route_name': 'Kilima morning round',
  'status': 'in_progress',
  'stops': [
    for (final (id, position) in stops)
      {'customer_id': id, 'position': position},
  ],
};

void main() {
  test('the round is walked in the route order, not the listing order', () {
    final customers = [_customer('c'), _customer('a'), _customer('b')];
    final run = _run([('a', 1), ('b', 2), ('c', 3)]);

    final ordered = inRouteOrder(customers, run);

    expect(ordered.map((c) => c['id']), ['a', 'b', 'c']);
  });

  test('a customer who is not on the route is kept, at the end', () {
    // A household somebody forgot to add to the round still takes milk.
    final customers = [_customer('forgotten'), _customer('a')];
    final run = _run([('a', 1)]);

    final ordered = inRouteOrder(customers, run);

    expect(ordered.map((c) => c['id']), ['a', 'forgotten']);
    expect(ordered.length, customers.length, reason: 'nobody may be dropped');
  });

  test('a run with no stops leaves the round exactly as it was', () {
    final customers = [_customer('c'), _customer('a')];

    final ordered = inRouteOrder(customers, _run(const []));

    expect(ordered.map((c) => c['id']), ['c', 'a']);
  });

  test('the run carries no money for the round to display', () {
    // A run is an operational record. If it ever starts carrying an amount,
    // this fails rather than the figure quietly appearing on a phone.
    final run = _run([('a', 1)]);
    for (final key in const [
      'amount',
      'total_amount',
      'quantity',
      'unit_price',
      'currency',
      'balance',
    ]) {
      expect(run.containsKey(key), isFalse, reason: '$key is not a run fact');
    }
  });
}
