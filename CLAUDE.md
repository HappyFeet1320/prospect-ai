# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Running the Application

```bash
streamlit run app.py
# or on Windows:
run.bat
```

Access at http://localhost:8501.

## Environment Setup

Copy `.env.example` to `.env` and fill in:
```env
# LLM provider (required — pick one):
LLM_PROVIDER=groq
GROQ_API_KEY=gsk_...

# or:
LLM_PROVIDER=anthropic
ANTHROPIC_API_KEY=sk-ant-...

# CBE API (optional but recommended for Phase 4 contact enrichment):
CBEAPI_KEY=...   # free key at https://cbeapi.be
```

## Architecture Overview

5-phase sequential pipeline for Belgian job opportunity discovery.
Each phase validates and saves to SQLite before the next unlocks.

### Data Flow
```
Free text input
  → [Phase 1] LLM extraction → Session.operator_profile_json
               (NACE codes 4-digit, postal codes, skills)
  → [Phase 2] KBO SQLite index (NACE LIKE "xxxx%") → Company table (phase2_data_json)
               Alternative sources: CBE API (by postal code) | Mock (tests)
  → [Phase 3] 3-criteria scoring (sectoral 40% + geo 30% + structural 30%)
               → Company.phase3_score / is_phase3_selected
  → [Phase 4] Enrichment pipeline per company:
               0. CBE API GET /company/{bce} → email, phone, website (official)
               1. Web scraping (About, Careers pages)
               2. DuckDuckGo parallel searches (news, jobs, managers, financial)
               3. LLM synthesis → Company.phase4_data_json + DecisionMaker table
  → [Phase 5] LLM kit generation → PreparationKit table + .txt export
```

### Key Files

| File | Role |
|------|------|
| `app.py` | Streamlit entry point: session management, sidebar, phase routing |
| `config/settings.py` | All settings via `.env`; properties `has_llm_key`, `has_cbeapi_key`, `active_model` |
| `database/models.py` | 4 ORM tables: `Session`, `Company`, `DecisionMaker`, `PreparationKit` |
| `utils/llm_client.py` | LLM abstraction: `call_with_json_tool(system, user, tool_name, tool_schema)` |
| `phases/phase2/kbo_reader.py` | Builds 668 MB SQLite index from KBO CSVs (~90s one-time) |
| `phases/phase2/cbeapi_client.py` | CBE API client: `fetch_company_by_bce()` (Phase 4) + `search_by_postal_codes()` (Phase 2) |
| `phases/phase3/scorer.py` | Scoring engine: 3 weighted criteria → float 0–1 |
| `phases/phase4/enricher.py` | Full enrichment: CBE API + scraping + DDG + LLM → 5-block dossier |
| `ui/phase{1-5}_page.py` | Streamlit UI for each phase |

### LLM Abstraction

All LLM calls go through `utils/llm_client.py`:
```python
result_dict, usage_dict = call_with_json_tool(system, user, tool_name, tool_schema)
```
- Groq: `parameters` format; `_clean_schema_for_groq()` strips unsupported `minItems`/`maxItems`
- Anthropic: `input_schema` format (native JSON Schema)
- Both use forced `tool_choice` for guaranteed structured output

### Database Patterns

JSON columns use `@property` getter/setter on models:
```python
# Read:  company.phase4_data  → dict
# Write: company.phase4_data = {...}  → serializes to JSON string
```
All `*_json` text columns have corresponding property accessors.

### Streamlit State Convention

`st.session_state["p{N}_step"]` = `"input"` | `"review"` | `"validated"`
Phase 1 also has `"follow_up"`.

Progress callbacks for long operations:
```python
run_phase_X(session_id, progress_callback=lambda name, current, total, status: ...)
```

---

## Phase 2 — Company Search

**Source selection** via `source` parameter in `run_phase2()`:

| Source | Description | Speed | NACE filter |
|--------|-------------|-------|-------------|
| `"kbo"` | Local SQLite index from KBO CSVs (recommended) | ~1s | ✅ Native |
| `"cbe_api"` | CBE API by postal code (fresh data + contacts) | ~30-60s | ❌ Post-filter |
| `"mock"` | Fictional companies for testing | instant | ✅ |

- KBO CSVs → `KBO_DATA_DIR` (default: `KboOpenData_0242_2026_01_15_Full/`)
- First run: `build_index()` → `data/kbo_index.db` (~90s, one-time)
- **NACE codes**: KBO uses 5 digits (`"62010"`), profile uses 4 digits → search uses `LIKE "6201%"`
- CBE API searches by `post_code` only; Phase 3 does the NACE filtering

---

## Phase 3 — Scoring Thresholds

Configurable in `.env`:
- `PHASE3_MIN_SCORE=0.45` (primary threshold)
- `PHASE3_MIN_SCORE_FALLBACK=0.35` (fallback if < 15 companies pass primary)
- `PHASE3_TARGET_COMPANIES=100` (top N selected)

---

## Phase 4 — Enrichment

### EnrichConfig presets (phases/phase4/enricher.py)

```python
EnrichConfig.rapide()       # CBE API only — ~2-5s/company (DEFAULT)
EnrichConfig.standard()     # CBE + web scraping + DDG — ~30-45s/company
EnrichConfig.complet()      # All sources + LinkedIn + financial — ~60-90s/company
EnrichConfig.web_seulement()# Web + DDG, no CBE API
```

### CBE API in Phase 4
- `fetch_company_by_bce(bce_number)` → `{email, phone, website, denomination, legal_form, start_date, nace_descriptions}`
- Called as step 0 before any web search
- Returns `None` if `CBEAPI_KEY` missing, 404, or network error (graceful degradation)
- BCE number format: accepts `"0773.453.366"` or `"0773453366"` (dots stripped automatically)

---

## CBE API (phases/phase2/cbeapi_client.py)

- Base URL: `https://cbeapi.be/api/v1` — Auth: `Bearer CBEAPI_KEY`
- Rate limit: **2 500 requests/day** (free tier), delay 0.25s between calls
- Per-page: 25 results (fixed by API)
- NACE codes in API response: 5 digits → truncate to 4 to match profile
- Company status: accept both `"actif"` and `"active"` as active

**Key functions:**
```python
fetch_company_by_bce(bce_number)        # Phase 4: enrich one company
search_by_postal_codes(...)             # Phase 2: bulk search by postal code
test_cbeapi_connection()                # → (bool, str) connectivity test
```

**Endpoint used for enrichment:**
```
GET /v1/company/{cbeNumber}?lang=fr
```
Accepts formats: `"0123456789"`, `"0123.456.789"`, `"BE0123456789"`

---

## Phase 5 — Eligibility

Companies eligible for kit generation: `is_selected=True` OR `operator_rating >= 3`.

---

## Language

UI text and code comments are in **French**.
