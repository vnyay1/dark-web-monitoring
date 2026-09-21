/**
 * Icones de l'interface, en SVG inline.
 *
 * Traces issus de Lucide (https://lucide.dev, licence ISC), recopies ici
 * plutot qu'ajoutes en dependance : l'ensemble tient en quelques Ko, ne
 * charge rien a l'execution et n'etend pas la chaine d'approvisionnement.
 *
 * Une icone est DECORATIVE par defaut (aria-hidden) : le texte qui
 * l'accompagne porte le sens. Passer `titre` quand l'icone est seule.
 */

function fabriquer(nom, contenu) {
  function Icone({ taille = 18, className = "", titre, ...reste }) {
    return (
      <svg
        xmlns="http://www.w3.org/2000/svg"
        width={taille}
        height={taille}
        viewBox="0 0 24 24"
        fill="none"
        stroke="currentColor"
        strokeWidth="1.9"
        strokeLinecap="round"
        strokeLinejoin="round"
        className={`icone ${className}`}
        aria-hidden={titre ? undefined : "true"}
        role={titre ? "img" : undefined}
        focusable="false"
        {...reste}
      >
        {titre && <title>{titre}</title>}
        {contenu}
      </svg>
    );
  }
  Icone.displayName = nom;
  return Icone;
}

const BOUCLIER =
  "M20 13c0 5-3.5 7.5-7.66 8.95a1 1 0 0 1-.67-.01C7.5 20.5 4 18 4 13V6a1 1 0 0 1 1-1c2 0 4.5-1.2 6.24-2.72a1.17 1.17 0 0 1 1.52 0C14.51 3.81 17 5 19 5a1 1 0 0 1 1 1z";

export const IconeTableauDeBord = fabriquer("IconeTableauDeBord", (
  <>
    <rect width="7" height="9" x="3" y="3" rx="1" />
    <rect width="7" height="5" x="14" y="3" rx="1" />
    <rect width="7" height="9" x="14" y="12" rx="1" />
    <rect width="7" height="5" x="3" y="16" rx="1" />
  </>
));

export const IconeExpositions = fabriquer("IconeExpositions", (
  <>
    <path d={BOUCLIER} />
    <path d="M12 8v4" />
    <path d="M12 16h.01" />
  </>
));

// Lucide "archive" : le carton d'archives, couvercle puis corps.
export const IconeArchives = fabriquer("IconeArchives", (
  <>
    <rect width="20" height="5" x="2" y="3" rx="1" />
    <path d="M4 8v11a2 2 0 0 0 2 2h12a2 2 0 0 0 2-2V8" />
    <path d="M10 12h4" />
  </>
));

export const IconeAlertes = fabriquer("IconeAlertes", (
  <>
    <path d="M6 8a6 6 0 0 1 12 0c0 7 3 9 3 9H3s3-2 3-9" />
    <path d="M10.3 21a1.94 1.94 0 0 0 3.4 0" />
  </>
));

export const IconeCollecte = fabriquer("IconeCollecte", (
  <path d="M22 12h-4l-3 9L9 3l-3 9H2" />
));

export const IconeRapports = fabriquer("IconeRapports", (
  <>
    <path d="M15 2H6a2 2 0 0 0-2 2v16a2 2 0 0 0 2 2h12a2 2 0 0 0 2-2V7Z" />
    <path d="M14 2v4a2 2 0 0 0 2 2h4" />
    <path d="M10 9H8" />
    <path d="M16 13H8" />
    <path d="M16 17H8" />
  </>
));

export const IconeComptes = fabriquer("IconeComptes", (
  <>
    <path d="M16 21v-2a4 4 0 0 0-4-4H6a4 4 0 0 0-4 4v2" />
    <circle cx="9" cy="7" r="4" />
    <path d="M22 21v-2a4 4 0 0 0-3-3.87" />
    <path d="M16 3.13a4 4 0 0 1 0 7.75" />
  </>
));

export const IconeConfiguration = fabriquer("IconeConfiguration", (
  <>
    <line x1="21" x2="14" y1="4" y2="4" />
    <line x1="10" x2="3" y1="4" y2="4" />
    <line x1="21" x2="12" y1="12" y2="12" />
    <line x1="8" x2="3" y1="12" y2="12" />
    <line x1="21" x2="16" y1="20" y2="20" />
    <line x1="12" x2="3" y1="20" y2="20" />
    <line x1="14" x2="14" y1="2" y2="6" />
    <line x1="8" x2="8" y1="10" y2="14" />
    <line x1="16" x2="16" y1="18" y2="22" />
  </>
));

