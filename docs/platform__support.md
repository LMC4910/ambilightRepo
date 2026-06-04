# Platform Support

## Current Platform Status

| Platform | Status | Release Artifacts |
|----------|--------|------------------|
| Windows | ✅ Fully Supported | ✅ Published |
| Linux | ✅ Fully Supported | ✅ Published |
| macOS | ⚠️ Functional | ❌ Not Published |

## Windows

Windows is a fully supported platform.

Features:

- Desktop application
- Background service
- Screen synchronization
- Audio-reactive effects
- Automatic updates
- GitHub Actions release builds

Official installers are generated and published with every tagged release.

---

## Linux

Linux is a fully supported platform.

Features:

- Desktop application
- Background service
- Screen synchronization
- Audio-reactive effects
- AppImage distribution
- Debian package distribution
- GitHub Actions release builds

Official release artifacts are generated and published with every tagged release.

---

## macOS

The application itself is functional on macOS.

Core functionality works, including:

- Desktop application
- Background service
- Screen synchronization
- Configuration management

However, official release artifacts are currently not published.

### Why are macOS builds unavailable?

Apple requires:

- Apple Developer Account
- Developer ID Application Certificate
- Code Signing
- Notarization

The project currently does not have the required Apple signing and notarization infrastructure configured.

As a result:

- The codebase remains compatible with macOS.
- Development builds may work locally.
- Official release packages are intentionally disabled.

### Future Support

macOS release builds will be enabled once:

1. Apple Developer signing certificates are available.
2. Automated code signing is configured.
3. Automated notarization is configured.
4. CI/CD release validation passes successfully.

---

## Support Policy

### Fully Supported

- Windows
- Linux

### Functional but Release Builds Disabled

- macOS

Community testing and contributions are welcome on all platforms.
