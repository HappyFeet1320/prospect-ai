"""
Lecteur KBO Open Data — construit un index SQLite depuis les CSV officiels.

Opération en 2 temps :
  1. build_index()  — une seule fois (~3-6 min selon la machine)
  2. search_by_nace() — instantané ensuite

Structure des CSV KBO :
  enterprise.csv   → numéro BCE, statut, forme juridique, date de début
  denomination.csv → noms (langue, type)
  address.csv      → adresses (code postal, commune)
  activity.csv     → codes NACE (35 M lignes — filtrés par entreprises actives)
  code.csv         → libellés des formes juridiques
"""

from __future__ import annotations

import csv
import json
import sqlite3
from pathlib import Path

from loguru import logger

from config.settings import settings

# ============================================================
# Chemins
# ============================================================

KBO_INDEX_PATH = settings.data_dir / "kbo_index.db"


def get_kbo_data_dir() -> Path | None:
    """Retourne le dossier KBO configuré, ou None s'il n'est pas défini."""
    raw = getattr(settings, "KBO_DATA_DIR", "")
    if not raw:
        return None
    p = Path(raw)
    return p if p.is_dir() else None


def is_index_built() -> bool:
    """True si l'index SQLite existe et est non-vide."""
    return KBO_INDEX_PATH.exists() and KBO_INDEX_PATH.stat().st_size > 500_000


# ============================================================
# Construction de l'index
# ============================================================

def build_index(progress_callback=None) -> dict:
    """
    Lit les CSV KBO et construit l'index SQLite.

    Args:
        progress_callback: fn(step: str, current: int, total: int)
                           appelée pendant la construction.

    Returns:
        dict avec stats (nb_enterprises, nb_nace, etc.)
    """
    kbo_dir = get_kbo_data_dir()
    if kbo_dir is None:
        raise RuntimeError(
            "KBO_DATA_DIR non configuré dans .env ou dossier introuvable. "
            "Renseignez le chemin du dossier KBO Open Data."
        )

    logger.info("Construction de l'index KBO depuis {}", kbo_dir)
    KBO_INDEX_PATH.parent.mkdir(parents=True, exist_ok=True)

    # Supprimer l'ancien index si incomplet
    if KBO_INDEX_PATH.exists():
        KBO_INDEX_PATH.unlink()

    con = sqlite3.connect(str(KBO_INDEX_PATH))
    con.execute("PRAGMA journal_mode=WAL")
    con.execute("PRAGMA synchronous=NORMAL")
    con.execute("PRAGMA cache_size=-64000")  # 64 MB

    _create_tables(con)

    stats = {}

    # ── 1. Formes juridiques (code.csv) ───────────────────────
    jf_labels = _load_juridical_forms(kbo_dir / "code.csv")

    # ── 2. Entreprises actives (enterprise.csv) ───────────────
    _report(progress_callback, "entreprises", 0, 0)
    active_numbers, nb_ent = _load_enterprises(con, kbo_dir / "enterprise.csv", jf_labels, progress_callback)
    stats["nb_enterprises"] = nb_ent
    logger.info("Entreprises actives indexées : {}", nb_ent)

    # ── 3. Dénominations (denomination.csv) ───────────────────
    _report(progress_callback, "dénominations", 0, 0)
    _load_denominations(con, kbo_dir / "denomination.csv", active_numbers, progress_callback)
    logger.info("Dénominations chargées")

    # ── 4. Adresses (address.csv) ─────────────────────────────
    _report(progress_callback, "adresses", 0, 0)
    _load_addresses(con, kbo_dir / "address.csv", active_numbers, progress_callback)
    logger.info("Adresses chargées")

    # ── 5. Codes NACE (activity.csv — fichier lourd) ──────────
    _report(progress_callback, "activités NACE", 0, 0)
    nb_nace = _load_activities(con, kbo_dir / "activity.csv", active_numbers, progress_callback)
    stats["nb_nace"] = nb_nace
    logger.info("Codes NACE indexés : {}", nb_nace)

    # ── 6. Index SQL ──────────────────────────────────────────
    _report(progress_callback, "index SQL", 0, 1)
    con.execute("CREATE INDEX IF NOT EXISTS idx_nace_code ON nace_activities(nace_code)")
    con.execute("CREATE INDEX IF NOT EXISTS idx_nace_ent  ON nace_activities(enterprise_number)")
    con.commit()
    con.close()

    logger.success("Index KBO construit : {} entreprises, {} activités", nb_ent, nb_nace)
    return stats