export const IconeAudit = fabriquer("IconeAudit", (
  <>
    <rect width="8" height="4" x="8" y="2" rx="1" ry="1" />
    <path d="M16 4h2a2 2 0 0 1 2 2v14a2 2 0 0 1-2 2H6a2 2 0 0 1-2-2V6a2 2 0 0 1 2-2h2" />
    <path d="M12 11h4" />
    <path d="M12 16h4" />
    <path d="M8 11h.01" />
    <path d="M8 16h.01" />
  </>
));

export const IconeHistorique = fabriquer("IconeHistorique", (
  <>
    <path d="M3 12a9 9 0 1 0 9-9 9.75 9.75 0 0 0-6.74 2.74L3 8" />
    <path d="M3 3v5h5" />
    <path d="M12 7v5l4 2" />
  </>
));

export const IconeConformite = fabriquer("IconeConformite", (
  <>
    <path d={BOUCLIER} />
    <path d="m9 12 2 2 4-4" />
  </>
));

export const IconeSoleil = fabriquer("IconeSoleil", (
  <>
    <circle cx="12" cy="12" r="4" />
    <path d="M12 2v2" />
    <path d="M12 20v2" />
    <path d="m4.93 4.93 1.41 1.41" />
    <path d="m17.66 17.66 1.41 1.41" />
    <path d="M2 12h2" />
    <path d="M20 12h2" />
    <path d="m6.34 17.66-1.41 1.41" />
    <path d="m19.07 4.93-1.41 1.41" />
  </>
));

export const IconeLune = fabriquer("IconeLune", (
  <path d="M12 3a6 6 0 0 0 9 9 9 9 0 1 1-9-9Z" />
));

export const IconeMenu = fabriquer("IconeMenu", (
  <>
    <line x1="4" x2="20" y1="12" y2="12" />
    <line x1="4" x2="20" y1="6" y2="6" />
    <line x1="4" x2="20" y1="18" y2="18" />
  </>
));

export const IconeFermer = fabriquer("IconeFermer", (
  <>
    <path d="M18 6 6 18" />
    <path d="m6 6 12 12" />
  </>
));

export const IconeDeconnexion = fabriquer("IconeDeconnexion", (
  <>
    <path d="M9 21H5a2 2 0 0 1-2-2V5a2 2 0 0 1 2-2h4" />
    <polyline points="16 17 21 12 16 7" />
    <line x1="21" x2="9" y1="12" y2="12" />
  </>
));

export const IconeOeil = fabriquer("IconeOeil", (
  <>
    <path d="M2 12s3-7 10-7 10 7 10 7-3 7-10 7-10-7-10-7Z" />
    <circle cx="12" cy="12" r="3" />
  </>
));

export const IconeOeilBarre = fabriquer("IconeOeilBarre", (
  <>
    <path d="M9.88 9.88a3 3 0 1 0 4.24 4.24" />
    <path d="M10.73 5.08A10.43 10.43 0 0 1 12 5c7 0 10 7 10 7a13.16 13.16 0 0 1-1.67 2.68" />
    <path d="M6.61 6.61A13.53 13.53 0 0 0 2 12s3 7 10 7a9.74 9.74 0 0 0 5.39-1.61" />
    <line x1="2" x2="22" y1="2" y2="22" />
  </>
));

export const IconeHaut = fabriquer("IconeHaut", <path d="m18 15-6-6-6 6" />);
export const IconeBas = fabriquer("IconeBas", <path d="m6 9 6 6 6-6" />);
export const IconeTri = fabriquer("IconeTri", (
  <>
    <path d="m7 15 5 5 5-5" />
    <path d="m7 9 5-5 5 5" />
  </>
));

export const IconeRetour = fabriquer("IconeRetour", (
  <>
    <path d="m12 19-7-7 7-7" />
    <path d="M19 12H5" />
  </>
));

export const IconeSuite = fabriquer("IconeSuite", (
  <>
    <path d="M5 12h14" />
    <path d="m12 5 7 7-7 7" />
  </>
));

