"""
FR-20/FR-21 - Expositions : liste filtrable, detail, changement de statut.

ARCHIVAGE - une exposition qualifiee "faux positif" ou "cloturee" quitte la
liste de travail pour la page Archives (admin et super_admin). C'est un
simple FILTRE DE REQUETE, pas un deplacement de donnees : rien n'est
duplique, aucune relation existante n'est touchee (SourceReference, Alerte),
et remettre l'exposition dans un statut actif suffit a la faire reapparaitre
dans Expositions - il n'y a pas d'etat d'archivage a maintenir en coherence
avec le statut.

Le filtre s'arrete a CES DEUX ROUTES. Le tableau de bord, le rapport
mensuel, les exports et l'export de conformite continuent de voir toutes les
expositions : les statistiques et la tracabilite reglementaire doivent porter
sur l'historique complet, pas sur ce que l'analyste a range.
"""

from datetime import timedelta

from flask import jsonify, request
from flask_login import login_required

from app.config_system import get_config_int
from app.conservation import lire_selecteurs
from app.db import get_session
from app.models import (
    Categorie, Exposition, NiveauCriticite, RoleUtilisateur,
    SourceReference, StatutExposition, utc_now,
)
from app.web.permissions import role_requis


# Nombre maximum d'expositions renvoyees en une fois.
LIMITE_PAR_PAGE = 200

# Statuts terminaux : l'analyste a tranche, l'exposition n'a plus a encombrer
# la liste de travail. Cf. la note ARCHIVAGE en tete de module.
STATUTS_ARCHIVES = (StatutExposition.FALSE_POSITIVE, StatutExposition.CLOSED)


def seuil_du_niveau(niveau: NiveauCriticite) -> int:
    """
    Nombre minimum de selecteurs correspondant a un palier.

    On filtre sur `criticite` (l'entier) et non sur `niveau_criticite` :
    NiveauCriticite est une enumeration de chaines, dont l'ordre SQL serait
    alphabetique ("critique" < "elevee" < "faible") et sans rapport avec la
    gravite reelle.
    """
    if niveau == NiveauCriticite.CRITIQUE:
        return get_config_int("seuil_criticite_critique")
    if niveau == NiveauCriticite.ELEVEE:
        return get_config_int("seuil_criticite_elevee")
    if niveau == NiveauCriticite.MOYENNE:
        return get_config_int("seuil_criticite_moyenne")
    return 0


def _sources_de(exposition) -> list:
    """Signalements de l'exposition, un par source ou elle a ete vue."""
    return [
        {
            "id": sr.id,
            "nom_source": sr.source.nom if sr.source else None,
            "type_source": sr.type_source.value,
            "reference_source": sr.reference_source,
            "date_publication": (
                sr.date_publication.isoformat() if sr.date_publication else None
            ),
            "date_signalement": (
                sr.date_signalement.isoformat() if sr.date_signalement else None
            ),
            # Le texte lui-meme n'est JAMAIS ici : endpoint dedie, reserve aux
            # superviseurs (derogation CN-04/CN-05, cf. app.conservation).
            "texte_disponible": sr.date_texte_brut is not None,
        }
        for sr in exposition.sources
    ]


def _selecteurs_de(exposition) -> dict:
    """
    Selecteurs du catalogue trouves dans les annonces de l'exposition,
    reunis sur tous ses signalements : un selecteur vu sur deux sources
    n'apparait qu'une fois, avec ses sources. Ce sont eux qui justifient la
    criticite (somme de leurs poids sur l'annonce la plus complete).

    liste vaut None si aucun signalement n'en porte encore (exposition
    detectee avant leur enregistrement, pas encore relue).
    """
    # Nom ACTUEL de la categorie quand elle est toujours rattachee a
    # l'exposition (elle a pu etre renommee), sinon celui fige a la detection.
    noms_actuels = {c.id: c.nom for c in exposition.categories}
    par_valeur = {}
    enregistres, manquants = 0, 0

    for signalement in exposition.sources:
        selecteurs = lire_selecteurs(signalement)
        if selecteurs is None:
            manquants += 1
            continue
        enregistres += 1
        nom_source = signalement.source.nom if signalement.source else None

        for trouve in selecteurs:
            ligne = par_valeur.setdefault(trouve["valeur"], {
                "valeur": trouve["valeur"],
                "categorie": noms_actuels.get(trouve.get("categorie_id")) or trouve.get("categorie"),
                "poids": 0,
                "occurrences": 0,
                "correspondances": [],
                "sources": [],
            })
            ligne["poids"] = max(ligne["poids"], trouve.get("poids", 1))
            ligne["occurrences"] = max(ligne["occurrences"], trouve.get("occurrences", 0))
            for niveau in trouve.get("correspondances", {}):
                if niveau not in ligne["correspondances"]:
                    ligne["correspondances"].append(niveau)
            if nom_source and nom_source not in ligne["sources"]:
                ligne["sources"].append(nom_source)

    return {
        "liste": sorted(
            par_valeur.values(),
            key=lambda ligne: (-ligne["poids"], -ligne["occurrences"], ligne["valeur"].lower()),
        ) if enregistres else None,
        "signalements_non_relus": manquants,
    }


