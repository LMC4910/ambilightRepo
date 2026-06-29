"""
build.py
========
Cross-platform build script for Ambilight Desktop. Produces, for the host OS:

  1. A PyInstaller ``--onedir`` bundle of the Python service, named
     ``ambilight-service`` (the name the Electron shell looks for under
     ``resources/service/``).
  2. The Electron installer for the host OS via electron-builder
     (NSIS on Windows, DMG on macOS, AppImage + deb on Linux).

Usage:
    python build.py              # service + UI for the current OS
    python build.py --service    # service only
    python build.py --ui         # UI only

Requirements: Python 3.11+ with PyInstaller; Node 20+ with pnpm.
"""

from __future__ import annotations

import argparse
import os
import platform
import shutil
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent
DIST = ROOT / "dist"
SERVICE_DIST = DIST / "service"
UI_DIR = ROOT / "ui"
NATIVE_DIR = ROOT / "native"
NATIVE_BUILD = NATIVE_DIR / "build"

SERVICE_NAME = "ambilight-service"
CAPTURE_HOST_EXE = "capture_host.exe"
GRAPHICS_HOOK_DLL = "graphics_hook.dll"
SYSTEM = platform.system()  # Windows | Darwin | Linux
# cloudflared powers the optional GitHub-webhook tunnel (loopback → public URL).
# Bundled when found so webhooks work out of the box; missing it just leaves the
# integration on polling (or a PATH-installed cloudflared) — see tunnel.py.
CLOUDFLARED_NAME = "cloudflared.exe" if SYSTEM == "Windows" else "cloudflared"
# Pin the cloudflared release we auto-download so opt-in builds are reproducible
# and integrity-checked, instead of bundling whatever "latest" happens to serve.
# To bump: pick a tag from github.com/cloudflare/cloudflared/releases, update this
# version, then refresh CLOUDFLARED_SHA256 with the new digests — download each
# asset and hash it, e.g.:
#   curl -fSL <asset-url> | sha256sum
# (Cloudflare doesn't publish a checksums file, so we hash the release assets.)
# cloudflared ships no windows-arm64 build, so that target isn't pinned here.
CLOUDFLARED_VERSION = "2026.6.1"
CLOUDFLARED_SHA256: dict[str, str] = {
    "cloudflared-windows-amd64.exe": "5253e66f1f493c4e13539749f1aa86fd0c61e3072900fec29a44ba046a6d97e2",
    "cloudflared-linux-amd64": "5861a10a438fe8ddcfebb3b830f83966cbf193edafce0fe2eeb198fbae1f7a22",
    "cloudflared-linux-arm64": "59816ce9b16db71f5bc2a86d59b3632a96c8c3ee934bde2bc8641ee83a6070eb",
}


def _which(name: str) -> str:
    """Resolve *name* to a runnable path, honouring Windows shims.

    Python's subprocess on Windows only auto-resolves bare names to ``.exe``, so
    a Node tool installed as ``pnpm.cmd``/``.bat`` (with no ``.exe``) is invisible
    to ``subprocess.run([name])`` and raises FileNotFoundError. ``shutil.which``
    consults PATHEXT and finds the shim; passing its full path runs it correctly.
    Falls back to *name* unchanged so POSIX behaviour is identical.
    """
    return shutil.which(name) or name


def _run(cmd: list[str], cwd: Path | None = None) -> None:
    print(f"\n{'=' * 60}\n  Running: {' '.join(cmd)}\n  CWD:     {cwd or ROOT}\n{'=' * 60}\n")
    result = subprocess.run([_which(cmd[0]), *cmd[1:]], cwd=str(cwd or ROOT))
    if result.returncode != 0:
        print(f"\n[FATAL] Command failed with exit code {result.returncode}")
        sys.exit(result.returncode)


def _check_tool(name: str, version_flag: str = "--version") -> None:
    try:
        subprocess.run([_which(name), version_flag], capture_output=True, check=True)
    except (FileNotFoundError, OSError):
        print(f"[FATAL] Required tool not found on PATH: {name}")
        sys.exit(1)


