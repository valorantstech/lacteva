import 'package:flutter/material.dart';

import 'brand/auth_backdrop.dart';
import 'brand/auth_lockup.dart';
import 'brand/auth_motion.dart';

import 'api.dart';
import 'l10n.dart';
import 'theme.dart';

/// Reset a forgotten password from the handset (LACTEVA-ADMIN-003).
///
/// Two steps on one screen: ask for a code, then spend it. The backend flow
/// has existed, rate-limited and enumeration-safe, since before either client
/// shipped — and neither login surface offered it, so a locked-out operator at
/// 5 a.m. was a phone call to somebody who might not answer.
///
/// **The enumeration rule is the design, not a detail.** The platform answers
/// 202 for an address it has never seen exactly as it does for one it knows,
/// and this screen must not undo that: there is no "no such account" state, no
/// different heading, no different next step. Whoever typed the address gets
/// the same sentence either way, and only their inbox can tell them apart.
///
/// The one refusal worth showing is the rate limit — it is IP-based, says
/// nothing about any account, and "try again later" is something a person can
/// act on.
class PasswordResetScreen extends StatefulWidget {
  const PasswordResetScreen({super.key, required this.client, this.session});

  final ApiClient client;

  /// Language only — nobody is signed in here, so this is normally null and
  /// the screen renders English (P1-LOCALE-I18N-001).
  final Object? session;

  @override
  State<PasswordResetScreen> createState() => _PasswordResetScreenState();
}

class _PasswordResetScreenState extends State<PasswordResetScreen> {
  final _email = TextEditingController();
  final _code = TextEditingController();
  final _password = TextEditingController();
  final _confirm = TextEditingController();
  bool _codeSent = false;
  bool _busy = false;
  String? _error;

  /// WO-36: the confirmation does not match. Held apart from `_error`, which
  /// carries what the PLATFORM said — this is the one problem this screen can
  /// see for itself, and it belongs under the field that has it rather than
  /// in the slot reserved for the platform's own refusals.
  String? _mismatch;

  L10n get _l => L10n.of(null);

  /// The platform's refusal, or an honest transport failure — never silence.
  /// A save that fails in transit must SAY SO (R-1), and the structural guard
  /// in `save_transport_error_test.dart` enforces exactly this shape.
  void _fail(Object err) {
    if (!mounted) return;
    setState(() {
      if (err is ApiException) {
        _error = err.status == 429 ? _l.t('auth.resetTooMany') : err.detail;
      } else {
        _error = _l.t('common.couldNotReach');
      }
    });
  }

  Future<void> _requestCode() async {
    final email = _email.text.trim();
    if (email.isEmpty) return;
    setState(() {
      _busy = true;
      _error = null;
    });
    try {
      await widget.client.requestPasswordReset(email);
      if (mounted) setState(() => _codeSent = true);
    } on ApiException catch (e) {
      _fail(e);
    } catch (e) {
      // Transport failure is not a platform refusal (P0-PRODUCT-008 D-1).
      _fail(e);
    } finally {
      if (mounted) setState(() => _busy = false);
    }
  }

  void _clearMismatch() {
    if (_mismatch != null) setState(() => _mismatch = null);
  }

  Future<void> _submitNewPassword() async {
    // The one mistake this screen can catch before it costs somebody their
    // only way in: a typo in a secret nobody can read back. Caught HERE, so
    // the platform is never asked and the reset code is not spent on it.
    if (_password.text != _confirm.text) {
      setState(() => _mismatch = _l.t('auth.resetMismatch'));
      return;
    }
    setState(() {
      _busy = true;
      _error = null;
      _mismatch = null;
    });
    try {
      await widget.client.confirmPasswordReset(
        _code.text.trim(),
        _password.text,
      );
      if (!mounted) return;
      // Back to sign-in, carrying the reason — the `notice` parameter the
      // LoginScreen already has for exactly this kind of hand-off.
      Navigator.of(context).pop(_l.t('auth.resetDone'));
    } on ApiException catch (e) {
      _fail(e);
    } catch (e) {
      // Transport failure is not a platform refusal (P0-PRODUCT-008 D-1).
      _fail(e);
    } finally {
      if (mounted) setState(() => _busy = false);
    }
  }

  @override
  void dispose() {
    _email.dispose();
    _code.dispose();
    _confirm.dispose();
    _password.dispose();
    super.dispose();
  }

  @override
  Widget build(BuildContext context) {
    final t = _l;
    // WO-33: the same ground and the same entrance as sign-in. The two
    // screens are one moment as far as anybody using them is concerned, and
    // arriving here used to feel like leaving the product.
    return Scaffold(
      appBar: AppBar(
        title: Text(t.t('auth.resetTitle')),
        // The ground runs under the bar, so the bar shows it.
        backgroundColor: LactevaColors.transparent,
        elevation: 0,
      ),
      extendBodyBehindAppBar: true,
      body: AuthBackdrop(
        child: Center(
        child: SingleChildScrollView(
          padding: const EdgeInsets.all(24),
          child: ConstrainedBox(
            constraints: const BoxConstraints(maxWidth: 420),
            child: Column(
              crossAxisAlignment: CrossAxisAlignment.stretch,
              children: [
                // WO-36: the same face sign-in wears. A locked-out operator
                // was leaving the product to get back into it.
                const AuthLockup(),
                if (!_codeSent) ...[
                  FocusGlow(
                    child: TextField(
                      controller: _email,
                      decoration: InputDecoration(labelText: t.t('auth.email')),
                      keyboardType: TextInputType.emailAddress,
                    ),
                  ),
                ] else ...[
                  // The same words whatever the platform found.
                  Padding(
                    padding: const EdgeInsets.only(bottom: 16),
                    child: Text(
                      t.t('auth.resetSent', {'email': _email.text.trim()}),
                    ),
                  ),
                  FocusGlow(
                    child: TextField(
                      controller: _code,
                      decoration: InputDecoration(
                        labelText: t.t('auth.resetCode'),
                      ),
                    ),
                  ),
                  const SizedBox(height: 12),
                  FocusGlow(
                    child: TextField(
                      controller: _password,
                      decoration: InputDecoration(
                        labelText: t.t('auth.resetNewPassword'),
                        helperText: t.t('auth.resetMinLength'),
                      ),
                      obscureText: true,
                      // Typing again clears the complaint rather than leaving
                      // it under a field the person has already fixed.
                      onChanged: (_) => _clearMismatch(),
                    ),
                  ),
                  const SizedBox(height: 12),
                  FocusGlow(
                    child: TextField(
                      controller: _confirm,
                      decoration: InputDecoration(
                        labelText: t.t('auth.resetConfirmPassword'),
                        errorText: _mismatch,
                      ),
                      obscureText: true,
                      onChanged: (_) => _clearMismatch(),
                    ),
                  ),
                ],
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
                PressDip(
                  enabled: !_busy,
                  child: FilledButton(
                    onPressed: _busy
                        ? null
                        : (_codeSent ? _submitNewPassword : _requestCode),
                    child: Text(
                      _codeSent
                          ? t.t('auth.resetSubmit')
                          : t.t('auth.resetSendCode'),
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
