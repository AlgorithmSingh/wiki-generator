# PRD: DeepWiki-Style Coverage Expansion for Generated Wikis

**Status:** Final PRD for requirements planning
**Product area:** `wiki-generator` coverage planning, evidence, and generation quality
**PRD workspace:** `docs/product-requirements/deepwiki-coverage-expansion/`
**Date:** 2026-06-29

## 1. Executive summary

The current official RAGFlow generated wiki is valid, concise, and source-grounded for its planned scope: 22 sections, 53/53 required topics covered, and 425 distinct citations. It is not, however, breadth-equivalent to the benchmark-only DeepWiki export, which shows a 62-page, subsystem-planned wiki with per-page “Relevant source files.”

This PRD defines the product requirements for expanding generated wiki coverage toward a DeepWiki-style hierarchical page plan without sacrificing grounding. The change should not make the current 22 sections longer. It should move coverage responsibility upstream: repository-derived topic/page discovery, hierarchical parent/child planning, deterministic per-page source selection, page-level evidence retrieval, grounded per-page rendering, and source-derived traceability evaluation.

The central product principle is: **coverage expansion is primarily a Phase 1/Phase 2 planning and source-selection problem, not a Phase 4 writing-length problem.** Phase 4 remains a grounded renderer of planned and evidenced obligations.

## 2. Problem statement and opportunity

### Problem

The generator can produce a grounded overview wiki, but its current planning granularity compresses major repository surfaces into broad sections. Existing validation proves scoped correctness, not DeepWiki-style breadth. A compact plan can pass if it covers all currently planned topics, even when important subtopics are never planned as pages, source portfolios, or page-level obligations.

Current observed state:

- Official live grounded E2E passed in enhancement mode.
- Generated coverage passed: 22 sections, 53 required topics, 53 covered, 0 omitted, 0 invalid.
- Citation manifest passed with 425 distinct citations and 725 total citation occurrences.
- Benchmark-only DeepWiki export shows a much broader hierarchy: 62 page blocks, subsystem planning, and per-page relevant source files.

The benchmark is a useful breadth signal, but it cannot be treated as source truth. It was indexed at commit `d32e05d5`, while the local RAGFlow run used a different commit. Therefore, benchmark headings and prose must not be copied into generated output unless independently supported by repository evidence.

### Opportunity

A source-derived hierarchical planning layer can turn the generator from a concise overview producer into a broader engineering wiki producer while preserving strict citations. The opportunity is to create product behavior that:

- discovers repository-backed subtopics before writing;
- plans parent/child pages for major systems such as Deployment, Frontend, LLM Integration, Document Processing, Backend API, Agents/Workflow, Retrieval/Search, Memory, and Admin/Ops;
- deterministically selects files, symbols, contracts, tests, docs, and spans per page;
- retrieves and validates evidence per page/topic before writing;
- renders with the grounded claim-plan path;
- evaluates coverage by page/topic traceability, not benchmark copying or word count.

## 3. Stakeholders and users

| Stakeholder / user | Need |
| --- | --- |
| New contributors | Navigate the repository by subsystem and find the right source files quickly. |
| Maintainers and reviewers | Trust that generated docs are grounded, complete enough, and not copied from a benchmark. |
| Operators / DevOps readers | Find deployment, configuration, health, migration, and operations guidance with citations. |
| Backend/API developers | Understand API resources, workers, tasks, data models, retrieval, and service boundaries. |
| Frontend developers | Find frontend routes, UI architecture, state/i18n/theming, and component organization. |
| LLM/agent workflow developers | Understand LLM provider integration, agents/workflows, tool calling, memory, and sandbox execution. |
| Documentation pipeline owners | Evaluate coverage, evidence sufficiency, validator strictness, and artifact freshness. |
| Product/release decision makers | Decide when a generated wiki is shareable as a broad engineering wiki versus a concise overview. |

## 4. Goals, non-goals, and success metrics

### Goals

