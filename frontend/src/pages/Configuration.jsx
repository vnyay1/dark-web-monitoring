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
import Confirmation from "../components/Confirmation";
import {
  Chargement,
  EnTetePage,
  Erreur,
  LIBELLE_NIVEAU,
  Messages,
} from "../components/communs";

/**
 * Forme de comparaison pour la recherche : minuscules et accents retires,
 * pour que "universite" trouve "Université".
 */
function pourRecherche(texte) {
  return (texte || "")
    .normalize("NFD")
    .replace(/[\u0300-\u036f]/g, "")
    .toLowerCase()
    .trim();
}

const libelleCategorie = (c) => c.replace(/_/g, " ");

const NIVEAUX = ["faible", "moyenne", "elevee", "critique"];

export default function Configuration() {
  const { messages, ajouter } = useMessages();

  const config = useChargement(() => api.configuration());
  const catalogue = useChargement(() => api.selecteurs());

  const [nouveau, setNouveau] = useState({ valeur: "", categorie: "" });
  const [recherche, setRecherche] = useState("");
  const [filtreCategorie, setFiltreCategorie] = useState("");
  const [aSupprimer, setASupprimer] = useState(null);
  const [suppressionEnCours, setSuppressionEnCours] = useState(false);

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

  async function confirmerSuppression() {
    setSuppressionEnCours(true);
    try {
      await api.supprimerSelecteur(aSupprimer.id);
      ajouter(`Sélecteur « ${aSupprimer.valeur} » supprimé.`);
      setASupprimer(null);
      catalogue.recharger();
    } catch (e) {
      ajouter(e.message, "error");
    } finally {
      setSuppressionEnCours(false);
    }
  }

  async function desactiverPlutot() {
    const cible = aSupprimer;
    setASupprimer(null);
    await basculer(cible.id);
    ajouter(`Sélecteur « ${cible.valeur} » désactivé.`);
  }

  if (config.chargement || catalogue.chargement) return <Chargement />;

  const modifiable = config.donnees?.modifiable;
  const terme = pourRecherche(recherche);
  const tousSelecteurs = catalogue.donnees?.selecteurs || [];
  const selecteurs = tousSelecteurs.filter(
    (s) =>
      (!terme || pourRecherche(s.valeur).includes(terme)) &&
      (!filtreCategorie || s.categorie === filtreCategorie),
  );
  const filtreActif = Boolean(terme || filtreCategorie);
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
                  {libelleCategorie(c)}
                </option>
              ))}
            </select>
          </div>

          <div className="btn-row">
            <button className="btn btn-primary" type="submit">
              Ajouter
            </button>
          </div>
        </form>

        {/* Barre de recherche dediee, au-dessus du tableau qu'elle filtre.
            Filtrage en direct cote client : le catalogue compte au plus
            quelques centaines d'entrees. */}
        <div className="barre-recherche" role="search">
          <input
            className="input"
            type="search"
            placeholder="Rechercher un sélecteur par nom…"
            value={recherche}
            onChange={(e) => setRecherche(e.target.value)}
            aria-label="Rechercher un sélecteur par nom"
          />
          <select
            className="select"
            value={filtreCategorie}
            onChange={(e) => setFiltreCategorie(e.target.value)}
            aria-label="Filtrer par catégorie"
          >
            <option value="">Toutes les catégories</option>
            {(catalogue.donnees?.categories || []).map((c) => (
              <option key={c} value={c}>
                {libelleCategorie(c)}
              </option>
            ))}
          </select>
          <span className="barre-recherche-compte" aria-live="polite">
            {filtreActif
              ? `${selecteurs.length} résultat(s) sur ${tousSelecteurs.length}`
              : `${tousSelecteurs.length} sélecteur(s)`}
          </span>
          {filtreActif && (
            <button
              className="btn btn-ghost btn-sm"
              onClick={() => {
                setRecherche("");
                setFiltreCategorie("");
              }}
            >
              Effacer la recherche
            </button>
          )}
        </div>

        <div className="table-wrap">
          <table className="data">
            <thead>
              <tr>
                <th>Sélecteur</th>
                <th>Catégorie</th>
                <th>Origine</th>
                <th style={{ width: 110 }}>État</th>
                <th style={{ width: 110 }}>
                  <span className="sr-only">Actions</span>
                </th>
              </tr>
            </thead>
            <tbody>
              {selecteurs.map((s) => (
                <tr key={s.id}>
                  <td className="cell-entity">{s.valeur}</td>
                  <td className="cell-muted">{libelleCategorie(s.categorie)}</td>
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
                  <td>
                    <button
                      className="btn btn-ghost btn-sm bouton-supprimer"
                      onClick={() => setASupprimer(s)}
                      aria-label={`Supprimer le sélecteur ${s.valeur}`}
                    >
                      Supprimer
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

      {aSupprimer && (
        <Confirmation
          titre="Supprimer ce sélecteur ?"
          libelleConfirmer="Supprimer définitivement"
          enCours={suppressionEnCours}
          onConfirmer={confirmerSuppression}
          onAnnuler={() => setASupprimer(null)}
          actionSecondaire={
            aSupprimer.actif
              ? { libelle: "Désactiver plutôt", onClick: desactiverPlutot }
              : null
          }
        >
          <p className="fenetre-cible">
            <strong>{aSupprimer.valeur}</strong>
            <span className="cell-muted"> — {libelleCategorie(aSupprimer.categorie)}</span>
          </p>
          <p>
            Il sera retiré du catalogue et ne sera plus recherché lors des
            prochaines collectes. Les expositions déjà détectées ne sont pas
            modifiées.
          </p>
          <p className="cell-muted">
            Cette suppression est définitive. Pour suspendre le sélecteur sans le
            perdre, désactivez-le plutôt : c'est réversible à tout moment.
          </p>
        </Confirmation>
      )}

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
