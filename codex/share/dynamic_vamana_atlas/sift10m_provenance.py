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
    parser.add_argument("--source-format", choices=("bvecs", "u8bin"), default="bvecs")
    parser.add_argument("--source-review-status", default="operator-source-review-required")
    parser.add_argument("--base-normalized-u8bin", type=Path)
    parser.add_argument("--query-normalized-u8bin", type=Path)
    parser.add_argument("--base-download-report", type=Path)
    parser.add_argument("--query-download-report", type=Path)
    parser.add_argument("--base-normalization-report", type=Path)
    parser.add_argument("--query-normalization-report", type=Path)
    parser.add_argument("--base-conversion-report", type=Path)
    parser.add_argument("--query-conversion-report", type=Path)
    parser.add_argument("--conversion-tool", type=Path)
    parser.add_argument("--conversion-command", default="")


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
    if args.base_normalized_u8bin:
        files["base_10m_u8bin"] = args.base_normalized_u8bin
    if args.query_normalized_u8bin:
        files["query_10k_u8bin"] = args.query_normalized_u8bin
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
    reports: dict[str, object] = {}
    for name, path in {
        "base_download": args.base_download_report,
        "query_download": args.query_download_report,
        "base_normalization": args.base_normalization_report,
        "query_normalization": args.query_normalization_report,
        "base_conversion": args.base_conversion_report,
        "query_conversion": args.query_conversion_report,
    }.items():
        if path:
            if not path.is_file():
                raise FileNotFoundError(path)
            reports[name] = json.loads(path.read_text())
    payload["source_identity"] = {
        "dataset": "BIGANN",
        "source_format": args.source_format,
        "source_corpus": "base.1B.u8bin prefix" if args.source_format == "u8bin" else "BIGANN bvecs prefix",
        "source_query": "query.public.10K.u8bin" if args.source_format == "u8bin" else "BIGANN query bvecs",
        "source_review_status": args.source_review_status,
        "metric": "squared-l2",
        "dimension": 128,
        "dtype_source": "uint8",
        "dtype_canonical": "float32",
    }
    payload["u8bin_audit_reports"] = reports
    if args.conversion_tool:
        if not args.conversion_tool.is_file():
            raise FileNotFoundError(args.conversion_tool)
        payload["conversion_tool"] = {
            "path": str(args.conversion_tool.resolve()),
            "sha256": sha256(args.conversion_tool),
            "command": args.conversion_command,
        }
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
    if expected.get("source_identity") != payload["source_identity"]:
        raise ValueError("source identity changed since provenance record")
    if expected.get("u8bin_audit_reports") != payload["u8bin_audit_reports"]:
        raise ValueError("u8bin audit reports changed since provenance record")
    print(json.dumps({"verified": True, "manifest": str(args.manifest)}, indent=2))


if __name__ == "__main__":
    main()
