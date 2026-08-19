import 'package:flutter/material.dart';

import 'api.dart';
import 'centers.dart' show LoginScreen;
import 'offline/offline_client.dart';

/// The explicit way out of a session on a shared handset (P0-PRODUCT-008
/// D-2). One phone serves a shift at a dairy; before this button existed the
/// only way to change operator was to kill the process.
///
/// Signing out forgets the token (and hands back any push token, best
/// effort) — it deliberately does NOT touch the offline queue: captured milk
/// and deliveries survive the sign-out and replay idempotently under whoever
/// signs in next, with the platform re-authorizing every operation.
class SignOutButton extends StatelessWidget {
  const SignOutButton({super.key, required this.client, this.label});

  final ApiClient client;

  /// Translated tooltip where the screen has a catalog ('common.signOut');
  /// plain English on the screens that do not translate yet.
  final String? label;

  Future<void> _signOut(BuildContext context) async {
    final c = client;
    if (c is OfflineApiClient) {
      await c.signOut();
      if (!context.mounted) return;
      await Navigator.of(context).pushAndRemoveUntil(
        MaterialPageRoute(builder: (_) => LoginScreen(client: c)),
        (route) => false,
      );
    } else {
      // A bare ApiClient (tests, embedding) has no queue to carry to the
      // login screen — forget the token and unwind to the root.
      c.logout();
      if (!context.mounted) return;
      Navigator.of(context).popUntil((route) => route.isFirst);
    }
  }

  @override
  Widget build(BuildContext context) {
    return IconButton(
      icon: const Icon(Icons.logout),
      tooltip: label ?? 'Sign out',
      onPressed: () => _signOut(context),
    );
  }
}
