/** @type {import('tailwindcss').Config} */
export default {
  content: ['./index.html', './src/**/*.{js,jsx}'],
  darkMode: ['selector', '[data-theme="dark"]'],
  theme: {
    extend: {
      colors: {
        primary: {
          DEFAULT: '#5567d5',
          dark: '#764ba2',
        },
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
        // ── shadcn/ui tokens, mapped onto FLT's semantic vars so shadcn
        // components (button, progress, …) blend with the dark theme.
        background: 'rgb(var(--bg-app) / <alpha-value>)',
        foreground: 'rgb(var(--content) / <alpha-value>)',
        card: 'rgb(var(--surface-overlay) / <alpha-value>)',
        'card-foreground': 'rgb(var(--content) / <alpha-value>)',
        popover: 'rgb(var(--surface-overlay) / <alpha-value>)',
        'popover-foreground': 'rgb(var(--content) / <alpha-value>)',
        'primary-foreground': '#ffffff',
        secondary: 'rgb(var(--surface-raised) / <alpha-value>)',
        'secondary-foreground': 'rgb(var(--content) / <alpha-value>)',
        muted: 'rgb(var(--surface-raised) / <alpha-value>)',
        'muted-foreground': 'rgb(var(--content-muted) / <alpha-value>)',
        accent: 'rgb(var(--surface-raised) / <alpha-value>)',
        'accent-foreground': 'rgb(var(--content) / <alpha-value>)',
        destructive: '#ef4444',
        'destructive-foreground': '#ffffff',
        input: 'rgb(var(--border-strong) / <alpha-value>)',
        ring: '#5567d5',
        sidebar: 'rgb(var(--surface-overlay) / <alpha-value>)',
        'sidebar-foreground': 'rgb(var(--content) / <alpha-value>)',
        'sidebar-primary': '#5567d5',
        'sidebar-primary-foreground': '#ffffff',
        'sidebar-accent': 'rgb(var(--surface-raised) / <alpha-value>)',
        'sidebar-accent-foreground': 'rgb(var(--content) / <alpha-value>)',
        'sidebar-border': 'rgb(var(--border-strong) / <alpha-value>)',
        'sidebar-ring': '#5567d5',
        'chart-1': '#5567d5',
        'chart-2': '#764ba2',
        'chart-3': '#22d3ee',
        'chart-4': '#f59e0b',
        'chart-5': '#ef4444',
      },
      backgroundImage: {
        'gradient-primary': 'linear-gradient(135deg, #5567d5 0%, #764ba2 100%)',
      },
    },
  },
  plugins: [],
}
