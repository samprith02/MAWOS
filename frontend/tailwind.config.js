/** @type {import('tailwindcss').Config} */
export default {
  content: ['./index.html', './src/**/*.{js,jsx}'],
  theme: {
    extend: {
      colors: {
        navy: '#0F172A', primary: '#2563EB', teal: '#0D9488',
        canvas: '#F8FAFC', line: '#E2E8F0', muted: '#64748B',
      },
      boxShadow: { card: '0 1px 3px rgb(15 23 42 / 0.08)' },
    },
  },
  plugins: [],
};