# ── Helpers de construction ────────────────────────────────

def _create_tables(con: sqlite3.Connection) -> None:
    con.executescript("""
        CREATE TABLE enterprises (
            enterprise_number TEXT PRIMARY KEY,
            denomination      TEXT DEFAULT '',
            juridical_form    TEXT DEFAULT '',
            start_year        INTEGER,
            zipcode           TEXT DEFAULT '',
            municipality_fr   TEXT DEFAULT '',
            street_fr         TEXT DEFAULT '',
            house_number      TEXT DEFAULT ''
        );

        CREATE TABLE nace_activities (
            enterprise_number TEXT NOT NULL,
            nace_code         TEXT NOT NULL,
            nace_version      TEXT DEFAULT ''
        );
    """)


def _report(cb, step: str, current: int, total: int) -> None:
    if cb:
        try:
            cb(step, current, total)
        except Exception:
            pass


def _load_juridical_forms(path: Path) -> dict[str, str]:
    """Lit code.csv et retourne {code → libellé FR}."""
    forms: dict[str, str] = {}
    if not path.exists():
        return forms
    with open(path, encoding="utf-8", errors="replace") as f:
        for row in csv.DictReader(f):
            if row.get("Category") == "JuridicalForm" and row.get("Language") == "FR":
                forms[row["Code"]] = row["Description"]
    return forms


def _load_enterprises(
    con: sqlite3.Connection,
    path: Path,
    jf_labels: dict[str, str],
    progress_callback,
) -> tuple[set[str], int]:
    """Insère les entreprises actives. Retourne (set des numéros, count)."""
    active: set[str] = set()
    batch: list[tuple] = []
    BATCH = 20_000
    count = 0

    with open(path, encoding="utf-8", errors="replace") as f:
        for row in csv.DictReader(f):
            if row.get("Status") != "AC":
                continue
            num  = row["EnterpriseNumber"]
            jf   = jf_labels.get(row.get("JuridicalForm", ""), row.get("JuridicalForm", ""))
            year = _parse_year(row.get("StartDate", ""))
            active.add(num)
            batch.append((num, jf, year))
            count += 1

            if len(batch) >= BATCH:
                con.executemany(
                    "INSERT OR IGNORE INTO enterprises(enterprise_number, juridical_form, start_year)"
                    " VALUES (?, ?, ?)",
                    batch,
                )
                con.commit()
                batch.clear()
                _report(progress_callback, "entreprises", count, 0)

    if batch:
        con.executemany(
            "INSERT OR IGNORE INTO enterprises(enterprise_number, juridical_form, start_year)"
            " VALUES (?, ?, ?)",
            batch,
        )
        con.commit()

    return active, count


def _load_denominations(
    con: sqlite3.Connection,
    path: Path,
    active: set[str],
    progress_callback,
) -> None:
    """Met à jour enterprises.denomination avec le meilleur nom disponible."""
    # Priorité : language FR (2) > NL (1) > autre ; type 001 > 002 > autre
    best: dict[str, tuple[int, str]] = {}  # num → (priority, name)

    LANG_PRIO = {"2": 10, "1": 5, "3": 3, "4": 2, "0": 1}
    TYPE_PRIO = {"001": 3, "002": 2, "003": 1}

    count = 0
    with open(path, encoding="utf-8", errors="replace") as f:
        for row in csv.DictReader(f):
            num = row.get("EntityNumber", "")
            if num not in active:
                continue
            prio = LANG_PRIO.get(row.get("Language", ""), 0) * 10 + TYPE_PRIO.get(row.get("TypeOfDenomination", ""), 0)
            denom = row.get("Denomination", "").strip()
            if denom and prio > best.get(num, (0, ""))[0]:
                best[num] = (prio, denom)
            count += 1
            if count % 500_000 == 0:
                _report(progress_callback, "dénominations", count, 0)

    # Mise à jour batch
    updates = [(name, num) for num, (_, name) in best.items()]
    BATCH = 20_000
    for i in range(0, len(updates), BATCH):
        con.executemany("UPDATE enterprises SET denomination=? WHERE enterprise_number=?", updates[i:i+BATCH])
    con.commit()


