import { defineConfig } from "vite";
import react from "@vitejs/plugin-react";

/**
 * Le build sort dans frontend/dist, servi tel quel par Flask en production
 * (aucun Node n'est requis sur la VM de collecte).
 *
 * En developpement, /api et les telechargements servis par Flask sont
 * relayes vers le serveur Flask local. Le navigateur ne voit donc qu'une
 * seule origine : le cookie de session suit naturellement et AUCUNE
 * configuration CORS n'est necessaire de part et d'autre.
 */
export default defineConfig({
  plugins: [react()],
  server: {
    port: 5173,
    proxy: {
      "/api": { target: "http://127.0.0.1:5000", changeOrigin: true },
      "/reports": { target: "http://127.0.0.1:5000", changeOrigin: true },
      "/compliance": { target: "http://127.0.0.1:5000", changeOrigin: true },
      "/static": { target: "http://127.0.0.1:5000", changeOrigin: true },
    },
  },
  build: {
    outDir: "dist",
    emptyOutDir: true,
    rollupOptions: {
      output: {
        // Recharts pese a lui seul plus que tout le reste de
        // l'application et ne sert qu'au tableau de bord. L'isoler evite
        // que chaque deploiement n'invalide un unique gros fichier dans
        // le cache du navigateur.
        manualChunks: {
          react: ["react", "react-dom", "react-router-dom"],
          graphiques: ["recharts"],
        },
      },
    },
  },
});