def serialiser(exposition, detaille: bool = False) -> dict:
    donnees = {
        "id": exposition.id,
        "nom_entite": exposition.nom_entite,
        # FR-13 : categories des selecteurs qui ont declenche l'exposition.
        "categories": [{"id": c.id, "nom": c.nom} for c in exposition.categories],
        "criticite": exposition.criticite,
        "niveau_criticite": exposition.niveau_criticite.value,
        "statut": exposition.statut.value,
        # Permet a l'interface de retirer la ligne de la liste ouverte des
        # qu'un changement de statut la fait basculer, sans rechargement.
        "archivee": exposition.statut in STATUTS_ARCHIVES,
        "date_premiere_detection": exposition.date_premiere_detection.isoformat(),
        "date_derniere_detection": exposition.date_derniere_detection.isoformat(),
        "date_publication_source": (
            exposition.date_publication_source.isoformat()
            if exposition.date_publication_source else None
        ),
        "nb_sources": len(exposition.sources),
        "sources": sorted({
            sr.source.nom for sr in exposition.sources if sr.source is not None
        }),
    }

    if detaille:
        donnees["signalements"] = _sources_de(exposition)
        donnees["selecteurs_trouves"] = _selecteurs_de(exposition)

    return donnees


def _appliquer_filtres(query, args):
    """
    Filtres communs a la liste de travail et aux archives.

    Un filtre dont la valeur est invalide est ignore plutot que rejete :
    l'interface ne doit pas casser sur un parametre d'URL bricole a la main.
    """
    categorie = args.get("categorie", "").strip()
    if categorie:
        query = query.filter(Exposition.categories.any(Categorie.id == categorie))

    statut = args.get("statut", "").strip()
    if statut:
        try:
            query = query.filter(Exposition.statut == StatutExposition(statut))
        except ValueError:
            pass

    niveau_min = args.get("niveau_min", "").strip()
    if niveau_min:
        try:
            query = query.filter(
                Exposition.criticite >= seuil_du_niveau(NiveauCriticite(niveau_min))
            )
        except ValueError:
            pass

    periode = args.get("periode", "").strip()
    # isdigit() seul acceptait une chaine de 300 chiffres, que timedelta
    # refuse par un OverflowError -> 500. 3650 jours (10 ans) depassent
    # largement l'historique que le systeme peut detenir.
    if periode.isdigit() and 1 <= len(periode) <= 4:
        jours = min(int(periode), 3650)
        query = query.filter(
            Exposition.date_premiere_detection >= utc_now() - timedelta(days=jours)
        )

    recherche = args.get("q", "").strip()
    if recherche:
        query = query.filter(Exposition.nom_entite.ilike(f"%{recherche}%"))

    return query


def _reponse_liste(session, query, statuts_proposes) -> dict:
    """
    Corps de reponse commun aux deux listes.

    statuts_proposes borne le FILTRE de statut de l'interface a ce que la
    route peut effectivement renvoyer : proposer "Cloturee" dans le filtre
    d'Expositions ne ramenerait jamais rien.

    statuts_modifiables, lui, reste COMPLET : c'est la liste du selecteur de
    changement de statut, et c'est precisement depuis Expositions qu'on
    classe une exposition en faux positif ou qu'on la cloture.
    """
    total = query.count()
    lignes = (
        query.order_by(Exposition.date_premiere_detection.desc())
        .limit(LIMITE_PAR_PAGE)
        .all()
    )

    return {
        "expositions": [serialiser(e) for e in lignes],
        "total": total,
        "tronque": total > len(lignes),
        "referentiels": {
            "categories": [
                {"id": c.id, "nom": c.nom}
                for c in session.query(Categorie).order_by(Categorie.nom)
            ],
            "statuts": [s.value for s in statuts_proposes],
            "statuts_modifiables": [s.value for s in StatutExposition],
            "niveaux": [n.value for n in NiveauCriticite],
        },
    }


