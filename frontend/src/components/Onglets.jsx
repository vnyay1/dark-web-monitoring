/**
 * Onglets accessibles (motif "tabs" de l'ARIA Authoring Practices).
 *
 * Un seul onglet est dans l'ordre de tabulation (tabindex mobile) ; les
 * fleches gauche / droite, Debut et Fin passent d'un onglet a l'autre et
 * l'activent. Le panneau est relie a son onglet (aria-controls /
 * aria-labelledby).
 */

import { useRef } from "react";

export function ListeOnglets({ onglets, actif, onChange, libelle, idBase }) {
  const refs = useRef({});

  function surTouche(evenement, index) {
    const dernier = onglets.length - 1;
    const cible = {
      ArrowRight: index === dernier ? 0 : index + 1,
      ArrowLeft: index === 0 ? dernier : index - 1,
      Home: 0,
      End: dernier,
    }[evenement.key];
    if (cible === undefined) return;
    evenement.preventDefault();
    const suivant = onglets[cible];
    onChange(suivant.cle);
    refs.current[suivant.cle]?.focus();
  }

  return (
    <div className="onglets" role="tablist" aria-label={libelle}>
      {onglets.map((onglet, index) => {
        const selectionne = onglet.cle === actif;
        return (
          <button
            key={onglet.cle}
            ref={(el) => {
              refs.current[onglet.cle] = el;
            }}
            type="button"
            role="tab"
            id={`${idBase}-onglet-${onglet.cle}`}
            aria-selected={selectionne}
            aria-controls={`${idBase}-panneau-${onglet.cle}`}
            tabIndex={selectionne ? 0 : -1}
            className="onglet"
            onClick={() => onChange(onglet.cle)}
            onKeyDown={(e) => surTouche(e, index)}
          >
            {onglet.libelle}
            {onglet.compte !== undefined && <span className="count">{onglet.compte}</span>}
          </button>
        );
      })}
    </div>
  );
}

export function PanneauOnglet({ cle, idBase, children }) {
  return (
    <div
      role="tabpanel"
      id={`${idBase}-panneau-${cle}`}
      aria-labelledby={`${idBase}-onglet-${cle}`}
      tabIndex={0}
      className="panneau-onglet"
    >
      {children}
    </div>
  );
}
