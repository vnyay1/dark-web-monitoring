/**
 * Liste des expositions.
 *
 * Les filtres vivent dans l'ADRESSE (?niveau_min=elevee&statut=new...) :
 * une vue filtree se partage par lien, survit a un rechargement, et le
 * bouton Precedent y ramene depuis le detail d'une exposition. Les listes
 * s'appliquent des leur choix ; la recherche, 300 ms apres la derniere
 * frappe, pour ne pas interroger le serveur a chaque lettre.
 */

import { useEffect, useState } from "react";
import { Link, useLocation, useSearchParams } from "react-router-dom";

import { api } from "../api/client";
import { useChargement, useMessages, useSession } from "../api/session";
import ChoixStatut from "../components/ChoixStatut";
import {
  Chargement,
  EnTetePage,
  enDate,
  Erreur,
  formaterDate,
  formaterDateHeure,
  IndicateurRechargement,
  LIBELLE_NIVEAU,
  LIBELLE_STATUT,
  ListeCategories,
  ListeSources,
  Messages,
  PastilleCriticite,
  PastilleStatut,
  pluriel,
  Vide,
} from "../components/communs";
import { IconeFermer, IconeRecherche } from "../components/icones";
import { EnTeteTri, useTri } from "../components/tri";

const CLES_FILTRES = ["q", "niveau_min", "categorie", "statut", "periode"];
const DELAI_RECHERCHE_MS = 300;

const ACCESSEURS_TRI = {
  criticite: (e) => e.criticite,
  publication: (e) => enDate(e.date_publication_source)?.getTime() ?? null,
  detection: (e) => enDate(e.date_premiere_detection)?.getTime() ?? null,
  entite: (e) => e.nom_entite.toLocaleLowerCase("fr"),
};

