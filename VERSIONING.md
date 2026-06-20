# Versioning Guide

**Ambilight Desktop** uses a **single source of truth** for versioning across both the Python backend service and the Electron UI.

## Single Source: The `VERSION` File

The canonical version is stored in the `VERSION` file at the repository root:

```
$ cat VERSION
1.0.2
```

**Format**: Semantic Versioning (X.Y.Z: major.minor.patch)

---

## How Version Is Used

### 1. **Python Service** (`ambilight.__version__`)

The Python package reads the `VERSION` file dynamically at runtime:

```python
# ambilight/__init__.py
from pathlib import Path

_version_file = Path(__file__).resolve().parent.parent / "VERSION"
__version__ = _version_file.read_text(encoding="utf-8").strip()
```

**Exposed on**:
- `/health` API endpoint (`GET /api/health`)
- `/api/status` endpoint
- Service startup logs
- Error reports and telemetry

### 2. **Electron UI** (`ui/package.json`)

The UI version is synced from `VERSION` by the `scripts/sync-version.mjs` script:

```json
// ui/package.json (auto-synced before every build)
{
  "version": "1.0.2"
}
```

**Driven by**:
- Installer name and version (e.g., `Ambilight Desktop Setup 1.0.2.exe`)
- electron-updater release feed
- GitHub release tags

### 3. **Build Validation** (`build.py`)

The build script validates version consistency:

```python
# build.py: _check_version_sync()
canonical_version = (ROOT / "VERSION").read_text().strip()  # Read once
pkg_version = json.load(UI_DIR / "package.json")["version"]  # Verify UI is synced
assert pkg_version == canonical_version
```

---

## Workflow: Bumping the Version

### For Release (1.0.2 → 1.0.3)

1. **Edit `VERSION` file** (only place to edit):

   ```bash
   echo "1.0.3" > VERSION
   ```

2. **Run sync script** (syncs to ui/package.json):

   ```bash
   node scripts/sync-version.mjs
   # Output: ✓ Version synced: 1.0.2 → 1.0.3
   ```

3. **Build the project** (builds automatically sync on start):

   ```bash
   npm run electron:build  # Runs sync:version internally
   ```

   Or explicitly sync before building any component:

   ```bash
   pnpm run sync:version  # Manual sync
   python build.py         # Build (validates sync'd versions)
   ```

4. **Commit & Tag**:

   ```bash
   git add VERSION ui/package.json
   git commit -m "chore: bump version to 1.0.3"
   git tag -a v1.0.3 -m "..."
   git push origin v1.0.3
   ```

---

## Design: Why Single Source?

| Problem (Multi-File) | Solution (Single Source) |
|----------------------|--------------------------|
| Easy to forget one file | Edit VERSION only |
| Version mismatch breaks builds | build.py validates sync |
| Installer/service disagree on version | Both read from single canonical file |
| Manual sync error-prone | sync-version.mjs automates |

**Benefits**:
- ✅ One place to bump: `VERSION` file
- ✅ Automatic validation: build.py fails if mismatched
- ✅ Auto-sync: sync:version runs before every build
- ✅ Python service always live: reads from disk at runtime (no rebuild needed for version bump)
- ✅ No version drift: guaranteed consistency

---

## Commands Reference

### Manual Operations

```bash
# Check current version
cat VERSION

# Bump version
echo "1.0.3" > VERSION

# Sync VERSION to ui/package.json
pnpm run sync:version
# Or: node scripts/sync-version.mjs

# Verify sync (should print "[OK] Version in sync: X.Y.Z")
python -c "from build import _check_version_sync; _check_version_sync()"

# Check Python service version
python -c "from ambilight import __version__; print(__version__)"
```

### Build Workflow (Automatic Sync)

```bash
# All these automatically sync before building:
npm run electron:build      # Sync + build UI installer
npm run dist:win            # Sync + build Windows version
npm run dist:mac            # Sync + build macOS version
npm run dist:linux          # Sync + build Linux version

# Python service only (does NOT sync, validation only):
python build.py --service   # Uses existing VERSION
```

---

## CI/CD Integration

GitHub Actions (or other CI) should:

1. **Before building**: Run sync-version.mjs to ensure ui/package.json matches VERSION
2. **Build step**: build.py validates sync'd versions match
3. **Release step**: Create git tag from VERSION file

**Example GitHub Actions**:

```yaml
- name: Sync version
  run: node scripts/sync-version.mjs

- name: Validate version sync
  run: python -c "from build import _check_version_sync; _check_version_sync()"

- name: Build
  run: npm run electron:build

- name: Create release
  run: |
    VERSION=$(cat VERSION)
    gh release create v${VERSION} ...
```

---

## Troubleshooting

### "Version mismatch: VERSION=X.Y.Z but ui/package.json=A.B.C"

**Cause**: ui/package.json is out of sync with VERSION file.

**Fix**:
```bash
node scripts/sync-version.mjs
git add ui/package.json
git commit -m "chore: sync version to $(cat VERSION)"
```

### "Invalid version format in VERSION file"

**Cause**: VERSION file doesn't contain a valid semver (X.Y.Z).

**Fix**:
```bash
echo "1.0.2" > VERSION  # Use proper X.Y.Z format
```

### "VERSION file is empty"

**Cause**: VERSION file exists but is blank.

**Fix**:
```bash
echo "1.0.2" > VERSION
```

---

## Implementation Details

### `VERSION` File

- **Location**: Repository root
- **Format**: Single line, X.Y.Z semver (e.g., `1.0.2\n`)
- **Checked by**: build.py, ambilight/__init__.py, sync-version.mjs

### `ambilight/__init__.py`

Reads VERSION at import time (runtime):

```python
_version_file = Path(__file__).resolve().parent.parent / "VERSION"
__version__ = _version_file.read_text(encoding="utf-8").strip()
```

**Advantages**:
- Python service reflects latest VERSION without rebuild
- No duplication; always live from disk
- Useful for in-dev testing (edit VERSION, restart service)

### `scripts/sync-version.mjs`

Reads VERSION and updates ui/package.json:

```bash
node scripts/sync-version.mjs
```

**Features**:
- Validates semver format
- Only writes if changed (cleaner git diff)
- Exits with error if VERSION is malformed

### `build.py`

Validates VERSION and ui/package.json match:

```python
def _check_version_sync() -> str:
    canonical_version = (ROOT / "VERSION").read_text().strip()
    pkg_version = json.load(UI_DIR / "package.json")["version"]
    assert canonical_version == pkg_version, "Mismatch!"
```

**Runs on**: Every build to catch sync issues early

---

## Summary

- **Edit only**: `VERSION` file
- **Syncs to**: ui/package.json (automatic via scripts/sync-version.mjs)
- **Read by**: Python service (runtime), build.py (validation), electron-builder (installer)
- **Verified by**: build.py before every build
- **Single source of truth**: VERSION file is canonical
