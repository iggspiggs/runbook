/** @type {import('tailwindcss').Config} */
export default {
  content: [
    './index.html',
    './src/**/*.{js,jsx,ts,tsx}',
  ],
  theme: {
    extend: {
      colors: {
        // Sidebar / shell
        slate: {
          850: '#172033',
          950: '#0c1322',
        },
        // Department colors
        dept: {
          finance:    { DEFAULT: '#6366f1', light: '#eef2ff' },
          ops:        { DEFAULT: '#0ea5e9', light: '#f0f9ff' },
          hr:         { DEFAULT: '#8b5cf6', light: '#f5f3ff' },
          it:         { DEFAULT: '#14b8a6', light: '#f0fdfa' },
          sales:      { DEFAULT: '#f59e0b', light: '#fffbeb' },
          marketing:  { DEFAULT: '#ec4899', light: '#fdf2f8' },
          legal:      { DEFAULT: '#64748b', light: '#f8fafc' },
          default:    { DEFAULT: '#94a3b8', light: '#f8fafc' },
        },
        // Risk level colors
        risk: {
          low:      { DEFAULT: '#22c55e', bg: '#f0fdf4', text: '#15803d', border: '#bbf7d0' },
          medium:   { DEFAULT: '#f59e0b', bg: '#fffbeb', text: '#b45309', border: '#fde68a' },
          high:     { DEFAULT: '#f97316', bg: '#fff7ed', text: '#c2410c', border: '#fed7aa' },
          critical: { DEFAULT: '#ef4444', bg: '#fef2f2', text: '#b91c1c', border: '#fecaca' },
        },
        // Status colors
        status: {
          active:   { DEFAULT: '#22c55e', bg: '#f0fdf4', text: '#15803d', border: '#bbf7d0' },
          paused:   { DEFAULT: '#f59e0b', bg: '#fffbeb', text: '#b45309', border: '#fde68a' },
          planned:  { DEFAULT: '#3b82f6', bg: '#eff6ff', text: '#1d4ed8', border: '#bfdbfe' },
          deferred: { DEFAULT: '#94a3b8', bg: '#f8fafc', text: '#475569', border: '#e2e8f0' },
        },
      },
      fontFamily: {
        mono: ['JetBrains Mono', 'Fira Code', 'Cascadia Code', 'monospace'],
      },
      animation: {
        'slide-in-right': 'slideInRight 0.2s ease-out',
        'fade-in': 'fadeIn 0.2s ease-out',
        'pulse-once': 'pulse 0.6s ease-in-out 1',
      },
      keyframes: {
        slideInRight: {
          '0%': { transform: 'translateX(100%)', opacity: '0' },
          '100%': { transform: 'translateX(0)', opacity: '1' },
        },
        fadeIn: {
          '0%': { opacity: '0', transform: 'translateY(4px)' },
          '100%': { opacity: '1', transform: 'translateY(0)' },
        },
      },
      boxShadow: {
        'drawer': '-4px 0 24px -4px rgba(0,0,0,0.15)',
        'card': '0 1px 3px rgba(0,0,0,0.04), 0 1px 2px rgba(0,0,0,0.02)',
      },
    },
  },
  plugins: [],
}
