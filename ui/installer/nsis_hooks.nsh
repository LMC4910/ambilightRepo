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

!include "FileFunc.nsh"   ; ${GetTime}

; -----------------------------------------------------------------------------
;  customInstall  — runs after electron-builder copies all files
; -----------------------------------------------------------------------------
!macro customInstall
  ; Force the NSIS detail/log pane visible so every DetailPrint is shown.
  SetDetailsView show

  ; Resolve the per-user data directory early.  Using $PROFILE (not $APPDATA)
  ; matches the path the Python service writes to (~/.ambilight/).
  StrCpy $R0 "$PROFILE\.ambilight"

  DetailPrint "Creating per-user data directories..."
  CreateDirectory "$R0"
  CreateDirectory "$R0\logs"

  ; Stamp date/time via FileFunc (local time).
  ; $R1=dd $R2=mm $R3=yyyy $R4=DOW $R5=HH $R6=MM $R7=SS
  ${GetTime} "" "L" $R1 $R2 $R3 $R4 $R5 $R6 $R7

  ; Write install.log — file mtime is the real timestamp, but the header
  ; makes it readable at a glance and easy to correlate with service logs.
  FileOpen $R8 "$R0\logs\install.log" w
  FileWrite $R8 "===== Ambilight Desktop Installation Log =====$\r$\n"
  FileWrite $R8 "Date/Time    : $R3-$R2-$R1  $R5:$R6:$R7 (local)$\r$\n"
  FileWrite $R8 "Version      : ${VERSION}$\r$\n"
  FileWrite $R8 "Install Dir  : $INSTDIR$\r$\n"
  FileWrite $R8 "Data Dir     : $R0$\r$\n"
  FileWrite $R8 "Log Dir      : $R0\logs$\r$\n"
  FileWrite $R8 "$\r$\n"
  FileWrite $R8 "--- Steps ---$\r$\n"
  FileWrite $R8 "[OK] Data directories created$\r$\n"
  FileWrite $R8 "[OK] Install files copied by electron-builder$\r$\n"
  FileClose $R8

  DetailPrint "Install log written: $R0\logs\install.log"
!macroend

!macro customUnInstall
  SetDetailsView show
  ; --- Stop any running service spawned in the user session ---
  DetailPrint "Stopping Ambilight background service..."
  nsExec::ExecToLog 'taskkill /F /IM ambilight-service.exe /T'

  ; --- Remove the per-user start-on-login launcher (autostart.py target) ---
  DetailPrint "Removing start-on-login launcher..."
  Delete "$APPDATA\Microsoft\Windows\Start Menu\Programs\Startup\AmbilightService.cmd"

  ; NOTE: user configuration, profiles, logs and metrics in %USERPROFILE%\.ambilight
  ; are intentionally preserved across uninstall.
!macroend

!macro customRemoveFiles
  ; Clean upgrade (FR-I: a new version must replace the old one completely).
  ;
  ; electron-builder's default file removal only deletes paths recorded in the
  ; install manifest. The bundled PyInstaller service under resources\service
  ; writes files the manifest never tracked — __pycache__/*.pyc compiled on
  ; first run, and any new/renamed bundle files between versions — so a plain
  ; in-place update would leave STALE old-version files behind (a classic source
  ; of "works on a clean install but breaks after an update" bugs). On both an
  ; update (electron-builder runs the previous version's uninstaller first) and
  ; a manual uninstall, wipe the whole install directory so nothing from the old
  ; version survives before the new files are laid down.
  ;
  ; Safe because: (1) the uninstaller runs from a temp copy, not from $INSTDIR,
  ; so it can delete its own directory; (2) user data lives in
  ; %USERPROFILE%\.ambilight, OUTSIDE $INSTDIR, and is untouched.
  ${if} $INSTDIR != ""
  ${andif} $INSTDIR != "$PROGRAMFILES"
  ${andif} $INSTDIR != "$PROGRAMFILES64"
  ${andif} $INSTDIR != "$WINDIR"
    RMDir /r "$INSTDIR"
  ${endif}
!macroend