def _check_version_sync() -> str:
    """Sync and validate version across all components.

    The VERSION file at the repo root is the single source of truth. This function:
    1. Reads VERSION (canonical)
    2. Syncs to ui/package.json (already done by npm, but double-check)
    3. Syncs to ambilight/_version.py (for PyInstaller bundles)
    
    Returns the agreed version string.
    """
    import json
    import re

    # Read VERSION file (single source of truth)
    version_file = ROOT / "VERSION"
    canonical_version = version_file.read_text(encoding="utf-8").strip()
    if not canonical_version:
        print("[FATAL] VERSION file is empty")
        sys.exit(1)

    # Validate semver format
    if not re.match(r"^\d+\.\d+\.\d+$", canonical_version):
        print(f"[FATAL] Invalid version format in VERSION file: {canonical_version}")
        print("        Expected format: X.Y.Z (semver)")
        sys.exit(1)

    # Check package.json version
    pkg_path = UI_DIR / "package.json"
    pkg_version = json.loads(pkg_path.read_text(encoding="utf-8"))["version"]

    if pkg_version != canonical_version:
        print(
            f"[WARN] Version mismatch: VERSION={canonical_version!r} but "
            f"ui/package.json={pkg_version!r}. Run 'node scripts/sync-version.mjs' "
            f"to sync, then rebuild."
        )
        sys.exit(1)

    # Sync to ambilight/_version.py (for PyInstaller bundles)
    version_py = ROOT / "ambilight" / "_version.py"
    version_py_content = (
        "# This file is auto-generated by build.py from the VERSION file.\n"
        "# Do not edit manually. Update VERSION file at the repo root instead.\n"
        f'__version__ = "{canonical_version}"\n'
    )
    old_content = version_py.read_text(encoding="utf-8") if version_py.exists() else ""
    if old_content != version_py_content:
        version_py.write_text(version_py_content, encoding="utf-8")
        print(f"[OK] Synced version to ambilight/_version.py: {canonical_version}")
    
    print(f"[OK] Version in sync: {canonical_version}")
    return canonical_version


def _find_native_artifact(filename: str) -> Path | None:
    """Locate a built native artifact under native/build/bin across the generator
    layouts CMake may use (Visual Studio multi-config adds a ``Release/`` subdir;
    Ninja does not). Returns *None* if it has not been built."""
    for rel in (
        Path("bin") / "Release" / filename,  # Visual Studio gen
        Path("bin") / filename,              # Ninja / single-config
    ):
        p = NATIVE_BUILD / rel
        if p.is_file():
            return p
    return None


def _cloudflared_asset_name() -> str | None:
    """Release asset filename for the host platform, or None if unsupported.

    macOS ships a ``.tgz`` (not a bare binary), so auto-fetch there is skipped —
    place the binary in ``bin/`` or set ``AMBILIGHT_CLOUDFLARED`` instead.
    """
    machine = platform.machine().lower()
    arch = "amd64" if machine in ("amd64", "x86_64") else ("arm64" if machine in ("arm64", "aarch64") else None)
    if arch is None:
        return None
    if SYSTEM == "Windows":
        return f"cloudflared-windows-{arch}.exe"
    if SYSTEM == "Linux":
        return f"cloudflared-linux-{arch}"
    return None


def _cloudflared_download_url(asset: str) -> str:
    """Pinned official release URL for *asset* (a specific version, not latest)."""
    return (f"https://github.com/cloudflare/cloudflared/releases/download/"
            f"{CLOUDFLARED_VERSION}/{asset}")


def _expected_cloudflared_sha256(asset: str) -> str | None:
    """Expected digest for *asset*: env override first, then the pinned table."""
    env = os.environ.get("AMBILIGHT_CLOUDFLARED_SHA256", "").strip().lower()
    if env:
        return env
    return CLOUDFLARED_SHA256.get(asset)