export default function Expositions() {
  const { aRole } = useSession();
  const { messages, ajouter } = useMessages();
  const location = useLocation();
  const [parametres, setParametres] = useSearchParams();

  const filtres = Object.fromEntries(CLES_FILTRES.map((cle) => [cle, parametres.get(cle) || ""]));
  const [recherche, setRecherche] = useState(filtres.q);

  const { donnees, erreur, chargement, rechargement, recharger, setDonnees } = useChargement(
    () => api.expositions(filtres),
    [parametres.toString()],
  );

  const { triees, tri, trierPar } = useTri(donnees?.expositions, ACCESSEURS_TRI);

  function appliquer(cle, valeur) {
    setParametres(
      (actuels) => {
        const suivants = new URLSearchParams(actuels);
        if (valeur) suivants.set(cle, valeur);
        else suivants.delete(cle);
        return suivants;
      },
      { replace: true },
    );
  }

  // Recherche differee : le parametre d'adresse suit la saisie a 300 ms.
  useEffect(() => {
    if (recherche === filtres.q) return undefined;
    const minuteur = setTimeout(() => appliquer("q", recherche.trim()), DELAI_RECHERCHE_MS);
    return () => clearTimeout(minuteur);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [recherche]);

  // Adresse modifiee ailleurs (lien du tableau de bord, Precedent).
  useEffect(() => {
    setRecherche(filtres.q);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [filtres.q]);

  function toutEffacer() {
    setRecherche("");
    setParametres({}, { replace: true });
  }

  async function changerStatut(exposition, statut) {
    try {
      const reponse = await api.changerStatut(exposition.id, statut);
      // Mise a jour locale plutot que rechargement : la position dans la
      // liste est conservee.
      setDonnees((precedent) => ({
        ...precedent,
        expositions: precedent.expositions.map((e) => (e.id === exposition.id ? reponse.exposition : e)),
      }));
      ajouter(`${exposition.nom_entite} : statut « ${LIBELLE_STATUT[statut] || statut} » enregistré.`);
      return true;
    } catch (e) {
      ajouter(e.message, "error");
      return false;
    }
  }

  const referentiels = donnees?.referentiels;
  const peutChangerStatut = aRole("supervisor");
  const nomCategorie = (id) => referentiels?.categories.find((c) => c.id === id)?.nom || id;

  const puces = [
    filtres.q && { cle: "q", libelle: `Recherche : « ${filtres.q} »` },
    filtres.niveau_min && { cle: "niveau_min", libelle: `Criticité ≥ ${LIBELLE_NIVEAU[filtres.niveau_min] || filtres.niveau_min}` },
    filtres.categorie && { cle: "categorie", libelle: `Catégorie : ${nomCategorie(filtres.categorie)}` },
    filtres.statut && { cle: "statut", libelle: `Statut : ${LIBELLE_STATUT[filtres.statut] || filtres.statut}` },
    filtres.periode && { cle: "periode", libelle: `${filtres.periode} derniers jours` },
  ].filter(Boolean);

  return (
    <>
      <IndicateurRechargement actif={rechargement} />
      <EnTetePage
        titre="Expositions"
        sousTitre="Indicateurs d'exposition détectés sur les sources surveillées"
      />

      <form
        className="card filters"
        role="search"
        aria-label="Filtrer les expositions"
        onSubmit={(e) => {
          e.preventDefault();
          appliquer("q", recherche.trim());
        }}
      >
        <div className="field">
          <label className="field-label" htmlFor="f-q">
            Recherche
          </label>
          <div className="champ-groupe">
            <IconeRecherche taille={16} className="champ-icone" />
            <input
              id="f-q"
              className="input"
              type="search"
              placeholder="Nom d'entité"
              value={recherche}
              onChange={(e) => setRecherche(e.target.value)}
            />
          </div>
        </div>

        <FiltreListe
          id="f-niveau"
          libelle="Criticité minimale"
          valeur={filtres.niveau_min}
          tous="Toutes"
          options={(referentiels?.niveaux || []).map((n) => [n, LIBELLE_NIVEAU[n] || n])}
          onChange={(v) => appliquer("niveau_min", v)}
        />
        <FiltreListe
          id="f-cat"
          libelle="Catégorie"
          valeur={filtres.categorie}
          tous="Toutes"
          options={(referentiels?.categories || []).map((c) => [c.id, c.nom])}
          onChange={(v) => appliquer("categorie", v)}
        />
        <FiltreListe
          id="f-statut"
          libelle="Statut"
          valeur={filtres.statut}
          tous="Tous"
          options={(referentiels?.statuts || []).map((s) => [s, LIBELLE_STATUT[s] || s])}
          onChange={(v) => appliquer("statut", v)}
        />
        <FiltreListe
          id="f-periode"
          libelle="Période"
          valeur={filtres.periode}
          tous="Toute la période"
          options={[
            ["1", "Dernières 24 h"],
            ["7", "7 derniers jours"],
            ["30", "30 derniers jours"],
            ["90", "90 derniers jours"],
            ...(filtres.periode && !["1", "7", "30", "90"].includes(filtres.periode)
              ? [[filtres.periode, `${filtres.periode} derniers jours`]]
              : []),
          ]}
          onChange={(v) => appliquer("periode", v)}
        />
      </form>

      {puces.length > 0 && (
        <div className="puces" aria-label="Filtres actifs">
          {puces.map((p) => (
            <span className="puce-filtre" key={p.cle}>
              {p.libelle}
              <button
                type="button"
                onClick={() => {
                  if (p.cle === "q") setRecherche("");
                  appliquer(p.cle, "");
                }}
                aria-label={`Retirer le filtre ${p.libelle}`}
              >
                <IconeFermer taille={14} />
              </button>
            </span>
          ))}
          <button type="button" className="btn btn-ghost btn-sm" onClick={toutEffacer}>
            Tout effacer
          </button>
        </div>
      )}

      <Erreur message={erreur} onReessayer={recharger} />

      {chargement ? (
        <Chargement />
      ) : !donnees ? null : donnees.expositions.length === 0 ? (
        <Vide titre="Aucune exposition ne correspond">
          {puces.length > 0
            ? "Retirez un filtre ou élargissez la période."
            : "Les expositions apparaîtront ici après la première collecte."}
        </Vide>
      ) : (
        <>
          <p className="barre-recherche-compte espace-resultats" role="status">
            <strong>{donnees.total}</strong> {pluriel("exposition", donnees.total)}
            {donnees.tronque &&
              ` · ${donnees.expositions.length} affichées, affinez les filtres pour voir les suivantes`}
          </p>

          <div className="table-wrap tableau-cartes">
            <table className="data">
              <caption className="sr-only">
                Expositions{puces.length > 0 ? `, filtrées (${puces.map((p) => p.libelle).join(", ")})` : ""}
              </caption>
              <thead>
                <tr>
                  <EnTeteTri cle="entite" tri={tri} trierPar={trierPar} sensInitial="asc">
                    Entité concernée
                  </EnTeteTri>
                  <EnTeteTri cle="criticite" tri={tri} trierPar={trierPar}>
                    Criticité
                  </EnTeteTri>
                  <th scope="col">Catégories</th>
                  <th scope="col">Sources</th>
                  <EnTeteTri cle="publication" tri={tri} trierPar={trierPar}>
                    Publication
                  </EnTeteTri>
                  <EnTeteTri cle="detection" tri={tri} trierPar={trierPar}>
                    Première détection
                  </EnTeteTri>
                  <th scope="col">Statut</th>
                </tr>
              </thead>
              <tbody>
                {triees.map((e) => (
                  <tr key={e.id}>
                    <td className="cell-titre">
                      <Link className="lien-entite" to={`/expositions/${e.id}`} state={{ retour: location.search }}>
                        {e.nom_entite}
                      </Link>
                    </td>
                    <td data-label="Criticité">
                      <PastilleCriticite niveau={e.niveau_criticite} criticite={e.criticite} />
                    </td>
                    <td data-label="Catégories">
                      <ListeCategories categories={e.categories} />
                    </td>
                    <td data-label="Sources">
                      <ListeSources sources={e.sources} />
                    </td>
                    <td className="cell-mono" data-label="Publication">
                      {e.date_publication_source ? formaterDate(e.date_publication_source) : "non datée"}
                    </td>
                    <td className="cell-mono" data-label="Première détection">
                      {formaterDateHeure(e.date_premiere_detection)}
                    </td>
                    <td data-label="Statut">
                      {peutChangerStatut ? (
                        <ChoixStatut
                          compact
                          statut={e.statut}
                          statuts={referentiels?.statuts || []}
                          libelle={`Statut de ${e.nom_entite}`}
                          onEnregistrer={(statut) => changerStatut(e, statut)}
                        />
                      ) : (
                        <PastilleStatut statut={e.statut} />
                      )}
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </>
      )}

      <Messages messages={messages} />
    </>
  );
}

function FiltreListe({ id, libelle, valeur, tous, options, onChange }) {
  return (
    <div className="field">
      <label className="field-label" htmlFor={id}>
        {libelle}
      </label>
      <select id={id} className="select" value={valeur} onChange={(e) => onChange(e.target.value)}>
        <option value="">{tous}</option>
        {options.map(([v, l]) => (
          <option key={v} value={v}>
            {l}
          </option>
        ))}
      </select>
    </div>
  );
}