- **G-01 — Broader source-derived coverage:** Expand from coarse section coverage to a repository-derived page/topic catalog and hierarchical plan.
- **G-02 — Preserve grounding:** Keep strict citation, unsupported-identifier, placeholder, truncation, malformed-token, and context-artifact validators.
- **G-03 — Shift work upstream:** Make Phase 1/Phase 2 identify and plan pages before Phase 3 retrieval and Phase 4 rendering.
- **G-04 — Page-level evidence:** Require each planned page/topic/content block to have deterministic, citeable source evidence before writing.
- **G-05 — Traceable evaluation:** Evaluate planned, evidenced, and generated coverage by source-derived page/topic traceability.
- **G-06 — Benchmark-safe comparison:** Use the DeepWiki export only as a breadth comparator/dashboard signal, never as evidence or copied structure.

### Non-goals

- **NG-01:** Do not copy benchmark headings, prose, claims, citations, or page structure into generated output without repository-derived evidence.
- **NG-02:** Do not solve coverage by merely increasing token limits, page length, or writing verbosity.
- **NG-03:** Do not introduce output patching, post-hoc mutation of generated Markdown, generic heal/retry loops, synthetic evidence, or silent required-to-optional downgrades.
- **NG-04:** Do not weaken existing validators or make broad recall sufficient for precise technical claims.
- **NG-05:** Do not define detailed module-level implementation architecture in this PRD; leave that to a later TDD.
- **NG-06:** Do not treat page-count or word-count parity with the benchmark as the primary success criterion.

### Success metrics

| Metric ID | Metric | Target |
| --- | --- | --- |
| M-01 | High-signal source-derived facets planned | 100% planned, or explicitly deferred with source-derived reason. |
| M-02 | Planned hierarchy completeness | Every normal source page has a parent/child placement, page profile, required content blocks, and required topics. |
| M-03 | Evidence sufficiency | 100% of blocking required topics/content blocks are sufficient before Phase 4. |
| M-04 | Generated coverage | 100% of evidenced required topics/content blocks are generated with valid local citations. |
| M-05 | Citation quality | 0 unresolved citations, malformed evidence tokens, context-artifact citations, unsupported identifiers, placeholders, or truncation defects. |
| M-06 | Artifact freshness | 100% of downstream PASS reports fingerprint the same plan/evidence artifacts they consumed. |
| M-07 | Coverage breadth | Material expansion beyond 22 sections / 53 topics, driven by source-derived facets. A first source-supported target band is roughly 45–70 pages and 150–250 required topics, but only after the catalog proves that breadth. |
| M-08 | Benchmark leakage | 0 benchmark-derived citeable evidence IDs, copied headings, copied prose, or benchmark-only claims in generated output. |

## 5. Scope

### In scope

- Repository-derived topic/page catalog.
- Hierarchical parent/child page planning.
- Page profiles such as overview, subsystem deep dive, API reference, configuration reference, deployment runbook, developer workflow, data-flow page, operations page, and glossary.
- Required content blocks per page profile, such as purpose, entrypoints, flow, key files, API/config matrices, tests, operations, and known gaps.
- Deterministic per-page source selection across citeable repository evidence: files, symbols, spans, routes/contracts, tests, docs, configs, deployment artifacts, and runtime surfaces.
- Per-page/per-topic evidence sufficiency before writing.
- Grounded claim-plan rendering per page.
- Source-derived planned/evidenced/generated coverage metrics.
- Benchmark-only comparison report that remains outside evidence gates.
- Artifact lineage/freshness validation.
- Bounded repair only for LLM-authored plans or claim plans, with exact diagnostics, audit artifacts, hard caps, and strict revalidation.

### Out of scope

- Detailed module/class/function implementation design.
- Live/billed generation policy changes beyond existing explicit-approval guardrails.
- Rewriting historical generated wiki outputs in place.
- Hand-patching generated pages, citation manifests, `covered_topics[]`, or coverage reports.
- Treating `ragflow-deepwiki.md` as source evidence.
- Replacing deterministic Phase 3 retrieval with LLM retrieval or fuzzy semantic acceptance.

## 6. User and product requirements

