# Home24 DE → NL Localization Platform

A production-ready Dutch localization platform for Home24 product content.
Translates German product data to Dutch using Translation Memory, glossary matching, and GPT fallback.

## Architecture

Translation Memory is the source of truth. GPT is used only when the TM and glossary cannot resolve a segment.

**Pipeline per segment:**

1. Exact TM match (SQLite, indexed by normalized source)
2. Context engine (category-aware rules)
3. Dutch glossary lookup
4. RapidFuzz fuzzy match + TF-IDF semantic match
5. GPT fallback (gpt-4o-mini)

**Post-processing on every result:**
- Naturalness rewriter (German-literal → native Dutch)
- German residue detector and auto-cleanup
- Glossary enforcement
- Dutch QA validation
- Product name optimizer

## Requirements

- Python 3.11+
- OpenAI API key

## Installation

```bash
git clone https://github.com/yves-alt/Home24NLDE.git
cd Home24NLDE
pip install -r requirements.txt
cp .env.example .env
# Edit .env and add your OpenAI API key
```

## Running locally

```bash
streamlit run app.py
```

Open [http://localhost:8501](http://localhost:8501) in your browser.

## First-time setup

1. Go to **Settings → Import TM** and upload the Home24 Translation Memory export
2. The system builds the glossary automatically from TM data
3. Go to **Translate** and upload any German product Excel file

## Configuration

All secrets are loaded from `.env` (locally) or Streamlit secrets (deployed). Never hardcoded.

```
OPENAI_API_KEY=sk-...
APP_USER_EMAIL=your-email@home24.de
APP_USER_PASSWORD=your-password
OPENAI_MODEL=gpt-4o-mini
TM_FUZZY_THRESHOLD=0.75
```

## Features

- **Translation Memory** — 37,944 Home24 NL segments, exact and fuzzy matching
- **Dutch Glossary** — auto-built from TM, manually editable via UI
- **Consistency engine** — same German term always maps to same Dutch term within a workbook
- **QA engine** — detects and auto-corrects forbidden patterns, German residue, capitalization errors
- **Name optimizer** — ensures product names never end with prepositions or incomplete phrases
- **Segmentation** — clusters rows by category (kitchen, bathroom, sofa, lighting…) before translation
- **Confidence scoring** — labels every result: `EXACT_TM` / `FUZZY_TM` / `GLOSSARY` / `GPT` / `LOW_CONFIDENCE`
- **Export** — color-coded XLSX + UTF-8 CSV, prefixed `NL-<filename>`

## Project structure

```
app.py                       Main Streamlit entry point
database/
  database.py                SQLite connection manager
  migrations.py              Schema and indexes
engines/
  translation_engine.py      Translation orchestrator
  tm_matcher.py              Exact + fuzzy TM matching
  semantic_matcher.py        TF-IDF semantic matching
  fuzzy_matcher.py           RapidFuzz wrapper
  glossary_engine.py         DutchGlossaryManager
  consistency_engine.py      DutchWorkbookConsistencyEngine
  context_engine.py          Category-aware translation rules
  naturalness_rewriter.py    German-literal to native Dutch rewriter
  residue_detector.py        German residue detection and cleanup
  qa_engine.py               Dutch QA validation
  name_optimizer.py          Product name validator and optimizer
  segmentation_engine.py     Row clustering by category
  confidence_scorer.py       Confidence label and scoring
  row_clusterer.py           ML row clusterer (TF-IDF + KMeans)
importers/
  tm_importer.py             Home24 TM Excel → SQLite
  glossary_importer.py       Glossary builder from TM
  excel_importer.py          Robust Excel workbook parser
  seed_glossary.py           Critical DE→NL vocabulary seed
exporters/
  xlsx_export.py             Color-coded NL-*.xlsx export
  csv_export.py              UTF-8 CSV export
ui/
  pages/                     Dashboard, Translate, TM, Glossary, QA, Settings
  components/                Shared UI components
  styling/                   Custom CSS theme
tests/
  tm_tests.py
  qa_tests.py
  consistency_tests.py
  glossary_tests.py
```

## Tests

```bash
python3 tests/tm_tests.py
python3 tests/qa_tests.py
python3 tests/consistency_tests.py
python3 tests/glossary_tests.py
```

## Deployment

Compatible with Streamlit Cloud. Add secrets via the Streamlit dashboard:

```toml
OPENAI_API_KEY = "sk-..."
APP_USER_EMAIL = "your-email@home24.de"
APP_USER_PASSWORD = "your-password"
```

## Author

Yves Reuel Valery Koulle Banga
