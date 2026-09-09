/**
 * Configuration systeme et catalogue de selecteurs.
 *
 * Les valeurs sont saisies selon leur TYPE declare cote serveur : un menu
 * deroulant pour un palier de criticite, un champ numerique sinon. C'est
 * le serveur qui reste juge - valider_valeur() refait le controle.
 */

import { useState } from "react";

import { api } from "../api/client";
import { useChargement, useMessages } from "../api/session";
import {
  Chargement,
  EnTetePage,
  Erreur,
  LIBELLE_NIVEAU,
  Messages,
} from "../components/communs";

const NIVEAUX = ["faible", "moyenne", "elevee", "critique"];

export default function Configuration() {
  const { messages, ajouter } = useMessages();

  const config = useChargement(() => api.configuration());
  const catalogue = useChargement(() => api.selecteurs());

  const [nouveau, setNouveau] = useState({ valeur: "", categorie: "" });
  const [recherche, setRecherche] = useState("");

  async function enregistrer(cle, valeur) {
    try {
      await api.modifierConfiguration(cle, valeur);
      ajouter("Configuration enregistrée.");
      config.recharger();
    } catch (e) {
      ajouter(e.message, "error");
    }
  }

  async function ajouterSelecteur(evenement) {
    evenement.preventDefault();
    try {
      await api.ajouterSelecteur(nouveau.valeur.trim(), nouveau.categorie);
      ajouter(`Sélecteur « ${nouveau.valeur.trim()} » ajouté.`);
      setNouveau({ valeur: "", categorie: nouveau.categorie });
      catalogue.recharger();
    } catch (e) {
      ajouter(e.message, "error");
    }
  }

  async function basculer(id) {
    try {
      await api.basculerSelecteur(id);
      catalogue.recharger();
    } catch (e) {
      ajouter(e.message, "error");
    }
  }

  if (config.chargement || catalogue.chargement) return <Chargement />;

  const modifiable = config.donnees?.modifiable;
  const selecteurs = (catalogue.donnees?.selecteurs || []).filter((s) =>
    s.valeur.toLowerCase().includes(recherche.trim().toLowerCase()),
  );
  const actifs = (catalogue.donnees?.selecteurs || []).filter((s) => s.actif).length;

  return (
    <>
      <EnTetePage
        titre="Configuration"
        sousTitre="Paliers de criticité, fenêtre de collecte et catalogue de sélecteurs"
      />

      <Erreur message={config.erreur || catalogue.erreur} />

      {!modifiable && (
        <div className="banner banner-info">
          Consultation seule : la modification des réglages système est réservée
          au super-administrateur.
        </div>
      )}

      <section style={{ marginBottom: 28 }}>
        <h2 className="section-title">Réglages système</h2>
        <div className="table-wrap">
          <table className="data">
            <thead>
              <tr>
                <th style={{ width: 260 }}>Clé</th>
                <th>Description</th>
                <th style={{ width: 230 }}>Valeur</th>
              </tr>
            </thead>
            <tbody>
              {(config.donnees?.configurations || []).map((c) => (
                <LigneConfig
                  key={c.cle}
                  entree={c}
                  modifiable={modifiable}
                  onEnregistrer={enregistrer}
                />
              ))}
            </tbody>
          </table>
        </div>
      </section>

      <section>
        <h2 className="section-title">
          Catalogue de sélecteurs
          <span className="count">
            {actifs} actif(s) sur {catalogue.donnees?.selecteurs.length || 0}
          </span>
        </h2>

        <form className="card filters" onSubmit={ajouterSelecteur}>
          <div className="field">
            <label className="field-label" htmlFor="sel-valeur">
              Nouveau sélecteur
            </label>
            <input
              id="sel-valeur"
              className="input"
              placeholder="Ex : MINSANTE"
              value={nouveau.valeur}
              onChange={(e) =>
                setNouveau((n) => ({ ...n, valeur: e.target.value }))
              }
              required
            />
          </div>

          <div className="field">
            <label className="field-label" htmlFor="sel-cat">
              Catégorie
            </label>
            <select
              id="sel-cat"
              className="select"
              value={nouveau.categorie}
              onChange={(e) =>
                setNouveau((n) => ({ ...n, categorie: e.target.value }))
              }
              required
            >
              <option value="">Choisir…</option>
              {(catalogue.donnees?.categories || []).map((c) => (
                <option key={c} value={c}>
                  {c.replace(/_/g, " ")}
                </option>
              ))}
            </select>
          </div>

          <div className="field">
            <label className="field-label" htmlFor="sel-q">
              Rechercher
            </label>
            <input
              id="sel-q"
              className="input"
              placeholder="Filtrer le catalogue…"
              value={recherche}
              onChange={(e) => setRecherche(e.target.value)}
            />
          </div>

          <div className="btn-row">
            <button className="btn btn-primary" type="submit">
              Ajouter
            </button>
          </div>
        </form>

        <div className="table-wrap">
          <table className="data">
            <thead>
              <tr>
                <th>Sélecteur</th>
                <th>Catégorie</th>
                <th>Origine</th>
                <th style={{ width: 150 }}>État</th>
              </tr>
            </thead>
            <tbody>
              {selecteurs.map((s) => (
                <tr key={s.id}>
                  <td className="cell-entity">{s.valeur}</td>
                  <td className="cell-muted">
                    {s.categorie.replace(/_/g, " ")}
                  </td>
                  <td className="cell-muted">
                    {s.propose_par_ner ? "Proposé par NER" : "Catalogue"}
                  </td>
                  <td>
                    <button
                      className={`btn btn-sm ${s.actif ? "" : "btn-ghost"}`}
                      onClick={() => basculer(s.id)}
                    >
                      {s.actif ? "Actif" : "Inactif"}
                    </button>
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>

        {selecteurs.length === 0 && (
          <p className="page-subtitle" style={{ marginTop: 11 }}>
            Aucun sélecteur ne correspond à cette recherche.
          </p>
        )}
      </section>

      <Messages messages={messages} />
    </>
  );
}

function LigneConfig({ entree, modifiable, onEnregistrer }) {
  const [valeur, setValeur] = useState(entree.valeur);
  const modifie = valeur !== entree.valeur;

  return (
    <tr>
      <td className="cell-mono">{entree.cle}</td>
      <td className="cell-muted">{entree.description}</td>
      <td>
        <div style={{ display: "flex", gap: 7, alignItems: "center" }}>
          {entree.type === "niveau" ? (
            <select
              className="select"
              value={valeur}
              disabled={!modifiable}
              onChange={(e) => setValeur(e.target.value)}
              aria-label={entree.cle}
            >
              {NIVEAUX.map((n) => (
                <option key={n} value={n}>
                  {LIBELLE_NIVEAU[n]}
                </option>
              ))}
            </select>
          ) : (
            <input
              className="input"
              type="number"
              min="0"
              value={valeur}
              disabled={!modifiable}
              onChange={(e) => setValeur(e.target.value)}
              aria-label={entree.cle}
            />
          )}

          {modifiable && modifie && (
            <button
              className="btn btn-primary btn-sm"
              onClick={() => onEnregistrer(entree.cle, valeur)}
            >
              OK
            </button>
          )}
        </div>
      </td>
    </tr>
  );
}
