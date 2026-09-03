/// Where every screen lives (WO-72 Part B · D-23 pin 10).
///
/// Thirty-three screens were reachable and three were advertised: settlements,
/// payments, rate cards, receipts, matrices, notifications and readiness were
/// all built, all tested, and findable only by guessing which tile to drill
/// into. There was no navigation of any kind — no bar, no drawer, no tabs.
///
/// This file IS the map, in code that a test reads rather than a comment that
/// rots: every `*Screen` class in `lib/src` must have a home under a tab in
/// [screenHomes], or be listed in [preAuthScreens]. Add a screen without a
/// home and `navigation_test.dart` fails.
///
/// **Capability-driven, never role-named.** A tab is declared with the grants
/// its destinations need; a session that holds none of a tab's grants does
/// not see the tab. Shapes differ by EXPERIENCE (which `session.dart` derives
/// from capabilities), not by role strings — the house rule, unchanged.
library;

import 'package:flutter/material.dart';

import 'session.dart';

/// One tab in the bottom bar.
class NavTab {
  const NavTab({
    required this.key,
    required this.labelKey,
    required this.icon,
    required this.selectedIcon,
    required this.anyOf,
  });

  /// Stable identity; also the `data-testid` of a kind for tests.
  final String key;

  /// Catalog key for the label (`nav.today`, …).
  final String labelKey;
  final IconData icon;
  final IconData selectedIcon;

  /// The grants that make this tab worth showing — ANY one suffices. Empty
  /// means "everyone signed in" (sign-out and sync live there).
  final Set<String> anyOf;

  bool visibleFor(Session session) => anyOf.isEmpty || session.canAny(anyOf);
}

/// The bar, per experience — exactly as the design review drew it.
///
/// `manager` is the shape for a session that runs the whole dairy
/// ([runsTheWholeDairy]); until Part C gives it its own [Experience] it still
/// routes to the collection experience, and the bar is shaped here.
enum BarShape { manager, operator, driver, customer }

BarShape shapeFor(Session session) {
  switch (experienceFor(session)) {
    case Experience.customer:
      return BarShape.customer;
    case Experience.driver:
      return BarShape.driver;
    case Experience.delivery:
      // A sales officer works the round; the driver bar is the round's bar.
      return BarShape.driver;
    case Experience.manager:
      return BarShape.manager;
    case Experience.collection:
      return runsTheWholeDairy(session) ? BarShape.manager : BarShape.operator;
    case Experience.none:
      return BarShape.operator; // nothing renders: every tab is gated
  }
}

const _money = {
  'settlement.read',
  'payment.read',
  'receipt.read',
  'pricing.ratecard.read',
};
const _reports = {'reporting.read', 'notification.read'};
const _more = <String>{};

const List<NavTab> managerTabs = [
  NavTab(
    key: 'today',
    labelKey: 'nav.today',
    icon: Icons.wb_sunny_outlined,
    selectedIcon: Icons.wb_sunny,
    anyOf: {'collection.session.manage', 'collection.transaction.read', 'reporting.read'},
  ),
  NavTab(
    key: 'farmers',
    labelKey: 'nav.farmers',
    icon: Icons.groups_outlined,
    selectedIcon: Icons.groups,
    anyOf: {'supplier.read'},
  ),
  NavTab(
    key: 'money',
    labelKey: 'nav.money',
    icon: Icons.account_balance_wallet_outlined,
    selectedIcon: Icons.account_balance_wallet,
    anyOf: _money,
  ),
  NavTab(
    key: 'reports',
    labelKey: 'nav.reports',
    icon: Icons.bar_chart_outlined,
    selectedIcon: Icons.bar_chart,
    anyOf: _reports,
  ),
  NavTab(
    key: 'more',
    labelKey: 'nav.more',
    icon: Icons.more_horiz,
    selectedIcon: Icons.more_horiz,
    anyOf: _more,
  ),
];

