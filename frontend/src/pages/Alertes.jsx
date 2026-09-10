import { Link } from "react-router-dom";

import { api } from "../api/client";
import { useChargement, useMessages } from "../api/session";
import {
  Chargement,
  EnTetePage,
  Erreur,
  formaterDateHeure,
  ListeCategories,
  Messages,
  PastilleCriticite,
  Vide,
} from "../components/communs";
import "./alertes.css";

export default function Alertes() {
  const { messages, ajouter } = useMessages();
  const { donnees, erreur, chargement, recharger } = useChargement(() =>
    api.alertes(),
  );

  async function marquerLue(id) {
    try {
      await api.marquerAlerteLue(id);
      recharger();
    } catch (e) {
      ajouter(e.message, "error");
    }
  }

  async function toutMarquer() {
    try {
      const reponse = await api.toutMarquerLu();
      ajouter(`${reponse.nb_marquees} alerte(s) marquée(s) comme lue(s).`);
      recharger();
    } catch (e) {
      ajouter(e.message, "error");
    }
  }

  if (chargement) return <Chargement />;
  if (erreur) return <Erreur message={erreur} />;

  return (
    <>
      <EnTetePage
        titre="Alertes"
        sousTitre="Notifications émises sur le canal interface"
      >
        {donnees?.non_lues > 0 && (
          <button className="btn" onClick={toutMarquer}>
            Tout marquer comme lu
          </button>
        )}
      </EnTetePage>

      {donnees?.non_lues > 0 && (
        <div className="banner banner-info" role="status">
          {donnees.non_lues} alerte(s) non lue(s).
        </div>
      )}

      {!donnees || donnees.alertes.length === 0 ? (
        <Vide titre="Aucune alerte">
          Les alertes apparaîtront ici dès qu'une exposition atteindra le niveau
          de criticité configuré.
        </Vide>
      ) : (
        <div className="alertes-fil">
          {donnees.alertes.map((a) => (
            <article
              key={a.id}
              className={`alerte-carte${a.lue ? "" : " non-lue"}`}
            >
              <div className="alerte-corps">
                <div className="alerte-titre">
                  {a.exposition ? (
                    <Link to={`/expositions/${a.exposition.id}`}>
                      {a.exposition.nom_entite}
                    </Link>
                  ) : (
                    <span className="cell-muted">Exposition supprimée</span>
                  )}
                  {!a.lue && <span className="point-non-lu" aria-label="Non lue" />}
                </div>

                <div className="alerte-meta">
                  {a.exposition && (
                    <>
                      <PastilleCriticite
                        niveau={a.exposition.niveau_criticite}
                        criticite={a.exposition.criticite}
                      />
                      <ListeCategories categories={a.exposition.categories} />
                    </>
                  )}
                  <span className="cell-mono">
                    {formaterDateHeure(a.date_creation)}
                  </span>
                </div>
              </div>

              {!a.lue && (
                <button
                  className="btn btn-ghost btn-sm"
                  onClick={() => marquerLue(a.id)}
                >
                  Marquer comme lue
                </button>
              )}
            </article>
          ))}
        </div>
      )}

      <Messages messages={messages} />
    </>
  );
}
