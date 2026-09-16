"""Resolves the ModelRuntime to use for a given ModelVersion.

Convention: a ModelVersion whose `metrics` JSON has no `features` entry is
treated as a placeholder/test fixture (not backed by a real trained
artifact) and gets `PlaceholderRuntime` — this is how every ModelVersion
created before this module existed, and every one created directly in
tests, keeps working unchanged. A ModelVersion registered with
`metrics.features` populated (see app/api/v1/models.py's create endpoint)
is treated as real and loaded via `SklearnPipelineRuntime`. If *that*
load fails, it is a genuine error, not silently downgraded to a
placeholder — a model declared real that can't actually be loaded must
fail loudly.

Loaded artifacts are cached in memory per model_version.id so a joblib
file isn't reloaded on every request. The cache is per-process — each
Gunicorn worker keeps its own; an accepted simplification for now (see
CHECKLIST.md Phase 4).
"""

from __future__ import annotations

import threading

from app.models.model import ModelVersion
from app.services.model_runtime import ModelRuntime
from app.services.placeholder_runtime import PlaceholderRuntime

_cache: dict[str, ModelRuntime] = {}
_lock = threading.Lock()


class RuntimeResolutionError(Exception):
    """A ModelVersion declared as real (has `metrics.features`) couldn't
    actually be loaded. `message` is always safe to show an API caller —
    never a stack trace, file path, or other internal detail."""

    def __init__(self, message: str = "Unable to load the model runtime for this model version"):
        super().__init__(message)
        self.message = message


def resolve_runtime(model_version: ModelVersion) -> ModelRuntime:
    features = (model_version.metrics or {}).get("features")
    if not features:
        return PlaceholderRuntime()

    with _lock:
        cached = _cache.get(model_version.id)
        if cached is not None:
            return cached

        try:
            # Imported lazily: pandas/joblib/shap are only needed on this
            # path (a model version backed by a real trained artifact),
            # not for PlaceholderRuntime or test-injected runtimes — the
            # rest of ScoringService must stay usable without them.
            from app.services.runtimes.sklearn_pipeline_runtime import SklearnPipelineRuntime

            artifact_path = _artifact_path(model_version.artifact_uri)
            runtime = SklearnPipelineRuntime(artifact_path, features["numeric"], features["categorical"])
        except Exception:
            raise RuntimeResolutionError() from None

        _cache[model_version.id] = runtime
        return runtime


def clear_cache() -> None:
    """Test-only: drop cached runtimes between test cases."""
    with _lock:
        _cache.clear()


def _artifact_path(artifact_uri: str) -> str:
    return artifact_uri.removeprefix("file://")
