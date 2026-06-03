# Design Document: README Documentation Update

## Overview

This design outlines the comprehensive update of the README.md file to serve as an effective entry point for the Ambilight Desktop project. The README must communicate both the current CLI-based implementation and the planned service-based architecture documented in the PRD and TRD, while remaining accessible to diverse user personas.

The design addresses the challenge of presenting a project in transition: the codebase currently implements a functional CLI-based ambilight system, while the product vision describes a comprehensive desktop application with persistent service architecture. The README must clearly distinguish current capabilities from planned features to set appropriate expectations.

### Design Goals

1. **Progressive Disclosure**: Enable readers to quickly find information relevant to their goals without forcing them to read irrelevant content
2. **Dual Timeline Communication**: Clearly distinguish current implementation from planned architecture
3. **Multi-Persona Accessibility**: Serve home theater enthusiasts, gamers, developers, and casual users with targeted information
4. **Technical Accuracy**: Ensure all commands, configurations, and architecture descriptions match actual implementation
5. **Comprehensive Referencing**: Connect README content to detailed documentation in docs/ folder


## Architecture

### Information Architecture

The README follows a layered information architecture that respects the reader's journey:

```
┌─────────────────────────────────────────────────────────────┐
│  LAYER 1: IMMEDIATE VALUE                                   │
│  - Hero statement (what is this?)                           │
│  - Status badges (build, license, version)                  │
│  - Project vision (30-second pitch)                         │
│  - Quick start for impatient users                          │
└─────────────────────────────────────────────────────────────┘
                            ↓
┌─────────────────────────────────────────────────────────────┐
│  LAYER 2: CURRENT CAPABILITIES                              │
│  - What works TODAY (CLI implementation)                    │
│  - Installation instructions                                │
│  - Configuration guide                                      │
│  - Usage examples                                           │
│  - Troubleshooting                                          │
└─────────────────────────────────────────────────────────────┘
                            ↓
┌─────────────────────────────────────────────────────────────┐
│  LAYER 3: FUTURE ARCHITECTURE                               │
│  - Planned service-based architecture                       │
│  - Desktop application vision                               │
│  - Development roadmap                                      │
│  - Migration path from CLI to service                       │
└─────────────────────────────────────────────────────────────┘
                            ↓
┌─────────────────────────────────────────────────────────────┐
│  LAYER 4: DEEP TECHNICAL REFERENCE                          │
│  - Module responsibilities                                  │
│  - Performance optimization                                 │
│  - Advanced configuration                                   │
│  - Links to comprehensive docs/                             │
└─────────────────────────────────────────────────────────────┘
```


### Document Structure

The README is organized into the following major sections:

1. **Header & Project Vision** (Requirements 1, 12)
   - Project name and tagline
   - Status badges (build status, license, version)
   - Product vision statement from PRD
   - User persona descriptions
   - Development status indicator

2. **Quick Start** (Requirements 3, 9)
   - Minimal path to running the CLI
   - Single command installation for common case
   - Device discovery command
   - Basic run command

3. **Current Implementation** (Requirements 3, 8, 9)
   - CLI architecture diagram
   - Installation instructions (detailed)
   - Configuration guide
   - Command-line usage
   - Environment variables
   - Troubleshooting

4. **Planned Architecture** (Requirements 2, 4)
   - Service-based architecture vision
   - Dual-component design (Python service + Electron UI)
   - Architecture diagram showing service lifecycle
   - Roadmap milestones (M0-M5)
   - Links to PRD and TRD

5. **Technical Reference** (Requirements 6, 7)
   - Module responsibilities table
   - Performance characteristics
   - Platform support matrix
   - Color modes comparison
   - Capture backend comparison

6. **Documentation Index** (Requirement 7)
   - Annotated list of docs/ files
   - Purpose of each document
   - When to consult each document

7. **Contributing** (Requirement 11)
   - Current development phase
   - Priority contribution areas
   - Link to refactoring plan
   - Testing instructions

8. **License & Contact** (Requirement 12)
   - MIT license statement
   - Issue reporting guidelines
   - Community channels


## Components and Interfaces

### Visual Distinction Strategy

To clearly distinguish current from planned features, the design employs consistent visual indicators:

#### Status Indicators

**Current Implementation**:
- Section header: `## Current Implementation: CLI Mode`
- Badge format: `✅ Available Now`
- Code blocks with runnable commands
- Reference to actual files in current codebase

**Planned Features**:
- Section header: `## Planned: Service Architecture`
- Badge format: `🚧 In Development` or `📅 Roadmap: M2`
- Architecture diagrams with future components
- Reference to PRD/TRD specifications

**Example Markdown Pattern**:
```markdown
## Current Implementation: CLI Mode ✅

You can use Ambilight Desktop today as a command-line tool...

## Planned: Desktop Application 🚧

The next phase of development will introduce...
(See [PRD Section 3.8](docs/02_prd.md#38-desktop-ui-fr-ui) for details)
```

### Navigation Components

#### Table of Contents

For sections exceeding 100 lines, include a linked table of contents:

```markdown
## Table of Contents

- [Quick Start](#quick-start)
- [Current Implementation](#current-implementation-cli-mode-)
  - [Installation](#installation)
  - [Configuration](#configuration)
  - [Usage](#usage)
- [Planned Architecture](#planned-service-architecture-)
- [Technical Reference](#technical-reference)
- [Documentation](#documentation)
```


#### Persona-Based Navigation Callouts

Include navigation hints for different reader personas:

```markdown
---

**👤 Different paths for different goals:**

- **Just want to try it?** → Jump to [Quick Start](#quick-start)
- **Evaluating for home theater setup?** → See [Current Implementation](#current-implementation-cli-mode-) and [Troubleshooting](#troubleshooting)
- **Interested in contributing?** → Read [Planned Architecture](#planned-service-architecture-) and [Contributing](#contributing)
- **Deep technical dive?** → Start with [Architecture](#architecture) then explore [Documentation](#documentation)

---
```

