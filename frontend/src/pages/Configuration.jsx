/**
 * Configuration systeme, categories et catalogue de selecteurs.
 *
 * Les reglages systeme sont saisis selon leur TYPE declare cote serveur :
 * un menu deroulant pour un palier de criticite, un champ numerique sinon.
 * C'est le serveur qui reste juge - valider_valeur() refait le controle.
 *
 * Les categories (FR-13) sont celles des selecteurs, et deviennent celles
 * des expositions qu'ils declenchent. Une categorie utilisee ne peut etre
 * supprimee qu'en transferant ses selecteurs et ses expositions vers une
 * autre : rien n'est perdu.
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

const NIVEAUX = ["faible", "moyenne", "elevee", "critique"];

export default function Configuration() {
  const { messages, ajouter } = useMessages();

  const config = useChargement(() => api.configuration());
  // Une seule requete pour le catalogue ET les categories (avec compteurs).
  const catalogue = useChargement(() => api.selecteurs());

  async function enregistrerConfig(cle, valeur) {
    try {
      await api.modifierConfiguration(cle, valeur);
      ajouter("Configuration enregistrée.");
      config.recharger();
    } catch (e) {
      ajouter(e.message, "error");
    }
  }

  /** Execute une action d'administration, puis recharge le catalogue. */
  async function agir(action, succes) {
    try {
      const reponse = await action();
      ajouter(typeof succes === "function" ? succes(reponse) : succes);
      catalogue.recharger();
      return true;
    } catch (e) {
      ajouter(e.message, "error");
      return false;
    }
  }

  if (config.chargement || catalogue.chargement) return <Chargement />;

  const modifiable = config.donnees?.modifiable;
  const categories = catalogue.donnees?.categories || [];
  const selecteurs = catalogue.donnees?.selecteurs || [];

  return (
    <>
      <EnTetePage
        titre="Configuration"
        sousTitre="Réglages système, catégories et catalogue de sélecteurs"
      />

      <Erreur message={config.erreur || catalogue.erreur} />

      <section style={{ marginBottom: 32 }}>
        <h2 className="section-title">Réglages système</h2>
        {!modifiable && (
          <div className="banner banner-info">
            Consultation seule : la modification des réglages système est
            réservée au super-administrateur.
          </div>
        )}
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
                  onEnregistrer={enregistrerConfig}
                />
              ))}
            </tbody>
          </table>
        </div>
      </section>

      <SectionCategories categories={categories} agir={agir} />

      <SectionCatalogue
        selecteurs={selecteurs}
        categories={categories}
        agir={agir}
      />

      <Messages messages={messages} />
    </>
  );
}

/* ================================================================== */
/* Categories                                                          */
/* ================================================================== */

const CATEGORIE_VIDE = {
  nom: "",
  description: "",
  lieu_generique: false,
  prioritaire: false,
};

