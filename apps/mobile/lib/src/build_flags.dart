import 'package:flutter/foundation.dart';

/// Whether this build may offer simulated scale and analyzer readings.
///
/// SEC-003 / F-01. The mock capture controls fabricate a weight and a quality
/// reading from a hash of the container id. Those numbers are priced,
/// settled, paid and receipted exactly like measured ones, and nothing
/// downstream can tell them apart — so a release build must not offer them,
/// and the buttons were previously unconditional.
///
/// A compile-time `const`, deliberately: `if (kMockHardwareEnabled)` around a
/// widget subtree is const-folded, so a release build does not merely hide
/// the controls — it does not contain them. Debug and profile builds keep
/// them, because that is what they were written for.
///
/// Overridable in either direction so both states are testable by execution:
///     flutter test --dart-define=LACTEVA_ALLOW_MOCK_HARDWARE=false
///
/// The app-side gate is a convenience, not the boundary. The platform refuses
/// `mock_scale` and `mock_analyzer` in production regardless of what any
/// client sends, so a rebuilt or patched app gains nothing.
const bool kMockHardwareEnabled = bool.fromEnvironment(
  'LACTEVA_ALLOW_MOCK_HARDWARE',
  defaultValue: !kReleaseMode,
);
