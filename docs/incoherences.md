# Revue de code — incohérences relevées et corrections

Revue complète du dépôt (backend Python, interface React, migrations, diagrammes UML, README),
menée le 25/09/2026 sur le commit `6c6331f`. Chaque incohérence indique **où** elle se trouvait,
**ce qui n'allait pas**, sa **gravité** et le **commit** qui la corrige.

Gravité : **haute** = résultat faux (détection manquée, doublon, droit accordé à tort) ;
**moyenne** = chiffre ou message trompeur, coût inutile ; **basse** = texte ou code sans effet.

Toutes les corrections ont été vérifiées hors ligne (connecteurs factices, base de test migrée,
client de test Flask). **Aucune n'a été testée sur une vraie source** : à vérifier sur la VM Kali
après `git pull`, `alembic upgrade head` (aucune migration nouvelle) et **redémarrage du serveur
web et du scheduler**.

---

## 1. Comportements faux (corrigés)

### 1.1 Le sélecteur « .cm » ne trouvait aucun domaine — haute — `1e404de`

- **Où** : `app/matching/engine.py::_pattern_mot_entier`, `app/matching/exclusion.py::_cm_isole_dans_mot`.
- **Problème** : « .cm » fait 3 caractères, c'est donc un sélecteur « court » qui exige une frontière
  de mot **avant et après** lui. Or un suffixe de domaine est toujours collé à son nom :
  dans « camtel.cm », « .cm » est précédé d'un « l », la correspondance était refusée. Et si elle
  avait été acceptée, la règle « cm isolé dans un mot » l'aurait rejetée pour la même lettre.
  Même défaut, de l'autre côté, pour « +237 » et « 00237 » : un numéro continue par des chiffres
  (« +237699… »), que la frontière après le sélecteur refusait.
  Le code annonçait pourtant l'inverse (catégorie « Domaine internet » du seed, docstring de
  `cmdorganization_connector` : « un .cm correspond directement aux sélecteurs DOMAINE »).
- **Correction** : pas de frontière avant un sélecteur qui commence par un point, pas de frontière
  après un indicatif (chiffres, « + » en tête). La règle « cm dans un mot » est supprimée (les
  frontières du moteur couvrent déjà ce cas). « start-of-the-art », « file.cmd », « UY12 » restent
  écartés.
- **Effet à connaître** : un domaine en « .gov.cm » compte désormais deux sélecteurs (« .cm » et
  « .gov.cm »), comme « CNI Cameroun » compte aussi « CNI ». C'est le catalogue qui se chevauche.

### 1.2 Une victime toujours listée recréait une exposition tous les 30 jours — haute — `fe295e6`

- **Où** : `app/matching/deduplication.py::_trouver_exposition_existante`.
- **Problème** : les sources sans page de détail (payload, cmd_organization, orion_leaks,
  data_exposure_logs, blackwater) sont ré-analysées à chaque cycle. Le rapprochement ne cherchait
  l'incident que parmi les expositions **de moins de 30 jours** : au 31ᵉ jour, une victime encore
  listée créait une **seconde exposition** et une alerte « NOUVELLE », puis une autre 30 jours plus
  tard. Payload et cmd_organization ne datant pas leurs annonces, la fenêtre d'analyse ne les en
  protégeait pas. Une exposition classée « faux positif » réapparaissait ainsi.
- **Correction** : on cherche d'abord une exposition qui porte **déjà un signalement de la même
  source pour la même référence** (nom proche), sans limite de date : c'est la même annonce revue.
  La fenêtre de 30 jours ne sert plus qu'au rapprochement entre sources ou d'une nouvelle annonce.

### 1.3 Signalement identifié par la famille de source — moyenne — `fe295e6`

- **Où** : `deduplication._ajouter_reference`.
- **Problème** : un signalement existant était reconnu par sa référence **et son `type_source`**
  (« ransomware_site »), pas par sa source. Deux sites de rançongiciel publiant la même référence
  relative (« /posts/12 ») passaient pour un seul signalement. Contraire au commentaire du modèle
  (`SourceReference.source_id` existe précisément parce que `type_source` ne donne que la famille).
