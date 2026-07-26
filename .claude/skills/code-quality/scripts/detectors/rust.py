"""Rust detector — wraps cargo-udeps (D1) + crates.io registry lookup (D2).

T1.3 implementation: detect_dead_code via cargo-udeps subprocess.
T2.4 implementation: detect_symbol_fabrication via tree-sitter + crates.io.
Other methods still stubs (T3.1) — T4.3 ADR DEFER for mutation.
"""
from __future__ import annotations

import re
import subprocess
from pathlib import Path

from scripts import _registry
from scripts._shared import Finding, safe_parse_json, sanitize_symbol, to_rel_path
from scripts.check_symbol_fab import extract_imports_and_calls

from . import BaseDetector

_RUST_MODULE_LOCAL_PREFIXES = ("crate::", "self::", "super::", "crate", "self", "super")

# Rust standard-library crates — always in-scope, never published to crates.io.
# Treating them as "fabricated crates" is a detector bug, not a code defect.
_RUST_STDLIB_CRATES = frozenset({"std", "core", "alloc", "proc_macro", "test"})

_CARGO_UDEPS_TIMEOUT_SEC = 180


def _norm_crate(name: str) -> str:
    """Cargo package names use `-`; `use` paths use `_`. Compare on the `_` form."""
    return name.strip().replace("-", "_")


def _workspace_member_crates(changed_files: list[Path]) -> frozenset[str]:
    """Collect local Cargo package names so intra-workspace `use` isn't fabricated.

    Walks up from each changed file to the workspace root (the nearest ancestor
    whose `Cargo.toml` declares `[workspace]`), then reads every `Cargo.toml`
    under it for `name = "..."`. Names are normalized to the underscore form used
    in `use` paths. Dependency-free (regex, no TOML lib) and failure-tolerant.
    """
    roots: set[Path] = set()
    for f in changed_files:
        cur = f.resolve().parent
        while True:
            manifest = cur / "Cargo.toml"
            try:
                if manifest.is_file() and "[workspace]" in manifest.read_text(
                    encoding="utf-8", errors="ignore"
                ):
                    roots.add(cur)
                    break
            except OSError:
                pass
            if cur.parent == cur:
                break
            cur = cur.parent

    names: set[str] = set()
    name_re = re.compile(r'^\s*name\s*=\s*"([^"]+)"', re.MULTILINE)
    for root in roots:
        for manifest in root.rglob("Cargo.toml"):
            if "target" in manifest.parts:
                continue
            try:
                text = manifest.read_text(encoding="utf-8", errors="ignore")
            except OSError:
                continue
            for m in name_re.finditer(text):
                names.add(_norm_crate(m.group(1)))
    return frozenset(names)


