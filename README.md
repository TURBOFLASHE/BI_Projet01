# Projet Business Intelligence — TD 01

**CS 2ème Année — Business Intelligence**

Tableau de bord analytique complet développé avec **Python / Streamlit / Plotly**, couvrant l'analyse des ventes, des achats et des marges d'une entreprise de distribution informatique.

---

## Apercu du projet

Ce projet répond aux trois parties du TD :

| Partie    | Sujet                       | Données source        |
| --------- | --------------------------- | --------------------- |
| Partie 01 | Analyse des Ventes          | `data.csv`            |
| Partie 02 | Analyse des Achats          | `data_achats.csv`     |
| Partie 03 | Analyse des Marges (fusion) | Les deux tables + PMP |

---

## Architecture — Best Practices BI

Le projet suit une architecture **3 couches** :

```
COUCHE 1 — RAW DATA
  data.csv              Données brutes ventes
  data_achats.csv       Données brutes achats

        |
        v  etl_build_views.py  (ETL — a executer une seule fois)
        |

COUCHE 2 — VUES PRE-CALCULEES
  vue_fait_ventes.csv   Faits ventes + dimensions derivees
  vue_fait_achats.csv   Faits achats + dimensions derivees
  vue_dim_produits.csv  Referentiel produits (union ventes + achats)
  vue_agg_pmp.csv       PMP global par produit (pre-calcule)
  vue_pmp_chrono.csv    PMP cumulatif chronologique
  vue_fait_marges.csv   Ventes + PMP + marges (table centrale P03)

        |
        v  app.py  (Dashboard — lecture seule des vues)
        |

COUCHE 3 — PRESENTATION
  app.py                Streamlit — zero calcul, zero merge
```

**Principe cle** : `app.py` ne fait aucun merge ni calcul. Tout est pre-calcule par `etl_build_views.py`. Cela garantit des temps de chargement rapides et une coherence des donnees entre les 3 parties.

---

## Structure des fichiers

```
BI_Complet/
|
|-- app.py                    Dashboard principal (les 3 parties)
|-- etl_build_views.py        Script ETL — genere les vues
|
|
|-- data.csv                  Donnees brutes — Ventes (Tableau 01)
|-- data_achats.csv           Donnees brutes — Achats (Tableau 02)
|
|-- vue_fait_ventes.csv       Vue enrichie des ventes
|-- vue_fait_achats.csv       Vue enrichie des achats
|-- vue_dim_produits.csv      Referentiel produits
|-- vue_agg_pmp.csv           PMP global par produit
|-- vue_pmp_chrono.csv        PMP cumulatif chronologique
|-- vue_fait_marges.csv       Marges calculees par ligne de vente
|
|
`-- .gitignore
 -- README.md
 -- requirements.txt          Dependances Python
