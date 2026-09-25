/**
 * Conformite : export integral et purge definitive.
 *
 * La purge est IRREVERSIBLE. L'interface impose trois etapes numerotees
 * avant qu'elle ne soit possible : choisir une date, voir COMBIEN
 * d'expositions seraient detruites, puis recopier le mot de confirmation. Le
 * decompte prealable est le point important - il evite de decouvrir
 * l'ampleur des degats une fois l'action faite. L'export, a faire AVANT,
 * est propose en premier.
 */

import { useState } from "react";

import { api } from "../api/client";
import { useChargement, useMessages } from "../api/session";
import {
  Banniere,
  Chargement,
  EnTetePage,
  Erreur,
  IndicateurRechargement,
  Messages,
  pluriel,
} from "../components/communs";
import { IconeAttention, IconeSupprimer, IconeTelecharger } from "../components/icones";

export default function Conformite() {
  const { messages, ajouter } = useMessages();
  const { donnees, erreur, chargement, rechargement, recharger } = useChargement(() => api.conformite());

  const [dateLimite, setDateLimite] = useState("");
  const [confirmation, setConfirmation] = useState("");
  const [apercu, setApercu] = useState(null);
  const [calcul, setCalcul] = useState(false);
  const [enCours, setEnCours] = useState(false);

  const motAttendu = donnees?.mot_de_confirmation || "CONFIRMER";

  async function previsualiser() {
    setApercu(null);
    setCalcul(true);
    try {
      setApercu(await api.prePurge(dateLimite));
    } catch (e) {
      ajouter(e.message, "error");
    } finally {
      setCalcul(false);
    }
  }

  async function purger(evenement) {
    evenement.preventDefault();
    setEnCours(true);
    try {
      const resultat = await api.purger(dateLimite, confirmation);
      ajouter(
        `${resultat.nb_purgees} ${pluriel("exposition supprimée", resultat.nb_purgees, "expositions supprimées")} `
        + `définitivement, ainsi que ${resultat.nb_audit_purgees} `
        + `${pluriel("entrée du journal d'audit", resultat.nb_audit_purgees, "entrées du journal d'audit")}.`,
      );
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
  if (erreur && !donnees) return <Erreur message={erreur} onReessayer={recharger} />;

  const etape2Faite = Boolean(apercu);
  const aSupprimer = apercu?.nb_concernees > 0;
  const motCorrect = confirmation === motAttendu;
  const purgePossible = dateLimite && aSupprimer && motCorrect;

  return (
    <>
      <IndicateurRechargement actif={rechargement} />
      <EnTetePage titre="Conformité" sousTitre="Export d'audit externe et purge des données" />

      <div className="grid grid-stats espace-bas">
        <div className="stat">
          <span className="stat-label">Expositions en base</span>
          <span className="stat-value">{donnees.total_expositions}</span>
          <span className="stat-hint">indicateurs conservés</span>
        </div>
      </div>

      <section className="card card-pad espace-bas" aria-labelledby="titre-export">
        <h2 className="section-title" id="titre-export">
          Export intégral
        </h2>
        <p className="texte-aide espace-texte">
          Export JSON de toutes les expositions, du journal d'audit et de l'historique des changements de
          rôle, destiné à un audit externe. À réaliser avant toute purge : elle supprime aussi les entrées
          anciennes du journal d'audit.
        </p>
        {/* Telechargement servi par Flask : un lien natif conserve le nom de
            fichier et la barre de progression du navigateur. */}
        <a className="btn btn-primary" href="/compliance/export-complet">
          <IconeTelecharger taille={16} />
          Télécharger l'export complet (JSON)
        </a>
      </section>

      <section className="card card-pad zone-danger" aria-labelledby="titre-purge">
        <h2 className="section-title titre-danger" id="titre-purge">
          <IconeAttention taille={18} />
          Purge définitive
        </h2>

        <Banniere ton="error">
          <p>
            Supprime définitivement les expositions antérieures à la date choisie, avec leurs signalements et
            leurs alertes, ainsi que les entrées du journal d'audit de la même période. Opération{" "}
            <strong>irréversible</strong>, annulable par aucun moyen.
          </p>
        </Banniere>

        <ol className="etapes">
          <li className={`etape${dateLimite ? " est-faite" : ""}`}>
            <div>
              <h3 className="etape-titre">Choisir la date limite</h3>
              <div className="field champ-etape">
                <label className="field-label" htmlFor="c-date">
                  Supprimer les expositions détectées et les entrées du journal d'audit
                  antérieures au
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
            </div>
          </li>

          <li className={`etape${etape2Faite ? " est-faite" : ""}${dateLimite ? "" : " est-inactive"}`}>
            <div>
              <h3 className="etape-titre">Mesurer ce qui serait supprimé</h3>
              <button type="button" className="btn" disabled={!dateLimite || calcul} onClick={previsualiser}>
                {calcul && <span className="spinner" aria-hidden="true" />}
                Calculer ce qui serait supprimé
              </button>
              {apercu && (
                <div className="espace-haut" role="status">
                  {aSupprimer ? (
                    <Banniere ton="warn">
                      <p>
                        <strong>
                          {apercu.nb_concernees} {pluriel("exposition", apercu.nb_concernees)}
                        </strong>{" "}
                        {apercu.nb_concernees > 1 ? "seraient supprimées" : "serait supprimée"} définitivement
                        (antérieures au {apercu.date_limite}).
                      </p>
                      <p>
                        Le journal d'audit est purgé sur la même date :{" "}
                        <strong>
                          {apercu.nb_audit} {pluriel("entrée", apercu.nb_audit)}
                        </strong>{" "}
                        {apercu.nb_audit > 1 ? "seraient supprimées" : "serait supprimée"}.
                      </p>
                    </Banniere>
                  ) : (
                    <Banniere ton="info">
                      <p>
                        Aucune exposition antérieure à cette date : rien à purger.
                        {apercu.nb_audit > 0 && (
                          <>
                            {" "}Le journal d'audit compte {apercu.nb_audit}{" "}
                            {pluriel("entrée", apercu.nb_audit)} de cette période, mais la purge
                            s'amorce sur les expositions.
                          </>
                        )}
                      </p>
                    </Banniere>
                  )}
                </div>
              )}
            </div>
          </li>

          <li className={`etape${aSupprimer ? "" : " est-inactive"}`}>
            <form onSubmit={purger}>
              <h3 className="etape-titre">Confirmer la suppression</h3>
              <div className="field champ-etape">
                <label className="field-label" htmlFor="c-conf">
                  Saisissez {motAttendu} pour confirmer
                </label>
                <input
                  id="c-conf"
                  className="input"
                  value={confirmation}
                  onChange={(e) => setConfirmation(e.target.value)}
                  autoComplete="off"
                  autoCapitalize="characters"
                  spellCheck={false}
                  disabled={!aSupprimer || enCours}
                  aria-describedby="c-conf-aide"
                  aria-invalid={confirmation && !motCorrect ? true : undefined}
                />
                <span className="field-aide" id="c-conf-aide">
                  {confirmation && !motCorrect
                    ? `Le mot saisi ne correspond pas à ${motAttendu}.`
                    : "Majuscules comprises."}
                </span>
              </div>
              <button type="submit" className="btn btn-danger" disabled={!purgePossible || enCours}>
                {enCours ? <span className="spinner" aria-hidden="true" /> : <IconeSupprimer taille={16} />}
                {enCours
                  ? "Suppression…"
                  : aSupprimer
                    ? `Supprimer définitivement ${apercu.nb_concernees} ${pluriel("exposition", apercu.nb_concernees)}`
                    : "Supprimer définitivement"}
              </button>
            </form>
          </li>
        </ol>
      </section>

      <Messages messages={messages} />
    </>
  );
}
