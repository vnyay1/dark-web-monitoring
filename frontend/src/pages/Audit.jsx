/**
 * Journal d'audit (FR-17).
 *
 * C'est ici, et nulle part ailleurs, que se consultent les ECHECS de
 * collecte : la console de supervision montre l'avancement, ce journal
 * conserve le detail technique de chaque appel de connecteur.
 */

import { useState } from "react";

import { api } from "../api/client";
import { useChargement } from "../api/session";
import {
  Banniere,
  Chargement,
  EnTetePage,
  Erreur,
  formaterDateHeure,
  IndicateurRechargement,
  pluriel,
  Vide,
} from "../components/communs";
import { IconeAttention, IconeAudit, IconeSucces } from "../components/icones";

export default function Audit() {
  const [filtres, setFiltres] = useState({ resultat: "", source_id: "" });

  const { donnees, erreur, chargement, rechargement, recharger } = useChargement(
    () => api.audit(filtres),
    [filtres.resultat, filtres.source_id],
  );

  function modifier(champ, valeur) {
    setFiltres((f) => ({ ...f, [champ]: valeur }));
  }

  return (
    <>
      <IndicateurRechargement actif={rechargement} />
      <EnTetePage titre="Journal d'audit" sousTitre="Trace de chaque appel de connecteur, en écriture seule" />

      <form className="card filters" role="search" aria-label="Filtrer le journal" onSubmit={(e) => e.preventDefault()}>
        <div className="field">
          <label className="field-label" htmlFor="a-res">
            Résultat
          </label>
          <select id="a-res" className="select" value={filtres.resultat} onChange={(e) => modifier("resultat", e.target.value)}>
            <option value="">Tous</option>
            {(donnees?.resultats || []).map((r) => (
              <option key={r} value={r}>
                {r === "succes" ? "Succès" : "Échec"}
              </option>
            ))}
          </select>
        </div>

        <div className="field">
          <label className="field-label" htmlFor="a-src">
            Source
          </label>
          <select id="a-src" className="select" value={filtres.source_id} onChange={(e) => modifier("source_id", e.target.value)}>
            <option value="">Toutes</option>
            {(donnees?.sources || []).map((s) => (
              <option key={s.id} value={s.id}>
                {s.nom}
              </option>
            ))}
          </select>
        </div>
      </form>

      <Erreur message={erreur} onReessayer={recharger} />

      {chargement ? (
        <Chargement />
      ) : !donnees || donnees.entrees.length === 0 ? (
        <Vide titre="Aucune entrée d'audit" icone={IconeAudit}>
          Le journal se remplit à chaque appel de connecteur.
        </Vide>
      ) : (
        <>
          <p className="barre-recherche-compte espace-resultats" role="status">
            {donnees.entrees.length} {pluriel("entrée", donnees.entrees.length)}
          </p>
          {donnees.tronque && (
            <Banniere ton="info">
              <p>
                Affichage limité aux 500 entrées les plus récentes. Filtrez par source ou par résultat pour
                remonter plus loin.
              </p>
            </Banniere>
          )}

          <div className="table-wrap tableau-cartes">
            <table className="data">
              <caption className="sr-only">Journal d'audit des connecteurs</caption>
              <thead>
                <tr>
                  <th scope="col">Horodatage</th>
                  <th scope="col">Source</th>
                  <th scope="col">Résultat</th>
                  <th scope="col">Détails</th>
                </tr>
              </thead>
              <tbody>
                {donnees.entrees.map((e) => (
                  <tr key={e.id}>
                    <td className="cell-mono cell-titre">{formaterDateHeure(e.horodatage)}</td>
                    <td className="cell-entity" data-label="Source">
                      {e.source || <span className="cell-muted">—</span>}
                    </td>
                    <td data-label="Résultat">
                      {e.resultat === "succes" ? (
                        <span className="pill pill-ok">
                          <IconeSucces taille={13} />
                          Succès
                        </span>
                      ) : (
                        <span className="pill pill-crit">
                          <IconeAttention taille={13} />
                          Échec
                        </span>
                      )}
                    </td>
                    <td className="cell-mono detail-audit" data-label="Détails">
                      {e.details || "—"}
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </>
      )}
    </>
  );
}
