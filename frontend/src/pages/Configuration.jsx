/**
 * Configuration systeme, categories, catalogue de selecteurs et liste
 * d'exclusion, en quatre onglets (l'onglet ouvert est dans l'adresse :
 * ?onglet=catalogue).
 *
 * Les reglages systeme sont saisis selon leur TYPE declare cote serveur :
 * un menu deroulant pour un palier de criticite, un champ numerique sinon.
 * C'est le serveur qui reste juge - valider_valeur() refait le controle, et
 * son message d'erreur s'affiche sous le champ concerne.
 *
 * Les categories (FR-13) sont celles des selecteurs, et deviennent celles
 * des expositions qu'ils declenchent. Une categorie utilisee ne peut etre
 * supprimee qu'en transferant ses selecteurs et ses expositions vers une
 * autre : rien n'est perdu.
 *
 * La liste d'exclusion (FR-11) est le pendant du catalogue : ce que le
 * systeme s'interdit de signaler. Le bouton « Tester » confronte un motif
 * aux donnees deja enregistrees AVANT de l'enregistrer, un motif trop large
 * pouvant aveugler la detection d'une source entiere. Son resultat ne
 * comporte que des compteurs et des noms d'entite - jamais le texte d'une
 * annonce, dont la lecture reste reservee au bouton « Details ».
 */

import { useId, useState } from "react";
import { useSearchParams } from "react-router-dom";

import { api } from "../api/client";
import { useChargement, useMessages } from "../api/session";
import Confirmation from "../components/Confirmation";
import Interrupteur from "../components/Interrupteur";
import { ListeOnglets, PanneauOnglet } from "../components/Onglets";
import {
  Banniere,
  Chargement,
  EnTetePage,
  Erreur,
  formaterDate,
  fuseauLocal,
  IndicateurRechargement,
  LIBELLE_NIVEAU,
  Messages,
  pluriel,
  Vide,
} from "../components/communs";
import {
  IconeAjouter,
  IconeAttention,
  IconeFermer,
  IconeModifier,
  IconeRecherche,
  IconeSupprimer,
} from "../components/icones";

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

// Poids d'un selecteur dans la criticite, aligne sur app.models.POIDS_MAXIMAL
// (l'API le verifie aussi).
const POIDS_MAXIMAL = 5;

/**
 * Presentation des reglages : libelle clair, unite et aide en francais. La
 * cle technique reste affichee, discrete. Une cle inconnue (ajoutee cote
 * serveur plus tard) apparait dans "Autres reglages" avec sa description.
 */
const GROUPES_REGLAGES = [
  {
    titre: "Criticité",
    description:
      "Paliers exprimés en points : chaque sélecteur camerounais distinct trouvé dans une annonce " +
      "compte pour son poids (1, davantage pour un sélecteur prioritaire).",
    reglages: {
      seuil_criticite_moyenne: { libelle: "Seuil « Moyenne »", unite: "points" },
      seuil_criticite_elevee: { libelle: "Seuil « Élevée »", unite: "points" },
      seuil_criticite_critique: { libelle: "Seuil « Critique »", unite: "points" },
      criticite_minimum_enregistrement: {
        libelle: "Minimum pour enregistrer",
        unite: "points",
        aide: "En dessous, une entrée n'est pas enregistrée comme exposition.",
      },
    },
  },
  {
    titre: "Alertes",
    reglages: {
      niveau_alerte_minimum: {
        libelle: "Niveau minimal d'alerte",
        aide: "Une exposition de niveau inférieur ne déclenche aucune alerte.",
      },
      hausse_criticite_confirmation: {
        libelle: "Hausse déclenchant une confirmation",
        unite: "points",
        aide: "Nouvelle alerte quand la criticité d'une exposition connue augmente d'au moins cette valeur.",
      },
    },
  },
  {
    titre: "Collecte",
    reglages: {
      periode_collecte_jours: {
        libelle: "Période analysée",
        unite: "jours",
        aide: "Les annonces plus anciennes sont ignorées.",
      },
      pages_listing_max: {
        libelle: "Pages parcourues au plus",
        unite: "pages par source",
        aide: "Plafond par source et par cycle, pour les sources paginées.",
      },
      sources_en_parallele: {
        libelle: "Sources collectées en parallèle",
        unite: "sources",
        aide: "1 : une source après l'autre. Chaque source garde son délai d'au moins 30 s entre deux requêtes.",
      },
    },
  },
  {
    titre: "Planification",
    description: "La collecte quotidienne part à une heure tirée au hasard dans cette plage, exprimée en UTC.",
    reglages: {
      collecte_heure_min: { libelle: "Heure la plus tôt", unite: "h UTC", heure: true },
      collecte_heure_max: { libelle: "Heure la plus tard", unite: "h UTC", heure: true },
    },
  },
];

const ONGLETS = ["reglages", "categories", "catalogue", "exclusions"];

/** Heure UTC ramenee a l'heure locale du navigateur. */
function heureLocale(heureUtc) {
  const h = Number(heureUtc);
  if (!Number.isInteger(h) || h < 0 || h > 23) return null;
  return new Date(Date.UTC(2000, 0, 1, h)).getHours();
}