def enregistrer(api_bp):

    @api_bp.route("/expositions", methods=["GET"])
    @login_required
    def liste_expositions():
        """Liste de travail : tout sauf les expositions archivees."""
        session = get_session()
        try:
            query = _appliquer_filtres(session.query(Exposition), request.args).filter(
                Exposition.statut.notin_(STATUTS_ARCHIVES)
            )
            return jsonify(_reponse_liste(
                session, query,
                [s for s in StatutExposition if s not in STATUTS_ARCHIVES],
            ))
        finally:
            session.close()

    @api_bp.route("/expositions/archives", methods=["GET"])
    @login_required
    @role_requis(RoleUtilisateur.ADMIN)
    def liste_archives():
        """
        Expositions qualifiees faux positif ou cloturees.

        Reservee a admin et super_admin : ce sont des dossiers tranches,
        conserves pour l'historique et la relecture, pas de la veille
        quotidienne. Un supervisor peut toujours changer un statut - il ne
        voit simplement plus ce qu'il a range.
        """
        session = get_session()
        try:
            query = _appliquer_filtres(session.query(Exposition), request.args).filter(
                Exposition.statut.in_(STATUTS_ARCHIVES)
            )
            return jsonify(_reponse_liste(session, query, STATUTS_ARCHIVES))
        finally:
            session.close()

    @api_bp.route("/expositions/<exposition_id>", methods=["GET"])
    @login_required
    def detail_exposition(exposition_id):
        session = get_session()
        try:
            exposition = session.get(Exposition, exposition_id)
            if exposition is None:
                return jsonify({
                    "erreur": "introuvable",
                    "message": "Exposition inexistante.",
                }), 404
            return jsonify(serialiser(exposition, detaille=True))
        finally:
            session.close()

    @api_bp.route(
        "/expositions/<exposition_id>/signalements/<signalement_id>/texte", methods=["GET"]
    )
    @login_required
    @role_requis(RoleUtilisateur.SUPERVISOR)
    def texte_signalement(exposition_id, signalement_id):
        """
        Texte conserve de l'annonce d'un signalement (derogation CN-04/CN-05,
        cf. app.conservation) : deja masque, lu a la demande, jamais mis en
        cache par le navigateur.
        """
        session = get_session()
        try:
            signalement = session.get(SourceReference, signalement_id)
            if signalement is None or signalement.exposition_id != exposition_id:
                return jsonify({
                    "erreur": "introuvable",
                    "message": "Signalement inexistant.",
                }), 404
            if signalement.date_texte_brut is None:
                return jsonify({
                    "erreur": "introuvable",
                    "message": "Aucun texte conserve pour ce signalement.",
                }), 404

            reponse = jsonify({
                "texte": signalement.texte_brut,
                "longueur": len(signalement.texte_brut or ""),
                "date_texte_brut": signalement.date_texte_brut.isoformat(),
            })
            reponse.headers["Cache-Control"] = "no-store"
            return reponse
        finally:
            session.close()

    @api_bp.route("/expositions/<exposition_id>/statut", methods=["POST"])
    @login_required
    @role_requis(RoleUtilisateur.SUPERVISOR)
    def changer_statut(exposition_id):
        donnees = request.get_json(silent=True) or {}

        try:
            nouveau_statut = StatutExposition(donnees.get("statut"))
        except ValueError:
            return jsonify({
                "succes": False,
                "message": "Statut inconnu.",
            }), 400

        session = get_session()
        try:
            exposition = session.get(Exposition, exposition_id)
            if exposition is None:
                return jsonify({
                    "erreur": "introuvable",
                    "message": "Exposition inexistante.",
                }), 404

            exposition.changer_statut(nouveau_statut)
            session.commit()

            return jsonify({"succes": True, "exposition": serialiser(exposition)})
        finally:
            session.close()
