import path from "path";
import { defineConfig } from "vite";
import react from "@vitejs/plugin-react";

export default defineConfig({
  plugins: [react()],
  resolve: {
    alias: {
      "@shared": path.resolve(__dirname, "../shared"),
    },
  },
  server: {
    host: "0.0.0.0",
    port: 5173,
    fs: {
      allow: [
        path.resolve(__dirname),
        path.resolve(__dirname, ".."),
        path.resolve(__dirname, "../shared"),
      ],
    },
  },
  build: {
    chunkSizeWarningLimit: 750,
    rollupOptions: {
      output: {
        manualChunks(id) {
          if (!id.includes("node_modules")) {
            return undefined;
          }
          if (id.includes("/node_modules/three/")) {
            return "three-core";
          }
          if (id.includes("@react-three/fiber")) {
            return "fiber-vendor";
          }
          if (
            id.includes("@react-three/drei") ||
            id.includes("camera-controls") ||
            id.includes("three-mesh-bvh") ||
            id.includes("meshline") ||
            id.includes("maath")
          ) {
            return "drei-vendor";
          }
          if (id.includes("react-router-dom")) {
            return "router-vendor";
          }
          return undefined;
        },
      },
    },
  },
});
