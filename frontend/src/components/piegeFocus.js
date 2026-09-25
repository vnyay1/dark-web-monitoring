/**
 * Comportement commun des fenetres modales et du tiroir de navigation
 * (motif "dialog" de l'ARIA Authoring Practices) :
 *  - le focus reste DANS le conteneur (Tab et Maj+Tab bouclent) ;
 *  - Echap ferme ;
 *  - le defilement de la page d'arriere-plan est bloque ;
 *  - a la fermeture, le focus revient sur l'element qui a ouvert la fenetre.
 */

import { useEffect, useRef } from "react";

const FOCALISABLES = [
  "a[href]",
  "button:not([disabled])",
  "input:not([disabled]):not([type='hidden'])",
  "select:not([disabled])",
  "textarea:not([disabled])",
  "[tabindex]:not([tabindex='-1'])",
].join(",");

function elementsFocalisables(conteneur) {
  if (!conteneur) return [];
  return Array.from(conteneur.querySelectorAll(FOCALISABLES)).filter(
    (el) => el.offsetParent !== null || el === document.activeElement,
  );
}

/**
 * actif      : la fenetre est ouverte
 * conteneur  : ref vers l'element qui doit garder le focus
 * onEchap    : appele sur Echap (sauf si bloquerEchap)
 * focusInitial : ref facultative de l'element a focaliser a l'ouverture
 */
export function usePiegeFocus(actif, conteneur, { onEchap, bloquerEchap = false, focusInitial } = {}) {
  const onEchapRef = useRef(onEchap);
  onEchapRef.current = onEchap;
  const bloquerRef = useRef(bloquerEchap);
  bloquerRef.current = bloquerEchap;

  useEffect(() => {
    if (!actif) return undefined;

    const declencheur = document.activeElement;
    const debordement = document.body.style.overflow;
    document.body.style.overflow = "hidden";

    // A l'ouverture seulement : refocaliser a chaque rendu volerait le focus
    // en pleine saisie.
    const cible = focusInitial?.current || elementsFocalisables(conteneur.current)[0] || conteneur.current;
    cible?.focus();

    function surTouche(evenement) {
      if (evenement.key === "Escape") {
        if (!bloquerRef.current) {
          evenement.stopPropagation();
          onEchapRef.current?.();
        }
        return;
      }
      if (evenement.key !== "Tab") return;

      const elements = elementsFocalisables(conteneur.current);
      if (elements.length === 0) {
        evenement.preventDefault();
        return;
      }
      const premier = elements[0];
      const dernier = elements[elements.length - 1];

      if (evenement.shiftKey && document.activeElement === premier) {
        evenement.preventDefault();
        dernier.focus();
      } else if (!evenement.shiftKey && document.activeElement === dernier) {
        evenement.preventDefault();
        premier.focus();
      } else if (!conteneur.current?.contains(document.activeElement)) {
        evenement.preventDefault();
        premier.focus();
      }
    }

    document.addEventListener("keydown", surTouche, true);
    return () => {
      document.removeEventListener("keydown", surTouche, true);
      document.body.style.overflow = debordement;
      if (declencheur && typeof declencheur.focus === "function" && document.contains(declencheur)) {
        declencheur.focus();
      }
    };
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [actif]);
}
