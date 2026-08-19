/// Where a sign-in lands (DEMO-012 §2, §12).
///
/// One application, three experiences, chosen by what the platform says this
/// principal may do.
///
/// **Why one app and not three.** The three roles differ in their screens and
/// agree in everything underneath: the same authentication, the same tenancy,
/// the same offline queue, the same API client, the same release pipeline.
/// Three applications would triplicate all of that so that each could hold one
/// folder the others do not — and the offline engine is the last thing in this
/// codebase that should exist in three slightly diverging copies. The work
/// order asks for shared code where practical and warns against creating
/// applications to make the architecture look larger; this is that judgement,
/// recorded.
///
/// **Why capabilities and not role names.** DEMO-008 made roles rows in a
/// database that an administrator may edit and add to. A client that switched
/// on `role == 'COLLECTION_OPERATOR'` would be wrong the moment somebody
/// created a role that does the same job under another name, which is exactly
/// what the registry exists to allow. So the routing below asks what the
/// principal CAN DO.
library;

import 'dart:async';

import 'package:flutter/material.dart';

import 'api.dart';
import 'centers.dart';
import 'customer_portal.dart';
import 'deliveries.dart';
import 'driver.dart';
import 'l10n.dart';
import 'offline/offline_client.dart';
import 'push.dart';
import 'session.dart';
import 'sign_out.dart';

/// Resolves the session, then shows the experience it earns.
class HomeRouter extends StatefulWidget {
  const HomeRouter({
    super.key,
    required this.client,
    this.pushTokens = const NoPushConfigured(),
  });

  final OfflineApiClient client;

  /// Where this build's push token comes from (DEMO-012 §10). The default
  /// supplies none, because no messaging vendor is wired — see `push.dart`.
  final PushTokenSource pushTokens;

  @override
  State<HomeRouter> createState() => _HomeRouterState();
}

class _HomeRouterState extends State<HomeRouter>
    with WidgetsBindingObserver {
  Session? _session;
  String? _error;

  @override
  void initState() {
    super.initState();
    WidgetsBinding.instance.addObserver(this);
    _resolve();
  }

  @override
  void dispose() {
    WidgetsBinding.instance.removeObserver(this);
    super.dispose();
  }

  /// Sync-on-resume (P1-MOBILE-COUNTER-001; audit D-13). The queue used to
  /// wait for a manual tap after any transport blip — one dead spot at 5 a.m.
  /// and every later capture silently queued all morning. Coming back to the
  /// app is the natural moment to try again. Fire-and-forget: `syncNow` is
  /// already idempotent (original keys, bounded backoff, no-op while a run is
  /// in flight), an expired session surfaces through the D-2 flow, and a
  /// failure simply leaves the queue for the next attempt.
  void _maybeSync() {
    if (widget.client.pendingCount > 0) {
      unawaited(() async {
        try {
          await widget.client.syncNow();
        } catch (_) {
          // The queue keeps the work; the next resume or manual sync retries.
        }
      }());
    }
  }

  @override
  void didChangeAppLifecycleState(AppLifecycleState state) {
    if (state == AppLifecycleState.resumed) _maybeSync();
  }

  Future<void> _resolve() async {
    setState(() => _error = null);
    try {
      final session = await loadSession(widget.client);
      if (!mounted) return;
      setState(() => _session = session);
      // Signing in is also such a moment: whatever queued before this login
      // replays now, re-authorized by the platform under this session.
      _maybeSync();
      // After the session, never before: the platform binds the handset to
      // the authenticated principal, and a registration sent before sign-in
      // has nobody to belong to. Deliberately not awaited into the screen's
      // loading state — being reachable by push is a nice-to-have and must
      // not hold up a rider's round.
      unawaited(
        registerForPush(
          widget.client,
          source: widget.pushTokens,
          label: session.email,
        ),
      );
    } catch (e) {
      if (!mounted) return;
      setState(
        () => _error =
            'Signed in, but the platform could not say what you may do. '
            'Check the connection and try again.',
      );
    }
  }

  @override
  Widget build(BuildContext context) {
    if (_error != null) {
      return Scaffold(
        body: Center(
          child: Padding(
            padding: const EdgeInsets.all(24),
            child: Column(
              mainAxisSize: MainAxisSize.min,
              children: [
                Text(_error!, textAlign: TextAlign.center),
                const SizedBox(height: 16),
                FilledButton(
                  onPressed: _resolve,
                  child: const Text('Try again'),
                ),
              ],
            ),
          ),
        ),
      );
    }
    final session = _session;
    if (session == null) {
      return const Scaffold(body: Center(child: CircularProgressIndicator()));
    }
    // DEMO-014 §9: the whole experience takes its direction from the person's
    // language, once, here. Wrapping at the router rather than per screen is
    // the point — a screen that had to remember would eventually forget, and
    // a half-mirrored app is worse than an unmirrored one.
    return Directionality(
      textDirection: directionFor(session),
      child: _experience(session),
    );
  }

  Widget _experience(Session session) {
    return switch (experienceFor(session)) {
      Experience.customer => CustomerHomeScreen(
        client: widget.client,
        session: session,
      ),
      Experience.driver => DriverHomeScreen(
        client: widget.client,
        session: session,
      ),
      Experience.delivery => DeliveryRoundScreen(
        client: widget.client,
        session: session,
      ),
      Experience.collection => CentersListScreen(client: widget.client),
      Experience.none => _NothingToDo(session: session, client: widget.client),
    };
  }
}

/// Signed in, and holding nothing this app offers.
///
/// An honest dead end rather than a screen that 403s on every request. A
/// finance officer's grants are real and useful — in the web portal.
class _NothingToDo extends StatelessWidget {
  const _NothingToDo({required this.session, required this.client});

  final Session session;
  final ApiClient client;

  @override
  Widget build(BuildContext context) {
    return Scaffold(
      // The dead end especially needs the way out (D-2): the person this
      // screen greets is on the wrong account by definition.
      appBar: AppBar(
        title: const Text('Lacteva'),
        actions: [SignOutButton(client: client)],
      ),
      body: Center(
        child: Padding(
          padding: const EdgeInsets.all(32),
          child: Column(
            mainAxisSize: MainAxisSize.min,
            children: [
              Icon(
                Icons.phonelink_off,
                size: 48,
                color: Theme.of(context).disabledColor,
              ),
              const SizedBox(height: 16),
              Text(
                'Nothing for this account on mobile',
                style: Theme.of(context).textTheme.titleMedium,
                textAlign: TextAlign.center,
              ),
              const SizedBox(height: 8),
              Text(
                'Signed in as ${session.email}. This app covers milk '
                'collection, the delivery round, and a customer\'s own '
                'account. Everything else is in the web portal.',
                textAlign: TextAlign.center,
              ),
            ],
          ),
        ),
      ),
    );
  }
}
