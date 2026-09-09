/**
 * Console de supervision de la collecte.
 *
 * Elle repond aux quatre questions qu'un operateur se pose devant un
 * scheduler : tourne-t-il, que fait-il en ce moment, depuis combien de
 * temps, et quand repassera-t-il ?
 *
 * Le fil d'activite est obtenu par sondage a curseur
 * (/scheduler/evenements?depuis=<id>) plutot que par flux SSE : voir
 * app/web/api/scheduler.py pour le raisonnement.
 */

import { useCallback, useEffect, useRef, useState } from "react";

import { api } from "../api/client";
import { useSession } from "../api/session";
import {
  dureeDepuis,
  EnTetePage,
  formaterDateHeure,
  formaterHeure,
} from "../components/communs";
import "./scheduler.css";

/** Cadence de sondage pendant une collecte, puis au repos. */
const SONDAGE_ACTIF_MS = 2000;
const SONDAGE_REPOS_MS = 8000;

/** Au-dela, les lignes les plus anciennes sont oubliees (memoire du navigateur). */
const MAX_LIGNES = 400;

const LIBELLE_STATUT = {
  arrete: "Arrêté",
  en_attente: "En veille",
  collecte_en_cours: "Collecte en cours",
};

const CLASSE_EVENEMENT = {
  debut_cycle: "ev-cycle",
  fin_cycle: "ev-cycle",
  debut_source: "ev-source",
  fin_source: "ev-source-fin",
  nouvelle_exposition: "ev-exposition",
};

const PREFIXE_EVENEMENT = {
  debut_cycle: "CYCLE",
  fin_cycle: "CYCLE",
  debut_source: "SOURCE",
  fin_source: "SOURCE",
  nouvelle_exposition: "EXPOSITION",
};

