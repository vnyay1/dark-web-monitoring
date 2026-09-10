/**
 * Briques d'interface partagees par toutes les pages.
 *
 * Les libelles metier (paliers de criticite, statuts, categories) sont
 * traduits ICI et nulle part ailleurs : l'API renvoie des identifiants
 * techniques ("donnees_personnelles", "under_review") qui ne doivent jamais
 * apparaitre tels quels a l'ecran.
 */

/* ------------------------------------------------------------------ */
/* Libelles                                                            */
/* ------------------------------------------------------------------ */

export const LIBELLE_NIVEAU = {
  critique: "Critique",
  elevee: "Élevée",
  moyenne: "Moyenne",
  faible: "Faible",
};

export const LIBELLE_STATUT = {
  new: "Nouvelle",
  under_review: "En cours d'analyse",
  confirmed: "Confirmée",
  false_positive: "Faux positif",
  notified: "Notifiée",
  closed: "Clôturée",
};

export const LIBELLE_ROLE = {
  user: "Analyste",
  supervisor: "Superviseur",
  admin: "Administrateur",
  super_admin: "Super-administrateur",
};

export const LIBELLE_TYPE_SOURCE = {
  ransomware_site: "Site de rançongiciel",
  paste: "Service de paste",
  forum: "Forum",
  telegram: "Telegram",
  test_clairnet: "Test (clairnet)",
};

const TON_STATUT = {
  new: "pill-info",
  under_review: "pill-warn",
  confirmed: "pill-crit",
  false_positive: "pill-neutral",
  notified: "pill-ok",
  closed: "pill-neutral",
};

const TON_NIVEAU = {
  critique: "pill-crit",
  elevee: "pill-high",
  moyenne: "pill-warn",
  faible: "pill-neutral",
};

/* ------------------------------------------------------------------ */
/* Dates                                                               */
/* ------------------------------------------------------------------ */

/**
 * Les horodatages arrivent en UTC naif (sans suffixe de fuseau), tel que
 * les stocke le projet. On force donc l'interpretation en UTC : sans le
 * "Z", le navigateur les lirait comme des heures locales et afficherait un
 * decalage silencieux.
 */
function enDate(valeur) {
  if (!valeur) return null;
  const normalise = /[Zz]|[+-]\d{2}:\d{2}$/.test(valeur) ? valeur : `${valeur}Z`;
  const date = new Date(normalise);
  return Number.isNaN(date.getTime()) ? null : date;
}

export function formaterDate(valeur) {
  const date = enDate(valeur);
  return date
    ? date.toLocaleDateString("fr-FR", {
        day: "2-digit",
        month: "2-digit",
        year: "numeric",
      })
    : "—";
}

export function formaterDateHeure(valeur) {
  const date = enDate(valeur);
  return date
    ? date.toLocaleString("fr-FR", {
        day: "2-digit",
        month: "2-digit",
        year: "numeric",
        hour: "2-digit",
        minute: "2-digit",
      })
    : "—";
}

export function formaterHeure(valeur) {
  const date = enDate(valeur);
  return date
    ? date.toLocaleTimeString("fr-FR", {
        hour: "2-digit",
        minute: "2-digit",
        second: "2-digit",
      })
    : "—";
}

/**
 * Duree entre deux instants au format chronometre "HH:MM:SS". `fin` absent
 * signifie "maintenant" : c'est ce qui fait avancer un compteur en cours.
 */
export function dureeEntre(debut, fin, maintenant = Date.now()) {
  const depart = enDate(debut);
  if (!depart) return "—";

  const arrivee = fin ? enDate(fin) : null;
  const finMs = arrivee ? arrivee.getTime() : maintenant;
  const secondes = Math.max(0, Math.floor((finMs - depart.getTime()) / 1000));

  const deuxChiffres = (n) => String(n).padStart(2, "0");
  return [
    Math.floor(secondes / 3600),
    Math.floor((secondes % 3600) / 60),
    secondes % 60,
  ].map(deuxChiffres).join(":");
}