### Architecture Diagrams

#### Current CLI Architecture Diagram

Preserve the existing ASCII diagram from the current README with minor enhancements:

```
Current CLI Architecture

┌─────────────────────────────────────────────────────────────────┐
│                    main.py (CLI entry) ✅                        │
└───────────────────────────────┬─────────────────────────────────┘
                                │
                    ┌───────────▼───────────┐
                    │   AmbilightPipeline   │
                    │  (orchestrates all)   │
                    └──┬────┬────┬────┬────┘
                       │    │    │    │
         ┌─────────────┘    │    │    └──────────────────┐
         │                  │    │                        │
┌────────▼───────┐  ┌───────▼──────┐  ┌──────────────────▼──────┐
│ ScreenCapture  │  │  ZoneManager │  │    ColorAnalyzer         │
│    Manager     │  │   zones.py   │  │      color.py            │
│   capture.py   │  └──────────────┘  └──────────────────────────┘
└────────────────┘                               │
                                                 │
                                    ┌────────────▼──────────┐
                                    │  SmoothingEngine      │
                                    │   smoothing.py        │
                                    └────────────┬──────────┘
                                                 │
                                    ┌────────────▼──────────┐
                                    │ MagicHomeController   │
                                    │   led_output.py       │
                                    └───────────────────────┘
```


#### Planned Service Architecture Diagram

Create a new diagram showing the future service-based architecture from the TRD:

```
Planned Service Architecture (🚧 Roadmap: M4)

┌──────────────────────────────────────────────────────────────┐
│               Electron Desktop Application                    │
│  ┌────────────────────────────────────────────────────────┐  │
│  │  React UI (Settings, Profiles, Live Preview, Logs)    │  │
│  └────────────┬───────────────────────────────────────────┘  │
│               │ WebSocket (metrics) + REST (control)         │
└───────────────┼──────────────────────────────────────────────┘
                │
┌───────────────▼──────────────────────────────────────────────┐
│          Python Background Service (auto-start)               │
│  ┌──────────────────────────────────────────────────────┐    │
│  │  FastAPI Server (REST + WebSocket)                    │    │
│  └──────────────────────┬───────────────────────────────┘    │
│                         │                                     │
│  ┌──────────────────────▼────────────────────────────────┐   │
│  │  Pipeline Controller                                   │   │
│  │  - Display event recovery (lock/unlock/sleep/wake)    │   │
│  │  - Profile management                                 │   │
│  │  - Effects engine                                     │   │
│  │  - Gradient engine (addressable LEDs)                 │   │
│  └──────────────────────┬────────────────────────────────┘   │
│                         │                                     │
│  ┌──────────────────────▼────────────────────────────────┐   │
│  │  Core Pipeline (reused from CLI)                      │   │
│  │  Capture → Zones → Color → Smoothing → LED Output     │   │
│  └────────────────────────────────────────────────────────┘   │
└──────────────────────────────────────────────────────────────┘
                         │ TCP :5577
                         ▼
                  MagicHome Device
```


### Content Organization Strategy

#### Persona-Targeted Content Blocks

Content is organized to serve different user personas identified in the PRD:

**Home Theater Enthusiast ("Alex")**
- Needs: DRM-bypass capture info, movie-quality smoothing settings, troubleshooting
- Served by: Capture backend comparison, smoothing tuning table, DRM troubleshooting section

**PC Gamer ("Jordan")**
- Needs: Performance impact data, low-latency reactive mode, FPS verification
- Served by: Performance optimization section, gaming profile config, "No FPS impact" verification

**Developer/Power User ("Sam")**
- Needs: Architecture understanding, API documentation, contribution opportunities
- Served by: Architecture diagrams, module responsibilities, contributing section, docs/ index

**Casual User ("Riley")**
- Needs: Simple installation, clear steps, safety assurances
- Served by: Quick start section, step-by-step guides, troubleshooting with solutions

#### Progressive Detail Pattern

Information follows a "summary → detail → reference" pattern:

1. **Summary Level**: High-level statement in main section
2. **Detail Level**: Explanation and examples in subsection
3. **Reference Level**: Link to comprehensive documentation in docs/

Example:
```markdown
## Planned: Service Architecture 🚧

Ambilight Desktop will transform into a persistent background service with a
native desktop UI. *(summary)*

The service will start automatically with your OS and continue running even
when you close the UI window, ensuring your LEDs work reliably without manual
intervention. *(detail)*

See the [Technical Requirements Document](docs/03_trd.md) for the complete
service architecture specification. *(reference)*
```


## Data Models

### README Content Model

The README can be modeled as structured sections with metadata:

```typescript
interface ReadmeSection {
  title: string;
  status: 'current' | 'planned' | 'reference';
  personas: Array<'alex' | 'jordan' | 'sam' | 'riley'>;
  priority: 'essential' | 'important' | 'supplementary';
  content: {
    summary?: string;
    body: string;
    codeExamples?: CodeBlock[];
    diagrams?: Diagram[];
    references?: DocumentReference[];
  };
}

interface CodeBlock {
  language: string;
  code: string;
  verified: boolean;  // Matches actual implementation
  platform?: 'windows' | 'macos' | 'linux' | 'all';
}

interface Diagram {
  type: 'ascii' | 'mermaid';
  content: string;
  caption?: string;
}

interface DocumentReference {
  path: string;  // Relative path to docs/ file
  section?: string;  // Optional anchor
  description: string;
}
```

### Configuration Schema Reference

When documenting configuration, maintain consistency with the actual schema:

```yaml
# Reference: ambilight/config.py AppConfig dataclass
device:
  ip: string (IPv4 format)
  mac: string (MAC address format, optional)

capture:
  method: enum ['wgc', 'dxgi', 'mss']
  monitor_index: integer >= 0
  fps_target: integer (5-60)
  analysis_width: integer (20-320)
  analysis_height: integer (11-180)

color:
  mode: enum ['average', 'edges', 'dominant', 'kmeans', 'saturation_weighted']
  ignore_black: boolean
  ignore_white: boolean
  black_threshold: integer (0-255)
  white_threshold: integer (0-255)

smoothing:
  base_alpha: float (0.0-1.0)
  fast_alpha: float (0.0-1.0)
  fast_threshold: integer (0-255)

led:
  min_change: integer (0-255)
```