export default function Scheduler() {
  const { aRole } = useSession();
  const peutPiloter = aRole("admin");

  const [etat, setEtat] = useState(null);
  const [lignes, setLignes] = useState([]);
  const [message, setMessage] = useState(null);
  const [action, setAction] = useState(null);
  const [autoDefilement, setAutoDefilement] = useState(true);
  const [maintenant, setMaintenant] = useState(Date.now());

  const curseur = useRef(null);
  const finDuFil = useRef(null);

  // Horloge locale : le temps ecoule doit avancer chaque seconde sans
  // dependre du rythme des sondages reseau.
  useEffect(() => {
    const t = setInterval(() => setMaintenant(Date.now()), 1000);
    return () => clearInterval(t);
  }, []);

  const sonder = useCallback(async () => {
    try {
      const nouvelEtat = await api.schedulerEtat();
      setEtat(nouvelEtat);

      // Premier passage : on se cale sur la fin du fil pour ne pas rejouer
      // sept jours d'historique a l'ouverture de la page.
      if (curseur.current === null) {
        const depart = await api.schedulerEvenements();
        curseur.current = depart.dernier_id;
        return;
      }

      const suite = await api.schedulerEvenements(curseur.current);
      if (suite.evenements.length > 0) {
        curseur.current = suite.dernier_id;
        setLignes((precedentes) =>
          [...precedentes, ...suite.evenements].slice(-MAX_LIGNES),
        );
      }
    } catch (e) {
      setMessage({ type: "error", texte: e.message });
    }
  }, []);

  useEffect(() => {
    sonder();
  }, [sonder]);

  // Le sondage s'accelere pendant une collecte et se calme au repos :
  // inutile d'interroger le serveur toutes les deux secondes pour un
  // scheduler arrete.
  useEffect(() => {
    const periode =
      etat?.statut === "collecte_en_cours" ? SONDAGE_ACTIF_MS : SONDAGE_REPOS_MS;
    const t = setInterval(sonder, periode);
    return () => clearInterval(t);
  }, [etat?.statut, sonder]);

  useEffect(() => {
    if (autoDefilement) {
      finDuFil.current?.scrollIntoView({ block: "end" });
    }
  }, [lignes, autoDefilement]);

  async function executer(nom, appel) {
    setAction(nom);
    setMessage(null);
    try {
      const reponse = await appel();
      setMessage({ type: "success", texte: reponse.message });
      // Le processus met un instant a publier son etat : on laisse passer
      // ce delai avant de rafraichir, sinon l'affichage semblerait ignorer
      // l'action qui vient d'etre demandee.
      setTimeout(sonder, 900);
    } catch (e) {
      setMessage({ type: "error", texte: e.message });
      sonder();
    } finally {
      setAction(null);
    }
  }

  const actif = etat?.actif;
  const enCollecte = etat?.statut === "collecte_en_cours";

  return (
    <>
      <EnTetePage
        titre="Supervision de la collecte"
        sousTitre="Pilotage du planificateur et suivi en direct du pipeline"
      />

      {message && (
        <div className={`banner banner-${message.type}`} role="status">
          {message.texte}
        </div>
      )}

      {!peutPiloter && (
        <div className="banner banner-info">
          Consultation seule : le pilotage du planificateur est réservé aux
          administrateurs.
        </div>
      )}

      <div className="sched-etat card card-pad">
        <div className="sched-statut">
          <span
            className={`voyant voyant-${etat?.statut || "arrete"}`}
            aria-hidden="true"
          />
          <div>
            <div className="sched-statut-libelle">
              {LIBELLE_STATUT[etat?.statut] || "—"}
            </div>
            <div className="sched-statut-detail">
              {actif
                ? `Processus ${etat.pid} sur ${etat.hostname}`
                : "Aucun processus de collecte en cours d'exécution"}
            </div>
          </div>
        </div>

        {peutPiloter && (
          <div className="btn-row">
            <button
              className="btn btn-primary"
              disabled={actif || action !== null}
              onClick={() => executer("demarrer", api.schedulerDemarrer)}
            >
              {action === "demarrer" ? "Démarrage…" : "Démarrer"}
            </button>
            <button
              className="btn"
              disabled={!actif || enCollecte || action !== null}
              onClick={() =>
                executer("collecte", api.schedulerCollecteImmediate)
              }
              title={
                enCollecte
                  ? "Une collecte est déjà en cours"
                  : "Lancer un cycle sans attendre l'échéance"
              }
            >
              {action === "collecte" ? "Demande…" : "Collecte immédiate"}
            </button>
            <button
              className="btn btn-danger"
              disabled={!actif || action !== null}
              onClick={() => executer("arreter", api.schedulerArreter)}
            >
              {action === "arreter" ? "Arrêt…" : "Arrêter"}
            </button>
          </div>
        )}
      </div>

      {/* Le verrou d'instance unique est le point le moins evident du
          systeme : on l'explique la ou l'operateur pourrait etre surpris
          qu'un second demarrage soit refuse. */}
      {actif && (
        <p className="sched-note">
          Un seul planificateur peut fonctionner à la fois. Toute tentative de
          démarrage supplémentaire, depuis cette interface comme en ligne de
          commande, sera refusée tant que celui-ci est actif.
        </p>
      )}

      <div className="grid grid-stats sched-metriques">
        <MetriqueSched
          label="Source en cours"
          valeur={etat?.source_en_cours || (enCollecte ? "Préparation…" : "—")}
          hint={enCollecte ? "analyse en cours" : "aucune analyse en cours"}
          accent={enCollecte}
        />
        <MetriqueSched
          label="Temps écoulé"
          valeur={actif ? dureeDepuis(etat.demarre_le, maintenant) : "—"}
          hint={
            actif ? `démarré à ${formaterHeure(etat.demarre_le)} UTC` : "à l'arrêt"
          }
        />
        <MetriqueSched
          label="Dernière collecte"
          valeur={
            etat?.derniere_execution
              ? formaterHeure(etat.derniere_execution)
              : "—"
          }
          hint={
            etat?.derniere_execution
              ? formaterDateHeure(etat.derniere_execution)
              : "aucun cycle terminé"
          }
        />
        <MetriqueSched
          label="Prochaine collecte"
          valeur={
            etat?.prochaine_execution
              ? formaterHeure(etat.prochaine_execution)
              : "—"
          }
          hint={
            etat?.prochaine_execution
              ? `${formaterDateHeure(etat.prochaine_execution)} · heure tirée au hasard`
              : "non planifiée"
          }
        />
      </div>

      {etat?.derniere_stats && (
        <ResumeCycle stats={etat.derniere_stats} />
      )}

      <section className="sched-console">
        <div className="console-barre">
          <h2 className="section-title" style={{ margin: 0 }}>
            Activité du pipeline
            <span className="count">
              {enCollecte ? "en direct" : "en veille"}
            </span>
          </h2>
          <div className="btn-row">
            <label className="console-option">
              <input
                type="checkbox"
                checked={autoDefilement}
                onChange={(e) => setAutoDefilement(e.target.checked)}
              />
              Défilement automatique
            </label>
            <button
              className="btn btn-ghost btn-sm"
              onClick={() => setLignes([])}
            >
              Effacer
            </button>
          </div>
        </div>

        <div className="console" role="log" aria-live="polite">
          {lignes.length === 0 ? (
            <div className="console-vide">
              En attente d'activité. Les événements du pipeline s'afficheront
              ici dès le prochain cycle de collecte.
              <br />
              <span className="console-vide-note">
                Les erreurs de collecte ne sont pas reprises ici : elles sont
                consultables dans le journal d'audit.
              </span>
            </div>
          ) : (
            lignes.map((ligne) => (
              <div
                key={ligne.id}
                className={`console-ligne ${CLASSE_EVENEMENT[ligne.type] || ""}`}
              >
                <span className="console-heure">
                  {formaterHeure(ligne.horodatage)}
                </span>
                <span className="console-type">
                  {PREFIXE_EVENEMENT[ligne.type] || ligne.type}
                </span>
                <span className="console-message">{ligne.message}</span>
              </div>
            ))
          )}
          <div ref={finDuFil} />
        </div>
      </section>
    </>
  );
}

