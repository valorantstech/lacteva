import 'package:flutter/material.dart';

import 'api.dart';

/// Today's operational summary for one center — REP-001. Deliberately
/// lightweight: the full reporting experience lives in the admin portal.
class CenterTodayScreen extends StatefulWidget {
  const CenterTodayScreen({
    super.key,
    required this.client,
    required this.centerId,
  });

  final ApiClient client;
  final String centerId;

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
      if (mounted) setState(() => _error = 'Could not reach the platform');
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
    return Scaffold(
      appBar: AppBar(title: const Text("Today's collection")),
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
                  _tile('${s.totalNetWeightKg} kg', 'Milk collected'),
                  const SizedBox(width: 8),
                  _tile(s.payable.isEmpty ? '—' : s.payable, 'Payable'),
                ],
              ),
              Row(
                children: [
                  _tile('${s.accepted} / ${s.rejected}', 'Accepted / Rejected'),
                  const SizedBox(width: 8),
                  _tile('${s.suppliersServed}', 'Suppliers served'),
                ],
              ),
              Row(
                children: [
                  _tile('${s.avgFat ?? "—"}', 'Avg FAT'),
                  const SizedBox(width: 8),
                  _tile('${s.avgSnf ?? "—"}', 'Avg SNF'),
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
                      '${s.unpricedAccepted} accepted without pricing',
                    ),
                    subtitle: const Text(
                      'Check the rate card for this center.',
                    ),
                  ),
                ),
              const SizedBox(height: 8),
              Center(
                child: Text(
                  'Pull to refresh · full reports in the admin portal',
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
