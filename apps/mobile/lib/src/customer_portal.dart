/// The household's own app (DEMO-012 §6, §8).
///
/// What a customer wants to know, in the order they want to know it: did the
/// milk come today, what do I owe, and what is on this month's bill.
///
/// Every figure here is the platform's. The bill in particular is rendered
/// exactly as the backend computed it — line by line, with the backend's OWN
/// reconciliation verdict (`totals_match_lines`) shown rather than a sum this
/// app performed. Re-adding the lines in Dart would create a second billing
/// engine whose only possible contribution is to disagree with the first, in
/// front of the person being billed.
///
/// The scope is not enforced here. A customer login is narrowed to its own
/// customer by the PLATFORM (`core/tenancy.enforce_customer_scope`), so this
/// screen would be shown nothing else even if it asked. What it does here is
/// decide what to render, not what may be seen.
library;

import 'package:flutter/material.dart';

import 'api.dart';
import 'l10n.dart';
import 'session.dart';
import 'sign_out.dart';
import 'theme.dart';

/// The device's own UTC date — a fallback only (DEMO-013).
///
/// The account screen asks the platform which day and which month it is by
/// omitting the dates from the report call; this stands in when that answer
/// is unavailable. A phone cannot compute an IANA date without a timezone
/// database, and its own clock is not the dairy's.
String _deviceDate() =>
    DateTime.now().toUtc().toIso8601String().substring(0, 10);

String _monthStart() {
  final now = DateTime.now().toUtc();
  return '${now.year.toString().padLeft(4, '0')}-'
      '${now.month.toString().padLeft(2, '0')}-01';
}

/// The seven days of the week `today` falls in, Monday first
/// (LACTEVA-MOBILE-007).
///
/// **This is calendar arithmetic, not timezone arithmetic**, and the
/// difference is the whole reason it is allowed here. Every date this app
/// touches is a business date the platform already computed in the dairy's
/// clock and sent as a plain `YYYY-MM-DD`; stepping such a string back to its
/// Monday and forward seven days involves no zone, no offset and no handset
/// clock. Converting an INSTANT to a wall clock is the thing this codebase
/// refuses, and nothing here does it.
///
/// Returns the dates as the same plain strings, so every comparison against a
/// delivery row stays a string comparison.
List<String> weekOf(String today) {
  final anchor = DateTime.parse(today);
  final monday = anchor.subtract(Duration(days: anchor.weekday - 1));
  return [for (var i = 0; i < 7; i++) _isoDate(monday.add(Duration(days: i)))];
}

String _isoDate(DateTime d) =>
    '${d.year.toString().padLeft(4, '0')}-'
    '${d.month.toString().padLeft(2, '0')}-'
    '${d.day.toString().padLeft(2, '0')}';

/// Which catalog key names `date` relative to `today`, or null for neither.
///
/// Only two days get a word — the two a household actually thinks in. Anything
/// further out is rendered as the platform's own date rather than counted into
/// a sentence.
String? relativeDayKey(String? date, String today) {
  if (date == null || date.isEmpty) return null;
  if (date == today) return 'customer.today';
  final tomorrow = _isoDate(DateTime.parse(today).add(const Duration(days: 1)));
  return date == tomorrow ? 'customer.tomorrow' : null;
}

/// The plan a household is actually on, or null.
///
/// Only an ACTIVE plan may promise milk. An inactive one is a record of what
/// used to happen, and a card built from it would tell somebody to expect a
/// delivery that nobody is going to make.
Map<String, dynamic>? activePlan(List<Map<String, dynamic>> plans) {
  for (final plan in plans) {
    if (plan['active'] == true) return plan;
  }
  return null;
}

class CustomerHomeScreen extends StatefulWidget {
  const CustomerHomeScreen({
    super.key,
    required this.client,
    required this.session,
  });

  final ApiClient client;
  final Session session;

  @override
  State<CustomerHomeScreen> createState() => _CustomerHomeScreenState();
}

class _CustomerHomeScreenState extends State<CustomerHomeScreen> {
  Map<String, dynamic>? _customer;

  /// The household's standing orders, as `/v1/customers/{id}` already returns
  /// them. The next-delivery card is built from these — the plan is where a
  /// quantity, a product and a schedule live, and nothing here invents one.
  List<Map<String, dynamic>> _plans = const [];
  Map<String, dynamic>? _balance;
  Map<String, dynamic>? _month;
  List<Map<String, dynamic>> _recent = const [];
  List<Map<String, dynamic>> _bills = const [];
  List<Map<String, dynamic>> _receipts = const [];
  bool _loading = true;
  String? _error;

  @override
  void initState() {
    super.initState();
    _load();
  }

