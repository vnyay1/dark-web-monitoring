"""
FR-17 - Consultation du journal d'audit (super_admin).

Lecture seule : le journal n'a qu'un point d'ecriture, app.audit, qui le
tient a app.audit.LIMITE_JOURNAL entrees (file circulaire).
"""

from flask import jsonify, request
from flask_login import login_required

from app.db import get_session
from app.models import JournalAudit, ResultatAudit, RoleUtilisateur, Source
from app.web.permissions import role_requis


# Borne d'AFFICHAGE, distincte du plafond de la table (app.audit :
# LIMITE_JOURNAL). Plus basse que lui volontairement : une page qui
# renverrait le journal entier serait illisible, et le drapeau "tronque"
# avertit l'analyste que d'autres lignes existent.
LIMITE_AUDIT = 500


def enregistrer(api_bp):

    @api_bp.route("/audit", methods=["GET"])
    @login_required
    @role_requis(RoleUtilisateur.SUPER_ADMIN)
    def journal_audit():
        session = get_session()
        try:
            query = session.query(JournalAudit).order_by(JournalAudit.horodatage.desc())

            resultat = request.args.get("resultat", "").strip()
            if resultat:
                try:
                    query = query.filter(JournalAudit.resultat == ResultatAudit(resultat))
                except ValueError:
                    pass

            source_id = request.args.get("source_id", "").strip()
            if source_id:
                query = query.filter(JournalAudit.source_id == source_id)

            entrees = query.limit(LIMITE_AUDIT).all()
            sources = session.query(Source).order_by(Source.nom).all()
            noms = {s.id: s.nom for s in sources}

            return jsonify({
                "entrees": [
                    {
                        "id": e.id,
                        "horodatage": e.horodatage.isoformat(),
                        "resultat": e.resultat.value,
                        "source": noms.get(e.source_id),
                        "source_id": e.source_id,
                        "details": e.details,
                    }
                    for e in entrees
                ],
                "sources": [{"id": s.id, "nom": s.nom} for s in sources],
                "resultats": [r.value for r in ResultatAudit],
                "tronque": len(entrees) == LIMITE_AUDIT,
            })
        finally:
            session.close()
