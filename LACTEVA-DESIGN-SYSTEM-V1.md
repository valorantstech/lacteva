---
id: LACTEVA-DESIGN-SYSTEM-V1
title: Lacteva Design System V1
type: reference
status: Approved
version: "1.1"
owner: Engineering
created: 2026-08-26
last-updated: 2026-08-26
related: [LACTEVA-P1-PRODUCT-READINESS-AUDIT, LACTEVA-P1-LOCALE-I18N-001, LACTEVA-MASTER-PRODUCT-ROADMAP]
baseline: ARCH-BASELINE-V1
---

# Lacteva Design System V1

## 1. What was actually there

The audit that preceded this is the reason it looks the way it does.

**The portal had no design system.** Every colour token was `oklch(L 0 0)` —
stock shadcn greyscale, zero chroma, `--primary` a near-black, all five chart
colours grey. It was an unstyled scaffold that forty pages had been built on.

**The brand existed, in two places, and not there.** The mobile app seeded
Material from `#1B5E20`, and the marketing site had an authored green-on-cream
palette. Neither had ever reached the product.

So V1 is not a repaint. It is the first time Lacteva has one visual language,
and the leverage came from a fact about the existing code: all forty pages
already consume semantic tokens (`bg-background`, `text-muted-foreground`,
`bg-primary`). **Redefining the token values makes the entire product Lacteva
without editing a single page.** That is why this milestone changed
foundations and showcase, and left production screens alone.

## 2. The idea

Milk over cream, deep dairy green, and motion that settles the way liquid does.

Three decisions carry most of it:

**Milk on cream, not white on grey.** Cards are true milk white; the page
beneath is warm cream. Surface hierarchy is legible before a single border is
drawn, and the whole product feels warm rather than clinical — a dairy, not a
fintech.

**Ink is green-black.** The darkest text is `oklch(0.23 0.025 150)`, not
neutral black. Even the heaviest type belongs to the brand family, and dark
bands still read as Lacteva.

**Chroma is spent, not sprinkled.** Everything an operator stares at for eight
hours is low-chroma; saturation is reserved for what must be noticed. A
saturated interface is a tiring one, and these are eight-hour shifts under bad
lighting.

## 3. Tokens

| Group | Tokens |
|---|---|
| Foundations | `--milk` `--cream` `--background` `--foreground` `--card` `--popover` |
| Brand | `--dairy` `--dairy-deep` `--fresh` `--water` `--amber` |
| Semantic | `--success` `--warning` `--destructive` `--info` (+ `-foreground` pairs) |
| Intelligence | `--intelligence` `--intelligence-foreground` |
| Structure | `--border` `--input` `--ring` `--radius` `--ink` |
| Charts | `--chart-1` … `--chart-5`, five hues distinguishable by more than lightness |
| Elevation | `--elevation-1..3`, green-tinted |
| Motion | `--motion-instant/fast/base/slow/flow`, `--ease-standard/out-liquid/in-out-liquid` |

Both faces are defined: light, and a dark face where the ground is deep
green-black and chroma rises slightly, because colour reads weaker on dark.

**Shadows are green-tinted.** A neutral black shadow over a warm ground reads
as dirt.

## 4. The milk motion language

Defined once, in `globals.css`, so no component invents its own timing.

| Keyframe | What it says |
|---|---|
| `lacteva-settle` | Something arrived — rises and settles |
| `lacteva-fill` | Progress as a vessel filling |
| `lacteva-drop` | The completion beat: a drop falling into place |
| `lacteva-flow` | Something is moving — sync draining, skeleton loading |
| `lacteva-attend` | The intelligence signal: a slow breath, never a blink |

Everything eases out long and arrives softly (`--ease-out-liquid`). That curve
is what separates this from the linear snap of a generic dashboard, and it is
the most recognisable thing in the system.

**The governing rule: motion may express state, never delay work.** An operator
with a queue of farmers must never wait for an animation. Anything on the
critical path runs at `--motion-fast` (160 ms) or less — enforced by test. The
slow liquid timings are reserved for things genuinely in progress.

A blinking badge reads as an alarm, so the intelligence signal breathes at
2.4 s instead.

## 5. The intelligence language

Lacteva computes exactly one such thing today: a statistical deviation flag on
collection quality. Everything else in that family is an unbuilt roadmap entry.
So the component is built to make overclaiming *hard*:

- **Indigo, used nowhere else.** A computed signal cannot be mistaken for
  success, warning, brand or water — asserted by test (>30° from every other
  hue).
- **It tints and outlines; it never fills.** An interface that glows whenever
  software had an opinion trains people to ignore it.
