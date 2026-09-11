/**
 * Routage de l'application.
 *
 * Deux niveaux de protection cote client :
 *  - RouteProtegee : exige une session ouverte ;
 *  - l'attribut `role` d'une route : exige un rang minimum.
 *
 * Ce n'est qu'une commodite d'affichage. L'autorisation qui fait foi est
 * celle du serveur : chaque endpoint porte @role_requis, et un utilisateur
 * qui forcerait une URL n'obtiendrait qu'un 403 en JSON.
 *
 * Chaque page est chargee a la demande (React.lazy) : l'ecran de connexion
 * ne telecharge plus le code de toutes les pages, ni surtout Recharts, qui
 * ne sert qu'au tableau de bord et pese plus que tout le reste. Le Suspense
 * des pages protegees est dans Layout, pour que la navigation reste
 * affichee pendant le chargement d'une page.
 */

import { lazy, Suspense } from "react";
import { Navigate, Route, Routes } from "react-router-dom";

import { useSession } from "./api/session";
import Layout from "./components/Layout";
import { Chargement } from "./components/communs";

const Alertes = lazy(() => import("./pages/Alertes"));
const Audit = lazy(() => import("./pages/Audit"));
const Comptes = lazy(() => import("./pages/Comptes"));
const Configuration = lazy(() => import("./pages/Configuration"));
const Conformite = lazy(() => import("./pages/Conformite"));
const Connexion = lazy(() => import("./pages/Connexion"));
const Dashboard = lazy(() => import("./pages/Dashboard"));
const DetailExposition = lazy(() => import("./pages/DetailExposition"));
const Expositions = lazy(() => import("./pages/Expositions"));
const HistoriqueRoles = lazy(() => import("./pages/HistoriqueRoles"));
const Rapports = lazy(() => import("./pages/Rapports"));
const Scheduler = lazy(() => import("./pages/Scheduler"));

function RouteProtegee({ children, role }) {
  const { utilisateur, chargement, aRole } = useSession();

  // Tant que /auth/moi n'a pas repondu, on ne sait pas si une session
  // existe : rediriger maintenant deconnecterait l'utilisateur a chaque
  // rechargement de page.
  if (chargement) return <Chargement texte="Vérification de la session…" />;

  if (!utilisateur) return <Navigate to="/connexion" replace />;

  if (role && !aRole(role)) {
    return (
      <div className="page">
        <div className="banner banner-error" role="alert">
          Vous ne disposez pas des privilèges nécessaires pour consulter cette
          page.
        </div>
      </div>
    );
  }

  return children;
}

export default function App() {
  return (
    <Routes>
      <Route
        path="/connexion"
        element={
          <Suspense fallback={<Chargement />}>
            <Connexion />
          </Suspense>
        }
      />

      <Route
        element={
          <RouteProtegee>
            <Layout />
          </RouteProtegee>
        }
      >
        <Route index element={<Dashboard />} />
        <Route path="expositions" element={<Expositions />} />
        <Route path="expositions/:id" element={<DetailExposition />} />
        <Route path="alertes" element={<Alertes />} />
        <Route path="scheduler" element={<Scheduler />} />

        <Route
          path="rapports"
          element={
            <RouteProtegee role="supervisor">
              <Rapports />
            </RouteProtegee>
          }
        />
        <Route
          path="comptes"
          element={
            <RouteProtegee role="admin">
              <Comptes />
            </RouteProtegee>
          }
        />
        <Route
          path="configuration"
          element={
            <RouteProtegee role="admin">
              <Configuration />
            </RouteProtegee>
          }
        />
        <Route
          path="audit"
          element={
            <RouteProtegee role="super_admin">
              <Audit />
            </RouteProtegee>
          }
        />
        <Route
          path="roles"
          element={
            <RouteProtegee role="super_admin">
              <HistoriqueRoles />
            </RouteProtegee>
          }
        />
        <Route
          path="conformite"
          element={
            <RouteProtegee role="super_admin">
              <Conformite />
            </RouteProtegee>
          }
        />
      </Route>

      <Route path="*" element={<Navigate to="/" replace />} />
    </Routes>
  );
}
