/** @type {import('tailwindcss').Config} */
export default {
  darkMode: "class",
  content: ["./index.html", "./src/**/*.{ts,tsx}"],
  theme: {
    extend: {
      fontFamily: {
        // Geist — clean high-end grotesk (no Inter). Mono for numeric data.
        sans: ["Geist Variable", "ui-sans-serif", "system-ui", "sans-serif"],
        mono: ["Geist Mono Variable", "ui-monospace", "SFMono-Regular", "monospace"],
      },
      colors: {
        // Single, slightly-desaturated accent (emerald). No AI-purple.
        accent: {
          DEFAULT: "#10b981",
          soft: "#34d399",
          deep: "#059669",
        },
        // Secondary text tones that actually clear WCAG AA (4.5:1) against the
        // zinc-950 page. Tailwind's zinc-500 measures 4.12:1 and zinc-600 only
        // 2.57:1, so those were failing wherever they carried real text.
        // Keeping two steps preserves the visual hierarchy the design relies on.
        muted: "#8b8b96", // 5.4:1  — secondary text (was text-zinc-500)
        subtle: "#7a7a85", // 4.6:1  — tertiary text/placeholders (was text-zinc-600)
      },
      transitionTimingFunction: {
        // Premium spring-ish curves — never linear/ease-in-out.
        smooth: "cubic-bezier(0.32, 0.72, 0, 1)",
        entrance: "cubic-bezier(0.16, 1, 0.3, 1)",
      },
      keyframes: {
        "fade-up": {
          "0%": { opacity: "0", transform: "translateY(8px)" },
          "100%": { opacity: "1", transform: "translateY(0)" },
        },
        blink: {
          "0%, 100%": { opacity: "1" },
          "50%": { opacity: "0" },
        },
        shimmer: {
          "100%": { transform: "translateX(100%)" },
        },
      },
      animation: {
        "fade-up": "fade-up 0.4s cubic-bezier(0.16, 1, 0.3, 1)",
        blink: "blink 1s step-start infinite",
      },
    },
  },
  plugins: [],
};