function MetriqueSched({ label, valeur, hint, accent }) {
  return (
    <div className={`stat${accent ? " tone-ok" : ""}`}>
      <div className="stat-label">{label}</div>
      <div className="stat-value sched-metrique-valeur">{valeur}</div>
      {hint && <div className="stat-hint">{hint}</div>}
    </div>
  );
}

/** Resume du dernier cycle, tel que publie par le scheduler. */
function ResumeCycle({ stats }) {
  if (!Array.isArray(stats) || stats.length === 0) return null;

  return (
    <section style={{ marginBottom: 20 }}>
      <h2 className="section-title">Résultat du dernier cycle</h2>
      <div className="table-wrap">
        <table className="data">
          <thead>
            <tr>
              <th>Source</th>
              <th>Collecte</th>
              <th>Entrées</th>
              <th>Hors période</th>
              <th>Faux positifs</th>
              <th>Expositions</th>
            </tr>
          </thead>
          <tbody>
            {stats.map((s, index) => (
              <tr key={`${s.source}-${index}`}>
                <td className="cell-entity">{s.source}</td>
                <td>
                  <span
                    className={`pill ${
                      s.collecte_reussie ? "pill-ok" : "pill-crit"
                    }`}
                  >
                    {s.collecte_reussie ? "Réussie" : "Échec"}
                  </span>
                </td>
                <td className="cell-mono">{s.nb_entries_brutes ?? 0}</td>
                <td className="cell-mono">{s.nb_hors_periode ?? 0}</td>
                <td className="cell-mono">{s.nb_rejetees_faux_positif ?? 0}</td>
                <td className="cell-mono">
                  {s.nb_expositions_creees_ou_maj ?? 0}
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </section>
  );
}
