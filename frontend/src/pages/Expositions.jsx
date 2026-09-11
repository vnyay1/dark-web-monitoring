import { useState } from "react";
import { Link } from "react-router-dom";

import { api } from "../api/client";
import { useChargement, useMessages, useSession } from "../api/session";
import {
  Chargement,
  EnTetePage,
  Erreur,
  formaterDate,
  formaterDateHeure,
  LIBELLE_NIVEAU,
  LIBELLE_STATUT,
  ListeCategories,
  ListeSources,
  Messages,
  PastilleCriticite,
  PastilleStatut,
  Vide,
} from "../components/communs";

const FILTRES_VIDES = {
  q: "",
  niveau_min: "",
  categorie: "",
  statut: "",
  periode: "",
};

export default function Expositions() {
  const { aRole } = useSession();
  const { messages, ajouter } = useMessages();

  // `filtres` suit la saisie, `appliques` declenche la requete : sans cette
  // separation, chaque frappe dans le champ de recherche lancerait un appel.
  const [filtres, setFiltres] = useState(FILTRES_VIDES);
  const [appliques, setAppliques] = useState(FILTRES_VIDES);

  const { donnees, erreur, chargement, setDonnees } = useChargement(
    () => api.expositions(appliques),
    [JSON.stringify(appliques)],
  );

  const peutChangerStatut = aRole("supervisor");

  function modifier(champ, valeur) {
    setFiltres((f) => ({ ...f, [champ]: valeur }));
  }

  function soumettre(evenement) {
    evenement.preventDefault();
    setAppliques(filtres);
  }

  function reinitialiser() {
    setFiltres(FILTRES_VIDES);
    setAppliques(FILTRES_VIDES);
  }

  async function changerStatut(id, statut) {
    try {
      const reponse = await api.changerStatut(id, statut);
      // Mise a jour locale plutot que rechargement complet : la liste peut
      // etre longue et l'operateur perdrait sa position de defilement.
      setDonnees((precedent) => ({
        ...precedent,
        expositions: precedent.expositions.map((e) =>
          e.id === id ? reponse.exposition : e,
        ),
      }));
      ajouter(`Statut mis à jour : ${LIBELLE_STATUT[statut] || statut}.`);
    } catch (e) {
      ajouter(e.message, "error");
    }
  }

  const referentiels = donnees?.referentiels;

  return (
    <>
      <EnTetePage
        titre="Expositions"
        sousTitre="Indicateurs d'exposition détectés sur les sources surveillées"
      />

      <form className="card filters" onSubmit={soumettre}>
        <div className="field">
          <label className="field-label" htmlFor="f-q">
            Recherche
          </label>
          <input
            id="f-q"
            className="input"
            placeholder="Nom d'entité…"
            value={filtres.q}
            onChange={(e) => modifier("q", e.target.value)}
          />
        </div>

        <div className="field">
          <label className="field-label" htmlFor="f-niveau">
            Criticité min.
          </label>
          <select
            id="f-niveau"
            className="select"
            value={filtres.niveau_min}
            onChange={(e) => modifier("niveau_min", e.target.value)}
          >
            <option value="">Toutes</option>
            {(referentiels?.niveaux || []).map((n) => (
              <option key={n} value={n}>
                {LIBELLE_NIVEAU[n] || n}
              </option>
            ))}
          </select>
        </div>

        <div className="field">
          <label className="field-label" htmlFor="f-cat">
            Catégorie
          </label>
          <select
            id="f-cat"
            className="select"
            value={filtres.categorie}
            onChange={(e) => modifier("categorie", e.target.value)}
          >
            <option value="">Toutes</option>
            {(referentiels?.categories || []).map((c) => (
              <option key={c.id} value={c.id}>
                {c.nom}
              </option>
            ))}
          </select>
        </div>

        <div className="field">
          <label className="field-label" htmlFor="f-statut">
            Statut
          </label>
          <select
            id="f-statut"
            className="select"
            value={filtres.statut}
            onChange={(e) => modifier("statut", e.target.value)}
          >
            <option value="">Tous</option>
            {(referentiels?.statuts || []).map((s) => (
              <option key={s} value={s}>
                {LIBELLE_STATUT[s] || s}
              </option>
            ))}
          </select>
        </div>

        <div className="field">
          <label className="field-label" htmlFor="f-periode">
            Période (jours)
          </label>
          <input
            id="f-periode"
            className="input"
            type="number"
            min="1"
            placeholder="Ex : 30"
            value={filtres.periode}
            onChange={(e) => modifier("periode", e.target.value)}
          />
        </div>

        <div className="btn-row">
          <button className="btn btn-primary" type="submit">
            Filtrer
          </button>
          <button className="btn btn-ghost" type="button" onClick={reinitialiser}>
            Effacer
          </button>
        </div>
      </form>

      <Erreur message={erreur} />

      {chargement ? (
        <Chargement />
      ) : !donnees || donnees.expositions.length === 0 ? (
        <Vide titre="Aucune exposition ne correspond">
          Ajustez les filtres, ou lancez une collecte depuis la page
          Supervision.
        </Vide>
      ) : (
        <>
          <div
            className="page-subtitle"
            style={{ marginBottom: 11 }}
            aria-live="polite"
          >
            <strong style={{ color: "var(--text-primary)" }}>
              {donnees.total}
            </strong>{" "}
            exposition(s)
            {donnees.tronque &&
              ` · ${donnees.expositions.length} affichées, affinez les filtres pour voir les suivantes`}
          </div>

          <div className="table-wrap">
            <table className="data">
              <thead>
                <tr>
                  <th>Entité concernée</th>
                  <th>Criticité</th>
                  <th>Catégories</th>
                  <th>Sources</th>
                  <th>Publication</th>
                  <th>1re détection</th>
                  <th>Statut</th>
                </tr>
              </thead>
              <tbody>
                {donnees.expositions.map((e) => (
                  <tr key={e.id}>
                    <td className="cell-entity">
                      <Link to={`/expositions/${e.id}`}>{e.nom_entite}</Link>
                    </td>
                    <td>
                      <PastilleCriticite
                        niveau={e.niveau_criticite}
                        criticite={e.criticite}
                      />
                    </td>
                    <td>
                      <ListeCategories categories={e.categories} />
                    </td>
                    <td>
                      <ListeSources sources={e.sources} />
                    </td>
                    <td className="cell-mono">
                      {e.date_publication_source
                        ? formaterDate(e.date_publication_source)
                        : "—"}
                    </td>
                    <td className="cell-mono">
                      {formaterDateHeure(e.date_premiere_detection)}
                    </td>
                    <td>
                      {peutChangerStatut ? (
                        <select
                          className="select"
                          style={{ minWidth: 148 }}
                          value={e.statut}
                          onChange={(ev) => changerStatut(e.id, ev.target.value)}
                          aria-label={`Statut de ${e.nom_entite}`}
                        >
                          {(referentiels?.statuts || []).map((s) => (
                            <option key={s} value={s}>
                              {LIBELLE_STATUT[s] || s}
                            </option>
                          ))}
                        </select>
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
