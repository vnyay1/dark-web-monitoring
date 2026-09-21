/**
 * Client HTTP unique de l'application.
 *
 * Deux details portent toute la logique d'authentification :
 *
 *  - `credentials: "include"` : la session repose sur un cookie Flask-Login,
 *    pas sur un jeton. Sans cette option, fetch() n'envoie pas le cookie et
 *    toutes les requetes reviennent en 401.
 *
 *  - l'en-tete `X-Requested-With` : la couche API refuse toute requete
 *    mutante qui ne le porte pas. C'est la protection CSRF du serveur, un
 *    formulaire tiers ne pouvant pas ajouter d'en-tete personnalise.
 */

const EN_TETES_BASE = {
  "X-Requested-With": "XMLHttpRequest",
};

/** Erreur portant le code HTTP, pour que l'appelant distingue 401, 403 et 409. */
export class ErreurApi extends Error {
  constructor(message, statut, donnees) {
    super(message);
    this.name = "ErreurApi";
    this.statut = statut;
    this.donnees = donnees;
  }
}

async function requete(chemin, options = {}) {
  let reponse;

  try {
    reponse = await fetch(`/api${chemin}`, {
      ...options,
      credentials: "include",
      headers: { ...EN_TETES_BASE, ...(options.headers || {}) },
    });
  } catch {
    // Panne reseau ou serveur eteint : fetch rejette sans reponse.
    throw new ErreurApi(
      "Serveur injoignable. Verifiez que l'application Flask est demarree.",
      0,
    );
  }

  if (reponse.status === 204) return null;

  let donnees = null;
  try {
    donnees = await reponse.json();
  } catch {
    donnees = null;
  }

  if (!reponse.ok) {
    const message =
      donnees?.message || `Erreur ${reponse.status} sur ${chemin}.`;
    throw new ErreurApi(message, reponse.status, donnees);
  }

  return donnees;
}

function corpsJson(donnees) {
  return {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(donnees ?? {}),
  };
}

/** Serialise des filtres en chaine de requete, en ignorant les valeurs vides. */
function parametres(filtres = {}) {
  const params = new URLSearchParams();
  Object.entries(filtres).forEach(([cle, valeur]) => {
    if (valeur !== "" && valeur !== null && valeur !== undefined) {
      params.append(cle, valeur);
    }
  });
  const chaine = params.toString();
  return chaine ? `?${chaine}` : "";
}

export const api = {
  // --- Authentification ---
  connexion: (nom_utilisateur, mot_de_passe) =>
    requete("/auth/connexion", corpsJson({ nom_utilisateur, mot_de_passe })),
  deconnexion: () => requete("/auth/deconnexion", corpsJson()),
  moi: () => requete("/auth/moi"),
  versionSysteme: () => requete("/systeme/version"),

  // --- Tableau de bord ---
  dashboard: () => requete("/dashboard"),

  // --- Expositions ---
  expositions: (filtres) => requete(`/expositions${parametres(filtres)}`),
  // Expositions archivees (faux positif, cloturees) - admin et super_admin.
  expositionsArchivees: (filtres) => requete(`/expositions/archives${parametres(filtres)}`),
  exposition: (id) => requete(`/expositions/${id}`),
  texteSignalement: (id, signalementId) =>
    requete(`/expositions/${id}/signalements/${signalementId}/texte`),
  changerStatut: (id, statut) =>
    requete(`/expositions/${id}/statut`, corpsJson({ statut })),

  // --- Alertes ---
  alertes: () => requete("/alertes"),
  marquerAlerteLue: (id) => requete(`/alertes/${id}/marquer-lue`, corpsJson()),
  toutMarquerLu: () => requete("/alertes/tout-marquer-lu", corpsJson()),

  // --- Scheduler ---
  schedulerEtat: () => requete("/scheduler/etat"),
  schedulerEvenements: (depuis) =>
    requete(`/scheduler/evenements${depuis === undefined ? "" : `?depuis=${depuis}`}`),
  schedulerHistorique: () => requete("/scheduler/evenements?historique=cycle"),
  schedulerVerifierIp: () => requete("/scheduler/verifier-ip", corpsJson()),
  schedulerDemarrer: () => requete("/scheduler/demarrer", corpsJson()),
  schedulerArreter: () => requete("/scheduler/arreter", corpsJson()),
  schedulerCollecteImmediate: () =>
    requete("/scheduler/collecte-immediate", corpsJson()),

  // --- Configuration ---
  configuration: () => requete("/configuration"),
  modifierConfiguration: (cle, valeur) =>
    requete(`/configuration/${cle}`, corpsJson({ valeur })),
  selecteurs: () => requete("/selecteurs"),
  ajouterSelecteur: (valeur, categorie_id, poids) =>
    requete("/selecteurs", corpsJson({ valeur, categorie_id, poids })),
  modifierSelecteur: (id, valeur, categorie_id, poids) =>
    requete(`/selecteurs/${id}`, {
      ...corpsJson({ valeur, categorie_id, poids }),
      method: "PUT",
    }),

  // --- Categories (FR-13) ---
  creerCategorie: (donnees) => requete("/categories", corpsJson(donnees)),
  modifierCategorie: (id, donnees) =>
    requete(`/categories/${id}`, { ...corpsJson(donnees), method: "PUT" }),
  supprimerCategorie: (id, remplacement_id) =>
    requete(`/categories/${id}`, {
      ...corpsJson(remplacement_id ? { remplacement_id } : {}),
      method: "DELETE",
    }),
  basculerSelecteur: (id) => requete(`/selecteurs/${id}/basculer`, corpsJson()),
  supprimerSelecteur: (id) => requete(`/selecteurs/${id}`, { method: "DELETE" }),

  // --- Comptes ---
  utilisateurs: () => requete("/utilisateurs"),
  creerUtilisateur: (donnees) => requete("/utilisateurs", corpsJson(donnees)),
  changerRole: (id, role) =>
    requete(`/utilisateurs/${id}/role`, corpsJson({ role })),
  basculerActif: (id) =>
    requete(`/utilisateurs/${id}/basculer-actif`, corpsJson()),
  historiqueRoles: () => requete("/utilisateurs/historique-roles"),

  // --- Audit ---
  audit: (filtres) => requete(`/audit${parametres(filtres)}`),

  // --- Conformite ---
  conformite: () => requete("/conformite"),
  prePurge: (date_limite) =>
    requete(`/conformite/pre-purge${parametres({ date_limite })}`),
  purger: (date_limite, confirmation) =>
    requete("/conformite/purger", corpsJson({ date_limite, confirmation })),

  // --- Rapports ---
  rapportMensuel: (mois, annee) =>
    requete(`/rapports/mensuel${parametres({ mois, annee })}`),
};