- **Correction** : comparaison sur `source_id` ; la famille ne sert qu'aux signalements antérieurs à
  cette colonne.

### 1.4 Compteur « en attente de page de détail » gonflé — moyenne — `9dc1597`

- **Où** : `app/pipeline.py::_traiter_une_entree`.
- **Problème** : toute annonce **déjà analysée** d'une source à pages de détail était comptée « en
  attente » à chaque cycle (everest, entièrement traité, affichait ses 46 entrées « en attente »).
  Et comme la fenêtre de dates était testée **après** ce compteur, une annonce que le listing date
  hors période — écartée sans lecture par la phase de détail — finissait « en attente » au lieu de
  « hors période » : la colonne *Hors période* de la page Collecte sous-comptait d'autant.
- **Correction** : la fenêtre est appliquée avant le test d'attente ; une annonce déjà analysée,
  sans relecture prévue, n'est plus comptée (clé `deja_traitee` posée depuis le registre).

### 1.5 Signature changée : page relue malgré la période… puis rejetée — moyenne — `9dc1597`

- **Où** : `BaseConnector._phase_detail` / `pipeline._traiter_une_entree`.
- **Problème** : le README et le connecteur prévoient qu'une annonce dont la signature de listing
  a **changé** est relue **même hors période** (le changement prouve un contenu neuf que la date
  peut ne pas refléter). Le pipeline la rejetait ensuite sur sa date : 30 s de requête pour rien,
  exception sans effet.
- **Correction** : le pipeline n'applique plus la fenêtre à ces relectures (clé `relecture`,
  calculée par `raison_relecture()`), ni à une exposition à compléter encore en attente.

### 1.6 Sonde de date en échec déguisée en « dates illisibles » — moyenne — `c5e210e`

- **Où** : `BaseConnector._arret_par_date`.
- **Problème** : quand la sonde de safepay (voir `doc.md`, § 5) échouait (Tor, page indisponible),
  l'arrêt était étiqueté `dates_illisibles`, avec l'avertissement « format de date modifié par le
  site ? ». Fausse piste : le format n'y était pour rien.
- **Correction** : motif distinct `sonde_echouee` (log et page Collecte). L'arrêt par prudence est
  conservé.

### 1.7 Un admin pouvait modifier le rôle d'un autre admin — haute — `1582a31`

- **Où** : `app/web/api/users.py::changer_role`.
- **Problème** : seul le rôle super_admin était protégé. Un admin pouvait rétrograder un autre admin
  (ou lui-même). README, en-tête du module et page Comptes posent la règle inverse : on n'agit
  jamais sur un compte de rang égal ou supérieur (sauf super_admin).
- **Correction** : `_rang_insuffisant()` (fondé sur `HIERARCHIE_ROLES`) protège le rôle comme
  l'activation. Vérifié : admin → admin 403, admin → user 200, super_admin → admin 200.

### 1.8 Rôle inconnu remplacé en silence par « user » — basse — `1582a31`

- **Où** : `users.creer_utilisateur`. Un rôle invalide devenait « user », juste au-dessus d'un
  commentaire qui refuse ce genre de surprise. **Correction** : réponse 400.

### 1.9 Règle de mot de passe affichée fausse — moyenne — `1582a31`

- **Où** : `frontend/src/pages/Comptes.jsx`.
- **Problème** : « Au moins 8 caractères… » et `minLength={8}`, sans chiffre, alors que
  `app/securite.py` exige **12 caractères et un chiffre** depuis l'audit de sécurité.
- **Correction** : texte et contrôle alignés sur le serveur.

### 1.10 Impossible de créer le premier administrateur — moyenne — `1582a31`

- **Où** : `app/create_user.py`, README (« Installation »).
- **Problème** : le script créait toujours un compte `user`, et seul un admin crée des comptes dans
  l'interface : une installation neuve n'avait aucun administrateur.
- **Correction** : option `--role` (`python3 -m app.create_user --role super_admin`).

