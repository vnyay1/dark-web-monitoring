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

export default function HistoriqueRoles() {
  const { donnees, erreur, chargement } = useChargement(() =>
    api.historiqueRoles(),
  );

  if (chargement) return <Chargement />;
  if (erreur) return <Erreur message={erreur} />;

  return (
    <>
      <EnTetePage
        titre="Historique des rôles"
        sousTitre="Trace de chaque changement de privilège"
      />

      {donnees.entrees.length === 0 ? (
        <Vide titre="Aucun changement de rôle enregistré">
          Les modifications de privilèges apparaîtront ici.
        </Vide>
      ) : (
        <div className="table-wrap">
          <table className="data">
            <thead>
              <tr>
                <th>Date</th>
                <th>Compte concerné</th>
                <th>Ancien rôle</th>
                <th>Nouveau rôle</th>
                <th>Modifié par</th>
              </tr>
            </thead>
            <tbody>
              {donnees.entrees.map((e) => (
                <tr key={e.id}>
                  <td className="cell-mono">
                    {formaterDateHeure(e.date_modification)}
                  </td>
                  <td className="cell-entity">{e.utilisateur_cible}</td>
                  <td className="cell-muted">
                    {LIBELLE_ROLE[e.ancien_role] || e.ancien_role || "—"}
                  </td>
                  <td>
                    <span className={`role-tag role-${e.nouveau_role}`}>
                      {LIBELLE_ROLE[e.nouveau_role] || e.nouveau_role}
                    </span>
                  </td>
                  <td className="cell-muted">{e.modifie_par}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}
    </>
  );
}
