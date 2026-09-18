/**
 * Detail d'une exposition : ce qu'on sait, et surtout D'OU on le sait.
 *
 * Le tableau des signalements est la raison d'etre de cette page : une meme
 * exposition peut etre reperee sur plusieurs sources a des dates
 * differentes, ce que la liste ne pouvait pas montrer.
 */

import { Link, useLocation, useParams } from "react-router-dom";

import { api } from "../api/client";
import { useChargement, useMessages, useSession } from "../api/session";
import ChoixStatut from "../components/ChoixStatut";
import {
  Chargement,
  enDate,
  Erreur,
  formaterDate,
  formaterDateHeure,
  LIBELLE_STATUT,
  LIBELLE_TYPE_SOURCE,
  ListeCategories,
  Messages,
  PastilleCriticite,
  PastilleStatut,
  pluriel,
} from "../components/communs";
import { IconeRetour } from "../components/icones";

export default function DetailExposition() {
  const { id } = useParams();
  const location = useLocation();
  const { aRole } = useSession();
  const { messages, ajouter } = useMessages();

  const { donnees, erreur, chargement, recharger, setDonnees } = useChargement(
    () => api.exposition(id),
    [id],
  );

  // Retour a la liste AVEC les filtres d'ou l'on venait.
  const retourListe = `/expositions${location.state?.retour || ""}`;

  async function changerStatut(statut) {
    try {
      await api.changerStatut(id, statut);
      setDonnees((precedent) => ({ ...precedent, statut }));
      ajouter(`Statut « ${LIBELLE_STATUT[statut] || statut} » enregistré.`);
      return true;
    } catch (e) {
      ajouter(e.message, "error");
      return false;
    }
  }

  if (chargement) return <Chargement />;
  if (erreur && !donnees) return <Erreur message={erreur} onReessayer={recharger} />;
  if (!donnees) return null;

  const jalons = [
    { libelle: "Première détection", date: donnees.date_premiere_detection },
    { libelle: "Publication la plus récente sur une source", date: donnees.date_publication_source },
    { libelle: "Dernière détection", date: donnees.date_derniere_detection },
  ]
    .filter((j) => j.date)
    .sort((a, b) => enDate(a.date) - enDate(b.date));

  return (
    <>
      <Link to={retourListe} className="lien-retour">
        <IconeRetour taille={16} />
        Liste des expositions
      </Link>

      <div className="page-header">
        <div>
          <h1 className="page-title">{donnees.nom_entite}</h1>
          <p className="page-subtitle">
            Détectée le {formaterDateHeure(donnees.date_premiere_detection)} ·{" "}
            {donnees.nb_sources} {pluriel("source", donnees.nb_sources)}
          </p>
        </div>
      </div>

      <div className="grid grid-stats espace-bas">
        <div className="stat">
          <span className="stat-label">Criticité</span>
          <span className="stat-contenu">
            <PastilleCriticite niveau={donnees.niveau_criticite} />
          </span>
          <span className="stat-hint">
            Score {donnees.criticite} : sélecteurs camerounais distincts trouvés, chacun compté pour son poids
          </span>
        </div>

        <div className="stat">
          <span className="stat-label" id="libelle-statut">
            Statut
          </span>
          <span className="stat-contenu">
            {aRole("supervisor") ? (
              <ChoixStatut
                statut={donnees.statut}
                statuts={Object.keys(LIBELLE_STATUT)}
                libelle="Statut de l'exposition"
                onEnregistrer={changerStatut}
              />
            ) : (
              <PastilleStatut statut={donnees.statut} />
            )}
          </span>
        </div>

        <div className="stat">
          <span className="stat-label">Catégories</span>
          <span className="stat-contenu">
            <ListeCategories categories={donnees.categories} />
          </span>
          <span className="stat-hint">celles des sélecteurs trouvés dans l'annonce</span>
        </div>

        <div className="stat">
          <span className="stat-label">Sources distinctes</span>
          <span className="stat-value">{donnees.nb_sources}</span>
          <span className="stat-hint">{donnees.sources.join(", ") || "origine non identifiée"}</span>
        </div>
      </div>

      <section className="card card-pad espace-bas" aria-labelledby="titre-chronologie">
        <h2 className="section-title" id="titre-chronologie">
          Chronologie
        </h2>
        <ol className="chronologie">
          {jalons.map((j) => (
            <li key={j.libelle}>
              <span className="chronologie-date">{formaterDateHeure(j.date)}</span>
              <span className="chronologie-libelle">{j.libelle}</span>
            </li>
          ))}
          {!donnees.date_publication_source && (
            <li className="est-absent">
              <span className="chronologie-date">—</span>
              <span className="chronologie-libelle">Publication non datée par la source</span>
            </li>
          )}
        </ol>
      </section>

      <section aria-labelledby="titre-signalements">
        <h2 className="section-title" id="titre-signalements">
          Signalements
          <span className="count">
            {donnees.signalements.length}{" "}
            {pluriel("occurrence recensée", donnees.signalements.length, "occurrences recensées")}
          </span>
        </h2>

        <div className="table-wrap tableau-cartes">
          <table className="data">
            <caption className="sr-only">Signalements de l'exposition par source</caption>
            <thead>
              <tr>
                <th scope="col">Source</th>
                <th scope="col">Type</th>
                <th scope="col">Publication</th>
                <th scope="col">Signalé le</th>
                <th scope="col">Référence</th>
              </tr>
            </thead>
            <tbody>
              {donnees.signalements.map((s) => (
                <tr key={s.id}>
                  <td className="cell-entity cell-titre">
                    {s.nom_source || <span className="cell-muted">Source non identifiée</span>}
                  </td>
                  <td className="cell-muted" data-label="Type">
                    {LIBELLE_TYPE_SOURCE[s.type_source] || s.type_source}
                  </td>
                  <td className="cell-mono" data-label="Publication">
                    {s.date_publication ? formaterDate(s.date_publication) : "non datée"}
                  </td>
                  <td className="cell-mono" data-label="Signalé le">
                    {formaterDateHeure(s.date_signalement)}
                  </td>
                  {/* La reference est affichee en clair mais JAMAIS
                      transformee en lien : ouvrir une adresse .onion depuis
                      le poste d'un analyste sortirait du cadre de collecte
                      passive et isolee (CN-07, CN-09). Tronquee a l'ecran,
                      elle se deploie au focus clavier ; les lecteurs d'ecran
                      la lisent en entier. */}
                  <td data-label="Référence">
                    <span className="cell-mono reference-source" tabIndex={0} title={s.reference_source}>
                      {s.reference_source}
                    </span>
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>

        <p className="texte-aide espace-haut">
          Les références ne sont pas cliquables : la consultation d'une source se fait exclusivement
          depuis l'environnement de collecte isolé.
        </p>
      </section>

      <Messages messages={messages} />
    </>
  );
}
