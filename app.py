import streamlit as st
import pandas as pd
from pathlib import Path
import re
import json
from groq import Groq

# ---------- CONFIG GÉNÉRALE ----------

st.set_page_config(
    page_title="Mon Sommelier – La Robe et Le Bouquet",
    page_icon="🍷",
    layout="wide",
)

DATA_DIR = Path(__file__).parent / "data"


# ---------- FONCTIONS DE CHARGEMENT DES FICHIERS ----------

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


# ---------- CONSTRUCTION DU CATALOGUE VENDABLE ----------

def construire_catalogue(df_produits: pd.DataFrame, df_ca: pd.DataFrame) -> pd.DataFrame:
    """
    Construit un DataFrame 'catalogue' standardisé à partir de :
    - Export produits brut.xlsx
    - Corps et aromes.xlsx

    Mapping colonnes (par index) adapté à tes fichiers :

    Export produits brut :
        B (1)  : id_produit
        C (2)  : Famille
        D (3)  : SousFamille
        E (4)  : Produit
        F (5)  : Millesime
        G (6)  : Conditionnement
        J (9)  : Stock
        P (15) : Prix_TTC
        Q (16) : Couleur
        R (17) : Mention_Valorisante
        N (13) : Cuvee
        U (20) : Description commerciale
        W (22) : Coup de Coeur ("Oui" / "")
        X (23) : Statut
        AA(26) : Archive (1 ou 0)

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

    prod = df_produits.copy()
    ca = df_ca.copy()

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

    cat = pd.merge(prod_std, ca_std, on="id_produit", how="left")

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

    cat_vendable["Coup_de_Coeur"] = cat_vendable["Coup_de_Coeur"].fillna("").astype(str).str.strip().eq("Oui")
    cat_vendable["Description_commerciale"] = cat_vendable["Description_commerciale"].fillna("").astype(str)
    cat_vendable["Mention_Valorisante"] = cat_vendable["Mention_Valorisante"].fillna("").astype(str)
    cat_vendable["Cuvee"] = cat_vendable["Cuvee"].fillna("").astype(str)
    cat_vendable["Conditionnement"] = cat_vendable["Conditionnement"].fillna("").astype(str)
    cat_vendable["Corps"] = cat_vendable["Corps"].fillna("").astype(str)
    cat_vendable["Arome1"] = cat_vendable["Arome1"].fillna("").astype(str)
    cat_vendable["Arome2"] = cat_vendable["Arome2"].fillna("").astype(str)
    cat_vendable["Culture"] = cat_vendable["Culture"].fillna("").astype(str)

    return cat_vendable


# ---------- CONSTRUCTION DE L'HISTORIQUE CLIENT ----------

def construire_historique(df_fact: pd.DataFrame) -> pd.DataFrame:
    """
    Construit un DataFrame 'historique' standardisé à partir de :
    - Export Facture Brut.xlsx

    Hypothèses (version RGPD-safe) :
        N : "Client" contient directement l'id_client
        T : "N° Pièce" = "Facture 20250503"
        P : "Produits" = "N° 352 - Nom du vin"
        E : "Quantité"
    """

    fact = df_fact.copy()

    col_client = fact.columns[13]  # N
    col_piece = fact.columns[19]   # T
    col_produit = fact.columns[15] # P
    col_qte = fact.columns[4]      # E

    hist = pd.DataFrame()
    hist["id_client_raw"] = fact[col_client]
    hist["id_commande_raw"] = fact[col_piece]
    hist["id_produit_raw"] = fact[col_produit]
    hist["quantite"] = fact[col_qte]

    def parse_client(x):
        if pd.isna(x):
            return None
        try:
            return int(str(x).strip())
        except Exception:
            return str(x).strip()

    hist["id_client"] = hist["id_client_raw"].apply(parse_client)

    def parse_commande(x):
        if pd.isna(x):
            return None
        s = str(x)
        if "Facture" in s:
            return s.split("Facture", 1)[1].strip()
        return s.strip()

    hist["id_commande"] = hist["id_commande_raw"].apply(parse_commande)

    def parse_produit(x):
        if pd.isna(x):
            return None
        s = str(x)
        m = re.search(r"N°\s*(\d+)", s)
        if m:
            return int(m.group(1))
        try:
            return int(s.strip())
        except Exception:
            return None

    hist["id_produit"] = hist["id_produit_raw"].apply(parse_produit)

    def parse_qte(x):
        try:
            return int(x)
        except Exception:
            try:
                return float(x)
            except Exception:
                return 0

    hist["quantite"] = hist["quantite"].apply(parse_qte)

    hist_std = hist[["id_client", "id_commande", "id_produit", "quantite"]].dropna(
        subset=["id_client", "id_commande", "id_produit"]
    )

    return hist_std


# ---------- IA GROQ (LLAMA 3.3) ----------

@st.cache_resource
def get_groq_client():
    api_key = st.secrets.get("GROQ_API_KEY", None)
    if not api_key:
        st.warning("Aucune clé GROQ_API_KEY trouvée dans les secrets Streamlit.")
        return None
    return Groq(api_key=api_key)


def construire_profil_simplifie_depuis_texte(question: str) -> dict:
    """
    Interprétation très simple : couleur + budget.
    Le gros du travail reste côté modèle.
    """
    q = question.lower()

    couleur = None
    if "rouge" in q:
        couleur = "Rouge"
    elif "blanc" in q:
        couleur = "Blanc"
    elif "rosé" in q or "rose" in q:
        couleur = "Rosé"

    numbers = re.findall(r"\d+", q)
    prix_min = None
    prix_max = None
    if numbers:
        ref = float(numbers[0])
        prix_min = max(0, ref - 5)
        prix_max = ref + 5
    else:
        # Sans précision, on reste sous 35 €
        prix_min = 0
        prix_max = 35

    return {
        "couleur": couleur,
        "prix_min": prix_min,
        "prix_max": prix_max,
    }


def filtrer_candidats(
    catalogue: pd.DataFrame,
    profil: dict,
    max_vins: int = 30,
    question_raw: str = ""
) -> list:
    """
    Filtre rapide côté Python pour limiter ce qu'on envoie à l'IA.
    On renvoie une liste de dicts JSON-sérialisables.

    Logique :
    - Si l'utilisateur fait une recherche précise (appellation, domaine, nom de vin,
      ou hiérarchie type 1er cru / grand cru) SANS mention de prix → on ne filtre PAS
      sur le prix et on restreint le catalogue aux vins qui correspondent.
    - Sinon :
        - on applique éventuellement la couleur,
        - et le filtre prix basé sur profil (prix_min / prix_max),
        - puis on réduit si besoin le nombre de vins.
    """
    df = catalogue.copy()

    # 1) Filtre couleur si renseignée
    if profil.get("couleur"):
        df = df[df["Couleur"].str.lower() == profil["couleur"].lower()]

    # 2) Détection d'une recherche "précise"
    question = (question_raw or "").lower()

    # Mots de la question (lettres uniquement)
    tokens = re.findall(r"[a-zàâçéèêëîïôûùüÿñæœ]+", question)

    # Mots très génériques à ignorer
    ignore = {"rouge", "blanc", "rose", "rosé", "vin", "vins", "bouteille", "bouteilles", "vos", "votre", "quels", "quelles"}
    tokens_significatifs = [t for t in tokens if len(t) >= 4 and t not in ignore]

    cuvee_series = df.get("Cuvee", pd.Series([""] * len(df)))
    mention_series = df.get("Mention_Valorisante", pd.Series([""] * len(df)))

    champ_concat = (
        df["Produit"].fillna("") + " " +
        df["Famille"].fillna("") + " " +
        df["SousFamille"].fillna("") + " " +
        cuvee_series.fillna("") + " " +
        mention_series.fillna("")
    ).str.lower()

    # Ajout de synonymes pour 1er cru / grand cru
    search_terms = list(tokens_significatifs)
    if "premier" in tokens or "premiers" in tokens:
        search_terms.append("1er cru")
    if "grand" in tokens and "cru" in tokens:
        search_terms.append("grand cru")

    recherche_precise = False
    if search_terms:
        mask = pd.Series(False, index=df.index)
        for tok in search_terms:
            mask = mask | champ_concat.str.contains(tok)
        if mask.any():
            df = df[mask]
            recherche_precise = True

    # 3) Présence d'un prix explicite dans la question ?
    has_number = bool(re.findall(r"\d+", question))

    # On n'applique PAS de filtre prix si :
    # - recherche précise trouvée
    # - ET pas de prix explicite
    appliquer_filtre_prix = not (recherche_precise and not has_number)

    # 4) Filtre prix si applicable
    if appliquer_filtre_prix:
        pm = profil.get("prix_min")
        px = profil.get("prix_max")
        if pm is not None and px is not None:
            df = df[(df["Prix_TTC"] >= pm) & (df["Prix_TTC"] <= px)]

    # 5) Si après tout ça on n'a rien, fallback sur couleur+prix
    if df.shape[0] == 0:
        df = catalogue.copy()
        if profil.get("couleur"):
            df = df[df["Couleur"].str.lower() == profil["couleur"].lower()]
        pm = profil.get("prix_min")
        px = profil.get("prix_max")
        if pm is not None and px is not None:
            df = df[(df["Prix_TTC"] >= pm) & (df["Prix_TTC"] <= px)]

    # 6) Limiter le nombre de vins envoyés à l'IA
    #    Sauf en cas de recherche précise => on laisse TOUT pour que l'IA liste tous les Meursault / Rully, etc.
    if df.shape[0] > max_vins and not recherche_precise:
        df = df.sample(max_vins, random_state=42)

    champs = [
        "id_produit", "Produit", "Millesime", "Prix_TTC",
        "Couleur", "Famille", "SousFamille", "Corps",
        "Arome1", "Arome2", "Culture", "Coup_de_Coeur",
        "Mention_Valorisante", "Cuvee", "Description_commerciale"
    ]

    vins = []
    for _, row in df.iterrows():
        obj = {}
        for c in champs:
            if c in df.columns:
                val = row.get(c, None)
                if isinstance(val, (pd.Timestamp, pd.NaT.__class__)):
                    val = str(val)
                obj[c] = val
        vins.append(obj)

    return vins


def appeler_sommelier_ia(question: str, catalogue: pd.DataFrame, conversation_history=None) -> str:
    """
    conversation_history = liste de messages :
    [{"role": "user"/"assistant", "content": "..."}]
    Utilisé pour donner du contexte à l'IA.
    """
    client = get_groq_client()
    if client is None:
        return "L'IA n'est pas configurée (clé GROQ_API_KEY manquante dans les secrets Streamlit)."

    history_text = ""
    if conversation_history:
        for msg in conversation_history:
            role = "Client" if msg["role"] == "user" else "Sommelier"
            history_text += f"{role} : {msg['content']}\n"

    profil = construire_profil_simplifie_depuis_texte(question)
    candidats = filtrer_candidats(
        catalogue,
        profil,
        max_vins=30,
        question_raw=question
    )
    vins_json = json.dumps(candidats, ensure_ascii=False)
    profil_json = json.dumps(profil, ensure_ascii=False)

    system_prompt = """
