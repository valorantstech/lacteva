/// Who is signed in, and what they are allowed to do (DEMO-012).
///
/// The app used to send everyone to the collection-centre list after login,
/// whoever they were. A household opening the customer app landed on a screen
/// listing the dairy's collection centres and got a wall of 403s — the
/// platform refused correctly, and the app had promised something it could not
/// deliver.
///
/// So the mobile client asks the platform who it is talking to and lets the
/// answer decide. THE ROLE IS NEVER INFERRED FROM WHAT THE USER TYPED, and
/// never stored on the device as a preference: it is read from
/// `GET /v1/auth/me` on every sign-in, which is the same source the web portal
/// uses and the same source the API enforces against.
///
/// A permission list is a PROMISE. Offering a screen the platform will refuse
/// breaks it, which is why every destination below is gated on the capability
/// it actually needs rather than on a role name.
library;

import 'api.dart';

/// The signed-in identity, exactly as the platform describes it.
class Session {
  const Session({
    required this.userId,
    required this.email,
    required this.fullName,
    required this.tenantId,
    required this.permissions,
    this.customerId,
  });

  final String userId;
  final String email;
  final String fullName;

  /// The organization this token is bound to. Null for a platform operator,
  /// who has no business in the field app.
  final String? tenantId;

  /// The grants the PLATFORM says this principal holds. Never edited locally.
  final Set<String> permissions;

  /// DEMO-012 — set when this login speaks for exactly one customer.
  ///
  /// The platform narrows every sales query to it server-side; the app reads
  /// it only to decide which experience to show. It is not a security control
  /// here, and must not be treated as one: removing this field would change
  /// which screen opens, never what the platform returns.
  final String? customerId;

  bool get isCustomer => customerId != null;

  /// Wildcard included, because the platform's own registry uses it for
  /// platform administrators and a client that ignored it would hide
  /// everything from the one principal who may see it all.
  bool can(String permission) =>
      permissions.contains('*') || permissions.contains(permission);

  bool canAny(Iterable<String> any) => any.any(can);

  static Session fromJson(Map<String, dynamic> json) {
    final raw = json['permissions'];
    return Session(
      userId: (json['id'] ?? '').toString(),
      email: (json['email'] ?? '').toString(),
      fullName: (json['full_name'] ?? '').toString(),
      tenantId: json['tenant_id']?.toString(),
      customerId: json['customer_id']?.toString(),
      permissions: raw is List
          ? raw.map((e) => e.toString()).toSet()
          : const <String>{},
    );
  }
}

/// Which experience this session opens on.
///
/// Deliberately derived from CAPABILITIES, not from a role name. DEMO-008 made
/// roles rows in a database that an administrator can edit; a client that
/// switched on `role == 'COLLECTION_OPERATOR'` would be wrong the moment
/// somebody made a new role with the same job, which is precisely the thing
/// the registry exists to allow.
enum Experience {
  /// A household: their deliveries, their bill, their balance.
  customer,

  /// The delivery round: today's schedule, record what was dropped.
  delivery,

  /// The collection centre: suppliers, weights, quality, pricing.
  collection,

  /// Signed in, but holding nothing this app can offer.
  none,
}

/// Choose the landing experience.
///
/// Order matters and encodes a real judgement:
///
/// 1. A customer-scoped login is a customer, whatever else it holds. The
///    scope is the narrower fact and the platform will enforce it regardless,
///    so showing anything else would be a screen full of somebody else's data
///    that never loads.
/// 2. Otherwise, if they can record a delivery, the round is their job.
/// 3. Otherwise, if they can run a collection session, the centre is.
/// 4. A user with read-only sales access — a manager checking the day — gets
///    the delivery experience, which is read-first anyway; the record button
///    is hidden by its own permission check.
Experience experienceFor(Session session) {
  if (session.isCustomer) return Experience.customer;
  if (session.can('sales.delivery.record')) return Experience.delivery;
  if (session.can('collection.session.manage')) return Experience.collection;
  if (session.can('sales.delivery.read')) return Experience.delivery;
  if (session.can('collection.transaction.read')) return Experience.collection;
  return Experience.none;
}

/// Fetch the identity the platform believes it is talking to.
Future<Session> loadSession(ApiClient client) async {
  final me = await client.me();
  return Session.fromJson(me);
}
