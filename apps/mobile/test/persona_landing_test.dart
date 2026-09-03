/// Where each persona LANDS (WO-64 · LACTEVA-MOBILE-011).
///
/// The architect installed a build on a moto g57 and signed in as all five
/// India demo logins. Four of the five landed on the same screen: the
/// delivery round. `experienceFor` returned the first capability that
/// matched, and `sales.delivery.record` was tested before
/// `collection.session.manage` — so a tenant-admin, who holds everything,
/// was shown a delivery van's worklist. The dairy OWNER opened the product he
/// had bought and could not reach the manager home built for him in cycle 3.
///
/// A screen nobody can get to is a screen that does not exist, and this was
/// found on glass rather than in the file — so the guard belongs here, at the
/// grain the defect had: one assertion per persona, naming the screen.
///
/// THE GRANTS BELOW ARE THE PLATFORM'S OWN, copied from
/// `modules/authz/permissions.py`, narrowed to the five that routing reads.
/// Copied rather than imported because Dart cannot read Python — so the risk
/// is that they drift, and `test_persona_grants_match_the_platform` on the
/// backend side asserts they have not.
library;

import 'package:flutter_test/flutter_test.dart';
import 'package:lacteva_mobile/src/session.dart';

/// Exactly the grants `experienceFor` consults, per role.
const personaGrants = <String, Set<String>>{
  'tenant-admin': {
    'collection.session.manage',
    'collection.transaction.read',
    'sales.delivery.read',
    'sales.delivery.record',
  },
  'ORGANIZATION_MANAGER': {
    'collection.session.manage',
    'collection.transaction.read',
    'sales.delivery.read',
    'sales.delivery.record',
  },
  'SALES_OFFICER': {'sales.delivery.read', 'sales.delivery.record'},
  'COLLECTION_OPERATOR': {'collection.session.manage', 'collection.transaction.read'},
  'CENTRE_MANAGER': {'collection.session.manage', 'collection.transaction.read'},
  'tenant-viewer': {'collection.transaction.read', 'sales.delivery.read'},
  'FINANCE_OFFICER': {'collection.transaction.read', 'sales.delivery.read'},
  'DRIVER': {'logistics.run.execute'},
  'ORGANIZATION_ADMIN': {
    'collection.session.manage',
    'collection.transaction.read',
    'sales.delivery.read',
    'sales.delivery.record',
  },
  'FINANCE_MANAGER': {'collection.transaction.read', 'sales.delivery.read'},
  'AUDITOR': {'collection.transaction.read', 'sales.delivery.read'},
  'CUSTOMER_PORTAL': {'sales.delivery.read'},
  // The wildcard roles. They hold every grant, including the driver's, and
  // the driver check comes first — so Lacteva staff signing in on a handset
  // land on a run. That is not a decision anyone made; it is what holding
  // everything means when the router tests the narrowest job first, and the
  // mobile app has no acting-tenant selector, so a platform session has no
  // dairy to show either way. Recorded here rather than silently routed:
  // this is the honest description of what happens today (see the note in
  // the test below).
  'platform-admin': {
    'collection.session.manage',
    'collection.transaction.read',
    'logistics.run.execute',
    'sales.delivery.read',
    'sales.delivery.record',
  },
  'PLATFORM_SUPER_ADMIN': {
    'collection.session.manage',
    'collection.transaction.read',
    'logistics.run.execute',
    'sales.delivery.read',
    'sales.delivery.record',
  },
};

