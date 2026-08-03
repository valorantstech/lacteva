import 'package:flutter/material.dart';

import 'api.dart';

/// Pricing Matrix screens — Pricing Increment-002 (data only, no calculation).
class MatrixListScreen extends StatefulWidget {
  const MatrixListScreen({super.key, required this.client, this.rateCardId});

  final ApiClient client;

  /// When set, lists only the matrices of this rate card.
  final String? rateCardId;

  @override
  State<MatrixListScreen> createState() => _MatrixListScreenState();
}

class _MatrixListScreenState extends State<MatrixListScreen> {
  static const pageSize = 20;
  final _search = TextEditingController();
  MatrixPageResult? _page;
  int _offset = 0;
  String? _error;

  @override
  void initState() {
    super.initState();
    _load();
  }

  Future<void> _load() async {
    try {
      final page = await widget.client.listMatrices(
        query: _search.text.trim(),
        rateCardId: widget.rateCardId ?? '',
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
    }
  }

  Future<void> _openCreate() async {
    final rateCardId = widget.rateCardId;
    if (rateCardId == null) return;
    final changed = await Navigator.of(context).push<bool>(
      MaterialPageRoute(
        builder: (_) =>
            MatrixFormScreen(client: widget.client, rateCardId: rateCardId),
      ),
    );
    if (changed == true) await _load();
  }

  @override
  Widget build(BuildContext context) {
    final page = _page;
    return Scaffold(
      appBar: AppBar(title: const Text('Pricing matrices')),
      floatingActionButton: widget.rateCardId == null
          ? null
          : FloatingActionButton(
              onPressed: _openCreate,
              tooltip: 'New matrix',
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
                hintText: 'Search by name or product',
              ),
              onSubmitted: (_) {
                _offset = 0;
                _load();
              },
            ),
            const SizedBox(height: 12),
            if (_error != null)
              Text(_error!,
                  style: TextStyle(color: Theme.of(context).colorScheme.error)),
            if (page == null && _error == null)
              const Padding(
                padding: EdgeInsets.all(32),
                child: Center(child: CircularProgressIndicator()),
              ),
            if (page != null && page.items.isEmpty)
              const Padding(
                padding: EdgeInsets.all(32),
                child: Center(child: Text('No pricing matrices yet.')),
              ),
            if (page != null)
              ...page.items.map(
                (m) => Card(
                  child: ListTile(
                    title: Text(m.name),
                    subtitle: Text(
                        '${m.rateCardCode} v${m.version} · ${m.productCode} · '
                        '${m.dimensionCode} · ${m.rowCount} band(s)'),
                    trailing: Chip(
                      label: Text(m.status),
                      visualDensity: VisualDensity.compact,
                    ),
                    onTap: () async {
                      await Navigator.of(context).push(
                        MaterialPageRoute(
                          builder: (_) => MatrixDetailScreen(
                              client: widget.client, matrixId: m.id),
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
                      '${(_offset ~/ pageSize) + 1} / ${(page.total / pageSize).ceil()}'),
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

class MatrixFormScreen extends StatefulWidget {
  const MatrixFormScreen(
      {super.key, required this.client, required this.rateCardId});

  final ApiClient client;
  final String rateCardId;

  @override
  State<MatrixFormScreen> createState() => _MatrixFormScreenState();
}

class _MatrixFormScreenState extends State<MatrixFormScreen> {
  final _formKey = GlobalKey<FormState>();
  final _name = TextEditingController();
  final _productCode = TextEditingController();
  final _productName = TextEditingController();
  List<DimensionSummary> _dimensions = const [];
  String? _dimensionCode;
  String? _error;
  bool _busy = false;

  @override
  void initState() {
    super.initState();
    _loadDimensions();
  }

  Future<void> _loadDimensions() async {
    try {
      final dims = await widget.client.listQualityDimensions();
      if (mounted) {
        setState(() => _dimensions = dims.where((d) => d.active).toList());
      }
    } on ApiException catch (e) {
      if (mounted) setState(() => _error = e.detail);
    }
  }

  Future<void> _submit() async {
    if (!_formKey.currentState!.validate()) return;
    setState(() {
      _busy = true;
      _error = null;
    });
    try {
      await widget.client.createMatrix(
        rateCardId: widget.rateCardId,
        name: _name.text.trim(),
        productCode: _productCode.text.trim().toUpperCase(),
        productName: _productName.text.trim(),
        dimensionCode: _dimensionCode!,
      );
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
      appBar: AppBar(title: const Text('New pricing matrix')),
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
                controller: _productCode,
                decoration: const InputDecoration(
                    labelText: 'Product code (must be in card scope)'),
                textCapitalization: TextCapitalization.characters,
                validator: (v) => (v == null || v.trim().length < 2)
                    ? 'Product code is required'
                    : null,
              ),
              const SizedBox(height: 12),
              TextFormField(
                controller: _productName,
                decoration:
                    const InputDecoration(labelText: 'Product name (optional)'),
              ),
              const SizedBox(height: 12),
              DropdownButtonFormField<String>(
                initialValue: _dimensionCode,
                decoration:
                    const InputDecoration(labelText: 'Quality dimension'),
                items: _dimensions
                    .map((d) => DropdownMenuItem(
                          value: d.code,
                          child: Text('${d.code} — ${d.name}'),
                        ))
                    .toList(),
                onChanged: (v) => setState(() => _dimensionCode = v),
                validator: (v) => v == null ? 'Pick a dimension' : null,
              ),
              const SizedBox(height: 20),
              if (_error != null)
                Padding(
                  padding: const EdgeInsets.only(bottom: 12),
                  child: Text(_error!,
                      style: TextStyle(
                          color: Theme.of(context).colorScheme.error)),
                ),
              FilledButton(
                onPressed: _busy ? null : _submit,
                child: Text(_busy ? 'Creating…' : 'Create'),
              ),
            ],
          ),
        ),
      ),
    );
  }
}

/// Matrix detail: price bands with a row editor while the card is draft.
class MatrixDetailScreen extends StatefulWidget {
  const MatrixDetailScreen(
      {super.key, required this.client, required this.matrixId});

  final ApiClient client;
  final String matrixId;

  @override
  State<MatrixDetailScreen> createState() => _MatrixDetailScreenState();
}

class _MatrixDetailScreenState extends State<MatrixDetailScreen> {
  MatrixDetailResult? _detail;
  String? _error;
  final _from = TextEditingController();
  final _to = TextEditingController();
  final _price = TextEditingController();

  @override
  void initState() {
    super.initState();
    _load();
  }

  Future<void> _load() async {
    try {
      final detail = await widget.client.matrixDetail(widget.matrixId);
      if (mounted) {
        setState(() {
          _detail = detail;
          _error = null;
        });
      }
    } on ApiException catch (e) {
      if (mounted) setState(() => _error = e.detail);
    }
  }

  void _toast(String message) {
    ScaffoldMessenger.of(context)
        .showSnackBar(SnackBar(content: Text(message)));
  }

  Future<void> _addRow() async {
    final from = double.tryParse(_from.text.trim());
    final to = double.tryParse(_to.text.trim());
    final price = double.tryParse(_price.text.trim());
    if (from == null || to == null || price == null) {
      _toast('Enter numeric from, to, and price values');
      return;
    }
    try {
      await widget.client.addMatrixRow(widget.matrixId,
          fromValue: from, toValue: to, unitPrice: price);
      _from.clear();
      _to.clear();
      _price.clear();
      await _load();
    } on ApiException catch (e) {
      _toast(e.detail);
    }
  }

  Future<void> _deleteRow(MatrixRowView row) async {
    try {
      await widget.client.deleteMatrixRow(widget.matrixId, row.id);
      await _load();
    } on ApiException catch (e) {
      _toast(e.detail);
    }
  }

  @override
  Widget build(BuildContext context) {
    final detail = _detail;
    return Scaffold(
      appBar: AppBar(title: Text(detail?.matrix.name ?? 'Pricing matrix')),
      body: detail == null
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
                    title: Text(
                        '${detail.matrix.rateCardCode} v${detail.matrix.version}'
                        ' · ${detail.matrix.productCode}'),
                    subtitle: Text('Dimension: ${detail.dimensionLabel}'),
                    trailing: Chip(
                      label: Text(detail.matrix.status),
                      visualDensity: VisualDensity.compact,
                    ),
                  ),
                ),
                const SizedBox(height: 8),
                Text('Price bands',
                    style: Theme.of(context).textTheme.titleMedium),
                const SizedBox(height: 4),
                if (detail.rows.isEmpty) const Text('No price bands yet.'),
                ...detail.rows.map(
                  (r) => Card(
                    child: ListTile(
                      dense: true,
                      leading: Icon(
                        r.active
                            ? Icons.check_circle_outline
                            : Icons.pause_circle_outline,
                        color: r.active ? Colors.green : Colors.grey,
                      ),
                      title: Text('[${r.fromValue} – ${r.toValue})'),
                      subtitle: Text('Unit price ${r.unitPrice}'),
                      trailing: detail.editable
                          ? IconButton(
                              icon: const Icon(Icons.delete_outline),
                              tooltip: 'Delete band',
                              onPressed: () => _deleteRow(r),
                            )
                          : null,
                    ),
                  ),
                ),
                if (detail.gaps.isNotEmpty)
                  Padding(
                    padding: const EdgeInsets.only(top: 8),
                    child: Text(
                      'Continuity gaps: ${detail.gaps.map((g) => '[${g['from_value']} – ${g['to_value']})').join(', ')}',
                      style: TextStyle(
                          color: Theme.of(context).colorScheme.tertiary),
                    ),
                  ),
                const SizedBox(height: 16),
                if (detail.editable) ...[
                  Text('Add band',
                      style: Theme.of(context).textTheme.titleMedium),
                  const SizedBox(height: 8),
                  Row(
                    children: [
                      Expanded(
                        child: TextField(
                          controller: _from,
                          decoration: const InputDecoration(labelText: 'From'),
                          keyboardType: TextInputType.number,
                        ),
                      ),
                      const SizedBox(width: 8),
                      Expanded(
                        child: TextField(
                          controller: _to,
                          decoration:
                              const InputDecoration(labelText: 'To (excl.)'),
                          keyboardType: TextInputType.number,
                        ),
                      ),
                      const SizedBox(width: 8),
                      Expanded(
                        child: TextField(
                          controller: _price,
                          decoration:
                              const InputDecoration(labelText: 'Unit price'),
                          keyboardType: TextInputType.number,
                        ),
                      ),
                    ],
                  ),
                  const SizedBox(height: 12),
                  FilledButton.tonal(
                    onPressed: _addRow,
                    child: const Text('Add band'),
                  ),
                ] else
                  Text(
                    'Read-only — this matrix follows its rate card and is no '
                    'longer draft.',
                    style: Theme.of(context).textTheme.bodySmall,
                  ),
              ],
            ),
    );
  }
}