export default function Configuration() {
  const { messages, ajouter } = useMessages();
  const [parametres, setParametres] = useSearchParams();
  const onglet = ONGLETS.includes(parametres.get("onglet")) ? parametres.get("onglet") : "reglages";

  const config = useChargement(() => api.configuration());
  // Une seule requete pour le catalogue ET les categories (avec compteurs).
  const catalogue = useChargement(() => api.selecteurs());
  // Chargement separe : la liste d'exclusion a son propre cycle de vie et
  // n'a pas a etre rechargee a chaque retouche du catalogue.
  const exclusions = useChargement(() => api.exclusions());

  /** Retourne null si enregistre, le message d'erreur sinon. */
  async function enregistrerConfig(cle, valeur) {
    try {
      await api.modifierConfiguration(cle, valeur);
      ajouter("Réglage enregistré.");
      config.recharger();
      return null;
    } catch (e) {
      return e.message;
    }
  }

  /**
   * Execute une action d'administration, puis recharge la liste concernee
   * (le catalogue par defaut, la liste d'exclusion pour l'onglet dedie).
   */
  async function agir(action, succes, recharger = catalogue.recharger) {
    try {
      const reponse = await action();
      ajouter(typeof succes === "function" ? succes(reponse) : succes);
      recharger();
      return true;
    } catch (e) {
      ajouter(e.message, "error");
      return false;
    }
  }

  /** `agir` de l'onglet Exclusions : meme contrat, autre liste a recharger. */
  const agirExclusions = (action, succes) => agir(action, succes, exclusions.recharger);

  if (config.chargement || catalogue.chargement || exclusions.chargement) return <Chargement />;

  const modifiable = config.donnees?.modifiable;
  const categories = catalogue.donnees?.categories || [];
  const selecteurs = catalogue.donnees?.selecteurs || [];
  const reglesExclusion = exclusions.donnees?.exclusions || [];

  return (
    <>
      <IndicateurRechargement
        actif={config.rechargement || catalogue.rechargement || exclusions.rechargement}
      />
      <EnTetePage
        titre="Configuration"
        sousTitre="Réglages système, catégories, catalogue de sélecteurs et liste d'exclusion"
      />

      <Erreur
        message={config.erreur || catalogue.erreur || exclusions.erreur}
        onReessayer={() => {
          config.recharger();
          catalogue.recharger();
          exclusions.recharger();
        }}
      />

      <ListeOnglets
        idBase="config"
        libelle="Sections de la configuration"
        actif={onglet}
        onChange={(cle) => setParametres({ onglet: cle }, { replace: true })}
        onglets={[
          { cle: "reglages", libelle: "Réglages système" },
          { cle: "categories", libelle: "Catégories", compte: categories.length },
          { cle: "catalogue", libelle: "Catalogue de sélecteurs", compte: selecteurs.length },
          { cle: "exclusions", libelle: "Liste d'exclusion", compte: reglesExclusion.length },
        ]}
      />

      {onglet === "reglages" && (
        <PanneauOnglet cle="reglages" idBase="config">
          <SectionReglages
            configurations={config.donnees?.configurations || []}
            modifiable={modifiable}
            onEnregistrer={enregistrerConfig}
          />
        </PanneauOnglet>
      )}
      {onglet === "categories" && (
        <PanneauOnglet cle="categories" idBase="config">
          <SectionCategories categories={categories} agir={agir} />
        </PanneauOnglet>
      )}
      {onglet === "catalogue" && (
        <PanneauOnglet cle="catalogue" idBase="config">
          <SectionCatalogue selecteurs={selecteurs} categories={categories} agir={agir} />
        </PanneauOnglet>
      )}
      {onglet === "exclusions" && (
        <PanneauOnglet cle="exclusions" idBase="config">
          <SectionExclusions
            exclusions={reglesExclusion}
            sources={exclusions.donnees?.sources || []}
            types={exclusions.donnees?.types || []}
            modifiable={exclusions.donnees?.modifiable}
            agir={agirExclusions}
          />
        </PanneauOnglet>
      )}

      <Messages messages={messages} />
    </>
  );
}

/* ================================================================== */
/* Reglages systeme                                                    */
/* ================================================================== */

function SectionReglages({ configurations, modifiable, onEnregistrer }) {
  const parCle = Object.fromEntries(configurations.map((c) => [c.cle, c]));
  const connues = new Set(GROUPES_REGLAGES.flatMap((g) => Object.keys(g.reglages)));
  const autres = configurations.filter((c) => !connues.has(c.cle));

  const groupes = [
    ...GROUPES_REGLAGES,
    ...(autres.length ? [{ titre: "Autres réglages", reglages: Object.fromEntries(autres.map((c) => [c.cle, {}])) }] : []),
  ];

  return (
    <>
      {!modifiable && (
        <Banniere ton="info">
          <p>Consultation seule : la modification des réglages système est réservée au super-administrateur.</p>
        </Banniere>
      )}

      <div className="reglages">
        {groupes.map((groupe) => (
          <section className="card card-pad groupe-reglages" key={groupe.titre} aria-labelledby={`groupe-${groupe.titre}`}>
            <h2 className="section-title" id={`groupe-${groupe.titre}`}>
              {groupe.titre}
            </h2>
            {groupe.description && <p className="texte-aide groupe-description">{groupe.description}</p>}
            <div className="liste-reglages">
              {Object.entries(groupe.reglages).map(([cle, presentation]) =>
                parCle[cle] ? (
                  <ChampReglage
                    key={cle}
                    entree={parCle[cle]}
                    presentation={presentation}
                    modifiable={modifiable}
                    onEnregistrer={onEnregistrer}
                  />
                ) : null,
              )}
            </div>
          </section>
        ))}
      </div>
    </>
  );
}

