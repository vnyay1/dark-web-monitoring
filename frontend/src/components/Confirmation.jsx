/**
 * Fenetre de confirmation d'une action irreversible.
 *
 * Le focus part sur "Annuler" et non sur l'action : un Entree reflexe ne
 * doit jamais declencher une suppression. Echap et un clic hors de la
 * fenetre annulent.
 */

import { useEffect, useRef } from "react";

export default function Confirmation({
  titre,
  children,
  libelleConfirmer,
  enCours = false,
  onConfirmer,
  onAnnuler,
  actionSecondaire = null,
}) {
  const boutonAnnuler = useRef(null);

  // A l'ouverture seulement : refocaliser a chaque rendu du parent volerait
  // le focus a l'utilisateur en pleine navigation au clavier.
  useEffect(() => {
    boutonAnnuler.current?.focus();
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
        role="alertdialog"
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
            className="btn btn-danger"
            onClick={onConfirmer}
            disabled={enCours}
          >
            {enCours ? "Suppression…" : libelleConfirmer}
          </button>
        </div>
      </div>
    </div>
  );
}
