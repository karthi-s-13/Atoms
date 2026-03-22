/** @type {import('tailwindcss').Config} */
export default {
  content: ["./index.html", "./src/**/*.{js,jsx}"],
  theme: {
    extend: {
      colors: {
        canvas: "#06111f",
        panel: "#0e1b2d",
        border: "rgba(148, 163, 184, 0.18)",
        accent: "#22d3ee",
        success: "#22c55e",
        warning: "#f59e0b",
        danger: "#f87171",
      },
      boxShadow: {
        glow: "0 18px 60px rgba(8, 47, 73, 0.35)",
      },
      backgroundImage: {
        "hero-grid":
          "radial-gradient(circle at top, rgba(34,211,238,0.12), transparent 36%), linear-gradient(180deg, rgba(8,15,28,0.92), rgba(4,10,20,1))",
      },
    },
  },
  plugins: [],
};