def _fetch_cloudflared() -> Path | None:
    """Opt-in download of cloudflared into ``bin/`` (gated by env).

    Fails closed: the binary is pinned to ``CLOUDFLARED_VERSION`` and verified
    against a known SHA-256 before it is bundled. With no expected digest pinned
    (table empty and no ``AMBILIGHT_CLOUDFLARED_SHA256`` override), we refuse to
    bundle an unverified, network-fetched executable.
    """
    import hashlib
    import urllib.request

    asset = _cloudflared_asset_name()
    if not asset:
        print(f"[WARN] No cloudflared auto-download for this platform; place it at "
              f"bin/{CLOUDFLARED_NAME} or set AMBILIGHT_CLOUDFLARED.")
        return None
    expected = _expected_cloudflared_sha256(asset)
    if not expected:
        print(f"[ERROR] No pinned SHA-256 for {asset} @ {CLOUDFLARED_VERSION}; "
              f"refusing to bundle an unverified cloudflared. Add its digest to "
              f"CLOUDFLARED_SHA256 or set AMBILIGHT_CLOUDFLARED_SHA256.")
        return None

    url = _cloudflared_download_url(asset)
    dest_dir = ROOT / "bin"
    dest_dir.mkdir(parents=True, exist_ok=True)
    dest = dest_dir / CLOUDFLARED_NAME
    tmp = dest_dir / f"{CLOUDFLARED_NAME}.download"
    print(f"[cloudflared] Downloading {url} …")
    try:
        urllib.request.urlretrieve(url, tmp)
    except Exception as exc:  # network/CI-specific
        print(f"[WARN] cloudflared download failed: {exc}")
        tmp.unlink(missing_ok=True)
        return None

    digest = hashlib.sha256(tmp.read_bytes()).hexdigest()
    if digest != expected:
        print(f"[ERROR] cloudflared checksum mismatch for {asset}: expected "
              f"{expected}, got {digest}. Discarding download.")
        tmp.unlink(missing_ok=True)
        return None

    tmp.replace(dest)
    if SYSTEM != "Windows":
        dest.chmod(0o755)
    print(f"[OK] cloudflared {CLOUDFLARED_VERSION} verified ({digest[:12]}…).")
    return dest


def _find_cloudflared() -> Path | None:
    """Locate a cloudflared binary to bundle: env override, repo ``bin/``, PATH,
    then an opt-in download (``AMBILIGHT_FETCH_CLOUDFLARED=1``). None if absent."""
    env = os.environ.get("AMBILIGHT_CLOUDFLARED", "").strip()
    if env and Path(env).is_file():
        return Path(env)
    local = ROOT / "bin" / CLOUDFLARED_NAME
    if local.is_file():
        return local
    found = shutil.which("cloudflared")
    if found:
        return Path(found)
    if os.environ.get("AMBILIGHT_FETCH_CLOUDFLARED", "").strip().lower() in ("1", "true", "yes"):
        return _fetch_cloudflared()
    return None


def _find_capture_host() -> Path | None:
    return _find_native_artifact(CAPTURE_HOST_EXE)


def _find_graphics_hook() -> Path | None:
    return _find_native_artifact(GRAPHICS_HOOK_DLL)


def _vs_generator() -> str | None:
    """Return the CMake Visual Studio generator string for the newest installed
    Visual Studio / Build Tools, or *None* if none is found.

    We pin the VS generator explicitly because CMake's *default* generator
    depends on what else is on PATH (e.g. Ninja), which without a ``vcvars`` shell
    picks up MinGW GCC instead of MSVC. The VS generator locates the MSVC toolset
    itself — no developer command prompt required. ``vswhere -products *`` is
    required to surface Build Tools installs (the default query hides them).
    """
    vswhere = Path(os.environ.get("ProgramFiles(x86)", r"C:\Program Files (x86)")) \
        / "Microsoft Visual Studio" / "Installer" / "vswhere.exe"
    if not vswhere.is_file():
        return None
    try:
        out = subprocess.run(
            [str(vswhere), "-latest", "-products", "*",
             "-property", "installationVersion"],
            capture_output=True, text=True, check=True,
        ).stdout.strip()
    except (OSError, subprocess.CalledProcessError):
        return None
    major = out.split(".", 1)[0] if out else ""
    return {"17": "Visual Studio 17 2022",
            "16": "Visual Studio 16 2019",
            "15": "Visual Studio 15 2017"}.get(major)