/// What each of them must OPEN, and the reason in one line.
const expected = <String, (Experience, String)>{
  // WO-64: the defect. Holds everything, so first-match sent him to the round.
  'tenant-admin': (Experience.manager, 'the owner runs the dairy, not a van'),
  'ORGANIZATION_MANAGER': (Experience.manager, 'organisation-wide authority'),
  // Single-purpose roles: the capability IS the intent, and this was already
  // right. The work order says so explicitly — do not "fix" these.
  'SALES_OFFICER': (Experience.delivery, 'the round is the whole job'),
  'COLLECTION_OPERATOR': (Experience.collection, 'the counter is the whole job'),
  'CENTRE_MANAGER': (Experience.collection, 'one centre, procurement side'),
  // Read-only personas land on the round with the controls ABSENT, which the
  // on-glass review called the permission model working beautifully. Absent,
  // never disabled — a greyed-out button teases a capability (WO-51b).
  'tenant-viewer': (Experience.delivery, 'read-only, and correct as it stands'),
  'FINANCE_OFFICER': (Experience.delivery, 'reads the round; works in the portal'),
  'DRIVER': (Experience.driver, 'the run they are on'),
  'ORGANIZATION_ADMIN': (Experience.manager, 'organisation-wide authority'),
  // Read-only finance and audit personas: the round reads first, and their
  // real tool is the portal.
  'FINANCE_MANAGER': (Experience.delivery, 'reads the round; works in the portal'),
  'AUDITOR': (Experience.delivery, 'reads everything, changes nothing'),
  'CUSTOMER_PORTAL': (Experience.delivery, 'a household login is scoped by its account'),
  // Lacteva staff. The driver grant is in the wildcard, and the driver check
  // is first, so this is where they land — stated rather than pretended.
  'platform-admin': (Experience.driver, 'holds every grant, including the driver run'),
  'PLATFORM_SUPER_ADMIN': (Experience.driver, 'holds every grant, including the driver run'),
};

Session _as(String role, {String? customerId}) => Session(
  userId: 'u1',
  email: '$role@dairy.example',
  fullName: 'Persona',
  tenantId: 'org-1',
  permissions: personaGrants[role]!,
  customerId: customerId,
);

void main() {
  group('every persona lands where its job is', () {
    for (final role in personaGrants.keys) {
      final (screen, why) = expected[role]!;
      test('$role opens ${screen.name} — $why', () {
        expect(experienceFor(_as(role)), screen);
      });
    }
  });

  test('the owner reaches the manager home, which is the defect this fixes', () {
    // Stated separately from the table because it is the finding, not a row:
    // four of five personas landed on the delivery round, and this is the one
    // that was wrong.
    // WO-72 Part C: the manager home is now its own experience, not the
    // counter's screen worn by the owner.
    expect(experienceFor(_as('tenant-admin')), Experience.manager);
    expect(experienceFor(_as('tenant-admin')), isNot(Experience.delivery));
    expect(experienceFor(_as('tenant-admin')), isNot(Experience.collection));
  });

  test('what routes them is the two halves of the business, not a role name', () {
    // The rule is "holds authority over procurement AND sales". A role named
    // anything at all with those two grants gets the manager home; a role
    // named `tenant-admin` without them does not.
    final invented = Session(
      userId: 'u2',
      email: 'someone@dairy.example',
      fullName: 'Someone',
      tenantId: 'org-1',
      permissions: const {'collection.session.manage', 'sales.delivery.record'},
      customerId: null,
    );
    expect(experienceFor(invented), Experience.manager);

    final halfOnly = Session(
      userId: 'u3',
      email: 'someone@dairy.example',
      fullName: 'Someone',
      tenantId: 'org-1',
      permissions: const {'sales.delivery.record'},
      customerId: null,
    );
    expect(experienceFor(halfOnly), Experience.delivery);
  });

  test('a customer-scoped login is a customer whatever else it holds', () {
    // The narrower fact wins, and it wins over the new rule too.
    expect(experienceFor(_as('tenant-admin', customerId: 'c1')), Experience.customer);
  });

  test('a driver stays a driver even when they also run the dairy', () {
    final s = Session(
      userId: 'u4',
      email: 'driver@dairy.example',
      fullName: 'Driver',
      tenantId: 'org-1',
      permissions: const {
        'logistics.run.execute',
        'collection.session.manage',
        'sales.delivery.record',
      },
      customerId: null,
    );
    // A person on a run is on a run; the board is where they go afterwards.
    expect(experienceFor(s), Experience.driver);
  });
}
