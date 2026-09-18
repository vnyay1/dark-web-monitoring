/**
 * Coquille de l'application : barre laterale groupee (ordinateur), tiroir
 * de navigation (mobile et tablette), barre superieure, contenu.
 *
 * La navigation n'affiche que les entrees accessibles au role courant. Le
 * masquage est un confort d'interface, PAS une securite : chaque route de
 * l'API porte sa propre garde role_requis cote serveur.
 *
 * Accessibilite :
 *  - lien d'evitement "Aller au contenu principal" en tout premier ;
 *  - a chaque changement de page, le titre du document est mis a jour et le
 *    focus passe sur le contenu : un lecteur d'ecran annonce la nouvelle page ;
 *  - le tiroir mobile est une fenetre modale (focus maintenu, Echap, retour
 *    du focus au bouton Menu).
 */

import { Suspense, useEffect, useRef, useState } from "react";
import { NavLink, Outlet, useLocation, useNavigate } from "react-router-dom";

import { api } from "../api/client";
import { useSession } from "../api/session";
import logoAntic from "../assets/logo-antic.png";
import { InterrupteurTheme } from "../theme/theme";
import { Banniere, Chargement, fuseauLocal, LIBELLE_ROLE } from "./communs";
import {
  IconeAlertes,
  IconeAudit,
  IconeCollecte,
  IconeComptes,
  IconeConfiguration,
  IconeConformite,
  IconeDeconnexion,
  IconeExpositions,
  IconeFermer,
  IconeHistorique,
  IconeHorloge,
  IconeMenu,
  IconeRapports,
  IconeTableauDeBord,
} from "./icones";
import { usePiegeFocus } from "./piegeFocus";
import "./layout.css";

const GROUPES = [
  {
    titre: "Surveillance",
    entrees: [
      { chemin: "/", libelle: "Tableau de bord", icone: IconeTableauDeBord, exact: true },
      { chemin: "/expositions", libelle: "Expositions", icone: IconeExpositions },
      { chemin: "/alertes", libelle: "Alertes", icone: IconeAlertes, badge: true },
    ],
  },
  {
    titre: "Opérations",
    entrees: [
      { chemin: "/scheduler", libelle: "Collecte", icone: IconeCollecte },
      { chemin: "/rapports", libelle: "Rapports", icone: IconeRapports, role: "supervisor" },
    ],
  },
  {
    titre: "Administration",
    entrees: [
      { chemin: "/comptes", libelle: "Comptes", icone: IconeComptes, role: "admin" },
      { chemin: "/configuration", libelle: "Configuration", icone: IconeConfiguration, role: "admin" },
      { chemin: "/audit", libelle: "Audit", icone: IconeAudit, role: "super_admin" },
      { chemin: "/roles", libelle: "Historique des rôles", icone: IconeHistorique, role: "super_admin" },
      { chemin: "/conformite", libelle: "Conformité", icone: IconeConformite, role: "super_admin" },
    ],
  },
];

/** Titre du document (onglet du navigateur) pour une adresse donnee. */
function titrePage(chemin) {
  if (chemin.startsWith("/expositions/")) return "Détail d'une exposition";
  for (const groupe of GROUPES) {
    const entree = groupe.entrees.find((e) => e.chemin === chemin);
    if (entree) return entree.libelle;
  }
  return null;
}

function Navigation({ nonLues, aRole, onNaviguer, idPrefixe }) {
  return (
    <nav className="navigation" aria-label="Navigation principale">
      {GROUPES.map((groupe) => {
        const visibles = groupe.entrees.filter((e) => !e.role || aRole(e.role));
        if (visibles.length === 0) return null;
        const idTitre = `${idPrefixe}-${groupe.titre}`;

        return (
          <div className="nav-groupe" key={groupe.titre}>
            <h2 className="nav-groupe-titre" id={idTitre}>
              {groupe.titre}
            </h2>
            <ul className="nav-liste" aria-labelledby={idTitre}>
              {visibles.map((entree) => {
                const Icone = entree.icone;
                const badge = entree.badge && nonLues > 0;
                return (
                  <li key={entree.chemin}>
                    <NavLink
                      to={entree.chemin}
                      end={entree.exact}
                      className={({ isActive }) => `nav-item${isActive ? " is-active" : ""}`}
                      onClick={onNaviguer}
                    >
                      <Icone taille={18} />
                      <span className="nav-libelle">{entree.libelle}</span>
                      {badge && (
                        <span className="nav-badge">
                          <span aria-hidden="true">{nonLues > 99 ? "99+" : nonLues}</span>
                          <span className="sr-only">
                            {`, ${nonLues} ${nonLues > 1 ? "alertes non lues" : "alerte non lue"}`}
                          </span>
                        </span>
                      )}
                    </NavLink>
                  </li>
                );
              })}
            </ul>
          </div>
        );
      })}
    </nav>
  );
}