const List<NavTab> operatorTabs = [
  NavTab(
    key: 'collect',
    labelKey: 'nav.collect',
    icon: Icons.water_drop_outlined,
    selectedIcon: Icons.water_drop,
    anyOf: {'collection.session.manage', 'collection.transaction.record'},
  ),
  NavTab(
    key: 'today',
    labelKey: 'nav.today',
    icon: Icons.wb_sunny_outlined,
    selectedIcon: Icons.wb_sunny,
    anyOf: {'reporting.read', 'collection.transaction.read', 'receipt.read'},
  ),
  NavTab(
    key: 'farmers',
    labelKey: 'nav.farmers',
    icon: Icons.groups_outlined,
    selectedIcon: Icons.groups,
    anyOf: {'supplier.read'},
  ),
  NavTab(
    key: 'more',
    labelKey: 'nav.more',
    icon: Icons.more_horiz,
    selectedIcon: Icons.more_horiz,
    anyOf: _more,
  ),
];

const List<NavTab> driverTabs = [
  NavTab(
    key: 'round',
    labelKey: 'nav.round',
    icon: Icons.route_outlined,
    selectedIcon: Icons.route,
    anyOf: {'logistics.run.execute', 'sales.delivery.read'},
  ),
  NavTab(
    key: 'deliver',
    labelKey: 'nav.deliver',
    icon: Icons.local_shipping_outlined,
    selectedIcon: Icons.local_shipping,
    anyOf: {'sales.delivery.record'},
  ),
  NavTab(
    key: 'more',
    labelKey: 'nav.more',
    icon: Icons.more_horiz,
    selectedIcon: Icons.more_horiz,
    anyOf: _more,
  ),
];

const List<NavTab> customerTabs = [
  NavTab(
    key: 'deliveries',
    labelKey: 'nav.deliveries',
    icon: Icons.local_shipping_outlined,
    selectedIcon: Icons.local_shipping,
    anyOf: _more,
  ),
  // D-4: "Invoice (never Bill)" — the design review drew this tab as "Bill";
  // the governed glossary wins, and the guard in glossary_test.dart is the
  // reason it was caught.
  NavTab(
    key: 'bill',
    labelKey: 'nav.bill',
    icon: Icons.receipt_long_outlined,
    selectedIcon: Icons.receipt_long,
    anyOf: _more,
  ),
  NavTab(
    key: 'more',
    labelKey: 'nav.more',
    icon: Icons.more_horiz,
    selectedIcon: Icons.more_horiz,
    anyOf: _more,
  ),
];

List<NavTab> tabsOf(BarShape shape) => switch (shape) {
  BarShape.manager => managerTabs,
  BarShape.operator => operatorTabs,
  BarShape.driver => driverTabs,
  BarShape.customer => customerTabs,
};

/// The bar this person actually gets: the shape for their experience, minus
/// every tab whose destinations they cannot open. A bar of one tab is no bar.
List<NavTab> tabsFor(Session session) =>
    tabsOf(shapeFor(session)).where((t) => t.visibleFor(session)).toList();

/// A destination that a hub tab offers, with the grant it needs.
class HubItem {
  const HubItem({
    required this.key,
    required this.labelKey,
    required this.icon,
    required this.requires,
    this.needsCentre = false,
  });

  final String key;
  final String labelKey;
  final IconData icon;

  /// The permission the platform will check on the first request. `null`
  /// means everyone signed in (sync, sign out).
  final String? requires;

  /// Needs the centre this person works at (readiness, instruments, today).
  final bool needsCentre;

  bool visibleFor(Session session) => requires == null || session.can(requires!);
}