def build_native() -> None:
    """Build ``capture_host.exe`` (the DX11 hook helper) with CMake.

    Windows-only: the helper exists solely for exclusive-fullscreen DX11 game
    capture and links Win32. On other platforms this is a no-op. Prefers the
    MSVC (Visual Studio) toolchain; if no Visual Studio install is detected it
    falls back to CMake's default generator (the CMakeLists handles MinGW too).
    """
    if SYSTEM != "Windows":
        print("\n[native] Skipping capture_host build (Windows-only helper).")
        return
    _check_tool("cmake")
    print("\n[native] Building capture_host.exe (DX11 game-capture helper)…")
    # Clean configure: avoids a generator-mismatch error if a previous run used a
    # different generator, and guarantees a deterministic build.
    if NATIVE_BUILD.exists():
        shutil.rmtree(NATIVE_BUILD)

    configure = ["cmake", "-S", str(NATIVE_DIR), "-B", str(NATIVE_BUILD)]
    gen = _vs_generator()
    if gen:
        configure += ["-G", gen, "-A", "x64"]
        print(f"[native] Using generator: {gen} (x64)")
    else:
        configure += ["-DCMAKE_BUILD_TYPE=Release"]
        print("[native] No Visual Studio found; using CMake default generator.")
    _run(configure)
    _run(["cmake", "--build", str(NATIVE_BUILD), "--config", "Release"])
    exe = _find_capture_host()
    if exe is None:
        print("[FATAL] Native build completed but capture_host.exe was not found.")
        sys.exit(1)
    print(f"[OK] Native helper built: {exe}")


