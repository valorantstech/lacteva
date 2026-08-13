import 'package:flutter/material.dart';
import 'package:qr_flutter/qr_flutter.dart';

import 'api.dart';

/// Supplier CRUD — SPRINT-005.
class SuppliersListScreen extends StatefulWidget {
  const SuppliersListScreen({super.key, required this.client});

  final ApiClient client;

  @override
  State<SuppliersListScreen> createState() => _SuppliersListScreenState();
}

class _SuppliersListScreenState extends State<SuppliersListScreen> {
  static const pageSize = 20;
  final _search = TextEditingController();
  SupplierPageResult? _page;
  int _offset = 0;
  String? _error;

  @override
  void initState() {
    super.initState();
    _load();
  }

  Future<void> _load() async {
    try {
      final page = await widget.client.listSuppliers(
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
    }
  }

  Future<void> _openForm({SupplierSummary? supplier}) async {
    final changed = await Navigator.of(context).push<bool>(
      MaterialPageRoute(
        builder: (_) =>
            SupplierFormScreen(client: widget.client, supplier: supplier),
      ),
    );
    if (changed == true) await _load();
  }

  @override
  Widget build(BuildContext context) {
    final page = _page;
    return Scaffold(
      appBar: AppBar(title: const Text('Suppliers')),
      floatingActionButton: FloatingActionButton(
        onPressed: () => _openForm(),
        tooltip: 'New supplier',
        child: const Icon(Icons.person_add),
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
                hintText: 'Search name, code, or phone',
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
                child: Center(child: Text('No suppliers match.')),
              ),
            if (page != null)
              ...page.items.map(
                (s) => Card(
                  child: ListTile(
                    title: Text(s.fullName),
                    subtitle: Text('${s.code} · ${s.status}'),
                    trailing: IconButton(
                      icon: const Icon(Icons.edit_outlined),
                      tooltip: 'Edit',
                      onPressed: () => _openForm(supplier: s),
                    ),
                    onTap: () => Navigator.of(context).push(
                      MaterialPageRoute(
                        builder: (_) => SupplierDetailScreen(
                          client: widget.client,
                          supplierId: s.id,
                        ),
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

class SupplierFormScreen extends StatefulWidget {
  const SupplierFormScreen({super.key, required this.client, this.supplier});

  final ApiClient client;
  final SupplierSummary? supplier;

  bool get isEdit => supplier != null;

  @override
  State<SupplierFormScreen> createState() => _SupplierFormScreenState();
}

class _SupplierFormScreenState extends State<SupplierFormScreen> {
  final _formKey = GlobalKey<FormState>();
  late final TextEditingController _name = TextEditingController(
    text: widget.supplier?.fullName ?? '',
  );
  late final TextEditingController _phone = TextEditingController(
    text: widget.supplier?.phone ?? '',
  );
  final _village = TextEditingController();
  String? _error;
  bool _busy = false;

  Future<void> _submit() async {
    if (!_formKey.currentState!.validate()) return;
    setState(() {
      _busy = true;
      _error = null;
    });
    try {
      if (widget.isEdit) {
        await widget.client.updateSupplier(
          widget.supplier!.id,
          fullName: _name.text.trim(),
          phone: _phone.text.trim(),
          village: _village.text.trim(),
        );
      } else {
        await widget.client.createSupplier(
          fullName: _name.text.trim(),
          phone: _phone.text.trim(),
          village: _village.text.trim(),
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
          widget.isEdit ? 'Edit ${widget.supplier!.code}' : 'New supplier',
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
                decoration: const InputDecoration(labelText: 'Full name'),
                validator: (v) => (v == null || v.trim().length < 2)
                    ? 'Name needs at least 2 characters'
                    : null,
              ),
              const SizedBox(height: 12),
              TextFormField(
                controller: _phone,
                decoration: const InputDecoration(labelText: 'Phone'),
                keyboardType: TextInputType.phone,
              ),
              const SizedBox(height: 12),
              TextFormField(
                controller: _village,
                decoration: const InputDecoration(labelText: 'Village'),
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

/// Detail with status actions and the supplier QR (rendered client-side).
class SupplierDetailScreen extends StatefulWidget {
  const SupplierDetailScreen({
    super.key,
    required this.client,
    required this.supplierId,
  });

  final ApiClient client;
  final String supplierId;

  @override
  State<SupplierDetailScreen> createState() => _SupplierDetailScreenState();
}

class _SupplierDetailScreenState extends State<SupplierDetailScreen> {
  SupplierDetailResult? _detail;
  String? _error;

  @override
  void initState() {
    super.initState();
    _load();
  }

  Future<void> _load() async {
    try {
      final detail = await widget.client.supplierDetail(widget.supplierId);
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

  Future<void> _setStatus(String status) async {
    try {
      await widget.client.setSupplierStatus(widget.supplierId, status);
      await _load();
    } on ApiException catch (e) {
      if (!mounted) return;
      ScaffoldMessenger.of(
        context,
      ).showSnackBar(SnackBar(content: Text(e.detail)));
    }
  }

  @override
  Widget build(BuildContext context) {
    final detail = _detail;
    return Scaffold(
      appBar: AppBar(title: Text(detail?.supplier.fullName ?? 'Supplier')),
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
                    title: Text(detail.supplier.code),
                    subtitle: Text(
                      '${detail.supplier.status} · ${detail.supplier.phone}'
                      '${detail.village.isNotEmpty ? ' · ${detail.village}' : ''}',
                    ),
                  ),
                ),
                Wrap(
                  spacing: 8,
                  children: [
                    if (detail.supplier.status == 'draft' ||
                        detail.supplier.status == 'suspended')
                      FilledButton.tonal(
                        onPressed: () => _setStatus('active'),
                        child: const Text('Activate'),
                      ),
                    if (detail.supplier.status == 'active')
                      FilledButton.tonal(
                        onPressed: () => _setStatus('suspended'),
                        child: const Text('Suspend'),
                      ),
                  ],
                ),
                const SizedBox(height: 8),
                Text(
                  '${detail.centerIds.length} collection center(s) assigned',
                  style: Theme.of(context).textTheme.bodyMedium,
                ),
                const SizedBox(height: 16),
                Center(
                  child: Card(
                    child: Padding(
                      padding: const EdgeInsets.all(16),
                      child: Column(
                        children: [
                          QrImageView(
                            data: detail.qrPayload,
                            size: 220,
                            backgroundColor: Colors.white,
                          ),
                          const SizedBox(height: 8),
                          Text(
                            detail.supplier.code,
                            style: Theme.of(context).textTheme.titleMedium,
                          ),
                        ],
                      ),
                    ),
                  ),
                ),
              ],
            ),
    );
  }
}
