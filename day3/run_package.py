"""Additive provenance capture; never imports or recalculates the forecast model."""

from __future__ import annotations

import hashlib
import importlib.metadata
import json
import math
import os
import platform
import re
import sys
import uuid
from collections.abc import Callable, Mapping, Sequence
from datetime import datetime, timezone
from pathlib import Path
from typing import Any
from urllib.parse import quote, quote_plus


DEFAULT_PACKAGE_ROOT = Path("/content/drive/MyDrive/FPL_VORTEX/MODEL_HISTORY/RUN_PACKAGES")
CONFIG_NAMES = frozenset({
    "FPL_ID", "FPL_TEAM_ID", "MARKET_ODDS", "ENABLE_MARKET_ODDS", "RENDER_MODE",
    "OUTPUT_MODE", "PLAN", "ACCOUNT", "PLAYERS", "NEXT_GW", "CURRENT_SEASON",
    "PREVIOUS_SEASON", "MARKET_BLEND_WEIGHT", "ELO_BLEND_WEIGHT",
    "FPL_API_FALLBACK_MAX_AGE_SECONDS", "FPL_API_DEFAULT_FALLBACK_MAX_AGE_SECONDS",
})
# These are public model constant families, not an unrestricted namespace dump.
CONFIG_PREFIXES = tuple(f"PHASE{number}_" for number in range(1, 13))
REQUIRED_CONFIG = frozenset({
    "CURRENT_SEASON", "NEXT_GW", "PHASE4_POISSON_MODEL_VERSION", "PHASE4_OUTPUT_MODEL_VERSION",
})
INPUT_OBJECT_NAMES = (
    "fixtures_raw", "fixtures", "team_context_raw", "team_news_overrides",
    "team_strength_updated", "fixture_context_phase2", "market_odds_raw",
    "phase10_player_features", "phase11_current_squad_state", "phase11_eo_dashboard",
)
INPUT_FILE_NAMES = (
    "PHASE1_CONTEXT_PATH", "PHASE2_NEWS_PATH", "PHASE2_NEWS_TEMPLATE_PATH",
    "PHASE5_HISTORY_PATH", "PHASE7_HISTORY_PATH",
)
VALIDATION_FIELDS = frozenset({
    "validation_status", "status", "completed_frozen_forecasts", "completed_fixtures",
    "validation_eligible_completed_fixtures", "official_completed_fixtures",
    "sample_size", "live_blend_active", "automatic_promotion_allowed",
})
DEPENDENCIES = ("IPython", "numpy", "pandas", "scipy", "requests")
_SENSITIVE = re.compile(
    r"secret|token|password|passwd|credential|authorization|cookie|api_?key|private_?key",
    re.IGNORECASE,
)
_LITERAL = re.compile(
    r"\b(?:api_?key|access_token|refresh_token|client_secret|password|authorization)"
    r"[\"']?\s*[:=]\s*[\"']([^\"'\r\n]+)[\"']", re.IGNORECASE,
)
_AUTH_URL = re.compile(
    r"https?://[^\s\"'<>]*(?:[?&](?:key|api_?key|token|access_token|sig|signature|"
    r"x-amz-[\w-]+|x-goog-[\w-]+)=|://[^/\s]+:[^/@\s]+@)", re.IGNORECASE,
)
_DATA_SUFFIXES = {".json", ".jsonl", ".csv", ".parquet"}


class PackagingError(RuntimeError):
    """Messages contain fixed diagnostic codes, never source text or secret values."""


def _canonical(value: Any) -> bytes:
    return json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=False,
                      allow_nan=False).encode("utf-8")


