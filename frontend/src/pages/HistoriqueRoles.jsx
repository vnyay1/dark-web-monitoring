import { api } from "../api/client";
import { useChargement } from "../api/session";
import {
  Chargement,
  EnTetePage,
  Erreur,
  formaterDateHeure,
  LIBELLE_ROLE,
  Vide,
} from "../components/communs";
import { IconeHistorique, IconeSuite } from "../components/icones";

export default function HistoriqueRoles() {
  const { donnees, erreur, chargement, recharger } = useChargement(() => api.historiqueRoles());

  if (chargement) return <Chargement />;
  if (erreur && !donnees) return <Erreur message={erreur} onReessayer={recharger} />;

  return (
    <>
      <EnTetePage titre="Historique des rôles" sousTitre="Trace de chaque changement de privilège" />

      {donnees.entrees.length === 0 ? (
        <Vide titre="Aucun changement de rôle enregistré" icone={IconeHistorique}>
          Les modifications de privilèges apparaîtront ici.
        </Vide>
      ) : (
        <div className="table-wrap tableau-cartes">
          <table className="data">
            <caption className="sr-only">Changements de rôle, du plus récent au plus ancien</caption>
            <thead>
              <tr>
                <th scope="col">Date</th>
                <th scope="col">Compte concerné</th>
                <th scope="col">Changement</th>
                <th scope="col">Modifié par</th>
              </tr>
            </thead>
            <tbody>
              {donnees.entrees.map((e) => (
                <tr key={e.id}>
                  <td className="cell-mono" data-label="Date">
                    {formaterDateHeure(e.date_modification)}
                  </td>
                  <td className="cell-entity cell-titre">{e.utilisateur_cible}</td>
                  <td data-label="Changement">
                    <span className="changement-role">
                      <span className="cell-muted">{LIBELLE_ROLE[e.ancien_role] || e.ancien_role || "—"}</span>
                      <IconeSuite taille={14} titre="devient" />
                      <span className={`role-tag role-${e.nouveau_role}`}>
                        {LIBELLE_ROLE[e.nouveau_role] || e.nouveau_role}
                      </span>
                    </span>
                  </td>
                  <td className="cell-muted" data-label="Modifié par">
                    {e.modifie_par}
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}
    </>
  );
}