  Future<void> _load() async {
    setState(() {
      _loading = true;
      _error = null;
    });
    try {
      final id = widget.session.customerId!;
      // Five aggregate calls for the whole screen. Not one per delivery, and
      // not one per bill (§13).
      final detail = await widget.client.customerDetail(id);
      final balance = await widget.client.customerBalance(id);
      final deliveries = await widget.client.listDeliveries(limit: 60);
      final bills = await widget.client.listInvoices(limit: 12);
      Map<String, dynamic>? month;
      try {
        // The month, in the DAIRY's calendar. `date_to` is omitted so the
        // platform supplies its own today; `date_from` is that month's first
        // day, which the platform's answer then confirms.
        month = await widget.client.deliveryReport(dateFrom: _monthStart());
      } on ApiException {
        month = null;
      }
      List<Map<String, dynamic>> receipts = const [];
      try {
        final r = await widget.client.listCustomerReceipts(limit: 12);
        receipts = ((r['items'] as List?) ?? const [])
            .cast<Map<String, dynamic>>();
      } on ApiException {
        receipts = const [];
      }
      if (!mounted) return;
      setState(() {
        _customer = detail['customer'] as Map<String, dynamic>?;
        _plans = ((detail['plans'] as List?) ?? const [])
            .cast<Map<String, dynamic>>();
        _balance = balance;
        _month = month;
        _recent = ((deliveries['items'] as List?) ?? const [])
            .cast<Map<String, dynamic>>();
        _bills = ((bills['items'] as List?) ?? const [])
            .cast<Map<String, dynamic>>();
        _receipts = receipts;
        _loading = false;
      });
    } on ApiException catch (e) {
      if (!mounted) return;
      setState(() {
        _error = e.detail;
        _loading = false;
      });
    } catch (_) {
      if (!mounted) return;
      setState(() {
        _error =
            'Could not reach the dairy. Showing nothing rather than '
            'something out of date.';
        _loading = false;
      });
    }
  }

  @override
  Widget build(BuildContext context) {
    final t = L10n.of(widget.session);
    final today = (_month?['date_to'] ?? _deviceDate()).toString();
    if (_loading) {
      return const Scaffold(body: Center(child: CircularProgressIndicator()));
    }
    return Scaffold(
      body: RefreshIndicator(
        onRefresh: _load,
        child: ListView(
          padding: EdgeInsets.zero,
          children: [
            _Hero(
              t: t,
              session: widget.session,
              householdName: _customer?['name']?.toString() ?? '',
              month: _month,
              balance: _balance,
              latestInvoice: _bills.isEmpty ? null : _bills.first,
              signOut: SignOutButton(client: widget.client),
            ),
            _NextDelivery(
              t: t,
              session: widget.session,
              plan: activePlan(_plans),
              today: today,
            ),
            _WeekStrip(t: t, today: today, deliveries: _recent),
            if (_error != null)
              Padding(
                padding: const EdgeInsets.fromLTRB(20, 20, 20, 0),
                child: Text(
                  _error!,
                  style: TextStyle(color: Theme.of(context).colorScheme.error),
                ),
              ),
            _Invoices(
              t: t,
              session: widget.session,
              bills: _bills,
              onOpen: (bill) => Navigator.of(context).push(
                MaterialPageRoute(
                  builder: (_) => CustomerBillScreen(
                    client: widget.client,
                    invoiceId: bill['id'].toString(),
                    session: widget.session,
                  ),
                ),
              ),
            ),
            _Receipts(t: t, session: widget.session, receipts: _receipts),
            _History(t: t, deliveries: _recent),
            _Footer(t: t, dairy: widget.session.organization?.name ?? ''),
          ],
        ),
      ),
    );
  }
}

// =====================================================================
// The hero (Customer.dc.html, top band)
// =====================================================================

/// Deep green, lit from one corner, with the household's month in it.
///
/// The one place in the product with an ambient animation. Everything else
/// this cycle added is still — but a household opens this screen once a day to
/// be reassured, not to work, and the mark breathing is the difference between
/// a receipt and something alive. It is four seconds, three pixels, and it
/// stops entirely when the platform asks for reduced motion.
class _Hero extends StatelessWidget {
  const _Hero({
    required this.t,
    required this.session,
    required this.householdName,
    required this.month,
    required this.balance,
    required this.latestInvoice,
    required this.signOut,
  });

  final L10n t;
  final Session session;
  final String householdName;
  final Map<String, dynamic>? month;
  final Map<String, dynamic>? balance;
  final Map<String, dynamic>? latestInvoice;
  final Widget signOut;

