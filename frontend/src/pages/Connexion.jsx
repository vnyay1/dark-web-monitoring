import { useState } from "react";
import { Navigate, useNavigate } from "react-router-dom";

import { useSession } from "../api/session";
import logoAntic from "../assets/logo-antic.png";
import { Chargement } from "../components/communs";
import "./connexion.css";

export default function Connexion() {
  const { utilisateur, chargement, connexion } = useSession();
  const navigate = useNavigate();

  const [nom, setNom] = useState("");
  const [motDePasse, setMotDePasse] = useState("");
  const [erreur, setErreur] = useState(null);
  const [envoi, setEnvoi] = useState(false);

  if (chargement) return <Chargement texte="Vérification de la session…" />;
  if (utilisateur) return <Navigate to="/" replace />;

  async function soumettre(evenement) {
    evenement.preventDefault();
    setErreur(null);
    setEnvoi(true);

    try {
      await connexion(nom.trim(), motDePasse);
      navigate("/", { replace: true });
    } catch (e) {
      setErreur(e.message);
      setMotDePasse("");
    } finally {
      setEnvoi(false);
    }
  }

  return (
    <div className="ecran-connexion">
      <form className="carte-connexion" onSubmit={soumettre}>
        <div className="connexion-entete">
          <img className="connexion-logo" src={logoAntic} alt="ANTIC" />
          <h1>SENTINEL</h1>
          <p>Surveillance de sources clandestines — ANTIC</p>
        </div>

        {erreur && (
          <div className="banner banner-error" role="alert">
            {erreur}
          </div>
        )}

        <div className="field">
          <label className="field-label" htmlFor="nom">
            Identifiant
          </label>
          <input
            id="nom"
            className="input"
            value={nom}
            onChange={(e) => setNom(e.target.value)}
            autoComplete="username"
            autoFocus
            required
          />
        </div>

        <div className="field">
          <label className="field-label" htmlFor="mdp">
            Mot de passe
          </label>
          <input
            id="mdp"
            className="input"
            type="password"
            value={motDePasse}
            onChange={(e) => setMotDePasse(e.target.value)}
            autoComplete="current-password"
            required
          />
        </div>

        <button
          className="btn btn-primary"
          type="submit"
          disabled={envoi}
          style={{ width: "100%", marginTop: 4 }}
        >
          {envoi ? "Connexion…" : "Se connecter"}
        </button>

        <p className="connexion-note">
          Accès réservé aux analystes habilités. Toute connexion est
          journalisée.
        </p>
      </form>
    </div>
  );
}