export const IconeAttention = fabriquer("IconeAttention", (
  <>
    <path d="m21.73 18-8-14a2 2 0 0 0-3.48 0l-8 14A2 2 0 0 0 4 21h16a2 2 0 0 0 1.73-3" />
    <path d="M12 9v4" />
    <path d="M12 17h.01" />
  </>
));

export const IconeCritique = fabriquer("IconeCritique", (
  <>
    <path d="M12 16h.01" />
    <path d="M12 8v4" />
    <path d="M15.31 2a2 2 0 0 1 1.42.59l4.68 4.68A2 2 0 0 1 22 8.69v6.62a2 2 0 0 1-.59 1.42l-4.68 4.68a2 2 0 0 1-1.42.59H8.69a2 2 0 0 1-1.42-.59l-4.68-4.68A2 2 0 0 1 2 15.31V8.69a2 2 0 0 1 .59-1.42l4.68-4.68A2 2 0 0 1 8.69 2z" />
  </>
));

export const IconeSucces = fabriquer("IconeSucces", (
  <>
    <circle cx="12" cy="12" r="10" />
    <path d="m9 12 2 2 4-4" />
  </>
));

export const IconeInfo = fabriquer("IconeInfo", (
  <>
    <circle cx="12" cy="12" r="10" />
    <path d="M12 16v-4" />
    <path d="M12 8h.01" />
  </>
));

export const IconeCercle = fabriquer("IconeCercle", <circle cx="12" cy="12" r="9" />);

export const IconeTelecharger = fabriquer("IconeTelecharger", (
  <>
    <path d="M21 15v4a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2v-4" />
    <polyline points="7 10 12 15 17 10" />
    <line x1="12" x2="12" y1="15" y2="3" />
  </>
));

export const IconeRecherche = fabriquer("IconeRecherche", (
  <>
    <circle cx="11" cy="11" r="8" />
    <path d="m21 21-4.3-4.3" />
  </>
));

export const IconeActualiser = fabriquer("IconeActualiser", (
  <>
    <path d="M3 12a9 9 0 0 1 9-9 9.75 9.75 0 0 1 6.74 2.74L21 8" />
    <path d="M21 3v5h-5" />
    <path d="M21 12a9 9 0 0 1-9 9 9.75 9.75 0 0 1-6.74-2.74L3 16" />
    <path d="M8 16H3v5" />
  </>
));

export const IconeLecture = fabriquer("IconeLecture", <polygon points="6 3 20 12 6 21 6 3" />);
export const IconeArret = fabriquer("IconeArret", <rect width="14" height="14" x="5" y="5" rx="2" />);
export const IconeValider = fabriquer("IconeValider", <path d="M20 6 9 17l-5-5" />);
export const IconeAjouter = fabriquer("IconeAjouter", (
  <>
    <path d="M5 12h14" />
    <path d="M12 5v14" />
  </>
));

export const IconeModifier = fabriquer("IconeModifier", (
  <path d="M21.17 6.81a1 1 0 0 0-3.99-3.99L3.84 16.17a2 2 0 0 0-.5.83l-1.32 4.35a.5.5 0 0 0 .62.62l4.35-1.32a2 2 0 0 0 .83-.5z" />
));

export const IconeSupprimer = fabriquer("IconeSupprimer", (
  <>
    <path d="M3 6h18" />
    <path d="M19 6v14c0 1-1 2-2 2H7c-1 0-2-1-2-2V6" />
    <path d="M8 6V4c0-1 1-2 2-2h4c1 0 2 1 2 2v2" />
    <line x1="10" x2="10" y1="11" y2="17" />
    <line x1="14" x2="14" y1="11" y2="17" />
  </>
));

export const IconeReseau = fabriquer("IconeReseau", (
  <>
    <circle cx="12" cy="12" r="10" />
    <path d="M12 2a14.5 14.5 0 0 0 0 20 14.5 14.5 0 0 0 0-20" />
    <path d="M2 12h20" />
  </>
));

export const IconeSources = fabriquer("IconeSources", (
  <>
    <ellipse cx="12" cy="5" rx="9" ry="3" />
    <path d="M3 5V19A9 3 0 0 0 21 19V5" />
    <path d="M3 12A9 3 0 0 0 21 12" />
  </>
));

export const IconeHorloge = fabriquer("IconeHorloge", (
  <>
    <circle cx="12" cy="12" r="10" />
    <polyline points="12 6 12 12 16 14" />
  </>
));
