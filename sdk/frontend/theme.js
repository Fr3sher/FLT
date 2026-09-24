// Public LDS theme preset v1. Utilities only; the host owns reset and fonts.
const safelight = {
  50: '#FBF3E7',
  100: '#F6E6CE',
  200: '#EFD0A0',
  300: '#E9B366',
  400: '#E59A3C',
  500: '#E1861F',
  600: '#C06E10',
  700: '#9C580D',
  800: '#78440B',
  900: '#573208',
  950: '#382004',
}

export default {
  // The bundled plugins' screens (bundled/<id>/frontend/) use this package's
  // Tailwind like the core's own files — their classes must be generated too,
  // or a class only a plugin uses silently renders unstyled.
  content: [],
  corePlugins: { preflight: false },
  darkMode: ['selector', '[data-theme="dark"]'],
  theme: {
    extend: {
      fontFamily: {
        sans: ['Archivo', 'ui-sans-serif', 'system-ui', 'sans-serif'],
        mono: ['"IBM Plex Mono"', 'ui-monospace', 'monospace'],
      },
      colors: {
        primary: {
          DEFAULT: safelight[500],
          dark: safelight[600],
        },
        indigo: safelight,
        // ── Semantic theme tokens (backed by CSS vars in index.css) ──────────
        // App is dark-only. The *-alpha-baked tokens (surface, surface-raised,
        // border, border-strong) carry CSS-var-controlled default opacity.
        // Use the *-solid variants when you need to set your own alpha via
        // Tailwind's /NN modifier.
        app: 'rgb(var(--bg-app) / <alpha-value>)',
        surface: 'rgb(var(--surface) / var(--surface-alpha))',
        'surface-raised': 'rgb(var(--surface-raised) / var(--surface-raised-alpha))',
        'surface-overlay': 'rgb(var(--surface-overlay) / <alpha-value>)',
        'surface-solid': 'rgb(var(--surface-overlay) / <alpha-value>)',
        content: 'rgb(var(--content) / <alpha-value>)',
        'content-muted': 'rgb(var(--content-muted) / <alpha-value>)',
        'content-subtle': 'rgb(var(--content-subtle) / <alpha-value>)',
        border: 'rgb(var(--border) / var(--border-alpha))',
        'border-strong': 'rgb(var(--border-strong) / var(--border-strong-alpha))',
      },
      backgroundImage: {
        // Kept as a (near-flat) gradient so all existing `bg-gradient-primary`
        // call sites keep working — the tight amber ramp gives buttons a hint
        // of depth without reading as a two-hue gradient.
        'gradient-primary': `linear-gradient(135deg, ${safelight[500]} 0%, ${safelight[600]} 100%)`,
      },
    },
  },
  plugins: [],
}
