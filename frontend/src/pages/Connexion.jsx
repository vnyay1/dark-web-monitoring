import { useRef, useState } from "react";
import { Navigate, useNavigate } from "react-router-dom";

import { useSession } from "../api/session";
import logoAntic from "../assets/logo-antic.png";
import { Chargement } from "../components/communs";
import { IconeAttention, IconeOeil, IconeOeilBarre } from "../components/icones";
import { InterrupteurTheme } from "../theme/theme";
import "./connexion.css";

export default function Connexion() {
  const { utilisateur, chargement, connexion } = useSession();
  const navigate = useNavigate();

  const [nom, setNom] = useState("");
  const [motDePasse, setMotDePasse] = useState("");
  const [visible, setVisible] = useState(false);
  const [majuscules, setMajuscules] = useState(false);
  const [erreur, setErreur] = useState(null);
  const [envoi, setEnvoi] = useState(false);
  const champMotDePasse = useRef(null);

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
      // Le focus revient au champ a ressaisir, pas au debut du formulaire.
      champMotDePasse.current?.focus();
    } finally {
      setEnvoi(false);
    }
  }

  // Verrouillage des majuscules : cause frequente d'echec, invisible dans
  // un champ masque.
  function surTouche(evenement) {
    if (typeof evenement.getModifierState === "function") {
      setMajuscules(evenement.getModifierState("CapsLock"));
    }
  }

  return (
    <div className="ecran-connexion">
      <div className="connexion-theme">
        <InterrupteurTheme />
      </div>

      <main className="carte-connexion">
        <div className="connexion-entete">
          <img className="connexion-logo" src={logoAntic} alt="ANTIC" />
          <h1>SENTINEL</h1>
          <p>Surveillance de sources clandestines</p>
        </div>

        <form className="connexion-formulaire" onSubmit={soumettre} aria-busy={envoi || undefined}>
          {erreur && (
            <div className="banner banner-error" role="alert" id="erreur-connexion">
              <IconeAttention taille={18} />
              <div className="banner-corps">{erreur}</div>
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
              autoCapitalize="none"
              spellCheck={false}
              autoFocus
              required
            />
          </div>

          <div className="field">
            <label className="field-label" htmlFor="mdp">
              Mot de passe
            </label>
            <div className="champ-groupe">
              <input
                id="mdp"
                ref={champMotDePasse}
                className="input"
                type={visible ? "text" : "password"}
                value={motDePasse}
                onChange={(e) => setMotDePasse(e.target.value)}
                onKeyDown={surTouche}
                onKeyUp={surTouche}
                autoComplete="current-password"
                aria-invalid={erreur ? true : undefined}
                aria-describedby={[majuscules && "mdp-majuscules", erreur && "erreur-connexion"]
                  .filter(Boolean)
                  .join(" ") || undefined}
                required
              />
              <button
                type="button"
                className="champ-bouton"
                onClick={() => setVisible((v) => !v)}
                aria-pressed={visible}
                aria-label="Afficher le mot de passe"
                aria-controls="mdp"
              >
                {visible ? <IconeOeilBarre taille={18} /> : <IconeOeil taille={18} />}
              </button>
            </div>
            {majuscules && (
              <span className="field-aide connexion-majuscules" id="mdp-majuscules">
                <IconeAttention taille={14} /> Verrouillage des majuscules activé
              </span>
            )}
          </div>

          <button className="btn btn-primary btn-bloc" type="submit" disabled={envoi}>
            {envoi && <span className="spinner" aria-hidden="true" />}
            {envoi ? "Connexion…" : "Se connecter"}
          </button>
        </form>

        <p className="connexion-note">
          Accès réservé aux analystes habilités de l'ANTIC. Toute connexion est journalisée.
        </p>
      </main>
    </div>
  );
}
