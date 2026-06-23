"""
service_entry.py
================
PyInstaller entry point for the bundled background service binary
(``ambilight-service``). It delegates to ``ambilight.service.main``.

``multiprocessing.freeze_support()`` is mandatory and MUST run before any heavy
imports: the pipeline runs in a ``multiprocessing.Process`` and, in a frozen
(spawn-based) build, the child re-executes this binary with
``--multiprocessing-fork`` arguments. ``freeze_support()`` intercepts those and
runs the worker target; if it runs *after* importing the whole app, the re-exec
is fragile (notably when the install path contains spaces, e.g.
``C:\\Program Files\\Ambilight Desktop\\``) and the worker spawn fails — which
takes the parent service down in a silent crash-loop. Keeping freeze_support as
the first statement and importing the app only afterwards is the
PyInstaller-recommended structure. ``--collect-submodules ambilight`` in
build.py keeps the package bundled despite the import living inside the guard.
"""

import multiprocessing


def _run_selfcheck() -> int:
    """Probe the capture backends and report which are available, then exit.

    Two uses, same command (``ambilight-service --selfcheck``):
      * **Post-build smoke test** — build.py runs the freshly frozen binary with
        this flag and fails the build if a backend was silently dropped from the
        bundle, so an installer can never ship MSS-only by accident.
      * **Runtime diagnostic** — answers "why did capture fall back to MSS?" on a
        user's machine without digging through logs.

    Exit code is 0 only when every backend *expected on this platform* is
    importable; non-zero otherwise. The ``open()`` probe below is informational
    (it needs a real display, so it may legitimately fail on a headless CI box)
    and never changes the exit code.
    """
    import importlib
    import sys

    is_win = sys.platform == "win32"
    # (import name, friendly label, required-on-this-platform)
    modules = [
        ("mss", "MSS", True),
        ("windows_capture", "WGC", is_win),
        ("dxcam", "DXGI", is_win),
        ("comtypes", "comtypes (dxcam dep)", is_win),
    ]

    print("[selfcheck] Capture backend import availability:")
    missing_required: list[str] = []
    for mod, label, required in modules:
        try:
            importlib.import_module(mod)
            status = "OK"
        except Exception as exc:  # ImportError or a native-load error
            status = f"MISSING ({type(exc).__name__}: {exc})"
            if required:
                missing_required.append(label)
        tag = "required" if required else "optional"
        print(f"  - {label:<22} ({mod}) [{tag}]: {status}")

    # Best-effort open() probe — surfaces runtime D3D/WinRT failures that a bare
    # import can't (e.g. dxcam imports but can't duplicate). Informational only.
    try:
        from ambilight.capture import WGCBackend, DXGIBackend, MSSBackend

        print("[selfcheck] open() probe (informational - needs a display):")
        for cls in (WGCBackend, DXGIBackend, MSSBackend):
            backend = cls()
            try:
                result = "opened" if backend.open(0) is True else "unavailable"
            except Exception as exc:
                result = f"error: {type(exc).__name__}: {exc}"
            finally:
                try:
                    backend.close()
                except Exception:
                    pass
            print(f"  - {backend.name.upper():<6}: {result}")
    except Exception as exc:
        print(f"[selfcheck] open() probe skipped: {exc}")

    if missing_required:
        print(
            "[selfcheck] FAIL - required capture backend(s) not bundled: "
            + ", ".join(missing_required)
        )
        return 1
    print("[selfcheck] PASS - all required capture backends are present.")
    return 0


def _ensure_std_streams() -> None:
    """Guarantee ``sys.stdout``/``sys.stderr`` are writable file objects.

    A windowed (no-console) PyInstaller build — and ``pythonw.exe`` in dev — sets
    both streams to ``None`` because there's no console attached. uvicorn and
    ``logging.basicConfig(stream=sys.stdout)`` then crash on ``None.write``. The
    Electron supervisor launches us with real file handles wired to fd 1/2
    (``service.out.log``), so rebind Python's streams to those descriptors; that
    keeps boot/crash output captured. When no valid descriptor exists (e.g. the
    Startup launcher with no redirection) fall back to the null device — the
    rotating file log under ``~/.ambilight/logs`` is unaffected either way.
    """
    import os
    import sys

    for name, fd in (("stdout", 1), ("stderr", 2)):
        if getattr(sys, name, None) is not None:
            continue
        try:
            stream = os.fdopen(fd, "w", buffering=1)
        except OSError:
            stream = open(os.devnull, "w")
        setattr(sys, name, stream)


if __name__ == "__main__":
    multiprocessing.freeze_support()

    import sys

    _ensure_std_streams()

    # Capture self-check / bundling smoke test (see _run_selfcheck). Handled
    # after freeze_support so a multiprocessing fork re-exec is never hijacked,
    # and before the heavy service import so it stays a fast, isolated probe.
    if "--selfcheck" in sys.argv:
        sys.exit(_run_selfcheck())

    # Frozen builds re-exec this binary for spawn; pin the method explicitly
    # (default on Windows/macOS, but be deterministic for the frozen child).
    if getattr(sys, "frozen", False):
        try:
            multiprocessing.set_start_method("spawn", force=True)
        except RuntimeError:
            pass  # already set in this interpreter

    from ambilight.service.__main__ import main
    main()