  @override
  Widget build(BuildContext context) {
    final top = MediaQuery.paddingOf(context).top;
    final unit = (month?['quantity_unit'] ?? 'L').toString();
    final delivered = _decimal(month?['total_quantity']);
    // `planned_quantity` is what the dairy's rounds INTENDED for this window —
    // the report's own figure, not arithmetic done here. It covers the rounds
    // generated so far, which is why the board's copy carries a tilde.
    final expected = _decimal(month?['planned_quantity']);
    // A vessel is a measurement, and a measurement needs a scale. With
    // nothing planned there is nothing to be full OF — drawing one empty
    // while 54 L arrived would be a false statement to a glancing reader,
    // and filling it against a number this screen made up would be worse.
    // So the figures stand alone and the vessel is simply absent.
    final hasScale = expected != null && expected > 0 && delivered != null;
    final fill = hasScale ? (delivered / expected).clamp(0.0, 1.0) : 0.0;

    return Container(
      padding: EdgeInsets.fromLTRB(20, top + 20, 20, 26),
      decoration: BoxDecoration(gradient: deepBrandGradient()),
      child: Stack(
        clipBehavior: Clip.hardEdge,
        children: [
          const Positioned(right: -50, top: -60, child: _CornerGlow()),
          Column(
            crossAxisAlignment: CrossAxisAlignment.start,
            children: [
              Row(
                children: [
                  Expanded(
                    child: Column(
                      crossAxisAlignment: CrossAxisAlignment.start,
                      children: [
                        if (householdName.isNotEmpty)
                          Text(
                            householdName,
                            maxLines: 1,
                            overflow: TextOverflow.ellipsis,
                            style: const TextStyle(
                              color: LactevaColors.onBrandFaint,
                              fontSize: 13,
                            ),
                          ),
                        const SizedBox(height: 2),
                        Text(
                          t.t('customer.yourMilk'),
                          style: const TextStyle(
                            color: LactevaColors.onBrand,
                            fontSize: 24,
                            fontWeight: FontWeight.w700,
                            letterSpacing: -0.48,
                          ),
                        ),
                      ],
                    ),
                  ),
                  const SizedBox(width: 8),
                  const _ShimmeringMark(),
                  signOut,
                ],
              ),
              const SizedBox(height: 18),
              Row(
                crossAxisAlignment: CrossAxisAlignment.end,
                children: [
                  if (hasScale) ...[
                    _Vessel(fill: fill, label: t.t('customer.vesselLabel')),
                    const SizedBox(width: 20),
                  ],
                  Expanded(
                    child: Column(
                      crossAxisAlignment: CrossAxisAlignment.start,
                      children: [
                        _figure(
                          value: delivered == null
                              ? '—'
                              : '${month?['total_quantity']} $unit',
                          caption: expected == null || expected <= 0
                              // No expectation to compare against: say what
                              // arrived and claim nothing about a target.
                              ? t.t('customer.deliveredThisMonth')
                              : t.t('customer.deliveredOf', {
                                  'expected':
                                      '${month?['planned_quantity']} $unit',
                                }),
                          size: 32,
                          colour: LactevaColors.onBrand,
                        ),
                        const SizedBox(height: 10),
                        _due(),
                      ],
                    ),
                  ),
                ],
              ),
            ],
          ),
        ],
      ),
    );
  }

  Widget _due() {
    final outstanding = balance?['outstanding']?.toString();
    final settled = _decimal(outstanding) == 0;
    final invoice = latestInvoice;
    return _figure(
      value: outstanding == null
          ? '—'
          : t.t('customer.due', {'amount': money(outstanding, session)}),
      caption: settled
          ? t.t('customer.allPaid')
          : invoice == null
          ? t.t('customer.billed', {
              'billed': balance?['invoiced'] ?? '—',
              'paid': balance?['paid'] ?? '—',
            })
          : t.t('customer.dueOn', {'invoice': invoice['invoice_number'] ?? ''}),
      size: 20,
      // Never colour alone: the word "due" is always beside the figure, and
      // paid-up is a lighter green only as the second signal.
      colour: settled ? LactevaColors.onBrandPositive : LactevaColors.onBrand,
    );
  }

  Widget _figure({
    required String value,
    required String caption,
    required double size,
    required Color colour,
  }) => Column(
    crossAxisAlignment: CrossAxisAlignment.start,
    children: [
      FittedBox(
        fit: BoxFit.scaleDown,
        alignment: AlignmentDirectional.centerStart,
        child: Text(
          value,
          maxLines: 1,
          style: TextStyle(
            color: colour,
            fontSize: size,
            fontWeight: FontWeight.w700,
            letterSpacing: -0.02 * size,
          ),
        ),
      ),
      const SizedBox(height: 1),
      Text(
        caption,
        style: const TextStyle(
          color: LactevaColors.onBrandFaint,
          fontSize: 12.5,
        ),
      ),
    ],
  );
}

/// A decimal STRING from the platform, as a number for layout only.
///
/// The value rendered is always the platform's own string — this exists so a
/// vessel can be filled to a fraction and a balance can be tested for zero.
/// Nothing derived from it is ever shown.
double? _decimal(Object? value) =>
    value == null ? null : double.tryParse(value.toString());

/// The light in the corner of the band.
class _CornerGlow extends StatelessWidget {
  const _CornerGlow();

  @override
  Widget build(BuildContext context) => Container(
    width: 210,
    height: 210,
    decoration: BoxDecoration(
      shape: BoxShape.circle,
      gradient: RadialGradient(
        center: const Alignment(-0.3, -0.4),
        radius: 0.65,
        colors: [
          LactevaColors.onBrand.withValues(alpha: 0.16),
          LactevaColors.onBrand.withValues(alpha: 0),
        ],
      ),
    ),
  );
}

/// The mark, breathing.
///
/// Four seconds, three logical pixels, and nothing else on this screen moves.
/// [MediaQuery.disableAnimationsOf] is the platform's own accessibility
/// switch: when it is on there is no controller at all, rather than a
/// controller running at zero — a screen reader user should not pay for an
/// animation they asked not to have.
class _ShimmeringMark extends StatefulWidget {
  const _ShimmeringMark();

  @override
  State<_ShimmeringMark> createState() => _ShimmeringMarkState();
}