def _load_addresses(
    con: sqlite3.Connection,
    path: Path,
    active: set[str],
    progress_callback,
) -> None:
    """Met à jour enterprises avec l'adresse du siège (REGO)."""
    updates: dict[str, tuple] = {}

    count = 0
    with open(path, encoding="utf-8", errors="replace") as f:
        for row in csv.DictReader(f):
            num = row.get("EntityNumber", "")
            if num not in active:
                continue
            addr_type = row.get("TypeOfAddress", "")
            if addr_type not in ("REGO", "BAET"):  # siège social ou autre
                continue
            # Préférer REGO sur BAET
            if num in updates and addr_type != "REGO":
                continue

            zipcode  = row.get("Zipcode", "").strip()
            muni_fr  = (row.get("MunicipalityFR") or row.get("MunicipalityNL") or "").strip()
            street   = (row.get("StreetFR") or row.get("StreetNL") or "").strip()
            house    = row.get("HouseNumber", "").strip()
            updates[num] = (zipcode, muni_fr, street, house)

            count += 1
            if count % 300_000 == 0:
                _report(progress_callback, "adresses", count, 0)

    upd_list = [(z, m, s, h, num) for num, (z, m, s, h) in updates.items()]
    BATCH = 20_000
    for i in range(0, len(upd_list), BATCH):
        con.executemany(
            "UPDATE enterprises SET zipcode=?, municipality_fr=?, street_fr=?, house_number=?"
            " WHERE enterprise_number=?",
            upd_list[i:i+BATCH],
        )
    con.commit()


def _load_activities(
    con: sqlite3.Connection,
    path: Path,
    active: set[str],
    progress_callback,
) -> int:
    """Insère les codes NACE pour les entreprises actives (fichier 35 M lignes)."""
    batch: list[tuple] = []
    BATCH = 50_000
    count = 0
    total_lines = 35_000_000  # estimation

    with open(path, encoding="utf-8", errors="replace") as f:
        for i, row in enumerate(csv.DictReader(f)):
            num = row.get("EntityNumber", "")
            if num not in active:
                continue
            nace = row.get("NaceCode", "").strip()
            ver  = row.get("NaceVersion", "").strip()
            if not nace:
                continue
            batch.append((num, nace, ver))
            count += 1

            if len(batch) >= BATCH:
                con.executemany(
                    "INSERT INTO nace_activities(enterprise_number, nace_code, nace_version)"
                    " VALUES (?, ?, ?)",
                    batch,
                )
                con.commit()
                batch.clear()
                if i % 1_000_000 == 0:
                    _report(progress_callback, "activités NACE", i, total_lines)

    if batch:
        con.executemany(
            "INSERT INTO nace_activities(enterprise_number, nace_code, nace_version)"
            " VALUES (?, ?, ?)",
            batch,
        )
        con.commit()

    return count


def _parse_year(date_str: str) -> int | None:
    """Extrait l'année depuis 'DD-MM-YYYY' ou 'YYYY-MM-DD'."""
    if not date_str:
        return None
    parts = date_str.replace("/", "-").split("-")
    for p in parts:
        if len(p) == 4 and p.isdigit():
            return int(p)
    return None


# ============================================================
# Recherche dans l'index
# ============================================================

