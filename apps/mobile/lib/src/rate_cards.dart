import 'package:flutter/material.dart';

import 'api.dart';
import 'pricing_matrices.dart';

/// Rate Card lifecycle — Pricing Increment-001 (no calculations).
class RateCardsListScreen extends StatefulWidget {
  const RateCardsListScreen({super.key, required this.client});

  final ApiClient client;

  @override
  State<RateCardsListScreen> createState() => _RateCardsListScreenState();
}

class _RateCardsListScreenState extends State<RateCardsListScreen> {
  static const pageSize = 20;
  final _search = TextEditingController();
  RateCardPageResult? _page;
  int _offset = 0;
  String? _error;

  @override
  void initState() {
    super.initState();
    _load();
  }

  Future<void> _load() async {
    try {
      final page = await widget.client.listRateCards(
        query: _search.text.trim(),
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

  Future<void> _openForm({RateCardSummary? card}) async {
    final changed = await Navigator.of(context).push<bool>(
      MaterialPageRoute(
        builder: (_) => RateCardFormScreen(client: widget.client, card: card),
      ),
    );
    if (changed == true) await _load();
  }

  @override
  Widget build(BuildContext context) {
    final page = _page;
    return Scaffold(
      appBar: AppBar(title: const Text('Rate cards')),
      floatingActionButton: FloatingActionButton(
        onPressed: () => _openForm(),
        tooltip: 'New rate card',
        child: const Icon(Icons.add),
      ),
      body: RefreshIndicator(
        onRefresh: _load,
        child: ListView(
          padding: const EdgeInsets.all(16),
          children: [
            TextField(
              controller: _search,
              decoration: const InputDecoration(
                prefixIcon: Icon(Icons.search),
                hintText: 'Search by code or name',
              ),
              onSubmitted: (_) {
                _offset = 0;
                _load();
              },
            ),
            const SizedBox(height: 12),
            if (_error != null)
              Text(
                _error!,
                style: TextStyle(color: Theme.of(context).colorScheme.error),
              ),
            if (page == null && _error == null)
              const Padding(
                padding: EdgeInsets.all(32),
                child: Center(child: CircularProgressIndicator()),
              ),
            if (page != null && page.items.isEmpty)
              const Padding(
                padding: EdgeInsets.all(32),
                child: Center(child: Text('No rate cards match.')),
              ),
            if (page != null)
              ...page.items.map(
                (c) => Card(
                  child: ListTile(
                    title: Text(c.name),
                    subtitle: Text(
                      '${c.code} v${c.version} · ${c.currency} · ${c.effectiveLabel}',
                    ),
                    trailing: RateCardStatusChip(status: c.status),
                    onTap: () async {
                      await Navigator.of(context).push(
                        MaterialPageRoute(
                          builder: (_) => RateCardDetailScreen(
                            client: widget.client,
                            cardId: c.id,
                          ),
                        ),
                      );
                      await _load();
                    },
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
                    '${(_offset ~/ pageSize) + 1} / ${(page.total / pageSize).ceil()}',
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

class RateCardStatusChip extends StatelessWidget {
  const RateCardStatusChip({super.key, required this.status});

  final String status;

  @override
  Widget build(BuildContext context) {
    final scheme = Theme.of(context).colorScheme;
    final color = switch (status) {
      'published' => scheme.primaryContainer,
      'archived' => scheme.surfaceContainerHighest,
      _ => scheme.secondaryContainer,
    };
    return Chip(
      label: Text(status.replaceAll('_', ' ')),
      backgroundColor: color,
      visualDensity: VisualDensity.compact,
    );
  }
}

class RateCardFormScreen extends StatefulWidget {
  const RateCardFormScreen({super.key, required this.client, this.card});

  final ApiClient client;
  final RateCardSummary? card;

  bool get isEdit => card != null;

  @override
  State<RateCardFormScreen> createState() => _RateCardFormScreenState();
}

class _RateCardFormScreenState extends State<RateCardFormScreen> {
  final _formKey = GlobalKey<FormState>();
  late final TextEditingController _name = TextEditingController(
    text: widget.card?.name ?? '',
  );
  late final TextEditingController _currency = TextEditingController(
    text: widget.card?.currency ?? 'KES',
  );
  late final TextEditingController _from = TextEditingController(
    text: widget.card?.effectiveFrom ?? '',
  );
  late final TextEditingController _until = TextEditingController(
    text: widget.card?.effectiveUntil ?? '',
  );
  late final TextEditingController _description = TextEditingController(
    text: widget.card?.description ?? '',
  );
  String? _error;
  bool _busy = false;

  static final _datePattern = RegExp(r'^\d{4}-\d{2}-\d{2}$');

  Future<void> _submit() async {
    if (!_formKey.currentState!.validate()) return;
    setState(() {
      _busy = true;
      _error = null;
    });
    final until = _until.text.trim();
    try {
      if (widget.isEdit) {
        await widget.client.updateRateCard(
          widget.card!.id,
          name: _name.text.trim(),
          currency: _currency.text.trim(),
          effectiveFrom: _from.text.trim(),
          effectiveUntil: until.isEmpty ? null : until,
          description: _description.text.trim(),
        );
      } else {
        await widget.client.createRateCard(
          name: _name.text.trim(),
          currency: _currency.text.trim(),
          effectiveFrom: _from.text.trim(),
          effectiveUntil: until.isEmpty ? null : until,
          description: _description.text.trim(),
        );
      }
      if (mounted) Navigator.of(context).pop(true);
    } on ApiException catch (e) {
      setState(() => _error = e.detail);
    } finally {
      if (mounted) setState(() => _busy = false);
    }
  }

  @override
  Widget build(BuildContext context) {
    return Scaffold(
      appBar: AppBar(
        title: Text(
          widget.isEdit
              ? 'Edit ${widget.card!.code} v${widget.card!.version}'
              : 'New rate card',
        ),
      ),
      body: SingleChildScrollView(
        padding: const EdgeInsets.all(16),
        child: Form(
          key: _formKey,
          child: Column(
            crossAxisAlignment: CrossAxisAlignment.stretch,
            children: [
              TextFormField(
                controller: _name,
                decoration: const InputDecoration(labelText: 'Name'),
                validator: (v) => (v == null || v.trim().length < 2)
                    ? 'Name needs at least 2 characters'
                    : null,
              ),
              const SizedBox(height: 12),
              TextFormField(
                controller: _currency,
                decoration: const InputDecoration(
                  labelText: 'Currency (ISO 4217)',
                ),
                textCapitalization: TextCapitalization.characters,
                validator: (v) => (v == null || v.trim().length != 3)
                    ? 'Currency must be 3 letters'
                    : null,
              ),
              const SizedBox(height: 12),
              TextFormField(
                controller: _from,
                decoration: const InputDecoration(
                  labelText: 'Effective from (YYYY-MM-DD)',
                ),
                validator: (v) =>
                    (v == null || !_datePattern.hasMatch(v.trim()))
                    ? 'Enter a date as YYYY-MM-DD'
                    : null,
              ),
              const SizedBox(height: 12),
              TextFormField(
                controller: _until,
                decoration: const InputDecoration(
                  labelText: 'Effective until (optional)',
                ),
                validator: (v) {
                  final value = v?.trim() ?? '';
                  if (value.isEmpty) return null;
                  return _datePattern.hasMatch(value)
                      ? null
                      : 'Enter a date as YYYY-MM-DD';
                },
              ),
              const SizedBox(height: 12),
              TextFormField(
                controller: _description,
                decoration: const InputDecoration(labelText: 'Description'),
                maxLines: 2,
              ),
              const SizedBox(height: 20),
              if (_error != null)
                Padding(
                  padding: const EdgeInsets.only(bottom: 12),
                  child: Text(
                    _error!,
                    style: TextStyle(
                      color: Theme.of(context).colorScheme.error,
                    ),
                  ),
                ),
              FilledButton(
                onPressed: _busy ? null : _submit,
                child: Text(_busy ? 'Saving…' : 'Save'),
              ),
            ],
          ),
        ),
      ),
    );
  }
}

/// Detail with the review workflow: submit → approve → publish → archive.
class RateCardDetailScreen extends StatefulWidget {
  const RateCardDetailScreen({
    super.key,
    required this.client,
    required this.cardId,
  });

  final ApiClient client;
  final String cardId;

  @override
  State<RateCardDetailScreen> createState() => _RateCardDetailScreenState();
}

class _RateCardDetailScreenState extends State<RateCardDetailScreen> {
  RateCardDetailResult? _detail;
  String? _error;

  @override
  void initState() {
    super.initState();
    _load();
  }

  Future<void> _load() async {
    try {
      final detail = await widget.client.rateCardDetail(widget.cardId);
      if (mounted) {
        setState(() {
          _detail = detail;
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

  Future<void> _action(String action) async {
    try {
      await widget.client.rateCardAction(widget.cardId, action);
      await _load();
    } on ApiException catch (e) {
      if (!mounted) return;
      ScaffoldMessenger.of(
        context,
      ).showSnackBar(SnackBar(content: Text(e.detail)));
    } catch (_) {
      // Transport failure ≠ refusal (P0-PRODUCT-008 D-1).
      if (!mounted) return;
      ScaffoldMessenger.of(
        context,
      ).showSnackBar(SnackBar(content: Text('Could not reach the platform')));
    }
  }

  Future<void> _edit() async {
    final card = _detail?.card;
    if (card == null) return;
    final changed = await Navigator.of(context).push<bool>(
      MaterialPageRoute(
        builder: (_) => RateCardFormScreen(client: widget.client, card: card),
      ),
    );
    if (changed == true) await _load();
  }

  @override
  Widget build(BuildContext context) {
    final detail = _detail;
    final card = detail?.card;
    return Scaffold(
      appBar: AppBar(
        title: Text(card?.name ?? 'Rate card'),
        actions: [
          if (card != null)
            IconButton(
              icon: const Icon(Icons.grid_on_outlined),
              tooltip: 'Pricing matrices',
              onPressed: () async {
                await Navigator.of(context).push(
                  MaterialPageRoute(
                    builder: (_) => MatrixListScreen(
                      client: widget.client,
                      rateCardId: card.id,
                    ),
                  ),
                );
                await _load();
              },
            ),
          if (card != null && card.status == 'draft')
            IconButton(
              icon: const Icon(Icons.edit_outlined),
              tooltip: 'Edit draft',
              onPressed: _edit,
            ),
        ],
      ),
      body: detail == null || card == null
          ? Center(
              child: _error != null
                  ? Text(_error!)
                  : const CircularProgressIndicator(),
            )
          : ListView(
              padding: const EdgeInsets.all(16),
              children: [
                Card(
                  child: ListTile(
                    title: Text('${card.code} v${card.version}'),
                    subtitle: Text(
                      '${card.currency} · ${card.effectiveLabel}'
                      '${card.description.isNotEmpty ? '\n${card.description}' : ''}',
                    ),
                    trailing: RateCardStatusChip(status: card.status),
                    isThreeLine: card.description.isNotEmpty,
                  ),
                ),
                const SizedBox(height: 8),
                Wrap(
                  spacing: 8,
                  runSpacing: 8,
                  children: [
                    if (card.status == 'draft')
                      FilledButton.tonal(
                        onPressed: () => _action('submit'),
                        child: const Text('Submit for review'),
                      ),
                    if (card.status == 'under_review')
                      FilledButton.tonal(
                        onPressed: () => _action('approve'),
                        child: const Text('Approve'),
                      ),
                    if (card.status == 'approved')
                      FilledButton(
                        onPressed: () => _action('publish'),
                        child: const Text('Publish'),
                      ),
                    if (card.status == 'published' || card.status == 'archived')
                      FilledButton.tonal(
                        onPressed: () => _action('versions'),
                        child: const Text('New version'),
                      ),
                    if (card.status != 'archived')
                      OutlinedButton(
                        onPressed: () => _action('archive'),
                        child: const Text('Archive'),
                      ),
                  ],
                ),
                const SizedBox(height: 16),
                Text('Scope', style: Theme.of(context).textTheme.titleMedium),
                const SizedBox(height: 4),
                Text(
                  '${detail.centerIds.length} collection center(s) assigned',
                ),
                Text(
                  detail.productCodes.isEmpty
                      ? 'No products assigned'
                      : 'Products: ${detail.productCodes.join(', ')}',
                ),
                const SizedBox(height: 16),
                Text(
                  'Pricing rules arrive with Increment-002 — this card only '
                  'defines identity, validity, and scope.',
                  style: Theme.of(context).textTheme.bodySmall,
                ),
              ],
            ),
    );
  }
}