Tu es **Mon Sommelier LR&LB**, l’assistant officiel de La Robe & Le Bouquet.  
La robe et le bouquet est un societe de négoce de vin spécialisé en Bourgogne qui vend aussi quelques vins d'autres régions
Nous proposons des vins sélectionnés pour leur excellent, rapport qualité, prix, tout en étant représentatif de leur appellation
Nous avons des marges reduites pour proposer des vins à prix d'amis.
Tu te comportes comme un **sommelier-caviste professionnel**, chaleureux, expert, simple et passionné.  
Ton rôle est d’aider chaque client à choisir un vin **uniquement parmi le catalogue LR&LB fourni en JSON**.

=====================================================================
🔴 RÈGLE FONDAMENTALE — ANTI-INVENTION
=====================================================================
Tu ne dois jamais inventer :
- un vin,
- une cuvée,
- un domaine,
- une appellation,
- un millésime,
- un prix,
- une caractéristique absente du JSON.

Tu ne recommandes que les vins figurant dans la liste JSON fournie.  
Tu reprends **exactement** le champ `Produit` sans modification.

Tu peux utiliser tes connaissances générales en vin, mais uniquement pour :
- expliquer une appellation,
- décrire un cépage,
- décrire une texture ou un style,
- décrire des accords mets-vins,
- interpréter les commentaires du client (“juteux”, “tendu”, “minéral”, “longue caudalie”…).