### 1.11 L'export « complet » ne contenait pas le journal d'audit — haute — `ef33e65`

- **Où** : `app/web/compliance.py`, `app/reports/export.py`.
- **Problème** : `/compliance/export-complet` renvoyait exactement l'export JSON des expositions
  (déjà ouvert aux superviseurs). Or README, `app/audit.py` et l'API de conformité le présentent
  comme ce qui « fait foi » avant une purge — purge qui supprime **aussi** le journal d'audit.
  Rien ne permettait donc de conserver ce que la purge allait effacer.
- **Correction** : `exporter_conformite()` = expositions + journal d'audit + historique des rôles
  (toujours sans le texte conservé des annonces).

### 1.12 Réessais Tor hors délai FR-06 — moyenne — `9bf6ac3`

- **Où** : `app/tor/__init__.py::get_via_tor`.
- **Problème** : une boucle de 3 tentatives espacées de **5 s**, hors de tout délai de 30 s,
  neutralisée seulement parce que `BaseConnector` passait `max_retries=1`. Tout autre appelant,
  avec les valeurs par défaut, aurait martelé la source. Par ailleurs `requete()` réessayait une
  réponse trop volumineuse que Tor déclarait inutile à réessayer.
- **Correction** : `get_via_tor` fait une seule tentative ; `BaseConnector.requete` reste seul
  maître des réessais (délai complet, nouveau circuit) et ne réessaie plus une réponse > 10 Mo.

### 1.13 Rattrapage de textes sans signature — basse — `d0aef7f`

- **Où** : `app/maintenance/recuperer_textes.py::_completer`. L'annonce relue était marquée
  traitée **sans** sa signature de listing : au cycle suivant, everest la relisait (« amorçage »).
  **Correction** : signature enregistrée comme dans le pipeline.

### 1.14 Période de rapport non bornée au téléchargement — basse — `d0aef7f`

- **Où** : `app/web/reports.py::_mois_annee`. `annee=0` provoquait une erreur 500 sur
  `/reports/monthly/pdf`, alors que l'API répondait 400. **Correction** : `erreur_de_periode()`
  partagée.

### 1.15 Type de source inconnu rangé en « test_clairnet » — basse — `9dc1597`

- **Où** : `pipeline._get_or_create_source`. Un connecteur au `SOURCE_TYPE` inconnu était
  enregistré en silence sous le type de la source retirée (The Hacker News). **Correction** :
  erreur explicite.

---

## 2. Documentation et commentaires faux (corrigés — `c07846f`, `f64ec41`)

| Où | Ce qui était écrit | Réalité |
|---|---|---|
| `models.EntreeCollectee.signature_listing` | « NULL = jamais relue » | NULL = relue **une fois** (amorçage) |
| `app/journalisation.py` | bouton « Vider l'affichage », efface l'écran | bouton « Vider les logs », vide la table |
| `conservation.texte_complet`, `conserver_selecteurs` | entrée connue ré-analysée sur son titre | le titre seul ne produit plus d'exposition |
| `reconnaissance` (verdicts [A], [F], [E/F]) | « exposition née du titre seul », « analysée sur son titre » | idem : l'entrée attend sa page |
| `base_connector` (en-tête, `_phase_detail`) | détail « pour les entrées NOUVELLES uniquement » | aussi complétion, changement, amorçage |
| `base_connector._journaliser_synthese` | « table append-only sans purge » | file circulaire de 1 000 lignes |
| `engine._match_fuzzy` | courts « couverts par insensible_casse » | ce niveau est désactivé pour eux |
| `engine.match_text_against_catalogue` | tuples « pour les tests » | forme utilisée par la collecte |
| en-tête de `app/models` | « à ajuster… ambiguïté 3 du rapport de suivi » | décision prise, Alembic propriétaire du schéma |
| connecteurs cmd / everest | « réel #7 », « réel #8 » | #6 et #7 (README) |
| 6 connecteurs | « MISE À JOUR : utilise désormais app.tor » | vrai depuis toujours, bruit |
| `everest_connector` | page d'accueil « non encore confirmée » | confirmée sur la VM (46 catégories) |
| `orionleaks_connector` | « on enregistre son existence (booléen) » | rien n'était enregistré |
| `users.py` | règles « des blueprints / du formulaire Jinja » | ces fichiers n'existent plus |
| `seed_selecteurs` | « seed d'origine », « poids faible dans le moteur de scoring » | ni l'un ni l'autre n'existe |
| rapport mensuel, `seuil_du_niveau` | paliers en « sélecteurs » | paliers en **points** (poids) |
| message d'alerte de confirmation | hausse « suite à une nouvelle source » | aussi relecture de l'annonce |
| `use_case.puml` | cas « Valider un sélecteur proposé (NER) » | FR-14 non implémenté |
| `classes.puml` | exclusion sans portée ; journal « append-only » | 4 champs ajoutés ; file circulaire |
| `components.puml` | interface en HTTPS | HTTP local sur la VM |
| README | alertes email/SMS/WhatsApp présentées comme réelles | **simulées** (mocks) |
| README | `logs/pipeline.log` pour toute collecte | seulement la collecte manuelle |

