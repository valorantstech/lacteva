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
    this.locale = 'en',
    this.organization,
    this.organizationId,
    this.membershipStatus,
    this.roleNames = const <String>[],
    this.centerScope,
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

  /// DEMO-013 — the language THIS PERSON chose, as a BCP-47 tag.
  ///
  /// From their account, not from the handset: a phone left in the wrong
  /// language, or lent to a colleague, must not decide what a dairy's staff
  /// read. The organization decides which languages exist; this is the one
  /// they picked from that list.
  final String locale;

  /// DEMO-013 — the organization's money, clock and languages.
  ///
  /// Carried on the session rather than fetched separately, which is what
  /// makes it available offline: the app already caches the session, and a
  /// rider in a valley still has to see amounts and dates.
  final OrgLocale? organization;

  /// The organization's id, distinct from `tenantId` only in that the platform
  /// nests it under `organization` — they are the same value.
  final String? organizationId;

  /// `active`, `suspended`, … as the platform reports it. Carried so the app
  /// can say something true when a member has been suspended, rather than
  /// showing a wall of refusals.
  final String? membershipStatus;

  /// Role names, for DISPLAY AND DIAGNOSTICS ONLY (DEMO-013 §4).
  ///
  /// **Nothing in this app may branch on them.** DEMO-008 made roles editable
  /// rows, so a client that switched on a role name would be wrong the moment
  /// an administrator created a role doing the same job under another name.
  /// `permissions` is the authority; this exists so a support call can ask
  /// "what does it say you are?".
  final List<String> roleNames;

  /// The centres this principal may act at, or null for the whole
  /// organization. A centre-scoped operator must not be offered another
  /// centre's work.
  final List<String>? centerScope;

  bool get isCustomer => customerId != null;

  /// May this principal act at this centre? Null scope means everywhere.
  bool coversCenter(String centerId) =>
      centerScope == null || centerScope!.contains(centerId);

  /// Wildcard included, because the platform's own registry uses it for
  /// platform administrators and a client that ignored it would hide
  /// everything from the one principal who may see it all.
  bool can(String permission) =>
      permissions.contains('*') || permissions.contains(permission);

  bool canAny(Iterable<String> any) => any.any(can);

  static Session fromJson(Map<String, dynamic> json) {
    final raw = json['permissions'];
    // `/v1/auth/me` nests the person under `user` and keeps permissions,
    // tenant and customer at the top level. DEMO-012 read `id`/`email` from
    // the top level, where they are not — so the signed-in address rendered
    // blank on the dead-end screen and in the push-device label. Both shapes
    // are accepted because the unit tests construct the flat one directly.
    final user = json['user'] is Map
        ? (json['user'] as Map).cast<String, dynamic>()
        : json;
    final org = json['organization'] is Map
        ? OrgLocale.fromJson(
            (json['organization'] as Map).cast<String, dynamic>(),
          )
        : null;
    final orgJson = json['organization'] is Map
        ? (json['organization'] as Map).cast<String, dynamic>()
        : const <String, dynamic>{};
    final membership = json['membership'] is Map
        ? (json['membership'] as Map).cast<String, dynamic>()
        : const <String, dynamic>{};
    final roles = json['roles'] is List ? json['roles'] as List : const [];
    final scope = json['center_scope'];
    return Session(
      userId: (user['id'] ?? json['id'] ?? '').toString(),
      email: (user['email'] ?? json['email'] ?? '').toString(),
      fullName: (user['full_name'] ?? json['full_name'] ?? '').toString(),
      tenantId: json['tenant_id']?.toString(),
      customerId: json['customer_id']?.toString(),
      locale: (user['locale'] ?? json['locale'] ?? 'en').toString(),
      organization: org,
      organizationId: orgJson['id']?.toString(),
      membershipStatus: membership['status']?.toString(),
      roleNames: roles
          .map((r) => r is Map ? (r['name'] ?? '').toString() : r.toString())
          .where((name) => name.isNotEmpty)
          .toList(),
      // Null and empty are DIFFERENT: null is "the whole organization",
      // an empty list would be "no centre at all".
      centerScope: scope is List
          ? scope.map((e) => e.toString()).toList()
          : null,
      permissions: raw is List
          ? raw.map((e) => e.toString()).toSet()
          : const <String>{},
    );
  }
}

/// The organization's locale context, exactly as the platform describes it
/// (DEMO-013 §13).
///
/// The app holds NO country configuration of its own. There is no map from
/// India to rupees in this codebase — the platform resolved that when the
/// dairy was onboarded, and a second copy here would be a second answer that
/// disagrees the first time somebody changes a setting.
class OrgLocale {
  const OrgLocale({
    required this.name,
    required this.countryCode,
    required this.currencyCode,
    required this.currencySymbol,
    required this.timezone,
    required this.defaultLanguage,
    required this.supportedLanguages,
    this.quantityUnit = 'kg',
    this.quantityUnitLabel = 'kg',
    this.tradeUnit,
    this.tradeUnitLabel,
    this.conversionFactor,
  });

  final String name;
  final String countryCode;
  final String currencyCode;
  final String currencySymbol;

  /// IANA. Authoritative for what "today" means to this dairy — never the
  /// handset's zone, which changes when a rider crosses a border.
  final String timezone;
  final String defaultLanguage;
  final List<String> supportedLanguages;