class _ShimmeringMarkState extends State<_ShimmeringMark>
    with SingleTickerProviderStateMixin {
  AnimationController? _controller;

  @override
  void didChangeDependencies() {
    super.didChangeDependencies();
    final reduced = MediaQuery.disableAnimationsOf(context);
    if (reduced) {
      _controller?.dispose();
      _controller = null;
      return;
    }
    _controller ??= AnimationController(
      vsync: this,
      duration: const Duration(seconds: 4),
    )..repeat(reverse: true);
  }

  @override
  void dispose() {
    _controller?.dispose();
    super.dispose();
  }

  @override
  Widget build(BuildContext context) {
    const mark = Icon(Icons.water_drop, size: 34, color: LactevaColors.onBrand);
    final controller = _controller;
    if (controller == null) return const ExcludeSemantics(child: mark);
    return ExcludeSemantics(
      child: AnimatedBuilder(
        animation: controller,
        builder: (context, child) => Transform.translate(
          // A gentle rise and settle, on the curve milk uses everywhere else.
          offset: Offset(0, -3 * Curves.easeInOut.transform(controller.value)),
          child: child,
        ),
        child: mark,
      ),
    );
  }
}

/// How much of the month has arrived, as a thing rather than a number.
class _Vessel extends StatelessWidget {
  const _Vessel({required this.fill, required this.label});

  /// 0..1. Zero is a legitimate reading — a new household's first month.
  final double fill;
  final String label;

  @override
  Widget build(BuildContext context) {
    return Semantics(
      label: label,
      value: '${(fill * 100).round()}%',
      child: Container(
        width: 84,
        height: 118,
        decoration: BoxDecoration(
          color: LactevaColors.onBrand.withValues(alpha: 0.10),
          border: Border.all(
            color: LactevaColors.onBrand.withValues(alpha: 0.28),
            width: 1.5,
          ),
          borderRadius: const BorderRadius.vertical(
            top: Radius.circular(14),
            bottom: Radius.circular(20),
          ),
        ),
        child: ClipRRect(
          borderRadius: const BorderRadius.vertical(
            top: Radius.circular(13),
            bottom: Radius.circular(19),
          ),
          child: Align(
            alignment: Alignment.bottomCenter,
            child: FractionallySizedBox(
              heightFactor: fill,
              widthFactor: 1,
              child: Stack(
                clipBehavior: Clip.none,
                children: [
                  const DecoratedBox(
                    decoration: BoxDecoration(
                      gradient: LinearGradient(
                        begin: Alignment.topCenter,
                        end: Alignment.bottomCenter,
                        colors: [LactevaColors.milk, LactevaColors.milkFill],
                      ),
                    ),
                    child: SizedBox.expand(),
                  ),
                  // The meniscus: milk has a surface, and drawing one is the
                  // difference between a fill bar and a vessel.
                  if (fill > 0)
                    const Positioned(
                      top: -5,
                      left: 0,
                      right: 0,
                      height: 10,
                      child: DecoratedBox(
                        decoration: BoxDecoration(
                          shape: BoxShape.rectangle,
                          color: LactevaColors.milk,
                          borderRadius: BorderRadius.all(
                            Radius.elliptical(42, 5),
                          ),
                        ),
                      ),
                    ),
                ],
              ),
            ),
          ),
        ),
      ),
    );
  }
}

// =====================================================================
// The next delivery, overlapping the hero
// =====================================================================

/// What is coming, from the household's own standing order.
///
/// Built entirely from `DeliveryPlanView`, which `/v1/customers/{id}` already
/// returns: the quantity, the product, the slot and the schedule are all the
/// plan's, and `schedule_key` arrives as a translation KEY precisely so the
/// platform does not decide what a Hindi-speaking household reads.
///
/// A household with no active plan gets a welcome instead of an apology. They
/// have not lost anything; nothing has started yet.
class _NextDelivery extends StatelessWidget {
  const _NextDelivery({
    required this.t,
    required this.session,
    required this.plan,
    required this.today,
  });

  final L10n t;
  final Session session;
  final Map<String, dynamic>? plan;
  final String today;