def build_service(gpu: bool = False) -> None:
    print(f"\n[1/2] Building Python service with PyInstaller ({'GPU' if gpu else 'lean CPU'})…")
    # Invoke PyInstaller via the current interpreter (`python -m PyInstaller`)
    # rather than the `pyinstaller` console script: pip user installs put that
    # script in a Scripts dir that's often not on PATH, so a bare `pyinstaller`
    # FATALs even though the package is installed. Verify the module is present.
    import importlib.util as _ilu
    if _ilu.find_spec("PyInstaller") is None:
        print("[FATAL] PyInstaller is not installed. Run: pip install pyinstaller")
        sys.exit(1)

    if SERVICE_DIST.exists():
        shutil.rmtree(SERVICE_DIST)
    SERVICE_DIST.mkdir(parents=True, exist_ok=True)

    hidden_imports = [
        "--hidden-import=mss",
        "--hidden-import=numpy",
        "--hidden-import=PIL",
        "--hidden-import=yaml",
        "--hidden-import=uvicorn",
        "--hidden-import=fastapi",
        "--hidden-import=pydantic",
    ]
    # Probe availability WITHOUT importing — importing winsdk/comtypes/
    # windows_capture here would fight over the COM apartment and crash the build.
    import importlib.util
    def _available(name: str) -> bool:
        try:
            return importlib.util.find_spec(name) is not None
        except Exception:
            return False

    # The capture backends are REQUIRED on Windows. Shipping without them
    # silently degrades every install to MSS — fullscreen games / overlay video
    # render black, and a transient MSS failure (screen lock, display sleep) has
    # nothing to fail over to, which is exactly the "All backends exhausted" loop
    # users hit. Fail the build loudly rather than producing an MSS-only installer
    # (these are pinned in requirements.txt under the Windows markers).
    # cv2 (opencv-python) is included: windows_capture imports it at module load
    # and dxcam uses it for colour conversion — without it BOTH WGC and DXGI fail
    # and every install is stranded on MSS. It is a hard dependency of
    # windows-capture, so installing the requirements already pulls it in.
    if SYSTEM == "Windows":
        required_caps = ["mss", "windows_capture", "dxcam", "comtypes", "cv2"]
        missing = [p for p in required_caps if not _available(p)]
        if missing:
            print(
                f"[FATAL] Required capture dependency(ies) missing from the build "
                f"environment: {', '.join(missing)}.\n"
                f"        Install them so the installer ships every backend:\n"
                f"          pip install windows-capture dxcam comtypes mss opencv-python"
            )
            sys.exit(1)

    # Feature dependencies are hard requirements in requirements.txt now, so the
    # installer must ship them — the integrations they power are off by default
    # but have to work the moment a user enables them, with no separate pip step.
    required_features = ["zeroconf", "paho", "keyring", "httpx"]
    missing_feat = [p for p in required_features if not _available(p)]
    if missing_feat:
        print(
            f"[FATAL] Required feature dependency(ies) missing from the build "
            f"environment: {', '.join(missing_feat)}.\n"
            f"        Install the requirements so the installer ships them:\n"
            f"          pip install -r requirements.txt"
        )
        sys.exit(1)

    # Always-bundled optional deps: capture backends + audio + WGC, the
    # smart-home integration stack (paho-mqtt + keyring), and the GitHub
    # integration's HTTP client (httpx) — all bundled when present.
    optional = ["dxcam", "winsdk", "comtypes", "soundcard", "windows_capture", "paho", "keyring", "httpx"]
    collect_all: list[str] = []
    # winsdk is collected in full: its WinRT namespaces (e.g.
    # winsdk.windows.ui.notifications.management for Notification Flash) are
    # imported dynamically, so a bare --hidden-import misses them. dxcam + comtypes
    # are collected in full too: dxcam imports dxcam.core.* submodules dynamically
    # and drives the display via comtypes-generated COM wrappers, which a bare
    # --hidden-import leaves out — so the frozen DXGI backend fails to import.
    # httpx pulls in httpcore/h11/anyio/sniffio submodules dynamically, so collect
    # it in full (a bare --hidden-import misses them and the GitHub client breaks).
    for pkg in ("windows_capture", "dxcam", "comtypes", "soundcard", "paho", "keyring", "winsdk", "httpx"):
        if _available(pkg):
            collect_all += ["--collect-all", pkg]

    # Lean build: drop the heavy GPU stack (CuPy ~118 MB + CUDA ~86 MB) and obvious
    # dead weight. OpenCV (cv2) is NOT dropped on Windows — the WGC backend's
    # windows_capture imports cv2 at module load and dxcam uses it for colour
    # conversion, so excluding it silently broke WGC+DXGI and stranded installs on
    # MSS (cv2 also gives _cpu_resize a faster path than Pillow). Off Windows there
    # is no native capture backend (MSS is pure-Python), so cv2 stays excluded to
    # keep the bundle lean. GPU build (--gpu) re-includes CuPy for CUDA users.
    excludes = ["tkinter", "_tkinter", "lib2to3", "pydoc_data", "matplotlib", "PyQt5", "PySide2"]
    bundle_cv2 = (SYSTEM == "Windows" or gpu) and _available("cv2")
    if bundle_cv2:
        collect_all += ["--collect-all", "cv2"]
        optional.append("cv2")
    else:
        excludes.append("cv2")
    if gpu:
        optional += ["cupy", "torch"]
        if _available("cupy"):
            collect_all += ["--collect-all", "cupy"]
    else:
        excludes += ["cupy", "cupyx", "cupy_backends", "torch", "nvidia"]

    for opt in optional:
        if _available(opt):
            hidden_imports.append(f"--hidden-import={opt}")

    exclude_args: list[str] = []
    for mod in excludes:
        exclude_args += ["--exclude-module", mod]

    sep = os.pathsep  # ; on Windows, : elsewhere

    # Bundle the native capture helper + injected hook DLL together under `native/`
    # in the onedir, so the opt-in "hook" backend launches capture_host.exe via
    # resource_path('native/capture_host.exe') and the host finds graphics_hook.dll
    # right next to itself. Opt-in and non-essential: a missing helper only disables
    # the hook backend (it falls back to WGC/DXGI/MSS), so warn rather than fail.
    add_binary_args: list[str] = []
    if SYSTEM == "Windows":
        host = _find_capture_host()
        hook_dll = _find_graphics_hook()
        if host is not None:
            add_binary_args += ["--add-binary", f"{host}{sep}native"]
            print(f"[OK] Bundling native capture helper: {host}")
            if hook_dll is not None:
                add_binary_args += ["--add-binary", f"{hook_dll}{sep}native"]
                print(f"[OK] Bundling graphics hook DLL: {hook_dll}")
            else:
                print("[WARN] graphics_hook.dll not built; game capture (the 'hook' "
                      "backend's real source) will be unavailable.")
        else:
            print("[WARN] capture_host.exe not built; the 'hook' capture backend "
                  "will be unavailable in this bundle (run build_native first).")

    # Bundle cloudflared (under bin/) so the optional GitHub-webhook tunnel works
    # out of the box. Non-essential: a missing binary just leaves webhooks on
    # polling (or a PATH-installed cloudflared at runtime), so warn rather than fail.
    cloudflared_args: list[str] = []
    cf = _find_cloudflared()
    if cf is not None:
        cloudflared_args += ["--add-binary", f"{cf}{sep}bin"]
        print(f"[OK] Bundling cloudflared (GitHub webhook tunnel): {cf}")
    else:
        print("[INFO] cloudflared not found; GitHub webhooks will rely on a "
              "PATH-installed cloudflared or fall back to polling. Set "
              "AMBILIGHT_CLOUDFLARED=<path> or AMBILIGHT_FETCH_CLOUDFLARED=1 to bundle it.")

    # Bake the GitHub OAuth App client id into the bundle when provided via the
    # build environment (CI injects it from a repo secret/variable at release
    # time). A device-flow client id is NOT a secret — it ships in the app — so
    # baking it is fine; it's read at runtime via resource_path('github_client_id.txt').
    client_id_args: list[str] = []
    gh_client_id = os.environ.get("AMBILIGHT_GITHUB_CLIENT_ID", "").strip()
    if gh_client_id:
        cid_dir = DIST / "build_meta"
        cid_dir.mkdir(parents=True, exist_ok=True)
        cid_file = cid_dir / "github_client_id.txt"
        cid_file.write_text(gh_client_id, encoding="utf-8")
        client_id_args += ["--add-data", f"{cid_file}{sep}."]
        print("[OK] Baking GitHub OAuth client id into the service bundle.")
    else:
        print("[INFO] AMBILIGHT_GITHUB_CLIENT_ID not set; the GitHub integration "
              "will need a client id at runtime (config or env).")

    _run([
        sys.executable, "-m", "PyInstaller",
        "--noconfirm",
        "--onedir",
        # Build a windowed (no-console) binary. The service is a background
        # process supervised by the Electron shell / launched via the Startup
        # launcher — a console subsystem exe (PyInstaller's default) pops up a
        # terminal window on every launch that neither `windowsHide` nor
        # `start /min` can suppress. stdout/stderr still reach the Electron
        # capture log because the supervisor passes real file handles for fd
        # 1/2; service_entry.py rebinds sys.stdout/err to them when frozen.
        "--windowed",
        "--name", SERVICE_NAME,
        "--distpath", str(SERVICE_DIST),
        "--specpath", str(DIST / "build_spec"),
        "--workpath", str(DIST / "build_work"),
        "--add-data", f"{ROOT / 'configuration.yaml'}{sep}.",
        "--add-data", f"{ROOT / 'profiles'}{sep}profiles",
        *add_binary_args,
        *cloudflared_args,
        *client_id_args,
        # Collect the whole package so conditionally/dynamically imported
        # submodules (capture backends, api_server referenced via uvicorn) ship.
        "--collect-submodules", "ambilight",
        *exclude_args,
        *collect_all,
        *hidden_imports,
        str(ROOT / "service_entry.py"),
    ])
    print(f"\n[OK] Service built: {SERVICE_DIST / SERVICE_NAME}")

    # Post-build bundling check: confirm every required capture backend was
    # actually collected into the onedir, before an installer is ever produced.
    # This is a *filesystem* check, not an import/open — WGC (WinRT) and DXGI need
    # an interactive desktop + GPU to load, which a headless CI runner doesn't
    # have, so running the frozen exe there gives false failures. The bundling
    # guarantee we care about is simply that the modules shipped; whether they can
    # capture is a runtime concern verified by `ambilight-service --selfcheck` on a
    # real machine.
    missing = _missing_bundled_backends(SERVICE_DIST / SERVICE_NAME)
    if missing:
        print(
            f"[FATAL] Capture backend(s) missing from the bundle: {', '.join(missing)}.\n"
            f"        The installer would ship MSS-only. Check the --collect-all / "
            f"--hidden-import flags above for these packages."
        )
        sys.exit(1)
    print("[OK] All required capture backends are bundled.")


