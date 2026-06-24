"""Planned-topic taxonomy for DeepWiki-informed coverage enhancement (Milestone 2).

This module is deterministic, LLM-free, and import-light: it only declares the
*mandatory topic families* a coverage-enhanced RAGFlow guide must plan for, plus
the deterministic signals (explicit coverage labels and distinctive keywords) used
to decide whether a planned section covers each family.

The framing is **coverage enhancement**, not parody or line-count parity. The
families below are derived from repository evidence and the reference benchmark
table-of-contents only; the reference export is never citeable evidence.

Design rules that keep detection honest:

- A family is matched either by an *explicit* ``coverage_labels`` declaration on a
  planned section (exact-set match against ``TopicFamily.all_labels``) or by a
  *distinctive* keyword appearing as a whole word/phrase in the section's planner
  text (title, required topics, key questions, goal, purpose).
- Keywords for *deep* families (retrieval internals, document parsing internals,
  LLM provider internals, …) are deliberately specific so that a broad parent page
  (e.g. a single "Core RAG Pipeline" section whose only topic is the word
  "retrieval") does NOT count as coverage for a deep child topic. A broad parent
  must declare the child's label or carry the child's distinctive vocabulary.
"""
from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class TopicFamily:
    """One mandatory (or optional) DeepWiki topic family.

    ``key``             stable kebab-case identifier (also a valid coverage label).
    ``label``           human-readable family name for reports/diagnostics.
    ``summary``         one-line description of what the family must cover.
    ``coverage_labels`` additional exact-match label aliases a planned section may
                        declare (in a future ``coverage_labels`` plan field).
    ``keywords``        distinctive lower-case word/phrase signals; matched on a
                        whole-word/phrase boundary against a section's planner text.
    ``mandatory``       whether the family is required in coverage-enhanced mode.
    """

    key: str
    label: str
    summary: str
    coverage_labels: tuple[str, ...] = ()
    keywords: tuple[str, ...] = ()
    mandatory: bool = True

    @property
    def all_labels(self) -> frozenset[str]:
        """Every exact label that maps to this family (the key plus its aliases)."""
        return frozenset({self.key, *self.coverage_labels})