  @override
  Widget build(BuildContext context) {
    final p = plan;
    final relative = p == null
        ? null
        : relativeDayKey(p['next_delivery']?.toString(), today);
    final when = p == null
        ? null
        : relative != null
        ? t.t(relative)
        : businessDate(p['next_delivery']?.toString());

    return Transform.translate(
      // The board's -16px: the card sits INTO the band, so the two read as one
      // object rather than as a header above a list.
      offset: const Offset(0, -16),
      child: Padding(
        padding: const EdgeInsets.fromLTRB(20, 0, 20, 0),
        child: Container(
          padding: const EdgeInsets.symmetric(horizontal: 18, vertical: 15),
          decoration: BoxDecoration(
            color: LactevaColors.milk,
            borderRadius: BorderRadius.circular(16),
            boxShadow: [
              BoxShadow(
                color: LactevaColors.ink.withValues(alpha: 0.07),
                blurRadius: 6,
                offset: const Offset(0, 2),
              ),
              BoxShadow(
                color: LactevaColors.dairy.withValues(alpha: 0.10),
                blurRadius: 26,
                offset: const Offset(0, 12),
              ),
            ],
          ),
          child: Row(
            children: [
              Container(
                width: 42,
                height: 42,
                decoration: BoxDecoration(
                  color: LactevaColors.successTint,
                  borderRadius: BorderRadius.circular(12),
                ),
                child: const Icon(
                  Icons.water_drop_outlined,
                  size: 21,
                  color: LactevaColors.dairy,
                ),
              ),
              const SizedBox(width: 13),
              Expanded(
                child: Column(
                  crossAxisAlignment: CrossAxisAlignment.start,
                  children: [
                    Text(
                      p == null
                          ? t.t('customer.noPlanYet')
                          : when == null || when.isEmpty
                          ? t.t('customer.nextDelivery')
                          : when,
                      style: const TextStyle(
                        fontSize: 14.5,
                        fontWeight: FontWeight.w700,
                        color: LactevaColors.ink,
                      ),
                    ),
                    const SizedBox(height: 1),
                    Text(
                      p == null
                          ? t.t('customer.noPlanYetDetail')
                          : t.t('customer.planLine', {
                              'quantity':
                                  '${p['default_quantity']} ${p['quantity_unit'] ?? 'L'}',
                              'product': p['product'] ?? '',
                              'slot': t.t('slot.${p['slot'] ?? 'morning'}'),
                            }),
                      style: const TextStyle(
                        fontSize: 12.5,
                        color: LactevaColors.muted,
                      ),
                    ),
                  ],
                ),
              ),
              if (p != null) ...[
                const SizedBox(width: 10),
                _Chip(
                  // The platform sends a KEY, never a sentence.
                  text: t.t('${p['schedule_key'] ?? 'schedule.daily'}'),
                  tint: LactevaColors.successTint,
                  ink: LactevaColors.onSuccessTint,
                ),
              ],
            ],
          ),
        ),
      ),
    );
  }
}

// =====================================================================
// The week
// =====================================================================

/// Seven days: what came, what is today, and what has not happened yet.
class _WeekStrip extends StatelessWidget {
  const _WeekStrip({
    required this.t,
    required this.today,
    required this.deliveries,
  });

  final L10n t;
  final String today;
  final List<Map<String, dynamic>> deliveries;

  static const _dayKeys = [
    'day.mon',
    'day.tue',
    'day.wed',
    'day.thu',
    'day.fri',
    'day.sat',
    'day.sun',
  ];

  @override
  Widget build(BuildContext context) {
    final week = weekOf(today);
    return Padding(
      padding: const EdgeInsets.fromLTRB(20, 4, 20, 0),
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: [
          _SectionLabel(text: t.t('customer.thisWeek')),
          const SizedBox(height: 10),
          Row(
            children: [
              for (var i = 0; i < week.length; i++) ...[
                Expanded(
                  child: _Day(
                    label: t.t(_dayKeys[i]),
                    isToday: week[i] == today,
                    // A day in the future has not failed to happen; it simply
                    // has not happened. Only a past day can be empty.
                    isFuture: week[i].compareTo(today) > 0,
                    delivered: _deliveredOn(week[i]),
                  ),
                ),
                if (i != week.length - 1) const SizedBox(width: 7),
              ],
            ],
          ),
        ],
      ),
    );
  }

  /// What arrived that day, as the platform's own string — never summed here.
  String? _deliveredOn(String date) {
    for (final d in deliveries) {
      if (d['delivery_date']?.toString() == date &&
          d['status'] == 'delivered' &&
          d['quantity'] != null) {
        return '${d['quantity']} ${d['quantity_unit'] ?? 'L'}';
      }
    }
    return null;
  }
}

class _Day extends StatelessWidget {
  const _Day({
    required this.label,
    required this.isToday,
    required this.isFuture,
    required this.delivered,
  });

  final String label;
  final bool isToday;
  final bool isFuture;
  final String? delivered;

  @override
  Widget build(BuildContext context) {
    final quantity = delivered;
    // A coloured box with a number in it is nothing to a screen reader: the
    // day it belongs to is carried by a label under it, and only sighted
    // readers get to associate the two. So the cell says both.
    return Semantics(
      label: label,
      value: quantity ?? '',
      child: Column(
        children: [
          SizedBox(
            height: 54,
            width: double.infinity,
            child: isFuture && quantity == null
                ? CustomPaint(painter: _DashedBox())
                : DecoratedBox(
                    decoration: BoxDecoration(
                      color: isToday || quantity == null
                          ? null
                          : LactevaColors.successTint,
                      gradient: isToday
                          ? const LinearGradient(
                              begin: Alignment.topCenter,
                              end: Alignment.bottomCenter,
                              colors: [
                                LactevaColors.fresh,
                                LactevaColors.success,
                              ],
                            )
                          : null,
                      border: quantity == null && !isToday
                          ? Border.all(color: LactevaColors.hairline)
                          : null,
                      borderRadius: BorderRadius.circular(10),
                    ),
                    child: Align(
                      alignment: Alignment.bottomCenter,
                      child: Padding(
                        padding: const EdgeInsets.only(bottom: 5),
                        child: FittedBox(
                          fit: BoxFit.scaleDown,
                          child: Text(
                            quantity ?? '',
                            maxLines: 1,
                            style: TextStyle(
                              fontSize: 11.5,
                              fontWeight: FontWeight.w700,
                              color: isToday
                                  ? LactevaColors.onBrand
                                  : LactevaColors.onSuccessTint,
                            ),
                          ),
                        ),
                      ),
                    ),
                  ),
          ),
          const SizedBox(height: 5),
          ExcludeSemantics(
            child: Text(
              label,
              style: TextStyle(
                fontSize: 11,
                fontWeight: isToday ? FontWeight.w700 : FontWeight.w400,
                color: isToday ? LactevaColors.ink : LactevaColors.faint,
              ),
            ),
          ),
        ],
      ),
    );
  }
}