def _digest(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def _json_value(value: Any) -> Any:
    if value is None or isinstance(value, (str, bool, int)):
        return value
    if isinstance(value, float):
        return value if math.isfinite(value) else None
    if isinstance(value, (datetime, Path)):
        return str(value)
    if isinstance(value, Mapping):
        return {str(key): _json_value(item) for key, item in value.items()}
    if isinstance(value, (list, tuple)):
        return [_json_value(item) for item in value]
    if callable(getattr(value, "item", None)):
        return _json_value(value.item())
    raise TypeError("UNSUPPORTED_CAPTURE_TYPE")


class RunPackage:
    def __init__(
        self, notebook_path: Path, cells: Sequence[tuple[int, str]], *,
        repository_root: Path, environment: Mapping[str, str] | None = None,
        package_root: Path | None = None,
        clock: Callable[[], datetime] | None = None,
    ) -> None:
        self.environment = dict(os.environ if environment is None else environment)
        self.repository_root = repository_root.resolve()
        self.clock = clock or (lambda: datetime.now(timezone.utc))
        self.secrets: set[str] = set()
        self._learn_secrets(self.environment)
        self._staged_sources: dict[str, bytes] = {}
        self.cells = list(cells)
        if not cells or any(type(index) is not int or index < 0 or not isinstance(source, str)
                            for index, source in cells):
            raise PackagingError("INVALID_CELL_SEQUENCE")
        if len({index for index, _ in cells}) != len(cells):
            raise PackagingError("DUPLICATE_CELL_INDEX")
        run_id = self.environment.get("GITHUB_RUN_ID") or self.environment.get("VORTEX_RUN_ID")
        run_id = run_id or f"local-{uuid.uuid4().hex}"
        attempt = self.environment.get("GITHUB_RUN_ATTEMPT", "1")
        if not re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9_.-]{0,100}", run_id):
            raise PackagingError("INVALID_RUN_ID")
        if not re.fullmatch(r"[1-9][0-9]{0,8}", attempt):
            raise PackagingError("INVALID_RUN_ATTEMPT")
        root = package_root or Path(self.environment.get("VORTEX_RUN_PACKAGE_ROOT", str(DEFAULT_PACKAGE_ROOT)))
        self.directory = root / run_id / f"attempt-{attempt}"
        self._guard(str(self.directory))
        self.directory.mkdir(parents=True, mode=0o700, exist_ok=False)
        self.manifest: dict[str, Any] = {
            "schema_version": 1, "run_id": run_id, "attempt": int(attempt),
            "started_at": self._now(), "finished_at": None, "package_status": "RUNNING",
            "execution_status": "RUNNING", "completed_cells": [], "attempted_cells": [],
            "submitted_sources": [],
            "repository_commit": self._commit(),
            "repository_commit_source": "GITHUB_SHA" if self._commit() else "UNAVAILABLE",
            "repository": self.environment.get("GITHUB_REPOSITORY"),
            "runtime": {"python": platform.python_version(), "dependencies": self._dependencies()},
            "source_files": [], "configuration_snapshots": [], "input_fingerprints": [],
            "output_fingerprints": [], "validation": {}, "diagnostics": [],
            "missing_input_files": [],
            "input_coverage": "DECLARED_INPUTS_OBSERVED_AT_CELL_BOUNDARIES",
            "configuration_coverage": {"exact_names": sorted(CONFIG_NAMES),
                                       "constant_prefixes": list(CONFIG_PREFIXES)},
            "runtime_overrides": self._runtime_overrides(),
            "replay_ready": False,
            "historical_baseline": "FDR_V1.0_MODEL_ONLY",
            "historical_provenance_fully_verified": False,
        }
        self._captured_inputs: set[tuple[str, str]] = set()
        self._last_configuration: str | None = None
        self._save()
        self._perform("SOURCE_CAPTURE_FAILED", lambda: self._capture_sources(notebook_path))

    def _now(self) -> str:
        return self.clock().astimezone(timezone.utc).isoformat()

    def _commit(self) -> str | None:
        value = self.environment.get("GITHUB_SHA", "")
        return value if re.fullmatch(r"[a-fA-F0-9]{40}", value) else None

    def _runtime_overrides(self) -> dict[str, str]:
        names = ("DAY3_PLAN", "DAY3_TRANSFER_MODE", "DAY3_PLANNED_CHIP", *(
            f"DAY3_{direction}_{number}" for direction in ("OUT", "IN") for number in range(1, 6)
        ))
        return {name: self.environment[name] for name in names if name in self.environment}

    @staticmethod
    def _dependencies() -> dict[str, str | None]:
        versions: dict[str, str | None] = {}
        for name in DEPENDENCIES:
            try:
                versions[name] = importlib.metadata.version(name)
            except importlib.metadata.PackageNotFoundError:
                versions[name] = None
        return versions

    def _learn_secrets(self, values: Mapping[str, Any]) -> None:
        for name, value in values.items():
            if _SENSITIVE.search(str(name)) and isinstance(value, str):
                if value.strip() and value not in {"NONE", "None", "null", "****"}:
                    self.secrets.update({value, quote(value, safe=""), quote_plus(value),
                                         json.dumps(value, ensure_ascii=False)[1:-1],
                                         json.dumps(value, ensure_ascii=True)[1:-1]})

    def _guard(self, text: str) -> None:
        if any(secret in text for secret in self.secrets):
            raise PackagingError("SECRET_VALUE_DETECTED")
        if _AUTH_URL.search(text):
            raise PackagingError("AUTHENTICATED_URL_DETECTED")
        for match in _LITERAL.finditer(text):
            value = match.group(1).strip()
            if value and value not in {"***", "****", "REDACTED"}:
                raise PackagingError("CREDENTIAL_LITERAL_DETECTED")

    def _perform(self, code: str, action: Callable[[], Any]) -> Any:
        try:
            return action()
        except Exception:
            if code not in self.manifest["diagnostics"]:
                self.manifest["diagnostics"].append(code)
            self.manifest["package_status"] = "INCOMPLETE"
            return None

    def _save(self, *, final: bool = False) -> None:
        payload = json.loads(_canonical(self.manifest))
        if not final:
            # Values and source bytes wait until the run's discovered secrets are known.
            for snapshot in payload["configuration_snapshots"]:
                snapshot.pop("values", None)
            payload["runtime_overrides"] = {"sha256": _digest(_canonical(payload["runtime_overrides"]))}
            payload["source_values_pending_final_screen"] = True
        payload["manifest_sha256"] = _digest(_canonical(payload))
        data = _canonical(payload)
        self._guard(data.decode("utf-8"))
        temporary = self.directory / f".manifest-{uuid.uuid4().hex}"
        try:
            with temporary.open("xb") as handle:
                handle.write(data)
            temporary.chmod(0o600)
            temporary.replace(self.directory / "manifest.json")
        finally:
            temporary.unlink(missing_ok=True)

    def _source(self, relative: str, data: bytes) -> None:
        self._guard(data.decode("utf-8"))
        if relative in self._staged_sources:
            raise PackagingError("DUPLICATE_SOURCE_PATH")
        self._staged_sources[relative] = data
        self.manifest["source_files"].append({"path": relative, "size_bytes": len(data),
                                               "sha256": _digest(data)})

    def _flush_sources(self) -> None:
        for data in self._staged_sources.values():
            self._guard(data.decode("utf-8"))
        for relative, data in self._staged_sources.items():
            path = self.directory / relative
            path.parent.mkdir(parents=True, mode=0o700, exist_ok=True)
            with path.open("xb") as handle:
                handle.write(data)
            path.chmod(0o600)

    def _screen_configuration(self) -> None:
        for snapshot in self.manifest["configuration_snapshots"]:
            try:
                self._guard(_canonical(snapshot["values"]).decode())
            except PackagingError:
                snapshot["values"] = {}
                snapshot["sha256"] = _digest(_canonical({}))
                snapshot["capture_status"] = "REJECTED_SECRET_VALUE"
                if "CONFIGURATION_SECRET_DETECTED" not in self.manifest["diagnostics"]:
                    self.manifest["diagnostics"].append("CONFIGURATION_SECRET_DETECTED")
        try:
            self._guard(_canonical(self.manifest["runtime_overrides"]).decode())
        except PackagingError:
            self.manifest["runtime_overrides"] = {}
            self.manifest["diagnostics"].append("RUNTIME_OVERRIDE_SECRET_DETECTED")

    def _capture_sources(self, notebook_path: Path) -> None:
        original = notebook_path.read_bytes()
        self._guard(original.decode("utf-8"))
        for _, source in self.cells:
            self._guard(source)
        self._source("source/original.ipynb", original)
        self._source("source/submitted_cells.json", _canonical([
            {"cell_index": index, "source": source} for index, source in self.cells
        ]))
        sources = {Path(__file__).resolve(), self.repository_root / "day3/run_notebook.py"}
        for module in tuple(sys.modules.values()):
            filename = getattr(module, "__file__", None)
            if isinstance(filename, str) and filename.endswith(".py"):
                path = Path(filename).resolve()
                if path.is_relative_to(self.repository_root) and not path.name.startswith("test_"):
                    sources.add(path)
        for path in sorted(sources):
            if path.is_file() and path.is_relative_to(self.repository_root):
                self._source(f"source/repository/{path.relative_to(self.repository_root).as_posix()}",
                             path.read_bytes())
        self._save()

    def _configuration(self, namespace: Mapping[str, Any], cell_index: int, boundary: str) -> None:
        values: dict[str, Any] = {}
        for name, value in namespace.items():
            allowed = name in CONFIG_NAMES or (name.isupper() and name.startswith(CONFIG_PREFIXES))
            if not allowed or _SENSITIVE.search(name) or name.endswith(("_PATH", "_DIR", "_FIELDS")):
                continue
            try:
                values[name] = _json_value(value)
            except (TypeError, ValueError):
                continue
        self._guard(_canonical(values).decode())
        digest = _digest(_canonical(values))
        if digest != self._last_configuration:
            self.manifest["configuration_snapshots"].append({
                "cell_index": cell_index, "boundary": boundary, "captured_at": self._now(),
                "sha256": digest, "values": values,
            })
            self._last_configuration = digest

    def _fingerprint_file(self, path: Path) -> dict[str, Any]:
        if path.is_symlink() or not path.is_file():
            raise PackagingError("FILE_NOT_REGULAR")
        self._guard(str(path))
        before = path.stat()
        digest = hashlib.sha256()
        with path.open("rb") as handle:
            for chunk in iter(lambda: handle.read(1024 * 1024), b""):
                digest.update(chunk)
        after = path.stat()
        if (before.st_size, before.st_mtime_ns) != (after.st_size, after.st_mtime_ns):
            raise PackagingError("FILE_CHANGED_DURING_CAPTURE")
        return {"path": str(path), "size_bytes": after.st_size, "sha256": digest.hexdigest()}

    def _inputs(self, namespace: Mapping[str, Any], cell_index: int) -> None:
        for name in INPUT_OBJECT_NAMES:
            if name not in namespace:
                continue
            value = namespace[name]
            if callable(getattr(value, "to_dict", None)):
                value = value.to_dict("records")
            data = _canonical(_json_value(value))
            fingerprint = {"name": name, "kind": "canonical_json_object", "sha256": _digest(data),
                           "size_bytes": len(data), "rows": len(value) if isinstance(value, list) else None}
            self._add_input(fingerprint, cell_index)
        for name in INPUT_FILE_NAMES:
            value = namespace.get(name)
            if isinstance(value, (str, Path)):
                path = Path(value)
                if path.is_file():
                    self._add_input({"name": name, "kind": "file", **self._fingerprint_file(path)}, cell_index)
                elif not any(row["name"] == name and row["path"] == str(path)
                             for row in self.manifest["missing_input_files"]):
                    self._guard(str(path))
                    self.manifest["missing_input_files"].append({
                        "name": name, "path": str(path), "observed_before_cell": cell_index,
                        "status": "NOT_PRESENT", "captured_at": self._now(),
                    })

    def _add_input(self, fingerprint: dict[str, Any], cell_index: int) -> None:
        identity = (fingerprint["name"], fingerprint["sha256"])
        if identity not in self._captured_inputs:
            self.manifest["input_fingerprints"].append({
                **fingerprint, "observed_before_cell": cell_index, "captured_at": self._now(),
            })
            self._captured_inputs.add(identity)

    def before_cell(self, cell_index: int, source: str, namespace: Mapping[str, Any]) -> None:
        self._learn_secrets(namespace)
        expected = dict(self.cells).get(cell_index)
        if source != expected:
            self.manifest["diagnostics"].append("SUBMITTED_SOURCE_CHANGED")
        self.manifest["attempted_cells"].append(cell_index)
        def record_submitted() -> None:
            relative = f"source/submitted/{len(self.manifest['attempted_cells']):04d}-cell-{cell_index}.py"
            self._source(relative, source.encode("utf-8"))
            self.manifest["submitted_sources"].append({
                "cell_index": cell_index, "path": relative, "sha256": _digest(source.encode("utf-8")),
            })
        self._perform("SUBMITTED_SOURCE_CAPTURE_FAILED", record_submitted)
        self._perform("CONFIGURATION_CAPTURE_FAILED", lambda: self._configuration(namespace, cell_index, "before"))
        self._perform("INPUT_CAPTURE_FAILED", lambda: self._inputs(namespace, cell_index))
        self._save()

    def after_cell(self, cell_index: int, namespace: Mapping[str, Any]) -> None:
        self._learn_secrets(namespace)
        self.manifest["completed_cells"].append(cell_index)
        self._perform("CONFIGURATION_CAPTURE_FAILED", lambda: self._configuration(namespace, cell_index, "after"))
        self._save()

    def _outputs(self, namespace: Mapping[str, Any]) -> None:
        directories: set[Path] = set()
        for name in ("DATA_DIR", "OUTPUT_ROOT", "WORK_ROOT"):
            value = namespace.get(name)
            if isinstance(value, (str, Path)):
                path = Path(value)
                directories.add(path if name == "DATA_DIR" else path / ("data" if name == "WORK_ROOT" else "DATA"))
        paths: set[Path] = set()
        for directory in directories:
            if directory.is_dir():
                paths.update(path for path in directory.rglob("*") if path.suffix.lower() in _DATA_SUFFIXES)
        for path in sorted(paths):
            if not _SENSITIVE.search(path.name) and not path.is_symlink():
                self.manifest["output_fingerprints"].append(self._fingerprint_file(path))

    def _validation(self, namespace: Mapping[str, Any]) -> None:
        for phase in (7, 9):
            report: dict[str, Any] = {"status": "MISSING"}
            value = namespace.get(f"PHASE{phase}_SUMMARY_PATH")
            if isinstance(value, (str, Path)) and Path(value).is_file():
                path = Path(value)
                payload = json.loads(path.read_text(encoding="utf-8"))
                if not isinstance(payload, dict):
                    raise PackagingError("VALIDATION_REPORT_NOT_OBJECT")
                selected = {key: _json_value(item) for key, item in payload.items() if key in VALIDATION_FIELDS}
                self._guard(_canonical(selected).decode())
                report = {"status": "CAPTURED", "values": selected, "file": self._fingerprint_file(path)}
            elif f"PHASE{phase}_VALIDATION_STATUS" in namespace:
                status = _json_value(namespace[f"PHASE{phase}_VALIDATION_STATUS"])
                self._guard(_canonical(status).decode())
                report = {"status": "STATUS_ONLY", "value": status}
            self.manifest["validation"][f"phase{phase}"] = report

    def finish(self, namespace: Mapping[str, Any], error: BaseException | None = None) -> None:
        self._learn_secrets(namespace)
        self._perform("CONFIGURATION_CAPTURE_FAILED", lambda: self._configuration(namespace, -1, "final"))
        self._perform("OUTPUT_CAPTURE_FAILED", lambda: self._outputs(namespace))
        self._perform("VALIDATION_CAPTURE_FAILED", lambda: self._validation(namespace))
        self._screen_configuration()
        source_error_count = len(self.manifest["diagnostics"])
        self._perform("SOURCE_FINAL_SCREEN_OR_WRITE_FAILED", self._flush_sources)
        if len(self.manifest["diagnostics"]) > source_error_count:
            self.manifest["source_files"] = [
                row for row in self.manifest["source_files"] if (self.directory / row["path"]).is_file()
            ]
            self.manifest["submitted_sources"] = [
                row for row in self.manifest["submitted_sources"] if (self.directory / row["path"]).is_file()
            ]
        snapshots = self.manifest["configuration_snapshots"]
        values = snapshots[-1]["values"] if snapshots else {}
        missing = sorted(REQUIRED_CONFIG - values.keys())
        self.manifest["missing_required_configuration"] = missing
        self.manifest["execution_status"] = "FAILED" if error is not None else "COMPLETED"
        self.manifest["error_type"] = "MODEL_EXECUTION_ERROR" if error is not None else None
        self.manifest["finished_at"] = self._now()
        incomplete = bool(error is not None or self.manifest["diagnostics"] or missing or
                          self.manifest["missing_input_files"] or
                          len(self.manifest["completed_cells"]) != len(self.cells) or
                          not self.manifest["input_fingerprints"] or not self.manifest["output_fingerprints"] or
                          any(self.manifest["validation"].get(f"phase{phase}", {}).get("status") == "MISSING"
                              for phase in (7, 9)))
        self.manifest["package_status"] = "INCOMPLETE" if incomplete else "COMPLETE"
        self._save(final=True)


def capture_safely(recorder: RunPackage | None, method: str, *arguments: Any) -> None:
    """A provenance failure must not replace the original model exception or output."""
    if recorder is None:
        return
    try:
        getattr(recorder, method)(*arguments)
    except Exception:
        if "PACKAGING_OPERATION_FAILED" not in recorder.manifest["diagnostics"]:
            recorder.manifest["diagnostics"].append("PACKAGING_OPERATION_FAILED")
        recorder.manifest["package_status"] = "INCOMPLETE"
        print("Run packaging incomplete; no exception details or source values are logged.", file=sys.stderr)


def start_package(notebook_path: Path, cells: Sequence[tuple[int, str]], repository_root: Path) -> RunPackage | None:
    try:
        return RunPackage(notebook_path, cells, repository_root=repository_root)
    except Exception:
        print("Run packaging unavailable; no existing package was replaced.", file=sys.stderr)
        return None
