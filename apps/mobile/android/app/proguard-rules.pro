# PORTAL-001 / F-05. Flutter's engine is reached by reflection from the
# platform side, so it must survive shrinking. Everything else is Dart, which
# is AOT-compiled and untouched by R8.
-keep class io.flutter.** { *; }
-keep class io.flutter.plugins.** { *; }

# WO-67. The Flutter engine's Play Store deferred-component support
# (`io.flutter.embedding.engine.deferredcomponents.*`) references
# `com.google.android.play.core.splitcompat`, `.splitinstall` and `.tasks`,
# and this app does not ship that library because it does not use deferred
# components — every screen is in the one APK. R8 sees the references, cannot
# find the classes, and refuses to build ("Missing classes detected while
# running R8"). The references are unreachable at runtime for exactly the
# reason the classes are absent, so telling R8 not to warn is the correct fix,
# not a suppression: there is nothing to keep and nothing to load.
#
# One wildcard rather than the eleven literal `-dontwarn` lines R8 wrote to
# build/app/outputs/mapping/release/missing_rules.txt, because the eleven are
# whichever classes THIS engine version happens to touch and the next Flutter
# upgrade would leave the list stale. The package is the invariant.
#
# This was the first release build this project ever ran (the previous
# evidence was four tests against the Gradle contract), and it did not
# compile. `flutter build apk --no-shrink` does not help: minification is set
# in build.gradle.kts, so the flag is ignored.
-dontwarn com.google.android.play.core.**
