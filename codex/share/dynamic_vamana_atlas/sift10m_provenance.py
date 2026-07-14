#!/usr/bin/env python3
"""Record and verify SIFT10M source/conversion provenance without trusting names."""

from __future__ import annotations

import argparse
import hashlib
import json
import time
from pathlib import Path


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        while chunk := handle.read(16 * 1024 * 1024):
            digest.update(chunk)
    return digest.hexdigest()


def add_common_arguments(parser: argparse.ArgumentParser) -> None:
    parser.add_argument("--manifest", type=Path, required=True)
    parser.add_argument("--base-source", type=Path, required=True)
    parser.add_argument("--query-source", type=Path, required=True)
    parser.add_argument("--base-fbin", type=Path, required=True)
    parser.add_argument("--query-fbin", type=Path, required=True)
    parser.add_argument("--base-expected-sha256", default="")
    parser.add_argument("--query-expected-sha256", default="")


def normalized_expected(value: str) -> str | None:
    value = value.strip().lower()
    if not value:
        return None
    if len(value) != 64 or any(ch not in "0123456789abcdef" for ch in value):
        raise ValueError("expected SHA256 must be 64 lowercase/uppercase hex characters")
    return value


def actual_payload(args: argparse.Namespace) -> dict[str, object]:
    files = {
        "base_source": args.base_source,
        "query_source": args.query_source,
        "base_10m_fbin": args.base_fbin,
        "query_fbin": args.query_fbin,
    }
    payload: dict[str, object] = {"files": {}}
    for name, path in files.items():
        if not path.is_file():
            raise FileNotFoundError(path)
        payload["files"][name] = {
            "path": str(path.resolve()),
            "bytes": path.stat().st_size,
            "sha256": sha256(path),
        }
    base_expected = normalized_expected(args.base_expected_sha256)
    query_expected = normalized_expected(args.query_expected_sha256)
    payload["expected_hashes"] = {
        "base_source_sha256": base_expected,
        "query_source_sha256": query_expected,
        "expected_hash_available": bool(base_expected and query_expected),
    }
    if base_expected and payload["files"]["base_source"]["sha256"] != base_expected:
        raise ValueError("base source SHA256 does not match SIFT10M_BASE_EXPECTED_SHA256")
    if query_expected and payload["files"]["query_source"]["sha256"] != query_expected:
        raise ValueError("query source SHA256 does not match SIFT10M_QUERY_EXPECTED_SHA256")
    return payload


def main() -> None:
    parser = argparse.ArgumentParser()
    subparsers = parser.add_subparsers(dest="action", required=True)
    record = subparsers.add_parser("record")
    verify = subparsers.add_parser("verify")
    verify_recorded = subparsers.add_parser("verify-recorded")
    for subparser in (record, verify):
        add_common_arguments(subparser)
    record.add_argument("--base-url", default="")
    record.add_argument("--query-url", default="")
    verify_recorded.add_argument("--manifest", type=Path, required=True)
    args = parser.parse_args()

    if args.action == "verify-recorded":
        expected = json.loads(args.manifest.read_text())
        if expected.get("schema") != "dynamic-vamana-sift10m-provenance-v2":
            raise ValueError("unexpected provenance schema")
        for name, recorded in expected.get("files", {}).items():
            path = Path(recorded["path"])
            if not path.is_file() or path.stat().st_size != recorded["bytes"] or sha256(path) != recorded["sha256"]:
                raise ValueError(f"recorded provenance no longer matches {name}")
        print(json.dumps({"verified": True, "manifest": str(args.manifest)}, indent=2))
        return

    payload = actual_payload(args)
    if args.action == "record":
        payload.update(
            {
                "schema": "dynamic-vamana-sift10m-provenance-v2",
                "created_utc": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
                "base_source_url": args.base_url or None,
                "query_source_url": args.query_url or None,
                "standard_corpus_status": (
                    "expected-hash-verified"
                    if payload["expected_hashes"]["expected_hash_available"]
                    else "operator-source-review-required"
                ),
            }
        )
        args.manifest.parent.mkdir(parents=True, exist_ok=True)
        args.manifest.write_text(json.dumps(payload, indent=2) + "\n")
        print(json.dumps(payload, indent=2))
        return

    expected = json.loads(args.manifest.read_text())
    if expected.get("schema") != "dynamic-vamana-sift10m-provenance-v2":
        raise ValueError("unexpected provenance schema")
    for name, detail in payload["files"].items():
        recorded = expected.get("files", {}).get(name, {})
        if recorded.get("sha256") != detail["sha256"] or recorded.get("bytes") != detail["bytes"]:
            raise ValueError(f"provenance mismatch for {name}")
    print(json.dumps({"verified": True, "manifest": str(args.manifest)}, indent=2))


if __name__ == "__main__":
    main()
