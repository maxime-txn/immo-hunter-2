from immohunter.verdict import (AU_DESSUS, AU_PRIX, EN_DESSOUS, SOUS_EVALUE, SUREVALUE,
                                verdict)

# Estimation 500 000 €, fourchette 420 000 € - 600 000 €
EST, BAS, HAUT = 500_000, 420_000, 600_000


def test_au_prix_du_marche():
    assert verdict(510_000, EST, BAS, HAUT)["verdict"] == AU_PRIX


def test_au_dessus_mais_dans_la_fourchette():
    assert verdict(560_000, EST, BAS, HAUT)["verdict"] == AU_DESSUS


def test_surevalue_au_dela_de_la_fourchette():
    r = verdict(650_000, EST, BAS, HAUT)
    assert r["verdict"] == SUREVALUE and r["ecart_pct"] == 30.0


def test_en_dessous_et_sous_evalue():
    assert verdict(450_000, EST, BAS, HAUT)["verdict"] == EN_DESSOUS
    assert verdict(400_000, EST, BAS, HAUT)["verdict"] == SOUS_EVALUE
