# PROSPECT-AI

Agent intelligent de recherche d'opportunités professionnelles en Belgique.

## Démarrage rapide

### 1. Configuration

```bash
cp .env.example .env
# Éditez .env et ajoutez votre clé ANTHROPIC_API_KEY
```

### 2. Installation des dépendances

```bash
pip install -r requirements.txt
```

### 3. Lancement

```bash
streamlit run app.py
```

Ou sous Windows : double-cliquez sur `run.bat`

L'application sera accessible sur : http://localhost:8501

---

## Structure du projet

```
prospect-ai/
├── app.py                    # Point d'entrée Streamlit
├── requirements.txt
├── .env.example              # Template variables d'environnement
├── config/
│   └── settings.py           # Configuration centralisée
├── database/
│   ├── models.py             # Modèles SQLAlchemy
│   └── connection.py         # Connexion SQLite
├── phases/
│   ├── phase1/               # ✅ Profiling Opérateur (Claude API)
│   ├── phase2/               # 🚧 Recherche BCE/KBO
│   ├── phase3/               # 🚧 Scoring
│   ├── phase4/               # 🚧 Recherche Approfondie
│   └── phase5/               # 🚧 Préparation Entretien
├── ui/                       # Pages Streamlit par phase
├── utils/                    # Fonctions utilitaires
└── data/                     # Base SQLite (générée au lancement)
```

## Phases

| Phase | Nom | Statut |
|-------|-----|--------|
| P1 | Profiling Opérateur | ✅ Disponible |
| P2 | Recherche BCE/KBO | 🚧 En développement |
| P3 | Filtrage & Scoring | 🚧 En développement |
| P4 | Dossiers Entreprises | 🚧 En développement |
| P5 | Kit de Préparation | 🚧 En développement |

## APIs utilisées

- **Claude (Anthropic)** — Analyse profil, génération NACE, scoring IA
- **BCE/KBO** — Registre officiel des entreprises belges (public)
- **BNB** — Banque Nationale de Belgique (comptes annuels)