# The thirteen mandatory topic families (canonical spec §"Required topic families").
# Keyword sets are intentionally distinctive: a generic baseline section's broad
# title/purpose must NOT accidentally satisfy a deep family.
MANDATORY_TOPIC_FAMILIES: tuple[TopicFamily, ...] = (
    TopicFamily(
        key="frontend",
        label="Frontend / i18n / UI architecture",
        summary="frontend structure, routing, state management, "
                "internationalization, component architecture, theming, build/runtime",
        coverage_labels=("ui", "i18n", "web-frontend"),
        keywords=("frontend", "front-end", "i18n", "internationalization",
                  "theming", "ui component", "web ui", "umi", "tailwind"),
    ),
    TopicFamily(
        key="memory",
        label="Memory system",
        summary="memory APIs, internals, storage, agent-workflow use, and "
                "raw/semantic/episodic/procedural concepts",
        coverage_labels=("memory-system",),
        keywords=("memory", "episodic", "procedural memory", "semantic memory"),
    ),
    TopicFamily(
        key="queue-system",
        label="Task queues and Redis Streams",
        summary="queue names, task lifecycle, workers, cancellation, retries, "
                "parsing/indexing/RAPTOR/GraphRAG/memory queues, operations",
        coverage_labels=("queue", "task-queue", "redis-streams"),
        keywords=("queue", "redis stream", "redis streams", "task executor",
                  "task worker", "task lifecycle"),
    ),
    TopicFamily(
        key="helm-k8s",
        label="Kubernetes and Helm deployment",
        summary="charts, values, manifests, services/deployments, ingress, "
                "config, secrets, and the deployment workflow",
        coverage_labels=("kubernetes", "helm", "k8s"),
        keywords=("kubernetes", "k8s", "helm", "helm chart", "ingress",
                  "values.yaml"),
    ),
    TopicFamily(
        key="ci-cd-build",
        label="CI/CD and build system",
        summary="package managers, Docker build flow, dependency pre-caching, "
                "GitHub workflows, release scripts, image build/publish, dev commands",
        coverage_labels=("ci-cd", "cicd", "build-system"),
        keywords=("ci/cd", "cicd", "continuous integration", "github actions",
                  "github workflow", "build system", "docker build",
                  "release script"),
    ),
    TopicFamily(
        key="go-native",
        label="Go server and native components",
        summary="Go server/admin/native pieces, build modes, parser/lexer/native "
                "services, and Python integration points",
        coverage_labels=("golang", "native-components"),
        keywords=("golang", "go server", "go service", "native component",
                  "go module", "go binary"),
    ),
    TopicFamily(
        key="retrieval-internals",
        label="Retrieval and search internals",
        summary="document-store abstraction, index selection, query transformation, "
                "hybrid search, reranking, filters, pruning, response generation, "
                "citation insertion",
        coverage_labels=("search-internals",),
        keywords=("document store", "docstore", "hybrid search", "reranking",
                  "rerank", "query transformation", "query processing",
                  "response generation", "citation insertion", "index selection"),
    ),
    TopicFamily(
        key="doc-processing",
        label="Document parsing, OCR, layout, and chunking",
        summary="parser factories, DeepDoc, MinerU, OCR/layout operators, chunking "
                "strategies, content enhancement, embedding, connectors, "
                "upload-to-index pipeline stages",
        coverage_labels=("document-parsing", "ocr", "chunking"),
        keywords=("deepdoc", "mineru", "ocr", "layout recognition",
                  "layout analysis", "parser factory", "chunking strategy",
                  "document parsing", "content enhancement"),
    ),
    TopicFamily(
        key="llm-internals",
        label="LLM provider internals, tool calling, retry, usage",
        summary="LLMBundle, model registration, providers, error classes, "
                "retry/backoff, usage tracking, tenant config, tool/function "
                "schemas, tool-call execution",
        coverage_labels=("llm-provider",),
        keywords=("llmbundle", "tool calling", "function calling", "retry logic",
                  "backoff", "usage tracking", "model registration",
                  "provider implementation"),
    ),
    TopicFamily(
        key="user-tenant-admin-health",
        label="User, tenant, admin, and system health",
        summary="user/tenant management, admin routes/services, auth/authorization, "
                "status probes, health endpoints, settings, operational dashboards",
        coverage_labels=("admin", "tenant", "health"),
        keywords=("tenant", "admin service", "admin route", "health endpoint",
                  "health check", "system health", "user management",
                  "status probe"),
    ),
    TopicFamily(
        key="sandbox-executor",
        label="Sandbox / code executor",
        summary="sandbox manager, provider registry, configuration, security "
                "boundaries, code-execution tool, admin/operator controls",
        coverage_labels=("sandbox", "code-executor"),
        keywords=("sandbox", "code executor", "code execution", "executor manager"),
    ),
    TopicFamily(
        key="migrations-operations",
        label="Migrations and operations",
        summary="database migrations/schema sync, ES-to-OceanBase migration, "
                "utility scripts, reset/admin commands, runbooks, upgrade paths",
        coverage_labels=("migrations", "operations"),
        keywords=("migration", "schema sync", "oceanbase", "upgrade path",
                  "runbook", "reset command", "database migration",
                  "utility script"),
    ),
    TopicFamily(
        key="glossary",
        label="Glossary",
        summary="repo-specific terminology, acronyms, component/service/queue/"
                "data-store names, and concepts used throughout the guide",
        coverage_labels=(),
        keywords=("glossary", "terminology", "acronym"),
    ),
)


def family_keys() -> tuple[str, ...]:
    """Stable ordered tuple of mandatory-family keys."""
    return tuple(f.key for f in MANDATORY_TOPIC_FAMILIES)


def family_by_key(key: str,
                  families: tuple[TopicFamily, ...] = MANDATORY_TOPIC_FAMILIES
                  ) -> TopicFamily | None:
    """Look up a family by its stable key, or ``None`` if unknown."""
    for f in families:
        if f.key == key:
            return f
    return None


def _assert_taxonomy_well_formed() -> None:
    """Defensive invariant check run at import: keys/labels are unique and every
    family declares at least one detection signal. Keeps the taxonomy honest if it
    is edited later."""
    keys = [f.key for f in MANDATORY_TOPIC_FAMILIES]
    if len(keys) != len(set(keys)):
        raise ValueError("duplicate TopicFamily key in MANDATORY_TOPIC_FAMILIES")
    labels = [f.label for f in MANDATORY_TOPIC_FAMILIES]
    if len(labels) != len(set(labels)):
        raise ValueError("duplicate TopicFamily label in MANDATORY_TOPIC_FAMILIES")
    for f in MANDATORY_TOPIC_FAMILIES:
        if not (f.coverage_labels or f.keywords):
            raise ValueError(f"family {f.key!r} declares no detection signal")


_assert_taxonomy_well_formed()
