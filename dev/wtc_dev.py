"""Dev wrapper around the stock wt-compiler CLI (no wt-compiler changes).

Patches only how the discovery env is built, then hands off to
wt_compiler.cli.main() with the same flags.

WTC_DEV_MODE:
  baseline        stock behaviour
  shared-cache    rattler's shared package cache instead of a temp one
  persistent-env  + keep the discovery env, keyed on solved package sha256s
  skip-solve      + skip the solve when the requested specs/channels are unchanged
WTC_DEV_CACHE: where persistent envs live (default ~/.cache/wt-dev-discovery)

Relies on wt_compiler.discovery internals, so it only patches the versions in
TESTED_WT_COMPILER and falls back to stock behaviour on any other version.
"""

import hashlib
import importlib.metadata
import os
import shutil
import sys
import time
from pathlib import Path

import wt_compiler.discovery as d
from rattler import PrefixRecord
from wt_compiler.cli import main

TESTED_WT_COMPILER = {"0.10.2"}
MODE = os.environ.get("WTC_DEV_MODE", "skip-solve")
ROOT = Path(os.environ.get("WTC_DEV_CACHE", Path.home() / ".cache" / "wt-dev-discovery"))
_real_install = d.install
_real_solve = d.solve


def log(msg: str) -> None:
    print(f"[wtc-dev:{MODE}] {msg}", file=sys.stderr, flush=True)


async def _install_shared(*, records, target_prefix, cache_dir=None, **kw):  # noqa: ARG001
    return await _real_install(records=records, target_prefix=target_prefix, **kw)


def _sha(parts: list[str]) -> str:
    return hashlib.sha256("\n".join(sorted(parts)).encode()).hexdigest()[:20]


def _records_key(records) -> str:
    parts = []
    for r in records:
        sha = r.sha256
        parts.append(sha.hex() if isinstance(sha, bytes | bytearray) else f"{r.url}")
    return _sha(parts)


def _read_prefix_records(env: Path) -> list:
    return [PrefixRecord.from_path(p) for p in sorted((env / "conda-meta").glob("*.json"))]


async def _create_persistent(env_path, requirements, channels, platform, on_progress=None):
    spec_key = _sha([str(r) for r in requirements] + [c.base_url for c in channels] + [str(platform)])
    by_spec = ROOT / "by-spec" / spec_key
    t = time.perf_counter()

    if MODE == "skip-solve" and (by_spec / ".wtc-complete").exists():
        target = by_spec.resolve()
        records = _read_prefix_records(target)
        log(f"reused env for unchanged specs ({len(records)} pkgs, no solve) {time.perf_counter() - t:.1f}s")
    else:
        records = await _real_solve(
            sources=channels,
            specs=requirements,
            platforms=[platform, d.Platform("noarch")],
            virtual_packages=d.VirtualPackage.detect(),
        )
        log(f"solved {len(records)} pkgs {time.perf_counter() - t:.1f}s")
        target = ROOT / "envs" / _records_key(records)
        if not (target / ".wtc-complete").exists():
            # rattler bakes the prefix path into files, so install at the final
            # path; the marker is written only after a successful install
            t = time.perf_counter()
            shutil.rmtree(target, ignore_errors=True)
            target.mkdir(parents=True)
            await _real_install(records=records, target_prefix=str(target))
            (target / ".wtc-complete").touch()
            log(f"built persistent env {target.name} {time.perf_counter() - t:.1f}s")
        else:
            log(f"reused persistent env {target.name}")
        by_spec.parent.mkdir(parents=True, exist_ok=True)
        if by_spec.is_symlink() or by_spec.exists():
            by_spec.unlink()
        by_spec.symlink_to(target)

    env_path.symlink_to(target)
    return records


WT_VERSION = importlib.metadata.version("wt-compiler")
if MODE != "baseline" and WT_VERSION not in TESTED_WT_COMPILER:
    log(f"wt-compiler {WT_VERSION} not tested with this wrapper; using stock compile")
    MODE = "baseline"

if MODE == "shared-cache":
    d.install = _install_shared
elif MODE in ("persistent-env", "skip-solve"):
    d._create_environment = _create_persistent
elif MODE != "baseline":
    sys.exit(f"unknown WTC_DEV_MODE={MODE}")

if __name__ == "__main__":
    sys.argv[0] = "wt-compiler"
    t0 = time.perf_counter()
    try:
        main()
    finally:
        log(f"total {time.perf_counter() - t0:.1f}s")
