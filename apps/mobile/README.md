# mobile

Lacteva Flutter application — **one app, three field experiences**, chosen by what the platform says the signed-in principal may do:

| Who | Screen | Entry |
| --- | --- | --- |
| Collection operator | the centre, sessions, collection | `lib/src/centers.dart` |
| Delivery rider | today's round, one tap per household | `lib/src/deliveries.dart` |
| Customer | their own deliveries, balance, bills, receipts | `lib/src/customer_portal.dart` |

`lib/src/home.dart` routes a sign-in by **capability, never by role name** — roles are editable database rows (DEMO-008), so `role == 'COLLECTION_OPERATOR'` would be wrong the moment an administrator created a role doing the same job under another name.

The app is a *client*: no pricing, no billing, no settlement, no payment, no tenancy logic, and it never recomputes a financial figure the platform has already produced. The architecture, and why, is [docs/03-architecture/04-technology-layer/MOBILE-EXPERIENCES.md](../../docs/03-architecture/04-technology-layer/MOBILE-EXPERIENCES.md).

Scaffolded with `flutter create` (org `com.lacteva`, project `lacteva_mobile`, platforms android/ios/web), Flutter 3.38 stable.

## Run

```bash
flutter devices                                            # list targets
flutter run --dart-define=LACTEVA_API_URL=http://10.0.2.2:8000   # Android emulator
flutter run -d chrome --dart-define=LACTEVA_API_URL=http://localhost:8000
# or from the repo root: make mobile [DEVICE=<id>]
```

`10.0.2.2` is the Android emulator's route to the host machine. The API URL is a compile-time define (`lib/main.dart`), defaulting to `http://localhost:8000`.

## Quality gates (CI-enforced)

```bash
flutter analyze
flutter test
```

## Architecture constraints before feature work (from the Collect package)

- **Offline-first** (rule R09): the local queue + sync engine is the first M2 infrastructure slice — features must not assume connectivity.
- **Localization from day one**: `flutter_localizations` + ARB files (en/sw/hi to start), matching platform i18n.
- Auth against platform-core (`/v1/auth/token` + refresh), tenant-scoped.
- Hardware integration (scales/analyzers per PSP-0007) goes behind a device-profile platform-channel interface — M2+.

## Push notifications

Off by design. No messaging vendor is chosen or paid for, so `PushTokenSource`
defaults to `NoPushConfigured` (supplies no token, registers nothing) and the
server's `LACTEVA_NOTIFICATION_PUSH_PROVIDER` defaults to `disabled`. To wire
FCM: add `firebase_messaging`, drop in `google-services.json` /
`GoogleService-Info.plist`, implement `PushTokenSource` over `getToken()`, and
configure the server. `registerForPush` already runs after sign-in and
`revokePush` on sign-out — see `lib/src/push.dart`.

**No credential lives in this app.** The API base URL is a compile-time
define; the release keystore comes from `android/key.properties`, which is
gitignored, and a release build fails rather than falling back to debug
signing.

## Staying signed in

The platform issues a fourteen-day session. Since 2026-09-04 the app keeps it
in the device's encrypted store (`flutter_secure_storage`) and restores it at
launch, so a restart is not a sign-out. The session ends on **Sign out** (More
tab) or when the platform refuses a refresh; nothing else forgets it. See
`lib/src/session_store.dart` and `lib/src/startup.dart`.

## Release builds

```bash
flutter build apk --debug                 # works with no keystore
flutter build apk --release               # REFUSES without android/key.properties

# WO-63: the address a distributed build must carry.
flutter build apk --release \
  --dart-define=LACTEVA_API_URL=https://api.lacteva.com
# WO-67: is it signed by Phoenix Software, with the same key as last time?
../../infra/ci/verify-release-apk.sh build/app/outputs/flutter-apk/app-release.apk
```

**The first release build (WO-67, 2026-09-03) failed twice**, on things no
test that read the build file could see: `storeFile` in `key.properties` is
relative to `android/app/` (so a keystore beside the file is
`../lacteva-release.jks`), and R8 refused the Flutter engine's references to
Play Core deferred components, which this app does not ship —
`proguard-rules.pro` now says `-dontwarn com.google.android.play.core.**`
and why. CI builds a release APK on every push with a throwaway key so the
path stays walked; `.github/workflows/release-apk.yml` signs the real one.
Details in DEPLOYMENT.md → *Mobile release builds*.

**`https://api.lacteva.com` is the API address, and the only one.** It has its
own name rather than sharing `app.lacteva.com` because this constant is
compiled in: changing it means a store release and breaks every install until
each one updates, so it is the one address that has to be repointable with a
DNS record instead.

**`https://dev.phoenixsoft.in` was retired on 2026-09-03** (owner's decision).
It is not served and not redirected — a 301 is not followed with method and
body intact by an HTTP client POSTing to `/v1/`, so a redirect would have been
an outage that looked like a courtesy. **Every handset still carrying a build
made against the old name has lost its server and needs this APK
reinstalled.** That is the cost the compile-time constant imposes, and it is
the reason `api.lacteva.com` exists: the next move is a DNS record.

The refusal is deliberate (PORTAL-001 / F-05): a debug-signed APK is not
distributable and cannot be upgraded. The guard fires from the Gradle task
graph, not from the release configuration block — a check there is evaluated
for `assembleDebug` too and blocks every build (DEMO-012).