Tu n’ajoutes jamais un vin extérieur, même si tes connaissances te disent qu’il existe.

=====================================================================
🟩 UTILISATION DES CONNAISSANCES ŒNOLOGIQUES (libérée mais contrôlée)
=====================================================================
Tu peux utiliser pleinement ta culture vin pour :
- expliquer ce qu’on attend d’un Rully, Mâcon, Saint-Joseph, Chablis, etc.,
- expliquer les cépages (Pinot Noir, Chardonnay, Gamay, Syrah…),
- commenter les textures : ample, tendu, juteux, rond, soyeux, velouté, structuré,
- expliquer la caudalie (longueur en bouche),
- comprendre ce que veut dire “gourmand”, “minéral”, “fruité”, “complexe”, “solaire”, “élégant”,
- faire des accords mets-vins cohérents,
- analyser la demande du client en langage sommelier.

Mais :
- tu ne modifies jamais les données d’un vin du catalogue,
- tu ne mens jamais sur un vin,
- tu ne cites jamais une info factuelle absente du JSON.

=====================================================================
🟦 ARÔMES & STYLE (règles LR&LB)
=====================================================================
Chaque vin possède exactement **deux arômes officiels** : `Arome1` et `Arome2`.  
Tu dois :
- utiliser uniquement ces deux arômes comme références,
- ne jamais en inventer un troisième,
- ne jamais remplacer un arôme par un autre,
- intégrer les arômes avec naturel dans ton texte.

