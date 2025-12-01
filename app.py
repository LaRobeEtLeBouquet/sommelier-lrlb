import streamlit as st
import pandas as pd
from pathlib import Path

# ---------- CONFIG GÉNÉRALE ----------

st.set_page_config(
   page_title="Mon Sommelier – La Robe et Le Bouquet",
   page_icon="🍷",
   layout="wide",
)

DATA_DIR = Path(__file__).parent / "data"


# ---------- FONCTIONS DE CHARGEMENT ----------

@st.cache_data
def load_pictos():
   path = DATA_DIR / "Pictos.xlsx"
   return pd.read_excel(path)


@st.cache_data
def load_corps_aromes():
   path = DATA_DIR / "Corps et aromes.xlsx"
   return pd.read_excel(path)


@st.cache_data
def load_export_produits():
   path = DATA_DIR / "Export produits brut.xlsx"
   return pd.read_excel(path)


@st.cache_data
def load_export_facture():
   path = DATA_DIR / "Export Facture Brut.xlsx"
   return pd.read_excel(path)


# ---------- CONSTRUCTION DU CATALOGUE ----------

def construire_catalogue(df_produits: pd.DataFrame, df_ca: pd.DataFrame) -> pd.DataFrame:
   """
   Construit un DataFrame 'catalogue' standardisé à partir de :
   - Export produits brut.xlsx
   - Corps et aromes.xlsx

   On utilise les numéros de colonnes fournis :
   Export produits brut :
       B (1) : id_produit
       C (2) : Famille
       D (3) : SousFamille
       E (4) : Produit
       F (5) : Millesime
       G (6) : Conditionnement
       J (9) : Stock
       P (15): Prix_TTC
       Q (16): Couleur
       R (17): Mention_Valorisante
       U (20): Description commerciale
       W (22): Coup de Coeur
       X (23): Statut
       AA (26): Archivé
       N (13): Cuvée
   Corps et aromes :
       A (0): id_produit
       B (1): Désignation
       C (2): Millésime
       D (3): Couleur
       E (4): Corps
       F (5): Arome1
       G (6): Arome2
       H (7): Culture
   """

   # Renommer les colonnes par index pour plus de clarté
   # (on ne dépend pas des labels exacts avec \n etc.)
   prod = df_produits.copy()
   ca = df_ca.copy()

   # On récupère les colonnes par index
   prod_cols = {
       "id_produit": prod.columns[1],
       "Famille": prod.columns[2],
       "SousFamille": prod.columns[3],
       "Produit": prod.columns[4],
       "Millesime": prod.columns[5],
       "Conditionnement": prod.columns[6],
       "Stock": prod.columns[9],
       "Prix_TTC": prod.columns[15],
       "Couleur": prod.columns[16],
       "Mention_Valorisante": prod.columns[17],
       "Description_commerciale": prod.columns[20],
       "Coup_de_Coeur": prod.columns[22],
       "Statut": prod.columns[23],
       "Archive": prod.columns[26],
       "Cuvee": prod.columns[13],
   }

   ca_cols = {
       "id_produit": ca.columns[0],
       "Designation": ca.columns[1],
       "CA_Millesime": ca.columns[2],
       "CA_Couleur": ca.columns[3],
       "Corps": ca.columns[4],
       "Arome1": ca.columns[5],
       "Arome2": ca.columns[6],
       "Culture": ca.columns[7],
   }

   prod_std = prod.rename(columns={
       prod_cols["id_produit"]: "id_produit",
       prod_cols["Famille"]: "Famille",
       prod_cols["SousFamille"]: "SousFamille",
       prod_cols["Produit"]: "Produit",
       prod_cols["Millesime"]: "Millesime",
       prod_cols["Conditionnement"]: "Conditionnement",
       prod_cols["Stock"]: "Stock",
       prod_cols["Prix_TTC"]: "Prix_TTC",
       prod_cols["Couleur"]: "Couleur",
       prod_cols["Mention_Valorisante"]: "Mention_Valorisante",
       prod_cols["Description_commerciale"]: "Description_commerciale",
       prod_cols["Coup_de_Coeur"]: "Coup_de_Coeur",
       prod_cols["Statut"]: "Statut",
       prod_cols["Archive"]: "Archive",
       prod_cols["Cuvee"]: "Cuvee",
   })

   ca_std = ca.rename(columns={
       ca_cols["id_produit"]: "id_produit",
       ca_cols["Designation"]: "Designation",
       ca_cols["CA_Millesime"]: "CA_Millesime",
       ca_cols["CA_Couleur"]: "CA_Couleur",
       ca_cols["Corps"]: "Corps",
       ca_cols["Arome1"]: "Arome1",
       ca_cols["Arome2"]: "Arome2",
       ca_cols["Culture"]: "Culture",
   })

   # Jointure sur id_produit
   cat = pd.merge(prod_std, ca_std, on="id_produit", how="left")

   # Nettoyage des statuts / filtres produits vendables
   def est_vendable(row):
       statut = str(row.get("Statut", "") or "").strip()
       archive = row.get("Archive", 0)
       try:
           archive = int(archive)
       except Exception:
           archive = 0
       if statut in ["Épuisé", "Echantillon"]:
           return False
       if archive == 1:
           return False
       return True

   cat["Vendable"] = cat.apply(est_vendable, axis=1)
   cat_vendable = cat[cat["Vendable"]].copy()

   # Normalisation de quelques champs
   cat_vendable["Coup_de_Coeur"] = cat_vendable["Coup_de_Coeur"].fillna("").astype(str).str.strip().eq("Oui")
   cat_vendable["Description_commerciale"] = cat_vendable["Description_commerciale"].fillna("").astype(str)
   cat_vendable["Mention_Valorisante"] = cat_vendable["Mention_Valorisante"].fillna("").astype(str)
   cat_vendable["Cuvee"] = cat_vendable["Cuvee"].fillna("").astype(str)
   cat_vendable["Conditionnement"] = cat_vendable["Conditionnement"].fillna("").astype(str)

   return cat_vendable