class RustDetector(BaseDetector):
    language = "rust"
    manifest_marker = "Cargo.toml"

    def detect_dead_code(self, repo_root: Path) -> list[Finding]:
        """Run `cargo +nightly udeps --output json` and parse unused deps."""
        cmd = ["cargo", "+nightly", "udeps", "--output", "json", "--all-targets"]
        try:
            result = subprocess.run(
                cmd,
                cwd=str(repo_root),
                capture_output=True,
                text=True,
                timeout=_CARGO_UDEPS_TIMEOUT_SEC,
                check=False,
            )
        except FileNotFoundError:
            return [self._auditor_unavailable("cargo +nightly udeps not found (install nightly + cargo-udeps)")]
        except subprocess.TimeoutExpired:
            return [self._auditor_unavailable(f"cargo-udeps timed out after {_CARGO_UDEPS_TIMEOUT_SEC}s")]
        except (subprocess.SubprocessError, OSError) as e:
            return [self._auditor_unavailable(f"cargo-udeps invocation failed: {e}")]

        if not result.stdout.strip():
            # No JSON output — likely no Cargo.toml or build error
            if result.returncode != 0:
                return [
                    self._auditor_unavailable(
                        f"cargo-udeps exit {result.returncode}: {result.stderr.strip()[:200]}"
                    )
                ]
            return []

        data, parse_finding = safe_parse_json(result.stdout, "cargo-udeps")
        if parse_finding is not None:
            return [
                Finding(
                    detector="d1_dead_code",
                    language="rust",
                    severity="SOFT_CAP",
                    file_path=".",
                    symbol_or_line="cargo-udeps",
                    message=f"cargo-udeps JSON output failed to parse: {parse_finding.message}",
                    allowlist_key="rust|.|dead_code|auditor_output_malformed_cargo-udeps",
                )
            ]
        return self._parse_udeps_json(data)

    def detect_symbol_fabrication(self, changed_files: list[Path]) -> list[Finding]:
        """T2.4 — Validate `use` statements against crates.io. Skip module-local (EC-17 analog)."""
        findings: list[Finding] = []
        workspace_crates = _workspace_member_crates(changed_files)
        for src_file in changed_files:
            if not src_file.exists():
                continue
            rel = to_rel_path(src_file)
            for sym in extract_imports_and_calls(src_file, "rust"):
                if sym.kind != "import":
                    continue
                module = sym.module
                if not module:
                    continue
                # EC-17 analog — module-local
                if any(module == p or module.startswith(p) for p in _RUST_MODULE_LOCAL_PREFIXES):
                    continue
                # Extract crate name (first segment of "serde::Deserialize"), stripping
                # any `use x as y` alias that the extractor preserves verbatim.
                crate = module.split("::", 1)[0].split(" as ", 1)[0].strip()
                if not crate:
                    continue
                # Rust stdlib is never on crates.io; skip without a registry hit.
                if crate in _RUST_STDLIB_CRATES:
                    continue
                # A crate defined in this Cargo workspace is not a fabricated crate.
                if _norm_crate(crate) in workspace_crates:
                    continue
                exists = _registry.crate_exists_on_crates_io(crate)
                if exists is True:
                    continue
                sanitized = sanitize_symbol(crate)
                if exists is False:
                    findings.append(
                        Finding(
                            detector="d2_symbol_fab",
                            language="rust",
                            severity="HARD",
                            file_path=rel,
                            symbol_or_line=f"use {module}",
                            message=f"Fabricated crate '{crate}' (not found on crates.io)",
                            allowlist_key=f"rust|{rel}|symbol_fab|{sanitized}",
                        )
                    )
                else:
                    findings.append(
                        Finding(
                            detector="d2_symbol_fab",
                            language="rust",
                            severity="SOFT_FLOOR",
                            file_path=rel,
                            symbol_or_line=f"use {module}",
                            message=f"Could not verify crate '{crate}' (ambiguous response)",
                            allowlist_key=f"rust|{rel}|symbol_fab|symbol_fab_unverifiable_{sanitized}",
                        )
                    )
        return findings

    def detect_orphan_exports(self, repo_root: Path) -> list[Finding]:
        raise NotImplementedError("T3.1: cross-package wiring detector not yet implemented")

    def detect_mutation_score(self, critical_paths: list[Path]) -> list[Finding]:
        # T4.3 — DEFERRED to v0.2 (evaluate cargo-mutants vs gremlins first)
        raise NotImplementedError("T4.3: Rust mutation testing DEFERRED to v0.2 (graceful skip)")

    # ------------------------------------------------------------------

    def _parse_udeps_json(self, data: dict) -> list[Finding]:
        findings: list[Finding] = []
        unused = data.get("unused_deps", {}) or {}
        for crate_id, sections in unused.items():
            for section_name in ("normal", "development", "build"):
                for dep_name in sections.get(section_name, []) or []:
                    sanitized = sanitize_symbol(dep_name)
                    findings.append(
                        Finding(
                            detector="d1_dead_code",
                            language="rust",
                            severity="HARD",
                            file_path="Cargo.toml",
                            symbol_or_line=f"{dep_name} ({section_name}, crate={crate_id})",
                            message=f"Unused {section_name} dependency '{dep_name}' "
                            f"in crate {crate_id}",
                            allowlist_key=f"rust|Cargo.toml|dead_code|{sanitized}",
                        )
                    )
        return findings

    def _auditor_unavailable(self, reason: str) -> Finding:
        return Finding(
            detector="d1_dead_code",
            language="rust",
            severity="SOFT_CAP",
            file_path=".",
            symbol_or_line="cargo-udeps",
            message=f"cargo-udeps auditor unavailable: {reason}",
            allowlist_key="rust|.|dead_code|auditor_unavailable_cargo-udeps",
        )
