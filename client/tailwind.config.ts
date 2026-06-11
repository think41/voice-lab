import type { Config } from 'tailwindcss';

export default {
  content: ['./index.html', './src/**/*.{ts,tsx}'],
  theme: {
    extend: {
      colors: {
        navy: '#0A1628',
        navy2: '#111F3A',
        primary: '#1E6FFF',
        off: '#F4F6FA',
        off2: '#EBEEF5',
        line: '#D6DCEB',
        text: '#0A1628',
        muted: '#4A5578',
        faint: '#8892AA',
        success: '#12B76A',
        warning: '#F79009',
        danger: '#F04438',
        purple: '#7C3AED'
      },
      fontFamily: {
        sans: ['Inter', 'ui-sans-serif', 'system-ui'],
        mono: ['JetBrains Mono', 'ui-monospace', 'SFMono-Regular']
      },
      boxShadow: {
        soft: '0 1px 3px rgba(10,22,40,0.08), 0 1px 2px rgba(10,22,40,0.04)',
        panel: '0 4px 12px rgba(10,22,40,0.10), 0 2px 4px rgba(10,22,40,0.06)'
      }
    }
  },
  plugins: []
} satisfies Config;