- **`basis` is a required prop.** An insight without its reason is an oracle,
  and nobody can act on an oracle.
- **There is no "available" prop.** A roadmap capability gets
  `<ComingSoonInsight>`, which says so in words.

The claims guards remain the enforcement. This is the shape that makes passing
them the natural thing to do — and the guard caught this milestone's own draft
comment, which was reworded rather than the guard weakened.

## 6. Components

**New primitives**

| Component | Why it exists |
|---|---|
| `Skeleton` / `SkeletonRows` | The audit found four pages that render nothing while fetching (UX-1). A blank screen is indistinguishable from a broken one. Shows the shape of what is coming, so the page does not jump. |
| `LiquidProgress` | The house progress shape — fills like a vessel. Vertical, so it has no direction to get wrong in RTL. Percentage always rendered. |
| `SyncIndicator` | The one status an operator must never guess. Word always rendered, count always rendered, `aria-live="polite"`, and only `syncing` animates. |
| `Insight` / `ComingSoonInsight` | §5. |

**Unchanged and deliberately reused:** `Money`, `Quantity`, `StatusBadge`,
`DataTable`, `EmptyState`, `ErrorState`, `EntityPicker`, `PageHeader`,
`AppShell`, and the shadcn primitives. V1 changed what they *look* like by
changing tokens, not what they *are*.

## 7. Mobile is not the portal, smaller

Shared: the palette, and the motion timings — pinned by a test that reads the
portal's own stylesheet, so the two clients cannot drift into two products.

Deliberately different, and pinned so a future "let's be consistent" cannot
shrink them:

- **48 dp minimum touch target** (above the 44 dp platform floor) — the
  operator may be gloved, hurried, or both.
- **56 dp primary action**, larger again: "what do I press next" should never
  be a question mid-collection.
- **Body type ≥ 16 pt**, a step above Material's default. Bright daylight on a
  cheap screen costs more legibility than any font choice recovers.
- **Generous fields.** Typing is the slowest thing an operator does.

## 8. Localization

The system is built on **logical properties**, so right-to-left is a direction
change rather than a redesign. The showcase carries a live RTL panel.

- No component hard-codes a physical side.
- Every user-visible string in the new components is a **prop with an English
  fallback**, never a baked-in literal — so they are translatable the day the
  catalogs reach those pages.
- `LiquidProgress` is vertical, which sidesteps direction entirely.
- Numerals stay Latin and money keeps the platform's exact decimal string
  (`formatAmount` is untouched, and its guards still pass).

**Not claimed:** this milestone did not localize the 26 English-only pages.
That is P1-LOCALE-I18N-002 and remains open.

## 9. Accessibility

| Requirement | How |
|---|---|
| Contrast | **Executable.** `design-system.test.ts` computes WCAG ratios from OKLCH for 12 pairs in both faces. Body text ≥ 7:1, all semantic labels ≥ 4.5:1 |
| Colour never alone | Preserved from `foundation.test.tsx`; `SyncIndicator` renders a shape *and* a word; `StatusBadge` unchanged |
| Focus | A visible two-colour ring on every interactive element, defined once in `@layer base` |
| Reduced motion | One global `prefers-reduced-motion` block, asserted by test — components cannot forget it |
| Touch targets | 48 dp minimum on mobile, asserted by test |
| Screen readers | `role="status"` + `aria-live="polite"` on sync; `progressbar` with value and label; skeletons `aria-hidden` with one polite announcement for the block |

**The contrast guard found a real defect in this milestone's own palette:**
white on amber measured 3.59:1, below AA. The amber was changed to take ink
rather than the threshold being lowered.

## 10. What was NOT changed

- **No production screen was redesigned.** All 40 portal pages and every mobile
  screen render through the new tokens without their code being touched.
- **No functional behaviour, API contract, route, permission or business rule.**
- **No roadmap capability** was implemented, implied or re-labelled.
- **No animation was added to an existing screen.** The motion language exists
  and is demonstrated; applying it screen by screen is deliberate future work.
- **The 26 English-only pages** remain English-only (P1-LOCALE-I18N-002).
- **UX-1's four pages** still lack loading states — `Skeleton` now exists to
  fix them, but wiring it into production pages is a change to those pages.

## 11. V1.1 — the visual refinement pass

Review of the rendered page found V1 **technically sound but flat and
documentation-like**: uniformly small type, a border on everything, and a milk
language represented by one small progress bar. The foundations were right and
the surface was under-built. V1.1 rebuilds the surface without touching the
foundations.

