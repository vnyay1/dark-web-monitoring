/**
 * Coquille de l'application : barre superieure, navigation, contenu.
 *
 * La navigation n'affiche que les entrees accessibles au role courant. Le
 * masquage est un confort d'interface, PAS une securite : chaque route de
 * l'API porte sa propre garde role_requis cote serveur.
 */

import { useEffect, useState } from "react";
import { NavLink, Outlet, useNavigate } from "react-router-dom";

import { api } from "../api/client";
import { useSession } from "../api/session";
import logoAntic from "../assets/logo-antic.png";
import { LIBELLE_ROLE } from "./communs";
import "./layout.css";

const ENTREES = [
  { chemin: "/", libelle: "Tableau de bord", exact: true },
  { chemin: "/expositions", libelle: "Expositions" },
  { chemin: "/alertes", libelle: "Alertes", badge: true },
  { chemin: "/scheduler", libelle: "Collecte" },
  { chemin: "/rapports", libelle: "Rapports", role: "supervisor" },
  { chemin: "/comptes", libelle: "Comptes", role: "admin" },
  { chemin: "/configuration", libelle: "Configuration", role: "admin" },
  { chemin: "/audit", libelle: "Audit", role: "super_admin" },
  { chemin: "/roles", libelle: "Historique rôles", role: "super_admin" },
  { chemin: "/conformite", libelle: "Conformité", role: "super_admin" },
];

export default function Layout() {
  const { utilisateur, deconnexion, aRole } = useSession();
  const navigate = useNavigate();
  const [nonLues, setNonLues] = useState(0);
  const [menuOuvert, setMenuOuvert] = useState(false);

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

  async function seDeconnecter() {
    await deconnexion();
    navigate("/connexion", { replace: true });
  }

  const entreesVisibles = ENTREES.filter((e) => !e.role || aRole(e.role));

  return (
    <div className="app-shell">
      <header className="topbar">
        <div className="topbar-inner">
          <div className="brand">
            <img className="brand-logo" src={logoAntic} alt="ANTIC" />
            <div>
              <div className="brand-name">SENTINEL</div>
              <div className="brand-sub">ANTIC · Surveillance dark web</div>
            </div>
          </div>

          <div className="topbar-right">
            <div className="user-chip">
              <span className="user-name">{utilisateur?.nom_utilisateur}</span>
              <span className={`role-tag role-${utilisateur?.role}`}>
                {LIBELLE_ROLE[utilisateur?.role] || utilisateur?.role}
              </span>
            </div>
            <button className="btn btn-ghost btn-sm" onClick={seDeconnecter}>
              Déconnexion
            </button>
            <button
              className="btn btn-ghost btn-sm nav-toggle"
              onClick={() => setMenuOuvert((o) => !o)}
              aria-expanded={menuOuvert}
              aria-label="Afficher ou masquer la navigation"
            >
              Menu
            </button>
          </div>
        </div>

        <nav className={`nav${menuOuvert ? " is-open" : ""}`} aria-label="Navigation principale">
          <div className="nav-inner">
            {entreesVisibles.map((entree) => (
              <NavLink
                key={entree.chemin}
                to={entree.chemin}
                end={entree.exact}
                className={({ isActive }) =>
                  `nav-item${isActive ? " is-active" : ""}`
                }
                onClick={() => setMenuOuvert(false)}
              >
                {entree.libelle}
                {entree.badge && nonLues > 0 && (
                  <span className="nav-badge">{nonLues}</span>
                )}
              </NavLink>
            ))}
          </div>
        </nav>
      </header>

      <main className="page">
        <Outlet context={{ rafraichirAlertes: () => setNonLues(0) }} />
      </main>
    </div>
  );
}
