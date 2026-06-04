import forms from '@tailwindcss/forms'
import containerQueries from '@tailwindcss/container-queries'

/** @type {import('tailwindcss').Config} */
export default {
  content: ['./index.html', './src/**/*.{js,jsx}'],
  theme: {
    extend: {
      colors: {
        'deep-navy': '#0a0c1a',
        'card-bg': 'rgba(23, 27, 48, 0.6)',
        'brand-purple': '#8b5cf6',
        'brand-blue': '#3b82f6',
        'brand-indigo': '#6366f1',
        'brand-violet': '#a855f7',
        'accent-red': '#ef4444',
      },
      fontFamily: {
        sans: ['Inter', 'sans-serif'],
        mono: ['JetBrains Mono', 'monospace'],
      },
    },
  },
  plugins: [forms, containerQueries],
}