def search_by_nace(
    nace_code: str,
    max_results: int = 500,
    postal_codes: list[str] | None = None,
) -> list[dict]:
    """
    Recherche les entreprises actives par code NACE dans l'index SQLite.

    Args:
        nace_code:    Code NACE exact (ex: "6201") ou préfixe (ex: "62").
        max_results:  Nombre max de résultats.
        postal_codes: Filtrer par codes postaux (optionnel).

    Returns:
        Liste de dicts entreprises, triée par start_year desc.
    """
    if not is_index_built():
        raise RuntimeError("L'index KBO n'est pas encore construit. Lancez build_index() d'abord.")

    con = sqlite3.connect(str(KBO_INDEX_PATH))
    con.row_factory = sqlite3.Row

    # Les codes NACE dans le KBO ont 5 chiffres (ex: "62010")
    # tandis que nos profils utilisent 4 chiffres (ex: "6201").
    # On cherche toujours par préfixe : "6201" → LIKE "6201%"
    nace_filter = "n.nace_code LIKE ?"
    nace_param  = nace_code + "%"

    # Filtre géographique optionnel
    if postal_codes:
        placeholders = ",".join("?" * len(postal_codes))
        geo_filter   = f"AND e.zipcode IN ({placeholders})"
        geo_params   = postal_codes
    else:
        geo_filter = ""
        geo_params = []

    sql = f"""
        SELECT DISTINCT
            e.enterprise_number,
            e.denomination,
            e.juridical_form,
            e.start_year,
            e.zipcode,
            e.municipality_fr,
            e.street_fr,
            e.house_number,
            n.nace_code  AS nace_searched
        FROM nace_activities n
        JOIN enterprises e ON e.enterprise_number = n.enterprise_number
        WHERE {nace_filter}
          AND e.denomination != ''
          {geo_filter}
        ORDER BY e.start_year DESC NULLS LAST
        LIMIT ?
    """

    params = [nace_param] + geo_params + [max_results]
    rows   = con.execute(sql, params).fetchall()
    con.close()

    companies = []
    for r in rows:
        zipcode = r["zipcode"] or ""
        city    = r["municipality_fr"] or ""
        street  = r["street_fr"] or ""
        house   = r["house_number"] or ""
        addr    = f"{street} {house}, {zipcode} {city}".strip(", ")

        # Province approximative depuis code postal
        province = _zipcode_to_province(zipcode)

        companies.append({
            "bce_number":   r["enterprise_number"],
            "denomination": r["denomination"] or f"Entreprise {r['enterprise_number']}",
            "legal_form":   r["juridical_form"] or "",
            "postal_code":  zipcode,
            "city":         city,
            "province":     province,
            "address_raw":  addr,
            "creation_year": r["start_year"],
            "nace_searched": r["nace_searched"],
            "status":       "active",
            "source":       "kbo_opendata",
        })

    logger.info("KBO index — NACE={} → {} résultats", nace_code, len(companies))
    return companies


