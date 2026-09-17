/**
 * Comptes analystes et privileges.
 *
 * La liste des roles proposes reflete ce que le serveur acceptera (un admin
 * ne cree pas de super-admin) ; le serveur reste juge (role_requis, regles
 * de hierarchie dans app/web/permissions.py).
 */

import { useState } from "react";

import { api } from "../api/client";
import { useChargement, useMessages } from "../api/session";
import { ChoixEnregistre } from "../components/ChoixStatut";
import Interrupteur from "../components/Interrupteur";
import {
  Chargement,
  EnTetePage,
  Erreur,
  formaterDate,
  IndicateurRechargement,
  LIBELLE_ROLE,
  Messages,
} from "../components/communs";
import { IconeAjouter, IconeOeil, IconeOeilBarre } from "../components/icones";

const FORMULAIRE_VIDE = {
  nom_utilisateur: "",
  mot_de_passe: "",
  role: "user",
};

export default function Comptes() {
  const { messages, ajouter } = useMessages();
  const { donnees, erreur, chargement, rechargement, recharger } = useChargement(() => api.utilisateurs());

  const [formulaire, setFormulaire] = useState(FORMULAIRE_VIDE);
  const [visible, setVisible] = useState(false);
  const [envoi, setEnvoi] = useState(false);
  const [bascule, setBascule] = useState(null);

  async function creer(evenement) {
    evenement.preventDefault();
    setEnvoi(true);
    try {
      await api.creerUtilisateur({ ...formulaire, nom_utilisateur: formulaire.nom_utilisateur.trim() });
      ajouter(`Compte « ${formulaire.nom_utilisateur.trim()} » créé.`);
      setFormulaire(FORMULAIRE_VIDE);
      setVisible(false);
      recharger();
    } catch (e) {
      ajouter(e.message, "error");
    } finally {
      setEnvoi(false);
    }
  }

  async function changerRole(utilisateur, role) {
    try {
      await api.changerRole(utilisateur.id, role);
      ajouter(`${utilisateur.nom_utilisateur} : rôle « ${LIBELLE_ROLE[role] || role} » enregistré.`);
      recharger();
      return true;
    } catch (e) {
      ajouter(e.message, "error");
      return false;
    }
  }

  async function basculer(utilisateur) {
    setBascule(utilisateur.id);
    try {
      await api.basculerActif(utilisateur.id);
      ajouter(`Compte « ${utilisateur.nom_utilisateur} » ${utilisateur.actif ? "désactivé" : "réactivé"}.`);
      recharger();
    } catch (e) {
      ajouter(e.message, "error");
    } finally {
      setBascule(null);
    }
  }

  if (chargement) return <Chargement />;
  if (erreur && !donnees) return <Erreur message={erreur} onReessayer={recharger} />;

  const estSuperAdmin = donnees.est_super_admin;
  const rolesAttribuables = donnees.roles.filter((r) => estSuperAdmin || r !== "super_admin");

  return (
    <>
      <IndicateurRechargement actif={rechargement} />
      <EnTetePage titre="Comptes" sousTitre="Gestion des accès analystes et de leurs privilèges" />

      <form className="card card-pad formulaire-ajout" onSubmit={creer} aria-labelledby="titre-nouveau-compte">
        <h2 className="section-title" id="titre-nouveau-compte">
          Nouveau compte
        </h2>
        <div className="formulaire-ligne">
          <div className="field">
            <label className="field-label" htmlFor="u-nom">
              Identifiant
            </label>
            <input
              id="u-nom"
              className="input"
              value={formulaire.nom_utilisateur}
              onChange={(e) => setFormulaire((f) => ({ ...f, nom_utilisateur: e.target.value }))}
              autoComplete="off"
              autoCapitalize="none"
              spellCheck={false}
              required
            />
          </div>

          <div className="field">
            <label className="field-label" htmlFor="u-mdp">
              Mot de passe initial
            </label>
            <div className="champ-groupe">
              <input
                id="u-mdp"
                className="input"
                type={visible ? "text" : "password"}
                value={formulaire.mot_de_passe}
                onChange={(e) => setFormulaire((f) => ({ ...f, mot_de_passe: e.target.value }))}
                autoComplete="new-password"
                aria-describedby="u-mdp-regles"
                minLength={8}
                required
              />
              <button
                type="button"
                className="champ-bouton"
                onClick={() => setVisible((v) => !v)}
                aria-pressed={visible}
                aria-label="Afficher le mot de passe"
                aria-controls="u-mdp"
              >
                {visible ? <IconeOeilBarre taille={18} /> : <IconeOeil taille={18} />}
              </button>
            </div>
            <span className="field-aide" id="u-mdp-regles">
              Au moins 8 caractères, dont une majuscule, une minuscule et un caractère spécial.
            </span>
          </div>

          <div className="field">
            <label className="field-label" htmlFor="u-role">
              Rôle
            </label>
            <select
              id="u-role"
              className="select"
              value={formulaire.role}
              onChange={(e) => setFormulaire((f) => ({ ...f, role: e.target.value }))}
            >
              {rolesAttribuables.map((r) => (
                <option key={r} value={r}>
                  {LIBELLE_ROLE[r] || r}
                </option>
              ))}
            </select>
          </div>
        </div>
        <div className="formulaire-options">
          <button className="btn btn-primary" type="submit" disabled={envoi}>
            {envoi ? <span className="spinner" aria-hidden="true" /> : <IconeAjouter taille={16} />}
            Créer le compte
          </button>
        </div>
      </form>

      <Erreur message={erreur} onReessayer={recharger} />

      <div className="table-wrap tableau-cartes">
        <table className="data">
          <caption className="sr-only">Comptes utilisateurs</caption>
          <thead>
            <tr>
              <th scope="col">Identifiant</th>
              <th scope="col">Rôle</th>
              <th scope="col">Créé le</th>
              <th scope="col">Compte actif</th>
            </tr>
          </thead>
          <tbody>
            {donnees.utilisateurs.map((u) => {
              const cestMoi = u.id === donnees.moi;
              const cibleProtegee = ["admin", "super_admin"].includes(u.role);
              const peutAgir = estSuperAdmin || !cibleProtegee;

              return (
                <tr key={u.id}>
                  <td className="cell-titre">
                    <span className="cell-entity">{u.nom_utilisateur}</span>
                    {cestMoi && <span className="pill pill-neutral espace-gauche">Vous</span>}
                  </td>
                  <td data-label="Rôle">
                    {peutAgir ? (
                      <ChoixEnregistre
                        compact
                        valeur={u.role}
                        libelle={`Rôle de ${u.nom_utilisateur}`}
                        options={donnees.roles.map((r) => [r, LIBELLE_ROLE[r] || r, r === "super_admin" && !estSuperAdmin])}
                        onEnregistrer={(role) => changerRole(u, role)}
                      />
                    ) : (
                      <span className={`role-tag role-${u.role}`}>{LIBELLE_ROLE[u.role] || u.role}</span>
                    )}
                  </td>
                  <td className="cell-mono" data-label="Créé le">
                    {formaterDate(u.date_creation)}
                  </td>
                  <td data-label="Compte actif">
                    <div className="cellule-interrupteur">
                      <Interrupteur
                        actif={u.actif}
                        libelle={`Compte ${u.nom_utilisateur} actif`}
                        libelleVisible={u.actif ? "Actif" : "Désactivé"}
                        desactive={cestMoi || !peutAgir}
                        enCours={bascule === u.id}
                        onChange={() => basculer(u)}
                      />
                      {cestMoi && <span className="field-aide">votre propre compte</span>}
                      {!cestMoi && !peutAgir && <span className="field-aide">privilège supérieur requis</span>}
                    </div>
                  </td>
                </tr>
              );
            })}
          </tbody>
        </table>
      </div>

      <Messages messages={messages} />
    </>
  );
}
