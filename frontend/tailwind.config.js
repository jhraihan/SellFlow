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
        sans: ["Inter", "system-ui", "Segoe UI", "sans-serif"],
        display: ["Instrument Serif", "Georgia", "Times New Roman", "serif"],
      },
      letterSpacing: {
        eyebrow: "0.18em",
      },
    },
  },
  plugins: [],
};