def search_by_nace_list(
    nace_codes: list[str],
    max_results: int = 2000,
) -> list[dict]:
    """
    Recherche toutes les entreprises actives possédant AU MOINS UN des codes NACE listés.

    Une seule requête SQL avec condition OR pour tous les codes → bien plus efficace
    que N requêtes séparées. Chaque entreprise est retournée UNE SEULE FOIS avec la
    liste complète de ses codes NACE correspondants parmi ceux recherchés.

    Triée par nombre de codes NACE correspondants décroissant (meilleure opportunité
    d'abord), puis par ancienneté.

    Args:
        nace_codes:   Liste de codes NACE 4 chiffres (ex: ["6201", "6202", "7010"]).
        max_results:  Nombre max d'entreprises retournées.

    Returns:
        Liste de dicts entreprises, chacune avec :
          - matched_nace_codes : list[str] — codes profil (4 chiffres) trouvés
          - matched_nace_count : int       — nombre de codes correspondants
    """
    if not nace_codes:
        return []
    if not is_index_built():
        raise RuntimeError("L'index KBO n'est pas encore construit. Lancez build_index() d'abord.")

    con = sqlite3.connect(str(KBO_INDEX_PATH))
    con.row_factory = sqlite3.Row

    # Construire les conditions LIKE : "6201" → nace_code LIKE '6201%'
    like_clauses = " OR ".join("n.nace_code LIKE ?" for _ in nace_codes)
    like_params  = [code.strip() + "%" for code in nace_codes]

    sql = f"""
        SELECT
            e.enterprise_number,
            e.denomination,
            e.juridical_form,
            e.start_year,
            e.zipcode,
            e.municipality_fr,
            e.street_fr,
            e.house_number,
            GROUP_CONCAT(DISTINCT n.nace_code) AS matched_kbo_codes_raw,
            COUNT(DISTINCT n.nace_code)         AS kbo_match_count
        FROM nace_activities n
        JOIN enterprises e ON e.enterprise_number = n.enterprise_number
        WHERE ({like_clauses})
          AND e.denomination != ''
        GROUP BY
            e.enterprise_number, e.denomination, e.juridical_form, e.start_year,
            e.zipcode, e.municipality_fr, e.street_fr, e.house_number
        ORDER BY kbo_match_count DESC, e.start_year DESC NULLS LAST
        LIMIT ?
    """

    params = like_params + [max_results]
    rows   = con.execute(sql, params).fetchall()
    con.close()

    profile_codes_set = {code.strip() for code in nace_codes}

    companies = []
    for r in rows:
        zipcode = r["zipcode"] or ""
        city    = r["municipality_fr"] or ""
        street  = r["street_fr"] or ""
        house   = r["house_number"] or ""
        addr    = f"{street} {house}, {zipcode} {city}".strip(", ")
        province = _zipcode_to_province(zipcode)

        # Mapper codes KBO (5 chiffres) → codes profil (4 chiffres)
        kbo_raw   = r["matched_kbo_codes_raw"] or ""
        kbo_codes = [c.strip() for c in kbo_raw.split(",") if c.strip()]
        matched   = sorted({kc[:4] for kc in kbo_codes if kc[:4] in profile_codes_set})

        companies.append({
            "bce_number":         r["enterprise_number"],
            "denomination":       r["denomination"] or f"Entreprise {r['enterprise_number']}",
            "legal_form":         r["juridical_form"] or "",
            "postal_code":        zipcode,
            "city":               city,
            "province":           province,
            "address_raw":        addr,
            "creation_year":      r["start_year"],
            "nace_searched":      matched[0] if matched else "",
            "matched_nace_codes": matched,
            "matched_nace_count": len(matched),
            "status":             "active",
            "source":             "kbo_opendata",
        })

    logger.info(
        "KBO batch — {} codes NACE → {} entreprises uniques",
        len(nace_codes), len(companies),
    )
    return companies


def get_index_stats() -> dict:
    """Retourne des statistiques sur l'index construit."""
    if not is_index_built():
        return {"built": False}
    con = sqlite3.connect(str(KBO_INDEX_PATH))
    nb_ent  = con.execute("SELECT COUNT(*) FROM enterprises").fetchone()[0]
    nb_nace = con.execute("SELECT COUNT(*) FROM nace_activities").fetchone()[0]
    nb_dist = con.execute("SELECT COUNT(DISTINCT nace_code) FROM nace_activities").fetchone()[0]
    con.close()
    size_mb = round(KBO_INDEX_PATH.stat().st_size / 1_048_576, 1)
    return {
        "built":        True,
        "nb_enterprises": nb_ent,
        "nb_nace":       nb_nace,
        "nb_distinct_nace": nb_dist,
        "size_mb":       size_mb,
    }


# ============================================================
# Code postal → Province (approximatif)
# ============================================================

def _zipcode_to_province(zipcode: str) -> str:
    """Déduit la province belge depuis le code postal."""
    z = zipcode.strip()
    if not z or not z.isdigit():
        return ""
    n = int(z)
    if 1000 <= n <= 1299:
        return "Bruxelles-Capitale"
    if 1300 <= n <= 1499:
        return "Brabant wallon"
    if 1500 <= n <= 1999:
        return "Brabant flamand"
    if 2000 <= n <= 2999:
        return "Anvers"
    if 3000 <= n <= 3499:
        return "Brabant flamand"
    if 3500 <= n <= 3999:
        return "Limbourg"
    if 4000 <= n <= 4999:
        return "Liège"
    if 5000 <= n <= 5999:
        return "Namur"
    if 6000 <= n <= 6599:
        return "Hainaut"
    if 6600 <= n <= 6999:
        return "Luxembourg"
    if 7000 <= n <= 7999:
        return "Hainaut"
    if 8000 <= n <= 8999:
        return "Flandre occidentale"
    if 9000 <= n <= 9999:
        return "Flandre orientale"
    return ""
