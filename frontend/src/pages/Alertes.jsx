/**
 * Fil des alertes du canal interface, regroupe par jour.
 *
 * Marquer comme lue met la liste et le badge de navigation a jour
 * IMMEDIATEMENT (mise a jour optimiste), sans recharger la page : l'operateur
 * garde sa position et son focus. En cas d'echec, l'etat precedent revient.
 */

import { useState } from "react";
import { Link, useOutletContext } from "react-router-dom";

import { api } from "../api/client";
import { useChargement, useMessages } from "../api/session";
import {
  Chargement,
  EnTetePage,
  Erreur,
  formaterHeure,
  formaterJour,
  ListeCategories,
  Messages,
  PastilleCriticite,
  pluriel,
  Vide,
} from "../components/communs";
import { IconeAlertes, IconeValider } from "../components/icones";
import "./alertes.css";

function cleJour(iso) {
  return (iso || "").slice(0, 10);
}

export default function Alertes() {
  const { messages, ajouter } = useMessages();
  const contexte = useOutletContext();
  const { donnees, erreur, chargement, recharger, setDonnees } = useChargement(() => api.alertes());
  const [enCours, setEnCours] = useState(null);

  // Calcul hors de la fonction de mise a jour d'etat : le badge de la
  // navigation appartient a un autre composant, qu'on ne doit pas modifier
  // pendant le rendu de celui-ci.
  function appliquerLocalement(mise) {
    const alertes = donnees.alertes.map(mise);
    const nonLues = alertes.filter((a) => !a.lue).length;
    setDonnees({ ...donnees, alertes, non_lues: nonLues });
    contexte?.setNonLues?.(nonLues);
  }

  async function marquerLue(alerte) {
    const avant = donnees;
    setEnCours(alerte.id);
    appliquerLocalement((a) => (a.id === alerte.id ? { ...a, lue: true } : a));
    try {
      await api.marquerAlerteLue(alerte.id);
    } catch (e) {
      setDonnees(avant);
      contexte?.setNonLues?.(avant.non_lues);
      ajouter(e.message, "error");
    } finally {
      setEnCours(null);
    }
  }

  async function toutMarquer() {
    const avant = donnees;
    setEnCours("tout");
    appliquerLocalement((a) => ({ ...a, lue: true }));
    try {
      const reponse = await api.toutMarquerLu();
      ajouter(
        `${reponse.nb_marquees} ${pluriel("alerte marquée", reponse.nb_marquees, "alertes marquées")} comme ${pluriel("lue", reponse.nb_marquees)}.`,
      );
    } catch (e) {
      setDonnees(avant);
      contexte?.setNonLues?.(avant.non_lues);
      ajouter(e.message, "error");
    } finally {
      setEnCours(null);
    }
  }

  if (chargement) return <Chargement />;
  if (erreur && !donnees) return <Erreur message={erreur} onReessayer={recharger} />;

  const alertes = donnees?.alertes || [];
  const jours = [];
  for (const alerte of alertes) {
    const cle = cleJour(alerte.date_creation);
    let jour = jours[jours.length - 1];
    if (!jour || jour.cle !== cle) {
      jour = { cle, date: alerte.date_creation, alertes: [] };
      jours.push(jour);
    }
    jour.alertes.push(alerte);
  }

  return (
    <>
      <EnTetePage
        titre="Alertes"
        sousTitre={
          donnees?.non_lues > 0
            ? `${donnees.non_lues} ${pluriel("alerte non lue", donnees.non_lues, "alertes non lues")} sur ${alertes.length}`
            : "Notifications émises sur le canal interface"
        }
      >
        {donnees?.non_lues > 0 && (
          <button type="button" className="btn" onClick={toutMarquer} disabled={enCours !== null}>
            <IconeValider taille={16} />
            Tout marquer comme lu
          </button>
        )}
      </EnTetePage>

      <Erreur message={erreur} onReessayer={recharger} />

      {alertes.length === 0 ? (
        <Vide titre="Aucune alerte" icone={IconeAlertes}>
          Les alertes apparaîtront ici dès qu'une exposition atteindra le niveau de criticité
          configuré.
        </Vide>
      ) : (
        jours.map((jour) => (
          <section className="alertes-jour" key={jour.cle} aria-labelledby={`jour-${jour.cle}`}>
            <h2 className="alertes-jour-titre" id={`jour-${jour.cle}`}>
              {formaterJour(jour.date)}
              <span className="count">
                {jour.alertes.length} {pluriel("alerte", jour.alertes.length)}
              </span>
            </h2>
            <ul className="alertes-fil">
              {jour.alertes.map((a) => (
                <li key={a.id} className={`alerte-carte${a.lue ? "" : " non-lue"}`}>
                  <div className="alerte-corps">
                    <div className="alerte-titre">
                      {!a.lue && (
                        <span className="pill pill-accent alerte-etat">
                          <span className="point-non-lu" aria-hidden="true" />
                          Non lue
                        </span>
                      )}
                      {a.exposition ? (
                        <Link className="lien-entite" to={`/expositions/${a.exposition.id}`}>
                          {a.exposition.nom_entite}
                        </Link>
                      ) : (
                        <span className="cell-muted">Exposition supprimée</span>
                      )}
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
                      <span className="cell-mono">{formaterHeure(a.date_creation)}</span>
                    </div>
                  </div>

                  {!a.lue && (
                    <button
                      type="button"
                      className="btn btn-contour btn-sm"
                      onClick={() => marquerLue(a)}
                      disabled={enCours !== null}
                      aria-label={`Marquer comme lue l'alerte ${a.exposition?.nom_entite || ""}`.trim()}
                    >
                      <IconeValider taille={14} />
                      Marquer comme lue
                    </button>
                  )}
                </li>
              ))}
            </ul>
          </section>
        ))
      )}

      <Messages messages={messages} />
    </>
  );
}
