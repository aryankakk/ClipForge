import type { Config } from 'tailwindcss';

const config: Config = {
  content: ['./src/**/*.{js,ts,jsx,tsx,mdx}'],
  theme: {
    extend: {
      colors: {
        'forge-bg': 'var(--forge-bg)',
        'forge-surface': 'var(--forge-surface)',
        'forge-border': 'var(--forge-border)',
        'forge-text': 'var(--forge-text)',
        'forge-muted': 'var(--forge-muted)',
        'forge-accent': 'var(--forge-accent)',
        'forge-green': 'var(--forge-green)',
        'forge-red': 'var(--forge-red)',
        'forge-amber': 'var(--forge-amber)',
      },
      fontFamily: {
        display: ['Syne', 'system-ui', 'sans-serif'],
        mono: ['"Space Mono"', 'monospace'],
      },
    },
  },
  plugins: [],
};

export default config;