/// A day that has not happened yet — outlined, not empty.
class _DashedBox extends CustomPainter {
  @override
  void paint(Canvas canvas, Size size) {
    final paint = Paint()
      ..color = LactevaColors.controlBorder
      ..style = PaintingStyle.stroke
      ..strokeWidth = 1.5;
    final rect = RRect.fromRectAndRadius(
      Rect.fromLTWH(0.75, 0.75, size.width - 1.5, size.height - 1.5),
      const Radius.circular(10),
    );
    for (final metric in (Path()..addRRect(rect)).computeMetrics()) {
      var distance = 0.0;
      while (distance < metric.length) {
        canvas.drawPath(metric.extractPath(distance, distance + 4), paint);
        distance += 8;
      }
    }
  }

  @override
  bool shouldRepaint(_DashedBox oldDelegate) => false;
}

// =====================================================================
// Invoices, receipts, history
// =====================================================================

class _Invoices extends StatelessWidget {
  const _Invoices({
    required this.t,
    required this.session,
    required this.bills,
    required this.onOpen,
  });

  final L10n t;
  final Session session;
  final List<Map<String, dynamic>> bills;
  final void Function(Map<String, dynamic>) onOpen;

  @override
  Widget build(BuildContext context) {
    return _Section(
      label: t.t('customer.bills'),
      child: bills.isEmpty
          ? _Welcome(text: t.t('customer.noBill'))
          : Column(
              children: [
                for (final bill in bills)
                  Padding(
                    padding: const EdgeInsets.only(bottom: 8),
                    child: _ListRow(
                      onTap: () => onOpen(bill),
                      title: bill['invoice_number']?.toString() ?? '—',
                      detail: t.t('customer.invoiceLine', {
                        'from': businessDate(bill['period_from']?.toString()),
                        'to': businessDate(bill['period_to']?.toString()),
                        'count': bill['line_count'] ?? 0,
                      }),
                      trailing: [
                        Text(
                          money(bill['amount_due']?.toString(), session),
                          style: const TextStyle(
                            fontSize: 13,
                            fontWeight: FontWeight.w700,
                            color: LactevaColors.ink,
                          ),
                        ),
                        const SizedBox(width: 8),
                        // The status arrives as a CODE; the catalog decides
                        // the word, and the amount is beside it so the chip is
                        // never the only signal.
                        _Chip(
                          text: t.t('invoice.${bill['status']}'),
                          tint: bill['status'] == 'paid'
                              ? LactevaColors.successTint
                              : LactevaColors.warningTint,
                          ink: bill['status'] == 'paid'
                              ? LactevaColors.onSuccessTint
                              : LactevaColors.onWarningTint,
                        ),
                      ],
                    ),
                  ),
              ],
            ),
    );
  }
}

class _Receipts extends StatelessWidget {
  const _Receipts({
    required this.t,
    required this.session,
    required this.receipts,
  });

  final L10n t;
  final Session session;
  final List<Map<String, dynamic>> receipts;

  @override
  Widget build(BuildContext context) {
    if (receipts.isEmpty) return const SizedBox.shrink();
    return _Section(
      label: t.t('customer.receipts'),
      child: Column(
        children: [
          for (final r in receipts)
            Padding(
              padding: const EdgeInsets.only(bottom: 8),
              child: _ListRow(
                title: r['receipt_number']?.toString() ?? '—',
                detail: r['payment_number']?.toString() ?? '',
                trailing: [
                  Text(
                    money(r['amount']?.toString(), session),
                    style: const TextStyle(
                      fontSize: 13,
                      fontWeight: FontWeight.w700,
                      color: LactevaColors.ink,
                    ),
                  ),
                ],
              ),
            ),
        ],
      ),
    );
  }
}

class _History extends StatelessWidget {
  const _History({required this.t, required this.deliveries});

  final L10n t;
  final List<Map<String, dynamic>> deliveries;

  @override
  Widget build(BuildContext context) {
    return _Section(
      label: t.t('customer.history'),
      child: deliveries.isEmpty
          ? _Welcome(text: t.t('customer.firstMonth'))
          : Column(
              children: [
                for (final d in deliveries.take(30))
                  Padding(
                    padding: const EdgeInsets.only(bottom: 8),
                    child: _ListRow(
                      title: businessDate(d['delivery_date']?.toString()),
                      detail: t.t('status.${d['status']}'),
                      trailing: [
                        Text(
                          d['status'] == 'delivered'
                              ? '${d['quantity']} ${d['quantity_unit'] ?? 'L'}'
                              : '—',
                          style: const TextStyle(
                            fontSize: 13,
                            fontWeight: FontWeight.w600,
                            color: LactevaColors.ink,
                          ),
                        ),
                      ],
                    ),
                  ),
              ],
            ),
    );
  }
}

