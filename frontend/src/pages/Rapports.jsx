/**
 * Synthese mensuelle et exports.
 *
 * Les telechargements sont des liens natifs, pas des appels fetch : le
 * navigateur gere le fichier, son nom et sa progression.
 */

import { useState } from "react";

import { api } from "../api/client";
import { useChargement } from "../api/session";
import {
  Chargement,
  EnTetePage,
  Erreur,
  IndicateurRechargement,
  LIBELLE_NIVEAU,
  ListeCategories,
  ListeSources,
  ORDRE_NIVEAUX,
  PastilleCriticite,
  PastilleStatut,
  Tuile,
  Vide,
} from "../components/communs";
import { IconeRapports, IconeTelecharger } from "../components/icones";

const MOIS = [
  "Janvier", "Février", "Mars", "Avril", "Mai", "Juin",
  "Juillet", "Août", "Septembre", "Octobre", "Novembre", "Décembre",
];

export default function Rapports() {
  const maintenant = new Date();
  const [mois, setMois] = useState(maintenant.getMonth() + 1);
  const [annee, setAnnee] = useState(maintenant.getFullYear());

  const { donnees, erreur, chargement, rechargement, recharger } = useChargement(
    () => api.rapportMensuel(mois, annee),
    [mois, annee],
  );

  const annees = Array.from({ length: 6 }, (_, i) => maintenant.getFullYear() - i);
  const periode = `${MOIS[mois - 1]} ${annee}`;

  return (
    <>
      <IndicateurRechargement actif={rechargement} />
      <EnTetePage titre="Rapports" sousTitre="Synthèse mensuelle et exports" />

      <section className="card card-pad espace-bas barre-rapport" aria-labelledby="titre-periode">
        <h2 className="sr-only" id="titre-periode">
          Période et téléchargements
        </h2>
        <div className="barre-rapport-periode">
          <div className="field">
            <label className="field-label" htmlFor="r-mois">
              Mois
            </label>
            <select id="r-mois" className="select" value={mois} onChange={(e) => setMois(Number(e.target.value))}>
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
            <select id="r-annee" className="select" value={annee} onChange={(e) => setAnnee(Number(e.target.value))}>
              {annees.map((a) => (
                <option key={a} value={a}>
                  {a}
                </option>
              ))}
            </select>
          </div>
        </div>

        <div className="barre-rapport-actions">
          <a className="btn btn-primary" href={`/reports/monthly/pdf?mois=${mois}&annee=${annee}`}>
            <IconeTelecharger taille={16} />
            Rapport PDF · {periode}
          </a>
          <a className="btn btn-contour" href={`/reports/monthly/html?mois=${mois}&annee=${annee}`} target="_blank" rel="noreferrer">
            Aperçu HTML
            <span className="sr-only"> (s'ouvre dans un nouvel onglet)</span>
          </a>
          <span className="separateur-vertical" aria-hidden="true" />
          <a className="btn btn-ghost" href="/reports/export/json">
            Export JSON
          </a>
          <a className="btn btn-ghost" href="/reports/export/csv">
            Export CSV
          </a>
        </div>
        <p className="texte-aide">Les exports JSON et CSV contiennent toutes les expositions, quelle que soit la période.</p>
      </section>

      <Erreur message={erreur} onReessayer={recharger} />

      {chargement ? (
        <Chargement />
      ) : !donnees ? null : donnees.total_periode === 0 ? (
        <Vide titre={`Aucune exposition en ${periode}`} icone={IconeRapports}>
          Choisissez une autre période, ou lancez une collecte.
        </Vide>
      ) : (
        <>
          <div className="grid grid-stats espace-bas">
            <Tuile label="Expositions" valeur={donnees.total_periode} hint={periode} />
            <Tuile label="Criticité haute" valeur={donnees.nb_niveaux_hauts} hint="niveau élevé ou critique" ton="crit" />
            <Tuile label="À qualifier" valeur={donnees.nb_a_qualifier} hint="nouvelles, sans analyse" ton="warn" />
            <Tuile
              label="Catégories"
              valeur={Object.keys(donnees.repartition_categorie).length}
              hint="catégories représentées"
              ton="info"
            />
          </div>

          <section className="espace-bas" aria-labelledby="titre-repartition">
            <h2 className="section-title" id="titre-repartition">
              Répartition par criticité
            </h2>
            <ul className="repartition-niveaux">
              {ORDRE_NIVEAUX.map((niveau) => (
                <li key={niveau}>
                  <PastilleCriticite niveau={niveau} />
                  <span className="repartition-nombre">{donnees.repartition_criticite[niveau] || 0}</span>
                  <span className="sr-only"> {LIBELLE_NIVEAU[niveau]}</span>
                </li>
              ))}
            </ul>
          </section>

          <section aria-labelledby="titre-detail">
            <h2 className="section-title" id="titre-detail">
              Détail des expositions
              <span className="count">triées par criticité décroissante</span>
            </h2>

            <div className="table-wrap tableau-cartes">
              <table className="data">
                <caption className="sr-only">Expositions de {periode}, par criticité décroissante</caption>
                <thead>
                  <tr>
                    <th scope="col">Entité</th>
                    <th scope="col">Catégories</th>
                    <th scope="col">Sources</th>
                    <th scope="col">Criticité</th>
                    <th scope="col">Statut</th>
                  </tr>
                </thead>
                <tbody>
                  {donnees.entites.map((e, index) => (
                    <tr key={`${e.nom}-${index}`}>
                      <td className="cell-entity cell-titre">{e.nom}</td>
                      <td data-label="Catégories">
                        <ListeCategories categories={e.categories} />
                      </td>
                      <td data-label="Sources">
                        <ListeSources sources={e.sources} />
                      </td>
                      <td data-label="Criticité">
                        <PastilleCriticite niveau={e.niveau_criticite} criticite={e.criticite} />
                      </td>
                      <td data-label="Statut">
                        <PastilleStatut statut={e.statut} />
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
