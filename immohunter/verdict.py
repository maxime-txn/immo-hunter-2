"""
Étape 4 : le verdict sur une annonce.

On compare le prix DEMANDÉ à l'estimation du prix de VENTE et à sa fourchette
(l'intervalle qui contient 80 % des ventes réelles comparables).

    au-dessus de la fourchette haute   -> Surévalué
    entre +5 % et la fourchette haute  -> Au-dessus du marché
    entre -5 % et +5 %                 -> Au prix du marché
    entre la fourchette basse et -5 %  -> En dessous du marché
    sous la fourchette basse           -> Sous-évalué

Le seuil de 5 % correspond à une marge de négociation courante : un prix d'annonce
légèrement au-dessus de l'estimation n'est pas anormal.
"""

SOUS_EVALUE = "Sous-évalué"
EN_DESSOUS = "En dessous du marché"
AU_PRIX = "Au prix du marché"
AU_DESSUS = "Au-dessus du marché"
SUREVALUE = "Surévalué"

MARGE_PCT = 5


def verdict(prix_demande, prix_estime, fourchette_basse, fourchette_haute):
    ecart_pct = (prix_demande - prix_estime) / prix_estime * 100
    if prix_demande > fourchette_haute:
        label = SUREVALUE
    elif prix_demande < fourchette_basse:
        label = SOUS_EVALUE
    elif ecart_pct > MARGE_PCT:
        label = AU_DESSUS
    elif ecart_pct < -MARGE_PCT:
        label = EN_DESSOUS
    else:
        label = AU_PRIX
    return {"verdict": label, "ecart_pct": round(ecart_pct, 1)}
