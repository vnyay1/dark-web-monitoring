import { useState } from "react";

import { api } from "../api/client";
import { useChargement, useMessages } from "../api/session";
import {
  Chargement,
  EnTetePage,
  Erreur,
  formaterDate,
  LIBELLE_ROLE,
  Messages,
} from "../components/communs";

const FORMULAIRE_VIDE = {
  nom_utilisateur: "",
  mot_de_passe: "",
  role: "user",
};

export default function Comptes() {
  const { messages, ajouter } = useMessages();
  const { donnees, erreur, chargement, recharger } = useChargement(() =>
    api.utilisateurs(),
  );

  const [formulaire, setFormulaire] = useState(FORMULAIRE_VIDE);

  async function creer(evenement) {
    evenement.preventDefault();
    try {
      await api.creerUtilisateur({
        ...formulaire,
        nom_utilisateur: formulaire.nom_utilisateur.trim(),
      });
      ajouter(`Compte « ${formulaire.nom_utilisateur.trim()} » créé.`);
      setFormulaire(FORMULAIRE_VIDE);
      recharger();
    } catch (e) {
      ajouter(e.message, "error");
    }
  }

  async function changerRole(id, role) {
    try {
      await api.changerRole(id, role);
      ajouter("Rôle mis à jour.");
      recharger();
    } catch (e) {
      ajouter(e.message, "error");
      recharger();
    }
  }

  async function basculer(id) {
    try {
      await api.basculerActif(id);
      recharger();
    } catch (e) {
      ajouter(e.message, "error");
    }
  }

  if (chargement) return <Chargement />;
  if (erreur) return <Erreur message={erreur} />;

  const estSuperAdmin = donnees.est_super_admin;

  // Un admin ne peut pas creer de super_admin : la liste proposee reflete
  // ce que le serveur acceptera, plutot que de laisser l'utilisateur
  // decouvrir le refus apres coup.
  const rolesAttribuables = donnees.roles.filter(
    (r) => estSuperAdmin || r !== "super_admin",
  );

  return (
    <>
      <EnTetePage
        titre="Comptes"
        sousTitre="Gestion des accès analystes et de leurs privilèges"
      />

      <form className="card filters" onSubmit={creer}>
        <div className="field">
          <label className="field-label" htmlFor="u-nom">
            Identifiant
          </label>
          <input
            id="u-nom"
            className="input"
            value={formulaire.nom_utilisateur}
            onChange={(e) =>
              setFormulaire((f) => ({ ...f, nom_utilisateur: e.target.value }))
            }
            required
          />
        </div>

        <div className="field">
          <label className="field-label" htmlFor="u-mdp">
            Mot de passe
          </label>
          <input
            id="u-mdp"
            className="input"
            type="password"
            value={formulaire.mot_de_passe}
            onChange={(e) =>
              setFormulaire((f) => ({ ...f, mot_de_passe: e.target.value }))
            }
            autoComplete="new-password"
            required
          />
        </div>

        <div className="field">
          <label className="field-label" htmlFor="u-role">
            Rôle
          </label>
          <select
            id="u-role"
            className="select"
            value={formulaire.role}
            onChange={(e) =>
              setFormulaire((f) => ({ ...f, role: e.target.value }))
            }
          >
            {rolesAttribuables.map((r) => (
              <option key={r} value={r}>
                {LIBELLE_ROLE[r] || r}
              </option>
            ))}
          </select>
        </div>

        <div className="btn-row">
          <button className="btn btn-primary" type="submit">
            Créer le compte
          </button>
        </div>
      </form>

      <p className="page-subtitle" style={{ marginBottom: 16 }}>
        Le mot de passe doit contenir au moins 8 caractères, dont une
        majuscule, une minuscule et un caractère spécial.
      </p>

      <div className="table-wrap">
        <table className="data">
          <thead>
            <tr>
              <th>Identifiant</th>
              <th>Rôle</th>
              <th>Créé le</th>
              <th style={{ width: 160 }}>État</th>
            </tr>
          </thead>
          <tbody>
            {donnees.utilisateurs.map((u) => {
              const cestMoi = u.id === donnees.moi;
              const cibleProtegee = ["admin", "super_admin"].includes(u.role);
              const peutAgir = estSuperAdmin || !cibleProtegee;

              return (
                <tr key={u.id}>
                  <td className="cell-entity">
                    {u.nom_utilisateur}
                    {cestMoi && (
                      <span className="pill pill-neutral" style={{ marginLeft: 8 }}>
                        vous
                      </span>
                    )}
                  </td>
                  <td>
                    <select
                      className="select"
                      style={{ minWidth: 175 }}
                      value={u.role}
                      disabled={!peutAgir}
                      onChange={(e) => changerRole(u.id, e.target.value)}
                      aria-label={`Rôle de ${u.nom_utilisateur}`}
                    >
                      {donnees.roles.map((r) => (
                        <option
                          key={r}
                          value={r}
                          disabled={r === "super_admin" && !estSuperAdmin}
                        >
                          {LIBELLE_ROLE[r] || r}
                        </option>
                      ))}
                    </select>
                  </td>
                  <td className="cell-mono">{formaterDate(u.date_creation)}</td>
                  <td>
                    <button
                      className={`btn btn-sm ${u.actif ? "" : "btn-ghost"}`}
                      disabled={cestMoi || !peutAgir}
                      onClick={() => basculer(u.id)}
                      title={
                        cestMoi
                          ? "Vous ne pouvez pas désactiver votre propre compte"
                          : undefined
                      }
                    >
                      {u.actif ? "Actif" : "Désactivé"}
                    </button>
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
