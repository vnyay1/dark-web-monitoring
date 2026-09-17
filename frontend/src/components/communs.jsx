/**
 * Briques d'interface partagees par toutes les pages.
 *
 * Les libelles metier (paliers de criticite, statuts, roles) sont traduits
 * ICI et nulle part ailleurs : l'API renvoie des identifiants techniques
 * ("under_review", "super_admin") qui ne doivent jamais apparaitre tels
 * quels a l'ecran.
 *
 * ACCESSIBILITE - une information n'est jamais portee par la seule couleur :
 * chaque pastille a son texte ET une icone de forme distincte.
 */

import { Link } from "react-router-dom";

import {
  IconeAttention,
  IconeCercle,
  IconeCritique,
  IconeFermer,
  IconeHorloge,
  IconeInfo,
  IconeSucces,
  IconeSuite,
} from "./icones";

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

/** Ordre de gravite, du plus grave au moins grave. */
export const ORDRE_NIVEAUX = ["critique", "elevee", "moyenne", "faible"];

const TON_STATUT = {
  new: ["pill-info", IconeInfo],
  under_review: ["pill-warn", IconeHorloge],
  confirmed: ["pill-crit", IconeAttention],
  false_positive: ["pill-neutral", IconeCercle],
  notified: ["pill-ok", IconeSucces],
  closed: ["pill-neutral", IconeSucces],
};

const TON_NIVEAU = {
  critique: ["pill-crit", IconeCritique],
  elevee: ["pill-high", IconeAttention],
  moyenne: ["pill-warn", IconeInfo],
  faible: ["pill-neutral", IconeCercle],
};

/* ------------------------------------------------------------------ */
/* Dates                                                               */
/* ------------------------------------------------------------------ */

/**
 * Les horodatages arrivent en UTC naif (sans suffixe de fuseau), tel que
 * les stocke le projet. On force donc l'interpretation en UTC ; l'AFFICHAGE
 * se fait ensuite dans le fuseau du navigateur.
 */
export function enDate(valeur) {
  if (!valeur) return null;
  const normalise = /[Zz]|[+-]\d{2}:\d{2}$/.test(valeur) ? valeur : `${valeur}Z`;
  const date = new Date(normalise);
  return Number.isNaN(date.getTime()) ? null : date;
}

/**
 * Nom court du fuseau local ("UTC+1"). Les heures de l'interface sont
 * affichees en heure LOCALE : il faut le dire, sans pretendre a de l'UTC.
 */
export function fuseauLocal() {
  const decalage = -new Date().getTimezoneOffset();
  if (decalage === 0) return "UTC";
  const signe = decalage > 0 ? "+" : "−";
  const heures = Math.floor(Math.abs(decalage) / 60);
  const minutes = Math.abs(decalage) % 60;
  return `UTC${signe}${heures}${minutes ? `:${String(minutes).padStart(2, "0")}` : ""}`;
}

export function formaterDate(valeur) {
  const date = enDate(valeur);
  return date
    ? date.toLocaleDateString("fr-FR", { day: "2-digit", month: "2-digit", year: "numeric" })
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
    ? date.toLocaleTimeString("fr-FR", { hour: "2-digit", minute: "2-digit", second: "2-digit" })
    : "—";
}