function Marque() {
  return (
    <div className="brand">
      <img className="brand-logo" src={logoAntic} alt="" />
      <div>
        <div className="brand-name">SENTINEL</div>
        <div className="brand-sub">ANTIC · Surveillance</div>
      </div>
    </div>
  );
}

function PuceUtilisateur({ utilisateur }) {
  return (
    <div className="user-chip">
      <span className="user-avatar" aria-hidden="true">
        {(utilisateur?.nom_utilisateur || "?").slice(0, 1).toUpperCase()}
      </span>
      <span className="user-textes">
        <span className="user-name">{utilisateur?.nom_utilisateur}</span>
        <span className={`role-tag role-${utilisateur?.role}`}>
          {LIBELLE_ROLE[utilisateur?.role] || utilisateur?.role}
        </span>
      </span>
    </div>
  );
}

// Frequence de la verification de version : un redemarrage oublie se voit
// sans recharger la page, sans solliciter le serveur pour rien.
const INTERVALLE_VERIFICATION_VERSION_MS = 5 * 60 * 1000;

/**
 * Previent l'administrateur quand le serveur web ou le planificateur
 * executent une version du code anterieure a celle installee : apres un
 * git pull, tant qu'ils ne sont pas redemarres, les modifications ne sont
 * pas actives (cf. app/version.py).
 */
function BandeauVersion({ actif }) {
  const [version, setVersion] = useState(null);

  useEffect(() => {
    if (!actif) return undefined;
    let annule = false;
    const verifier = () =>
      api
        .versionSysteme()
        .then((v) => {
          if (!annule) setVersion(v);
        })
        .catch(() => {});

    verifier();
    const minuterie = setInterval(verifier, INTERVALLE_VERIFICATION_VERSION_MS);
    return () => {
      annule = true;
      clearInterval(minuterie);
    };
  }, [actif]);

  if (!version?.installee) return null;
  const webAncien = version.web && version.web !== version.installee;
  const planificateurAncien = version.scheduler_actif && version.scheduler !== version.installee;
  if (!webAncien && !planificateurAncien) return null;

  return (
    <div className="espace-bas">
      <Banniere ton="warn" role="status">
        {webAncien && (
          <p>
            Le serveur web exécute une ancienne version du code ({version.web}, installée : {version.installee}) :
            les dernières modifications ne sont pas actives. Redémarrez-le (arrêter puis relancer{" "}
            <code>python3 run.py</code>).
          </p>
        )}
        {planificateurAncien && (
          <p>
            Le planificateur exécute une ancienne version du code
            {version.scheduler ? ` (${version.scheduler}, installée : ${version.installee})` : ""} : la collecte
            suit l'ancienne logique. Arrêtez-le puis redémarrez-le depuis la page Collecte.
          </p>
        )}
      </Banniere>
    </div>
  );
}

