import json
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
MANIFEST_PATH = REPO_ROOT / "data" / "policy" / "manifest.json"
SOURCES_DIR = REPO_ROOT / "data" / "policy" / "sources"

EXPECTED_INDICATORS = {
    "name_mismatch",
    "address_mismatch",
    "missing_required_field",
    "invalid_document_date",
    "reference_customer_not_found",
    "unsupported_document_type",
}


def test_policy_manifest_exists_and_is_versioned():
    assert MANIFEST_PATH.is_file()
    manifest = json.loads(MANIFEST_PATH.read_text(encoding="utf-8"))
    assert manifest["corpus_id"] == "kyc-demo-policy-corpus"
    assert manifest["corpus_version"]
    assert manifest["external_sources_allowed"] is False
    assert manifest["items"]


def test_every_required_risk_indicator_has_a_policy_source():
    manifest = json.loads(MANIFEST_PATH.read_text(encoding="utf-8"))
    indicators = {item["risk_indicator"] for item in manifest["items"]}
    assert indicators == EXPECTED_INDICATORS


def test_manifest_sources_exist_and_have_stable_versions():
    manifest = json.loads(MANIFEST_PATH.read_text(encoding="utf-8"))
    source_ids = set()

    for item in manifest["items"]:
        source_id = item["source_id"]
        version = item["version"]
        source_path = REPO_ROOT / item["path"]

        assert source_id
        assert source_id not in source_ids
        source_ids.add(source_id)

        assert version
        assert source_path.is_file()

        content = source_path.read_text(encoding="utf-8")
        assert f"source_id: {source_id}" in content
        assert f"version: {version}" in content
        assert item["risk_indicator"] in content


def test_policy_sources_are_marked_as_project_controlled_content():
    manifest = json.loads(MANIFEST_PATH.read_text(encoding="utf-8"))

    for item in manifest["items"]:
        source_path = REPO_ROOT / item["path"]
        content = source_path.read_text(encoding="utf-8")

        assert "project-authored controlled demo content" in content
        assert "No external web or regulatory source is used." in content
