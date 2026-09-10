/**
 * Fenetre modale : confirmation d'une action irreversible, ou petit
 * formulaire (modification d'une categorie, d'un selecteur).
 *
 * En confirmation, le focus part sur "Annuler" et non sur l'action : un
 * Entree reflexe ne doit jamais declencher une suppression. En formulaire
 * (focusAnnuler=false), le focus est laisse au premier champ. Echap et un
 * clic hors de la fenetre annulent.
 */

import { useEffect, useRef } from "react";

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
  const boutonAnnuler = useRef(null);

  // A l'ouverture seulement : refocaliser a chaque rendu du parent volerait
  // le focus a l'utilisateur en pleine navigation au clavier.
  useEffect(() => {
    if (focusAnnuler) boutonAnnuler.current?.focus();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  useEffect(() => {
    const surTouche = (evenement) => {
      if (evenement.key === "Escape" && !enCours) onAnnuler();
    };
    document.addEventListener("keydown", surTouche);
    return () => document.removeEventListener("keydown", surTouche);
  }, [enCours, onAnnuler]);

  return (
    <div
      className="voile"
      onMouseDown={(e) => {
        if (e.target === e.currentTarget && !enCours) onAnnuler();
      }}
    >
      <div
        className="fenetre"
        role={variante === "danger" ? "alertdialog" : "dialog"}
        aria-modal="true"
        aria-labelledby="fenetre-titre"
      >
        <h2 id="fenetre-titre" className="fenetre-titre">
          {titre}
        </h2>
        <div className="fenetre-corps">{children}</div>
        <div className="fenetre-actions">
          <button
            ref={boutonAnnuler}
            className="btn btn-ghost"
            onClick={onAnnuler}
            disabled={enCours}
          >
            Annuler
          </button>
          {actionSecondaire && (
            <button
              className="btn"
              onClick={actionSecondaire.onClick}
              disabled={enCours}
            >
              {actionSecondaire.libelle}
            </button>
          )}
          <button
            className={`btn ${variante === "danger" ? "btn-danger" : "btn-primary"}`}
            onClick={onConfirmer}
            disabled={enCours || desactiverConfirmer}
          >
            {enCours ? libelleEnCours : libelleConfirmer}
          </button>
        </div>
      </div>
    </div>
  );
}
