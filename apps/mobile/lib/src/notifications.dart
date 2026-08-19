import 'package:flutter/material.dart';

import 'api.dart';

/// Notification history — NOT-001.
///
/// Read-only by design. The device never sends a message and never registers
/// for push; it only shows what the platform already dispatched, so a field
/// operator can answer "did the farmer get their settlement SMS?".
class NotificationHistoryScreen extends StatefulWidget {
  const NotificationHistoryScreen({super.key, required this.client});

  final ApiClient client;

  @override
  State<NotificationHistoryScreen> createState() =>
      _NotificationHistoryScreenState();
}

class _NotificationHistoryScreenState extends State<NotificationHistoryScreen> {
  static const pageSize = 20;
  static const statuses = ['', 'sent', 'failed', 'dead'];

  final _search = TextEditingController();
  NotificationPageResult? _page;
  String _status = '';
  int _offset = 0;
  String? _error;

  @override
  void initState() {
    super.initState();
    _load();
  }

  @override
  void dispose() {
    _search.dispose();
    super.dispose();
  }

  Future<void> _load() async {
    try {
      final page = await widget.client.listNotifications(
        query: _search.text.trim(),
        status: _status,
        limit: pageSize,
        offset: _offset,
      );
      if (!mounted) return;
      setState(() {
        _page = page;
        _error = null;
      });
    } on ApiException catch (e) {
      if (mounted) setState(() => _error = e.detail);
    } catch (_) {
      // A transport failure is not a platform refusal (P0-PRODUCT-008 D-1):
      // say so instead of leaving the spinner forever.
      if (mounted) setState(() => _error = 'Could not reach the platform');
    }
  }

  IconData _icon(String status) => switch (status) {
    'sent' => Icons.check_circle_outline,
    'dead' => Icons.cancel_outlined,
    'failed' => Icons.schedule,
    _ => Icons.mail_outline,
  };

  Color _color(String status, ColorScheme scheme) => switch (status) {
    'sent' => Colors.green,
    'dead' => scheme.error,
    'failed' => Colors.orange,
    _ => scheme.outline,
  };

  @override
  Widget build(BuildContext context) {
    final page = _page;
    final scheme = Theme.of(context).colorScheme;
    return Scaffold(
      appBar: AppBar(title: const Text('Notifications')),
      body: RefreshIndicator(
        onRefresh: _load,
        child: ListView(
          padding: const EdgeInsets.all(16),
          children: [
            TextField(
              controller: _search,
              decoration: const InputDecoration(
                prefixIcon: Icon(Icons.search),
                hintText: 'Search recipient or message',
              ),
              onSubmitted: (_) {
                _offset = 0;
                _load();
              },
            ),
            const SizedBox(height: 12),
            SingleChildScrollView(
              scrollDirection: Axis.horizontal,
              child: Row(
                children: statuses
                    .map(
                      (s) => Padding(
                        padding: const EdgeInsets.only(right: 8),
                        child: ChoiceChip(
                          label: Text(s.isEmpty ? 'All' : s),
                          selected: _status == s,
                          onSelected: (_) {
                            setState(() {
                              _status = s;
                              _offset = 0;
                            });
                            _load();
                          },
                        ),
                      ),
                    )
                    .toList(),
              ),
            ),
            const SizedBox(height: 12),
            if (_error != null)
              Text(_error!, style: TextStyle(color: scheme.error)),
            if (page == null && _error == null)
              const Padding(
                padding: EdgeInsets.all(32),
                child: Center(child: CircularProgressIndicator()),
              ),
            if (page != null && page.items.isEmpty)
              const Padding(
                padding: EdgeInsets.all(32),
                child: Center(child: Text('No notifications yet.')),
              ),
            if (page != null)
              ...page.items.map(
                (n) => Card(
                  child: ListTile(
                    leading: Icon(
                      _icon(n.status),
                      color: _color(n.status, scheme),
                    ),
                    title: Text(n.title ?? n.templateKey),
                    subtitle: Text(
                      '${n.text ?? n.error ?? ''}\n'
                      '${n.recipient ?? 'unresolved'} · ${n.channel} · '
                      '${n.createdAt.replaceFirst('T', ' ').split('.').first}',
                    ),
                    isThreeLine: true,
                    trailing: n.attemptCount > 1
                        ? Text(
                            '×${n.attemptCount}',
                            style: Theme.of(context).textTheme.bodySmall,
                          )
                        : null,
                    onTap: () => Navigator.of(context).push(
                      MaterialPageRoute(
                        builder: (_) =>
                            NotificationDetailScreen(notification: n),
                      ),
                    ),
                  ),
                ),
              ),
            if (page != null && page.total > pageSize)
              Row(
                mainAxisAlignment: MainAxisAlignment.center,
                children: [
                  TextButton(
                    onPressed: _offset == 0
                        ? null
                        : () {
                            _offset = (_offset - pageSize).clamp(0, 1 << 30);
                            _load();
                          },
                    child: const Text('Previous'),
                  ),
                  Text(
                    '${(_offset ~/ pageSize) + 1} / '
                    '${(page.total / pageSize).ceil()}',
                  ),
                  TextButton(
                    onPressed: _offset + pageSize >= page.total
                        ? null
                        : () {
                            _offset += pageSize;
                            _load();
                          },
                    child: const Text('Next'),
                  ),
                ],
              ),
          ],
        ),
      ),
    );
  }
}

/// What was sent, to whom, and which event caused it.
class NotificationDetailScreen extends StatelessWidget {
  const NotificationDetailScreen({super.key, required this.notification});

  final NotificationSummary notification;

  @override
  Widget build(BuildContext context) {
    final n = notification;
    final theme = Theme.of(context);
    return Scaffold(
      appBar: AppBar(title: Text(n.templateKey)),
      body: ListView(
        padding: const EdgeInsets.all(16),
        children: [
          Card(
            child: ListTile(
              title: Text(n.title ?? n.templateKey),
              subtitle: Text(
                n.text ?? 'Not rendered — delivery never got that far.',
              ),
            ),
          ),
          const SizedBox(height: 8),
          ListTile(
            dense: true,
            leading: const Icon(Icons.person_outline),
            title: const Text('Recipient'),
            subtitle: Text(n.recipient ?? 'unresolved'),
          ),
          ListTile(
            dense: true,
            leading: const Icon(Icons.bolt_outlined),
            title: const Text('Triggered by'),
            subtitle: Text(n.eventName),
          ),
          ListTile(
            dense: true,
            leading: const Icon(Icons.send_outlined),
            title: const Text('Channel'),
            subtitle: Text('${n.channel} · ${n.language}'),
          ),
          ListTile(
            dense: true,
            leading: const Icon(Icons.info_outline),
            title: const Text('Status'),
            subtitle: Text('${n.status} after ${n.attemptCount} attempt(s)'),
          ),
          if (n.error != null)
            ListTile(
              dense: true,
              leading: Icon(
                Icons.error_outline,
                color: theme.colorScheme.error,
              ),
              title: const Text('Last error'),
              subtitle: Text(n.error!),
            ),
          ListTile(
            dense: true,
            leading: const Icon(Icons.schedule),
            title: const Text('Created'),
            subtitle: Text(n.createdAt.replaceFirst('T', ' ').split('.').first),
          ),
        ],
      ),
    );
  }
}
