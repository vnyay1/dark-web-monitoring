/**
 * Conformite : export integral et purge definitive.
 *
 * La purge est IRREVERSIBLE. L'interface impose donc trois etapes avant
 * qu'elle ne soit possible : choisir une date, voir COMBIEN d'expositions
 * seraient detruites, puis recopier le mot de confirmation. Le decompte
 * prealable est le point important - il evite de decouvrir l'ampleur des
 * degats une fois l'action faite.
 */

import { useState } from "react";

import { api } from "../api/client";
import { useChargement, useMessages } from "../api/session";
import {
  Chargement,
  EnTetePage,
  Erreur,
  Messages,
} from "../components/communs";

export default function Conformite() {
  const { messages, ajouter } = useMessages();
  const { donnees, erreur, chargement, recharger } = useChargement(() =>
    api.conformite(),
  );

  const [dateLimite, setDateLimite] = useState("");
  const [confirmation, setConfirmation] = useState("");
  const [apercu, setApercu] = useState(null);
  const [enCours, setEnCours] = useState(false);

  const motAttendu = donnees?.mot_de_confirmation || "CONFIRMER";

  async function previsualiser() {
    setApercu(null);
    try {
      const resultat = await api.prePurge(dateLimite);
      setApercu(resultat);
    } catch (e) {
      ajouter(e.message, "error");
    }
  }

  async function purger() {
    setEnCours(true);
    try {
      const resultat = await api.purger(dateLimite, confirmation);
      ajouter(`${resultat.nb_purgees} exposition(s) supprimée(s) définitivement.`);
      setApercu(null);
      setConfirmation("");
      setDateLimite("");
      recharger();
    } catch (e) {
      ajouter(e.message, "error");
    } finally {
      setEnCours(false);
    }
  }

  if (chargement) return <Chargement />;
  if (erreur) return <Erreur message={erreur} />;

  const purgePossible =
    dateLimite && apercu && apercu.nb_concernees > 0 && confirmation === motAttendu;

  return (
    <>
      <EnTetePage
        titre="Conformité"
        sousTitre="Export d'audit externe et purge des données"
      />

      <div className="grid grid-stats" style={{ marginBottom: 24 }}>
        <div className="stat">
          <div className="stat-label">Expositions en base</div>
          <div className="stat-value">{donnees.total_expositions}</div>
          <div className="stat-hint">indicateurs conservés</div>
        </div>
      </div>

      <section className="card card-pad" style={{ marginBottom: 24 }}>
        <h2 className="section-title">Export intégral</h2>
        <p className="page-subtitle" style={{ marginBottom: 13 }}>
          Export JSON de toutes les expositions, destiné à un audit externe.
          À réaliser avant toute purge.
        </p>
        {/* Telechargement servi par Flask : un lien natif conserve le nom de
            fichier et la barre de progression du navigateur. */}
        <a className="btn" href="/compliance/export-complet">
          Télécharger l'export complet (JSON)
        </a>
      </section>

      <section className="card card-pad">
        <h2 className="section-title" style={{ color: "var(--crit)" }}>
          Purge définitive
        </h2>

        <div className="banner banner-error" role="note">
          Cette opération supprime définitivement les expositions antérieures à
          la date choisie, ainsi que leurs signalements et leurs alertes. Elle
          est <strong>irréversible</strong> et n'est annulable par aucun moyen.
        </div>

        <div className="filters" style={{ padding: 0, marginBottom: 16 }}>
          <div className="field">
            <label className="field-label" htmlFor="c-date">
              Supprimer avant le
            </label>
            <input
              id="c-date"
              className="input"
              type="date"
              value={dateLimite}
              onChange={(e) => {
                setDateLimite(e.target.value);
                setApercu(null);
                setConfirmation("");
              }}
            />
          </div>

          <div className="btn-row">
            <button
              className="btn"
              disabled={!dateLimite}
              onClick={previsualiser}
            >
              Calculer ce qui serait supprimé
            </button>
          </div>
        </div>

        {apercu && (
          <>
            <div
              className={`banner ${
                apercu.nb_concernees > 0 ? "banner-warn" : "banner-info"
              }`}
              role="status"
            >
              {apercu.nb_concernees > 0 ? (
                <>
                  <strong>{apercu.nb_concernees} exposition(s)</strong> seraient
                  supprimées définitivement (antérieures au{" "}
                  {apercu.date_limite}).
                </>
              ) : (
                <>Aucune exposition antérieure à cette date : rien à purger.</>
              )}
            </div>

            {apercu.nb_concernees > 0 && (
              <div className="filters" style={{ padding: 0 }}>
                <div className="field">
                  <label className="field-label" htmlFor="c-conf">
                    Saisissez {motAttendu} pour confirmer
                  </label>
                  <input
                    id="c-conf"
                    className="input"
                    value={confirmation}
                    onChange={(e) => setConfirmation(e.target.value)}
                    autoComplete="off"
                  />
                </div>

                <div className="btn-row">
                  <button
                    className="btn btn-danger"
                    disabled={!purgePossible || enCours}
                    onClick={purger}
                  >
                    {enCours
                      ? "Suppression…"
                      : `Supprimer définitivement ${apercu.nb_concernees} exposition(s)`}
                  </button>
                </div>
              </div>
            )}
          </>
        )}
      </section>

      <Messages messages={messages} />
    </>
  );
}
