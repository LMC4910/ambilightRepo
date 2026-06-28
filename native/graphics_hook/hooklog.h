// hooklog.h — tiny diagnostic logger for the injected DLL.
//
// Writes to %USERPROFILE%\.ambilight\logs\graphics_hook.log (same tree as the
// rest of the app) and to the debugger (OutputDebugString). Because the DLL runs
// inside the game process, a logfile is the practical way to confirm what hooked
// and how many frames flowed when testing.

#ifndef AMBILIGHT_HOOKLOG_H
#define AMBILIGHT_HOOKLOG_H

namespace ambilight {

void hook_log(const char* fmt, ...);

}  // namespace ambilight

#endif  // AMBILIGHT_HOOKLOG_H