/** Duree lisible depuis un instant donne, ex. "2 h 14 min". */
export function dureeDepuis(valeur, maintenant = Date.now()) {
  const date = enDate(valeur);
  if (!date) return "—";

  const secondes = Math.max(0, Math.floor((maintenant - date.getTime()) / 1000));
  const jours = Math.floor(secondes / 86400);
  const heures = Math.floor((secondes % 86400) / 3600);
  const minutes = Math.floor((secondes % 3600) / 60);

  if (jours > 0) return `${jours} j ${heures} h`;
  if (heures > 0) return `${heures} h ${minutes} min`;
  if (minutes > 0) return `${minutes} min ${secondes % 60} s`;
  return `${secondes} s`;
}

/* ------------------------------------------------------------------ */
/* Composants                                                          */
/* ------------------------------------------------------------------ */

export function PastilleCriticite({ niveau, criticite }) {
  const titre =
    criticite === undefined
      ? undefined
      : `${criticite} sélecteur(s) camerounais distinct(s) trouvé(s) dans l'annonce`;

  return (
    <span
      style={{ display: "inline-flex", alignItems: "center", gap: 7 }}
      title={titre}
    >
      <span className={`pill ${TON_NIVEAU[niveau] || "pill-neutral"}`}>
        {LIBELLE_NIVEAU[niveau] || niveau}
      </span>
      {criticite !== undefined && (
        <span className="cell-mono" style={{ color: "var(--text-muted)" }}>
          {criticite} sél.
        </span>
      )}
    </span>
  );
}

export function PastilleStatut({ statut }) {
  return (
    <span className={`pill ${TON_STATUT[statut] || "pill-neutral"}`}>
      {LIBELLE_STATUT[statut] || statut}
    </span>
  );
}

/**
 * Categories d'une exposition (FR-13) : celles des selecteurs qui l'ont
 * declenchee. Accepte des noms ou des objets {id, nom}. Ce sont des
 * enregistrements deja libelles, geres par l'administrateur.
 */
export function ListeCategories({ categories }) {
  if (!categories || categories.length === 0) {
    return <span className="cell-muted">—</span>;
  }
  return (
    <span className="tag-row">
      {categories.map((c) => {
        const nom = typeof c === "string" ? c : c.nom;
        return (
          <span className="etiquette-categorie" key={nom}>
            {nom}
          </span>
        );
      })}
    </span>
  );
}

export function ListeSources({ sources }) {
  if (!sources || sources.length === 0) {
    return <span className="cell-muted">—</span>;
  }
  return (
    <span className="tag-row">
      {sources.map((nom) => (
        <span className="tag" key={nom}>
          {nom}
        </span>
      ))}
    </span>
  );
}

export function Chargement({ texte = "Chargement…" }) {
  return (
    <div className="loader">
      <span className="spinner" aria-hidden="true" />
      <span>{texte}</span>
    </div>
  );
}

export function Erreur({ message }) {
  if (!message) return null;
  return (
    <div className="banner banner-error" role="alert">
      {message}
    </div>
  );
}

export function Vide({ titre, children }) {
  return (
    <div className="empty">
      <div className="empty-title">{titre}</div>
      {children}
    </div>
  );
}

export function Tuile({ label, valeur, hint, ton }) {
  return (
    <div className={`stat${ton ? ` tone-${ton}` : ""}`}>
      <div className="stat-label">{label}</div>
      <div className="stat-value">{valeur}</div>
      {hint && <div className="stat-hint">{hint}</div>}
    </div>
  );
}

export function Messages({ messages }) {
  if (messages.length === 0) return null;
  return (
    <div className="toasts" aria-live="polite">
      {messages.map((m) => (
        <div key={m.id} className={`toast toast-${m.type}`}>
          {m.texte}
        </div>
      ))}
    </div>
  );
}

export function EnTetePage({ titre, sousTitre, children }) {
  return (
    <div className="page-header">
      <div>
        <h1 className="page-title">{titre}</h1>
        {sousTitre && <div className="page-subtitle">{sousTitre}</div>}
      </div>
      {children && <div className="btn-row">{children}</div>}
    </div>
  );
}
