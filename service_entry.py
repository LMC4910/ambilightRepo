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

if __name__ == "__main__":
    multiprocessing.freeze_support()

    import sys

    # Frozen builds re-exec this binary for spawn; pin the method explicitly
    # (default on Windows/macOS, but be deterministic for the frozen child).
    if getattr(sys, "frozen", False):
        try:
            multiprocessing.set_start_method("spawn", force=True)
        except RuntimeError:
            pass  # already set in this interpreter

    from ambilight.service.__main__ import main
    main()
