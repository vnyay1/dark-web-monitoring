import { useState } from "react";

import { api } from "../api/client";
import { useChargement } from "../api/session";
import {
  Chargement,
  EnTetePage,
  Erreur,
  ListeCategories,
  LIBELLE_NIVEAU,
  LIBELLE_STATUT,
  ListeSources,
  PastilleCriticite,
  Tuile,
  Vide,
} from "../components/communs";

const MOIS = [
  "Janvier", "Février", "Mars", "Avril", "Mai", "Juin",
  "Juillet", "Août", "Septembre", "Octobre", "Novembre", "Décembre",
];

const ORDRE_NIVEAUX = ["critique", "elevee", "moyenne", "faible"];

export default function Rapports() {
  const maintenant = new Date();
  const [mois, setMois] = useState(maintenant.getMonth() + 1);
  const [annee, setAnnee] = useState(maintenant.getFullYear());

  const { donnees, erreur, chargement } = useChargement(
    () => api.rapportMensuel(mois, annee),
    [mois, annee],
  );

  const annees = Array.from({ length: 6 }, (_, i) => maintenant.getFullYear() - i);

  return (
    <>
      <EnTetePage
        titre="Rapports"
        sousTitre="Synthèse mensuelle et exports"
      />

      <div className="card filters">
        <div className="field">
          <label className="field-label" htmlFor="r-mois">
            Mois
          </label>
          <select
            id="r-mois"
            className="select"
            value={mois}
            onChange={(e) => setMois(Number(e.target.value))}
          >
            {MOIS.map((libelle, index) => (
              <option key={libelle} value={index + 1}>
                {libelle}
              </option>
            ))}
          </select>
        </div>

        <div className="field">
          <label className="field-label" htmlFor="r-annee">
            Année
          </label>
          <select
            id="r-annee"
            className="select"
            value={annee}
            onChange={(e) => setAnnee(Number(e.target.value))}
          >
            {annees.map((a) => (
              <option key={a} value={a}>
                {a}
              </option>
            ))}
          </select>
        </div>

        {/* Les exports sont des liens natifs, pas des appels fetch : le
            navigateur gere le telechargement et son nom de fichier. */}
        <div className="btn-row">
          <a
            className="btn btn-primary"
            href={`/reports/monthly/pdf?mois=${mois}&annee=${annee}`}
          >
            Rapport PDF
          </a>
          <a
            className="btn"
            href={`/reports/monthly/html?mois=${mois}&annee=${annee}`}
            target="_blank"
            rel="noreferrer"
          >
            Aperçu HTML
          </a>
          <a className="btn btn-ghost" href="/reports/export/json">
            Export JSON
          </a>
          <a className="btn btn-ghost" href="/reports/export/csv">
            Export CSV
          </a>
        </div>
      </div>

      <Erreur message={erreur} />

      {chargement ? (
        <Chargement />
      ) : !donnees ? null : donnees.total_periode === 0 ? (
        <Vide titre={`Aucune exposition en ${MOIS[mois - 1]} ${annee}`}>
          Choisissez une autre période, ou lancez une collecte.
        </Vide>
      ) : (
        <>
          <div className="grid grid-stats" style={{ marginBottom: 24 }}>
            <Tuile
              label="Expositions"
              valeur={donnees.total_periode}
              hint={`${MOIS[mois - 1]} ${annee}`}
            />
            <Tuile
              label="Criticité haute"
              valeur={donnees.nb_niveaux_hauts}
              hint="niveau élevé ou critique"
              ton="crit"
            />
            <Tuile
              label="Secteurs touchés"
              valeur={Object.keys(donnees.repartition_secteur).length}
              hint="secteurs distincts"
              ton="info"
            />
            <Tuile
              label="Catégories"
              valeur={Object.keys(donnees.repartition_categorie).length}
              hint="catégories représentées"
              ton="warn"
            />
          </div>

          <section style={{ marginBottom: 24 }}>
            <h2 className="section-title">Répartition par criticité</h2>
            <div className="btn-row">
              {ORDRE_NIVEAUX.map((niveau) => (
                <span key={niveau} className="pill pill-neutral">
                  {LIBELLE_NIVEAU[niveau]} :{" "}
                  <strong>{donnees.repartition_criticite[niveau] || 0}</strong>
                </span>
              ))}
            </div>
          </section>

          <section>
            <h2 className="section-title">
              Détail des expositions
              <span className="count">triées par criticité décroissante</span>
            </h2>

            <div className="table-wrap">
              <table className="data">
                <thead>
                  <tr>
                    <th>Entité</th>
                    <th>Secteur</th>
                    <th>Catégories</th>
                    <th>Sources</th>
                    <th>Criticité</th>
                    <th>Statut</th>
                  </tr>
                </thead>
                <tbody>
                  {donnees.entites.map((e, index) => (
                    <tr key={`${e.nom}-${index}`}>
                      <td className="cell-entity">{e.nom}</td>
                      <td className="cell-muted">{e.secteur}</td>
                      <td>
                        <ListeCategories categories={e.categories} />
                      </td>
                      <td>
                        <ListeSources sources={e.sources} />
                      </td>
                      <td>
                        <PastilleCriticite
                          niveau={e.niveau_criticite}
                          criticite={e.criticite}
                        />
                      </td>
                      <td className="cell-muted">
                        {LIBELLE_STATUT[e.statut] || e.statut}
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          </section>
        </>
      )}
    </>
  );
}
