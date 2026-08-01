# 11 — Glossary

The company-wide glossary is the **terminology source of truth**. Every document in this repository uses these terms with exactly these meanings; consistent language is what lets hundreds of engineers, and the platform's own AI systems, talk about the same things.

- The glossary itself: [`GLOSSARY.md`](GLOSSARY.md)
- Entry format and rules: [TPL-0011](../02-templates/TPL-0011-glossary-template.md)

## Rules

- **Using a term the glossary doesn't define?** Add it in the same PR — the review workflow enforces this.
- **One meaning per entry.** Terms whose meaning differs by bounded context get one entry per context, explicitly qualified (see the domain-model template's ubiquitous-language rules).
- Deprecated terms remain listed and point to their replacement, so historical documents stay interpretable.
- The docs guild owns the glossary and is a required reviewer for every change to it.