### Platform Support Matrix

Platform support information must match PRD NFR-C requirements:

```typescript
interface PlatformSupport {
  os: 'windows' | 'macos' | 'linux';
  currentStatus: 'supported' | 'partial' | 'planned';
  minimumVersion: string;
  recommendedVersion: string;
  captureBackends: Array<{
    name: string;
    status: 'available' | 'planned';
    latency: 'low' | 'medium' | 'high';
    drmBypass: boolean;
  }>;
  specialRequirements?: string[];
}
```

Example data:
```typescript
const windowsSupport: PlatformSupport = {
  os: 'windows',
  currentStatus: 'supported',
  minimumVersion: '10 22H2 (build 19045)',
  recommendedVersion: '11 23H2',
  captureBackends: [
    { name: 'WGC', status: 'available', latency: 'low', drmBypass: true },
    { name: 'DXGI', status: 'available', latency: 'low', drmBypass: false },
    { name: 'MSS', status: 'available', latency: 'medium', drmBypass: false }
  ],
  specialRequirements: ['WGC requires Windows 10 1903+']
};
```


## Error Handling

### Technical Accuracy Validation

To maintain requirement 6 (technical accuracy), the README update process includes validation steps:

#### Command Verification

All command examples in the README must be verified:

```python
# Validation script: scripts/validate-readme-commands.py
import re
import subprocess
from pathlib import Path

def extract_command_blocks(readme_path: Path) -> list[str]:
    """Extract all bash/powershell code blocks from README."""
    content = readme_path.read_text()
    # Match ```bash or ```powershell blocks
    pattern = r'```(?:bash|powershell)\n(.*?)\n```'
    return re.findall(pattern, content, re.DOTALL)

def verify_command_syntax(command: str) -> bool:
    """Verify command syntax without execution."""
    # For Python commands
    if command.startswith('python'):
        return verify_python_command(command)
    # For pip commands
    if command.startswith('pip'):
        return verify_pip_command(command)
    return True  # Skip verification for complex commands

def verify_python_command(command: str) -> bool:
    """Check if Python command references real modules."""
    if '-m' in command:
        module = extract_module_name(command)
        # Check if module exists in codebase
        return module_exists(module)
    return True
```

#### Configuration Schema Consistency

Configuration examples must match the actual AppConfig dataclass:

```python
# Validation: compare README yaml examples with config.py schema
from ambilight.config import AppConfig
import yaml

def validate_config_example(yaml_str: str) -> tuple[bool, list[str]]:
    """Validate that README config example matches AppConfig schema."""
    config_dict = yaml.safe_load(yaml_str)
    errors = []
    
    # Check all keys exist in AppConfig
    valid_keys = get_appconfig_fields(AppConfig)
    for key in config_dict.keys():
        if key not in valid_keys:
            errors.append(f"Unknown config key: {key}")
    
    return len(errors) == 0, errors
```


#### Architecture Diagram Consistency

Architecture diagrams must reflect actual module relationships:

```python
def validate_architecture_diagram(diagram: str, codebase_path: Path) -> bool:
    """Verify that diagram modules exist and relationships are correct."""
    # Extract module names from diagram (e.g., "capture.py", "color.py")
    mentioned_modules = extract_module_names_from_diagram(diagram)
    
    # Check all mentioned modules exist
    for module in mentioned_modules:
        module_path = codebase_path / 'ambilight' / module
        if not module_path.exists():
            print(f"Warning: Diagram references non-existent module: {module}")
            return False
    
    return True
```

### Handling Documentation Drift

Documentation can drift from implementation over time. The design includes mechanisms to detect and prevent drift:

#### Automated Consistency Checks

```yaml
# .github/workflows/docs-check.yml
name: Documentation Consistency Check

on: [pull_request]

jobs:
  validate-readme:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v3
      - name: Setup Python
        uses: actions/setup-python@v4
        with:
          python-version: '3.12'
      - name: Install dependencies
        run: pip install -r requirements.txt
      - name: Validate README commands
        run: python scripts/validate-readme-commands.py
      - name: Check config examples
        run: python scripts/validate-config-examples.py
      - name: Verify module references
        run: python scripts/check-module-references.py
```

#### Manual Review Checklist

When updating README, reviewers must verify:

- [ ] All `python` commands reference existing scripts or modules
- [ ] All configuration examples use valid keys from AppConfig
- [ ] Version numbers match pyproject.toml and package.json
- [ ] Platform requirements match PRD NFR-C section
- [ ] Performance claims cite PRD/TRD or benchmarks
- [ ] Architecture diagrams reference existing files
- [ ] Links to docs/ files are valid relative paths


## Testing Strategy

Since this is a documentation feature, traditional property-based testing is not applicable. Instead, testing focuses on content accuracy, link validity, and readability.

### Documentation Testing Approach

#### 1. Link Validation Tests

Verify all internal and external links are valid:

```python
# tests/test_readme_links.py
import re
from pathlib import Path
import requests

def test_internal_links_valid():
    """Verify all internal links point to existing files/sections."""
    readme = Path('README.md').read_text()
    
    # Extract markdown links: [text](path) or [text](path#anchor)
    links = re.findall(r'\[([^\]]+)\]\(([^\)]+)\)', readme)
    
    for text, link in links:
        if link.startswith('http'):
            continue  # Skip external links in this test
        
        # Handle anchors
        if '#' in link:
            path, anchor = link.split('#', 1)
        else:
            path = link
            anchor = None
        
        # Verify file exists
        target = Path(path)
        assert target.exists(), f"Broken link: {link} (from text: {text})"
        
        # If anchor specified, verify it exists in target file
        if anchor:
            content = target.read_text()
            assert anchor_exists(content, anchor), \
                f"Anchor #{anchor} not found in {path}"

def test_external_links_accessible():
    """Verify external links return 200 OK."""
    readme = Path('README.md').read_text()
    links = re.findall(r'\[([^\]]+)\]\((http[^\)]+)\)', readme)
    
    for text, url in links:
        response = requests.head(url, timeout=5, allow_redirects=True)
        assert response.status_code == 200, \
            f"Broken external link: {url}"
```