| ID | Requirement | Priority |
| --- | --- | --- |
| UR-01 | The product shall build a repository-derived expanded topic/page catalog before page planning. | Must |
| UR-02 | The product shall plan a hierarchical parent/child page tree instead of relying only on broad flat sections. | Must |
| UR-03 | The product shall assign each planned page a page profile and required content blocks appropriate to that profile. | Must |
| UR-04 | The product shall deterministically select relevant files, symbols, contracts, tests, docs, and source spans for each planned page before Phase 3 evidence retrieval. | Must |
| UR-05 | The product shall retrieve and validate evidence per page/topic/content block before writing begins. | Must |
| UR-06 | The product shall render pages through the grounded claim-plan path when operating in expanded/DeepWiki-style coverage mode. | Must |
| UR-07 | The product shall produce planned → evidenced → generated traceability for every blocking page/topic/content block. | Must |
| UR-08 | The product shall evaluate coverage using source-derived page/topic traceability and facet/content-block completeness, not benchmark copying. | Must |
| UR-09 | The product shall preserve strict validators for citations, malformed tokens, unsupported identifiers, placeholders, truncation, context artifacts, and generated coverage. | Must |
| UR-10 | The product shall fail closed when mandatory source-derived planned/evidenced/generated coverage is missing, weak, stale, or unsupported. | Must |
| UR-11 | The product shall record known gaps when source evidence is weak or absent instead of forcing invented pages or claims. | Must |
| UR-12 | The product shall keep benchmark comparison separate from source-evidence gates and generated output. | Must |
| UR-13 | The product shall expose human-readable navigation that preserves hierarchy and helps readers choose paths by subsystem/audience. | Should |
| UR-14 | The product shall report citation quality, coverage quality, and artifact freshness per page. | Should |
| UR-15 | The product shall support bounded repair only for LLM-authored plan or claim-plan artifacts, with exact diagnostics and hard caps. | Must |

## 7. Business and product rules

| ID | Rule |
| --- | --- |
| BR-01 | Benchmark material is comparator-only. It is not citeable evidence, not source truth, and not a source for copied headings/prose. |
| BR-02 | Repository evidence outranks benchmark breadth signals. If a benchmark topic is not supported by the indexed repository evidence, it may only become a known gap or source-derived discovery task. |
| BR-03 | Broad parent pages do not satisfy child-page obligations. Child topics must have their own planned, evidenced, and generated coverage. |
| BR-04 | Broad recall lanes may provide context but cannot be the only support for precise required topics or technical claims. |
| BR-05 | Phase 3 evidence retrieval remains deterministic and fail-closed in expanded coverage mode. |
| BR-06 | Strict validators must not be weakened to make expanded coverage pass. |
| BR-07 | Output patching is forbidden: generated Markdown, citation manifests, coverage declarations, and reports must not be mutated after generation to satisfy validators. |
| BR-08 | Generic heal/retry-until-green loops are forbidden. Repair is allowed only for LLM-authored plans or claim plans, with exact diagnostics, audit logs, hard attempt caps, and strict revalidation. |
| BR-09 | Artifact freshness is required. A downstream PASS cannot rely on stale, mismatched, or earlier-failed plan/evidence artifacts. |
| BR-10 | Page and topic expansion must be source-derived and bounded by evidence, not by arbitrary line-count or page-count targets. |
| BR-11 | Missing or low-signal topics must be explicit known gaps rather than hidden omissions. |
| BR-12 | The generated wiki must remain auditable through machine-readable metadata and human-readable reports. |

## 8. Quality attributes and measurable acceptance criteria

| ID | Quality attribute | Acceptance criteria |
| --- | --- | --- |
| QA-01 | Grounding | 100% of repo-specific claims on generated pages have valid EvidencePacket citations; no context-only or benchmark citations are accepted. |
| QA-02 | Determinism | Catalog, plan, evidence sufficiency, generated coverage, citation manifest, and freshness checks are deterministic for the same inputs. |
| QA-03 | Traceability | Every blocking required topic/content block traces from source-derived facet → planned page → evidence IDs → generated coverage row → citations. |
| QA-04 | Coverage breadth | Every high-signal facet is planned/evidenced/generated or explicitly deferred with a source-derived reason; broad parent pages cannot mask child omissions. |
| QA-05 | Citation integrity | Citation manifest resolves all citations; malformed `[ev:...]` tokens, dangling evidence tokens, unsupported identifiers, placeholders, and truncation fail validation. |
| QA-06 | Evidence sufficiency | Required topics cannot pass on broad recall alone; exact/high-confidence evidence is required for precise technical obligations. |
| QA-07 | Usability | The generated index presents nested navigation and reader paths; page headings are reader-facing, not prompt-like, where evidence supports them. |
| QA-08 | Failure transparency | Gate failures include actionable diagnostics naming page, topic, source field/evidence issue, and remediation owner. |
| QA-09 | Repair discipline | Any bounded repair has a recorded diagnostic input, attempt count, accepted/rejected verdict, and final strict validation result. |
| QA-10 | Benchmark safety | Benchmark-only comparison can report breadth gaps but cannot create evidence IDs, required topics, generated headings, or claims by itself. |