---

## 3. Code inutile retiré (`f64ec41`)

- `texte_global`, `nb_entries`, `metadata` / `get_metadata()` : calculés à chaque page, jamais lus.
- `BaseConnector.priorite_detail()` : toujours 0, jamais surchargée.
- Champs extraits sans lecteur (taille, compte à rebours, vues, code pays, statut, volume, nombre
  de liens, site officiel, slug, « verrouillé »…). Vérifié : identifiants de crawl, textes analysés
  et signatures **identiques** avant/après — le registre n'est pas perturbé.
- Paramètres jamais passés : `battre_coeur(statut=)`, `declencher_alertes(niveau_minimum=)`,
  `_match_fuzzy(threshold=)`, `get_via_tor(timeout, headers, retry_delay)`, `fetch(**kwargs)`.
- `BaseSender.CANAL_NOM`, `_ContexteTexte.texte`, `_est_dans_liste_de_pays` (doublon jamais
  appelé), relations `HistoriqueRole.user_cible/modifie_par`, import `flask.request`.
- `seed_selecteurs` s'importait lui-même pour un `SEED_SELECTEURS` inexistant et configurait la
  journalisation à l'import ; `config_system` fermait une session deux fois (et jamais en cas
  d'erreur).
- En-têtes de section en double dans `app/models`, `export` de trois fonctions React utilisées
  localement.

---

## 4. Constatés, volontairement non modifiés

| Constat | Pourquoi rien n'a été changé |
|---|---|
| Trois migrations vides en double (`00ff39938e95`, `2796e558c196`, `e876c6c31d5d`) | Elles font partie de la chaîne Alembic de la base de la VM ; les retirer imposerait de réécrire l'historique pour un gain nul. |
| Catalogue : « Centre », « Est », « Nord », « Sud », « Ouest » sont des mots courants (faux positifs probables) ; « Edea » et « Bertoua » en double dans le seed | Décision métier : le catalogue s'administre depuis *Configuration*. Le seed n'ajoute que ce qui manque, il ne corrige pas une base existante. **À arbitrer par l'administrateur** (désactiver ou abaisser ces régions). |
| Les sondes de date de safepay ne comptent pas dans le budget de pages de détail | Voulu et borné (une par page de listing, ≤ 10) ; désormais documenté (`doc.md` § 5, en-tête de `base_connector`). |
| Le filtre « niveau minimum » des listes compare la criticité aux seuils **actuels**, alors que le niveau affiché est figé à la détection | Choix documenté dans `seuil_du_niveau` (l'ordre SQL de l'énumération est alphabétique). Seul un changement de seuils fait diverger les deux. |
| Alertes email / SMS / WhatsApp simulées, marquées « envoyées » en base | En attente des accès ANTIC ; désormais écrit dans le README. Ces statuts ne s'affichent nulle part dans l'interface. |
| `docs/Leaks-sites.md` : liste brute d'adresses .onion | Liste des sources candidates (objectif 20 connecteurs) : utile, conservée. |