#### 2. Command Syntax Tests

Verify that all command examples are syntactically valid:

```python
# tests/test_readme_commands.py
import re
import subprocess
from pathlib import Path

def test_python_commands_valid():
    """Verify all python commands reference existing modules."""
    readme = Path('README.md').read_text()
    
    # Extract python commands from bash blocks
    bash_blocks = re.findall(r'```bash\n(.*?)\n```', readme, re.DOTALL)
    
    for block in bash_blocks:
        lines = block.split('\n')
        for line in lines:
            if line.startswith('python'):
                verify_python_command_syntax(line)

def verify_python_command_syntax(command: str):
    """Check python command syntax without execution."""
    # Extract module name from "python -m ambilight.service"
    if '-m' in command:
        match = re.search(r'-m\s+(\S+)', command)
        if match:
            module = match.group(1)
            # Check module exists
            module_path = Path('service/ambilight') / module.replace('.', '/') + '.py'
            alt_path = Path('service/ambilight') / module.replace('.', '/') / '__main__.py'
            assert module_path.exists() or alt_path.exists(), \
                f"Command references non-existent module: {module}"

def test_pip_install_commands_valid():
    """Verify all pip install commands reference real packages."""
    readme = Path('README.md').read_text()
    
    pip_commands = re.findall(r'pip install ([^\n]+)', readme)
    
    for packages in pip_commands:
        # Parse package names (handle "pkg>=version" syntax)
        pkg_names = [p.split('[')[0].split('>')[0].split('=')[0].strip() 
                     for p in packages.split()]
        
        for pkg in pkg_names:
            if pkg.startswith('-'):  # Skip flags like -r
                continue
            # Check package exists in requirements files
            assert package_in_requirements(pkg), \
                f"Package {pkg} not found in any requirements file"
```


#### 3. Configuration Example Tests

Verify configuration examples match the actual schema:

```python
# tests/test_readme_config.py
import yaml
from pathlib import Path
from ambilight.config import AppConfig
import re

def test_config_examples_valid():
    """Verify all YAML config examples in README are valid."""
    readme = Path('README.md').read_text()
    
    # Extract YAML code blocks
    yaml_blocks = re.findall(r'```yaml\n(.*?)\n```', readme, re.DOTALL)
    
    for block in yaml_blocks:
        # Skip if it's a schema documentation block
        if 'string (IPv4 format)' in block or 'enum [' in block:
            continue
        
        # Parse YAML
        config_dict = yaml.safe_load(block)
        
        # Validate against AppConfig schema
        errors = validate_config_dict(config_dict, AppConfig)
        assert len(errors) == 0, \
            f"Invalid config example:\n{block}\nErrors: {errors}"

def validate_config_dict(config: dict, schema: type) -> list[str]:
    """Validate config dict against AppConfig dataclass schema."""
    from dataclasses import fields, is_dataclass
    errors = []
    
    # Get valid field names
    if is_dataclass(schema):
        valid_keys = {f.name for f in fields(schema)}
        
        # Check for unknown keys
        for key in config.keys():
            if key not in valid_keys:
                errors.append(f"Unknown field: {key}")
        
        # Recursively validate nested dataclasses
        for field in fields(schema):
            if field.name in config:
                if is_dataclass(field.type):
                    nested_errors = validate_config_dict(
                        config[field.name], 
                        field.type
                    )
                    errors.extend(nested_errors)
    
    return errors
```


#### 4. Readability and Accessibility Tests

Verify the README meets readability standards:

```python
# tests/test_readme_readability.py
from pathlib import Path
import re

def test_section_headers_hierarchy():
    """Verify headers follow proper hierarchy (no skipping levels)."""
    readme = Path('README.md').read_text()
    
    # Extract all headers
    headers = re.findall(r'^(#{1,6})\s+(.+)$', readme, re.MULTILINE)
    
    prev_level = 0
    for hashes, title in headers:
        level = len(hashes)
        # Should not skip levels (e.g., # then ###)
        assert level <= prev_level + 1, \
            f"Header hierarchy skip: {hashes} {title}"
        prev_level = level

def test_code_blocks_have_language():
    """Verify all code blocks specify a language for syntax highlighting."""
    readme = Path('README.md').read_text()
    
    # Find code blocks without language specifier
    invalid_blocks = re.findall(r'```\n', readme)
    
    assert len(invalid_blocks) == 0, \
        f"Found {len(invalid_blocks)} code blocks without language specifier"

def test_table_formatting():
    """Verify markdown tables are properly formatted."""
    readme = Path('README.md').read_text()
    
    # Find table blocks (lines with |)
    lines = readme.split('\n')
    in_table = False
    
    for i, line in enumerate(lines):
        if '|' in line and not line.strip().startswith('│'):  # ASCII art uses │
            if not in_table:
                # First line of table
                in_table = True
                # Next line should be separator (|---|---|)
                if i + 1 < len(lines):
                    next_line = lines[i + 1]
                    assert re.match(r'^\|[\s\-:|]+\|$', next_line), \
                        f"Table at line {i} missing separator row"
        elif in_table and '|' not in line:
            in_table = False

def test_line_length_reasonable():
    """Verify no line exceeds reasonable length for readability."""
    readme = Path('README.md').read_text()
    
    max_length = 120
    long_lines = []
    
    for i, line in enumerate(readme.split('\n'), 1):
        # Ignore code blocks and tables
        if line.startswith('```') or '|' in line or line.startswith('│'):
            continue
        if len(line) > max_length:
            long_lines.append((i, len(line), line[:80]))
    
    # Allow some long lines (URLs, etc.) but flag excessive ones
    assert len(long_lines) < 10, \
        f"Too many long lines ({len(long_lines)}). Examples:\n" + \
        '\n'.join(f"Line {i}: {length} chars: {preview}..." 
                  for i, length, preview in long_lines[:3])