## 9. Data and interface requirements at product level

| ID | Product-level data/interface requirement |
| --- | --- |
| DI-01 | The system shall consume repository-derived inventories and signals, including files, directories, docs, tests, configs, deployment artifacts, API/contracts, frontend/runtime surfaces, symbols, chunks, and spans. |
| DI-02 | The system shall produce a machine-readable expanded topic/page catalog with stable IDs, source-derived facets, signal strength, suggested page profiles, candidate source handles, and known gaps. |
| DI-03 | The system shall produce a hierarchical page plan with stable page IDs, parent/child links, page profiles, required content blocks, required topics, and source obligations. |
| DI-04 | The system shall express page/topic evidence requirements as structured product artifacts that map required topics/content blocks to exact citeable source-selection handles. |
| DI-05 | The system shall produce a page/topic evidence sufficiency matrix with statuses such as sufficient, weak, missing, and not applicable. |
| DI-06 | The system shall pass page-level evidence portfolios into writing packets, including exact allowed evidence IDs for each required topic/content block. |
| DI-07 | The system shall accept and validate grounded claim plans as the source of generated page prose in expanded coverage mode. |
| DI-08 | The system shall produce generated coverage metadata mapping planned/evidenced obligations to generated Markdown anchors, citations, and validation status. |
| DI-09 | The system shall produce a citation manifest with evidence IDs, lanes, confidence, source artifacts, source paths/ranges or route pointers, and usage sections. |
| DI-10 | The system shall produce human-readable and machine-readable validation reports for planned coverage, evidenced coverage, generated coverage, citation quality, and artifact freshness. |
| DI-11 | The system shall produce a benchmark-only comparison report that is clearly marked non-citeable and excluded from evidence gates. |

## 10. Acceptance criteria and validation gates

| Gate ID | Gate | Acceptance criteria |
| --- | --- | --- |
| VG-01 | Catalog gate | Expanded catalog is built from repository signals; every high-signal facet is present, deferred with reason, or marked low/missing; benchmark text is not used as evidence. |
| VG-02 | Planning gate | Hierarchical plan includes parent/child links, page profiles, required content blocks, required topics, and exact source obligations. A broad 13-family-only or 22-section-only plan fails expanded mode. |
| VG-03 | Source-selection gate | Each planned page has deterministic relevant files/symbols/spans/contracts/tests/docs selected before Phase 3 retrieval. |
| VG-04 | Evidence sufficiency gate | Every blocking topic/content block has sufficient citeable evidence from acceptable lanes before Phase 4. Weak/missing evidence fails closed. |
| VG-05 | Grounded rendering gate | Expanded pages are rendered from validated grounded claim plans; free-typed unsupported technical tokens fail before accepted Markdown is assembled. |
| VG-06 | Generated coverage gate | Every evidenced required topic/content block appears in generated Markdown with valid local citations and a generated coverage row. |
| VG-07 | Validator gate | Existing strict validators pass: citations, malformed evidence tokens, unsupported identifiers, placeholders, truncation, context artifacts, and generated coverage. |
| VG-08 | Artifact freshness gate | Planned/evidenced/generated PASS reports fingerprint or otherwise prove they consumed the same current plan/evidence artifacts. Stale FAIL/PASS mismatches fail. |
| VG-09 | Benchmark isolation gate | Benchmark comparison is produced only as a separate breadth report; no generated page, evidence ID, required topic, or citation is sourced from benchmark-only material. |
| VG-10 | Traceability gate | Traceability matrix links requirements, source facts, acceptance criteria, risks, and final PRD sections; no Must requirement is orphaned. |

## 11. Risks, assumptions, and open decisions