export default function Layout() {
  const { utilisateur, deconnexion, aRole } = useSession();
  const navigate = useNavigate();
  const location = useLocation();
  const [nonLues, setNonLues] = useState(0);
  const [menuOuvert, setMenuOuvert] = useState(false);

  const contenu = useRef(null);
  const tiroir = useRef(null);
  const premierAffichage = useRef(true);

  // Le compteur d'alertes est rafraichi periodiquement : une detection peut
  // survenir pendant que l'operateur consulte une autre page.
  useEffect(() => {
    let annule = false;
    const rafraichir = () =>
      api
        .alertes()
        .then((d) => {
          if (!annule) setNonLues(d.non_lues);
        })
        .catch(() => {});

    rafraichir();
    const minuterie = setInterval(rafraichir, 60000);
    return () => {
      annule = true;
      clearInterval(minuterie);
    };
  }, []);

  // Changement de page : titre du document, puis focus sur le contenu (sauf
  // au tout premier affichage, pour ne pas voler le focus initial).
  useEffect(() => {
    const titre = titrePage(location.pathname);
    document.title = titre ? `${titre} · Sentinel` : "Sentinel — ANTIC";

    if (premierAffichage.current) {
      premierAffichage.current = false;
      return;
    }
    window.scrollTo(0, 0);
    contenu.current?.focus({ preventScroll: true });
  }, [location.pathname]);

  // Le tiroir n'a pas de sens sur grand ecran : il se ferme si la fenetre
  // est elargie pendant qu'il est ouvert.
  useEffect(() => {
    const grandEcran = window.matchMedia("(min-width: 1024px)");
    const surChangement = (e) => {
      if (e.matches) setMenuOuvert(false);
    };
    grandEcran.addEventListener("change", surChangement);
    return () => grandEcran.removeEventListener("change", surChangement);
  }, []);

  usePiegeFocus(menuOuvert, tiroir, { onEchap: () => setMenuOuvert(false) });

  async function seDeconnecter() {
    await deconnexion();
    navigate("/connexion", { replace: true });
  }

  return (
    <div className="app-shell">
      <a className="lien-evitement" href="#contenu">
        Aller au contenu principal
      </a>

      <aside className="barre-laterale">
        <Marque />
        <Navigation nonLues={nonLues} aRole={aRole} idPrefixe="lat" />
      </aside>

      <div className="zone-principale">
        <header className="topbar">
          <button
            type="button"
            className="btn btn-ghost btn-icone nav-toggle"
            onClick={() => setMenuOuvert(true)}
            aria-expanded={menuOuvert}
            aria-controls="tiroir-navigation"
            aria-label="Ouvrir la navigation"
          >
            <IconeMenu taille={20} />
          </button>
          <div className="topbar-marque">
            <Marque />
          </div>

          <div className="topbar-right">
            <span className="fuseau" title="Toutes les heures sont affichées dans ce fuseau">
              <IconeHorloge taille={14} />
              <span>Heure locale {fuseauLocal()}</span>
            </span>
            <InterrupteurTheme />
            <PuceUtilisateur utilisateur={utilisateur} />
            <button type="button" className="btn btn-contour btn-sm bouton-deconnexion" onClick={seDeconnecter}>
              <IconeDeconnexion taille={16} />
              <span className="bouton-deconnexion-libelle">Déconnexion</span>
            </button>
          </div>
        </header>

        <main id="contenu" className="page" tabIndex={-1} ref={contenu}>
          <BandeauVersion actif={aRole("admin")} />
          {/* Pages chargees a la demande (cf. App.jsx) : seul le contenu
              attend, la navigation reste en place. */}
          <Suspense fallback={<Chargement />}>
            <Outlet context={{ rafraichirAlertes: () => setNonLues(0), setNonLues }} />
          </Suspense>
        </main>
      </div>

      {menuOuvert && (
        <div
          className="tiroir-voile"
          onMouseDown={(e) => {
            if (e.target === e.currentTarget) setMenuOuvert(false);
          }}
        >
          <div
            id="tiroir-navigation"
            className="tiroir"
            role="dialog"
            aria-modal="true"
            aria-label="Navigation"
            ref={tiroir}
          >
            <div className="tiroir-entete">
              <Marque />
              <button
                type="button"
                className="btn btn-ghost btn-icone"
                onClick={() => setMenuOuvert(false)}
                aria-label="Fermer la navigation"
              >
                <IconeFermer taille={20} />
              </button>
            </div>
            <Navigation
              nonLues={nonLues}
              aRole={aRole}
              idPrefixe="tiroir"
              onNaviguer={() => setMenuOuvert(false)}
            />
            <div className="tiroir-pied">
              <PuceUtilisateur utilisateur={utilisateur} />
              <button type="button" className="btn btn-contour btn-sm" onClick={seDeconnecter}>
                <IconeDeconnexion taille={16} />
                Déconnexion
              </button>
            </div>
          </div>
        </div>
      )}
    </div>
  );
}