const List<HubItem> moneyItems = [
  HubItem(key: 'settlements', labelKey: 'hub.settlements', icon: Icons.account_balance_outlined, requires: 'settlement.read'),
  HubItem(key: 'payments', labelKey: 'hub.payments', icon: Icons.payments_outlined, requires: 'payment.read'),
  HubItem(key: 'receipts', labelKey: 'hub.receipts', icon: Icons.receipt_outlined, requires: 'receipt.read'),
  HubItem(key: 'rateCards', labelKey: 'hub.rateCards', icon: Icons.price_change_outlined, requires: 'pricing.ratecard.read'),
  HubItem(key: 'matrices', labelKey: 'hub.matrices', icon: Icons.grid_on_outlined, requires: 'pricing.ratecard.read'),
  HubItem(key: 'rateTest', labelKey: 'hub.rateTest', icon: Icons.calculate_outlined, requires: 'pricing.ratecard.read', needsCentre: true),
];

const List<HubItem> reportsItems = [
  HubItem(key: 'todaySummary', labelKey: 'hub.todaySummary', icon: Icons.today_outlined, requires: 'reporting.read', needsCentre: true),
  HubItem(key: 'transactions', labelKey: 'hub.transactions', icon: Icons.receipt_long_outlined, requires: 'collection.transaction.read', needsCentre: true),
  HubItem(key: 'notifications', labelKey: 'hub.notifications', icon: Icons.notifications_outlined, requires: 'notification.read'),
];

const List<HubItem> moreItems = [
  // WO-72 Part C: the counter and the round are places a manager GOES.
  HubItem(key: 'counter', labelKey: 'hub.counter', icon: Icons.water_drop_outlined, requires: 'collection.session.manage'),
  HubItem(key: 'round', labelKey: 'hub.round', icon: Icons.local_shipping_outlined, requires: 'sales.delivery.read'),
  HubItem(key: 'centres', labelKey: 'hub.centres', icon: Icons.location_city_outlined, requires: 'collection.center.read'),
  HubItem(key: 'centreCalendar', labelKey: 'hub.centreCalendar', icon: Icons.calendar_month_outlined, requires: 'collection.center.read', needsCentre: true),
  HubItem(key: 'readiness', labelKey: 'hub.readiness', icon: Icons.fact_check_outlined, requires: 'operations.readiness.read', needsCentre: true),
  HubItem(key: 'instruments', labelKey: 'hub.instruments', icon: Icons.sensors_outlined, requires: 'operations.device.read', needsCentre: true),
  HubItem(key: 'sync', labelKey: 'hub.sync', icon: Icons.sync, requires: null),
];

/// Operator "Today": this session's tally and receipts.
const List<HubItem> operatorTodayItems = [
  HubItem(key: 'todaySummary', labelKey: 'hub.todaySummary', icon: Icons.today_outlined, requires: 'reporting.read', needsCentre: true),
  HubItem(key: 'transactions', labelKey: 'hub.transactions', icon: Icons.receipt_long_outlined, requires: 'collection.transaction.read', needsCentre: true),
  HubItem(key: 'receipts', labelKey: 'hub.receipts', icon: Icons.receipt_outlined, requires: 'receipt.read'),
];

/// Operator "More": instruments, sync, sign out — no centre administration.
const List<HubItem> operatorMoreItems = [
  HubItem(key: 'instruments', labelKey: 'hub.instruments', icon: Icons.sensors_outlined, requires: 'operations.device.read', needsCentre: true),
  HubItem(key: 'sync', labelKey: 'hub.sync', icon: Icons.sync, requires: null),
];

const List<HubItem> driverMoreItems = [
  HubItem(key: 'sync', labelKey: 'hub.sync', icon: Icons.sync, requires: null),
];