Tu peux compléter avec :
- texture (rond, vif, ample, juteux…),
- sensations (minéralité, fraîcheur, finesse…),
à condition que cela soit cohérent avec le style général du vin.

=====================================================================
🟨 LOGIQUE BUDGÉTAIRE LR&LB
=====================================================================
- Sans précision → vins **≤ 35 €**.  
- “Petit budget” / “pas cher” → **≤ 15 €**.  
- Si un prix est donné (ex. 25 €) → viser au plus près de ce montant sans dépasser.  
- Si fourchette → viser le haut de la fourchette.  
- Si l’utilisateur ne parle pas de budget → rester subtil, ne pas poser la question directement sauf si la demande l’exige.

=====================================================================
🟫 COMPORTEMENT CAVISTE-CONSEIL (complet)
=====================================================================
Tu fonctionnes comme un caviste en boutique :

1) **Commencer par écouter**  
Si la demande est claire → tu ne poses pas de questions inutiles.  
Si elle est floue → tu poses **maximum 2 questions** (couleur / corps / occasion / budget).

2) **Analyser intelligemment** ce que dit le client  
Tu interprètes naturellement :
- style implicite,
- occasion,
- arômes recherchés,
- niveau de puissance,
- niveau de prix,
- contexte du repas.

3) **Proposer rapidement**  
Toujours proposer 2 à 3 vins dès que possible.  
Ne jamais bloquer le client dans une suite de questions.

4) **Conseiller avec pédagogie**  
Tu expliques simplement et joliment :
- le style général,
- la texture en bouche,
- les arômes (Arome1 & Arome2),
- ce qui fait la personnalité du vin.

5) **Ton humain, professionnel, chaleureux**  
Tu écris comme un vrai caviste :
- naturel,  
- souriant dans le ton,  
- jamais scolaire,  
- jamais trop technique sauf si demandé,  
- jamais robotique (“ce vin est adapté car…” → ❌).

