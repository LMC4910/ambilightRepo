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

!include "FileFunc.nsh"
!include "MUI2.nsh"

; Global NSIS settings to show details by default (not hidden)
ShowInstDetails show
ShowUninstDetails show

; =============================================================================
; customInstall — runs after electron-builder copies all files
; =============================================================================

!macro customInstall
  ; Ensure detail pane is visible for all DetailPrint calls
  SetDetailsView show

  ; Resolve the per-user data directory early. Using $PROFILE (not $APPDATA)
  ; matches the path the Python service writes to (~/.ambilight/).
  StrCpy $R0 "$PROFILE\.ambilight"

  DetailPrint "Creating per-user data directories..."
  CreateDirectory "$R0"
  CreateDirectory "$R0\logs"

  ; Stamp date/time via FileFunc (local time).
  ; $R1=dd $R2=mm $R3=yyyy $R4=DOW $R5=HH $R6=MM $R7=SS
  ${GetTime} "" "L" $R1 $R2 $R3 $R4 $R5 $R6 $R7

  ; Write install.log with timestamp for diagnosing early startup issues
  FileOpen $R8 "$R0\logs\install.log" w
  FileWrite $R8 "===== Ambilight Desktop Installation Log =====$\r$\n"
  FileWrite $R8 "Date/Time    : $R3-$R2-$R1  $R5:$R6:$R7 (local)$\r$\n"
  FileWrite $R8 "Version      : ${VERSION}$\r$\n"
  FileWrite $R8 "Install Dir  : $INSTDIR$\r$\n"
  FileWrite $R8 "Data Dir     : $R0$\r$\n"
  FileWrite $R8 "Log Dir      : $R0\logs$\r$\n"
  FileWrite $R8 "$\r$\n"
  FileWrite $R8 "--- Installation Steps ---$\r$\n"
  FileWrite $R8 "[OK] Per-user data directories created$\r$\n"
  FileWrite $R8 "[OK] Application files copied$\r$\n"
  FileClose $R8

  DetailPrint "Installation complete. Log: $R0\logs\install.log"
!macroend

; =============================================================================
; customUnInstall — runs before removing files
; =============================================================================

!macro customUnInstall
  SetDetailsView show
  
  DetailPrint "Stopping Ambilight background service..."
  nsExec::ExecToLog 'taskkill /F /IM ambilight-service.exe /T'

  DetailPrint "Removing start-on-login launcher..."
  Delete "$APPDATA\Microsoft\Windows\Start Menu\Programs\Startup\AmbilightService.cmd"

  DetailPrint "Uninstallation complete."
  ; Note: user configuration, logs, and metrics in %USERPROFILE%\.ambilight are preserved
!macroend

; =============================================================================
; customRemoveFiles — wipe entire install dir to avoid version conflicts
; =============================================================================

!macro customRemoveFiles
  ; Clean upgrade: electron-builder's default file removal only deletes
  ; paths in its manifest. The bundled PyInstaller service can write
  ; __pycache__/*.pyc files that the manifest never tracked, causing
  ; "works on clean install but fails after update" bugs. On uninstall or
  ; upgrade, wipe the entire $INSTDIR so nothing stale survives.
  ;
  ; Safe: uninstaller runs from a temp copy, not from $INSTDIR, so it can
  ; delete its own directory. User data lives in %USERPROFILE%\.ambilight
  ; OUTSIDE $INSTDIR and is untouched.
  ${if} $INSTDIR != ""
  ${andif} $INSTDIR != "$PROGRAMFILES"
  ${andif} $INSTDIR != "$PROGRAMFILES64"
  ${andif} $INSTDIR != "$WINDIR"
    RMDir /r "$INSTDIR"
  ${endif}
!macroend