```

---

## Donnees sources

### Tableau 01 — Ventes (`data.csv`)

| Colonne        | Description                        |
| -------------- | ---------------------------------- |
| `Num.CMD`      | Numero de commande (ex: SLSD/0001) |
| `Date.CMD`     | Date de la commande                |
| `Client`       | Nom du client                      |
| `Adresse`      | Adresse + Wilaya                   |
| `Code Produit` | Code article (ex: LAP.0120)        |
| `Produit`      | Designation                        |
| `Qte`          | Quantite vendue                    |
| `Montant HT`   | Montant hors taxe                  |
| `Taxe`         | TVA (19%)                          |
| `Montant TTC`  | Montant toutes taxes comprises     |

**Type de vente** derive du prefixe du `Num.CMD` :

- `SLSD` → Direct
- `SLSR` → Retail
- `SLSG` → Government

### Tableau 02 — Achats (`data_achats.csv`)

| Colonne        | Description                             |
| -------------- | --------------------------------------- |
| `Num.CMD`      | Numero de commande achat (ex: POL/0001) |
| `Date.CMD`     | Date de la commande                     |
| `Fournisseur`  | Nom du fournisseur                      |
| `Code Produit` | Code article                            |
| `Produit`      | Designation                             |
| `QTY`          | Quantite achetee                        |
| `Montant HT`   | Cout hors taxe                          |
| `Taxe`         | TVA (19%)                               |
| `Montant TTC`  | Cout toutes taxes comprises             |

**Type d'achat** derive du prefixe du `Num.CMD` :

- `POL` → Local
- `POI` → Import

---

## ETL — Construction des vues

Le script `etl_build_views.py` effectue toutes les transformations :

1. **Dimensions derivees** (colonnes calculees automatiquement) :
   - `Type Vente` / `Type Achat` depuis le prefixe du `Num.CMD`
   - `Categorie Produit` depuis le prefixe du `Code Produit` (LAP, PRI, INK, SCA)
   - `Wilaya` depuis le dernier segment de l'`Adresse`
   - `Forme Juridique` depuis le premier mot du nom Client/Fournisseur
   - `Mois`, `Annee`, `Nom Mois` depuis la date

2. **Calcul du PMP (Prix Moyen Pondere)** :
   - Les achats sont tries **chronologiquement** par produit
   - A chaque nouvelle entree en stock :
     ```
     Cout cumule  += Montant HT
     QTY cumulee  += QTY
     PMP          = Cout cumule / QTY cumulee
     ```
   - Le PMP final est enregistre dans `vue_agg_pmp.csv`
   - L'evolution ligne par ligne est dans `vue_pmp_chrono.csv`

3. **Calcul des marges** :

   ```
   PMP             = Cout total achats / QTY totale achetee
   Marge Unitaire  = Prix Vente HT unitaire - PMP
   Marge Totale    = Marge Unitaire x Quantite vendue
   Taux de Marge   = Marge Unitaire / Prix Vente HT x 100
   Cout Ligne      = PMP x Quantite vendue
   ```

   - Si un produit est vendu sans achat enregistre : PMP = 0, Taux de marge = 100%

**Pour regenerer les vues apres une mise a jour des donnees :**

```bash
python etl_build_views.py
```

---

## Dashboard — `app.py`

Application Streamlit avec **navigation par sidebar** entre les 3 parties.

### Partie 01 — Analyse des Ventes

**Filtres globaux** : Periode, Annee, Type de vente, Wilaya, Categorie produit, Forme juridique

**Indicateurs (KPIs)** :

- Chiffre d'affaires HT
- Montant TTC total
- Quantites vendues
- Categorie la plus rentable

**Analyse dynamique** : l'utilisateur choisit librement les parametres d'analyse, l'indicateur et le type de graphe.

**Questions d'analyse repondues** :

- Q1 — Liste des produits vendus apres une date choisie
- Q2 — Classement des produits par CA, type de vente et annee
- Q3 — Classement des clients par wilaya et forme juridique
- Q4 — Ventes quantitatives par produit / type / mois / annee
- Q5 — Categorie de produit la plus rentable

---

### Partie 02 — Analyse des Achats

**Filtres globaux** : Periode, Fournisseur, Categorie produit, Type achat, Annee

**Indicateurs (KPIs)** :

- Cout d'achat total HT
- Montant TTC total
- Quantites achetees
- Categorie la plus couteuse

**Analyse dynamique** : memes capacites que la Partie 01.

**Questions d'analyse repondues** :

- Q1 — Liste des produits achetes pour une annee choisie
- Q2 — Achats quantitatifs par produit / type / mois / annee
- Q3 — Classement des fournisseurs par categorie produit
- Q4 — Categorie de produit la plus couteuse

---

### Partie 03 — Analyse des Marges

**Filtres globaux** : Periode, Produit, Categorie, Wilaya, Annee

**Indicateurs (KPIs)** :

- Chiffre d'affaires HT
- Cout d'achat total (PMP x Quantite)
- Marge brute totale
- Taux de marge global

**4 sections analytiques, chacune avec graphe interactif + tableau** :

1. **PMP Global** — visualisation du PMP, cout total et QTY par produit, avec choix du type de graphe
2. **PMP Cumulatif chronologique** — evolution du PMP dans le temps par produit (graphe lineaire ideal)
3. **Analyse dynamique des marges** — parametres, indicateur et type de graphe librement choisis par l'utilisateur
4. **Detail des marges par ligne de vente** — axe X, indicateur et type de graphe configurables
5. **Classement produits** — tri par marge totale, taux, CA ou quantite avec choix du graphe

**Types de graphes disponibles** dans toutes les sections :
Barres | Barres empilees | Lignes | Aires | Camembert | Treemap

---

## Installation et lancement

### Prerequis

- Python 3.9+
- pip

### Installation

```bash
# 1. Cloner le repo
git clone https://github.com/TON_USERNAME/NOM_DU_REPO.git
cd NOM_DU_REPO

# 2. Creer et activer l'environnement virtuel
python -m venv .venv

# Windows
.venv\Scripts\Activate

# macOS / Linux
source .venv/bin/activate

# 3. Installer les dependances
pip install -r requirements.txt

# 4. Generer les vues (a faire une seule fois, ou apres modif des donnees)
python etl_build_views.py

# 5. Lancer le dashboard
streamlit run app.py
```

L'application s'ouvre automatiquement sur `http://localhost:8501`

---

## Acces en ligne (sans installation)

L'application est deployee sur Streamlit Cloud et accessible directement via ce lien :

**[https://biprojet01-ydvahtkwbcomw7u4f3k9uw.streamlit.app/]**

---

## Technologies utilisees

| Outil           | Role                                       |
| --------------- | ------------------------------------------ |
| Python 3        | Langage principal                          |
| Pandas          | Manipulation et transformation des donnees |
| Streamlit       | Interface web du dashboard                 |
| Plotly Express  | Graphes interactifs                        |
| Streamlit Cloud | Deploiement en ligne (gratuit)             |
| GitHub          | Versionnement et hebergement du code       |

---

## Choix techniques justifies

- **Separation ETL / Presentation** : le merge et le calcul du PMP ne sont faits qu'une seule fois par `etl_build_views.py`, pas a chaque rechargement du dashboard. Cela respecte le principe de separation des couches en BI.
- **`@st.cache_data`** : les vues CSV sont mises en cache par Streamlit, evitant de relire les fichiers a chaque interaction utilisateur.
- **Format K/M** : tous les grands nombres sont affiches en milliers (K) ou millions (M) pour la lisibilite.
- **PMP = 0 si aucun achat** : les produits vendus sans achat correspondant ont un PMP de 0 DA, ce qui donne un taux de marge de 100%. Un avertissement est affiche dans l'interface.
- **Couleurs semantiques** : les marges negatives s'affichent en rouge, les positives en vert.