/** Date relative lisible : "aujourd'hui", "hier", sinon la date. */
export function formaterJour(valeur) {
  const date = enDate(valeur);
  if (!date) return "—";
  const debutJour = (d) => new Date(d.getFullYear(), d.getMonth(), d.getDate()).getTime();
  const ecart = Math.round((debutJour(new Date()) - debutJour(date)) / 86400000);
  if (ecart === 0) return "Aujourd'hui";
  if (ecart === 1) return "Hier";
  return date.toLocaleDateString("fr-FR", { weekday: "long", day: "numeric", month: "long", year: "numeric" });
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
  return [Math.floor(secondes / 3600), Math.floor((secondes % 3600) / 60), secondes % 60]
    .map(deuxChiffres)
    .join(":");
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

/** Accord simple : pluriel("exposition", 3) -> "expositions". */
export function pluriel(mot, nombre, forme = `${mot}s`) {
  return Math.abs(nombre) > 1 ? forme : mot;
}

/* ------------------------------------------------------------------ */
/* Pastilles                                                           */
/* ------------------------------------------------------------------ */

export function PastilleCriticite({ niveau, criticite }) {
  const [classe, Icone] = TON_NIVEAU[niveau] || ["pill-neutral", IconeCercle];

  return (
    <span className="criticite">
      <span className={`pill ${classe}`}>
        <Icone taille={13} />
        {LIBELLE_NIVEAU[niveau] || niveau}
      </span>
      {criticite !== undefined && (
        <span className="criticite-compte">
          {criticite} <abbr title="sélecteurs distincts">sél.</abbr>
          <span className="sr-only">
            {" "}
            : {criticite} {pluriel("sélecteur", criticite)} camerounais{" "}
            {pluriel("distinct", criticite)}
          </span>
        </span>
      )}
    </span>
  );
}

export function PastilleStatut({ statut }) {
  const [classe, Icone] = TON_STATUT[statut] || ["pill-neutral", IconeCercle];
  return (
    <span className={`pill ${classe}`}>
      <Icone taille={13} />
      {LIBELLE_STATUT[statut] || statut}
    </span>
  );
}

/**
 * Categories d'une exposition (FR-13) : celles des selecteurs qui l'ont
 * declenchee. Accepte des noms ou des objets {id, nom}.
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

/* ------------------------------------------------------------------ */
/* Etats                                                               */
/* ------------------------------------------------------------------ */

export function Chargement({ texte = "Chargement…" }) {
  return (
    <div className="loader" role="status">
      <span className="spinner" aria-hidden="true" />
      <span>{texte}</span>
    </div>
  );
}

/** Barre fine en haut d'ecran : un rechargement en arriere-plan. */
export function IndicateurRechargement({ actif }) {
  if (!actif) return null;
  return (
    <div className="barre-progression" role="progressbar" aria-label="Actualisation en cours" />
  );
}

export function Erreur({ message, onReessayer }) {
  if (!message) return null;
  return (
    <div className="banner banner-error" role="alert">
      <IconeAttention taille={18} />
      <div className="banner-corps">
        <p>{message}</p>
        {onReessayer && (
          <button type="button" className="btn btn-sm" onClick={onReessayer}>
            Réessayer
          </button>
        )}
      </div>
    </div>
  );
}

/** Banniere d'information ou d'avertissement, avec icone. */
export function Banniere({ ton = "info", children, role }) {
  const Icone = { info: IconeInfo, warn: IconeAttention, error: IconeAttention, success: IconeSucces }[ton];
  return (
    <div className={`banner banner-${ton}`} role={role}>
      <Icone taille={18} />
      <div className="banner-corps">{children}</div>
    </div>
  );
}

export function Vide({ titre, children, icone: Icone = IconeInfo }) {
  return (
    <div className="empty">
      <Icone taille={28} />
      <div className="empty-title">{titre}</div>
      {children && <p>{children}</p>}
    </div>
  );
}

/**
 * Chiffre cle. Avec `vers`, la tuile devient un lien vers la liste
 * correspondante (ex. les expositions de criticite haute).
 */
export function Tuile({ label, valeur, hint, ton, vers, libelleLien }) {
  const contenu = (
    <>
      <span className="stat-label">{label}</span>
      <span className="stat-value">{valeur}</span>
      {hint && <span className="stat-hint">{hint}</span>}
      {vers && (
        <span className="stat-suite" aria-hidden="true">
          {libelleLien || "Voir la liste"} <IconeSuite taille={14} />
        </span>
      )}
    </>
  );

  const classe = `stat${ton ? ` tone-${ton}` : ""}`;
  if (vers) {
    return (
      <Link to={vers} className={classe} aria-label={`${label} : ${valeur}. ${libelleLien || "Voir la liste"}`}>
        {contenu}
      </Link>
    );
  }
  return <div className={classe}>{contenu}</div>;
}

/* ------------------------------------------------------------------ */
/* Messages transitoires                                               */
/* ------------------------------------------------------------------ */

/**
 * Toasts. Le conteneur est TOUJOURS monte : une region live inseree en meme
 * temps que son contenu n'est souvent pas annoncee par les lecteurs d'ecran.
 * Les erreurs sont en role="alert" et restent jusqu'a fermeture (cf.
 * useMessages).
 */
export function Messages({ messages }) {
  return (
    <div className="toasts" aria-live="polite" aria-relevant="additions">
      {messages.map((m) => (
        <div
          key={m.id}
          className={`toast toast-${m.type}`}
          role={m.type === "error" ? "alert" : undefined}
          onMouseEnter={m.suspendre}
          onMouseLeave={m.reprendre}
          onFocus={m.suspendre}
          onBlur={m.reprendre}
        >
          {m.type === "error" ? <IconeAttention taille={18} /> : <IconeSucces taille={18} />}
          <span className="toast-texte">{m.texte}</span>
          {m.fermer && (
            <button
              type="button"
              className="btn btn-ghost btn-sm btn-icone"
              onClick={m.fermer}
              aria-label="Fermer le message"
            >
              <IconeFermer taille={16} />
            </button>
          )}
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
        {sousTitre && <p className="page-subtitle">{sousTitre}</p>}
      </div>
      {children && <div className="btn-row">{children}</div>}
    </div>
  );
}
