# Status — DeepWiki Scale-Parity (Anti-Compression)

- **Slug**: `deepwiki-scale-parity-next-phase`
- **Title**: DeepWiki Scale-Parity (Anti-Compression) technical design
- **Audience**: coverage-gate maintainers, future implementation agents, pipeline operator
- **Status**: Draft — Slice 1 (Phase 2 anti-compression gate) implemented & tested non-live
- **Document weight**: Standard
- **Phase relation**: Next phase of `deepwiki-coverage-expansion` (preserved unchanged)
- **Source index**:
  - PRD: `docs/product-requirements/deepwiki-scale-parity-next-phase/artifacts/final_prd.md`
  - Prior PRD/TDD: `docs/.../deepwiki-coverage-expansion/`
  - Real run: `19-do-it-e2e/runs/20260629-152217-real-ragflow-gpt54-expanded-681b900-ragflow-3f805a64f/`
- **Definition of done**: `definition-of-done.json` (DOD-1…DOD-10)
- **ADRs**: `adr/0001-deepwiki-scale-anti-compression-mode.md` (Accepted)
- **Last action**: Slice 1 implemented; focused + relevant suites run non-live.
- **Open decisions**: OD-S1…OD-S4 (require user sign-off before any live run).
- **Intentional omissions**: deployment/migration sections (no schema migration; opt-in
  additive mode); heavy data-model section (no new persistent store — one new JSON
  artifact documented in TDD §6).
