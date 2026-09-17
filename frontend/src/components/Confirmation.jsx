/**
 * Fenetre modale : confirmation d'une action irreversible, ou petit
 * formulaire (modification d'une categorie, d'un selecteur).
 *
 * En confirmation, le focus part sur "Annuler" et non sur l'action : un
 * Entree reflexe ne doit jamais declencher une suppression. En formulaire
 * (focusAnnuler=false), le focus va au premier champ.
 *
 * Accessibilite (cf. piegeFocus) : focus maintenu dans la fenetre, Echap et
 * clic sur le voile annulent, retour du focus au bouton qui l'a ouverte,
 * defilement de la page bloque. Sur petit ecran, la fenetre s'ancre en bas.
 */

import { useId, useRef } from "react";

import { IconeAttention } from "./icones";
import { usePiegeFocus } from "./piegeFocus";

export default function Confirmation({
  titre,
  children,
  libelleConfirmer,
  libelleEnCours = "Suppression…",
  variante = "danger",
  enCours = false,
  desactiverConfirmer = false,
  focusAnnuler = true,
  onConfirmer,
  onAnnuler,
  actionSecondaire = null,
}) {
  const fenetre = useRef(null);
  const boutonAnnuler = useRef(null);
  const idTitre = useId();
  const idCorps = useId();

  usePiegeFocus(true, fenetre, {
    onEchap: onAnnuler,
    bloquerEchap: enCours,
    focusInitial: focusAnnuler ? boutonAnnuler : undefined,
  });

  const danger = variante === "danger";

  return (
    <div
      className="voile"
      onMouseDown={(e) => {
        if (e.target === e.currentTarget && !enCours) onAnnuler();
      }}
    >
      <div
        ref={fenetre}
        className="fenetre"
        role={danger ? "alertdialog" : "dialog"}
        aria-modal="true"
        aria-labelledby={idTitre}
        aria-describedby={idCorps}
        aria-busy={enCours || undefined}
      >
        <h2 id={idTitre} className="fenetre-titre">
          {danger && <IconeAttention taille={20} />}
          {titre}
        </h2>
        <div id={idCorps} className="fenetre-corps">
          {children}
        </div>
        <div className="fenetre-actions">
          <button
            ref={boutonAnnuler}
            type="button"
            className="btn btn-contour"
            onClick={onAnnuler}
            disabled={enCours}
          >
            Annuler
          </button>
          {actionSecondaire && (
            <button
              type="button"
              className="btn"
              onClick={actionSecondaire.onClick}
              disabled={enCours}
            >
              {actionSecondaire.libelle}
            </button>
          )}
          <button
            type="button"
            className={`btn ${danger ? "btn-danger" : "btn-primary"}`}
            onClick={onConfirmer}
            disabled={enCours || desactiverConfirmer}
          >
            {enCours && <span className="spinner" aria-hidden="true" />}
            {enCours ? libelleEnCours : libelleConfirmer}
          </button>
        </div>
      </div>
    </div>
  );
}
