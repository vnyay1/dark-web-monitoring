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
  dureeEntre,
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

/** Motif d'arret du parcours des pages d'une source (cf. BaseConnector). */
const LIBELLE_ARRET = {
  page_unique: "page unique",
  page_vide: "page vide",
  page_connue: "pages déjà connues",
  fin_pagination: "dernière page",
  profondeur_max: "plafond atteint",
  hors_periode: "hors période",
  dates_illisibles: "dates illisibles",
  erreur_page: "erreur de page",
};

const LIBELLE_STATUT = {
  arrete: "Arrêté",
  en_attente: "En veille",
  collecte_en_cours: "Collecte en cours",
};

const CLASSE_EVENEMENT = {
  circuit_renouvele: "ev-tor",
  debut_cycle: "ev-cycle",
  fin_cycle: "ev-cycle",
  debut_source: "ev-source",
  fin_source: "ev-source-fin",
  nouvelle_exposition: "ev-exposition",
};

const PREFIXE_EVENEMENT = {
  circuit_renouvele: "TOR",
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
  const [historiqueTronque, setHistoriqueTronque] = useState(false);
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

      // Premier passage (ouverture de la page, ou retour depuis une autre
      // page) : on recharge le cycle en cours ou le dernier cycle, puis le
      // sondage enchaine sur le direct a partir de son dernier evenement.
      // Le fil vit en base : changer de page ne perd rien.
      if (curseur.current === null) {
        const historique = await api.schedulerHistorique();
        curseur.current = historique.dernier_id;
        setLignes(historique.evenements);
        setHistoriqueTronque(Boolean(historique.tronque));
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
                ? `Processus ${etat.pid} sur ${etat.hostname}, lancé il y a ${dureeDepuis(etat.demarre_le, maintenant)}`
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
        {/* Duree du CYCLE : avance pendant une collecte, se fige a sa fin
            (on lit alors la duree du dernier cycle) et repart de zero au
            cycle suivant. L'age du processus reste sur la carte de statut. */}
        <MetriqueSched
          label={enCollecte ? "Temps écoulé" : "Durée du dernier cycle"}
          valeur={
            etat?.debut_collecte
              ? dureeEntre(etat.debut_collecte, enCollecte ? null : etat.fin_collecte, maintenant)
              : "—"
          }
          hint={
            etat?.debut_collecte
              ? enCollecte
                ? `cycle lancé à ${formaterHeure(etat.debut_collecte)} UTC`
                : `${formaterHeure(etat.debut_collecte)} → ${formaterHeure(etat.fin_collecte)} UTC`
              : "aucun cycle effectué"
          }
          accent={enCollecte}
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

      <CarteTor
        etat={etat}
        actif={actif}
        maintenant={maintenant}
        peutVerifier={peutPiloter}
        enCours={action === "ip"}
        onVerifier={() => executer("ip", api.schedulerVerifierIp)}
      />

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
              onClick={() => {
                setLignes([]);
                setHistoriqueTronque(false);
              }}
              title="Vide seulement l'affichage : le fil reste enregistré et réapparaît au prochain chargement de la page"
            >
              Vider l'affichage
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
            <>
            {historiqueTronque && (
              <div className="console-vide-note" style={{ marginBottom: 6 }}>
                … début du cycle non affiché (seules les lignes les plus récentes sont rechargées)
              </div>
            )}
            {lignes.map((ligne) => (
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
            ))}
            </>
          )}
          <div ref={finDuFil} />
        </div>
      </section>
    </>
  );
}

/**
 * Noeud de sortie Tor, tel que publie par le processus scheduler. Le
 * serveur web ne parle jamais a Tor : le bouton ne fait que demander une
 * verification au scheduler, qui la traite sous quelques secondes.
 */
function CarteTor({ etat, actif, maintenant, peutVerifier, enCours, onVerifier }) {
  const ip = etat?.ip_sortie;
  const enAttente = etat?.verification_ip_demandee;

  return (
    <section className={`card card-pad carte-tor${actif ? "" : " inactive"}`}>
      <div className="carte-tor-corps">
        <div>
          <div className="stat-label">Nœud de sortie Tor</div>
          <div className="carte-tor-ip">{ip || "—"}</div>
          <div className="stat-hint">
            {!ip
              ? "aucune IP constatée pour l'instant"
              : actif
                ? `vérifiée il y a ${dureeDepuis(etat.ip_verifiee_le, maintenant)}`
                : `dernière IP connue, vérifiée le ${formaterDateHeure(etat.ip_verifiee_le)}`}
          </div>
          {etat?.ip_sortie_precedente && (
            <div className="stat-hint">
              précédente : {etat.ip_sortie_precedente} · changement à{" "}
              {formaterHeure(etat.ip_changee_le)} UTC
            </div>
          )}
        </div>

        {peutVerifier && (
          <button
            className="btn btn-sm"
            disabled={!actif || enCours || enAttente}
            onClick={onVerifier}
            title={
              actif
                ? "Demande au planificateur de vérifier l'IP de sortie du circuit courant"
                : "Démarrez le planificateur : c'est lui qui interroge Tor"
            }
          >
            {enCours || enAttente ? "Vérification…" : "Vérifier maintenant"}
          </button>
        )}
      </div>

      <p className="carte-tor-note">
        L'IP change à chaque renouvellement de circuit. Tor peut réattribuer la
        même sortie de temps à autre ; une IP qui ne change jamais signale en
        revanche un renouvellement défaillant.
      </p>
    </section>
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
              <th title="Pages de listing parcourues, et motif de l'arrêt">Pages</th>
              <th>Entrées</th>
              <th title="Entrées dont la source ne publie pas de date, ou dans un format non reconnu">
                Sans date
              </th>
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
                <td className="cell-mono" title={LIBELLE_ARRET[s.arret] || s.arret || ""}>
                  {s.pages_listing ?? 0}
                  {s.arret && s.arret !== "page_unique" && (
                    <span className="cell-muted"> · {LIBELLE_ARRET[s.arret] || s.arret}</span>
                  )}
                </td>
                <td className="cell-mono">{s.nb_entries_brutes ?? 0}</td>
                <td className="cell-mono">{s.nb_sans_date ?? 0}</td>
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
