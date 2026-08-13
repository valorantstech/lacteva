/// Which experience a sign-in opens, and why (DEMO-012 §2, §12).
///
/// The app used to send everyone to the collection-centre list. A household
/// signing in landed on a screen listing the dairy's centres and got a wall of
/// 403s — the platform refused correctly and the app had promised something it
/// could not deliver.
///
/// These tests are about the promise. A menu is a promise, and offering a
/// screen the platform will refuse breaks it, so the routing is asserted
/// against CAPABILITIES rather than role names: DEMO-008 made roles editable
/// rows, and a client that switched on `role == 'COLLECTION_OPERATOR'` would
/// be wrong the moment an administrator created a role doing the same job
/// under a different name.
library;

import 'package:flutter_test/flutter_test.dart';
import 'package:lacteva_mobile/src/session.dart';

Session _session({
  Set<String> permissions = const {},
  String? customerId,
  String? tenantId = 'org-1',
}) => Session(
  userId: 'u1',
  email: 'someone@dairy.example',
  fullName: 'Someone',
  tenantId: tenantId,
  permissions: permissions,
  customerId: customerId,
);

void main() {
  group('the experience follows the permissions', () {
    test('a collection operator opens the centre', () {
      final s = _session(
        permissions: {'collection.session.manage', 'supplier.read'},
      );
      expect(experienceFor(s), Experience.collection);
    });

    test('someone who records deliveries opens the round', () {
      final s = _session(
        permissions: {'sales.delivery.record', 'sales.customer.read'},
      );
      expect(experienceFor(s), Experience.delivery);
    });

    test('a customer-scoped login opens their own account', () {
      final s = _session(
        permissions: {'sales.invoice.read', 'sales.delivery.read'},
        customerId: 'cus-1',
      );
      expect(experienceFor(s), Experience.customer);
    });

    test('a customer scope wins over every other capability', () {
      // The scope is the narrower fact and the platform enforces it whatever
      // the app does, so any other experience would be a screen that never
      // loads anybody else's data.
      final s = _session(
        permissions: {
          'sales.delivery.record',
          'collection.session.manage',
          '*',
        },
        customerId: 'cus-1',
      );
      expect(experienceFor(s), Experience.customer);
    });

    test('a read-only sales manager gets the round, not a dead end', () {
      final s = _session(permissions: {'sales.delivery.read'});
      expect(experienceFor(s), Experience.delivery);
    });

    test('an account with nothing this app offers gets an honest dead end', () {
      // A finance officer's grants are real and useful — in the web portal.
      final s = _session(
        permissions: {'payment.read', 'settlement.read', 'reporting.read'},
      );
      expect(experienceFor(s), Experience.none);
    });

    test('a platform administrator is not locked out by the wildcard', () {
      final s = _session(permissions: {'*'});
      expect(experienceFor(s), isNot(Experience.none));
    });
  });

  group('permissions come from the platform, never from the client', () {
    test('parses exactly what /v1/auth/me returned', () {
      final s = Session.fromJson({
        'id': 'u9',
        'email': 'rider@dairy.example',
        'full_name': 'Rider',
        'tenant_id': 'org-7',
        'customer_id': null,
        'permissions': ['sales.delivery.record', 'sales.customer.read'],
      });
      expect(s.can('sales.delivery.record'), isTrue);
      expect(s.can('sales.invoice.issue'), isFalse);
      expect(s.isCustomer, isFalse);
      expect(s.tenantId, 'org-7');
    });

    test('a missing permission list grants nothing', () {
      // A malformed or truncated response must not open doors.
      final s = Session.fromJson({'id': 'u1', 'email': 'x@y.example'});
      expect(s.permissions, isEmpty);
      expect(s.can('sales.delivery.record'), isFalse);
      expect(experienceFor(s), Experience.none);
    });

    test('the wildcard is honoured, because the registry uses it', () {
      final s = Session.fromJson({
        'id': 'u1',
        'email': 'root@lacteva.example',
        'permissions': ['*'],
      });
      expect(s.can('anything.at.all'), isTrue);
    });

    test('a customer scope is read from the account, not inferred', () {
      final s = Session.fromJson({
        'id': 'u2',
        'email': 'household@dairy.example',
        'tenant_id': 'org-7',
        'customer_id': 'cus-42',
        'permissions': ['sales.invoice.read'],
      });
      expect(s.isCustomer, isTrue);
      expect(s.customerId, 'cus-42');
    });
  });
}
