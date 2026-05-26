/** @type {import('tailwindcss').Config} */
export default {
  content: ['./index.html', './src/**/*.{ts,tsx}'],
  theme: {
    extend: {
      colors: {
        bg: {
          DEFAULT: '#0f1115',
          panel: '#161922',
          card: '#1c2030',
          hover: '#232838',
        },
        line: '#2a2f3f',
        text: {
          DEFAULT: '#e6e8ee',
          muted: '#9aa1b2',
          dim: '#6b7280',
        },
        brand: {
          DEFAULT: '#7c9cff',
          hover: '#94afff',
        },
        conf: {
          high: '#22c55e',
          medium: '#eab308',
          low: '#f97316',
          uncertain: '#ef4444',
        },
        status: {
          pending: '#a78bfa',
          needs: '#f59e0b',
          approved: '#22c55e',
          rejected: '#ef4444',
        },
      },
      fontFamily: {
        sans: ['Inter', 'system-ui', '-apple-system', 'Segoe UI', 'Roboto', 'sans-serif'],
        mono: ['ui-monospace', 'SFMono-Regular', 'Menlo', 'monospace'],
      },
    },
  },
  plugins: [],
};

