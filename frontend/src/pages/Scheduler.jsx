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
 *
 * Defilement : seul le conteneur de la console defile, et seulement si
 * l'operateur est deja en bas du fil. S'il remonte pour lire, rien ne bouge
 * et un bouton "Revenir au direct" apparait. (scrollIntoView faisait defiler
 * TOUTE la page a chaque evenement.)
 */

import { useCallback, useEffect, useRef, useState } from "react";

import { api } from "../api/client";
import { useSession } from "../api/session";
import Confirmation from "../components/Confirmation";
import {
  Banniere,
  dureeDepuis,
  dureeEntre,
  EnTetePage,
  formaterDateHeure,
  formaterHeure,
  pluriel,
} from "../components/communs";
import { IconeActualiser, IconeArret, IconeBas, IconeLecture, IconeReseau } from "../components/icones";
import "./scheduler.css";

/** Cadence de sondage pendant une collecte, puis au repos. */
const SONDAGE_ACTIF_MS = 2000;
const SONDAGE_REPOS_MS = 8000;

/** Au-dela, les lignes les plus anciennes sont oubliees (memoire du navigateur). */
const MAX_LIGNES = 400;

/** Tolerance (px) pour considerer que la console est "en bas". */
const SEUIL_BAS_PX = 24;

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
  echeance_manquee: "ev-echeance",
  debut_cycle: "ev-cycle",
  fin_cycle: "ev-cycle",
  debut_source: "ev-source",
  fin_source: "ev-source-fin",
  nouvelle_exposition: "ev-exposition",
};

const PREFIXE_EVENEMENT = {
  circuit_renouvele: "TOR",
  echeance_manquee: "ÉCHÉANCE",
  debut_cycle: "CYCLE",
  fin_cycle: "CYCLE",
  debut_source: "SOURCE",
  fin_source: "SOURCE",
  nouvelle_exposition: "EXPOSITION",
};

/** Evenements annonces aux lecteurs d'ecran (les autres sont du detail). */
const EVENEMENTS_ANNONCES = new Set(["nouvelle_exposition", "echeance_manquee"]);

