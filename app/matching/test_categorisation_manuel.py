"""Test manuel de la categorisation FR-13."""

from app.matching.categorisation import categoriser_texte

SAMPLE_TEXTS = [
    "Leaked database contains username and password combolist for 50000 accounts.",
    "Full customer PII exposed including national id and date of birth.",
    "Bank account numbers and credit card data from a Cameroonian institution.",
    "Patient medical records and diagnosis history leaked from hospital systems.",
    "Internal confidential memo and contract documents from the finance department.",
    "Proprietary source code and internal repository dumped on the forum.",
    "A ransomware group claims to have breached the network, no further details.",
]

for i, texte in enumerate(SAMPLE_TEXTS, start=1):
    categorie, details = categoriser_texte(texte)
    print(f"Texte {i}: '{texte[:60]}...'")
    print(f"  -> Categorie : {categorie.value} | Details : {details}\n")