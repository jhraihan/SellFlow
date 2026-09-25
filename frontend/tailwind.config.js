export default {
  content: ["./index.html", "./src/**/*.{js,jsx}"],
  theme: {
    extend: {
      colors: {
        brand: {
          50: "#FBF1C2",
          100: "#F6E6A0",
          500: "#6B6A55",
          600: "#3E3D32",
          700: "#23221C",
        },
        butter: {
          DEFAULT: "#F8E27A",
          deep: "#EFD24F",
          soft: "#FCF3C8",
        },
        olive: {
          DEFAULT: "#5C5B4A",
          deep: "#45443A",
          soft: "#8C8B77",
        },
        sand: {
          DEFAULT: "#EDE6D8",
          deep: "#DDD3C0",
        },
        clay: {
          DEFAULT: "#B98C66",
          soft: "#F1E3D6",
        },
        paper: "#F6F3EC",
        ink: "#1D1C18",
        muted: "#8B877A",
        line: "#E4DED2",
        surface: "#F6F3EC",
        ok: "#4E7A4F",
        warn: "#A8741A",
        danger: "#B0442F",
      },
      fontFamily: {
        sans: ["Plus Jakarta Sans", "Inter", "system-ui", "Segoe UI", "sans-serif"],
        display: ["Plus Jakarta Sans", "Inter", "system-ui", "sans-serif"],
      },
      letterSpacing: {
        eyebrow: "0.16em",
      },
      boxShadow: {
        soft: "0 1px 2px rgba(29, 28, 24, 0.04), 0 2px 8px -2px rgba(29, 28, 24, 0.05)",
        lift: "0 18px 40px -18px rgba(69, 68, 58, 0.35)",
        glow: "0 10px 30px -10px rgba(239, 210, 79, 0.65)",
      },
    },
  },
  plugins: [],
};
