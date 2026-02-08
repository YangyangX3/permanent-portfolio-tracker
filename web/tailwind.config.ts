import type { Config } from "tailwindcss";

export default {
  content: ["./src/**/*.{ts,tsx}"],
  theme: {
    extend: {
      colors: {
        paper: "hsl(var(--paper))",
        ink: "hsl(var(--ink))",
        muted: "hsl(var(--muted))",
        wash: "hsl(var(--wash))",
        ring: "hsl(var(--ring))",
        accent: "hsl(var(--accent))",
        stamp: "hsl(var(--stamp))",
        danger: "hsl(var(--danger))",
        ok: "hsl(var(--ok))"
      },
      boxShadow: {
        card: "0 10px 30px rgba(0,0,0,.10)",
        lifted: "0 18px 60px rgba(0,0,0,.16)"
      },
      borderRadius: {
        xl: "18px",
        "2xl": "22px"
      }
    }
  },
  plugins: []
} satisfies Config;

