/// P0-PILOT-004: the first real handset run crashed the centres list on a
/// null `timezone` — nullable BY DESIGN (DEMO-014: a centre without its own
/// timezone inherits the organization's). Every fixture had obligingly set
/// one, so only real data could find it. This test keeps the defect dead.
library;

import 'package:flutter_test/flutter_test.dart';
import 'package:lacteva_mobile/src/api.dart';

void main() {
  test('a centre inheriting the org timezone (null) parses', () {
    final page = CenterPage.fromJson({
      'items': [
        {
          'id': 'c1',
          'branch_id': 'b1',
          'name': 'Devanahalli Collection Centre',
          'code': 'DV-C1',
          'status': 'active',
          'timezone': null,
        },
        {
          'id': 'c2',
          'branch_id': 'b1',
          'name': 'Kilima Hill',
          'code': 'KH-C1',
          'status': 'active',
          'timezone': 'Africa/Nairobi',
        },
      ],
      'total': 2,
    });
    expect(page.items.first.timezone, isNull);
    expect(page.items.last.timezone, 'Africa/Nairobi');
  });
}
