import type { Config } from "tailwindcss";

const config: Config = {
  content: [
    "./app/**/*.{js,ts,jsx,tsx,mdx}",
    "./components/**/*.{js,ts,jsx,tsx,mdx}",
    "./lib/**/*.{js,ts,jsx,tsx,mdx}",
  ],
  theme: {
    extend: {
      colors: {
        base: {
          900: "#0a0e14",
          850: "#0f141c",
          800: "#141b26",
          750: "#1a2230",
          700: "#212b3b",
          600: "#2c384c",
        },
        accent: {
          DEFAULT: "#38bdf8",
        },
        profit: "#22c55e",
        loss: "#ef4444",
      },
      fontFamily: {
        mono: ["ui-monospace", "SFMono-Regular", "Menlo", "Monaco", "monospace"],
      },
    },
  },
  plugins: [],
};

export default config;
