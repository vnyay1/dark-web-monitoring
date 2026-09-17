/**
 * Changement du statut d'une exposition, avec ENREGISTREMENT EXPLICITE.
 *
 * WCAG 3.2.2 - l'ancien <select> enregistrait a chaque changement de valeur.
 * Or au clavier, les fleches d'une liste fermee changent la valeur : chaque
 * pression envoyait une requete et modifiait le statut. Ici, choisir une
 * valeur ne fait rien ; le bouton "Enregistrer" apparait et valide.
 */

import { useEffect, useState } from "react";

import { LIBELLE_STATUT } from "./communs";
import { IconeFermer, IconeValider } from "./icones";

export default function ChoixStatut({ statut, statuts, libelle, onEnregistrer, compact = false }) {
  const [valeur, setValeur] = useState(statut);
  const [enCours, setEnCours] = useState(false);

  // Le statut enregistre peut changer ailleurs (rechargement de la liste).
  useEffect(() => {
    setValeur(statut);
  }, [statut]);

  const modifie = valeur !== statut;

  async function enregistrer() {
    setEnCours(true);
    try {
      const ok = await onEnregistrer(valeur);
      if (ok === false) setValeur(statut);
    } finally {
      setEnCours(false);
    }
  }

  return (
    <div className={`choix-statut${compact ? " est-compact" : ""}`}>
      <select
        className="select"
        value={valeur}
        onChange={(e) => setValeur(e.target.value)}
        aria-label={libelle}
        disabled={enCours}
      >
        {statuts.map((s) => (
          <option key={s} value={s}>
            {LIBELLE_STATUT[s] || s}
          </option>
        ))}
      </select>
      {modifie && (
        <>
          <button
            type="button"
            className="btn btn-primary btn-sm btn-icone"
            onClick={enregistrer}
            disabled={enCours}
            aria-label={`Enregistrer le statut « ${LIBELLE_STATUT[valeur] || valeur} »`}
            title="Enregistrer"
          >
            {enCours ? <span className="spinner" aria-hidden="true" /> : <IconeValider taille={16} />}
          </button>
          <button
            type="button"
            className="btn btn-ghost btn-sm btn-icone"
            onClick={() => setValeur(statut)}
            disabled={enCours}
            aria-label="Annuler le changement de statut"
            title="Annuler"
          >
            <IconeFermer taille={16} />
          </button>
        </>
      )}
    </div>
  );
}