```


#### 5. Integration Tests

Test the README with actual user workflows:

```python
# tests/integration/test_quick_start_workflow.py
import subprocess
from pathlib import Path
import tempfile
import shutil

def test_quick_start_workflow():
    """Verify the Quick Start section commands work end-to-end."""
    with tempfile.TemporaryDirectory() as tmpdir:
        # 1. Clone would happen here (skip in test)
        # 2. Create virtual environment
        venv_path = Path(tmpdir) / 'venv'
        subprocess.run(['python', '-m', 'venv', str(venv_path)], check=True)
        
        # 3. Activate and install requirements
        if sys.platform == 'win32':
            python = venv_path / 'Scripts' / 'python.exe'
        else:
            python = venv_path / 'bin' / 'python'
        
        subprocess.run([
            str(python), '-m', 'pip', 'install', '-r', 'requirements.txt'
        ], check=True)
        
        # 4. Test discovery command (should not fail)
        result = subprocess.run([
            str(python), 'main.py', '--discover'
        ], capture_output=True, text=True)
        
        # Should succeed or report "no devices found" (not crash)
        assert result.returncode in [0, 1]
        assert 'Traceback' not in result.stderr
        
        # 5. Test config validation
        result = subprocess.run([
            str(python), '-c', 
            'from ambilight.config import load_config; load_config("configuration.yaml")'
        ], capture_output=True, text=True)
        
        assert result.returncode == 0
```


### Manual Testing Checklist

Human reviewers must verify:

**Visual Consistency**
- [ ] Status badges (✅, 🚧, 📅) are used consistently
- [ ] ASCII diagrams render correctly in GitHub's markdown viewer
- [ ] Tables are properly aligned
- [ ] Code blocks have proper syntax highlighting

**Content Accuracy**
- [ ] All version numbers match actual versions in pyproject.toml
- [ ] Performance claims cite specific benchmarks or TRD sections
- [ ] Configuration examples use valid keys from AppConfig
- [ ] Module names match actual files in ambilight/

**Navigation**
- [ ] Table of contents links work
- [ ] Internal file links point to existing docs
- [ ] Anchor links navigate to correct headers
- [ ] Persona callouts clearly direct readers

**Completeness**
- [ ] All 12 requirements are addressed
- [ ] Current CLI features are documented
- [ ] Planned service architecture is explained
- [ ] Platform support is clearly stated
- [ ] Contribution guidelines are present

**Accessibility**
- [ ] No broken images or links
- [ ] Alt text provided for diagrams (in comments)
- [ ] Headers follow logical hierarchy
- [ ] Text is readable without special formatting


## Content Strategy Details

### Product Vision Section

This section addresses Requirement 1 (Communicate Product Vision):

```markdown
# Ambilight Desktop

**Production-grade ambient lighting platform for any display**