### Risks

| ID | Risk | Mitigation |
| --- | --- | --- |
| R-01 | Page-count chasing creates filler or shallow summaries. | Use source-derived facets, evidence sufficiency, and content-block gates instead of line-count parity. |
| R-02 | Benchmark leakage contaminates plans or generated headings. | Keep benchmark comparator-only and validate no benchmark-derived evidence or copied prose/headings. |
| R-03 | Expanded planning over-requires unsupported topics. | Allow explicit known gaps when source signals are weak/missing. |
| R-04 | Broad recall masks weak evidence. | Require exact/high-quality citeable evidence for blocking topics and precise technical claims. |
| R-05 | Larger hierarchies increase stale artifact risk. | Add artifact lineage/freshness validation. |
| R-06 | More pages strain writing consistency. | Use page profiles, required content blocks, grounded claim plans, and generated coverage validation. |
| R-07 | Deterministic source selection misses non-Python/frontend/Go/deployment surfaces. | Treat language/runtime coverage as part of catalog/source-selection acceptance, with explicit low-signal gaps. |
| R-08 | Bounded repair expands into retry-until-green behavior. | Limit repair to LLM-authored plans/claim plans, exact diagnostics, hard caps, audit trails, and strict final validation. |

### Assumptions

| ID | Assumption |
| --- | --- |
| A-01 | The current official generated wiki is valid for its planned scope but insufficient for DeepWiki-style breadth. |
| A-02 | The benchmark export is useful as a breadth signal but not as source truth because it was indexed at a different commit. |
| A-03 | Repository-derived signals can identify enough high-value facets to justify a deeper hierarchy. |
| A-04 | Phase 3 can remain deterministic if page/topic evidence obligations are explicit before retrieval. |
| A-05 | Grounded claim-plan rendering can scale to per-page generation while preserving strict validation. |
| A-06 | The first expanded target band should be calibrated after catalog generation rather than fixed solely from the benchmark. |

### Open decisions

| ID | Decision needed | Owner |
| --- | --- | --- |
| OD-01 | Should grounded claim-plan mode become the default for expanded coverage runs, or remain opt-in? | Product/engineering lead |
| OD-02 | What threshold promotes a source-derived facet from optional to required? | Product/engineering lead with evaluator input |
| OD-03 | What initial page-count/topic-count target is appropriate after the first real catalog is generated? | Product/engineering lead |
| OD-04 | Which page profiles must be included in the first implementation slice? | Product/engineering lead |
| OD-05 | Which high-risk page families require human sign-off before broad release? | Product/release owner |

## 12. Source reference index

| Source ID | Source |
| --- | --- |
| SRC-USER | User request captured in `input.md`. |
| SRC-PRD-GUIDE | PRD Companion Round 2 phase guide under `/Users/ankitsingh/Documents/my-pi-ai-tts-setup/4-PRD-Companion/3-phases/round-2`. |
| SRC-REV | `/Users/ankitsingh/Documents/deep-wiki/reverse-engineer.md`. |
| SRC-COMP | `GPT55_XHIGH_BENCHMARK_COMPARISON.md`. |
| SRC-COVX | `COVERAGE_EXPANSION_GPT55_XHIGH.md`. |
| SRC-DR | `COVERAGE_EXPANSION_DEEP_RESEARCH.md`. |
| SRC-E2E | `OFFICIAL_LIVE_E2E_RESULT.md`. |
| SRC-GENCOV | `wiki/metadata/generated-coverage.json`. |
| SRC-CITMAN | `wiki/metadata/citation-manifest.json`. |
| SRC-SPEC | `docs/specs/not-done/PHASE_DEEPWIKI_COVERAGE_ENHANCEMENT_ITERATION_SPEC.md`. |
| SRC-HANDOFF | `docs/handoffs/not-done/HANDOFF_DEEPWIKI_COVERAGE_ENHANCEMENT_ITERATION.md`. |

## 13. Product conclusion

The next coverage expansion should be treated as a product capability for source-derived hierarchical planning and evidence traceability. The desired outcome is not “longer sections”; it is a broader, auditable, page-level wiki plan where every page and topic exists because the repository supports it, every technical claim is grounded, and every coverage claim can be traced from source signal to final generated citation.
