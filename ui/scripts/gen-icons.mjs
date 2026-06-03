/**
 * gen-icons.mjs
 * =============
 * Rasterize the brand mark (public/favicon.svg) into the PNGs electron-builder
 * and the Electron runtime need:
 *
 *   build/icon.png            1024×1024 — app icon; electron-builder auto-derives
 *                             .ico (Windows) and .icns (macOS) from this.
 *   electron/assets/icon.png  256×256   — tray icon + BrowserWindow icon.
 *
 * The mark is centred on a transparent square canvas with a little padding so it
 * reads well at small tray sizes. Run via `pnpm run gen:icons` (invoked before
 * every build).
 */

import { fileURLToPath } from 'node:url'
import { dirname, join } from 'node:path'
import { mkdirSync, existsSync } from 'node:fs'
import sharp from 'sharp'

const __dirname = dirname(fileURLToPath(import.meta.url))
const UI_ROOT = join(__dirname, '..')
const SRC_SVG = join(UI_ROOT, 'public', 'favicon.svg')

const TARGETS = [
  { out: join(UI_ROOT, 'build', 'icon.png'), size: 1024, pad: 0.14 },
  { out: join(UI_ROOT, 'electron', 'assets', 'icon.png'), size: 256, pad: 0.12 },
]

async function render({ out, size, pad }) {
  const dir = dirname(out)
  if (!existsSync(dir)) mkdirSync(dir, { recursive: true })

  // Render the SVG to an inner square, then composite it centred on a
  // transparent full-size canvas so there is breathing room around the glyph.
  const inner = Math.round(size * (1 - pad * 2))
  const glyph = await sharp(SRC_SVG, { density: 384 })
    .resize(inner, inner, { fit: 'contain', background: { r: 0, g: 0, b: 0, alpha: 0 } })
    .png()
    .toBuffer()

  await sharp({
    create: { width: size, height: size, channels: 4, background: { r: 0, g: 0, b: 0, alpha: 0 } },
  })
    .composite([{ input: glyph, gravity: 'center' }])
    .png()
    .toFile(out)

  console.log(`[gen-icons] wrote ${out} (${size}×${size})`)
}

if (!existsSync(SRC_SVG)) {
  console.error(`[gen-icons] source not found: ${SRC_SVG}`)
  process.exit(1)
}

for (const t of TARGETS) {
  await render(t)
}
console.log('[gen-icons] done')
