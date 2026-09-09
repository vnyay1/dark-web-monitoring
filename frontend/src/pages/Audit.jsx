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
  Chargement,
  EnTetePage,
  Erreur,
  formaterDateHeure,
  Vide,
} from "../components/communs";

export default function Audit() {
  const [filtres, setFiltres] = useState({ resultat: "", source_id: "" });

  const { donnees, erreur, chargement } = useChargement(
    () => api.audit(filtres),
    [filtres.resultat, filtres.source_id],
  );

  function modifier(champ, valeur) {
    setFiltres((f) => ({ ...f, [champ]: valeur }));
  }

  return (
    <>
      <EnTetePage
        titre="Journal d'audit"
        sousTitre="Trace de chaque appel de connecteur, en écriture seule"
      />

      <div className="card filters">
        <div className="field">
          <label className="field-label" htmlFor="a-res">
            Résultat
          </label>
          <select
            id="a-res"
            className="select"
            value={filtres.resultat}
            onChange={(e) => modifier("resultat", e.target.value)}
          >
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
          <select
            id="a-src"
            className="select"
            value={filtres.source_id}
            onChange={(e) => modifier("source_id", e.target.value)}
          >
            <option value="">Toutes</option>
            {(donnees?.sources || []).map((s) => (
              <option key={s.id} value={s.id}>
                {s.nom}
              </option>
            ))}
          </select>
        </div>
      </div>

      <Erreur message={erreur} />

      {chargement ? (
        <Chargement />
      ) : !donnees || donnees.entrees.length === 0 ? (
        <Vide titre="Aucune entrée d'audit">
          Le journal se remplit à chaque appel de connecteur.
        </Vide>
      ) : (
        <>
          {donnees.tronque && (
            <div className="banner banner-info">
              Affichage limité aux 500 entrées les plus récentes. Filtrez par
              source ou par résultat pour remonter plus loin.
            </div>
          )}

          <div className="table-wrap">
            <table className="data">
              <thead>
                <tr>
                  <th style={{ width: 170 }}>Horodatage</th>
                  <th style={{ width: 170 }}>Source</th>
                  <th style={{ width: 110 }}>Résultat</th>
                  <th>Détails</th>
                </tr>
              </thead>
              <tbody>
                {donnees.entrees.map((e) => (
                  <tr key={e.id}>
                    <td className="cell-mono">
                      {formaterDateHeure(e.horodatage)}
                    </td>
                    <td className="cell-entity">
                      {e.source || <span className="cell-muted">—</span>}
                    </td>
                    <td>
                      <span
                        className={`pill ${
                          e.resultat === "succes" ? "pill-ok" : "pill-crit"
                        }`}
                      >
                        {e.resultat === "succes" ? "Succès" : "Échec"}
                      </span>
                    </td>
                    <td className="cell-mono detail-audit">
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