def _missing_bundled_backends(bundle_root: Path) -> list[str]:
    """Return the binary capture-backend packages that did NOT make it into the
    onedir.

    Filesystem-only (no import) so it works on a headless build box. We check the
    Windows fast-capture backends specifically because they're the ones that
    silently went missing before (optional, native, ``--collect-all``'d) and that
    leave users on MSS. They ship as extracted ``_internal/<pkg>/`` directories
    (native ``.pyd`` / data), so a missing directory means a dropped backend.

    Pure-Python ``mss`` is deliberately not checked here: as a plain
    ``--hidden-import`` it's compiled into the PYZ archive rather than extracted to
    disk, so it's invisible to a filesystem scan. Its presence is already
    guaranteed by the hardcoded ``--hidden-import=mss`` plus the build-env check
    above, and the test suite imports it."""
    if SYSTEM != "Windows":
        return []  # no native fast-capture backends off Windows; MSS is in the PYZ
    # cv2 is included because windows_capture/dxcam need it — a dropped cv2 is what
    # silently broke WGC+DXGI before, so guard it like a backend.
    required = ["windows_capture", "dxcam", "comtypes", "cv2"]

    missing: list[str] = []
    for imp in required:
        hits = list(bundle_root.rglob(imp)) + list(bundle_root.rglob(f"{imp}.*"))
        bundled = any(
            h.is_dir() or h.suffix in {".pyd", ".so", ".dll", ".py", ".pyc"}
            for h in hits
        )
        if not bundled:
            missing.append(imp)
    return missing


