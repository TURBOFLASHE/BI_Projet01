"""
etl_build_views.py
==================
Couche ETL / Transformation — Best Practices BI
------------------------------------------------
Ce script lit les données brutes (data.csv, data_achats.csv,
data_ventes_new.csv, data_achats_new.csv), harmonise les colonnes,
fusionne les fichiers anciens et nouveaux, applique toutes les
transformations, calcule les agrégats (PMP, marges) et produit
des VUES pré-calculées sous forme de CSV.

Architecture en 3 couches :
  RAW     → data.csv, data_achats.csv              (données sources anciennes)
            data_ventes_new.csv, data_achats_new.csv (données sources nouvelles)
  VUES    → vue_*.csv                               (tables de faits + dims + agrégats)
  APP     → app.py ...                              (lecture seule des vues, 0 calcul)

Lancer ce script une seule fois (ou à chaque mise à jour des données brutes) :
  python etl_build_views.py

Les vues générées :
  vue_fait_ventes.csv      — Faits ventes enrichis (dimensions dérivées)
  vue_fait_achats.csv      — Faits achats enrichis (dimensions dérivées)
  vue_dim_produits.csv     — Référentiel produits (union ventes + achats)
  vue_agg_pmp.csv          — PMP global par produit (agrégat pré-calculé)
  vue_pmp_chrono.csv       — PMP cumulatif chronologique par produit
  vue_fait_marges.csv      — Ventes + PMP + marges (table centrale Partie 03)
"""

import pandas as pd
import os

# ── Chemins ────────────────────────────────────────────────────────────────────
RAW_VENTES      = "data.csv"
RAW_ACHATS      = "data_achats.csv"
RAW_VENTES_NEW  = "data_ventes_new.csv"
RAW_ACHATS_NEW  = "data_achats_new.csv"
OUTPUT_DIR      = "."   # même dossier, changer si besoin (ex: "vues/")


def clean_numeric(series):
    """
    Nettoie une colonne numérique :
    - Supprime les virgules de milliers (ex: "1,590,000" → "1590000")
    - Convertit en float
    """
    return (
        series.astype(str)
        .str.replace(",", "", regex=False)
        .str.strip()
        .replace("nan", pd.NA)
        .astype(float)
    )


def load_ventes():
    """
    Charge et fusionne les fichiers ventes ancien et nouveau.

    Différences entre les deux fichiers (même ordre de colonnes) :
      Ancien  → "Qte"       | dates format YYYY-MM-DD | montants sans virgules
      Nouveau → "Quantité"  | dates format M/D/YYYY   | montants avec virgules (ex: "384,000")
                + colonnes parasites "Unnamed: 10", "Unnamed: 11"

    Résultat uniforme :
      Num.CMD | Date.CMD | Client | Adresse | Code Produit | Produit
      Qte | Montant HT | Taxe | Montant TTC
    """
    # ── Ancien fichier (colonnes de référence) ─────────────────────────────
    old = pd.read_csv(RAW_VENTES)

    # ── Nouveau fichier ────────────────────────────────────────────────────
    new = pd.read_csv(RAW_VENTES_NEW)

    # Supprimer les colonnes parasites (Unnamed: ...)
    new = new.loc[:, ~new.columns.str.startswith("Unnamed")]

    # Renommer "Quantité" → "Qte" pour aligner sur l'ancien
    new = new.rename(columns={"Quantité": "Qte"})

    # Nettoyer les colonnes numériques (virgules de milliers)
    for col in ["Qte", "Montant HT", "Taxe", "Montant TTC"]:
        new[col] = clean_numeric(new[col])

    # ── Concaténation ──────────────────────────────────────────────────────
    ventes = pd.concat([old, new], ignore_index=True)
    print(f"      ventes ancien : {len(old)} lignes | nouveau : {len(new)} lignes "
          f"| total fusionné : {len(ventes)} lignes")
    return ventes


