/**
 * Session utilisateur et outils transverses.
 *
 * La session vit dans un cookie HttpOnly : le JavaScript ne peut donc pas
 * la lire. Au demarrage, l'application interroge /auth/moi pour savoir si
 * un cookie valide existe encore - c'est la seule facon de restaurer une
 * session apres un rechargement de page.
 */

import {
  createContext,
  useCallback,
  useContext,
  useEffect,
  useMemo,
  useRef,
  useState,
} from "react";

import { api, ErreurApi } from "./client";

const ContexteSession = createContext(null);

/** Hierarchie des roles, identique a app/web/permissions.py. */
const RANG_ROLES = {
  user: 0,
  supervisor: 1,
  admin: 2,
  super_admin: 3,
};

export function FournisseurSession({ children }) {
  const [utilisateur, setUtilisateur] = useState(null);
  const [chargement, setChargement] = useState(true);

  useEffect(() => {
    let annule = false;

    api
      .moi()
      .then((donnees) => {
        if (!annule) setUtilisateur(donnees);
      })
      .catch(() => {
        // Un 401 est le cas nominal quand personne n'est connecte.
        if (!annule) setUtilisateur(null);
      })
      .finally(() => {
        if (!annule) setChargement(false);
      });

    return () => {
      annule = true;
    };
  }, []);

  const connexion = useCallback(async (nom, motDePasse) => {
    const reponse = await api.connexion(nom, motDePasse);
    setUtilisateur(reponse.utilisateur);
    return reponse.utilisateur;
  }, []);

  const deconnexion = useCallback(async () => {
    try {
      await api.deconnexion();
    } finally {
      // Meme si l'appel echoue (session deja expiree cote serveur), on
      // rend la main a l'ecran de connexion.
      setUtilisateur(null);
    }
  }, []);

  const valeur = useMemo(
    () => ({
      utilisateur,
      chargement,
      connexion,
      deconnexion,
      /** Vrai si l'utilisateur possede au moins ce role. */
      aRole: (minimum) =>
        (RANG_ROLES[utilisateur?.role] ?? -1) >= (RANG_ROLES[minimum] ?? 99),
      signalerDeconnexion: () => setUtilisateur(null),
    }),
    [utilisateur, chargement, connexion, deconnexion],
  );

  return (
    <ContexteSession.Provider value={valeur}>
      {children}
    </ContexteSession.Provider>
  );
}

export function useSession() {
  const contexte = useContext(ContexteSession);
  if (!contexte) {
    throw new Error("useSession doit etre utilise dans un FournisseurSession.");
  }
  return contexte;
}

/**
 * Charge des donnees depuis l'API en gerant les etats : premier chargement,
 * rechargement, erreur, donnees. Une expiration de session (401) renvoie
 * l'utilisateur a l'ecran de connexion plutot que d'afficher une erreur
 * incomprehensible.
 *
 * RECHARGEMENT - les donnees deja affichees sont CONSERVEES pendant qu'on
 * les actualise : `chargement` ne vaut true qu'au premier chargement, et
 * `rechargement` signale une actualisation en arriere-plan. Remplacer toute
 * la page par un indicateur a chaque action faisait perdre a l'utilisateur
 * sa position de defilement et son focus.
 */
export function useChargement(fonction, dependances = []) {
  const { signalerDeconnexion } = useSession();
  const [donnees, setDonnees] = useState(null);
  const [erreur, setErreur] = useState(null);
  const [chargement, setChargement] = useState(true);
  const [rechargement, setRechargement] = useState(false);

  // Conserve la fonction courante sans la mettre dans les dependances :
  // une fonction fleche redefinie a chaque rendu relancerait l'effet en
  // boucle.
  const fonctionRef = useRef(fonction);
  fonctionRef.current = fonction;
  const dejaCharge = useRef(false);

  const [compteur, setCompteur] = useState(0);
  const recharger = useCallback(() => setCompteur((n) => n + 1), []);

  useEffect(() => {
    let annule = false;
    if (dejaCharge.current) {
      setRechargement(true);
    } else {
      setChargement(true);
    }

    fonctionRef
      .current()
      .then((resultat) => {
        if (annule) return;
        setDonnees(resultat);
        setErreur(null);
        dejaCharge.current = true;
      })
      .catch((e) => {
        if (annule) return;
        if (e instanceof ErreurApi && e.statut === 401) {
          signalerDeconnexion();
          return;
        }
        setErreur(e.message);
      })
      .finally(() => {
        if (annule) return;
        setChargement(false);
        setRechargement(false);
      });

    return () => {
      annule = true;
    };
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [compteur, ...dependances]);

  return { donnees, erreur, chargement, rechargement, recharger, setDonnees };
}

/** Duree d'affichage d'un message de succes. Les erreurs restent affichees. */
const DUREE_MESSAGE_MS = 6000;

/**
 * File de messages transitoires (succes / erreur).
 *
 * WCAG 2.2.1 - un message de SUCCES disparait seul, mais son minuteur se
 * suspend au survol ou au focus ; un message d'ERREUR reste jusqu'a ce que
 * l'utilisateur le ferme : il doit avoir le temps de le lire.
 */
export function useMessages() {
  const [messages, setMessages] = useState([]);
  const minuteurs = useRef(new Map());

  const retirer = useCallback((id) => {
    clearTimeout(minuteurs.current.get(id));
    minuteurs.current.delete(id);
    setMessages((liste) => liste.filter((m) => m.id !== id));
  }, []);

  const armer = useCallback(
    (id) => {
      clearTimeout(minuteurs.current.get(id));
      minuteurs.current.set(id, setTimeout(() => retirer(id), DUREE_MESSAGE_MS));
    },
    [retirer],
  );

  useEffect(() => {
    const actifs = minuteurs.current;
    return () => actifs.forEach((minuteur) => clearTimeout(minuteur));
  }, []);

  const ajouter = useCallback(
    (texte, type = "success") => {
      const id = Date.now() + Math.random();
      const persistant = type === "error";
      setMessages((liste) => [
        ...liste,
        {
          id,
          texte,
          type,
          fermer: () => retirer(id),
          suspendre: persistant ? undefined : () => clearTimeout(minuteurs.current.get(id)),
          reprendre: persistant ? undefined : () => armer(id),
        },
      ]);
      if (!persistant) armer(id);
    },
    [armer, retirer],
  );

  return { messages, ajouter, retirer };
}
