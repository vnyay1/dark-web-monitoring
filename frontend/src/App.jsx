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
 */

import { Navigate, Route, Routes } from "react-router-dom";

import { useSession } from "./api/session";
import Layout from "./components/Layout";
import { Chargement } from "./components/communs";

import Alertes from "./pages/Alertes";
import Audit from "./pages/Audit";
import Comptes from "./pages/Comptes";
import Configuration from "./pages/Configuration";
import Conformite from "./pages/Conformite";
import Connexion from "./pages/Connexion";
import Dashboard from "./pages/Dashboard";
import DetailExposition from "./pages/DetailExposition";
import Expositions from "./pages/Expositions";
import HistoriqueRoles from "./pages/HistoriqueRoles";
import Rapports from "./pages/Rapports";
import Scheduler from "./pages/Scheduler";

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
      <Route path="/connexion" element={<Connexion />} />

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