def load_achats():
    """
    Charge et fusionne les fichiers achats ancien et nouveau.

    Différences entre les deux fichiers (même ordre de colonnes) :
      Ancien  → "QTY"       | dates format YYYY-MM-DD | montants sans virgules
      Nouveau → "Quantité"  | dates format M/D/YYYY   | montants avec virgules (ex: "1,590,000")
                + colonnes parasites "Unnamed: 9", "Unnamed: 10"

    Résultat uniforme :
      Num.CMD | Date.CMD | Fournisseur | Code Produit | Produit
      QTY | Montant HT | Taxe | Montant TTC
    """
    # ── Ancien fichier (colonnes de référence) ─────────────────────────────
    old = pd.read_csv(RAW_ACHATS)

    # ── Nouveau fichier ────────────────────────────────────────────────────
    new = pd.read_csv(RAW_ACHATS_NEW)

    # Supprimer les colonnes parasites (Unnamed: ...)
    new = new.loc[:, ~new.columns.str.startswith("Unnamed")]

    # Renommer "Quantité" → "QTY" pour aligner sur l'ancien
    new = new.rename(columns={"Quantité": "QTY"})

    # Nettoyer les colonnes numériques (virgules de milliers)
    for col in ["QTY", "Montant HT", "Taxe", "Montant TTC"]:
        new[col] = clean_numeric(new[col])

    # ── Concaténation ──────────────────────────────────────────────────────
    achats = pd.concat([old, new], ignore_index=True)
    print(f"      achats ancien : {len(old)} lignes | nouveau : {len(new)} lignes "
          f"| total fusionné : {len(achats)} lignes")
    return achats


