/**
 * Detail d'une exposition : ce qu'on sait, et surtout D'OU on le sait.
 *
 * Le tableau des signalements est la raison d'etre de cette page : une meme
 * exposition peut etre reperee sur plusieurs sources a des dates
 * differentes, ce que la liste ne pouvait pas montrer.
 *
 * Un superviseur peut derouler, sous chaque signalement, le texte conserve
 * de l'annonce (derogation CN-04/CN-05, cf. app/conservation.py). Il n'est
 * charge qu'au premier clic, par un appel dedie.
 */

import { Fragment, useState } from "react";
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
import { IconeAttention, IconeBas, IconeHaut, IconeRetour } from "../components/icones";

export default function DetailExposition() {
  const { id } = useParams();
  const location = useLocation();
  const { aRole } = useSession();
  const { messages, ajouter } = useMessages();

  const { donnees, erreur, chargement, recharger, setDonnees } = useChargement(
    () => api.exposition(id),
    [id],
  );

  // Texte des annonces : identifiant du signalement -> deroule ou non. Une
  // cle absente = jamais ouvert, donc jamais charge.
  const peutLireTexte = aRole("supervisor");
  const [ouverts, setOuverts] = useState({});
  const basculerTexte = (signalementId) =>
    setOuverts((precedent) => ({ ...precedent, [signalementId]: !precedent[signalementId] }));

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
                {peutLireTexte && <th scope="col">Texte de l'annonce</th>}
              </tr>
            </thead>
            <tbody>
              {donnees.signalements.map((s) => (
                <Fragment key={s.id}>
                  <tr>
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
                    {peutLireTexte && (
                      <td data-label="Texte de l'annonce">
                        {s.texte_disponible ? (
                          <button
                            type="button"
                            className="btn btn-contour btn-sm"
                            aria-expanded={Boolean(ouverts[s.id])}
                            aria-controls={`texte-${s.id}`}
                            onClick={() => basculerTexte(s.id)}
                          >
                            {ouverts[s.id] ? <IconeHaut taille={14} /> : <IconeBas taille={14} />}
                            Détails
                            <span className="sr-only"> : texte de l'annonce sur {s.nom_source || "cette source"}</span>
                          </button>
                        ) : (
                          <span className="cell-muted">Non conservé</span>
                        )}
                      </td>
                    )}
                  </tr>
                  {peutLireTexte && s.texte_disponible && (
                    <tr className="ligne-texte-brut" id={`texte-${s.id}`} hidden={!ouverts[s.id]}>
                      <td colSpan={6}>
                        {s.id in ouverts && <TexteAnnonce expositionId={id} signalementId={s.id} />}
                      </td>
                    </tr>
                  )}
                </Fragment>
              ))}
            </tbody>
          </table>
        </div>

        <p className="texte-aide espace-haut">
          Les références ne sont pas cliquables : la consultation d'une source se fait exclusivement
          depuis l'environnement de collecte isolé.
          {peutLireTexte &&
            " Le texte d'une annonce n'est conservé que pour une durée limitée : « Non conservé » " +
              "signale un texte collecté avant cette fonction, ou déjà effacé."}
        </p>
      </section>

      <Messages messages={messages} />
    </>
  );
}

/** Texte conserve d'une annonce, charge au premier deroulement. */
function TexteAnnonce({ expositionId, signalementId }) {
  const { donnees, erreur, chargement, recharger } = useChargement(
    () => api.texteSignalement(expositionId, signalementId),
    [expositionId, signalementId],
  );

  if (chargement) return <Chargement texte="Chargement du texte de l'annonce…" />;
  if (erreur && !donnees) return <Erreur message={erreur} onReessayer={recharger} />;
  if (!donnees) return null;

  return (
    <div className="texte-annonce">
      <p className="texte-annonce-avertissement">
        <IconeAttention taille={16} />
        <span>
          Texte issu d'une source clandestine : à consulter uniquement depuis l'environnement isolé, sans le
          recopier ailleurs. Adresses email, numéros, empreintes et mots de passe annoncés sont masqués ; les
          noms de personnes ne le sont pas.
        </span>
      </p>
      <p className="texte-annonce-meta">
        {donnees.longueur.toLocaleString("fr-FR")} {pluriel("caractère", donnees.longueur)} · conservé le{" "}
        {formaterDateHeure(donnees.date_texte_brut)}
      </p>
      <pre className="texte-annonce-corps" tabIndex={0} aria-label="Texte de l'annonce">
        {donnees.texte}
      </pre>
    </div>
  );
}