Préférer :
- « Voilà une jolie sélection… »
- « Celui-ci a vraiment de l’élégance… »
- « Une belle découverte dans ce registre… »

6) **Affiner ensuite**  
Après les premiers vins :
- proposer de préciser (puissance, fruité, garde, région…),
- ne pas reposer les mêmes questions.

=====================================================================
🟪 SI UN PROFIL CLIENT (HISTORIQUE) EST FOURNI
=====================================================================
(Version actuelle : l'historique réel n'est pas encore transmis au modèle.)

Si le client parle de :
- « mes commandes »,
- « mon historique »,
- « analyse mes factures / mes commandes »,

tu dois :
1) lui expliquer clairement et simplement que, dans cette version, tu n'as pas accès directement à ses factures ou à ses commandes,
2) lui proposer de reconstituer son profil avec quelques questions simples (couleur, styles préférés, budget, régions aimées),
3) ensuite seulement proposer des vins en précisant que tu t'appuies sur ses réponses et sur le catalogue LR&LB.

=====================================================================
🟧 FORMAT FINAL DES RECOMMANDATIONS (nouvelle version naturelle)
=====================================================================
Pour chaque vin recommandé, écrire :

1) **Nom du vin – Domaine – Millésime – Prix_TTC € TTC**

Le champ `Produit` contient généralement le nom de l'appellation suivi du domaine, séparés par « - ».
Lorsque c'est possible, sépare et affiche :
- le nom du vin (partie avant le dernier " - "),
- le domaine (partie après le dernier " - "),
puis le millésime et le prix.

2) Une phrase de style (couleur, famille, texture, caractère)
3) Arômes : Arome1 & Arome2 intégrés naturellement
4) Une phrase “situationnelle” :
   - pourquoi ce vin peut plaire au client,
   - ou dans quel contexte il brillerait (repas, ambiance, style recherché)

Interdictions :
- pas de phrases robotisées,
- pas de répétitions,
- pas de “ce vin est adapté car…”.

Préférer :
- « Un rouge gourmand et juteux : idéal si vous aimez les vins fruités et accessibles. »
- « Un blanc floral et précis, parfait pour un dîner léger ou un apéritif élégant. »
- « Une belle bouteille si vous recherchez finesse et fraîcheur. »

Dans les demandes classiques (choix de vin par goût/budget/occasion), limite-toi en général à **3 à 5 vins**.
Si en revanche le client demande explicitement :
- « Quels sont vos Meursault ? »
- « Quels sont vos Rully / Ladoix ? »
- « Quels sont vos premiers crus / grands crus ? »
alors tu peux lister **tous les vins correspondants** présents dans la liste JSON, même s'ils sont plus nombreux.

=====================================================================
🟦 CONVERSATION MULTI-TOURS
=====================================================================
- Tu gardes en mémoire ce qui a été dit,
- tu évites les redites,
- tu enrichis progressivement,
- tu restes cohérent avec les réponses précédentes,
- tu ne questionnes jamais plus de 2 fois de suite.

=====================================================================
🟩 TON FINAL DE CHAQUE RÉPONSE
=====================================================================
Toujours finir par une invitation douce à continuer :
- « Souhaitez-vous que je vous propose quelque chose de plus puissant ? »
- « Voulez-vous explorer une autre région ? »
- « On peut affiner si vous le souhaitez. »
- « Vous voulez rester dans ce style ou aller vers quelque chose de plus marqué ? »

=====================================================================
FIN DU PROMPT
=====================
"""

    user_prompt = f"""
Historique de la conversation (client / sommelier) :
{history_text}

Dernière demande du client :
{question}

Profil interprété (couleur, budget approximatif) :
{profil_json}

Voici une liste de vins du catalogue LR&LB (JSON) :

{vins_json}

À partir de cette liste uniquement :
- choisis des vins adaptés à la demande,
- présente chaque vin sur 3 à 5 lignes :
    1) Nom du vin – Domaine – Millésime – Prix_TTC € TTC
    2) Style (couleur, région/famille, corps)
    3) Arômes (Arome1, Arome2) et éventuellement un commentaire sur la texture / le style
    4) Une phrase naturelle sur pourquoi ce vin peut plaire ou dans quel contexte il brille
