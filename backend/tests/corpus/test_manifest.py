from pathlib import Path

import pytest

from hr_assist.corpus import ManifestError, load_manifest

VALID_ENTRY = """
- path: data/policies/02_Leave_and_Absence_Standard_v1.2.pdf
  document_id: NDS-HR-LAS-002
  document_version: v1.2
  title: Leave and Absence Standard
  kind: policy_document
  status: current
  effective_from: 2026-10-01
  effective_to: null
"""


def write_manifest(tmp_path: Path, text: str) -> Path:
    path = tmp_path / "manifest.yaml"
    path.write_text(text)
    return path


def test_a_valid_manifest_loads(tmp_path: Path) -> None:
    [entry] = load_manifest(write_manifest(tmp_path, VALID_ENTRY))

    assert entry.document_id == "NDS-HR-LAS-002"
    assert entry.kind == "policy_document"
    assert entry.effective_to is None


@pytest.mark.parametrize(
    ("change", "problem"),
    [
        (("document_id: NDS-HR-LAS-002", "document_id: ''"), "document_id"),
        (("  document_id: NDS-HR-LAS-002\n", ""), "document_id"),
        (("kind: policy_document", "kind: newsletter"), "kind"),
        (("effective_to: null", "effective_to: 2026-01-01"), "effective_to"),
    ],
    ids=["blank-document-id", "missing-document-id", "unknown-kind", "inverted-effective-period"],
)
def test_manifest_validation_rejects_bad_entries(
    tmp_path: Path, change: tuple[str, str], problem: str
) -> None:
    text = VALID_ENTRY.replace(*change)

    with pytest.raises(ManifestError, match=problem):
        load_manifest(write_manifest(tmp_path, text))
