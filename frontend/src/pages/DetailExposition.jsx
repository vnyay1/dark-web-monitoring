/**
 * Detail d'une exposition : ce qu'on sait, et surtout D'OU on le sait.
 *
 * Le tableau des signalements est la raison d'etre de cette page : une meme
 * exposition peut etre reperee sur plusieurs sources a des dates
 * differentes, ce que la liste ne pouvait pas montrer.
 */

import { Link, useNavigate, useParams } from "react-router-dom";

import { api } from "../api/client";
import { useChargement, useMessages, useSession } from "../api/session";
import {
  Chargement,
  EnTetePage,
  Erreur,
  formaterDate,
  formaterDateHeure,
  ListeCategories,
  LIBELLE_STATUT,
  LIBELLE_TYPE_SOURCE,
  Messages,
  PastilleCriticite,
  PastilleStatut,
} from "../components/communs";

export default function DetailExposition() {
  const { id } = useParams();
  const navigate = useNavigate();
  const { aRole } = useSession();
  const { messages, ajouter } = useMessages();

  const { donnees, erreur, chargement, setDonnees } = useChargement(
    () => api.exposition(id),
    [id],
  );

  async function changerStatut(statut) {
    try {
      await api.changerStatut(id, statut);
      setDonnees((precedent) => ({ ...precedent, statut }));
      ajouter(`Statut mis à jour : ${LIBELLE_STATUT[statut] || statut}.`);
    } catch (e) {
      ajouter(e.message, "error");
    }
  }

  if (chargement) return <Chargement />;
  if (erreur) return <Erreur message={erreur} />;
  if (!donnees) return null;

  return (
    <>
      <EnTetePage titre={donnees.nom_entite}>
        <button className="btn btn-ghost" onClick={() => navigate(-1)}>
          Retour
        </button>
      </EnTetePage>

      <div className="grid grid-stats" style={{ marginBottom: 22 }}>
        <div className="stat">
          <div className="stat-label">Criticité</div>
          <div style={{ marginTop: 9 }}>
            <PastilleCriticite
              niveau={donnees.niveau_criticite}
              criticite={donnees.criticite}
            />
          </div>
          <div className="stat-hint" style={{ marginTop: 7 }}>
            {donnees.criticite} sélecteur(s) camerounais distinct(s) trouvé(s)
          </div>
        </div>

        <div className="stat">
          <div className="stat-label">Statut</div>
          <div style={{ marginTop: 9 }}>
            {aRole("supervisor") ? (
              <select
                className="select"
                value={donnees.statut}
                onChange={(e) => changerStatut(e.target.value)}
                aria-label="Statut de l'exposition"
              >
                {Object.keys(LIBELLE_STATUT).map((s) => (
                  <option key={s} value={s}>
                    {LIBELLE_STATUT[s]}
                  </option>
                ))}
              </select>
            ) : (
              <PastilleStatut statut={donnees.statut} />
            )}
          </div>
        </div>

        <div className="stat">
          <div className="stat-label">Catégories</div>
          <div style={{ marginTop: 9 }}>
            <ListeCategories categories={donnees.categories} />
          </div>
          <div className="stat-hint" style={{ marginTop: 7 }}>
            celles des sélecteurs trouvés dans l'annonce
          </div>
        </div>

        <div className="stat">
          <div className="stat-label">Sources distinctes</div>
          <div className="stat-value">{donnees.nb_sources}</div>
          <div className="stat-hint">
            {donnees.sources.join(", ") || "origine non identifiée"}
          </div>
        </div>
      </div>

      <section className="card card-pad" style={{ marginBottom: 22 }}>
        <h2 className="section-title">Chronologie</h2>
        <dl className="detail-liste">
          <Ligne
            terme="Première détection"
            valeur={formaterDateHeure(donnees.date_premiere_detection)}
          />
          <Ligne
            terme="Dernière détection"
            valeur={formaterDateHeure(donnees.date_derniere_detection)}
          />
          <Ligne
            terme="Publication la plus récente"
            valeur={
              donnees.date_publication_source
                ? formaterDateHeure(donnees.date_publication_source)
                : "non datée par la source"
            }
          />
        </dl>
      </section>

      <section>
        <h2 className="section-title">
          Signalements
          <span className="count">
            {donnees.signalements.length} occurrence(s) recensée(s)
          </span>
        </h2>

        <div className="table-wrap">
          <table className="data">
            <thead>
              <tr>
                <th>Source</th>
                <th>Type</th>
                <th>Publication</th>
                <th>Signalé le</th>
                <th>Référence</th>
              </tr>
            </thead>
            <tbody>
              {donnees.signalements.map((s) => (
                <tr key={s.id}>
                  <td className="cell-entity">
                    {s.nom_source || (
                      <span className="cell-muted">non identifiée</span>
                    )}
                  </td>
                  <td className="cell-muted">
                    {LIBELLE_TYPE_SOURCE[s.type_source] || s.type_source}
                  </td>
                  <td className="cell-mono">
                    {s.date_publication ? formaterDate(s.date_publication) : "—"}
                  </td>
                  <td className="cell-mono">
                    {formaterDateHeure(s.date_signalement)}
                  </td>
                  {/* La reference est affichee en clair mais JAMAIS
                      transformee en lien : ouvrir une adresse .onion depuis
                      le poste d'un analyste sortirait du cadre de collecte
                      passive et isolee (CN-07, CN-09). */}
                  <td className="cell-mono reference-source" title={s.reference_source}>
                    {s.reference_source}
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>

        <p className="page-subtitle" style={{ marginTop: 11 }}>
          Les références ne sont pas cliquables : la consultation d'une source
          se fait exclusivement depuis l'environnement de collecte isolé.
        </p>
      </section>

      <p style={{ marginTop: 22 }}>
        <Link to="/expositions" style={{ color: "var(--accent)", fontSize: 12.5 }}>
          ← Retour à la liste des expositions
        </Link>
      </p>

      <Messages messages={messages} />
    </>
  );
}

function Ligne({ terme, valeur }) {
  return (
    <>
      <dt>{terme}</dt>
      <dd>{valeur}</dd>
    </>
  );
}
