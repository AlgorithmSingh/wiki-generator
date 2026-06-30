# ADR 0001 — Make strict source-derived scale gates core to the expanded path

- Status: **Accepted**
- Date: 2026-06-29
- Builds on (does not supersede): `docs/technical-design/deepwiki-scale-parity-next-phase/adr/0001-deepwiki-scale-anti-compression-mode.md`

## Context

The anti-compression breadth gate was introduced behind a separate, opt-in
`deepwiki-scale` mode. The official/core `--coverage-mode expanded` path therefore kept
shipping compressed, benchmark-far output: a real RAGFlow run collapsed a 147-topic /
94-must / 12-family / 82-must-subsystem catalog into 21 flat pages and 42 TERs. The
product directive is that DeepWiki-scale breadth is the **core**, not a separate product
or add-on. Additionally, the gate only *rejected* compressed plans and did not carry
promoted catalog-topic granularity past Phase 2.

## Decision

1. `enforces_breadth(mode)` is true for **both** `expanded` and `deepwiki-scale`. The
   anti-compression breadth gate is therefore **core behaviour of the expanded path**,
   run by default, not an opt-in mode.
2. `deepwiki-scale` is retained as a **behaviour-identical compatibility alias** of
   `expanded` (kept in mode tuples + CLI choices, documented as deprecated). It is not a
   separate product or a stricter mode.
3. The Phase 2 planner is given a deterministic **source-derived breadth budget** (page /
   required-topic targets + per-family fan-out floor, computed only from the catalog) and
   explicit fan-out rules in the prompt, so it authors a hierarchy rather than only being
   rejected when it compresses.
4. The Phase 2 gate emits a downstream **promoted-topic contract**
   (`plans/promoted-topic-contract.json`), and Phase 4 carries each evidenced topic's
   `catalog_topic_id` into its generated-coverage obligations/rows, so promoted granularity
   cannot regress to broad-topic-only acceptance once a topic has evidence.

## Consequences

- **Positive:** the official path enforces source-derived breadth; the planner is taught
  to fan out from the catalog (never the benchmark); promoted granularity flows downstream.
- **Negative / accepted:** a previously-"passing" compressed `expanded` run now fails at
  Phase 2 (exit 3). This is intended; documented in rollout. Operators who specifically
  want the historical lenient hierarchical behaviour without breadth enforcement have no
  in-between mode — that is deliberate (breadth is core).
- **Comparator isolation preserved:** no benchmark text/structure/numbers are read or
  copied; all targets derive from the repository catalog.
- **Reversibility:** moderate. Reverting is a one-line change to `_BREADTH_MODES`
  (drop `MODE_EXPANDED`); the budget/contract/prompt additions are additive and inert when
  breadth is not enforced.

## Alternatives

- Keep breadth behind `deepwiki-scale` only (rejected: perpetuates a separate product and
  lets the core path ship compressed output).
- Delete `deepwiki-scale` entirely (rejected for this slice: gratuitous breaking change;
  alias is cheap and honest).
- Hard-gate only, no prompt change (rejected: proven insufficient by the real run).
- Put benchmark page counts in the prompt (rejected: violates comparator isolation).

## Follow-up (staged, not part of this ADR's acceptance)

- A standalone Phase 4 gate that cross-references `plans/promoted-topic-contract.json`
  end-to-end and fails when a promoted leaf topic with evidence is missing from output.
- A billed live RAGFlow run to confirm the hardened prompt + budget reach the
  source-derived page/topic targets.
