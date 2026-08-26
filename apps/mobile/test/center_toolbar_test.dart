/// The centre toolbar offers only what the session can actually open
/// (LACTEVA-MOBILE-002; handset finding D-2).
///
/// The second full handset run put a COLLECTION_OPERATOR in front of two
/// icons — "Today's summary" and the pricing resolution test — whose screens
/// could only ever refuse them, because that role holds neither
/// `reporting.read` nor `pricing.ratecard.read`. The platform's refusal was
/// correct both times; the toolbar was the defect.
///
/// What is pinned here:
///   1. the operator persona sees NEITHER icon;
///   2. a manager persona holding both grants sees BOTH;
///   3. nothing else on the toolbar moves for either — the fix hides two
///      actions, it does not rebuild the bar.
///
/// Capability only, never a role name: the personas below are named for
/// readability but are defined purely by the grants they carry, which is what
/// the widget actually asks.
library;

import 'package:flutter/material.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:lacteva_mobile/src/api.dart';
import 'package:lacteva_mobile/src/centers.dart';
import 'package:lacteva_mobile/src/session.dart';

class _Fake extends ApiClient {
  @override
  Future<CenterDetail> centerDetail(String id) async => CenterDetail.fromJson({
    'center': {
      'id': id,
      'branch_id': 'b1',
      'name': 'Village Centre',
      'code': 'VC-1',
      'status': 'active',
      'timezone': null,
    },
    'settings': {},
    'operating_windows': [],
    'calendar': [],
  });

  @override
  Future<List<Map<String, dynamic>>> listOpenSessions(String centerId) async =>
      const [];
}

Session _session(Set<String> permissions) => Session(
  userId: 'u1',
  email: 'someone@dairy.example',
  fullName: 'Someone',
  tenantId: 'org-1',
  permissions: permissions,
);

/// COLLECTION_OPERATOR's real grants, copied from the platform's own registry
/// (`modules/authz/permissions.py`). Neither gated permission is among them —
/// which is correct, and is exactly why the icons must not be offered.
final _operator = _session({
  'collection.center.read',
  'operations.readiness.read',
  'supplier.read',
  'collection.session.manage',
  'collection.transaction.record',
  'collection.transaction.read',
});

/// Someone who can actually open both screens.
final _manager = _session({
  'collection.center.read',
  'operations.readiness.read',
  'reporting.read',
  'pricing.ratecard.read',
});

Future<void> _pump(WidgetTester tester, Session? session) async {
  await tester.pumpWidget(
    MaterialApp(
      home: CenterDetailScreen(
        client: _Fake(),
        centerId: 'c1',
        session: session,
      ),
    ),
  );
  await tester.pumpAndSettle();
}

void main() {
  testWidgets('the operator is offered neither door that would slam', (
    tester,
  ) async {
    await _pump(tester, _operator);

    expect(find.byTooltip("Today's summary"), findsNothing);
    expect(find.byTooltip('Pricing resolution test'), findsNothing);
  });

  testWidgets('a session holding both grants sees both', (tester) async {
    await _pump(tester, _manager);

    expect(find.byTooltip("Today's summary"), findsOneWidget);
    expect(find.byTooltip('Pricing resolution test'), findsOneWidget);
  });

  testWidgets('nothing else on the toolbar moves', (tester) async {
    // The three ungated actions — history, end-of-shift close, and capture —
    // plus readiness, which COLLECTION_OPERATOR genuinely holds. If hiding two
    // icons cost the operator any of these, the fix would have taken more than
    // it gave.
    for (final session in [_operator, _manager]) {
      await _pump(tester, session);
      expect(find.byTooltip('Collections'), findsOneWidget);
      expect(find.byTooltip('Close session'), findsOneWidget);
      expect(find.byTooltip('Collect milk'), findsOneWidget);
      expect(find.byTooltip('Operational readiness'), findsOneWidget);
    }
  });

  testWidgets('an unknown principal is treated as one who cannot', (
    tester,
  ) async {
    // `session` is nullable on this screen (it arrived for language alone).
    // A screen that would refuse anyway is not worth a door.
    await _pump(tester, null);

    expect(find.byTooltip("Today's summary"), findsNothing);
    expect(find.byTooltip('Pricing resolution test'), findsNothing);
  });
}
