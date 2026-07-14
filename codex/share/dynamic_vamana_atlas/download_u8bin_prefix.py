#!/usr/bin/env python3
"""Fetch an exact prefix without retaining the full BIGANN 1B artifact."""

from __future__ import annotations

import argparse
import json
import os
import re
import time
import urllib.request
from pathlib import Path


CONTENT_RANGE = re.compile(r"^bytes\s+(\d+)-(\d+)/(\d+|\*)$", re.I)


def write_exact(response, destination: Path, expected_bytes: int) -> int:
    temporary = destination.with_suffix(destination.suffix + ".partial")
    written = 0
    with temporary.open("wb") as handle:
        while written < expected_bytes:
            chunk = response.read(min(16 * 1024 * 1024, expected_bytes - written))
            if not chunk:
                break
            handle.write(chunk)
            written += len(chunk)
    if written != expected_bytes:
        temporary.unlink(missing_ok=True)
        raise ValueError(f"short response: expected {expected_bytes} bytes, received {written}")
    os.replace(temporary, destination)
    return written


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--url", required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--bytes", type=int, required=True)
    parser.add_argument("--report", type=Path, required=True)
    args = parser.parse_args()
    if args.bytes <= 0:
        raise ValueError("--bytes must be positive")
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.report.parent.mkdir(parents=True, exist_ok=True)

    if args.output.is_file() and args.output.stat().st_size == args.bytes:
        report = {
            "schema": "dynamic-vamana-u8bin-download-v1",
            "url": args.url,
            "requested_bytes": args.bytes,
            "received_bytes": args.bytes,
            "download_mode": "reused-local",
            "http_status": None,
            "content_range": None,
            "created_utc": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
        }
        args.report.write_text(json.dumps(report, indent=2) + "\n")
        print(json.dumps(report, indent=2))
        return
    if args.output.exists():
        raise ValueError(f"existing output has wrong size: {args.output}")

    end = args.bytes - 1
    ranged = urllib.request.Request(args.url, headers={"Range": f"bytes=0-{end}"})
    with urllib.request.urlopen(ranged, timeout=90) as response:
        status = response.status
        content_range = response.headers.get("Content-Range")
        if status == 206:
            match = CONTENT_RANGE.fullmatch(content_range or "")
            if not match or int(match.group(1)) != 0 or int(match.group(2)) != end:
                raise ValueError(f"invalid Content-Range for prefix: {content_range!r}")
            mode = "http-range"
            received = write_exact(response, args.output, args.bytes)
        elif status == 200:
            # Close the ranged response before a clean streaming request.  Never
            # consume or retain the remaining 1B corpus after the requested prefix.
            mode = "streamed-prefix"
            content_range = None
            received = 0
        else:
            raise ValueError(f"unexpected HTTP status for range request: {status}")

    if mode == "streamed-prefix":
        with urllib.request.urlopen(urllib.request.Request(args.url), timeout=90) as response:
            if response.status != 200:
                raise ValueError(f"stream fallback expected HTTP 200, got {response.status}")
            received = write_exact(response, args.output, args.bytes)

    report = {
        "schema": "dynamic-vamana-u8bin-download-v1",
        "url": args.url,
        "requested_bytes": args.bytes,
        "received_bytes": received,
        "download_mode": mode,
        "http_status": status,
        "content_range": content_range,
        "created_utc": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
    }
    args.report.write_text(json.dumps(report, indent=2) + "\n")
    print(json.dumps(report, indent=2))


if __name__ == "__main__":
    main()
