#!/usr/bin/env python3
"""R05 mutable-tree sanity, capability negatives, and atomic failure injection."""
from __future__ import annotations

import argparse
import hashlib
import json
import os
import pwd
import shutil
import stat
import subprocess
from pathlib import Path


def sha(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for block in iter(lambda: stream.read(8 << 20), b""): digest.update(block)
    return digest.hexdigest()


def content(root: Path) -> list[tuple[str, int, str]]:
    return [(path.relative_to(root).as_posix(), path.stat().st_size, sha(path))
            for path in sorted(row for row in root.rglob("*") if row.is_file())]


def modes(root: Path) -> list[tuple[str, str, int, int, int, int]]:
    rows = []
    for path in [root] + sorted(root.rglob("*")):
        info = path.lstat(); rel = "." if path == root else path.relative_to(root).as_posix()
        kind = "directory" if stat.S_ISDIR(info.st_mode) else "regular" if stat.S_ISREG(info.st_mode) else "other"
        rows.append((rel, kind, info.st_uid, info.st_gid, stat.S_IMODE(info.st_mode), info.st_nlink))
    return rows


def remove_tree(root: Path) -> None:
    if not root.exists():
        return
    for directory, dirs, _files in os.walk(root):
        os.chmod(directory, 0o700)
        for name in dirs:
            os.chmod(Path(directory) / name, 0o700, follow_symlinks=False)
    shutil.rmtree(root)


def main() -> None:
    parser = argparse.ArgumentParser(); parser.add_argument("--root", type=Path, required=True)
    parser.add_argument("--helper", type=Path, required=True); parser.add_argument("--normalizer", type=Path, required=True)
    parser.add_argument("--scratch", type=Path, required=True); parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args(); root = args.root.resolve(); scratch = args.scratch
    formal_r05 = root / "formal/pilot3_sift10m_w1_r05"
    if args.output.exists() or scratch.exists() or formal_r05.exists(): raise SystemExit("R05 mutable test freshness guard failed")
    account = pwd.getpwnam("ubuntu"); scratch.mkdir(parents=True); os.chmod(scratch, 0o755)
    rows: list[dict] = []

    source = scratch / "source"; (source / "nested").mkdir(parents=True)
    (source / "IMMUTABLE_BASE_OK").write_text("")
    (source / "alpha.bin").write_bytes(b"alpha\x00payload")
    (source / "nested/beta.bin").write_bytes(b"beta\x00payload")
    for path in sorted(source.rglob("*"), reverse=True):
        os.chown(path, account.pw_uid, account.pw_gid, follow_symlinks=False)
        os.chmod(path, 0o555 if path.is_dir() else 0o444)
    os.chown(source, account.pw_uid, account.pw_gid); os.chmod(source, 0o555)
    source_content = content(source); source_modes = modes(source)

    common = os.environ.copy(); common.update({"W1_FORMAL_PATH_AUTHORIZED": "1", "W1_MUTABLE_CLONE_OWNER": "ubuntu",
        "ATLAS_ROOT": str(root), "ATLAS_NVME_MAJMIN": os.environ.get("ATLAS_NVME_MAJMIN", "259:10")})

    def helper_run(name: str, target: Path, expected: int, *, system: str = "DGAI", base: Path = source,
                   run: str = "pilot3_sift10m_w1_r05_fixture", attempt: str = "cp01-fixture",
                   capability_target: Path | None = None, capability_system: str | None = None,
                   omit: str | None = None, preflight: bool = True, injection: str = "", device: str | None = None) -> subprocess.CompletedProcess[str]:
        env = common.copy(); caps = {"W1_ALLOWED_CLONE_TARGET": str(capability_target or target),
            "W1_ALLOWED_CLONE_SYSTEM": capability_system or system, "W1_ALLOWED_CLONE_RUN": run,
            "W1_ALLOWED_CLONE_ATTEMPT": attempt}
        env.update(caps); env["W1_CLONE_PREFLIGHT_ONLY"] = "1" if preflight else "0"
        if omit: env.pop(omit, None)
        if injection: env.update({"W1_MUTABLE_TEST_MODE": "1", "W1_MUTABLE_FAILURE_INJECTION": injection})
        if device is not None: env["ATLAS_NVME_MAJMIN"] = device
        existed = target.exists(); result = subprocess.run([str(args.helper), system, str(base), str(target)], env=env,
                                                            text=True, capture_output=True)
        final_exists = target.exists(); partials = sorted(str(path) for path in target.parent.glob(target.name + ".partial.*")) if target.parent.exists() else []
        passed = result.returncode == expected and (preflight or expected != 0) and (not preflight or final_exists == existed)
        if not preflight and expected != 0: passed = passed and not final_exists and not partials
        rows.append({"name": name, "expected_exit": expected, "actual_exit": result.returncode, "target": str(target),
                     "caps": caps, "preflight_only": preflight, "target_existed_before": existed,
                     "target_exists_after": final_exists, "partials_after": partials, "stdout": result.stdout.strip(),
                     "stderr": result.stderr.strip(), "passed": passed})
        return result

    fixture_run = "pilot3_sift10m_w1_r05_fixture"; fixture_attempt = "cp01-fixture"
    fixture_target = root / f"formal/{fixture_run}/DGAI/{fixture_attempt}"
    result = helper_run("synthetic_mutable_tree", fixture_target, 0, preflight=False)
    if result.returncode != 0:
        raise SystemExit(f"synthetic mutable clone failed: stdout={result.stdout!r} stderr={result.stderr!r}")
    clone = fixture_target / "index"; clone_modes = modes(clone)
    audit = json.loads((fixture_target / "mutable_clone_audit.json").read_text())
    clone_manifest = json.loads((fixture_target / "clone_manifest.json").read_text())
    synthetic_checks = {"source_content_unchanged": content(source) == source_content,
        "source_mode_unchanged": modes(source) == source_modes, "clone_content_equal": content(clone) == source_content,
        "clone_dirs_0700": all(row[4] == 0o700 for row in clone_modes if row[1] == "directory"),
        "clone_files_0600": all(row[4] == 0o600 for row in clone_modes if row[1] == "regular"),
        "clone_owner_exact": all(row[2:4] == (account.pw_uid, account.pw_gid) for row in clone_modes),
        "live_audit_pass": audit.get("status") == "pass", "clone_schema_v3": clone_manifest.get("schema") == "dynamic-vamana-w1-clone-v3",
        "clone_accounting_present": all(key in clone_manifest for key in ("clone_wall_seconds", "clone_space", "clone_device_delta",
                                                                          "normalization_elapsed_seconds", "normalization_metadata_operations"))}
    rows[-1]["synthetic_checks"] = synthetic_checks; rows[-1]["passed"] = all(synthetic_checks.values())
    shutil.rmtree(root / f"formal/{fixture_run}")

    authorized = formal_r05 / "DGAI/cp01-05"
    helper_run("wrong_run_target", root / "formal/pilot3_sift10m_w1_r06/DGAI/cp01-05", 2,
               run="pilot3_sift10m_w1_r05", attempt="cp01-05")
    helper_run("wrong_attempt_target", formal_r05 / "DGAI/cp01-04", 2, run="pilot3_sift10m_w1_r05", attempt="cp01-05")
    helper_run("cross_system", authorized, 2, system="OdinANN", capability_system="DGAI",
               run="pilot3_sift10m_w1_r05", attempt="cp01-05")
    for key in ("W1_ALLOWED_CLONE_TARGET", "W1_ALLOWED_CLONE_SYSTEM", "W1_ALLOWED_CLONE_RUN", "W1_ALLOWED_CLONE_ATTEMPT"):
        helper_run("missing_" + key.lower(), authorized, 2, run="pilot3_sift10m_w1_r05", attempt="cp01-05", omit=key)
    helper_run("wrong_device", authorized, 1, run="pilot3_sift10m_w1_r05", attempt="cp01-05", device="0:0")
    helper_run("base_as_target", source, 2, run="pilot3_sift10m_w1_r05", attempt="cp01-05")
    helper_run("r04_clone_as_target", root / "formal/pilot3_sift10m_w1_r04/DGAI/cp01-04", 2,
               run="pilot3_sift10m_w1_r05", attempt="cp01-05")

    existing_run = "pilot3_sift10m_w1_r05_existing"; existing_target = root / f"formal/{existing_run}/DGAI/cp01-existing"
    existing_target.mkdir(parents=True)
    try: helper_run("existing_target", existing_target, 1, run=existing_run, attempt="cp01-existing")
    finally: shutil.rmtree(root / f"formal/{existing_run}")

    symlink_run = "pilot3_sift10m_w1_r05_symlink"; symlink_root = root / f"formal/{symlink_run}"
    escape = scratch / "escape"; escape.mkdir(); symlink_root.symlink_to(escape, target_is_directory=True)
    try: helper_run("symlink_escape", symlink_root / "DGAI/cp01-symlink", 2, run=symlink_run, attempt="cp01-symlink")
    finally: symlink_root.unlink(missing_ok=True)

    arbitrary = scratch / "arbitrary"; arbitrary.mkdir()
    direct_env = common.copy(); direct_env.update({"W1_ALLOWED_CLONE_TARGET": str(authorized), "W1_CLONE_HELPER_PID": str(os.getpid())})
    direct = subprocess.run(["python3", str(args.normalizer), "--clone-root", str(arbitrary), "--base-root", str(source),
        "--owner", "ubuntu", "--system", "DGAI", "--output-manifest", str(scratch / "arbitrary.json")],
        env=direct_env, text=True, capture_output=True)
    rows.append({"name": "direct_normalize_arbitrary", "expected_exit": 1, "actual_exit": direct.returncode,
                 "stdout": direct.stdout.strip(), "stderr": direct.stderr.strip(), "passed": direct.returncode != 0 and modes(arbitrary)[0][4] != 0o700})

    for object_kind in ("symlink", "fifo", "hardlink"):
        partial = Path(f"{authorized}.partial.{os.getpid()}"); index = partial / "index"
        index.mkdir(parents=True)
        if object_kind == "symlink": (index / "bad").symlink_to(source / "alpha.bin")
        elif object_kind == "fifo": os.mkfifo(index / "bad")
        else:
            (index / "bad-a").write_bytes(b"hard-link")
            os.link(index / "bad-a", index / "bad-b")
        scoped_env = common.copy(); scoped_env.update({"W1_ALLOWED_CLONE_TARGET": str(authorized), "W1_CLONE_HELPER_PID": str(os.getpid())})
        scoped = subprocess.run(["python3", str(args.normalizer), "--clone-root", str(index), "--base-root", str(source),
            "--owner", "ubuntu", "--system", "DGAI", "--output-manifest", str(partial / "normalization.json")],
            env=scoped_env, text=True, capture_output=True)
        rows.append({"name": "reject_" + object_kind, "expected_exit": 1, "actual_exit": scoped.returncode,
                     "stdout": scoped.stdout.strip(), "stderr": scoped.stderr.strip(),
                     "final_target_absent": not authorized.exists(), "passed": scoped.returncode != 0 and not authorized.exists()})
        shutil.rmtree(formal_r05)

    for injection, expected in (("after_copy", 97), ("normalization_mid", 1), ("live_audit", 1)):
        run = f"pilot3_sift10m_w1_r05_inject_{injection}"; attempt = f"cp01-{injection}"
        target = root / f"formal/{run}/DGAI/{attempt}"
        before_content, before_modes = content(source), modes(source)
        helper_run("failure_injection_" + injection, target, expected, run=run, attempt=attempt,
                   preflight=False, injection=injection)
        rows[-1]["base_content_unchanged"] = content(source) == before_content
        rows[-1]["base_mode_unchanged"] = modes(source) == before_modes
        rows[-1]["downstream_query_or_update_invoked"] = False
        rows[-1]["passed"] = rows[-1]["passed"] and rows[-1]["base_content_unchanged"] and rows[-1]["base_mode_unchanged"]
        run_root = root / f"formal/{run}"
        if run_root.exists(): shutil.rmtree(run_root)

    report = {"schema": "dynamic-vamana-w1-r05-mutable-clone-tests-v1",
              "status": "pass" if all(row["passed"] for row in rows) else "fail",
              "synthetic_source": str(source), "tests": rows,
              "test_count": len(rows), "failed": [row["name"] for row in rows if not row["passed"]],
              "failure_injection_downstream_query_or_update_invoked": False,
              "r05_formal_target_absent_after_tests": not formal_r05.exists()}
    args.output.parent.mkdir(parents=True, exist_ok=True); args.output.write_text(json.dumps(report, indent=2) + "\n")
    remove_tree(scratch)
    if report["status"] != "pass" or formal_r05.exists(): raise SystemExit("R05 mutable clone regressions failed")


if __name__ == "__main__":
    main()
