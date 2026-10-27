/** @type {import('tailwindcss').Config} */
export default {
  content: ["./index.html", "./src/**/*.{ts,tsx}"],
  theme: {
    extend: {
      colors: {
        // 品牌主色（indigo→violet 家族，對白底達 AA 對比）
        brand: {
          50: "#eef2ff", 100: "#e0e7ff", 200: "#c7d2fe", 300: "#a5b4fc",
          400: "#818cf8", 500: "#6366f1", 600: "#4f46e5", 700: "#4338ca",
          800: "#3730a3", 900: "#312e81", 950: "#1e1b4b",
        },
      },
      fontFamily: {
        sans: ["Inter", "Noto Sans TC", "system-ui", "-apple-system", "Segoe UI", "sans-serif"],
        display: ["Inter", "Noto Sans TC", "system-ui", "sans-serif"],
      },
      borderRadius: { xl2: "1rem" },
      boxShadow: {
        card: "0 1px 2px 0 rgb(15 23 42 / 0.04), 0 1px 3px 0 rgb(15 23 42 / 0.06)",
        cardHover: "0 12px 28px -8px rgb(15 23 42 / 0.16)",
        glow: "0 0 0 1px rgb(99 102 241 / 0.18), 0 24px 60px -16px rgb(79 70 229 / 0.45)",
      },
      keyframes: {
        "pulse-node": {
          "0%": { boxShadow: "0 0 0 0 rgb(129 140 248 / 0.55)" },
          "70%": { boxShadow: "0 0 0 7px rgb(129 140 248 / 0)" },
          "100%": { boxShadow: "0 0 0 0 rgb(129 140 248 / 0)" },
        },
        "fade-in-up": {
          from: { opacity: "0", transform: "translateY(8px)" },
          to: { opacity: "1", transform: "none" },
        },
        shimmer: {
          "100%": { transform: "translateX(100%)" },
        },
        dash: {
          to: { strokeDashoffset: "0" },
        },
      },
      animation: {
        "pulse-node": "pulse-node 1.6s ease-out infinite",
        "fade-in-up": "fade-in-up 0.4s ease-out both",
        shimmer: "shimmer 1.5s infinite",
        dash: "dash 0.9s linear infinite",
      },
    },
  },
  plugins: [],
}