class _Section extends StatelessWidget {
  const _Section({required this.label, required this.child});

  final String label;
  final Widget child;

  @override
  Widget build(BuildContext context) => Padding(
    padding: const EdgeInsets.fromLTRB(20, 20, 20, 0),
    child: Column(
      crossAxisAlignment: CrossAxisAlignment.start,
      children: [
        _SectionLabel(text: label),
        const SizedBox(height: 10),
        child,
      ],
    ),
  );
}

class _ListRow extends StatelessWidget {
  const _ListRow({
    required this.title,
    required this.detail,
    required this.trailing,
    this.onTap,
  });

  final String title;
  final String detail;
  final List<Widget> trailing;
  final VoidCallback? onTap;

  @override
  Widget build(BuildContext context) {
    return Material(
      color: LactevaColors.milk,
      borderRadius: BorderRadius.circular(14),
      child: InkWell(
        onTap: onTap,
        borderRadius: BorderRadius.circular(14),
        child: Ink(
          decoration: BoxDecoration(
            color: LactevaColors.milk,
            border: Border.all(color: LactevaColors.hairline),
            borderRadius: BorderRadius.circular(14),
          ),
          child: Padding(
            padding: const EdgeInsets.symmetric(horizontal: 16, vertical: 14),
            child: Row(
              children: [
                Expanded(
                  child: Column(
                    crossAxisAlignment: CrossAxisAlignment.start,
                    children: [
                      Text(
                        title,
                        style: const TextStyle(
                          fontSize: 14.5,
                          fontWeight: FontWeight.w600,
                          color: LactevaColors.ink,
                        ),
                      ),
                      if (detail.isNotEmpty) ...[
                        const SizedBox(height: 1),
                        Text(
                          detail,
                          style: const TextStyle(
                            fontSize: 12.5,
                            color: LactevaColors.muted,
                          ),
                        ),
                      ],
                    ],
                  ),
                ),
                ...trailing,
                if (onTap != null) ...[
                  const SizedBox(width: 6),
                  const Icon(
                    Icons.chevron_right,
                    size: 18,
                    color: LactevaColors.muted,
                  ),
                ],
              ],
            ),
          ),
        ),
      ),
    );
  }
}

/// An empty section that welcomes rather than apologises.
///
/// A household on its first morning has not lost anything and nothing has
/// gone wrong. "No invoices" states a deficiency; this states a beginning.
class _Welcome extends StatelessWidget {
  const _Welcome({required this.text});

  final String text;

  @override
  Widget build(BuildContext context) => Container(
    width: double.infinity,
    padding: const EdgeInsets.symmetric(horizontal: 16, vertical: 16),
    decoration: BoxDecoration(
      color: LactevaColors.milk,
      border: Border.all(color: LactevaColors.hairline),
      borderRadius: BorderRadius.circular(14),
    ),
    child: Text(
      text,
      style: const TextStyle(fontSize: 13.5, color: LactevaColors.muted),
    ),
  );
}

class _Footer extends StatelessWidget {
  const _Footer({required this.t, required this.dairy});

  final L10n t;
  final String dairy;

  @override
  Widget build(BuildContext context) => Padding(
    padding: const EdgeInsets.fromLTRB(20, 26, 20, 26),
    child: Center(
      child: Text(
        dairy.isEmpty
            ? t.t('customer.freshEveryMorning')
            : t.t('customer.freshFrom', {'dairy': dairy}),
        textAlign: TextAlign.center,
        style: const TextStyle(fontSize: 11.5, color: LactevaColors.faint),
      ),
    ),
  );
}

class _SectionLabel extends StatelessWidget {
  const _SectionLabel({required this.text});

  final String text;

  @override
  Widget build(BuildContext context) => Text(
    text.toUpperCase(),
    style: const TextStyle(
      fontSize: 12,
      fontWeight: FontWeight.w700,
      letterSpacing: 0.96,
      color: LactevaColors.muted,
    ),
  );
}

class _Chip extends StatelessWidget {
  const _Chip({required this.text, required this.tint, required this.ink});

  final String text;
  final Color tint;
  final Color ink;

  @override
  Widget build(BuildContext context) => Container(
    padding: const EdgeInsets.symmetric(horizontal: 10, vertical: 4),
    decoration: BoxDecoration(
      color: tint,
      borderRadius: BorderRadius.circular(999),
    ),
    child: Text(
      text,
      style: TextStyle(fontSize: 11.5, fontWeight: FontWeight.w700, color: ink),
    ),
  );
}

/// One monthly bill, exactly as the platform computed it (§8).
class CustomerBillScreen extends StatefulWidget {
  const CustomerBillScreen({
    super.key,
    required this.client,
    required this.invoiceId,
    this.session,
  });