# ---------- CONSTRUCTION DE L'HISTORIQUE ----------

def construire_historique(df_fact: pd.DataFrame) -> pd.DataFrame:
   """
   Construit un DataFrame 'historique' standardisé à partir de :
   - Export Facture Brut.xlsx

   Hypothèses (selon tes infos) :
       N : "Client" contient maintenant directement l'id_client (plus de nom)
       T : "N° Pièce" = "Facture 20250503"
       P : "Produits" = "N° 352 - Nom du vin"
       E : "Quantité"
   """

   fact = df_fact.copy()

   # Colonnes par index (0-based)
   col_client = fact.columns[13]  # N
   col_piece = fact.columns[19]   # T
   col_produit = fact.columns[15] # P
   col_qte = fact.columns[4]      # E

   hist = pd.DataFrame()
   hist["id_client_raw"] = fact[col_client]
   hist["id_commande_raw"] = fact[col_piece]
   hist["id_produit_raw"] = fact[col_produit]
   hist["quantite"] = fact[col_qte]

   # Extraction de l'id_client (déjà un identifiant seul)
   def parse_client(x):
       if pd.isna(x):
           return None
       # On essaie de le convertir en int si possible
       try:
           return int(str(x).strip())
       except Exception:
           return str(x).strip()

   hist["id_client"] = hist["id_client_raw"].apply(parse_client)

   # Extraction de id_commande après "Facture "
   def parse_commande(x):
       if pd.isna(x):
           return None
       s = str(x)
       if "Facture" in s:
           return s.split("Facture", 1)[1].strip()
       return s.strip()

   hist["id_commande"] = hist["id_commande_raw"].apply(parse_commande)

   # Extraction de id_produit à partir de "N° 352 - ..."
   import re

   def parse_produit(x):
       if pd.isna(x):
           return None
       s = str(x)
       m = re.search(r"N°\s*(\d+)", s)
       if m:
           return int(m.group(1))
       # fallback : rien trouvé
       try:
           return int(s.strip())
       except Exception:
           return None

   hist["id_produit"] = hist["id_produit_raw"].apply(parse_produit)

   # Nettoyage quantités
   def parse_qte(x):
       try:
           return int(x)
       except Exception:
           try:
               return float(x)
           except Exception:
               return 0

   hist["quantite"] = hist["quantite"].apply(parse_qte)

   # On garde seulement les colonnes standardisées
   hist_std = hist[["id_client", "id_commande", "id_produit", "quantite"]].dropna(subset=["id_client", "id_commande", "id_produit"])

   return hist_std


# ---------- UI PRINCIPALE (SQUELETTE) ----------

def main():
   st.title("🍷 Mon Sommelier – La Robe et Le Bouquet")

   st.markdown(
       """
       Ceci est une première version **technique** du sommelier LR&LB :  
       - chargement des fichiers Excel,  
       - construction du *catalogue vendable*,  
       - construction de l'*historique client*.  

       Ensuite, on branchera l'IA (Mistral via Groq) pour les recommandations.
       """
   )

   with st.sidebar:
       st.header("Données LR&LB")

       try:
           df_pictos = load_pictos()
           st.success(f"Pictos chargés : {df_pictos.shape[0]} lignes")
       except Exception as e:
           st.error(f"Erreur chargement Pictos.xlsx : {e}")

       try:
           df_ca = load_corps_aromes()
           st.success(f"Corps & arômes chargés : {df_ca.shape[0]} lignes")
       except Exception as e:
           st.error(f"Erreur chargement Corps et aromes.xlsx : {e}")

       try:
           df_prod = load_export_produits()
           st.success(f"Produits bruts chargés : {df_prod.shape[0]} lignes")
       except Exception as e:
           st.error(f"Erreur chargement Export produits brut.xlsx : {e}")

       try:
            df_fact = load_export_facture()
            st.success(f"Factures brutes chargées : {df_fact.shape[0]} lignes")
        except Exception as e:
            st.error(f"Erreur chargement Export Facture Brut.xlsx : {e}")

    # Construction catalogue + historique si tout va bien
    if "df_prod" in locals() and "df_ca" in locals():
        catalogue = construire_catalogue(df_prod, df_ca)
        st.subheader("Catalogue vendable construit")
        st.write(f"Nombre de vins vendables : **{catalogue.shape[0]}**")
        st.dataframe(catalogue.head(10))

    if "df_fact" in locals():
        historique = construire_historique(df_fact)
        st.subheader("Historique client construit")
        st.write(f"Lignes d'historique : **{historique.shape[0]}**")
        st.dataframe(historique.head(10))


if __name__ == "__main__":
   main()
