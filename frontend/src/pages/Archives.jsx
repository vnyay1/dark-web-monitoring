/**
 * Archives : expositions qualifiees « faux positif » ou « cloturee ».
 *
 * Reservee a admin et super_admin (route ET endpoint : cf. App.jsx et
 * app/web/api/expositions.py). Ce sont des dossiers tranches, conserves
 * pour l'historique et la relecture, pas de la veille quotidienne.
 *
 * Meme presentation que la page Expositions : le tableau, les filtres et le
 * tri sont le meme composant. Remettre une exposition dans un statut actif
 * la fait sortir d'ici et reapparaitre dans Expositions.
 */

import { Link } from "react-router-dom";

import { api } from "../api/client";
import ListeExpositions from "../components/ListeExpositions";

export default function Archives() {
  return (
    <ListeExpositions
      titre="Archives"
      sousTitre="Expositions qualifiées faux positif ou clôturées"
      etiquette="Expositions archivées"
      charger={api.expositionsArchivees}
      appartient={(exposition) => exposition.archivee}
      messageSortie={(nom) => `${nom} : dossier rouvert, revenu dans Expositions.`}
      titreVide="Aucune exposition archivée"
      aideVide="Une exposition classée « Faux positif » ou « Clôturée » apparaîtra ici."
      aide={
        <>
          Ces dossiers ne figurent plus dans <Link to="/expositions">Expositions</Link>. Leurs
          signalements, leurs alertes et le texte conservé de leurs annonces restent intacts : ils
          comptent toujours dans le tableau de bord, les rapports et les exports.
        </>
      }
    />
  );
}
