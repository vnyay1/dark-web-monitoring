# Sentinel — fonctionnement complet, de A à Z

Ce document explique **comment l'application fonctionne réellement**, du démarrage du planificateur
jusqu'à l'affichage d'une exposition, en expliquant les notions techniques au passage. Les noms de
fichiers et de fonctions sont donnés pour pouvoir retrouver chaque mécanisme dans le code. Les
valeurs citées sont celles **par défaut** ; celles qui sont réglables le sont dans *Configuration*.

**Sommaire**

1. [Ce que fait Sentinel, et ce qu'il ne fait jamais](#1-ce-que-fait-sentinel-et-ce-quil-ne-fait-jamais)
2. [Architecture générale](#2-architecture-générale)
3. [Le planificateur (scheduler)](#3-le-planificateur-scheduler)
4. [Le crawl expliqué](#4-le-crawl-expliqué)
5. [La sonde de date (`sonde_date`)](#5-la-sonde-de-date-sonde_date)
6. [L'arrêt d'une collecte](#6-larrêt-dune-collecte)
7. [La collecte parallèle et ses limites](#7-la-collecte-parallèle-et-ses-limites)
8. [De l'annonce à l'exposition : l'analyse](#8-de-lannonce-à-lexposition--lanalyse)
9. [Tor](#9-tor)
10. [Interface, API et rôles](#10-interface-api-et-rôles)
11. [Journaux, audit et conformité](#11-journaux-audit-et-conformité)
12. [Outils en ligne de commande](#12-outils-en-ligne-de-commande)
13. [Réglages](#13-réglages)
14. [Glossaire](#14-glossaire)

---

## 1. Ce que fait Sentinel, et ce qu'il ne fait jamais

Sentinel surveille des **sites de fuite** (sites de rançongiciels, annuaires de victimes) accessibles
par Tor, et signale quand une **entité camerounaise** (ministère, banque, opérateur, université,
entreprise…) y apparaît. Il enregistre l'**existence** de la fuite — qui, où, quand, avec quelle
gravité — **jamais les données volées elles-mêmes**.

Les contraintes non négociables du cahier des charges gouvernent tout le code :

| Contrainte | Traduction dans le code |
|---|---|
| **CN-03** : seules les métadonnées autorisées sont stockées | Une exposition = nom d'entité, catégories, sources, dates, criticité, statut. |
| **CN-04** : aucun nom de personne, email, mot de passe, hash, extrait | Aucun champ de la base ne reçoit de contenu de page, à une exception près (ci-dessous). Les liens vers les données divulguées ne sont jamais suivis ni conservés. |
| **CN-05** : l'analyse se fait en mémoire | Le HTML téléchargé est supprimé (`del raw`) dès qu'il a été lu ; rien n'est écrit sur disque. |
| **CN-09 / CN-10 / FR-06** : collecte passive, 30 s minimum entre deux requêtes à une même source | `BaseConnector._respect_rate_limit()`, plancher `DELAI_MINIMUM_ABSOLU = 30`. |

**Dérogation validée le 18/09/2026** : pour qu'un analyste puisse relire l'annonce qui a déclenché
une exposition, son **texte complet** est conservé sur le signalement (`SourceReference.texte_brut`),
**masqué** (emails, numéros, empreintes, mots de passe, URL), lisible uniquement par un superviseur
ou plus, via le bouton « Détails ». Jamais le HTML, jamais le texte d'une annonce sans
correspondance, jamais dans une liste, un export ou un rapport. Point d'audit unique :
`app/conservation.py`.

---

## 2. Architecture générale

Deux **processus** Python indépendants tournent sur la VM de collecte et ne communiquent **que par
la base de données** :

```
                 ┌────────────────────────── VM isolée ───────────────────────────┐
                 │                                                                 │
  Analyste ──HTTP──► Processus WEB (run.py)          Processus SCHEDULER             │
  (navigateur)   │    Flask : API JSON /api      (python3 -m app.scheduler)          │
                 │    + interface React           APScheduler : 1 cycle / jour     │
                 │          │                         │                              │
                 │          │  lit l'état,            │  collecte ──► Tor ──► sites  │
                 │          │  pose des demandes      │  analyse, enregistre         │
                 │          ▼                         ▼                              │
                 │        ┌───────────────── SQLite (schéma Alembic) ─────────────┐ │
                 │        │ expositions, signalements, registre du crawl,           │ │
                 │        │ état du scheduler, fil d'activité, journal d'audit...   │ │
                 │        └──────────────────────────────────────────────────────────┘ │
                 └─────────────────────────────────────────────────────────────────┘
```

- Le **serveur web** ne parle **jamais** à Tor ni aux sources. Quand un administrateur clique sur
  « Collecte immédiate » ou « Vérifier l'IP », il pose un **drapeau** en base ; le scheduler le lit
  toutes les 5 secondes et s'exécute.
- Le **scheduler** fait tout le travail de collecte et d'analyse.
- Le **schéma** de la base appartient à **Alembic** (`migrations/`). Au démarrage, chaque programme
  vérifie seulement que la base est à jour (`app/db.py::init_db`) et refuse de démarrer sinon.

Après un `git pull` : `alembic upgrade head`, puis **redémarrer** le serveur web **et** le scheduler
(un processus garde en mémoire le code chargé à son démarrage ; un bandeau prévient les
administrateurs quand un processus exécute une version plus ancienne que le code installé).

---

## 3. Le planificateur (scheduler)

Fichiers : `app/scheduler.py`, `app/supervision.py`.

**Une collecte par jour, à une heure tirée au hasard** dans la plage `collecte_heure_min` –
`collecte_heure_max` (UTC). Une heure fixe dessinerait, côté sources, un motif reconnaissable. À la
fin de chaque cycle, le scheduler tire l'heure du lendemain.

**Un seul scheduler à la fois.** Au démarrage, le processus réclame un **verrou** stocké dans la
ligne unique `EtatScheduler`, par **une seule requête UPDATE conditionnelle** (deux processus lancés
au même instant ne peuvent pas l'obtenir tous les deux). Le processus rafraîchit un **battement de
cœur** (*heartbeat*) toutes les 30 s ; un verrou sans battement depuis 90 s est considéré comme
abandonné (processus tué, VM coupée) et peut être repris.

**Tâches périodiques** du processus :

| Tâche | Fréquence | Rôle |
|---|---|---|
| `job_heartbeat` | 30 s | prouve que le processus est vivant |
| `job_verifier_demande` | 5 s | lance une collecte immédiate demandée depuis l'interface |
| `job_synchroniser_tor` | 5 s | publie l'IP de sortie Tor, sert « Vérifier maintenant » |
| `job_surveiller_echeance` | 60 s | filet de sécurité : aucune échéance ne reste passée sans collecte |
| collecte quotidienne | 1×/jour | le cycle lui-même, qui reprogramme le suivant |

**Échéance manquée** (VM en veille, processus bloqué) : trois mécanismes la détectent (événement
« missed » d'APScheduler au réveil, surveillance minute par minute, contrôle au démarrage). Elle est
signalée dans la console (`ECHEANCE_MANQUEE`) et une collecte de rattrapage est programmée le jour
même si la plage horaire le permet encore (au moins 10 min plus tard), sinon le lendemain.

Une seule collecte tourne à la fois, quelle que soit son origine (échéance, bouton, démarrage) :
un verrou interne (`_verrou_collecte`) fait ignorer la seconde.

---

## 4. Le crawl expliqué

### 4.1 Qu'est-ce qu'un crawl ?

**Crawler** (« ramper » en anglais), c'est parcourir automatiquement des pages web en suivant leurs
liens pour en extraire de l'information — ce que fait un moteur de recherche. Ici le crawl est
**très restreint** : chaque source n'est parcourue que sur les pages qu'un connecteur a explicitement
autorisées, lentement (30 s minimum entre deux pages), et jamais au-delà du site surveillé.

Un site de fuite présente deux sortes de pages :

- la **page de listing** (accueil, et ses pages 2, 3… : la *pagination*) : une carte par victime,
  avec un nom, parfois une date et une phrase ;
- la **page de détail** d'une annonce : le texte complet (description, secteur, pays, documents
  revendiqués…). C'est elle qui permet de reconnaître une entité camerounaise ; mais chaque page
  coûte au moins 30 s.

Chaque source a son **connecteur** (`app/connectors/*_connector.py`), une classe qui sait lire *ce*
site : `parse()` transforme une page de listing en liste d'**entrées** (une par annonce),
`parse_detail()` lit une page de détail, `url_page_suivante()` trouve le lien vers la page suivante,
`url_detail()` décide si le lien d'une annonce peut être visité (par défaut : **non**). Tout le reste
(délais, réessais, phases, statistiques, audit) est commun : `BaseConnector.collect()`.

| Source | Pagination | Pages de détail | Dates |
|---|---|---|---|
| payload | non | non | aucune |
| orion_leaks | oui | non (le lien mène aux données) | listing |
| data_exposure_logs | oui | non | listing (une carte sur deux, bornée) |
| blackwater | oui | non | listing |
| safepay | oui | oui | **uniquement sur la page de détail** (→ § 5) |
| cmd_organization | non | non (le lien mène au site de la victime) | aucune |
| everest | non | oui | listing et détail |

### 4.2 Les deux phases d'une collecte

`collect()` enchaîne :

1. **Phase de listing** (`_phase_listing`) : page 1, puis pages suivantes tant qu'aucun motif d'arrêt
   n'est atteint (→ § 6). Toutes les entrées rencontrées sont gardées.
2. **Phase de détail** (`_phase_detail`) : pour les entrées qui le méritent, et **dans la limite d'un
   budget**, la page de détail est lue et son texte ajouté à celui du listing.

Le texte de chaque entrée reste **en mémoire** ; le connecteur le rend au pipeline, qui l'analyse
(→ § 8).

### 4.3 Le registre : ne pas relire ce qui a déjà été lu

Relire chaque jour toutes les pages de détail de toutes les annonces coûterait des heures et
martèlerait les sources. Le **registre du crawl** (table `EntreeCollectee`, `app/crawl/registre.py`)
mémorise, par source, **quelles annonces ont déjà été analysées** — uniquement un identifiant
technique (chemin de la page d'annonce, ou empreinte `h:…` non navigable), **jamais** un nom de
victime ni un extrait : ce n'est pas un index de victimes.

| Statut | Signification |
|---|---|
| `A_TRAITER` | vue dans le listing, page de détail pas encore lue |
| `TRAITEE` | analysée (qu'elle ait produit une exposition ou non) |
| `SANS_DETAIL` | source sans page de détail : analysée sur son listing |
| `ECHEC` | page de détail en échec 3 fois de suite : abandonnée |

Le registre est **mis à jour après l'analyse** de chaque entrée : si le processus tombe entre la
lecture d'une page et son enregistrement, l'entrée est simplement relue au cycle suivant. Une entrée
qui n'a plus été vue depuis **90 jours** est oubliée.

### 4.4 Le budget et l'ordre de service

Le cycle dispose de **250 pages de détail**, réparties équitablement entre les sources puis
plafonnées par source (`MAX_DETAILS_PAR_RUN`) : en pratique **20 pour everest, 10 pour safepay**
(les autres sources n'ont pas de pages de détail). Chaque page coûtant ~50 s (délai + latence Tor),
ce budget borne la durée du cycle.

Les candidats au budget sont servis **par priorité** (`pipeline._priorite_detail`), puis dans l'ordre
du listing :

| Rang | Annonce |
|---|---|
| 3 | celle d'une exposition **à compléter** (texte ou sélecteurs manquants) |
| 2 | celle dont le **titre cite déjà un sélecteur** du catalogue — probablement camerounaise |
| 1 | une annonce déjà traitée dont le **listing a changé**, ou jamais « signée » (amorçage, § 4.5) |
| 0 | les autres |

Les annonces que le budget ne sert pas **restent `A_TRAITER`** et passent au cycle suivant : le crawl
est **reprenable**. Au premier cycle d'une source, il faut donc plusieurs jours pour tout lire, les
annonces prometteuses d'abord.

### 4.5 La signature de listing : relire une annonce qui a changé

Une annonce déjà `TRAITEE` n'est normalement plus relue. Mais sur everest, une catégorie peut
**gagner un post** après sa première lecture. Le connecteur calcule donc une **signature** de ce que
le listing annonce comme volume (`signature_listing()` : sha256 du nombre de posts et de la date,
**jamais** du nom ni d'un extrait). Au cycle suivant :

- signature **différente** → « changement » : la page est relue (rang 1), même hors période ;
- **aucune** signature enregistrée (annonce traitée avant ce mécanisme) → « amorçage » : la page est
  relue **une fois** pour établir la référence, puis plus jamais sans changement.

Les autres connecteurs ne publient pas de signature : pour eux, une annonce traitée n'est pas relue.

### 4.6 La fenêtre d'analyse

Seules les annonces publiées dans les **30 derniers jours** (`periode_collecte_jours`) sont
analysées. La fenêtre sert à trois endroits :

- **arrêt de la pagination** : une page entièrement plus ancienne arrête le parcours (§ 6) ;
- **phase de détail** : une annonce que le listing date déjà hors période ne coûte aucune page ;
- **pipeline** : une annonce hors période n'est pas analysée.

Deux exceptions (détail et pipeline) : une **exposition à compléter** et une **signature changée**.
Une annonce **sans date lisible** est toujours analysée (payload et cmd_organization ne datent rien).
Sur data_exposure_logs, dont le listing est trié du plus récent au plus ancien, une carte sans date
reçoit une **date plafond** : celle de la carte datée qui la précède ; elle sert à la fenêtre, jamais
de date de publication.

---

## 5. La sonde de date (`sonde_date`)

### Le problème

Pour arrêter la pagination au bon moment, il faut savoir **à partir de quelle page** les annonces
deviennent trop anciennes (§ 6, motif `hors_periode`). Les autres sources affichent une date sur
chaque carte du listing : il suffit de la lire. **safepay non** : son listing ne montre aucune date,
seule la **page de détail** d'une annonce la porte (`DATE_SUR_DETAIL = True`). Sans solution,
safepay serait parcouru jusqu'au plafond de pages à chaque cycle.

### La solution : sonder une annonce par page

Sur chaque page de listing, le connecteur visite **dès la phase de listing** la page de détail d'**une
seule** annonce — la **sonde** — et lit sa date (`_arret_par_date` → `_entree_a_sonder` →
`dater_par_sonde`) :

- **la dernière annonce de la page** : le listing est trié du plus récent au plus ancien, la dernière
  est donc la plus ancienne de la page. Si même elle est dans la période, toute la page l'est et la
  suivante mérite d'être lue ; si elle est hors période, les pages suivantes, plus anciennes encore,
  le sont aussi ;
- **une annonce NOUVELLE** (absente du registre) : sa page de détail aurait de toute façon été lue en
  phase de détail. La visite n'est **pas perdue** : l'entrée est enrichie immédiatement (texte, date)
  et la phase de détail ne la relit pas.

Si la page ne contient **aucune annonce nouvelle**, il n'y a rien à sonder : c'est l'arrêt sur
« pages déjà connues » qui bornera la suite.

### Ce que la sonde décide

| Résultat de la sonde | Conséquence |
|---|---|
| date **dans** la période | la pagination continue |
| date **avant** la période | arrêt `hors_periode` |
| page lue mais **aucune date** lisible | arrêt `dates_illisibles` (format changé par le site ?) |
| page de détail **en échec** (Tor, site) | arrêt `sonde_echouee` (prudence : la page n'est pas datée) |

### Exemple

Le 25/09, période de 30 jours (limite : 26/08). Page 1 de safepay : 12 annonces nouvelles ; la sonde
lit la 12ᵉ, datée du 20/09 → on continue. Page 2 : la sonde lit la dernière annonce nouvelle, datée
du 10/08 → arrêt `hors_periode`. Coût : 2 pages de listing + 2 sondes, et les 2 annonces sondées sont
déjà enrichies.

### Ce qu'il faut savoir

- Le compteur `sondes_date` des statistiques de collecte compte les sondes ; elles comptent aussi
  dans `details_ok` / `details_echec`.
- Les sondes **ne sont pas prises sur le budget** de pages de détail : au plus une par page de
  listing, donc au plus `pages_listing_max` (10) par cycle.
- Une sonde en échec compte comme un échec de détail pour son annonce (abandon après 3 cycles).
- `python3 -m app.connectors.reconnaissance --source safepay --phase pages --max 3` montre, page par
  page, la date lue par la sonde, sans rien écrire.

---

## 6. L'arrêt d'une collecte

« Arrêt » recouvre trois choses différentes.

### 6.1 L'arrêt de la pagination d'une source (motif `arret`)

Pour chaque source, la phase de listing s'arrête au **premier** motif rencontré. Le motif est
enregistré dans les statistiques (`stats["arret"]`), le journal d'audit et la colonne **Pages** de la
page *Collecte* (« 3 · hors période »).

Pour chaque page lue, les tests se font **dans cet ordre** (`BaseConnector._phase_listing`) :

| # | Test | Motif | Fin normale ? |
|---|---|---|---|
| 1 | la page n'a pas pu être téléchargée ou lue | page 1 : **échec de la source** (§ 6.2) ; page 2+ : `erreur_page` | non |
| 2 | la page ne contient aucune annonce | `page_vide` | oui |
| 3 | deux pages **de suite** sans aucune annonce nouvelle (`PAGES_GRACE = 1` page de tolérance) | `page_connue` | oui |
| 4 | la source n'est pas paginée | `page_unique` (non affiché) | oui |
| 5 | toutes les dates lisibles de la page sont avant la période | `hors_periode` | oui |
| 5 | aucune date lisible sur la page | `dates_illisibles` | garde-fou |
| 5 | la sonde de date a échoué (safepay, § 5) | `sonde_echouee` | garde-fou |
| 6 | il n'y a pas de lien vers une page suivante | `fin_pagination` | oui |
| 7 | le plafond de pages est atteint (le plus petit de `MAX_PAGES_LISTING` = 30 et du réglage `pages_listing_max` = 10) | `profondeur_max` | oui |

Pourquoi ces motifs :

- **`page_connue`** : chaque jour, seules les premières pages ont du neuf. Dès que deux pages de
  suite ne contiennent que des annonces déjà connues, les suivantes (plus anciennes) le sont aussi.
  La page de tolérance absorbe une annonce **épinglée** ou un réordonnancement.
- **`hors_periode`** : inutile de demander des pages plus anciennes que la période analysée.
- **`dates_illisibles`** / **`sonde_echouee`** : si l'on ne peut pas dater la page, on s'arrête par
  prudence plutôt que de parcourir la source jusqu'au plafond à chaque cycle. `dates_illisibles`
  signale souvent un **changement de format** du site : à vérifier avec
  `python3 -m app.connectors.reconnaissance --source <X> --phase dates`.
- Chaque lien « page suivante » est vérifié (`_page_suivante_validee`) : même domaine, même chemin,
  numéro de page = courant + 1. Un lien douteux termine la pagination (`fin_pagination`).

**Exemple (blackwater)**. Premier cycle : pages 1, 2, 3 lues ; toutes les dates de la page 3 sont
avant la limite → `hors_periode`. Le lendemain : la page 1 contient une annonce nouvelle, la page 2
aucune (1 page sans nouveauté, dans la tolérance) ; ses dates sont encore dans la période → page 3,
toujours rien de nouveau (2 pages de suite) → `page_connue`.

### 6.2 L'échec d'une source

Une source est **en échec** si et seulement si sa **page 1** n'a pas pu être obtenue (3 tentatives,
chacune après le délai complet et sur un nouveau circuit Tor) ou lue. Conséquences : ligne « Échec »
dans le résultat du cycle, compteur d'erreurs de la source incrémenté, ligne `ECHEC` au journal
d'audit, une ligne neutre dans la console. **Les autres sources continuent.** Une source injoignable
depuis plus de 48 h apparaît « indisponible » au tableau de bord.

Une page 2+ ou une page de détail en erreur n'est qu'une **dégradation** : comptée, mais la source
reste « réussie ». Une page de détail est tentée **une seule fois** par cycle ; elle est retentée au
cycle suivant, et abandonnée après 3 échecs (`ECHEC`). L'annonce est alors analysée sur son seul
titre, pour ne jamais manquer une entité camerounaise derrière une page cassée.

### 6.3 L'arrêt du planificateur

- **Bouton « Arrêter »** (page *Collecte*, administrateur) : le serveur web termine le processus
  (signal SIGTERM sous Linux, `taskkill` sous Windows) et **libère le verrou** quoi qu'il arrive.
  Si une collecte était en cours, son cycle est clos (sa durée se fige).
- **Ctrl+C** dans le terminal : même arrêt propre.
- **Processus tué brutalement** (kill -9, coupure de la VM) : le verrou expire seul après 90 s sans
  battement ; la durée du cycle est bornée par le dernier battement connu.

Que devient une collecte **interrompue** ? L'analyse enregistre **chaque entrée dès qu'elle est
traitée** (un commit par entrée) : tout ce qui a été analysé est conservé. Les annonces non encore
analysées ne sont pas marquées dans le registre ; elles seront reprises au cycle suivant. Aucune
donnée n'est corrompue, au pire un peu de travail réseau est refait.

Un cycle qui se termine par une **erreur inattendue** est clos proprement (`interrompre_collecte`) et
le scheduler continue de tourner : l'erreur est dans `logs/scheduler.log`.

---

## 7. La collecte parallèle et ses limites

### 7.1 Comment ça marche

Une source passe l'essentiel de son temps à **attendre** : 30 à 45 s entre deux requêtes (FR-06),
plus 5 à 25 s de latence Tor. Plutôt que de traiter les sept sources l'une après l'autre, le pipeline
les collecte **en parallèle** (`pipeline.executer_tous_les_connecteurs`) :

- un **pool de fils d'exécution** (`ThreadPoolExecutor`) de `sources_en_parallele` fils (4 par
  défaut) ; chaque fil prend une source, dans l'ordre du registre des connecteurs, puis la suivante
  libre ;
- chaque fil a **sa propre session** de base de données (une session ne se partage pas entre fils) ;
- **seule la phase réseau** (`connector.collect()`) se chevauche. Tout ce qui lit puis écrit la base
  — préparation, analyse, enregistrement, journal d'audit — passe sous un **verrou unique**
  (`app.db.verrou_base`), une source à la fois. Deux raisons : la déduplication (chercher une
  exposition puis l'insérer n'est pas atomique : deux sources publiant la même victime au même
  instant créeraient deux expositions) et SQLite, qui n'admet qu'un écrivain à la fois ;
- le **délai FR-06 reste compté par source** (`_fin_derniere_requete_par_source`, clé = nom de la
  source) : chaque source continue de ne recevoir qu'une requête toutes les 30 à 45 s, quel que soit
  le nombre de fils. Une source n'est jamais traitée par deux fils ;
- le **budget** de pages de détail est réparti entre sources **avant** le lancement ;
- les résultats sont rendus dans l'ordre du registre, quel que soit l'ordre d'arrivée ;
- tous les fils passent par le **même client Tor** ; le renouvellement de circuit est cadencé
  globalement (§ 9), pas par fil.

### 7.2 Y a-t-il une limite selon le PC ou le débit réseau ?

**Limite imposée par le code** : `sources_en_parallele` est borné entre 1 et **10** (réglage), et de
toute façon au **nombre de sources** : avec 7 connecteurs, aller au-delà de 7 ne change rien.

**Ce qui ne limite pas en pratique :**

| Ressource | Besoin réel | Pourquoi ce n'est pas une limite |
|---|---|---|
| **Processeur** | lecture HTML : quelques ms par page ; comparaison d'une annonce au catalogue (~380 sélecteurs) : ~0,2 s pour 45 000 caractères | L'analyse est faite une source à la fois, sous verrou : ajouter des fils n'ajoute pas de calcul simultané. Les fils passent leur temps à dormir. |
| **Mémoire** | quelques Mo par source (textes des annonces du cycle ; réponse HTTP plafonnée à 10 Mo) | Quelques dizaines de Mo au pire pour 7 sources. |
| **Débit réseau** | ~1 requête toutes les 30-50 s par source, pages de quelques dizaines de Ko : **quelques Ko/s** pour 7 sources | Un circuit Tor offre couramment plusieurs centaines de Ko/s. Un réseau lent allonge la latence (donc le cycle), sans provoquer d'échec tant que le site répond dans le délai d'attente (30 s sans données reçues). |

**Ce qui limite réellement :**

1. **Le délai FR-06** : une source ne peut pas aller plus vite qu'une requête toutes les 30 à 45 s.
   La durée d'un cycle est donc celle de la **source la plus longue**, pas la somme.
2. **Le nombre de sources** : 7 aujourd'hui (20 visées).
3. **L'écriture en base** : SQLite n'a qu'un écrivain ; les analyses passent une par une. Avec des
   dizaines de sources et beaucoup d'annonces, c'est ce verrou qui deviendrait le goulot, bien avant
   le processeur.
4. **Le client Tor unique** : toutes les requêtes simultanées sortent par le même Tor. Quelques
   flux en parallèle ne lui posent aucun problème ; des dizaines ralentiraient l'établissement des
   circuits vers les services `.onion`.
5. **La discrétion** (CN-09) : chaque source ne voit jamais plus d'une requête toutes les 30 s, mais
   un même client Tor qui interroge beaucoup de sites à la fois reste un profil de trafic plus
   visible.

### 7.3 Ordre de grandeur, et réglage conseillé

Durées **maximales** d'une source (≈ 50 s par requête, plafond de 10 pages) :

| Source | Requêtes au plus | Durée au plus |
|---|---|---|
| payload, cmd_organization | 1 page | ~1 min |
| orion_leaks, data_exposure_logs, blackwater | 10 pages | ~8 min |
| everest | 1 page + 20 détails | ~17 min |
| safepay | 10 pages + 10 sondes + 10 détails | ~25 min |

- **1 fil** (séquentiel) : la somme, ~70 min au pire.
- **4 fils** (défaut) : safepay démarre dès que payload a fini (~1 min) et everest dès qu'une source
  paginée se libère (~8 min) : le cycle dure **~26 min**.
- **7 fils** : ~25 min, la durée de safepay.

Au-delà de **4**, le gain est donc négligeable avec les sources actuelles : **4 reste le bon
réglage** ; **1** sert au diagnostic (journaux non entremêlés). Il faudra réévaluer (et penser à une
base plus capable que SQLite) quand le nombre de connecteurs approchera de 20. Dans les journaux, le
nom du fil (`collecte_0`, `collecte_1`…) permet de suivre une source.

---

## 8. De l'annonce à l'exposition : l'analyse

Fichier chef d'orchestre : `app/pipeline.py`. Pour **chaque entrée** rendue par le connecteur
(`_traiter_une_entree`) :

1. **Normalisation** (`_normaliser_entry`) : chaque site nomme ses champs à sa façon ; la date
   (« Aug 13, 2026 », « 2d », « Sep 1 »…) est convertie par `app/connectors/dates.py` ; une date
   illisible donne « pas de date », jamais une date inventée.
2. **Complétion** : si l'annonce est celle d'une exposition à qui il manque son texte ou ses
   sélecteurs, et qu'elle vient d'être lue en entier, elle complète son propre signalement.
3. **Fenêtre d'analyse** (§ 4.6).
4. **Le listing seul ne crée jamais d'exposition** : une annonce qui a une page de détail attend sa
   lecture. Sinon le titre créait une exposition et une alerte, puis la page de détail une seconde
   alerte pour le même incident. Exception : page de détail définitivement perdue (3 échecs).
5. **Correspondance** (`app/matching/engine.py`) avec le **catalogue de sélecteurs** (noms
   d'entités et mots-clés camerounais, chacun dans une catégorie) en trois niveaux :
   **exact**, **insensible à la casse**, **approché** (RapidFuzz, ≥ 85 % de ressemblance, pour les
   fautes de frappe ; limité aux 20 000 premiers caractères, les deux autres niveaux lisent tout).
   Les sélecteurs de 6 caractères ou moins (« ART », « MINFI ») ne sont trouvés qu'en **majuscules
   exactes** et en **mot isolé** — sauf un suffixe de domaine (« .cm », collé à son nom) et un
   indicatif (« +237 », suivi du numéro). Une correspondance approchée dont le mot trouvé est
   lui-même un sélecteur est écartée (« Cameroon » n'est pas une faute de « Cameroun »).
6. **Faux positifs** (`app/matching/exclusion.py`) : un nom de lieu noyé dans une énumération de
   pays (« USA, France, Cameroun, Nigeria ») est écarté ; puis la **liste d'exclusion** tenue par
   les analystes : des expressions régulières sur le **texte** de l'annonce ou sur le **nom
   d'entité** (une société étrangère homonyme), pour toutes les sources ou une seule. Une règle
   n'est jamais rétroactive.
7. **Criticité** (`app/matching/criticite.py`) : le **score** d'une annonce est la somme des
   **poids** des sélecteurs **distincts** trouvés (poids 1, jusqu'à 5 pour un sélecteur
   prioritaire). Paliers : Moyenne ≥ 2, Élevée ≥ 3, Critique ≥ 4 (réglables). Une annonce sous
   `criticite_minimum_enregistrement` (1) n'est pas enregistrée.
8. **Catégories** : celles des sélecteurs trouvés (une annonce peut en porter plusieurs).
9. **Déduplication** (`app/matching/deduplication.py`) : la même victime ne fait qu'**une**
   exposition, avec un **signalement par source**. Une exposition existante est retrouvée d'abord
   par le **même signalement** (même source, même référence, nom proche — sans limite de date :
   c'est la même annonce revue), sinon par un **nom proche** (≥ 90 %) détecté depuis moins de
   30 jours. Sur une exposition connue, la criticité et les catégories ne font que **monter**.
10. **Conservation** (dérogation, § 1) : texte complet masqué et sélecteurs trouvés, sur le
    signalement ; remplacés seulement par plus complet.
11. **Alertes** (`app/alerting/`) : une exposition **nouvelle**, ou dont la criticité monte d'au
    moins `hausse_criticite_confirmation`, déclenche des alertes si son niveau atteint
    `niveau_alerte_minimum` (Moyenne) :

    | Niveau | Canaux | Si catégorie prioritaire (ou domaine .gov.cm) |
    |---|---|---|
    | Moyenne | interface, email | — |
    | Élevée | interface, email | + SMS |
    | Critique | interface, email, SMS | + WhatsApp |

    **Email, SMS et WhatsApp sont simulés** (`senders.py` : journalisés, rien ne part) en attendant
    les accès de l'ANTIC ; seul le canal interface est réel.
12. **Registre** : l'entrée est marquée traitée (avec sa signature si sa page vient d'être lue).

Une exposition nouvelle apparaît aussitôt dans le fil d'activité de la page *Collecte*
(`NOUVELLE_EXPOSITION`). En fin de source, une ligne `FIN_SOURCE` résume : entrées analysées,
expositions, complétions, hors période, en attente de page de détail.

---

## 9. Tor

Fichier : `app/tor/__init__.py`. Toutes les requêtes vers les sources passent par
`BaseConnector.requete()` puis `get_via_tor()`, via le proxy SOCKS de Tor.

- **Une tentative par appel** ; les réessais (3 pour une page de listing, 1 pour une page de détail)
  sont faits par `requete()`, **chacun après le délai complet**, sur un circuit renouvelé.
- **Renouvellement proactif** du circuit (nouvelle IP de sortie) à intervalle aléatoire de 10 à
  120 s, et **réactif** entre deux tentatives ; jamais deux renouvellements à moins de 10 s.
- Chaque réponse est **plafonnée à 10 Mo** : un site malveillant ne peut pas saturer la mémoire.
- L'IP de sortie est vérifiée auprès de check.torproject.org après chaque renouvellement et publiée
  dans la page *Collecte* (le serveur web, lui, ne parle jamais à Tor).
- Les journaux ne contiennent que le **chemin** des pages, jamais l'adresse `.onion` complète.

---

## 10. Interface, API et rôles

Le serveur Flask expose une **API JSON** (`app/web/api/`) consommée par une **application React**
(`frontend/`, compilée dans `frontend/dist`, versionnée : la VM n'a pas besoin de Node). Toute
requête qui modifie quelque chose doit porter l'en-tête `X-Requested-With` (protection CSRF). Les
rapports et exports sont de simples téléchargements.

| Page | Contenu |
|---|---|
| Tableau de bord | chiffres clés, répartitions, état des sources, dernières expositions |
| Expositions | liste filtrable ; détail : sélecteurs trouvés, chronologie, signalements, texte (« Détails ») |
| Archives | expositions « faux positif » ou « clôturée » (simple filtre, rien n'est déplacé) |
| Alertes | alertes du canal interface, à marquer lues |
| Collecte | état du planificateur, pilotage, IP Tor, résultat du dernier cycle, fil d'activité |
| Rapports | synthèse mensuelle, PDF, exports JSON / CSV |
| Configuration | réglages, catégories, catalogue de sélecteurs, liste d'exclusion |
| Comptes, Historique des rôles, Audit, Conformité | administration |

Quatre rôles hiérarchiques : **user** (consultation) < **supervisor** (+ statut des expositions,
alertes lues, texte des annonces, rapports et exports, lecture de la liste d'exclusion) < **admin**
(+ création de comptes jusqu'au rang admin, gestion des comptes user et supervisor, catalogue,
liste d'exclusion, pilotage de la collecte, archives) <
**super_admin** (+ comptes admin, réglages système, journal d'audit, conformité, historique des
rôles). Un compte n'agit jamais sur un compte de rang égal ou supérieur au sien (sauf super_admin)
et ne peut pas se désactiver lui-même. Les mots de passe font au moins 12 caractères (majuscule,
minuscule, chiffre, caractère spécial) ; 5 échecs de connexion bloquent le couple identifiant/IP
15 minutes ; une session dure 8 heures.

---

## 11. Journaux, audit et conformité

Trois journaux distincts :

| Journal | Où | Contenu | Vidé par |
|---|---|---|---|
| Fil d'activité | table `EvenementCollecte` | avancement des cycles, nouvelles expositions, circuits Tor, échéances manquées | rétention 7 jours, bouton « Vider les logs » |
| Journal d'audit (FR-17) | table `journal_audit` | synthèse de chaque collecte par source, erreurs agrégées, connexions, purges | file circulaire de 1 000 lignes, purge de conformité |
| Journaux serveur | `logs/*.log` | tout ce que les processus écrivent | rotation 5 Mo × 5 |

Les erreurs de collecte ne sont pas reprises dans le fil d'activité (elles sont au journal
d'audit). **Conformité** (super_admin) : l'**export complet** (expositions, journal d'audit,
historique des rôles) est à télécharger **avant** une **purge**, qui supprime définitivement les
expositions antérieures à une date — avec leurs signalements, alertes et textes — et le journal
d'audit de la même période.

---

## 12. Outils en ligne de commande

| Commande | Usage |
|---|---|
| `python3 run.py` | serveur web (http://127.0.0.1:5000) |
| `python3 -m app.scheduler [--sans-collecte-initiale]` | planificateur (ou bouton « Démarrer ») |
| `python3 -m app.pipeline [--source X] [--paralleles N]` | collecte manuelle (scheduler arrêté) |
| `python3 -m app.create_user [--role super_admin]` | créer un compte |
| `python3 -m app.matching.seed_selecteurs` | catalogue initial |
| `python3 -m app.connectors.reconnaissance --source X --phase …` | structure d'une source, dates, pagination, diagnostic d'une entrée — sans rien afficher du contenu ni rien écrire |
| `python3 -m app.crawl.registre --source X --identifiant /chemin` | remettre une annonce en file |
| `python3 -m app.maintenance.recuperer_textes [--confirmer]` | récupérer le texte des annonces « Non conservé » |
| `python3 -m app.maintenance.recategoriser [--confirmer]` | catégories des expositions anciennes |
| `python3 -m app.maintenance.retirer_source --lister` | retirer une source et ses données |
| `alembic upgrade head` | mettre la base à jour, avant tout le reste |

Les outils de maintenance **simulent** par défaut ; seul `--confirmer` écrit.

---

## 13. Réglages

| Réglage | Défaut | Effet |
|---|---|---|
| `seuil_criticite_moyenne` / `_elevee` / `_critique` | 2 / 3 / 4 | paliers de criticité (points) |
| `criticite_minimum_enregistrement` | 1 | score minimal pour enregistrer une exposition |
| `niveau_alerte_minimum` | moyenne | niveau minimal d'alerte |
| `hausse_criticite_confirmation` | 1 | hausse déclenchant une alerte de confirmation |
| `periode_collecte_jours` | 30 | fenêtre d'analyse |
| `pages_listing_max` | 10 | plafond de pages de listing par source et par cycle |
| `sources_en_parallele` | 4 | sources collectées en même temps (1 à 10) |
| `collecte_heure_min` / `_max` | 0 / 23 | plage horaire (UTC) de la collecte quotidienne |

Constantes du code : 30 s minimum entre deux requêtes + 0 à 15 s aléatoires ; 250 pages de détail
par cycle (20 everest, 10 safepay) ; 3 échecs avant abandon d'une page de détail ; rétention du
registre 90 jours ; déduplication 90 % de ressemblance, 30 jours entre sources.

---

## 14. Glossaire

- **Annonce / entrée** : une carte de victime sur un site de fuite ; une entrée = une exposition
  potentielle.
- **Amorçage** : première relecture d'une annonce déjà traitée, pour enregistrer sa signature.
- **Budget** : nombre maximal de pages de détail lues par cycle.
- **Connecteur** : classe qui sait lire une source donnée.
- **Crawl** : parcours automatisé de pages web ; ici borné, lent et incrémental.
- **Criticité** : score d'une annonce (sélecteurs distincts, pondérés) et son palier.
- **Cycle** : une collecte complète de toutes les sources.
- **Date plafond** : borne de date d'une annonce non datée sur un listing trié.
- **Exposition** : l'indicateur enregistré — une entité camerounaise vue dans une fuite.
- **Fenêtre d'analyse** : période (30 jours) des annonces analysées.
- **Heartbeat** : signal de vie du scheduler, qui entretient son verrou.
- **Listing / page de détail** : page de liste des annonces / page d'une annonce.
- **Registre** : table `EntreeCollectee`, mémoire des annonces déjà analysées.
- **Sélecteur** : terme du catalogue recherché dans les annonces (nom d'entité, mot-clé).
- **Signalement** : lien entre une exposition et une source où elle a été vue.
- **Signature de listing** : empreinte du volume annoncé, pour détecter une annonce enrichie.
- **Sonde (`sonde_date`)** : lecture anticipée d'une page de détail pour dater une page de listing.