  /// D-21 / WO-70. What this dairy MEASURES intake in — `litre` or `kg` —
  /// and the symbol a person reads (`L`, `kg`). From the platform, like the
  /// currency: there is no map from India to litres in this app, and the
  /// handset's home used to say "L" over a kilogram total because it assumed.
  /// The defaults are `kg` for one reason only: a platform from before WO-70
  /// measured everything in kilograms, so a session it describes was weighed.
  final String quantityUnit;
  final String quantityUnitLabel;

  /// Ruling 3: null in the ordinary case. When set, the dairy PAYS in this
  /// unit at the declared kg-per-litre factor, and every figure shows both.
  final String? tradeUnit;
  final String? tradeUnitLabel;
  final String? conversionFactor;

  static OrgLocale fromJson(Map<String, dynamic> json) => OrgLocale(
    name: (json['name'] ?? '').toString(),
    countryCode: (json['country_code'] ?? '').toString(),
    currencyCode: (json['currency_code'] ?? '').toString(),
    currencySymbol: (json['currency_symbol'] ?? '').toString(),
    timezone: (json['timezone'] ?? 'UTC').toString(),
    defaultLanguage: (json['default_language'] ?? 'en').toString(),
    supportedLanguages:
        (json['supported_languages'] as List?)
            ?.map((e) => e.toString())
            .toList() ??
        const ['en'],
    quantityUnit: (json['quantity_unit'] ?? 'kg').toString(),
    quantityUnitLabel: (json['quantity_unit_label'] ?? 'kg').toString(),
    tradeUnit: json['trade_unit']?.toString(),
    tradeUnitLabel: json['trade_unit_label']?.toString(),
    conversionFactor: json['conversion_factor']?.toString(),
  );

  Map<String, dynamic> toJson() => {
    'name': name,
    'country_code': countryCode,
    'currency_code': currencyCode,
    'currency_symbol': currencySymbol,
    'timezone': timezone,
    'default_language': defaultLanguage,
    'supported_languages': supportedLanguages,
    'quantity_unit': quantityUnit,
    'quantity_unit_label': quantityUnitLabel,
    'trade_unit': tradeUnit,
    'trade_unit_label': tradeUnitLabel,
    'conversion_factor': conversionFactor,
  };
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

  /// A delivery DRIVER: their own assigned runs, and nothing else
  /// (P0-MOB-001). Deliberately keyed on `logistics.run.execute` — its own
  /// grant, held only by the DRIVER role — and checked BEFORE the operator
  /// keys below, because the collection-hardware audit found the delivery
  /// experience keyed on the sales grant, which would have collapsed driver
  /// and operator into one persona.
  driver,

  /// The delivery round: today's schedule, record what was dropped.
  delivery,

  /// The collection centre: suppliers, weights, quality, pricing.
  collection,

  /// Signed in, but holding nothing this app can offer.
  none,
}

/// Does this person's remit cover the WHOLE dairy rather than one job in it?
///
/// The two grants are the two halves of the business: running a collection
/// session is the procurement side, recording a delivery is the sales side.
/// A person trusted with both is not doing either job — they are running the
/// place, and every role that holds both is an organisation-wide one
/// (`tenant-admin`, `ORGANIZATION_MANAGER`, `ORGANIZATION_ADMIN`), while
/// every single-purpose role holds exactly one (`SALES_OFFICER` the sales
/// half, `COLLECTION_OPERATOR` and `CENTRE_MANAGER` the procurement half).
///
/// Expressed as capabilities and never as a role NAME, which is the house
/// rule and not a preference: role names are rows in a database that a
/// deployment may rename or compose differently, and a screen that branched
/// on one would be deciding what somebody is allowed to see from a label
/// rather than from a grant (`test_experience.dart` asserts a role named
/// anything at all changes nothing).
bool _runsTheWholeDairy(Session session) =>
    session.can('collection.session.manage') && session.can('sales.delivery.record');

/// Choose the landing experience.
///
/// Order matters and encodes a real judgement:
///
/// 1. A customer-scoped login is a customer, whatever else it holds. The
///    scope is the narrower fact and the platform will enforce it regardless,
///    so showing anything else would be a screen full of somebody else's data
///    that never loads.
/// 2. A driver's whole job is the run they are on.
/// 3. WHOEVER RUNS THE DAIRY LANDS ON THE MANAGER HOME (WO-64). This test
///    comes before the single-capability ones and it is the fix for a real
///    defect: the checks below return the FIRST capability that matches, and
///    `sales.delivery.record` was tested before `collection.session.manage`,
///    so a tenant-admin — who holds everything — landed on the delivery
///    round. The owner of the dairy opened the product he had bought and was
///    shown a delivery van's worklist, with the manager home built in cycle 3
///    unreachable from it. Found on a real handset, not by reading this file.
///
///    Routing by INTENT rather than by first match is the difference: for a
///    person with one job the capability IS the intent, and steps 4-7 are
///    right for them and unchanged; for a person with authority over both
///    halves it is not, and the round and the counter become places they
///    navigate to rather than where they are put.
/// 4. Otherwise, if they can record a delivery, the round is their job.
/// 5. Otherwise, if they can run a collection session, the centre is.
/// 6. A user with read-only sales access — a manager checking the day — gets
///    the delivery experience, which is read-first anyway; the record button
///    is hidden by its own permission check.
Experience experienceFor(Session session) {
  if (session.isCustomer) return Experience.customer;
  if (session.can('logistics.run.execute')) return Experience.driver;
  if (_runsTheWholeDairy(session)) return Experience.collection;
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