def build_views():
    print("=" * 55)
    print("  ETL — Construction des vues BI")
    print("=" * 55)

    # ── 1. Chargement et fusion des données brutes ────────────────────────────
    print("\n[1/6] Chargement et fusion des données brutes...")
    ventes = load_ventes()
    achats = load_achats()

    # format='mixed' gère les deux formats de date en même temps :
    #   YYYY-MM-DD (ancien) et M/D/YYYY (nouveau)
    ventes["Date.CMD"] = pd.to_datetime(ventes["Date.CMD"], format="mixed", dayfirst=False)
    achats["Date.CMD"] = pd.to_datetime(achats["Date.CMD"], format="mixed", dayfirst=False)

    print(f"      Total ventes : {len(ventes)} lignes | Total achats : {len(achats)} lignes")

    # ── 2. VUE : fait_ventes ─────────────────────────────────────────────────
    print("\n[2/6] Construction vue_fait_ventes...")

    # Mapping basé sur la DERNIÈRE LETTRE du préfixe (avant le "/")
    # Ex: VCD → D, VCR → R, SLSD → D, SLSR → R  (flexible quel que soit le codage)
    TYPE_VENTE_MAP = {
        "D": "Direct",
        "R": "Retail",
        "G": "Government",
    }

    ventes["Type Vente"]        = (
        ventes["Num.CMD"]
        .str.split("/").str[0]   # préfixe avant le "/"  ex: "VCD", "VCR", "SLSD"
        .str[-1]                 # dernière lettre        ex: "D",   "R",   "D"
        .map(TYPE_VENTE_MAP)
        .fillna("Autre")
    )
    ventes["Catégorie Produit"] = ventes["Code Produit"].str.split(".").str[0]
    ventes["Wilaya"]            = ventes["Adresse"].str.split(",").str[-1].str.strip()
    ventes["Forme Juridique"]   = ventes["Client"].str.split().str[0]
    ventes["Mois"]              = ventes["Date.CMD"].dt.month
    ventes["Année"]             = ventes["Date.CMD"].dt.year
    ventes["Nom Mois"]          = ventes["Date.CMD"].dt.strftime("%B")
    ventes["PU_Vente"]          = ventes["Montant HT"] / ventes["Qte"]

    path = os.path.join(OUTPUT_DIR, "vue_fait_ventes.csv")
    ventes.to_csv(path, index=False)
    print(f"      ✓ {path}  ({len(ventes)} lignes, {len(ventes.columns)} colonnes)")

    # ── 3. VUE : fait_achats ─────────────────────────────────────────────────
    print("\n[3/6] Construction vue_fait_achats...")

    # Mapping basé sur la DERNIÈRE LETTRE du préfixe (avant le "/")
    # Ex: AFL → L, AFI → I, POL → L, POI → I  (flexible quel que soit le codage)
    TYPE_ACHAT_MAP = {
        "L": "Local",
        "I": "Import",
    }

    achats["Type Achat"]        = (
        achats["Num.CMD"]
        .str.split("/").str[0]   # préfixe avant le "/"  ex: "AFL", "AFI", "POL"
        .str[-1]                 # dernière lettre        ex: "L",   "I",   "L"
        .map(TYPE_ACHAT_MAP)
        .fillna("Autre")
    )
    achats["Catégorie Produit"] = achats["Code Produit"].str.split(".").str[0]
    achats["Forme Juridique"]   = achats["Fournisseur"].str.split().str[0]
    achats["Mois"]              = achats["Date.CMD"].dt.month
    achats["Année"]             = achats["Date.CMD"].dt.year
    achats["Nom Mois"]          = achats["Date.CMD"].dt.strftime("%B")
    achats["PU_Achat"]          = achats["Montant HT"] / achats["QTY"]

    path = os.path.join(OUTPUT_DIR, "vue_fait_achats.csv")
    achats.to_csv(path, index=False)
    print(f"      ✓ {path}  ({len(achats)} lignes, {len(achats.columns)} colonnes)")

    # ── 4. VUE : dim_produits ────────────────────────────────────────────────
    print("\n[4/6] Construction vue_dim_produits...")

    prod_v = ventes[["Code Produit", "Produit", "Catégorie Produit"]].drop_duplicates()
    prod_a = achats[["Code Produit", "Produit", "Catégorie Produit"]].drop_duplicates()
    dim_produits = (
        pd.concat([prod_v, prod_a])
        .drop_duplicates(subset="Code Produit")
        .sort_values("Code Produit")
        .reset_index(drop=True)
    )

    path = os.path.join(OUTPUT_DIR, "vue_dim_produits.csv")
    dim_produits.to_csv(path, index=False)
    print(f"      ✓ {path}  ({len(dim_produits)} produits uniques)")

    # ── 5. VUE : agg_pmp ────────────────────────────────────────────────────
    print("\n[5/6] Construction vue_agg_pmp (PMP global par produit)...")

    # Trier chronologiquement AVANT le groupby pour respecter l'ordre des entrées
    achats_sorted = achats.sort_values("Date.CMD")

    agg_pmp = (
        achats_sorted
        .groupby(["Code Produit", "Produit", "Catégorie Produit"], sort=False)
        .apply(lambda g: pd.Series({
            # PMP = Σ(Montant HT) / Σ(QTY)  — pondéré par les quantités
            "PMP":        g["Montant HT"].sum() / g["QTY"].sum(),
            "Cout_Total": g["Montant HT"].sum(),
            "QTY_Totale": g["QTY"].sum(),
            "Nb_Entrees": len(g),
            "Premiere_Entree": g["Date.CMD"].min().strftime("%Y-%m-%d"),
            "Derniere_Entree": g["Date.CMD"].max().strftime("%Y-%m-%d"),
        }))
        .reset_index()
        .sort_values("Code Produit")
    )

    path = os.path.join(OUTPUT_DIR, "vue_agg_pmp.csv")
    agg_pmp.to_csv(path, index=False)
    print(f"      ✓ {path}  ({len(agg_pmp)} produits)")
    print(agg_pmp[["Code Produit", "PMP", "Cout_Total", "QTY_Totale"]].to_string(index=False))

    # ── 5b. VUE : pmp_chrono ────────────────────────────────────────────────
    print("\n      Construction vue_pmp_chrono (PMP cumulatif)...")

    rows = []
    for code, grp in achats_sorted.groupby("Code Produit", sort=False):
        cout_cumul = qty_cumul = 0
        for _, row in grp.iterrows():
            cout_cumul += row["Montant HT"]
            qty_cumul  += row["QTY"]
            rows.append({
                "Code Produit": code,
                "Produit":      row["Produit"],
                "Date.CMD":     row["Date.CMD"].strftime("%Y-%m-%d"),
                "Num.CMD":      row["Num.CMD"],
                "QTY":          row["QTY"],
                "PU_Achat":     row["PU_Achat"],
                "Montant HT":   row["Montant HT"],
                "Cout_Cumul":   cout_cumul,
                "QTY_Cumul":    qty_cumul,
                "PMP_Cumul":    round(cout_cumul / qty_cumul, 4),
            })

    pmp_chrono = pd.DataFrame(rows)
    path = os.path.join(OUTPUT_DIR, "vue_pmp_chrono.csv")
    pmp_chrono.to_csv(path, index=False)
    print(f"      ✓ {path}  ({len(pmp_chrono)} lignes)")

    # ── 6. VUE : fait_marges ────────────────────────────────────────────────
    print("\n[6/6] Construction vue_fait_marges (ventes + PMP + marges)...")

    # Jointure ventes ← PMP (LEFT JOIN pour garder les ventes sans achat)
    fait_marges = ventes.merge(
        agg_pmp[["Code Produit", "PMP"]],
        on="Code Produit",
        how="left"
    )

    # PMP=0 si le produit n'a aucun achat enregistré → marge = 100%
    pmp_zero = fait_marges[fait_marges["PMP"].isna()]["Produit"].unique()
    if len(pmp_zero):
        print(f"      ⚠ PMP manquant → mis à 0 (marge 100%) pour : {list(pmp_zero)}")
    fait_marges["PMP"] = fait_marges["PMP"].fillna(0)

    fait_marges["Marge_Unitaire"] = fait_marges["PU_Vente"] - fait_marges["PMP"]
    fait_marges["Marge_Totale"]   = fait_marges["Marge_Unitaire"] * fait_marges["Qte"]
    fait_marges["Taux_Marge"]     = (
        (fait_marges["Marge_Unitaire"] / fait_marges["PU_Vente"]) * 100
    ).round(4)
    # Coût total de la ligne = PMP × quantité vendue
    fait_marges["Cout_Ligne"]     = fait_marges["PMP"] * fait_marges["Qte"]

    path = os.path.join(OUTPUT_DIR, "vue_fait_marges.csv")
    fait_marges.to_csv(path, index=False)
    print(f"      ✓ {path}  ({len(fait_marges)} lignes, {len(fait_marges.columns)} colonnes)")

    # ── Résumé ───────────────────────────────────────────────────────────────
    print("\n" + "=" * 55)
    print("  ✅ Toutes les vues ont été générées avec succès.")
    print("=" * 55)
    print("\n  Vues disponibles :")
    vues = [
        ("vue_fait_ventes.csv",  "Faits ventes enrichis"),
        ("vue_fait_achats.csv",  "Faits achats enrichis"),
        ("vue_dim_produits.csv", "Référentiel produits"),
        ("vue_agg_pmp.csv",      "PMP global par produit"),
        ("vue_pmp_chrono.csv",   "PMP cumulatif chronologique"),
        ("vue_fait_marges.csv",  "Ventes + PMP + Marges"),
    ]
    for fname, desc in vues:
        size = os.path.getsize(os.path.join(OUTPUT_DIR, fname))
        print(f"  📄 {fname:<28} {desc}  ({size:,} octets)")

if __name__ == "__main__":
    build_views()