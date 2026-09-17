/**
 * Liste de choix a ENREGISTREMENT EXPLICITE (statut d'une exposition, role
 * d'un compte).
 *
 * WCAG 3.2.2 - un <select> qui enregistre a chaque changement de valeur est
 * piegeux au clavier : les fleches d'une liste fermee changent la valeur, et
 * chaque pression envoyait une requete. Ici, choisir ne fait rien ; les
 * boutons Enregistrer / Annuler apparaissent et valident.
 */

import { useEffect, useState } from "react";

import { LIBELLE_STATUT } from "./communs";
import { IconeFermer, IconeValider } from "./icones";

/**
 * options : [[valeur, libelle, desactivee?], ...]
 * onEnregistrer(valeur) : async, renvoie false en cas d'echec (la valeur
 * enregistree est alors restauree).
 */
export function ChoixEnregistre({ valeur: valeurEnregistree, options, libelle, onEnregistrer, compact = false, desactive = false }) {
  const [valeur, setValeur] = useState(valeurEnregistree);
  const [enCours, setEnCours] = useState(false);

  // La valeur enregistree peut changer ailleurs (rechargement de la liste).
  useEffect(() => {
    setValeur(valeurEnregistree);
  }, [valeurEnregistree]);

  const modifie = valeur !== valeurEnregistree;
  const libelleValeur = options.find(([v]) => v === valeur)?.[1] || valeur;

  async function enregistrer() {
    setEnCours(true);
    try {
      const ok = await onEnregistrer(valeur);
      if (ok === false) setValeur(valeurEnregistree);
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
        disabled={desactive || enCours}
      >
        {options.map(([v, l, optionDesactivee]) => (
          <option key={v} value={v} disabled={optionDesactivee}>
            {l}
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
            aria-label={`Enregistrer : ${libelleValeur}`}
            title="Enregistrer"
          >
            {enCours ? <span className="spinner" aria-hidden="true" /> : <IconeValider taille={16} />}
          </button>
          <button
            type="button"
            className="btn btn-ghost btn-sm btn-icone"
            onClick={() => setValeur(valeurEnregistree)}
            disabled={enCours}
            aria-label="Annuler le changement"
            title="Annuler"
          >
            <IconeFermer taille={16} />
          </button>
        </>
      )}
    </div>
  );
}

export default function ChoixStatut({ statut, statuts, libelle, onEnregistrer, compact = false }) {
  return (
    <ChoixEnregistre
      valeur={statut}
      options={statuts.map((s) => [s, LIBELLE_STATUT[s] || s])}
      libelle={libelle}
      onEnregistrer={onEnregistrer}
      compact={compact}
    />
  );
}