function ChampReglage({ entree, presentation, modifiable, onEnregistrer }) {
  const [valeur, setValeur] = useState(entree.valeur);
  const [erreur, setErreur] = useState(null);
  const [enCours, setEnCours] = useState(false);
  const id = useId();
  const modifie = valeur !== entree.valeur;

  const locale = presentation.heure ? heureLocale(valeur) : null;
  const aide = presentation.aide || (!presentation.libelle ? entree.description : null);

  async function enregistrer(evenement) {
    evenement.preventDefault();
    setEnCours(true);
    const message = await onEnregistrer(entree.cle, valeur);
    setErreur(message);
    setEnCours(false);
  }

  const idsDescription = [aide && `${id}-aide`, locale !== null && `${id}-locale`, erreur && `${id}-erreur`]
    .filter(Boolean)
    .join(" ");

  return (
    <form className="reglage" onSubmit={enregistrer}>
      <div className="reglage-textes">
        <label className="reglage-libelle" htmlFor={id}>
          {presentation.libelle || entree.cle}
        </label>
        <span className="reglage-cle">{entree.cle}</span>
        {aide && (
          <span className="field-aide" id={`${id}-aide`}>
            {aide}
          </span>
        )}
      </div>

      <div className="reglage-saisie">
        <div className="reglage-controle">
          {entree.type === "niveau" ? (
            <select
              id={id}
              className="select"
              value={valeur}
              disabled={!modifiable || enCours}
              onChange={(e) => {
                setValeur(e.target.value);
                setErreur(null);
              }}
              aria-describedby={idsDescription || undefined}
              aria-invalid={erreur ? true : undefined}
            >
              {NIVEAUX.map((n) => (
                <option key={n} value={n}>
                  {LIBELLE_NIVEAU[n]}
                </option>
              ))}
            </select>
          ) : (
            <input
              id={id}
              className="input"
              type="number"
              inputMode="numeric"
              min="0"
              max={presentation.heure ? 23 : undefined}
              value={valeur}
              disabled={!modifiable || enCours}
              onChange={(e) => {
                setValeur(e.target.value);
                setErreur(null);
              }}
              aria-describedby={idsDescription || undefined}
              aria-invalid={erreur ? true : undefined}
            />
          )}
          {presentation.unite && <span className="reglage-unite">{presentation.unite}</span>}
        </div>

        {modifiable && modifie && (
          <div className="btn-row reglage-actions">
            <button type="submit" className="btn btn-primary btn-sm" disabled={enCours}>
              {enCours && <span className="spinner" aria-hidden="true" />}
              Enregistrer
            </button>
            <button
              type="button"
              className="btn btn-ghost btn-sm"
              disabled={enCours}
              onClick={() => {
                setValeur(entree.valeur);
                setErreur(null);
              }}
            >
              Annuler
            </button>
          </div>
        )}

        {locale !== null && (
          <span className="field-aide" id={`${id}-locale`}>
            soit {locale} h en heure locale ({fuseauLocal()})
          </span>
        )}
        {erreur && (
          <span className="field-erreur" id={`${id}-erreur`} role="alert">
            <IconeAttention taille={14} /> {erreur}
          </span>
        )}
      </div>
    </form>
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
    const ok = await agir(() => api.modifierCategorie(enEdition.id, enEdition), "Catégorie modifiée.");
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
          ? `Catégorie supprimée : ${r.selecteurs_transferes} ${pluriel("sélecteur", r.selecteurs_transferes)} et ` +
            `${r.expositions_transferees} ${pluriel("exposition", r.expositions_transferees)} ${pluriel("transféré", r.selecteurs_transferes + r.expositions_transferees)}.`
          : "Catégorie supprimée.",
    );
    setEnCours(false);
    if (ok) setASupprimer(null);
  }

  const utilisee = aSupprimer && (aSupprimer.nb_selecteurs || aSupprimer.nb_expositions);

  return (
    <>
      <p className="texte-aide espace-texte">
        Une exposition reçoit les catégories des sélecteurs trouvés dans l'annonce.
      </p>

      <form className="card card-pad formulaire-ajout" onSubmit={creer} aria-labelledby="titre-nouvelle-categorie">
        <h2 className="section-title" id="titre-nouvelle-categorie">
          Nouvelle catégorie
        </h2>
        <div className="formulaire-ligne">
          <div className="field">
            <label className="field-label" htmlFor="cat-nom">
              Nom
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
              Description <span className="facultatif">(facultative)</span>
            </label>
            <input
              id="cat-desc"
              className="input"
              value={nouvelle.description}
              onChange={(e) => setNouvelle((n) => ({ ...n, description: e.target.value }))}
            />
          </div>
        </div>
        <div className="formulaire-options">
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
          <button className="btn btn-primary" type="submit">
            <IconeAjouter taille={16} />
            Ajouter la catégorie
          </button>
        </div>
      </form>

      <div className="table-wrap tableau-cartes">
        <table className="data">
          <caption className="sr-only">Catégories de sélecteurs</caption>
          <thead>
            <tr>
              <th scope="col">Catégorie</th>
              <th scope="col">Description</th>
              <th scope="col" className="num-col">Sélecteurs</th>
              <th scope="col" className="num-col">Expositions</th>
              <th scope="col" className="cell-actions">
                <span className="sr-only">Actions</span>
              </th>
            </tr>
          </thead>
          <tbody>
            {categories.map((c) => (
              <tr key={c.id}>
                <td className="cell-titre">
                  <span className="cell-entity">{c.nom}</span>
                  <span className="tag-row espace-etiquettes">
                    {c.prioritaire && <span className="pill pill-warn">Secteur prioritaire</span>}
                    {c.lieu_generique && <span className="pill pill-neutral">Lieu générique</span>}
                  </span>
                </td>
                <td className="cell-muted" data-label="Description">
                  {c.description || "—"}
                </td>
                <td className="cell-mono num-col" data-label="Sélecteurs">
                  {c.nb_selecteurs}
                </td>
                <td className="cell-mono num-col" data-label="Expositions">
                  {c.nb_expositions}
                </td>
                <td className="cell-actions">
                  <div className="btn-row">
                    <button
                      type="button"
                      className="btn btn-contour btn-sm"
                      onClick={() => setEnEdition({ ...c, description: c.description || "" })}
                      aria-label={`Modifier la catégorie ${c.nom}`}
                    >
                      <IconeModifier taille={14} />
                      Modifier
                    </button>
                    <button
                      type="button"
                      className="btn btn-contour btn-sm bouton-supprimer"
                      onClick={() => ouvrirSuppression(c)}
                      aria-label={`Supprimer la catégorie ${c.nom}`}
                    >
                      <IconeSupprimer taille={14} />
                      Supprimer
                    </button>
                  </div>
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
      <p className="texte-aide espace-haut">
        <strong>Secteur prioritaire</strong> : alertes par SMS dès le niveau élevé, WhatsApp au niveau
        critique. <strong>Lieu générique</strong> : le filtre « nom de lieu dans une liste de pays »
        s'applique à ses sélecteurs.
      </p>

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
            <label className="field-label" htmlFor="edit-cat-nom">
              Nom
            </label>
            <input
              id="edit-cat-nom"
              className="input"
              maxLength={100}
              value={enEdition.nom}
              onChange={(e) => setEnEdition((c) => ({ ...c, nom: e.target.value }))}
            />
          </div>
          <div className="field">
            <label className="field-label" htmlFor="edit-cat-desc">
              Description
            </label>
            <input
              id="edit-cat-desc"
              className="input"
              value={enEdition.description}
              onChange={(e) => setEnEdition((c) => ({ ...c, description: e.target.value }))}
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
          <p className="texte-aide">
            Le nouveau nom s'applique aussi {enEdition.nb_expositions > 1 ? "aux" : "à"}{" "}
            {enEdition.nb_expositions} {pluriel("exposition", enEdition.nb_expositions)} qui{" "}
            {enEdition.nb_expositions > 1 ? "portent" : "porte"} déjà cette catégorie.
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
              {" "}
              — {aSupprimer.nb_selecteurs} {pluriel("sélecteur", aSupprimer.nb_selecteurs)},{" "}
              {aSupprimer.nb_expositions} {pluriel("exposition", aSupprimer.nb_expositions)}
            </span>
          </p>

          {utilisee ? (
            <>
              <p>
                Elle est encore utilisée : ses sélecteurs et les expositions qui la portent seront
                transférés vers la catégorie choisie. Aucun sélecteur n'est supprimé.
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
                  required
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
    </>
  );
}

function CaseLieuGenerique({ id, coche, onChange }) {
  return (
    <label className="case-a-cocher" htmlFor={id}>
      <input id={id} type="checkbox" checked={coche} onChange={(e) => onChange(e.target.checked)} />
      <span>
        Nom de lieu générique
        <span className="case-aide">villes, régions : écartés s'ils figurent dans une simple liste de pays</span>
      </span>
    </label>
  );
}

function CasePrioritaire({ id, coche, onChange }) {
  return (
    <label className="case-a-cocher" htmlFor={id}>
      <input id={id} type="checkbox" checked={coche} onChange={(e) => onChange(e.target.checked)} />
      <span>
        Secteur prioritaire
        <span className="case-aide">alertes par SMS dès le niveau élevé, WhatsApp au niveau critique</span>
      </span>
    </label>
  );
}

/* ================================================================== */
/* Catalogue de selecteurs                                             */
/* ================================================================== */

function SectionCatalogue({ selecteurs, categories, agir }) {
  const [nouveau, setNouveau] = useState({ valeur: "", categorie_id: "", poids: 1 });
  const [recherche, setRecherche] = useState("");
  const [filtreCategorie, setFiltreCategorie] = useState("");
  const [enEdition, setEnEdition] = useState(null);
  const [aSupprimer, setASupprimer] = useState(null);
  const [enCours, setEnCours] = useState(false);
  const [bascule, setBascule] = useState(null);

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
      () => api.ajouterSelecteur(valeur, nouveau.categorie_id, nouveau.poids),
      `Sélecteur « ${valeur} » ajouté.`,
    );
    if (ok) setNouveau((n) => ({ ...n, valeur: "", poids: 1 }));
  }

  async function basculer(selecteur) {
    setBascule(selecteur.id);
    await agir(
      () => api.basculerSelecteur(selecteur.id),
      `Sélecteur « ${selecteur.valeur} » ${selecteur.actif ? "désactivé" : "activé"}.`,
    );
    setBascule(null);
  }

  async function enregistrerEdition() {
    setEnCours(true);
    const ok = await agir(
      () => api.modifierSelecteur(enEdition.id, enEdition.valeur.trim(), enEdition.categorie_id, enEdition.poids),
      "Sélecteur modifié.",
    );
    setEnCours(false);
    if (ok) setEnEdition(null);
  }

  async function confirmerSuppression() {
    setEnCours(true);
    const ok = await agir(() => api.supprimerSelecteur(aSupprimer.id), `Sélecteur « ${aSupprimer.valeur} » supprimé.`);
    setEnCours(false);
    if (ok) setASupprimer(null);
  }

  async function desactiverPlutot() {
    const cible = aSupprimer;
    setASupprimer(null);
    await agir(() => api.basculerSelecteur(cible.id), `Sélecteur « ${cible.valeur} » désactivé.`);
  }

  return (
    <>
      <p className="texte-aide espace-texte">
        {actifs} {pluriel("sélecteur actif", actifs, "sélecteurs actifs")} sur {selecteurs.length}. Un
        sélecteur inactif n'est plus recherché lors des collectes. Un sélecteur prioritaire (poids 2 à{" "}
        {POIDS_MAXIMAL}) compte autant de fois dans la criticité d'une annonce où il est trouvé.
      </p>

      <form className="card card-pad formulaire-ajout" onSubmit={ajouterSelecteur} aria-labelledby="titre-nouveau-selecteur">
        <h2 className="section-title" id="titre-nouveau-selecteur">
          Nouveau sélecteur
        </h2>
        <div className="formulaire-ligne formulaire-ligne-action">
          <div className="field">
            <label className="field-label" htmlFor="sel-valeur">
              Valeur
            </label>
            <input
              id="sel-valeur"
              className="input"
              placeholder="Ex : MINSANTE"
              value={nouveau.valeur}
              onChange={(e) => setNouveau((n) => ({ ...n, valeur: e.target.value }))}
              aria-describedby="aide-sel-valeur"
              required
            />
            <span className="field-aide" id="aide-sel-valeur">
              6 caractères ou moins : reconnu seulement tel quel, casse comprise, et en mot entier.
            </span>
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
          <div className="field">
            <label className="field-label" htmlFor="sel-poids">
              Poids
            </label>
            <SelectPoids
              id="sel-poids"
              valeur={nouveau.poids}
              onChange={(v) => setNouveau((n) => ({ ...n, poids: v }))}
            />
          </div>
          <button className="btn btn-primary" type="submit">
            <IconeAjouter taille={16} />
            Ajouter
          </button>
        </div>
      </form>

      {/* Filtrage en direct cote client : le catalogue compte au plus
          quelques centaines d'entrees. */}
      <div className="barre-recherche" role="search" aria-label="Rechercher dans le catalogue">
        <div className="champ-groupe">
          <IconeRecherche taille={16} className="champ-icone" />
          <input
            className="input"
            type="search"
            placeholder="Rechercher un sélecteur"
            value={recherche}
            onChange={(e) => setRecherche(e.target.value)}
            aria-label="Rechercher un sélecteur par nom"
          />
        </div>
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
        <span className="barre-recherche-compte" role="status">
          {filtreActif
            ? `${affiches.length} ${pluriel("résultat", affiches.length)} sur ${selecteurs.length}`
            : `${selecteurs.length} ${pluriel("sélecteur", selecteurs.length)}`}
        </span>
        {filtreActif && (
          <button
            type="button"
            className="btn btn-ghost btn-sm"
            onClick={() => {
              setRecherche("");
              setFiltreCategorie("");
            }}
          >
            <IconeFermer taille={14} />
            Effacer la recherche
          </button>
        )}
      </div>

      {affiches.length === 0 ? (
        <Vide titre="Aucun sélecteur ne correspond" icone={IconeRecherche}>
          Modifiez la recherche ou la catégorie.
        </Vide>
      ) : (
        <div className="table-wrap tableau-cartes">
          <table className="data">
            <caption className="sr-only">Catalogue de sélecteurs</caption>
            <thead>
              <tr>
                <th scope="col">Sélecteur</th>
                <th scope="col">Catégorie</th>
                <th scope="col">Actif</th>
                <th scope="col" className="cell-actions">
                  <span className="sr-only">Actions</span>
                </th>
              </tr>
            </thead>
            <tbody>
              {affiches.map((s) => (
                <tr key={s.id}>
                  <td className={`cell-titre${s.actif ? "" : " est-inactif"}`}>
                    <span className="cell-entity">{s.valeur}</span>
                    {s.poids > 1 && (
                      <>
                        {" "}
                        <span className="pill pill-accent">Prioritaire · poids {s.poids}</span>
                      </>
                    )}
                  </td>
                  <td className="cell-muted" data-label="Catégorie">
                    {s.categorie.nom}
                  </td>
                  <td data-label="Actif">
                    <Interrupteur
                      actif={s.actif}
                      libelle={`Sélecteur ${s.valeur} actif`}
                      libelleVisible={s.actif ? "Actif" : "Inactif"}
                      enCours={bascule === s.id}
                      onChange={() => basculer(s)}
                    />
                  </td>
                  <td className="cell-actions">
                    <div className="btn-row">
                      <button
                        type="button"
                        className="btn btn-contour btn-sm"
                        onClick={() =>
                          setEnEdition({ id: s.id, valeur: s.valeur, categorie_id: s.categorie.id, poids: s.poids })
                        }
                        aria-label={`Modifier le sélecteur ${s.valeur}`}
                      >
                        <IconeModifier taille={14} />
                        Modifier
                      </button>
                      <button
                        type="button"
                        className="btn btn-contour btn-sm bouton-supprimer"
                        onClick={() => setASupprimer(s)}
                        aria-label={`Supprimer le sélecteur ${s.valeur}`}
                      >
                        <IconeSupprimer taille={14} />
                        Supprimer
                      </button>
                    </div>
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
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
            <label className="field-label" htmlFor="edit-sel-valeur">
              Valeur
            </label>
            <input
              id="edit-sel-valeur"
              className="input"
              value={enEdition.valeur}
              onChange={(e) => setEnEdition((s) => ({ ...s, valeur: e.target.value }))}
            />
          </div>
          <div className="field">
            <label className="field-label" htmlFor="edit-sel-cat">
              Catégorie
            </label>
            <SelectCategorie
              id="edit-sel-cat"
              categories={categories}
              valeur={enEdition.categorie_id}
              onChange={(v) => setEnEdition((s) => ({ ...s, categorie_id: v }))}
            />
          </div>
          <div className="field">
            <label className="field-label" htmlFor="edit-sel-poids">
              Poids
            </label>
            <SelectPoids
              id="edit-sel-poids"
              valeur={enEdition.poids}
              onChange={(v) => setEnEdition((s) => ({ ...s, poids: v }))}
            />
          </div>
          <p className="texte-aide">
            La modification vaut pour les collectes à venir. Les expositions déjà détectées gardent leurs
            catégories ; leur criticité peut augmenter lors d'une nouvelle détection, jamais baisser.
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
          actionSecondaire={aSupprimer.actif ? { libelle: "Désactiver plutôt", onClick: desactiverPlutot } : null}
        >
          <p className="fenetre-cible">
            <strong>{aSupprimer.valeur}</strong>
            <span className="cell-muted"> — {aSupprimer.categorie.nom}</span>
          </p>
          <p>
            Il sera retiré du catalogue et ne sera plus recherché lors des prochaines collectes. Les
            expositions déjà détectées ne sont pas modifiées.
          </p>
          <p className="texte-aide">
            Cette suppression est définitive. Pour suspendre le sélecteur sans le perdre, désactivez-le
            plutôt : c'est réversible à tout moment.
          </p>
        </Confirmation>
      )}
    </>
  );
}

function SelectPoids({ id, valeur, onChange }) {
  return (
    <select id={id} className="select" value={valeur} onChange={(e) => onChange(Number(e.target.value))}>
      {Array.from({ length: POIDS_MAXIMAL }, (_, i) => i + 1).map((poids) => (
        <option key={poids} value={poids}>
          {poids === 1 ? "1 — normal" : `${poids} — prioritaire`}
        </option>
      ))}
    </select>
  );
}

function SelectCategorie({ id, categories, valeur, onChange, required }) {
  return (
    <select id={id} className="select" value={valeur} onChange={(e) => onChange(e.target.value)} required={required}>
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
/* Liste d'exclusion des faux positifs (FR-11)                         */
/* ================================================================== */

const EXCLUSION_VIDE = {
  motif: "",
  type_exclusion: "entite",
  source_id: "",
  commentaire: "",
};

const LIBELLE_TYPE_EXCLUSION = {
  entite: "Nom d'entité",
  texte: "Texte de l'annonce",
};

const AIDE_TYPE_EXCLUSION = {
  entite:
    "Le motif est comparé au nom d'entité retenu pour l'annonce : le cas d'une société étrangère " +
    "homonyme, qu'aucune règle automatique ne peut deviner.",
  texte:
    "Le motif est comparé au texte de l'annonce : un en-tête ou une formule qui revient à chaque " +
    "publication d'une source.",
};

/** Au-dela, le motif ecarte une telle part de l'echantillon qu'il est probablement trop large. */
const SEUIL_APERCU_ALERTE = 20;

function SectionExclusions({ exclusions, sources, types, modifiable, agir }) {
  const [nouvelle, setNouvelle] = useState(EXCLUSION_VIDE);
  const [enEdition, setEnEdition] = useState(null);
  const [aSupprimer, setASupprimer] = useState(null);
  const [enCours, setEnCours] = useState(false);
  const [bascule, setBascule] = useState(null);
  const [apercu, setApercu] = useState(null);
  const [apercuEnCours, setApercuEnCours] = useState(false);

  const motif = nouvelle.motif.trim();

  /**
   * L'apercu ne vaut que pour le motif exact qui l'a produit : la moindre
   * frappe l'invalide, sinon le resultat affiche repondrait a une autre
   * question que celle posee par le champ.
   */
  function modifierNouvelle(champs) {
    setApercu(null);
    setNouvelle((e) => ({ ...e, ...champs }));
  }

  async function tester() {
    setApercuEnCours(true);
    try {
      setApercu(await api.apercuExclusion({ ...nouvelle, motif }));
    } catch (e) {
      setApercu({ erreur: e.message });
    }
    setApercuEnCours(false);
  }

  async function creer(evenement) {
    evenement.preventDefault();
    const ok = await agir(
      () => api.creerExclusion({ ...nouvelle, motif }),
      `Règle « ${motif} » ajoutée.`,
    );
    if (ok) {
      setNouvelle(EXCLUSION_VIDE);
      setApercu(null);
    }
  }

  async function basculer(exclusion) {
    setBascule(exclusion.id);
    await agir(
      () => api.basculerExclusion(exclusion.id),
      `Règle « ${exclusion.motif} » ${exclusion.actif ? "désactivée" : "activée"}.`,
    );
    setBascule(null);
  }

  async function enregistrerEdition() {
    setEnCours(true);
    const ok = await agir(
      () => api.modifierExclusion(enEdition.id, { ...enEdition, motif: enEdition.motif.trim() }),
      "Règle modifiée.",
    );
    setEnCours(false);
    if (ok) setEnEdition(null);
  }

  async function confirmerSuppression() {
    setEnCours(true);
    const ok = await agir(
      () => api.supprimerExclusion(aSupprimer.id),
      `Règle « ${aSupprimer.motif} » supprimée.`,
    );
    setEnCours(false);
    if (ok) setASupprimer(null);
  }

  return (
    <>
      <p className="texte-aide espace-texte">
        Les faux positifs connus, écartés automatiquement à l'analyse. Chaque règle est une
        expression régulière comparée au nom d'entité ou au texte de l'annonce, pour toutes les
        sources ou pour une seule. Une règle n'est <strong>jamais rétroactive</strong> : elle
        n'efface ni ne déclasse une exposition déjà enregistrée.
      </p>

      {modifiable && (
        <form
          className="card card-pad formulaire-ajout"
          onSubmit={creer}
          aria-labelledby="titre-nouvelle-exclusion"
        >
          <h2 className="section-title" id="titre-nouvelle-exclusion">
            Nouvelle règle
          </h2>
          <div className="formulaire-ligne">
            <div className="field">
              <label className="field-label" htmlFor="exc-motif">
                Motif
              </label>
              <input
                id="exc-motif"
                className="input"
                placeholder="Ex : Cameroon Holdings"
                value={nouvelle.motif}
                onChange={(e) => modifierNouvelle({ motif: e.target.value })}
                required
              />
            </div>
            <div className="field">
              <label className="field-label" htmlFor="exc-type">
                Comparé à
              </label>
              <select
                id="exc-type"
                className="select"
                value={nouvelle.type_exclusion}
                onChange={(e) => modifierNouvelle({ type_exclusion: e.target.value })}
              >
                {types.map((t) => (
                  <option key={t} value={t}>
                    {LIBELLE_TYPE_EXCLUSION[t] || t}
                  </option>
                ))}
              </select>
            </div>
            <div className="field">
              <label className="field-label" htmlFor="exc-source">
                Portée
              </label>
              <SelectSource
                id="exc-source"
                sources={sources}
                valeur={nouvelle.source_id}
                onChange={(v) => modifierNouvelle({ source_id: v })}
              />
            </div>
          </div>
          <div className="field">
            <label className="field-label" htmlFor="exc-commentaire">
              Commentaire <span className="facultatif">(facultatif)</span>
            </label>
            <input
              id="exc-commentaire"
              className="input"
              placeholder="Pourquoi cette règle, pour l'analyste suivant"
              value={nouvelle.commentaire}
              onChange={(e) => modifierNouvelle({ commentaire: e.target.value })}
            />
          </div>
          <p className="texte-aide">{AIDE_TYPE_EXCLUSION[nouvelle.type_exclusion]}</p>

          <div className="formulaire-options">
            <button
              className="btn btn-contour"
              type="button"
              onClick={tester}
              disabled={!motif || apercuEnCours}
            >
              <IconeRecherche taille={16} />
              {apercuEnCours ? "Test en cours…" : "Tester le motif"}
            </button>
            <button className="btn btn-primary" type="submit" disabled={!motif}>
              <IconeAjouter taille={16} />
              Ajouter la règle
            </button>
          </div>

          {apercu && <ResultatApercu apercu={apercu} />}
        </form>
      )}

      <div className="table-wrap tableau-cartes">
        <table className="data">
          <caption className="sr-only">Règles d'exclusion des faux positifs</caption>
          <thead>
            <tr>
              <th scope="col">Motif</th>
              <th scope="col">Comparé à</th>
              <th scope="col">Portée</th>
              <th scope="col">Ajoutée</th>
              <th scope="col">État</th>
              {modifiable && (
                <th scope="col" className="cell-actions">
                  <span className="sr-only">Actions</span>
                </th>
              )}
            </tr>
          </thead>
          <tbody>
            {exclusions.map((e) => (
              <tr key={e.id}>
                <td className="cell-titre">
                  <span className="cell-mono">{e.motif}</span>
                  {e.commentaire && (
                    <span className="cell-muted espace-etiquettes">{e.commentaire}</span>
                  )}
                </td>
                <td data-label="Comparé à">
                  {LIBELLE_TYPE_EXCLUSION[e.type_exclusion] || e.type_exclusion}
                </td>
                <td data-label="Portée">
                  {e.source ? (
                    <span className="pill pill-neutral">{e.source.nom}</span>
                  ) : (
                    <span className="cell-muted">Toutes les sources</span>
                  )}
                </td>
                <td className="cell-muted" data-label="Ajoutée">
                  {formaterDate(e.date_ajout)} par {e.ajoute_par}
                </td>
                <td data-label="État">
                  {modifiable ? (
                    <Interrupteur
                      actif={e.actif}
                      libelle={`Règle ${e.motif} active`}
                      libelleVisible={e.actif ? "Active" : "Inactive"}
                      enCours={bascule === e.id}
                      onChange={() => basculer(e)}
                    />
                  ) : (
                    <span className={`pill ${e.actif ? "pill-neutral" : "pill-warn"}`}>
                      {e.actif ? "Active" : "Inactive"}
                    </span>
                  )}
                </td>
                {modifiable && (
                  <td className="cell-actions">
                    <div className="btn-row">
                      <button
                        type="button"
                        className="btn btn-contour btn-sm"
                        onClick={() =>
                          setEnEdition({
                            id: e.id,
                            motif: e.motif,
                            type_exclusion: e.type_exclusion,
                            source_id: e.source?.id || "",
                            commentaire: e.commentaire || "",
                          })
                        }
                        aria-label={`Modifier la règle ${e.motif}`}
                      >
                        <IconeModifier taille={14} />
                        Modifier
                      </button>
                      <button
                        type="button"
                        className="btn btn-contour btn-sm bouton-supprimer"
                        onClick={() => setASupprimer(e)}
                        aria-label={`Supprimer la règle ${e.motif}`}
                      >
                        <IconeSupprimer taille={14} />
                        Supprimer
                      </button>
                    </div>
                  </td>
                )}
              </tr>
            ))}
          </tbody>
        </table>
        {exclusions.length === 0 && (
          <Vide titre="Aucune règle d'exclusion" icone={IconeAttention}>
            Les règles automatiques restent actives, comme le nom de lieu noyé dans une simple
            liste de pays.
          </Vide>
        )}
      </div>

      {enEdition && (
        <Confirmation
          titre="Modifier la règle"
          libelleConfirmer="Enregistrer"
          libelleEnCours="Enregistrement…"
          variante="primaire"
          focusAnnuler={false}
          enCours={enCours}
          desactiverConfirmer={!enEdition.motif.trim()}
          onConfirmer={enregistrerEdition}
          onAnnuler={() => setEnEdition(null)}
        >
          <div className="field">
            <label className="field-label" htmlFor="edit-exc-motif">
              Motif
            </label>
            <input
              id="edit-exc-motif"
              className="input"
              value={enEdition.motif}
              onChange={(e) => setEnEdition((x) => ({ ...x, motif: e.target.value }))}
            />
          </div>
          <div className="field">
            <label className="field-label" htmlFor="edit-exc-type">
              Comparé à
            </label>
            <select
              id="edit-exc-type"
              className="select"
              value={enEdition.type_exclusion}
              onChange={(e) => setEnEdition((x) => ({ ...x, type_exclusion: e.target.value }))}
            >
              {types.map((t) => (
                <option key={t} value={t}>
                  {LIBELLE_TYPE_EXCLUSION[t] || t}
                </option>
              ))}
            </select>
          </div>
          <div className="field">
            <label className="field-label" htmlFor="edit-exc-source">
              Portée
            </label>
            <SelectSource
              id="edit-exc-source"
              sources={sources}
              valeur={enEdition.source_id}
              onChange={(v) => setEnEdition((x) => ({ ...x, source_id: v }))}
            />
          </div>
          <div className="field">
            <label className="field-label" htmlFor="edit-exc-commentaire">
              Commentaire
            </label>
            <input
              id="edit-exc-commentaire"
              className="input"
              value={enEdition.commentaire}
              onChange={(e) => setEnEdition((x) => ({ ...x, commentaire: e.target.value }))}
            />
          </div>
        </Confirmation>
      )}

      {aSupprimer && (
        <Confirmation
          titre="Supprimer cette règle ?"
          enCours={enCours}
          onConfirmer={confirmerSuppression}
          onAnnuler={() => setASupprimer(null)}
        >
          <p className="fenetre-cible">
            <strong className="cell-mono">{aSupprimer.motif}</strong>
            <span className="cell-muted">
              {" "}
              — {LIBELLE_TYPE_EXCLUSION[aSupprimer.type_exclusion] || aSupprimer.type_exclusion},{" "}
              {aSupprimer.source ? aSupprimer.source.nom : "toutes les sources"}
            </span>
          </p>
          <p>
            Les prochaines collectes cesseront de l'appliquer. Les expositions déjà enregistrées ne
            sont pas modifiées. La désactivation reste l'alternative réversible.
          </p>
        </Confirmation>
      )}
    </>
  );
}

/** Portee d'une regle : toutes les sources, ou une seule. */
function SelectSource({ id, sources, valeur, onChange }) {
  return (
    <select id={id} className="select" value={valeur} onChange={(e) => onChange(e.target.value)}>
      <option value="">Toutes les sources</option>
      {sources.map((s) => (
        <option key={s.id} value={s.id}>
          {s.nom}
          {s.actif ? "" : " (retirée)"}
        </option>
      ))}
    </select>
  );
}

/**
 * Ce que le motif aurait ecarte parmi les donnees deja enregistrees.
 *
 * N'affiche que des compteurs et des NOMS D'ENTITE : le texte conserve des
 * annonces ne sort pas d'ici (CN-04/CN-05), sa lecture restant reservee au
 * bouton « Détails » d'un signalement.
 */
function ResultatApercu({ apercu }) {
  if (apercu.erreur) {
    return (
      <div className="banner banner-error espace-haut" role="alert">
        <IconeAttention taille={16} />
        {apercu.erreur}
      </div>
    );
  }

  const trop = apercu.pourcentage >= SEUIL_APERCU_ALERTE;
  const unite = apercu.type_exclusion === "entite" ? "exposition" : "signalement";

  return (
    <div className={`banner espace-haut ${trop ? "banner-warn" : "banner-info"}`} role="status">
      {trop && <IconeAttention taille={16} />}
      <div>
        <p>
          {apercu.nb_correspondances} {pluriel("correspondance", apercu.nb_correspondances)} sur{" "}
          {apercu.nb_testees} {pluriel(unite, apercu.nb_testees)}{" "}
          {pluriel("testé", apercu.nb_testees)} ({apercu.pourcentage} %).
          {trop && " Ce motif paraît trop large : il écarterait une grande part des détections."}
        </p>
        {apercu.exemples.length > 0 && (
          <p className="texte-aide">
            Aurait écarté : {apercu.exemples.map((e) => e.nom_entite).join(", ")}
            {apercu.nb_correspondances > apercu.exemples.length ? "…" : ""}
          </p>
        )}
      </div>
    </div>
  );
}
