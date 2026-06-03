; =============================================================================
;  NSIS Custom Hooks for Ambilight Desktop
; =============================================================================
;  Included by electron-builder's NSIS target.
;
;  Service-lifecycle model
;  -----------------------
;  The Python background service is NOT installed as a Windows Service. A
;  screen-capture process must run inside the interactive user session — a
;  Session-0 SYSTEM service cannot see the user's desktop/GPU output, and would
;  also double-bind port 7826 against the Electron supervisor. Instead:
;
;    * The Electron app spawns & supervises the bundled service
;      (resources\service\ambilight-service.exe) with a health watchdog.
;    * Start-on-login is registered per-user (no admin) by ambilight/autostart.py
;      via a launcher in the Startup folder (AmbilightService.cmd), toggled from
;      the app's Settings / onboarding wizard.
;
;  So install needs no service plumbing. Uninstall just has to leave nothing
;  running and remove the login launcher (NFR-I-02: complete uninstall).
; =============================================================================

!macro customUnInstall
  ; --- Stop any running service spawned in the user session ---
  DetailPrint "Stopping Ambilight background service..."
  nsExec::ExecToLog 'taskkill /F /IM ambilight-service.exe /T'

  ; --- Remove the per-user start-on-login launcher (autostart.py target) ---
  DetailPrint "Removing start-on-login launcher..."
  Delete "$APPDATA\Microsoft\Windows\Start Menu\Programs\Startup\AmbilightService.cmd"

  ; NOTE: user configuration, profiles, logs and metrics in %USERPROFILE%\.ambilight
  ; are intentionally preserved across uninstall.
!macroend
