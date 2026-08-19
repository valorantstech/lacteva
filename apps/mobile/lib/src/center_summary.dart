import 'package:flutter/material.dart';

import 'api.dart';
import 'l10n.dart';
import 'session.dart';

/// Today's operational summary for one center — REP-001. Deliberately
/// lightweight: the full reporting experience lives in the admin portal.
class CenterTodayScreen extends StatefulWidget {
  const CenterTodayScreen({
    super.key,
    required this.client,
    required this.centerId,
    this.session,
  });

  final ApiClient client;
  final String centerId;

  /// For language only (P1-LOCALE-I18N-001); null renders English.
  final Session? session;

  @override
  State<CenterTodayScreen> createState() => _CenterTodayScreenState();
}

class _CenterTodayScreenState extends State<CenterTodayScreen> {
  DailySummaryView? _summary;
  String? _error;

  @override
  void initState() {
    super.initState();
    _load();
  }

  Future<void> _load() async {
    try {
      final summary = await widget.client.dailyReport(widget.centerId);
      if (mounted) {
        setState(() {
          _summary = summary;
          _error = null;
        });
      }
    } on ApiException catch (e) {
      if (mounted) setState(() => _error = e.detail);
    } catch (_) {
      // A transport failure is not a platform refusal (P0-PRODUCT-008 D-1):
      // say so instead of leaving the spinner forever.
      if (mounted) {
        setState(
          () => _error = L10n.of(widget.session).t('common.couldNotReach'),
        );
      }
    }
  }

  Widget _tile(String value, String label) => Expanded(
    child: Card(
      child: Padding(
        padding: const EdgeInsets.all(12),
        child: Column(
          children: [
            Text(
              value,
              style: Theme.of(context).textTheme.titleLarge,
              textAlign: TextAlign.center,
            ),
            const SizedBox(height: 4),
            Text(
              label,
              style: Theme.of(context).textTheme.bodySmall,
              textAlign: TextAlign.center,
            ),
          ],
        ),
      ),
    ),
  );

  @override
  Widget build(BuildContext context) {
    final s = _summary;
    final t = L10n.of(widget.session);
    return Scaffold(
      appBar: AppBar(title: Text(t.t('today.title'))),
      body: RefreshIndicator(
        onRefresh: _load,
        child: ListView(
          padding: const EdgeInsets.all(16),
          children: [
            if (_error != null)
              Text(
                _error!,
                style: TextStyle(color: Theme.of(context).colorScheme.error),
              ),
            if (s == null && _error == null)
              const Padding(
                padding: EdgeInsets.all(32),
                child: Center(child: CircularProgressIndicator()),
              ),
            if (s != null) ...[
              Row(
                children: [
                  _tile('${s.totalNetWeightKg} kg', t.t('today.milkCollected')),
                  const SizedBox(width: 8),
                  _tile(
                    s.payable.isEmpty ? '—' : s.payable,
                    t.t('today.payable'),
                  ),
                ],
              ),
              Row(
                children: [
                  _tile(
                    '${s.accepted} / ${s.rejected}',
                    t.t('today.acceptedRejected'),
                  ),
                  const SizedBox(width: 8),
                  _tile('${s.suppliersServed}', t.t('today.suppliersServed')),
                ],
              ),
              Row(
                children: [
                  _tile('${s.avgFat ?? "—"}', t.t('today.avgFat')),
                  const SizedBox(width: 8),
                  _tile('${s.avgSnf ?? "—"}', t.t('today.avgSnf')),
                ],
              ),
              if (s.unpricedAccepted > 0)
                Card(
                  child: ListTile(
                    leading: Icon(
                      Icons.warning_amber,
                      color: Theme.of(context).colorScheme.tertiary,
                    ),
                    title: Text(
                      t.t('today.unpriced', {'n': s.unpricedAccepted}),
                    ),
                    subtitle: Text(t.t('today.checkRateCard')),
                  ),
                ),
              const SizedBox(height: 8),
              Center(
                child: Text(
                  t.t('today.footer'),
                  style: Theme.of(context).textTheme.bodySmall,
                ),
              ),
            ],
          ],
        ),
      ),
    );
  }
}
