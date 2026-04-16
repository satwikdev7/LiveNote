import type { Config } from "tailwindcss";

const config: Config = {
  darkMode: "class",
  content: [
    "./app/**/*.{ts,tsx}",
    "./components/**/*.{ts,tsx}",
    "./hooks/**/*.{ts,tsx}",
  ],
  theme: {
    extend: {
      colors: {
        bg: "#F1F5F9",
        surface: "#FFFFFF",
        ink: "#0F172A",
        muted: "#64748B",
        accent: "#2563EB",
        recording: "#EF4444",
      },
      boxShadow: {
        card: "0 1px 3px 0 rgba(0,0,0,0.08), 0 1px 2px -1px rgba(0,0,0,0.08)",
      },
    },
  },
  plugins: [],
};

export default config;
