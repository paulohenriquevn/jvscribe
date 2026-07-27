"""T1.3 — RustDetector.detect_dead_code (cargo-udeps wrapper) tests.

cargo-udeps requires nightly toolchain. Tests use subprocess mocks.
"""
from __future__ import annotations

import json
from pathlib import Path
from unittest.mock import patch

import pytest

from scripts.detectors.rust import RustDetector

pytestmark = pytest.mark.rust


_UDEPS_POSITIVE_JSON = json.dumps(
    {
        "success": False,
        "unused_deps": {
            "my-crate 0.1.0": {
                "manifest_path": "/abs/Cargo.toml",
                "normal": ["unused-crate"],
                "development": [],
                "build": [],
            }
        },
    }
)

_UDEPS_CLEAN_JSON = json.dumps({"success": True, "unused_deps": {}})


def _mock_run(stdout: str, returncode: int = 0, stderr: str = ""):
    class _R:
        def __init__(self) -> None:
            self.stdout = stdout
            self.stderr = stderr
            self.returncode = returncode

    return _R()


def test_rust_detector_flags_unused_dep(tmp_path: Path) -> None:
    det = RustDetector()
    with patch("subprocess.run", return_value=_mock_run(_UDEPS_POSITIVE_JSON, 1)):
        findings = det.detect_dead_code(tmp_path)
    dead = [f for f in findings if f.detector == "d1_dead_code"]
    assert any("unused-crate" in f.symbol_or_line for f in dead)


def test_rust_detector_no_findings_on_clean(tmp_path: Path) -> None:
    det = RustDetector()
    with patch("subprocess.run", return_value=_mock_run(_UDEPS_CLEAN_JSON, 0)):
        findings = det.detect_dead_code(tmp_path)
    dead = [f for f in findings if f.detector == "d1_dead_code"]
    assert dead == []


def test_rust_detector_emits_auditor_unavailable_when_nightly_missing(tmp_path: Path) -> None:
    det = RustDetector()
    with patch("subprocess.run", side_effect=FileNotFoundError("cargo +nightly missing")):
        findings = det.detect_dead_code(tmp_path)
    assert len(findings) == 1
    assert "auditor_unavailable_cargo-udeps" in findings[0].allowlist_key


def test_rust_detector_handles_malformed_json(tmp_path: Path) -> None:
    det = RustDetector()
    with patch("subprocess.run", return_value=_mock_run("not json at all", 1)):
        findings = det.detect_dead_code(tmp_path)
    assert len(findings) == 1
    assert "auditor_output_malformed_cargo-udeps" in findings[0].allowlist_key


# --- D2 symbol-fabrication false-positive regressions (rust.py) ---------------
# The Rust D2 detector flagged 98 false positives on the macaw workspace:
# 57 stdlib (`std`), 40 workspace-internal crates (`macaw_*`), 1 `use x as y`
# alias whose ` as pulse` suffix polluted the crate name. All three are detector
# bugs, not fabricated symbols. These tests pin the fix.


def _d2(findings):
    return [f for f in findings if f.detector == "d2_symbol_fab"]


def test_symbol_fab_skips_rust_stdlib(tmp_path: Path) -> None:
    """`std`/`core`/`alloc` are never on crates.io — must not hit the registry."""
    src = tmp_path / "a.rs"
    src.write_text("use std::collections::HashMap;\nuse core::fmt;\n")
    det = RustDetector()
    with patch("scripts.detectors.rust._registry.crate_exists_on_crates_io") as m:
        findings = det.detect_symbol_fabrication([src])
    m.assert_not_called()
    assert _d2(findings) == []


def test_symbol_fab_skips_workspace_member_crate(tmp_path: Path) -> None:
    """A crate defined in the same Cargo workspace is not a fabricated crate."""
    (tmp_path / "Cargo.toml").write_text('[workspace]\nmembers = ["crates/*"]\n')
    crate_dir = tmp_path / "crates" / "macaw-asr"
    crate_dir.mkdir(parents=True)
    (crate_dir / "Cargo.toml").write_text('[package]\nname = "macaw-asr"\n')
    src = crate_dir / "src" / "lib.rs"
    src.parent.mkdir()
    # a sibling crate importing the workspace member (underscore form)
    src.write_text("use macaw_asr::AsrEngine;\n")
    det = RustDetector()
    with patch("scripts.detectors.rust._registry.crate_exists_on_crates_io") as m:
        findings = det.detect_symbol_fabrication([src])
    m.assert_not_called()
    assert _d2(findings) == []


def test_symbol_fab_strips_use_alias(tmp_path: Path) -> None:
    """`use libpulse_binding as pulse;` must query the registry with the bare crate."""
    src = tmp_path / "a.rs"
    src.write_text("use libpulse_binding as pulse;\n")
    det = RustDetector()
    with patch(
        "scripts.detectors.rust._registry.crate_exists_on_crates_io", return_value=True
    ) as m:
        findings = det.detect_symbol_fabrication([src])
    m.assert_called_once_with("libpulse_binding")
    assert _d2(findings) == []