  final ApiClient client;
  final String invoiceId;

  /// For language only (P1-LOCALE-I18N-001); null renders English.
  final Session? session;

  @override
  State<CustomerBillScreen> createState() => _CustomerBillScreenState();
}

class _CustomerBillScreenState extends State<CustomerBillScreen> {
  L10n get _t => L10n.of(widget.session);

  Map<String, dynamic>? _detail;
  String? _error;

  @override
  void initState() {
    super.initState();
    _load();
  }

  Future<void> _load() async {
    try {
      final d = await widget.client.invoiceDetail(widget.invoiceId);
      if (!mounted) return;
      setState(() => _detail = d);
    } on ApiException catch (e) {
      if (!mounted) return;
      setState(() => _error = e.detail);
    } catch (_) {
      // Transport failure ≠ refusal (P0-PRODUCT-008 D-1).
      if (mounted) setState(() => _error = 'Could not reach the platform');
    }
  }

  @override
  Widget build(BuildContext context) {
    final d = _detail;
    final invoice = d?['invoice'] as Map<String, dynamic>?;
    final lines = ((d?['lines'] as List?) ?? const [])
        .cast<Map<String, dynamic>>();
    return Scaffold(
      appBar: AppBar(
        title: Text(
          invoice?['invoice_number']?.toString() ?? _t.t('customer.bill'),
        ),
      ),
      body: _error != null
          ? Center(
              child: Padding(
                padding: const EdgeInsets.all(24),
                child: Text(_error!),
              ),
            )
          : d == null
          ? const Center(child: CircularProgressIndicator())
          : ListView(
              padding: const EdgeInsets.all(16),
              children: [
                Card(
                  child: Padding(
                    padding: const EdgeInsets.all(20),
                    child: Column(
                      crossAxisAlignment: CrossAxisAlignment.start,
                      children: [
                        Text(
                          '${invoice?['period_from']} → ${invoice?['period_to']}',
                          style: Theme.of(context).textTheme.labelLarge,
                        ),
                        const SizedBox(height: 12),
                        _Row('Deliveries', '${invoice?['line_count'] ?? 0}'),
                        _Row(
                          _t.t('customer.subtotal'),
                          '${invoice?['subtotal']}',
                        ),
                        _Row(
                          _t.t('customer.adjustments'),
                          '${invoice?['adjustments']}',
                        ),
                        _Row(
                          _t.t('customer.broughtForward'),
                          '${invoice?['previous_balance']}',
                        ),
                        const Divider(),
                        _Row(
                          _t.t('customer.amountDue'),
                          '${invoice?['amount_due']} ${invoice?['currency'] ?? ''}',
                          bold: true,
                        ),
                        _Row(_t.t('customer.paid'), '${d['paid']}'),
                        _Row(
                          _t.t('customer.outstanding'),
                          '${d['outstanding']}',
                          bold: true,
                        ),
                        const SizedBox(height: 12),
                        // The PLATFORM's verdict, not a sum performed here.
                        Row(
                          children: [
                            Icon(
                              d['totals_match_lines'] == true
                                  ? Icons.verified_outlined
                                  : Icons.warning_amber_outlined,
                              size: 18,
                              color: d['totals_match_lines'] == true
                                  ? LactevaColors.success
                                  : Theme.of(context).colorScheme.error,
                            ),
                            const SizedBox(width: 8),
                            Expanded(
                              child: Text(
                                d['totals_match_lines'] == true
                                    ? _t.t('customer.checked')
                                    : _t.t('customer.mismatch'),
                                style: Theme.of(context).textTheme.bodySmall,
                              ),
                            ),
                          ],
                        ),
                      ],
                    ),
                  ),
                ),
                const SizedBox(height: 12),
                Card(
                  child: Column(
                    crossAxisAlignment: CrossAxisAlignment.start,
                    children: [
                      Padding(
                        padding: const EdgeInsets.fromLTRB(20, 20, 20, 4),
                        child: Text(
                          _t.t('customer.everyDelivery'),
                          style: Theme.of(context).textTheme.labelLarge,
                        ),
                      ),
                      for (final line in lines)
                        ListTile(
                          dense: true,
                          title: Text(
                            '${line['delivery_date']} · ${line['slot']}',
                          ),
                          subtitle: Text(
                            '${line['quantity']} ${line['quantity_unit'] ?? 'L'} '
                            '@ ${line['unit_price']}',
                          ),
                          trailing: Text(line['amount']?.toString() ?? ''),
                        ),
                    ],
                  ),
                ),
              ],
            ),
    );
  }
}

class _Row extends StatelessWidget {
  const _Row(this.label, this.value, {this.bold = false});

  final String label;
  final String value;
  final bool bold;

  @override
  Widget build(BuildContext context) {
    final style = TextStyle(
      fontWeight: bold ? FontWeight.bold : FontWeight.normal,
      fontSize: bold ? 17 : 15,
    );
    return Padding(
      padding: const EdgeInsets.symmetric(vertical: 3),
      child: Row(
        mainAxisAlignment: MainAxisAlignment.spaceBetween,
        children: [
          Text(label, style: style),
          Text(value, style: style),
        ],
      ),
    );
  }
}
