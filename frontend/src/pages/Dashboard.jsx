import { Link } from "react-router-dom";

import { api } from "../api/client";
import { useChargement } from "../api/session";
import {
  Chargement,
  EnTetePage,
  Erreur,
  formaterDate,
  formaterDateHeure,
  LIBELLE_NIVEAU,
  ListeCategories,
  ListeSources,
  PastilleCriticite,
  PastilleStatut,
  Tuile,
  Vide,
} from "../components/communs";
import { BarresHorizontales, COULEUR_NIVEAU } from "../components/graphiques";

/** Ordre de gravite : un graphique de severite ne se trie pas par quantite. */
const ORDRE_NIVEAUX = ["critique", "elevee", "moyenne", "faible"];

export default function Dashboard() {
  const { donnees, erreur, chargement } = useChargement(() => api.dashboard());

  if (chargement) return <Chargement />;
  if (erreur) return <Erreur message={erreur} />;
  if (!donnees) return null;

  const parCriticite = ORDRE_NIVEAUX.map((niveau) => ({
    libelle: LIBELLE_NIVEAU[niveau],
    valeur: donnees.repartition_criticite[niveau] || 0,
    niveau,
  }));

  const parCategorie = Object.entries(donnees.repartition_categorie).map(
    ([libelle, valeur]) => ({ libelle, valeur }),
  );

  const parSecteur = Object.entries(donnees.repartition_secteur)
    .map(([libelle, valeur]) => ({ libelle, valeur }))
    .slice(0, 10);

  const sourcesEnAlerte = donnees.sources.filter((s) => s.indisponible);

  return (
    <>
      <EnTetePage
        titre="Tableau de bord"
        sousTitre="Vue d'ensemble des expositions détectées sur les sources surveillées"
      />

      <div className="grid grid-stats" style={{ marginBottom: 22 }}>
        <Tuile
          label="Expositions"
          valeur={donnees.total}
          hint="total répertorié"
        />
        <Tuile
          label="Criticité haute"
          valeur={donnees.niveaux_hauts}
          hint="niveau élevé ou critique"
          ton="crit"
        />
        <Tuile
          label="À traiter"
          valeur={donnees.a_traiter}
          hint="nouvelles ou en analyse"
          ton="warn"
        />
        <Tuile
          label="7 derniers jours"
          valeur={donnees.nouvelles_7j}
          hint={`${donnees.nouvelles_30j} sur 30 jours`}
          ton="info"
        />
      </div>

      {sourcesEnAlerte.length > 0 && (
        <div className="banner banner-warn" role="status">
          {sourcesEnAlerte.length} source(s) sans collecte réussie depuis plus
          de 48 h : {sourcesEnAlerte.map((s) => s.nom).join(", ")}.
        </div>
      )}

      <div className="grid grid-2" style={{ marginBottom: 22 }}>
        <section className="card card-pad">
          <h2 className="section-title">
            Répartition par criticité
            <span className="count">nombre de sélecteurs distincts</span>
          </h2>
          <BarresHorizontales
            donnees={parCriticite}
            couleurParCle={(ligne) => COULEUR_NIVEAU[ligne.niveau]}
            suffixe="exposition(s)"
          />
        </section>

        <section className="card card-pad">
          <h2 className="section-title">
            Répartition par catégorie
            <span className="count">une exposition peut en porter plusieurs</span>
          </h2>
          <BarresHorizontales donnees={parCategorie} suffixe="exposition(s)" />
        </section>
      </div>

      <div className="grid grid-2" style={{ marginBottom: 22 }}>
        <section className="card card-pad">
          <h2 className="section-title">
            Secteurs concernés
            {parSecteur.length === 10 && <span className="count">top 10</span>}
          </h2>
          <BarresHorizontales donnees={parSecteur} suffixe="exposition(s)" />
        </section>

        <section className="card card-pad">
          <h2 className="section-title">
            État des sources
            <span className="count">{donnees.sources.length} surveillée(s)</span>
          </h2>
          {donnees.sources.length === 0 ? (
            <div className="cell-muted" style={{ fontSize: 12.5 }}>
              Aucune source enregistrée : lancez une première collecte.
            </div>
          ) : (
            <div className="table-wrap" style={{ border: "none" }}>
              <table className="data">
                <thead>
                  <tr>
                    <th>Source</th>
                    <th>Dernière collecte</th>
                    <th>État</th>
                  </tr>
                </thead>
                <tbody>
                  {donnees.sources.map((s) => (
                    <tr key={s.nom}>
                      <td className="cell-entity">{s.nom}</td>
                      <td className="cell-mono">
                        {s.derniere_collecte_reussie
                          ? formaterDate(s.derniere_collecte_reussie)
                          : "jamais"}
                      </td>
                      <td>
                        <span
                          className={`pill ${
                            s.indisponible ? "pill-crit" : "pill-ok"
                          }`}
                        >
                          {s.indisponible ? "Injoignable" : "Opérationnelle"}
                        </span>
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          )}
        </section>
      </div>

      <section>
        <h2 className="section-title">
          Dernières détections
          <Link
            to="/expositions"
            className="count"
            style={{ marginLeft: "auto", color: "var(--accent)" }}
          >
            Voir toutes les expositions →
          </Link>
        </h2>

        {donnees.dernieres_expositions.length === 0 ? (
          <Vide titre="Aucune exposition détectée">
            Les détections apparaîtront ici dès la première collecte réussie.
          </Vide>
        ) : (
          <div className="table-wrap">
            <table className="data">
              <thead>
                <tr>
                  <th>Entité</th>
                  <th>Criticité</th>
                  <th>Catégories</th>
                  <th>Sources</th>
                  <th>Détection</th>
                  <th>Statut</th>
                </tr>
              </thead>
              <tbody>
                {donnees.dernieres_expositions.map((e) => (
                  <tr key={e.id}>
                    <td className="cell-entity">
                      <Link to={`/expositions/${e.id}`}>{e.nom_entite}</Link>
                    </td>
                    <td>
                      <PastilleCriticite
                        niveau={e.niveau_criticite}
                        criticite={e.criticite}
                      />
                    </td>
                    <td>
                      <ListeCategories categories={e.categories} />
                    </td>
                    <td>
                      <ListeSources sources={e.sources} />
                    </td>
                    <td className="cell-mono">
                      {formaterDateHeure(e.date_premiere_detection)}
                    </td>
                    <td>
                      <PastilleStatut statut={e.statut} />
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}
      </section>
    </>
  );
}
