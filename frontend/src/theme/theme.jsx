/**
 * Theme clair / sombre, choisi par un interrupteur.
 *
 * Deux etats seulement. Au premier acces, rien n'est memorise : la position
 * initiale reprend la preference du systeme d'exploitation. Des que
 * l'utilisateur actionne l'interrupteur, son choix est enregistre et prevaut.
 *
 * Le meme calcul est fait par un court script dans index.html, AVANT le
 * premier affichage : sans lui, la page apparaitrait un instant dans le
 * mauvais theme.
 */

import { createContext, useCallback, useContext, useMemo, useRef, useState } from "react";

import { IconeLune, IconeSoleil } from "../components/icones";

const CLE_THEME = "sentinel-theme";

const ContexteTheme = createContext(null);

function themeMemorise() {
  try {
    const valeur = window.localStorage.getItem(CLE_THEME);
    return valeur === "clair" || valeur === "sombre" ? valeur : null;
  } catch {
    // Stockage indisponible (navigation privee stricte) : on suit le systeme.
    return null;
  }
}

function themeDuSysteme() {
  return window.matchMedia?.("(prefers-color-scheme: light)").matches ? "clair" : "sombre";
}

export function FournisseurTheme({ children }) {
  const [theme, setTheme] = useState(() => {
    const initial = document.documentElement.dataset.theme || themeMemorise() || themeDuSysteme();
    document.documentElement.dataset.theme = initial;
    return initial;
  });
  const themeCourant = useRef(theme);

  // L'attribut est pose AVANT la mise a jour de l'etat, et non dans un
  // effet : les effets des composants enfants (graphiques qui relisent les
  // couleurs du theme) s'executent avant ceux du fournisseur, et liraient
  // encore les couleurs de l'ancien theme.
  const basculer = useCallback(() => {
    const suivant = themeCourant.current === "sombre" ? "clair" : "sombre";
    themeCourant.current = suivant;
    document.documentElement.dataset.theme = suivant;
    try {
      window.localStorage.setItem(CLE_THEME, suivant);
    } catch {
      // Stockage indisponible : le choix vaut pour la session en cours.
    }
    setTheme(suivant);
  }, []);

  const valeur = useMemo(() => ({ theme, basculer }), [theme, basculer]);

  return <ContexteTheme.Provider value={valeur}>{children}</ContexteTheme.Provider>;
}

export function useTheme() {
  const contexte = useContext(ContexteTheme);
  if (!contexte) {
    throw new Error("useTheme doit etre utilise dans un FournisseurTheme.");
  }
  return contexte;
}

/**
 * Interrupteur a deux positions. role="switch" : un lecteur d'ecran annonce
 * "Theme sombre, interrupteur, active / desactive".
 */
export function InterrupteurTheme({ className = "" }) {
  const { theme, basculer } = useTheme();
  const sombre = theme === "sombre";

  return (
    <button
      type="button"
      role="switch"
      aria-checked={sombre}
      aria-label="Thème sombre"
      title={sombre ? "Passer au thème clair" : "Passer au thème sombre"}
      className={`interrupteur-theme ${className}`}
      onClick={basculer}
    >
      <span className="interrupteur-theme-piste" aria-hidden="true">
        <span className="interrupteur-theme-pastille">
          {sombre ? <IconeLune taille={12} /> : <IconeSoleil taille={12} />}
        </span>
      </span>
    </button>
  );
}