[![Build Status](https://github.com/user/ambilight-desktop/workflows/CI/badge.svg)](https://github.com/user/ambilight-desktop/actions)
[![License: MIT](https://img.shields.io/badge/License-MIT-blue.svg)](LICENSE)
[![Python 3.12](https://img.shields.io/badge/python-3.12-blue.svg)](https://www.python.org/downloads/)

> **Transform any display into an immersive viewing experience with dynamic,
> screen-reactive LED lighting — without proprietary hardware lock-in.**

Ambilight Desktop brings the premium Philips Ambilight experience to custom
LED setups with MagicHome controllers. Inspired by cinema-quality ambient
lighting, built to rival commercial systems.

## Development Status

🚧 **Current Phase: CLI Implementation** (✅ Stable and usable today)

The project is actively transitioning from a CLI tool to a full desktop
application with persistent background service. The CLI version is production-
ready; the desktop application is under development.

**Roadmap**: CLI → Service Foundation → Desktop UI → Packaged Installer
(See [Development Roadmap](#roadmap) for details)
```

### User Persona Descriptions

Include a concise persona summary (Requirement 1):

```markdown
## Who is this for?

- **🎬 Home Theater Enthusiasts**: Cinema-quality color accuracy, DRM-bypass
  capture, smooth transitions for streaming
- **🎮 PC Gamers**: Sub-50ms latency, zero FPS impact, reactive gaming profiles
- **💻 Developers**: REST API, plugin system, Home Assistant integration
- **👤 Everyone Else**: Simple setup, auto-discovery, reliable operation

Different paths for different goals → [Navigation Guide](#navigation)
```


### Current Implementation Section

This section addresses Requirements 3, 8, 9 (Document Current Capabilities, Platform Support, Setup Instructions):

```markdown
## Current Implementation: CLI Mode ✅

Ambilight Desktop is **available now** as a command-line tool with production-
grade performance and reliability.

### Architecture

[Include current CLI architecture diagram here]

### Features

- ✅ **Multi-backend screen capture**: WGC (DRM bypass), DXGI, MSS
- ✅ **5 color analysis modes**: average, edges, dominant, k-means, saturation-weighted
- ✅ **GPU acceleration**: CuPy, OpenCV CUDA, CPU fallback
- ✅ **Adaptive smoothing**: Fast response to cuts, slow for subtle changes
- ✅ **Auto device discovery**: MAC-based caching, automatic reconnect
- ✅ **Performance**: 30 FPS at <5% CPU, <50ms end-to-end latency

### Platform Support

| Platform | Status | Capture Backends | Notes |
|----------|--------|------------------|-------|
| Windows 10 22H2+ | ✅ Supported | WGC, DXGI, MSS | WGC requires 1903+ |
| Windows 11 | ✅ Supported | WGC, DXGI, MSS | Recommended |
| macOS 13+ | 🚧 Experimental | MSS | ScreenCaptureKit planned |
| Linux (Ubuntu 22.04+) | 🚧 Experimental | MSS | PipeWire planned |

### Installation

[Full installation instructions from current README, verified for accuracy]
```


### Planned Architecture Section

This section addresses Requirements 2, 4 (Describe Service Architecture, Clarify Development Roadmap):

```markdown
## Planned: Service Architecture 🚧

Ambilight Desktop is evolving into a **persistent background service** with a
native desktop control application.

### Vision

The service architecture transforms the current CLI tool into a reliable,
always-available platform:

- **Persistent operation**: Service starts with your OS, continues running when UI is closed
- **Automatic recovery**: Survives display lock/unlock, sleep/wake, monitor changes
- **Zero-maintenance**: Configure once, works reliably without manual intervention
- **Professional UI**: Native desktop app for configuration, monitoring, and profiles
- **Single installer**: One-click install on Windows, macOS, Linux

### Architecture

[Include planned service architecture diagram here]

### Communication Layer

The service exposes dual APIs:

- **WebSocket** (port 7825): Real-time metrics, color preview, device events
- **REST API** (port 7826): Configuration management, profile control, device operations

The Electron desktop app connects to these APIs, providing:
- Live FPS and latency monitoring
- Visual zone color preview
- Profile management (Gaming, Movie, Productivity, Night)
- Effects selection (screen sync, static, breathing, rainbow, music-reactive)
- Device management and diagnostics

### Development Roadmap

See [PRD Section 8](docs/02_prd.md#8-release-roadmap) for complete roadmap.

| Milestone | Status | Target | Key Features |
|-----------|--------|--------|--------------|
| M0 — Service Foundation | 🚧 In Progress | Week 4 | REST/WebSocket API, health checks |
| M1 — Stability | 📅 Planned | Week 6 | Display recovery, crash restart |
| M2 — UI Alpha | 📅 Planned | Week 10 | Electron app with basic controls |
| M3 — Beta | 📅 Planned | Week 14 | Profiles, gradients, system tray |
| M4 — Packaging | 📅 Planned | Week 18 | Platform installers, auto-update |
| M5 — Release | 📅 Planned | Week 24 | Public release with P2 features |

### Migration Path

The CLI implementation will be preserved as the **core pipeline**. The service
wraps this existing logic with:
- Event-driven lifecycle management
- API layer for external control
- Profile and effects engines

No rewrite required — the proven color analysis and capture logic remains
unchanged.

**See**: [Refactoring Plan](docs/04_refactoring_plan.md) for implementation details
```


### Documentation Index Section

This section addresses Requirement 7 (Reference Comprehensive Documentation):

```markdown
## Documentation

Comprehensive technical documentation is available in the `docs/` folder:

| Document | Purpose | When to read |
|----------|---------|--------------|
| [Codebase Assessment](docs/01_codebase_assessment.md) | Initial analysis of the CLI implementation | Understanding project history |
| [Product Requirements (PRD)](docs/02_prd.md) | Complete product vision, user personas, feature requirements | Evaluating project scope |
| [Technical Requirements (TRD)](docs/03_trd.md) | Service architecture, API specifications, security model | Understanding technical design |
| [Refactoring Plan](docs/04_refactoring_plan.md) | Step-by-step migration from CLI to service | Contributing to development |
| [Electron Architecture](docs/05_electron_architecture.md) | Desktop UI design and state management | UI development |
| [Service Architecture](docs/06_service_architecture.md) | Detailed service component design | Service development |
| [Migration Plan](docs/07_migration_plan.md) | Strategy for transitioning users from CLI to service | Deployment planning |
| [Project Structure](docs/08_project_structure.md) | Repository organization and conventions | Navigating codebase |
| [Test Plan](docs/test_plan.md) | Testing strategy and coverage requirements | Writing tests |

### Quick Reference by Goal

**Want to understand the product vision?**
→ Start with [PRD](docs/02_prd.md), especially Section 2 (User Personas) and Section 5 (User Stories)

**Need technical implementation details?**
→ Read [TRD](docs/03_trd.md) for architecture, API specs, and data flow diagrams

**Planning to contribute?**
→ Begin with [Refactoring Plan](docs/04_refactoring_plan.md) to understand current work and priorities

**Looking for code organization?**
→ Consult [Project Structure](docs/08_project_structure.md) for directory layout and module responsibilities
```


### Configuration Persistence Section

This section addresses Requirement 10 (Preserve Parser Round-Trip Requirement):

```markdown
## Configuration

Configuration is managed through `configuration.yaml` in the project root.

### Configuration Format

Ambilight Desktop uses YAML for human-readable configuration with strict
validation and atomic writes to prevent corruption.

**Important**: The configuration system guarantees **round-trip preservation** —
any valid configuration field present in the file will be preserved when the
system reads, modifies, and writes the configuration back. This ensures that
comments, field order, and additional valid fields are never lost.

Configuration updates use the atomic write pattern (write to temporary file,
then rename) to prevent corruption during system crashes or power loss.

### Configuration Schema

The complete configuration schema is defined in `ambilight/config.py` as the
`AppConfig` dataclass. For detailed field descriptions and validation rules,
see [TRD Section 10](docs/03_trd.md#10-configuration-schema-json-schema-fragment).

### Example Configuration

```yaml
device:
  ip: "192.168.1.29"
  mac: "aa:bb:cc:dd:ee:ff"  # Recommended: enables IP change detection

capture:
  method: wgc          # wgc | dxgi | mss
  monitor_index: 0     # 0 = primary monitor
  fps_target: 30
  analysis_width: 80
  analysis_height: 45

color:
  mode: saturation_weighted  # Best balance of quality and performance
  ignore_black: true
  ignore_white: true
  black_threshold: 10
  white_threshold: 245

smoothing:
  base_alpha: 0.15     # Gaming: 0.15, Movie: 0.08, Reactive: 0.30
  fast_alpha: 0.55
  fast_threshold: 60

led:
  min_change: 2        # Suppress imperceptible changes
```

### Configuration Validation

The system validates all configuration fields on load. Invalid values are
rejected with descriptive error messages. Run with `--debug` to see detailed
validation information.
```


### Contributing Section

This section addresses Requirement 11 (Include Contribution Guidelines):

```markdown
## Contributing

Ambilight Desktop welcomes contributions! The project is currently in active
development transitioning from CLI to service-based architecture.

### Current Development Phase

**Phase**: Service Foundation (M0-M1)
**Focus**: Building the REST/WebSocket API layer and display event recovery
**Priority Areas**: See [Refactoring Plan](docs/04_refactoring_plan.md) for current sprint

### High-Priority Contribution Areas

Based on the [PRD Priority Matrix](docs/02_prd.md#7-feature-prioritisation-matrix):

**Priority 0 (MVP — needed for beta release)**
- Service daemon with auto-start (RF-06 through RF-09)
- Display event recovery (RF-07, RF-08)
- REST/WebSocket API implementation (RF-09)
- Electron UI basic controls (Phase 3)

**Priority 1 (v1.1 — within 60 days of MVP)**
- Profile system implementation (RF-11)
- Gradient engine for addressable LEDs (RF-13)
- Device capability detection (RF-12)
- System tray integration

**Documentation improvements**
- Always welcome, especially:
  - Missing troubleshooting scenarios
  - Platform-specific setup guides
  - Performance tuning examples
  - Architecture clarifications

### Development Setup

```bash
# Clone repository
git clone https://github.com/user/ambilight-desktop.git
cd ambilight-desktop

# Install development dependencies
pip install -r requirements.txt -r requirements-dev.txt

# Run tests
pytest

# Run with debug logging
python main.py --debug
```

### Running Tests

```bash
# Run all tests
pytest

# Run with coverage
pytest --cov=ambilight --cov-report=html

# Run specific test file
pytest tests/unit/test_color.py

# Run integration tests (requires test fixtures)
pytest tests/integration/
```

### Code Quality

This project uses:
- **ruff**: Linting and formatting
- **mypy**: Static type checking
- **pytest**: Testing framework

Run quality checks before submitting:
```bash
ruff check .
mypy ambilight/
pytest
```

### Submitting Changes

1. Fork the repository
2. Create a feature branch (`git checkout -b feature/my-feature`)
3. Make your changes with tests
4. Run quality checks
5. Commit with descriptive messages
6. Push to your fork
7. Open a Pull Request

**PR Checklist**:
- [ ] Tests pass (`pytest`)
- [ ] Type checking passes (`mypy ambilight/`)
- [ ] Linting passes (`ruff check .`)
- [ ] Documentation updated if needed
- [ ] CHANGELOG.md updated for user-facing changes

### Questions or Help?

- Open an issue for bugs or feature requests
- Check existing issues before creating duplicates
- Provide system information (OS, Python version, hardware) for bugs
- Include relevant logs (set `AMBILIGHT_LOG_LEVEL=DEBUG`)
```


## Implementation Guidance

### Content Migration Strategy

When implementing the README update:

1. **Preserve Existing Content**: Keep all current technical content (troubleshooting, commands, architecture) that remains accurate
2. **Add Structure**: Insert section headers and navigation aids
3. **Add Status Indicators**: Mark sections as current (✅) or planned (🚧/📅)
4. **Add Vision Content**: Insert product vision, persona descriptions, roadmap
5. **Add Documentation Index**: Create the docs/ reference section
6. **Add Contributing Guide**: Insert contribution guidelines
7. **Verify Accuracy**: Run validation scripts to check commands and configs

### Phased Rollout

The README update can be implemented in phases:

**Phase 1: Structure and Status** (Low risk)
- Add section headers with status indicators
- Add table of contents
- Add persona-based navigation callouts
- Mark current vs planned sections

**Phase 2: Vision Content** (Medium priority)
- Add product vision statement
- Add user persona descriptions
- Add development status indicator
- Add roadmap table

**Phase 3: Planned Architecture** (High value)
- Add service architecture section
- Add planned architecture diagram
- Add roadmap details with milestone links
- Add migration path explanation

**Phase 4: Documentation Index** (High value)
- Create annotated docs/ file listing
- Add purpose descriptions
- Add quick reference by goal section

**Phase 5: Contributing Guide** (Community value)
- Add development phase indicator
- Add priority contribution areas
- Add development setup instructions
- Add testing instructions

### Content Maintenance

To keep the README accurate over time:

**On Code Changes**:
- Update module references if files are renamed/moved
- Update architecture diagrams if component relationships change
- Update configuration examples if AppConfig schema changes

**On Roadmap Progress**:
- Update milestone status (🚧 → ✅) when features ship
- Update "Current Phase" indicator
- Move completed features from "Planned" to "Current" sections

**On Release**:
- Update version badges
- Update platform support status
- Update performance characteristics if benchmarks change
- Run full validation suite before tagging release


### Validation Automation

Create automation scripts to validate README accuracy:

**scripts/validate-readme.sh**:
```bash
#!/bin/bash
set -e

echo "Validating README.md..."

# 1. Check internal links
python scripts/validate-readme-links.py

# 2. Verify command syntax
python scripts/validate-readme-commands.py

# 3. Validate config examples
python scripts/validate-readme-config.py

# 4. Check module references
python scripts/check-module-references.py

# 5. Verify readability standards
python scripts/check-readme-readability.py

echo "✅ All README validations passed"
```

Add this to CI pipeline:

**.github/workflows/readme-validation.yml**:
```yaml
name: README Validation

on:
  pull_request:
    paths:
      - 'README.md'
      - 'docs/**'
      - 'ambilight/**'
      - 'configuration.yaml'

jobs:
  validate:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v3
      - uses: actions/setup-python@v4
        with:
          python-version: '3.12'
      - name: Install dependencies
        run: |
          pip install -r requirements.txt
          pip install pyyaml requests
      - name: Validate README
        run: bash scripts/validate-readme.sh
```


## Requirements Traceability

This section maps design components to requirements:

| Requirement | Design Component | Implementation |
|-------------|------------------|----------------|
| Req 1: Communicate Product Vision | Product Vision Section, Persona Descriptions | Header content with vision statement and persona summaries |
| Req 2: Describe Service Architecture | Planned Architecture Section | Service architecture diagram, API description, lifecycle explanation |
| Req 3: Document Current Capabilities | Current Implementation Section | Preserve and enhance existing README content with status indicators |
| Req 4: Clarify Development Roadmap | Roadmap Table, Milestone Status | Roadmap table with milestone links to PRD |
| Req 5: Organize for Multiple Audiences | Layered Information Architecture, Navigation Callouts | Table of contents, persona navigation, progressive disclosure |
| Req 6: Maintain Technical Accuracy | Validation Scripts, Manual Checklist | Command verification, config validation, architecture diagram checks |
| Req 7: Reference Comprehensive Documentation | Documentation Index Section | Annotated docs/ listing with purpose descriptions |
| Req 8: Present Platform Support Information | Platform Support Table | Current and planned platform matrix with backend availability |
| Req 9: Update Setup Instructions | Installation Section | Preserve and verify current installation steps |
| Req 10: Preserve Parser Round-Trip | Configuration Section | Document atomic writes and round-trip guarantee |
| Req 11: Include Contribution Guidelines | Contributing Section | Development phase, priority areas, setup instructions |
| Req 12: License and Contact | License Section, Issue Guidelines | MIT license statement, issue reporting guidance |


## Success Criteria

The README update is successful when:

### Functional Success Criteria

1. **All 12 requirements are addressed** with verifiable implementation
2. **Validation scripts pass** without errors on the updated README
3. **All internal links are valid** and navigate to correct targets
4. **All code examples are runnable** or clearly marked as pseudo-code
5. **All configuration examples match AppConfig schema** exactly
6. **Platform support table matches PRD NFR-C requirements**

### User Experience Success Criteria

1. **First-time visitors can understand the project scope** within 2 minutes of reading
2. **Users can distinguish current from planned features** without confusion
3. **Each persona can find relevant information** via navigation callouts
4. **Installation instructions work** on a clean system without errors
5. **Troubleshooting covers common issues** from user reports

### Technical Quality Criteria

1. **No broken links** (internal or external)
2. **No invalid code examples** (syntax errors, non-existent modules)
3. **No configuration drift** (all examples match actual schema)
4. **Proper markdown formatting** (tables, headers, code blocks)
5. **Reasonable line lengths** (<120 chars for prose)

### Maintenance Criteria

1. **Validation scripts are integrated into CI** pipeline
2. **Manual review checklist exists** and is used
3. **Content maintenance procedures documented** for future updates
4. **Phase-based update strategy** allows incremental improvements


## Open Questions and Decisions

### Badge Selection

**Question**: Which status badges should be included in the header?

**Options**:
1. Minimal: License + Python version only
2. Standard: License + Python version + Build status
3. Comprehensive: License + Python version + Build status + Coverage + Version

**Recommendation**: Standard set initially. Add comprehensive badges after CI/CD is fully configured.

### Diagram Format

**Question**: Should we use ASCII art or Mermaid diagrams?

**Options**:
1. ASCII art (current approach)
   - ✅ Renders everywhere (GitHub, terminal, editors)
   - ✅ No external dependencies
   - ❌ Harder to modify
   - ❌ Limited visual appeal

2. Mermaid diagrams
   - ✅ More professional appearance
   - ✅ Easier to modify
   - ✅ GitHub renders automatically
   - ❌ Doesn't render in terminal or basic editors
   - ❌ More verbose source

**Recommendation**: Keep ASCII art for compatibility, but consider Mermaid for the planned service architecture diagram since it's more complex.

### Persona Depth

**Question**: How detailed should persona descriptions be in the README?

**Options**:
1. Minimal: One-line summary per persona
2. Medium: Name + needs + values (2-3 lines each)
3. Full: Complete persona profiles from PRD

**Recommendation**: Medium detail in README, link to PRD for full profiles. Balances informativeness with README length.

### Version Badging Strategy

**Question**: When should version badges reflect "v0.x" vs "v1.0"?

**Decision**: README should show current version from pyproject.toml. Development status indicator ("🚧 Current Phase: CLI Implementation") provides transparency about maturity.


## Summary

This design document specifies a comprehensive update to the Ambilight Desktop README.md that serves multiple user personas while clearly distinguishing current CLI capabilities from the planned service-based architecture.

### Key Design Principles

1. **Progressive Disclosure**: Information organized in layers from immediate value to deep technical reference
2. **Dual Timeline Communication**: Clear visual distinction between current (✅) and planned (🚧/📅) features
3. **Persona-Based Navigation**: Explicit pathways for different reader goals
4. **Technical Accuracy**: Validation scripts ensure all examples match actual implementation
5. **Comprehensive Referencing**: Every major concept links to detailed documentation in docs/

### Implementation Approach

The design enables phased implementation:
- **Phase 1**: Add structure and status indicators (low risk)
- **Phase 2-3**: Add vision and planned architecture content (high value)
- **Phase 4-5**: Add documentation index and contributing guidelines

### Quality Assurance

Documentation quality is maintained through:
- **Automated validation**: Link checking, command verification, config validation
- **Manual review checklist**: Visual consistency, content accuracy, navigation
- **CI integration**: Automated checks on every pull request
- **Maintenance procedures**: Update triggers and content freshness guidelines

### Testing Strategy

Since this is documentation, testing focuses on:
- Link validity (internal and external)
- Command syntax verification
- Configuration example validation against AppConfig schema
- Readability and accessibility standards
- Integration testing of quick-start workflow

This design satisfies all 12 requirements from the requirements document and provides a maintainable foundation for keeping the README accurate as the project evolves from CLI to service architecture.