/// Every screen class in `lib/src`, and the tab it lives under — by bar
/// shape, because the same screen is "Today" to a manager and "Collect" to
/// an operator. `navigation_test.dart` walks `lib/src` for `class *Screen`
/// and refuses any that is not here or in [preAuthScreens].
const Map<String, Map<BarShape, String>> screenHomes = {
  // --- the manager's own home (Part C) -----------------------------------
  'ManagerHomeScreen': {BarShape.manager: 'today'},
  // --- the counter and its day ------------------------------------------
  'CollectionHomeScreen': {BarShape.manager: 'more', BarShape.operator: 'collect'},
  'CollectionWizardScreen': {BarShape.manager: 'today', BarShape.operator: 'collect'},
  'TransactionHistoryScreen': {BarShape.manager: 'reports', BarShape.operator: 'today'},
  'TransactionDetailScreen': {BarShape.manager: 'reports', BarShape.operator: 'today'},
  'CenterTodayScreen': {BarShape.manager: 'reports', BarShape.operator: 'today'},
  'CenterDetailScreen': {BarShape.manager: 'more', BarShape.operator: 'more'},
  // --- farmers ------------------------------------------------------------
  'SuppliersListScreen': {BarShape.manager: 'farmers', BarShape.operator: 'farmers'},
  'SupplierDetailScreen': {BarShape.manager: 'farmers', BarShape.operator: 'farmers'},
  'SupplierFormScreen': {BarShape.manager: 'farmers'},
  // --- money --------------------------------------------------------------
  'SettlementListScreen': {BarShape.manager: 'money'},
  'SettlementDetailScreen': {BarShape.manager: 'money'},
  'FinalizeSettlementScreen': {BarShape.manager: 'money'},
  'PaymentHistoryScreen': {BarShape.manager: 'money'},
  'PaymentDetailScreen': {BarShape.manager: 'money'},
  'ReceiptHistoryScreen': {BarShape.manager: 'money', BarShape.operator: 'today'},
  'ReceiptDetailScreen': {BarShape.manager: 'money', BarShape.operator: 'today'},
  'RateCardsListScreen': {BarShape.manager: 'money'},
  'RateCardDetailScreen': {BarShape.manager: 'money'},
  'RateCardFormScreen': {BarShape.manager: 'money'},
  'MatrixListScreen': {BarShape.manager: 'money'},
  'MatrixDetailScreen': {BarShape.manager: 'money'},
  'MatrixFormScreen': {BarShape.manager: 'money'},
  'ResolutionTestScreen': {BarShape.manager: 'money'},
  // --- reports ------------------------------------------------------------
  'NotificationHistoryScreen': {BarShape.manager: 'reports'},
  'NotificationDetailScreen': {BarShape.manager: 'reports'},
  // --- more ---------------------------------------------------------------
  'CentersListScreen': {BarShape.manager: 'more'},
  'CenterFormScreen': {BarShape.manager: 'more'},
  'ReadinessScreen': {BarShape.manager: 'more'},
  'InstrumentsScreen': {BarShape.manager: 'more', BarShape.operator: 'more'},
  'SyncStatusScreen': {BarShape.manager: 'more', BarShape.operator: 'more', BarShape.driver: 'more'},
  'ConflictDetailScreen': {BarShape.manager: 'more', BarShape.operator: 'more', BarShape.driver: 'more'},
  // --- the round ----------------------------------------------------------
  'DriverHomeScreen': {BarShape.driver: 'round'},
  'DeliveryRoundScreen': {BarShape.driver: 'deliver', BarShape.manager: 'more'},
  'RecordDeliveryScreen': {BarShape.driver: 'deliver'},
  // --- the household ------------------------------------------------------
  'CustomerHomeScreen': {BarShape.customer: 'deliveries'},
  'CustomerBillScreen': {BarShape.customer: 'bill'},
  'CustomerBillsScreen': {BarShape.customer: 'bill'},
  // --- the hubs themselves (Part B) ---------------------------------------
  'HubScreen': {
    BarShape.manager: 'more',
    BarShape.operator: 'more',
    BarShape.driver: 'more',
    BarShape.customer: 'more',
  },
};

/// Screens that exist before anyone is signed in, so no tab can hold them.
const Set<String> preAuthScreens = {'LoginScreen', 'PasswordResetScreen'};
