"""Central configuration: ignore rules, file classification, language maps, caps.

Adapted from the proven repo-analysis classifier. Phase 1 is Python-first: only
``.py`` files get AST-level structure; everything else is inventoried and chunked
by line windows for retrieval.
"""
from __future__ import annotations

# --- Directories never walked / indexed (os.walk fallback only; git ls-files
#     already respects .gitignore) -------------------------------------------
IGNORE_DIRS = {
    ".git", ".hg", ".svn", "__pycache__", ".mypy_cache", ".pytest_cache",
    ".ruff_cache", ".idea", ".vscode", "node_modules", ".venv", "venv",
    "env", ".env.d", "dist", "build", ".next", ".turbo", ".cache",
    "target", ".gradle", ".tox", "site-packages", ".eggs", "coverage",
    ".agents", ".github_cache",
}

# Path substrings that mark generated/vendored content (still inventoried, but
# excluded from chunking/indexing and flagged in source-coverage).
VENDOR_PATH_MARKERS = (
    "web/dist/", "web/node_modules/", "/dist/", "/.next/", "/vendor/",
    "/third_party/", "/thirdparty/", "/external/", "/site-packages/",
)
GENERATED_FILE_NAMES = {
    "uv.lock", "go.sum", "package-lock.json", "yarn.lock", "pnpm-lock.yaml",
    "poetry.lock", "Cargo.lock", "composer.lock",
}
GENERATED_SUFFIXES = (".min.js", ".min.css", ".pb.go", "_pb2.py", "_pb2_grpc.py", ".lock")

# --- Extension -> language -----------------------------------------------------
LANG_BY_EXT = {
    ".py": "python", ".pyi": "python", ".pyx": "python",
    ".go": "go",
    ".ts": "typescript", ".tsx": "tsx", ".js": "javascript", ".jsx": "jsx",
    ".mjs": "javascript", ".cjs": "javascript",
    ".c": "c", ".h": "c", ".cc": "cpp", ".cpp": "cpp", ".cxx": "cpp",
    ".hpp": "cpp", ".hh": "cpp",
    ".java": "java", ".rs": "rust", ".rb": "ruby", ".php": "php",
    ".sh": "shell", ".bash": "shell", ".zsh": "shell",
    ".sql": "sql",
    ".md": "markdown", ".mdx": "markdown", ".rst": "rst", ".txt": "text",
    ".toml": "toml", ".ini": "ini", ".cfg": "ini",
    ".yaml": "yaml", ".yml": "yaml", ".json": "json", ".json5": "json",
    ".env": "dotenv", ".tmpl": "template", ".tpl": "template", ".j2": "jinja",
    ".html": "html", ".htm": "html", ".css": "css", ".less": "less",
    ".scss": "scss", ".vue": "vue", ".svelte": "svelte",
    ".dockerfile": "dockerfile", ".proto": "protobuf",
}

# Extensions whose textual content we read for chunking/indexing.
TEXT_EXTS = set(LANG_BY_EXT)

# Binary / asset extensions we record in inventory but never read.
BINARY_EXTS = {
    ".png", ".jpg", ".jpeg", ".gif", ".svg", ".ico", ".webp", ".bmp",
    ".pdf", ".woff", ".woff2", ".ttf", ".otf", ".eot",
    ".zip", ".gz", ".tar", ".whl", ".so", ".dylib", ".dll", ".bin",
    ".mp4", ".mp3", ".wav", ".pyc", ".o", ".a", ".class", ".jar",
    ".parquet", ".npy", ".pkl", ".pem", ".faiss", ".sqlite",
}

# --- Caps ----------------------------------------------------------------------
MAX_FILE_BYTES_FOR_TEXT = 1_500_000     # skip reading files larger than this
MAX_CHUNK_CHARS = 8000                   # stored chunk/span text cap
MAX_CHUNK_LINES = 220                    # split code chunks longer than this
CHUNK_LINE_OVERLAP = 15                  # overlap when window-splitting
WINDOW_LINES_NONPY = 160                 # window size for non-Python source
EMBED_TEXT_CHARS = 2000                  # chars per chunk fed to the embedder

# Embedding model for the optional vector lane (model2vec static embeddings —
# no torch). Only used when the `embeddings` extra is installed.
EMBED_MODEL = "minishlab/potion-base-8M"

# Leading path segments stripped when deriving a dotted module name, so a repo
# laid out under src/ produces `app.api` rather than `src.app.api`.
SOURCE_ROOT_PREFIXES = ("src/",)


def classify(rel_path: str, ext: str, size: int) -> dict:
    """Return {'category','is_generated','is_vendor','is_binary'} for a file."""
    p = rel_path.replace("\\", "/")
    low = p.lower()
    name = p.rsplit("/", 1)[-1]
    lname = name.lower()
    is_binary = ext in BINARY_EXTS
    is_vendor = any(m in "/" + p for m in VENDOR_PATH_MARKERS)
    is_generated = (
        name in GENERATED_FILE_NAMES
        or any(name.endswith(s) for s in GENERATED_SUFFIXES)
        or "/migrations/versions/" in "/" + low
    )

    def is_test() -> bool:
        return (
            "/test/" in "/" + low or "/tests/" in "/" + low
            or low.endswith("_test.go") or low.endswith("_test.py")
            or lname.startswith("test_") or lname == "conftest.py"
            or "/__tests__/" in "/" + low or low.endswith(".test.ts")
            or low.endswith(".test.tsx") or low.endswith(".spec.ts")
        )

    def is_deployment() -> bool:
        return (
            lname.startswith("dockerfile")
            or "dockerfile" in lname
            or "docker-compose" in lname
            or low.startswith("docker/") or low.startswith("helm/")
            or "/.github/workflows/" in "/" + low
            or (low.endswith(".tmpl") and "helm" in low)
            or lname in {"build.sh", "entrypoint.sh"}
            or low.startswith("deploy/") or "/k8s/" in "/" + low
        )

    def is_config() -> bool:
        if ext in {".toml", ".cfg", ".ini", ".env"} or (ext == "" and name.startswith(".env")):
            return True
        if name in {"pyproject.toml", "setup.cfg", "setup.py", "go.mod",
                    "codecov.yml", ".pre-commit-config.yaml", "pytest.ini",
                    "tox.ini", "mypy.ini"}:
            return True
        if low.startswith("conf/"):
            return True
        if ext in {".yaml", ".yml", ".json"} and not is_deployment():
            return True
        return False

    def is_docs() -> bool:
        return ext in {".md", ".mdx", ".rst"} or low.startswith("docs/")

    if is_binary:
        category = "asset"
    elif is_generated or is_vendor:
        category = "generated" if is_generated else "vendor"
    elif is_deployment():
        category = "deployment"
    elif is_test():
        category = "test"
    elif is_docs():
        category = "docs"
    elif is_config():
        category = "config"
    elif ext in LANG_BY_EXT and LANG_BY_EXT[ext] not in {"markdown", "text", "rst"}:
        category = "source"
    else:
        category = "other"

    return {
        "category": category,
        "is_generated": is_generated,
        "is_vendor": is_vendor,
        "is_binary": is_binary,
    }


def language_for(ext: str, name: str) -> str:
    low = name.lower()
    if low.startswith("dockerfile"):
        return "dockerfile"
    if low in {"go.mod", "go.sum"}:
        return "go-mod"
    if low in {"makefile", "dockerfile"}:
        return low
    return LANG_BY_EXT.get(ext, "other")
