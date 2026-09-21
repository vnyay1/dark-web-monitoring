/**
 * Liste de travail des expositions.
 *
 * Les expositions qualifiees « faux positif » ou « cloturee » n'y figurent
 * plus : elles sont archivees et consultables dans la page Archives
 * (admin et super_admin). Rien n'est supprime ni deplace - c'est le statut
 * qui decide, cote serveur (cf. app/web/api/expositions.py), donc un retour
 * a un statut actif les ramene ici.
 *
 * Le tableau lui-meme vit dans components/ListeExpositions.jsx, partage
 * avec Archives.
 */

import { Link } from "react-router-dom";

import { api } from "../api/client";
import { useSession } from "../api/session";
import ListeExpositions from "../components/ListeExpositions";

export default function Expositions() {
  const { aRole } = useSession();

  return (
    <ListeExpositions
      titre="Expositions"
      sousTitre="Indicateurs d'exposition détectés sur les sources surveillées"
      etiquette="Expositions"
      charger={api.expositions}
      appartient={(exposition) => !exposition.archivee}
      messageSortie={(nom) => `${nom} : dossier archivé, consultable dans Archives.`}
      titreVide="Aucune exposition ne correspond"
      aideVide="Les expositions apparaîtront ici après la première collecte."
      aide={
        aRole("admin") ? (
          <>
            Les expositions classées « Faux positif » ou « Clôturée » sont retirées de cette liste
            et regroupées dans <Link to="/archives">Archives</Link>.
          </>
        ) : (
          "Les expositions classées « Faux positif » ou « Clôturée » sont retirées de cette liste."
        )
      }
    />
  );
}