- adapte le nombre de vins : 3 à 5 en recommandation classique, tous les vins correspondants si le client demande « quels sont vos X ? ».
- termine par une phrase proposant d’affiner (plus de puissance, autre région, autre budget, etc.).
"""

    completion = client.chat.completions.create(
        model="llama-3.3-70b-versatile",
        messages=[
            {"role": "system", "content": system_prompt.strip()},
            {"role": "user", "content": user_prompt.strip()},
        ],
        temperature=0.4,
        max_tokens=1500,
    )

    return completion.choices[0].message.content


# ---------- UI PRINCIPALE (CHAT UNIQUEMENT) ----------

def main():
    st.title("🍷 Mon Sommelier – La Robe et Le Bouquet")

    # ----- Sidebar : état des données + reset -----
    with st.sidebar:
        st.header("Données LR&LB")

        df_pictos = None
        df_ca = None
        df_prod = None
        df_fact = None

        try:
            df_pictos = load_pictos()
            st.success(f"Pictos : {df_pictos.shape[0]} lignes")
        except Exception as e:
            st.error(f"Erreur Pictos.xlsx : {e}")

        try:
            df_ca = load_corps_aromes()
            st.success(f"Corps & arômes : {df_ca.shape[0]} lignes")
        except Exception as e:
            st.error(f"Erreur Corps et aromes.xlsx : {e}")

        try:
            df_prod = load_export_produits()
            st.success(f"Produits : {df_prod.shape[0]} lignes")
        except Exception as e:
            st.error(f"Erreur Export produits brut.xlsx : {e}")

        try:
            df_fact = load_export_facture()
            st.success(f"Factures : {df_fact.shape[0]} lignes")
        except Exception as e:
            st.error(f"Erreur Export Facture Brut.xlsx : {e}")

        if st.button("🔁 Réinitialiser la conversation"):
            st.session_state["messages"] = []
            st.experimental_rerun()

    # ----- Construction catalogue / historique -----
    catalogue = None
    historique = None

    if df_prod is not None and df_ca is not None:
        catalogue = construire_catalogue(df_prod, df_ca)

    if df_fact is not None:
        historique = construire_historique(df_fact)  # prêt pour une future V2 "mode facture"

    if catalogue is None or catalogue.empty:
        st.error("Le catalogue n'est pas disponible. Impossible d'activer le sommelier.")
        return

    st.markdown(
        """
Parlez avec votre sommelier LR&LB 👇  
Expliquez vos goûts, votre budget, l'occasion, ou demandez un accord met/vin.
        """
    )

    # ----- Historique de conversation -----
    if "messages" not in st.session_state:
        st.session_state["messages"] = []

    # Afficher les messages existants
    for msg in st.session_state["messages"]:
        with st.chat_message("user" if msg["role"] == "user" else "assistant"):
            st.markdown(msg["content"])

    # Saisie utilisateur
    question = st.chat_input("Que recherchez-vous comme vin aujourd'hui ?")

    if question:
        # Ajout du message utilisateur
        st.session_state["messages"].append({"role": "user", "content": question})

        # Affichage immédiat
        with st.chat_message("user"):
            st.markdown(question)

        # Historique avant cette question (pour le contexte IA)
        history_before = st.session_state["messages"][:-1]

        # Réponse IA
        with st.chat_message("assistant"):
            with st.spinner("Le sommelier LR&LB réfléchit à partir de votre demande et du catalogue..."):
                try:
                    reponse = appeler_sommelier_ia(
                        question=question,
                        catalogue=catalogue,
                        conversation_history=history_before
                    )
                    st.markdown(reponse)
                except Exception as e:
                    reponse = f"Erreur lors de l'appel à l'IA : {e}"
                    st.error(reponse)

        # Ajout de la réponse dans l'historique
        st.session_state["messages"].append({"role": "assistant", "content": reponse})


if __name__ == "__main__":
    main()
