# mobile

Flutter application for field users — the future home of Lacteva Collect's operator experience (shift control, member check-in, collection recording per `docs/13-products/lacteva-collect/`).

**Status: scaffold pending (roadmap M2).** Generate with official tooling:

```bash
cd apps/mobile
flutter create . --org com.lacteva --project-name lacteva_mobile --platforms android,ios
```

Non-negotiable architecture constraints (from the product package, before any feature code):

- **Offline-first** (Collect rule R09): local queue + sync engine is the first infrastructure slice, not an afterthought.
- **Localization from day one** (`flutter_localizations` + ARB files; locales en/sw/hi to start, per platform i18n).
- Auth against platform-core (`/v1/auth/token` + refresh), tenant-scoped.
- TODO(M2): device-profile abstraction for hardware integration (scale/analyzer, PSP-0007) behind a platform channel interface.
