"""FR-17 - Consultation du journal d'audit (super_admin)."""

from flask import jsonify, request
from flask_login import login_required

from app.db import get_session
from app.models import JournalAudit, ResultatAudit, RoleUtilisateur, Source
from app.web.permissions import role_requis


# Le journal grossit d'une ligne par appel de connecteur : une borne est
# indispensable pour ne pas envoyer des dizaines de milliers de lignes.
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