**Typography.** A `clamp()` scale replaces the flat sizing — display 32→48,
page 26→36, section 18→24, metric 28→40, metadata 13. Responsive by
construction rather than a desktop scale that shrinks badly, with mobile floors
chosen for daylight legibility and pinned by test.

**Depth instead of outlines.** Seven card tones (`quiet`, `metric`, `insight`,
`operational`, `warning`, `live`, `hero`) that separate by elevation and
surface rather than by drawing a line around everything. When every card is a
bordered rectangle, nothing is more important than anything else.

**Gradients, disciplined.** Five, each two steps of ONE family — milk→cream,
cream→fresh, dairy→deep, intelligence tint, water→aqua — all at a constant
150° so surfaces feel lit from one direction. A test enforces both the single
direction and a maximum of four colour stops, which is what keeps this from
becoming a rainbow.

**Milk became a real language.** `MilkFill` (with a meniscus — the detail that
makes it read as liquid rather than a coloured rectangle), `MilkVolume`,
`MilkStream`, `MilkRipple`, `CollectionProgress`. Surface movement is ambient
and tiny: it reads as liquid peripherally and disappears under scrutiny.

**Intelligence, evidence-first.** Indigo glow rather than fill; the basis is
the second line in reading order and is never hidden behind the disclosure;
confidence is a word plus a deliberately *partial* bar, because unfilled space
is information; long reasoning is collapsible for an auditor. There is still no
prop that can claim availability.

**Sync gained droplets** travelling toward a destination — the metaphor an
operator actually needs: work is leaving this device and arriving somewhere.
The word and the count remain the signal.

**Micro-interactions.** One `lacteva-lift` rule so every liftable surface lifts
identically — 2px, not 8, because this is used for eight hours rather than
admired for eight seconds. Plus ripple, surface movement, droplet and tick,
every one of them named in the global reduced-motion block and asserted to be.

### What V1.1 deliberately did not do

No production screen was redesigned. No neon, no glassmorphism showcase, no
particles, no oversized AI iconography, no decorative motion on a critical
workflow. Mobile was left untouched — the shared theme already carries the
palette and the counter ergonomics, and redesigning mobile screens is not this
milestone.

## 12. Where V1 goes next

1. Wire `Skeleton` into the four pages with no loading state (closes UX-1).
2. Apply `SyncIndicator` to `/sync` and the mobile offline banner.
3. Terminology glossary (UX-2) — a naming decision, not a visual one.
4. RTL physical-alignment pass on the three known tables (UX-4).
5. Page-level composition for the dashboards, once the operator journey has
   been proven on a physical handset.

## Change Log

| Version | Date | Author | Changes |
|---------|------|--------|---------|
| 1.1 | 2026-08-26 | Engineering | Visual refinement pass after review of the rendered page, which was judged technically sound but flat and documentation-like. Added a responsive `clamp()` type scale, five single-family dairy gradients at one light direction, seven card tones separating by elevation rather than borders, the `Surface`/`Metric` hierarchy, the milk primitive family (`MilkFill` with meniscus, `MilkVolume`, `MilkStream`, `MilkRipple`, `CollectionProgress`), an evidence-first intelligence treatment with confidence and collapsible reasoning, sync droplets, and a shared 2px hover-lift. Rebuilt `/design-system` as an interactive showroom with a hero, a responsive frame switcher and live chart examples. 18 further assertions (35 token guards + 13 primitive contracts). Foundations, claims guards, contrast thresholds and reduced-motion behaviour unchanged; no production screen, API, permission or business rule touched. |
| 1.0 | 2026-08-26 | Engineering | Design System V1 foundation. Replaced the portal's stock shadcn greyscale with the Lacteva palette (milk/cream ground, deep dairy green, fresh/water/amber accents, semantic and intelligence hues, green-tinted elevation, five distinguishable chart hues) in both light and dark faces; defined the milk motion language and a global reduced-motion honouring; added `Skeleton`, `LiquidProgress`, `SyncIndicator`, `Insight`/`ComingSoonInsight`; added the `/design-system` live reference route; gave mobile a shared-palette theme with counter ergonomics (48 dp targets, 56 dp primary action, larger type). Executable guards: 30 portal assertions incl. WCAG contrast computed from OKLCH for 12 pairs in both faces, and 9 mobile assertions incl. motion parity read from the portal's own stylesheet. The contrast guard caught this milestone's own amber failing AA at 3.59:1 (palette corrected, not the threshold); the claims guard caught its own draft comment (reworded, not weakened). No production screen, API, permission or business rule was changed. |
