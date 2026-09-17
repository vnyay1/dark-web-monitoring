import { Link } from "react-router-dom";

import { api } from "../api/client";
import { useChargement } from "../api/session";
import {
  Banniere,
  Chargement,
  EnTetePage,
  Erreur,
  formaterDate,
  formaterDateHeure,
  IndicateurRechargement,
  LIBELLE_NIVEAU,
  ListeCategories,
  ListeSources,
  ORDRE_NIVEAUX,
  PastilleCriticite,
  PastilleStatut,
  pluriel,
  Tuile,
  Vide,
} from "../components/communs";
import { BarresHorizontales } from "../components/graphiques";
import { IconeAttention, IconeSources, IconeSucces, IconeSuite } from "../components/icones";

export default function Dashboard() {
  const { donnees, erreur, chargement, rechargement, recharger } = useChargement(() =>
    api.dashboard(),
  );

  if (chargement) return <Chargement />;
  if (erreur && !donnees) return <Erreur message={erreur} onReessayer={recharger} />;
  if (!donnees) return null;

  const parCriticite = ORDRE_NIVEAUX.map((niveau) => ({
    libelle: LIBELLE_NIVEAU[niveau],
    valeur: donnees.repartition_criticite[niveau] || 0,
    niveau,
  }));

  const parCategorie = Object.entries(donnees.repartition_categorie).map(([libelle, valeur]) => ({
    libelle,
    valeur,
  }));

  const sourcesEnAlerte = donnees.sources.filter((s) => s.indisponible);

  return (
    <>
      <IndicateurRechargement actif={rechargement} />
      <EnTetePage
        titre="Tableau de bord"
        sousTitre="Vue d'ensemble des expositions détectées sur les sources surveillées"
      />

      <Erreur message={erreur} onReessayer={recharger} />

      <div className="grid grid-stats espace-bas">
        <Tuile
          label="Expositions"
          valeur={donnees.total}
          hint="total répertorié"
          vers="/expositions"
          libelleLien="Voir toutes"
        />
        <Tuile
          label="Criticité haute"
          valeur={donnees.niveaux_hauts}
          hint="niveau élevé ou critique"
          ton="crit"
          vers="/expositions?niveau_min=elevee"
          libelleLien="Voir la liste"
        />
        <Tuile
          label="À traiter"
          valeur={donnees.a_traiter}
          hint="nouvelles ou en analyse"
          ton="warn"
          vers="/expositions?statut=new"
          libelleLien="Voir les nouvelles"
        />
        <Tuile
          label="7 derniers jours"
          valeur={donnees.nouvelles_7j}
          hint={`${donnees.nouvelles_30j} sur 30 jours`}
          ton="info"
          vers="/expositions?periode=7"
          libelleLien="Voir la semaine"
        />
      </div>

      {sourcesEnAlerte.length > 0 && (
        <Banniere ton="warn" role="status">
          <p>
            <strong>
              {sourcesEnAlerte.length} {pluriel("source", sourcesEnAlerte.length)} sans collecte
              réussie depuis plus de 48 h
            </strong>{" "}
            : {sourcesEnAlerte.map((s) => s.nom).join(", ")}.
          </p>
        </Banniere>
      )}

      <div className="grid grid-2 espace-bas">
        <section className="card card-pad" aria-labelledby="titre-criticite">
          <h2 className="section-title" id="titre-criticite">
            Répartition par criticité
            <span className="count">nombre de sélecteurs distincts</span>
          </h2>
          <BarresHorizontales
            donnees={parCriticite}
            cleCouleur={(ligne) => ligne.niveau}
            suffixe="exposition(s)"
            titre="Expositions par niveau de criticité"
          />
        </section>

        <section className="card card-pad" aria-labelledby="titre-categories">
          <h2 className="section-title" id="titre-categories">
            Répartition par catégorie
            <span className="count">une exposition peut en porter plusieurs</span>
          </h2>
          <BarresHorizontales
            donnees={parCategorie}
            suffixe="exposition(s)"
            titre="Expositions par catégorie"
          />
        </section>
      </div>

      <section className="card card-pad espace-bas" aria-labelledby="titre-sources">
        <h2 className="section-title" id="titre-sources">
          État des sources
          <span className="count">
            {donnees.sources.length} {pluriel("surveillée", donnees.sources.length)}
          </span>
        </h2>
        {donnees.sources.length === 0 ? (
          <p className="texte-aide">Aucune source enregistrée : lancez une première collecte.</p>
        ) : (
          <div className="table-wrap sans-cadre tableau-cartes">
            <table className="data">
              <caption className="sr-only">État des sources surveillées</caption>
              <thead>
                <tr>
                  <th scope="col">Source</th>
                  <th scope="col">Dernière collecte réussie</th>
                  <th scope="col">État</th>
                </tr>
              </thead>
              <tbody>
                {donnees.sources.map((s) => (
                  <tr key={s.nom}>
                    <td className="cell-entity cell-titre">{s.nom}</td>
                    <td className="cell-mono" data-label="Dernière collecte">
                      {s.derniere_collecte_reussie ? formaterDate(s.derniere_collecte_reussie) : "jamais"}
                    </td>
                    <td data-label="État">
                      {s.indisponible ? (
                        <span className="pill pill-crit">
                          <IconeAttention taille={13} />
                          Injoignable
                        </span>
                      ) : (
                        <span className="pill pill-ok">
                          <IconeSucces taille={13} />
                          Opérationnelle
                        </span>
                      )}
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}
      </section>

      <section aria-labelledby="titre-detections">
        <h2 className="section-title" id="titre-detections">
          Dernières détections
          <Link to="/expositions" className="section-action">
            Voir toutes les expositions <IconeSuite taille={14} />
          </Link>
        </h2>

        {donnees.dernieres_expositions.length === 0 ? (
          <Vide titre="Aucune exposition détectée" icone={IconeSources}>
            Les détections apparaîtront ici dès la première collecte réussie.
          </Vide>
        ) : (
          <div className="table-wrap tableau-cartes">
            <table className="data">
              <caption className="sr-only">Les huit dernières expositions détectées</caption>
              <thead>
                <tr>
                  <th scope="col">Entité</th>
                  <th scope="col">Criticité</th>
                  <th scope="col">Catégories</th>
                  <th scope="col">Sources</th>
                  <th scope="col">Détection</th>
                  <th scope="col">Statut</th>
                </tr>
              </thead>
              <tbody>
                {donnees.dernieres_expositions.map((e) => (
                  <tr key={e.id}>
                    <td className="cell-titre">
                      <Link className="lien-entite" to={`/expositions/${e.id}`}>
                        {e.nom_entite}
                      </Link>
                    </td>
                    <td data-label="Criticité">
                      <PastilleCriticite niveau={e.niveau_criticite} criticite={e.criticite} />
                    </td>
                    <td data-label="Catégories">
                      <ListeCategories categories={e.categories} />
                    </td>
                    <td data-label="Sources">
                      <ListeSources sources={e.sources} />
                    </td>
                    <td className="cell-mono" data-label="Détection">
                      {formaterDateHeure(e.date_premiere_detection)}
                    </td>
                    <td data-label="Statut">
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