export default function Scheduler() {
  const { aRole } = useSession();
  const peutPiloter = aRole("admin");

  const [etat, setEtat] = useState(null);
  const [lignes, setLignes] = useState([]);
  const [historiqueTronque, setHistoriqueTronque] = useState(false);
  const [message, setMessage] = useState(null);
  const [action, setAction] = useState(null);
  const [confirmerArret, setConfirmerArret] = useState(false);
  const [confirmerVidage, setConfirmerVidage] = useState(false);
  const [maintenant, setMaintenant] = useState(Date.now());
  const [suitDirect, setSuitDirect] = useState(true);
  const [nonVues, setNonVues] = useState(0);
  const [annonce, setAnnonce] = useState("");

  const curseur = useRef(null);
  const console_ = useRef(null);
  const suitDirectRef = useRef(true);

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
        setLignes((precedentes) => [...precedentes, ...suite.evenements].slice(-MAX_LIGNES));
        if (!suitDirectRef.current) setNonVues((n) => n + suite.evenements.length);

        const importants = suite.evenements.filter((e) => EVENEMENTS_ANNONCES.has(e.type));
        if (importants.length > 0) {
          setAnnonce(importants.map((e) => e.message).join(". "));
        }
      }
    } catch (e) {
      setMessage({ type: "error", texte: e.message });
    }
  }, []);

  useEffect(() => {
    sonder();
  }, [sonder]);

  // Le sondage s'accelere pendant une collecte et se calme au repos.
  useEffect(() => {
    const periode = etat?.statut === "collecte_en_cours" ? SONDAGE_ACTIF_MS : SONDAGE_REPOS_MS;
    const t = setInterval(sonder, periode);
    return () => clearInterval(t);
  }, [etat?.statut, sonder]);

  // Nouvelles lignes : on ne fait defiler QUE la console, et seulement si
  // l'operateur suit le direct.
  useEffect(() => {
    const conteneur = console_.current;
    if (conteneur && suitDirectRef.current) {
      conteneur.scrollTop = conteneur.scrollHeight;
    }
  }, [lignes]);

  function surDefilementConsole() {
    const c = console_.current;
    if (!c) return;
    const enBas = c.scrollHeight - c.scrollTop - c.clientHeight <= SEUIL_BAS_PX;
    suitDirectRef.current = enBas;
    setSuitDirect(enBas);
    if (enBas) setNonVues(0);
  }

  function revenirAuDirect() {
    const c = console_.current;
    if (!c) return;
    c.scrollTop = c.scrollHeight;
    suitDirectRef.current = true;
    setSuitDirect(true);
    setNonVues(0);
  }

  async function executer(nom, appel) {
    setAction(nom);
    setMessage(null);
    try {
      const reponse = await appel();
      setMessage({ type: "success", texte: reponse.message });
      // Le processus met un instant a publier son etat : on laisse passer
      // ce delai avant de rafraichir.
      setTimeout(sonder, 900);
    } catch (e) {
      setMessage({ type: "error", texte: e.message });
      sonder();
    } finally {
      setAction(null);
    }
  }

  async function viderLogs() {
    await executer("vider", async () => {
      const reponse = await api.schedulerViderEvenements();

      // Le curseur DOIT repartir de zero : EvenementCollecte.id est un
      // entier auto-incremente sans AUTOINCREMENT, donc apres un vidage
      // SQLite reattribue les ids a partir de 1. Un curseur reste a 500 ne
      // verrait plus jamais aucun evenement, et la console resterait
      // definitivement vide. Remis a null, le prochain sondage repasse par
      // schedulerHistorique().
      curseur.current = null;
      setLignes([]);
      setHistoriqueTronque(false);
      setNonVues(0);
      return reponse;
    });
  }

  const actif = etat?.actif;
  const enCollecte = etat?.statut === "collecte_en_cours";

  return (
    <>
      <EnTetePage
        titre="Supervision de la collecte"
        sousTitre="Pilotage du planificateur et suivi en direct du pipeline"
      />

      <div className="sr-only" aria-live="polite" aria-atomic="true">
        {annonce}
      </div>

      {message && (
        <Banniere ton={message.type === "error" ? "error" : "success"} role={message.type === "error" ? "alert" : "status"}>
          <p>{message.texte}</p>
        </Banniere>
      )}

      {!peutPiloter && (
        <Banniere ton="info">
          <p>Consultation seule : le pilotage du planificateur est réservé aux administrateurs.</p>
        </Banniere>
      )}

      <section className="sched-etat card card-pad" aria-labelledby="titre-statut">
        <div className="sched-statut">
          <span className={`voyant voyant-${etat?.statut || "arrete"}`} aria-hidden="true" />
          <div>
            <h2 className="sched-statut-libelle" id="titre-statut">
              {etat ? LIBELLE_STATUT[etat.statut] || "—" : "Chargement…"}
            </h2>
            <p className="sched-statut-detail">
              {actif
                ? `Processus ${etat.pid} sur ${etat.hostname}, lancé il y a ${dureeDepuis(etat.demarre_le, maintenant)}`
                : "Aucun processus de collecte en cours d'exécution"}
            </p>
          </div>
        </div>

        {peutPiloter && (
          <div className="sched-actions">
            <div className="btn-row">
              <button
                type="button"
                className="btn btn-primary"
                disabled={actif || action !== null}
                onClick={() => executer("demarrer", api.schedulerDemarrer)}
              >
                {action === "demarrer" ? <span className="spinner" aria-hidden="true" /> : <IconeLecture taille={16} />}
                {action === "demarrer" ? "Démarrage…" : "Démarrer"}
              </button>
              <button
                type="button"
                className="btn"
                disabled={!actif || enCollecte || action !== null}
                onClick={() => executer("collecte", api.schedulerCollecteImmediate)}
                aria-describedby="aide-collecte"
              >
                {action === "collecte" ? <span className="spinner" aria-hidden="true" /> : <IconeActualiser taille={16} />}
                {action === "collecte" ? "Demande…" : "Collecte immédiate"}
              </button>
              <button
                type="button"
                className="btn btn-danger"
                disabled={!actif || action !== null}
                onClick={() => setConfirmerArret(true)}
              >
                <IconeArret taille={16} />
                {action === "arreter" ? "Arrêt…" : "Arrêter"}
              </button>
            </div>
            <p className="sched-aide" id="aide-collecte">
              {!actif
                ? "Démarrez le planificateur pour lancer une collecte."
                : enCollecte
                  ? "Une collecte est déjà en cours."
                  : "Lance un cycle sans attendre l'échéance."}
            </p>
          </div>
        )}
      </section>

      {/* Le verrou d'instance unique est le point le moins evident du
          systeme : on l'explique la ou l'operateur pourrait etre surpris
          qu'un second demarrage soit refuse. */}
      {actif && (
        <p className="sched-note">
          Un seul planificateur peut fonctionner à la fois : tout démarrage supplémentaire, depuis
          cette interface comme en ligne de commande, est refusé tant que celui-ci est actif.
        </p>
      )}

      <div className="grid grid-stats sched-metriques">
        <MetriqueSched
          label="Sources en cours"
          valeur={etat?.source_en_cours || (enCollecte ? "Préparation…" : "—")}
          hint={enCollecte ? "analyse en cours" : "aucune analyse en cours"}
          accent={enCollecte}
        />
        {/* Duree du CYCLE : avance pendant une collecte, se fige a sa fin
            et repart de zero au cycle suivant. */}
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
                ? `cycle lancé à ${formaterHeure(etat.debut_collecte)}`
                : `de ${formaterHeure(etat.debut_collecte)} à ${formaterHeure(etat.fin_collecte)}`
              : "aucun cycle effectué"
          }
          accent={enCollecte}
        />
        <MetriqueSched
          label="Dernière collecte"
          valeur={etat?.derniere_execution ? formaterHeure(etat.derniere_execution) : "—"}
          hint={etat?.derniere_execution ? formaterDateHeure(etat.derniere_execution) : "aucun cycle terminé"}
        />
        <MetriqueSched
          label="Prochaine collecte"
          valeur={
            etat?.echeance === "en_cours"
              ? "En cours"
              : etat?.prochaine_execution
                ? formaterHeure(etat.prochaine_execution)
                : "—"
          }
          hint={
            // "echeance" est calculee par le serveur (supervision) : une
            // date passee n'est jamais presentee comme la prochaine collecte.
            etat?.echeance === "en_cours"
              ? "la suivante sera tirée à la fin du cycle"
              : etat?.echeance === "depassee"
                ? `${formaterDateHeure(etat.prochaine_execution)} · échéance dépassée, reprogrammation en cours`
                : etat?.prochaine_execution
                  ? `${formaterDateHeure(etat.prochaine_execution)} · heure tirée au hasard`
                  : "non planifiée"
          }
          alerte={etat?.echeance === "depassee"}
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

      {etat?.derniere_stats && <ResumeCycle stats={etat.derniere_stats} />}

      <section className="sched-console" aria-labelledby="titre-console">
        <div className="console-barre">
          <h2 className="section-title" id="titre-console">
            Activité du pipeline
            <span className={`pill ${enCollecte ? "pill-accent" : "pill-neutral"}`}>
              {enCollecte ? "en direct" : "en veille"}
            </span>
          </h2>
          <div className="btn-row">
            {!suitDirect && (
              <button type="button" className="btn btn-sm" onClick={revenirAuDirect}>
                <IconeBas taille={14} />
                {nonVues > 0
                  ? `${nonVues} ${pluriel("nouvelle ligne", nonVues, "nouvelles lignes")}`
                  : "Revenir au direct"}
              </button>
            )}
            {peutPiloter && (
              <button
                type="button"
                className="btn btn-ghost btn-sm"
                onClick={() => setConfirmerVidage(true)}
                disabled={action === "vider"}
                aria-describedby="aide-vider"
              >
                {action === "vider" && <span className="spinner" aria-hidden="true" />}
                Vider les logs
              </button>
            )}
          </div>
        </div>

        {/* aria-live coupe sur la console : chaque ligne serait lue a voix
            haute toutes les deux secondes. Seuls les evenements importants
            sont annonces (region live separee ci-dessus). */}
        <div
          className="console"
          ref={console_}
          onScroll={surDefilementConsole}
          tabIndex={0}
          role="log"
          aria-live="off"
          aria-label="Journal d'activité du pipeline"
        >
          {lignes.length === 0 ? (
            <div className="console-vide">
              <p>En attente d'activité. Les événements du pipeline s'afficheront ici dès le prochain cycle de collecte.</p>
              <p className="console-vide-note">
                Les erreurs de collecte ne sont pas reprises ici : elles sont consultables dans le
                journal d'audit.
              </p>
            </div>
          ) : (
            <>
              {historiqueTronque && (
                <p className="console-vide-note console-tronque">
                  … début du cycle non affiché (seules les lignes les plus récentes sont rechargées)
                </p>
              )}
              {lignes.map((ligne) => (
                <div key={ligne.id} className={`console-ligne ${CLASSE_EVENEMENT[ligne.type] || ""}`}>
                  <span className="console-heure">{formaterHeure(ligne.horodatage)}</span>
                  <span className="console-type">{PREFIXE_EVENEMENT[ligne.type] || ligne.type}</span>
                  <span className="console-message">{ligne.message}</span>
                </div>
              ))}
            </>
          )}
        </div>
        <p className="texte-aide espace-haut" id="aide-vider">
          {peutPiloter
            ? "« Vider les logs » supprime définitivement le fil d'activité enregistré : il "
              + "disparaît pour tous les analystes, y compris après rechargement de la page. Le "
              + "journal d'audit et les journaux serveur (logs/*.log) ne sont pas concernés."
            : "Le fil d'activité est enregistré : il réapparaît au prochain chargement de la page. "
              + "Seul un administrateur peut le vider."}
        </p>
      </section>

      {confirmerArret && (
        <Confirmation
          titre="Arrêter le planificateur ?"
          libelleConfirmer="Arrêter"
          libelleEnCours="Arrêt…"
          enCours={action === "arreter"}
          onAnnuler={() => setConfirmerArret(false)}
          onConfirmer={async () => {
            await executer("arreter", api.schedulerArreter);
            setConfirmerArret(false);
          }}
        >
          <p>
            Plus aucune collecte n'aura lieu tant qu'il ne sera pas redémarré.
            {enCollecte && <strong> La collecte en cours sera interrompue.</strong>}
          </p>
        </Confirmation>
      )}

      {confirmerVidage && (
        <Confirmation
          titre="Vider les logs du pipeline ?"
          libelleConfirmer="Vider"
          libelleEnCours="Suppression…"
          enCours={action === "vider"}
          onAnnuler={() => setConfirmerVidage(false)}
          onConfirmer={async () => {
            await viderLogs();
            setConfirmerVidage(false);
          }}
        >
          <p>
            Le fil d'activité enregistré sera supprimé <strong>pour tous les analystes</strong>, et
            ne réapparaîtra pas au rechargement de la page. Le journal d'audit et les journaux
            serveur ne sont pas concernés.
          </p>
        </Confirmation>
      )}
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
    <section className={`card card-pad carte-tor${actif ? "" : " inactive"}`} aria-labelledby="titre-tor">
      <div className="carte-tor-corps">
        <div className="carte-tor-infos">
          <h2 className="stat-label carte-tor-titre" id="titre-tor">
            <IconeReseau taille={14} />
            Nœud de sortie Tor
          </h2>
          <p className="carte-tor-ip">{ip || "—"}</p>
          <p className="stat-hint">
            {!ip
              ? "aucune IP constatée pour l'instant"
              : actif
                ? `vérifiée il y a ${dureeDepuis(etat.ip_verifiee_le, maintenant)}`
                : `dernière IP connue, vérifiée le ${formaterDateHeure(etat.ip_verifiee_le)}`}
          </p>
          {etat?.ip_sortie_precedente && (
            <p className="stat-hint">
              précédente : {etat.ip_sortie_precedente} · changement à {formaterHeure(etat.ip_changee_le)}
            </p>
          )}
        </div>

        {peutVerifier && (
          <div className="carte-tor-action">
            <button
              type="button"
              className="btn btn-sm"
              disabled={!actif || enCours || enAttente}
              onClick={onVerifier}
              aria-describedby="aide-tor"
            >
              {enCours || enAttente ? <span className="spinner" aria-hidden="true" /> : <IconeActualiser taille={14} />}
              {enCours || enAttente ? "Vérification…" : "Vérifier maintenant"}
            </button>
            <p className="sched-aide" id="aide-tor">
              {actif
                ? "Le planificateur interroge Tor sous quelques secondes."
                : "Démarrez le planificateur : c'est lui qui interroge Tor."}
            </p>
          </div>
        )}
      </div>

      <p className="carte-tor-note">
        L'IP change à chaque renouvellement de circuit. Tor peut réattribuer la même sortie de temps à
        autre ; une IP qui ne change jamais signale en revanche un renouvellement défaillant.
      </p>
    </section>
  );
}

