/**
 * Interrupteur marche / arret (role="switch").
 *
 * Remplace les boutons dont le libelle affichait l'ETAT ("Actif") alors
 * qu'un clic declenchait l'ACTION inverse : un lecteur d'ecran annonce ici
 * "Activer le selecteur X, interrupteur, active".
 */

export default function Interrupteur({
  actif,
  onChange,
  libelle,
  libelleVisible,
  desactive = false,
  enCours = false,
}) {
  return (
    <button
      type="button"
      role="switch"
      aria-checked={actif}
      aria-label={libelleVisible ? undefined : libelle}
      aria-busy={enCours || undefined}
      className="interrupteur"
      onClick={() => onChange(!actif)}
      disabled={desactive || enCours}
    >
      <span className="interrupteur-piste" aria-hidden="true">
        <span className="interrupteur-pastille" />
      </span>
      {libelleVisible && <span>{libelleVisible}</span>}
    </button>
  );
}
