import type { Config } from "tailwindcss";

const config: Config = {
  content: [
    "./app/**/*.{ts,tsx}",
    "./components/**/*.{ts,tsx}",
  ],
  theme: {
    extend: {
      colors: {
        // "Chart" palette — warm parchment + deep ink, a clinical teal signal
        // accent, ember for in-progress/attention, brick reserved for alerts.
        ink: {
          25: "#FDFBF7",
          50: "#F7F4EE",
          100: "#EFEAE0",
          200: "#DFD8C9",
          300: "#C3B9A6",
          400: "#9C9284",
          500: "#75726A",
          600: "#565650",
          700: "#3D3F3A",
          800: "#26302C",
          900: "#182420",
        },
        teal: {
          50: "#EAF5F1",
          100: "#CFE9E0",
          200: "#9FD3C1",
          300: "#69B7A0",
          400: "#3B9682",
          500: "#0C6B57",
          600: "#0A5A49",
          700: "#08493B",
          800: "#06392E",
          900: "#042A22",
        },
        ember: {
          50: "#FBF1E7",
          100: "#F4DEC4",
          200: "#E9BE8C",
          300: "#DB9C5C",
          400: "#C98338",
          500: "#B8722E",
          600: "#9C5F26",
          700: "#7D4C1F",
          800: "#5F3A18",
          900: "#432912",
        },
        brick: {
          50: "#FBECE8",
          100: "#F3D2C9",
          200: "#E5A797",
          300: "#D37D68",
          400: "#BF5B45",
          500: "#A83F2E",
          600: "#8C3325",
          700: "#70281D",
          800: "#541E16",
          900: "#3A150F",
        },
      },
      fontFamily: {
        sans: ["var(--font-sans)", "ui-sans-serif", "system-ui", "sans-serif"],
        serif: ["var(--font-serif)", "ui-serif", "Georgia", "serif"],
        mono: ["var(--font-mono)", "ui-monospace", "SFMono-Regular", "Menlo", "monospace"],
      },
    },
  },
  plugins: [],
};

export default config;