function MetriqueSched({ label, valeur, hint, accent, alerte }) {
  const ton = alerte ? " tone-warn" : accent ? " tone-ok" : "";
  return (
    <div className={`stat${ton}`}>
      <span className="stat-label">{label}</span>
      <span className="stat-value sched-metrique-valeur">{valeur}</span>
      {hint && <span className="stat-hint">{hint}</span>}
    </div>
  );
}

/** Resume du dernier cycle, tel que publie par le scheduler. */
function ResumeCycle({ stats }) {
  if (!Array.isArray(stats) || stats.length === 0) return null;

  return (
    <section className="espace-bas" aria-labelledby="titre-resume">
      <h2 className="section-title" id="titre-resume">
        Résultat du dernier cycle
      </h2>
      <div className="table-wrap tableau-cartes">
        <table className="data">
          <caption className="sr-only">Résultat du dernier cycle, par source</caption>
          <thead>
            <tr>
              <th scope="col">Source</th>
              <th scope="col">Collecte</th>
              <th scope="col">Pages</th>
              <th scope="col" className="num-col">Entrées</th>
              <th scope="col" className="num-col">Sans date</th>
              <th scope="col" className="num-col">Hors période</th>
              <th scope="col" className="num-col">Faux positifs</th>
              <th scope="col" className="num-col">Expositions</th>
            </tr>
          </thead>
          <tbody>
            {stats.map((s, index) => (
              <tr key={`${s.source}-${index}`}>
                <td className="cell-entity cell-titre">{s.source}</td>
                <td data-label="Collecte">
                  <span className={`pill ${s.collecte_reussie ? "pill-ok" : "pill-crit"}`}>
                    {s.collecte_reussie ? "Réussie" : "Échec"}
                  </span>
                </td>
                <td className="cell-mono" data-label="Pages">
                  {s.pages_listing ?? 0}
                  {s.arret && s.arret !== "page_unique" && (
                    <span className="cell-muted"> · {LIBELLE_ARRET[s.arret] || s.arret}</span>
                  )}
                </td>
                <td className="cell-mono num-col" data-label="Entrées">{s.nb_entries_brutes ?? 0}</td>
                <td className="cell-mono num-col" data-label="Sans date">{s.nb_sans_date ?? 0}</td>
                <td className="cell-mono num-col" data-label="Hors période">{s.nb_hors_periode ?? 0}</td>
                <td className="cell-mono num-col" data-label="Faux positifs">{s.nb_rejetees_faux_positif ?? 0}</td>
                <td className="cell-mono num-col" data-label="Expositions">{s.nb_expositions_creees_ou_maj ?? 0}</td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
      <p className="texte-aide espace-haut">
        <strong>Pages</strong> : pages de listing parcourues et motif d'arrêt. <strong>Sans date</strong>{" "}
        : entrées dont la source ne publie pas de date, ou dans un format non reconnu.
      </p>
    </section>
  );
}