function SectionCategories({ categories, agir }) {
  const [nouvelle, setNouvelle] = useState(CATEGORIE_VIDE);
  const [enEdition, setEnEdition] = useState(null);
  const [aSupprimer, setASupprimer] = useState(null);
  const [remplacement, setRemplacement] = useState("");
  const [enCours, setEnCours] = useState(false);

  async function creer(evenement) {
    evenement.preventDefault();
    const ok = await agir(
      () => api.creerCategorie({ ...nouvelle, nom: nouvelle.nom.trim() }),
      `Catégorie « ${nouvelle.nom.trim()} » créée.`,
    );
    if (ok) setNouvelle(CATEGORIE_VIDE);
  }

  async function enregistrerEdition() {
    setEnCours(true);
    const ok = await agir(
      () => api.modifierCategorie(enEdition.id, enEdition),
      "Catégorie modifiée.",
    );
    setEnCours(false);
    if (ok) setEnEdition(null);
  }

  function ouvrirSuppression(categorie) {
    setRemplacement("");
    setASupprimer(categorie);
  }

  async function confirmerSuppression() {
    setEnCours(true);
    const ok = await agir(
      () => api.supprimerCategorie(aSupprimer.id, remplacement || null),
      (r) =>
        r.selecteurs_transferes || r.expositions_transferees
          ? `Catégorie supprimée : ${r.selecteurs_transferes} sélecteur(s) et ` +
            `${r.expositions_transferees} exposition(s) transférés.`
          : "Catégorie supprimée.",
    );
    setEnCours(false);
    if (ok) setASupprimer(null);
  }

  const utilisee = aSupprimer && (aSupprimer.nb_selecteurs || aSupprimer.nb_expositions);

  return (
    <section style={{ marginBottom: 32 }}>
      <h2 className="section-title">
        Catégories
        <span className="count">
          attribuées aux expositions d'après les sélecteurs trouvés
        </span>
      </h2>

      <form className="card filters" onSubmit={creer}>
        <div className="field">
          <label className="field-label" htmlFor="cat-nom">
            Nouvelle catégorie
          </label>
          <input
            id="cat-nom"
            className="input"
            placeholder="Ex : Santé"
            maxLength={100}
            value={nouvelle.nom}
            onChange={(e) => setNouvelle((n) => ({ ...n, nom: e.target.value }))}
            required
          />
        </div>
        <div className="field">
          <label className="field-label" htmlFor="cat-desc">
            Description
          </label>
          <input
            id="cat-desc"
            className="input"
            placeholder="Facultative"
            value={nouvelle.description}
            onChange={(e) =>
              setNouvelle((n) => ({ ...n, description: e.target.value }))
            }
          />
        </div>
        <CaseLieuGenerique
          id="cat-lieu"
          coche={nouvelle.lieu_generique}
          onChange={(v) => setNouvelle((n) => ({ ...n, lieu_generique: v }))}
        />
        <CasePrioritaire
          id="cat-prio"
          coche={nouvelle.prioritaire}
          onChange={(v) => setNouvelle((n) => ({ ...n, prioritaire: v }))}
        />
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
              <th>Catégorie</th>
              <th>Description</th>
              <th className="num-col">Sélecteurs</th>
              <th className="num-col">Expositions</th>
              <th style={{ width: 190 }}>
                <span className="sr-only">Actions</span>
              </th>
            </tr>
          </thead>
          <tbody>
            {categories.map((c) => (
              <tr key={c.id}>
                <td className="cell-entity">
                  {c.nom}
                  {c.prioritaire && (
                    <span
                      className="pill pill-warn"
                      style={{ marginLeft: 8 }}
                      title="Secteur prioritaire : alertes par SMS et WhatsApp dès les niveaux élevés"
                    >
                      prioritaire
                    </span>
                  )}
                  {c.lieu_generique && (
                    <span
                      className="pill pill-neutral"
                      style={{ marginLeft: 8 }}
                      title="Le filtre « nom de lieu dans une liste de pays » s'applique à ses sélecteurs"
                    >
                      lieu générique
                    </span>
                  )}
                </td>
                <td className="cell-muted">{c.description || "—"}</td>
                <td className="cell-mono num-col">{c.nb_selecteurs}</td>
                <td className="cell-mono num-col">{c.nb_expositions}</td>
                <td>
                  <div className="btn-row" style={{ justifyContent: "flex-end" }}>
                    <button
                      className="btn btn-ghost btn-sm"
                      onClick={() => setEnEdition({ ...c, description: c.description || "" })}
                    >
                      Modifier
                    </button>
                    <button
                      className="btn btn-ghost btn-sm bouton-supprimer"
                      onClick={() => ouvrirSuppression(c)}
                      aria-label={`Supprimer la catégorie ${c.nom}`}
                    >
                      Supprimer
                    </button>
                  </div>
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>

      {enEdition && (
        <Confirmation
          titre="Modifier la catégorie"
          libelleConfirmer="Enregistrer"
          libelleEnCours="Enregistrement…"
          variante="primaire"
          focusAnnuler={false}
          enCours={enCours}
          desactiverConfirmer={!enEdition.nom.trim()}
          onConfirmer={enregistrerEdition}
          onAnnuler={() => setEnEdition(null)}
        >
          <div className="field">
            <label className="field-label" htmlFor="edit-cat-nom">Nom</label>
            <input
              id="edit-cat-nom"
              className="input"
              maxLength={100}
              autoFocus
              value={enEdition.nom}
              onChange={(e) => setEnEdition((c) => ({ ...c, nom: e.target.value }))}
            />
          </div>
          <div className="field">
            <label className="field-label" htmlFor="edit-cat-desc">Description</label>
            <input
              id="edit-cat-desc"
              className="input"
              value={enEdition.description}
              onChange={(e) =>
                setEnEdition((c) => ({ ...c, description: e.target.value }))
              }
            />
          </div>
          <CaseLieuGenerique
            id="edit-cat-lieu"
            coche={enEdition.lieu_generique}
            onChange={(v) => setEnEdition((c) => ({ ...c, lieu_generique: v }))}
          />
          <CasePrioritaire
            id="edit-cat-prio"
            coche={enEdition.prioritaire}
            onChange={(v) => setEnEdition((c) => ({ ...c, prioritaire: v }))}
          />
          <p className="cell-muted">
            Le nouveau nom s'applique aussi aux {enEdition.nb_expositions}{" "}
            exposition(s) qui portent déjà cette catégorie.
          </p>
        </Confirmation>
      )}

      {aSupprimer && (
        <Confirmation
          titre="Supprimer cette catégorie ?"
          libelleConfirmer={utilisee ? "Supprimer et transférer" : "Supprimer"}
          enCours={enCours}
          desactiverConfirmer={Boolean(utilisee) && !remplacement}
          onConfirmer={confirmerSuppression}
          onAnnuler={() => setASupprimer(null)}
        >
          <p className="fenetre-cible">
            <strong>{aSupprimer.nom}</strong>
            <span className="cell-muted">
              {" "}— {aSupprimer.nb_selecteurs} sélecteur(s),{" "}
              {aSupprimer.nb_expositions} exposition(s)
            </span>
          </p>

          {utilisee ? (
            <>
              <p>
                Elle est encore utilisée : ses sélecteurs et les expositions qui
                la portent seront transférés vers la catégorie choisie. Aucun
                sélecteur n'est supprimé.
              </p>
              <div className="field">
                <label className="field-label" htmlFor="remplacement">
                  Transférer vers
                </label>
                <select
                  id="remplacement"
                  className="select"
                  value={remplacement}
                  onChange={(e) => setRemplacement(e.target.value)}
                >
                  <option value="">Choisir une catégorie…</option>
                  {categories
                    .filter((c) => c.id !== aSupprimer.id)
                    .map((c) => (
                      <option key={c.id} value={c.id}>
                        {c.nom}
                      </option>
                    ))}
                </select>
              </div>
            </>
          ) : (
            <p>Elle n'est utilisée par aucun sélecteur ni aucune exposition.</p>
          )}
        </Confirmation>
      )}
    </section>
  );
}

function CaseLieuGenerique({ id, coche, onChange }) {
  return (
    <label className="case-a-cocher" htmlFor={id}>
      <input
        id={id}
        type="checkbox"
        checked={coche}
        onChange={(e) => onChange(e.target.checked)}
      />
      <span>
        Noms de lieux génériques
        <span className="case-aide">
          villes, régions : écartés s'ils figurent dans une simple liste de pays
        </span>
      </span>
    </label>
  );
}

function CasePrioritaire({ id, coche, onChange }) {
  return (
    <label className="case-a-cocher" htmlFor={id}>
      <input
        id={id}
        type="checkbox"
        checked={coche}
        onChange={(e) => onChange(e.target.checked)}
      />
      <span>
        Secteur prioritaire
        <span className="case-aide">
          alertes par SMS dès le niveau élevé, WhatsApp au niveau critique
        </span>
      </span>
    </label>
  );
}

/* ================================================================== */
/* Catalogue de selecteurs                                             */
/* ================================================================== */

function SectionCatalogue({ selecteurs, categories, agir }) {
  const [nouveau, setNouveau] = useState({ valeur: "", categorie_id: "" });
  const [recherche, setRecherche] = useState("");
  const [filtreCategorie, setFiltreCategorie] = useState("");
  const [enEdition, setEnEdition] = useState(null);
  const [aSupprimer, setASupprimer] = useState(null);
  const [enCours, setEnCours] = useState(false);

  const terme = pourRecherche(recherche);
  const affiches = selecteurs.filter(
    (s) =>
      (!terme || pourRecherche(s.valeur).includes(terme)) &&
      (!filtreCategorie || s.categorie.id === filtreCategorie),
  );
  const filtreActif = Boolean(terme || filtreCategorie);
  const actifs = selecteurs.filter((s) => s.actif).length;

  async function ajouterSelecteur(evenement) {
    evenement.preventDefault();
    const valeur = nouveau.valeur.trim();
    const ok = await agir(
      () => api.ajouterSelecteur(valeur, nouveau.categorie_id),
      `Sélecteur « ${valeur} » ajouté.`,
    );
    if (ok) setNouveau((n) => ({ ...n, valeur: "" }));
  }

  async function enregistrerEdition() {
    setEnCours(true);
    const ok = await agir(
      () => api.modifierSelecteur(enEdition.id, enEdition.valeur.trim(), enEdition.categorie_id),
      "Sélecteur modifié.",
    );
    setEnCours(false);
    if (ok) setEnEdition(null);
  }

  async function confirmerSuppression() {
    setEnCours(true);
    const ok = await agir(
      () => api.supprimerSelecteur(aSupprimer.id),
      `Sélecteur « ${aSupprimer.valeur} » supprimé.`,
    );
    setEnCours(false);
    if (ok) setASupprimer(null);
  }

  async function desactiverPlutot() {
    const cible = aSupprimer;
    setASupprimer(null);
    await agir(() => api.basculerSelecteur(cible.id), `Sélecteur « ${cible.valeur} » désactivé.`);
  }

  return (
    <section>
      <h2 className="section-title">
        Catalogue de sélecteurs
        <span className="count">
          {actifs} actif(s) sur {selecteurs.length}
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
            onChange={(e) => setNouveau((n) => ({ ...n, valeur: e.target.value }))}
            required
          />
        </div>

        <div className="field">
          <label className="field-label" htmlFor="sel-cat">
            Catégorie
          </label>
          <SelectCategorie
            id="sel-cat"
            categories={categories}
            valeur={nouveau.categorie_id}
            onChange={(v) => setNouveau((n) => ({ ...n, categorie_id: v }))}
            required
          />
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
          {categories.map((c) => (
            <option key={c.id} value={c.id}>
              {c.nom}
            </option>
          ))}
        </select>
        <span className="barre-recherche-compte" aria-live="polite">
          {filtreActif
            ? `${affiches.length} résultat(s) sur ${selecteurs.length}`
            : `${selecteurs.length} sélecteur(s)`}
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
              <th style={{ width: 190 }}>
                <span className="sr-only">Actions</span>
              </th>
            </tr>
          </thead>
          <tbody>
            {affiches.map((s) => (
              <tr key={s.id}>
                <td className="cell-entity">{s.valeur}</td>
                <td className="cell-muted">{s.categorie.nom}</td>
                <td className="cell-muted">
                  {s.propose_par_ner ? "Proposé par NER" : "Catalogue"}
                </td>
                <td>
                  <button
                    className={`btn btn-sm ${s.actif ? "" : "btn-ghost"}`}
                    onClick={() =>
                      agir(
                        () => api.basculerSelecteur(s.id),
                        `Sélecteur « ${s.valeur} » ${s.actif ? "désactivé" : "activé"}.`,
                      )
                    }
                  >
                    {s.actif ? "Actif" : "Inactif"}
                  </button>
                </td>
                <td>
                  <div className="btn-row" style={{ justifyContent: "flex-end" }}>
                    <button
                      className="btn btn-ghost btn-sm"
                      onClick={() =>
                        setEnEdition({ id: s.id, valeur: s.valeur, categorie_id: s.categorie.id })
                      }
                      aria-label={`Modifier le sélecteur ${s.valeur}`}
                    >
                      Modifier
                    </button>
                    <button
                      className="btn btn-ghost btn-sm bouton-supprimer"
                      onClick={() => setASupprimer(s)}
                      aria-label={`Supprimer le sélecteur ${s.valeur}`}
                    >
                      Supprimer
                    </button>
                  </div>
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>

      {affiches.length === 0 && (
        <p className="page-subtitle" style={{ marginTop: 11 }}>
          Aucun sélecteur ne correspond à cette recherche.
        </p>
      )}

      {enEdition && (
        <Confirmation
          titre="Modifier le sélecteur"
          libelleConfirmer="Enregistrer"
          libelleEnCours="Enregistrement…"
          variante="primaire"
          focusAnnuler={false}
          enCours={enCours}
          desactiverConfirmer={!enEdition.valeur.trim() || !enEdition.categorie_id}
          onConfirmer={enregistrerEdition}
          onAnnuler={() => setEnEdition(null)}
        >
          <div className="field">
            <label className="field-label" htmlFor="edit-sel-valeur">Valeur</label>
            <input
              id="edit-sel-valeur"
              className="input"
              autoFocus
              value={enEdition.valeur}
              onChange={(e) => setEnEdition((s) => ({ ...s, valeur: e.target.value }))}
            />
          </div>
          <div className="field">
            <label className="field-label" htmlFor="edit-sel-cat">Catégorie</label>
            <SelectCategorie
              id="edit-sel-cat"
              categories={categories}
              valeur={enEdition.categorie_id}
              onChange={(v) => setEnEdition((s) => ({ ...s, categorie_id: v }))}
            />
          </div>
          <p className="cell-muted">
            La modification vaut pour les collectes à venir. Les expositions déjà
            détectées gardent leurs catégories.
          </p>
        </Confirmation>
      )}

      {aSupprimer && (
        <Confirmation
          titre="Supprimer ce sélecteur ?"
          libelleConfirmer="Supprimer définitivement"
          enCours={enCours}
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
            <span className="cell-muted"> — {aSupprimer.categorie.nom}</span>
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
    </section>
  );
}

function SelectCategorie({ id, categories, valeur, onChange, required }) {
  return (
    <select
      id={id}
      className="select"
      value={valeur}
      onChange={(e) => onChange(e.target.value)}
      required={required}
    >
      <option value="">Choisir…</option>
      {categories.map((c) => (
        <option key={c.id} value={c.id}>
          {c.nom}
        </option>
      ))}
    </select>
  );
}

/* ================================================================== */
/* Reglages systeme                                                    */
/* ================================================================== */

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
