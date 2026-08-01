# 13 — Products

Product implementation packages: one folder per product, holding its chapter-level specification documents (`PSP` prefix). A product package is the bridge between the product's architecture object ([`PDT` in the application layer](../03-architecture/03-application-layer/README.md)) and the engineering artifacts (SRS, API, DBD, UI) that will implement it.

## Structure of a Product Package

```
13-products/<product-slug>/
├── README.md          — package master: structure, status, high-level flows
├── PSP-NNNN-*.md      — chapter specifications (global PSP sequence)
├── TRACEABILITY.md    — capability → product → rule → event → future artifacts
└── REVIEW-NOTES.md    — ambiguities, assumptions, and open questions register
```

## Rules

- A product package **implements approved architecture; it never invents it.** Anything the package needed to assume is logged in its `REVIEW-NOTES.md`, and stays an assumption until confirmed by the architecture owners.
- PSP documents decompose later into formal EA artifacts (AGG/BPR/POL/EVT…) per the [dependency map](../03-architecture/DEPENDENCY-MAP.md); when that happens the EA artifact becomes authoritative and the PSP section references it instead of restating it.
- Every package has a `PDT` in the application layer; the package README links it.
- Prefer references over duplication — capability content lives in `05-capabilities/`, terms in the [glossary](../11-glossary/GLOSSARY.md).

## Index

| Product | Package | PDT | Status |
| --- | --- | --- | --- |
| Lacteva Collect | [`lacteva-collect/`](lacteva-collect/README.md) | [PDT-0001](../03-architecture/03-application-layer/PDT-0001-lacteva-collect.md) | Draft — first 3 chapters specified |
