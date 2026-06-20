#!/usr/bin/env node

/**
 * Sync VERSION file to ui/package.json
 *
 * This script reads the VERSION file at the repo root and updates
 * ui/package.json so both Python service and Electron UI use the
 * same version number (single source of truth).
 *
 * Run before building: `node scripts/sync-version.mjs`
 */

import { readFileSync, writeFileSync } from 'fs';
import { resolve } from 'path';
import { fileURLToPath } from 'url';

const __dirname = fileURLToPath(new URL('.', import.meta.url));
const repoRoot = resolve(__dirname, '..');
const versionFile = resolve(repoRoot, 'VERSION');
const packageJsonFile = resolve(repoRoot, 'ui', 'package.json');

// Read VERSION file
const version = readFileSync(versionFile, 'utf-8').trim();
if (!version) {
  console.error('❌ VERSION file is empty');
  process.exit(1);
}

// Validate semver format (basic check)
if (!/^\d+\.\d+\.\d+$/.test(version)) {
  console.error(`❌ Invalid version format in VERSION file: ${version}`);
  console.error('   Expected format: X.Y.Z (semver)');
  process.exit(1);
}

// Read package.json
const packageJson = JSON.parse(readFileSync(packageJsonFile, 'utf-8'));
const oldVersion = packageJson.version;

// Update version
packageJson.version = version;

// Write package.json back
writeFileSync(packageJsonFile, JSON.stringify(packageJson, null, 2) + '\n', 'utf-8');

if (oldVersion === version) {
  console.log(`✓ Version already in sync: ${version}`);
} else {
  console.log(`✓ Version synced: ${oldVersion} → ${version}`);
}