def build_ui() -> None:
    print("\n[2/2] Building Electron UI with electron-builder…")
    _check_tool("pnpm")

    _run(["pnpm", "install", "--frozen-lockfile"], cwd=UI_DIR)
    _run(["pnpm", "run", "build"], cwd=UI_DIR)

    target_flag = {"Windows": "--win", "Darwin": "--mac", "Linux": "--linux"}.get(SYSTEM, "--linux")
    _run(["pnpm", "exec", "electron-builder", target_flag], cwd=UI_DIR)
    print(f"\n[OK] UI built. See {UI_DIR / 'release'}")


def main() -> None:
    parser = argparse.ArgumentParser(description="Build Ambilight Desktop (cross-platform)")
    parser.add_argument("--service", action="store_true", help="Build service only")
    parser.add_argument("--ui", action="store_true", help="Build UI only")
    parser.add_argument("--native", action="store_true",
                        help="Build the native capture_host helper only (Windows)")
    parser.add_argument("--gpu", action="store_true",
                        help="Bundle CuPy/CUDA + OpenCV (large GPU build). Default is lean CPU-only.")
    args = parser.parse_args()

    # Single-source-of-truth version gate — keeps the service binary and the
    # installer/updater feed reporting the same version.
    _check_version_sync()

    build_all = not args.service and not args.ui and not args.native
    # The service bundle embeds the native helper, so build it first whenever the
    # service (or everything) is being built, as well as on an explicit --native.
    if build_all or args.service or args.native:
        build_native()
    if build_all or args.service:
        build_service(gpu=args.gpu)
    if build_all or args.ui:
        build_ui()

    if build_all:
        print("\n" + "=" * 60)
        print("  BUILD COMPLETE")
        print(f"  Service: {SERVICE_DIST / SERVICE_NAME}")
        print(f"  UI:      {UI_DIR / 'release'}")
        print("=" * 60)


if __name__ == "__main__":
    main()
