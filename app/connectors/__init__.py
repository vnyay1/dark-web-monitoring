"""
Registre unique des connecteurs branches au pipeline (FR-02).

Ajouter une source au systeme = ecrire une classe heritant de
BaseConnector, puis l'ajouter ici. Aucun autre fichier n'a besoin de
connaitre la liste des sources.

Les imports sont volontairement faits A L'INTERIEUR des fonctions :
app.connectors est importe en cascade par les connecteurs eux-memes, un
import au niveau module creerait un cycle.
"""


def connecteurs_actifs():
    """
    Classes de connecteurs executees a chaque cycle de collecte : les 7
    sources .onion. The Hacker News (clairnet) a ete retire de la
    surveillance ; ses donnees se nettoient avec app.maintenance.retirer_source.
    """
    from app.connectors.payload_connector import PayloadConnector
    from app.connectors.orionleaks_connector import OrionLeaksConnector
    from app.connectors.dataexposurelogs_connector import DataExposureLogsConnector
    from app.connectors.blackwater_connector import BlackWaterConnector
    from app.connectors.safepay_connector import SafePayConnector
    from app.connectors.cmdorganization_connector import CmdOrganizationConnector
    from app.connectors.everest_connector import EverestConnector

    return [
        PayloadConnector,
        OrionLeaksConnector,
        DataExposureLogsConnector,
        BlackWaterConnector,
        SafePayConnector,
        CmdOrganizationConnector,
        EverestConnector,
    ]


def connecteur_par_nom(nom):
    """
    Retrouve un connecteur par son SOURCE_NAME (execution ciblee :
    python -m app.pipeline --source payload).
    """
    for classe in connecteurs_actifs():
        if classe.SOURCE_NAME == nom:
            return classe

    connus = ", ".join(sorted(c.SOURCE_NAME for c in connecteurs_actifs()))
    raise KeyError(f"Connecteur inconnu : {nom}. Connecteurs disponibles : {connus}")
