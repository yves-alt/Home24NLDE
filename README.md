# Home24 DE → NL Localization Engine

A production-grade, deterministic-first Dutch localization engine for Home24
product content. It is built to fail loudly rather than ship German: terminology
and Translation Memory do the bulk of the work, GPT (gpt-4o) only refines, and a
quality gate blocks export whenever German residue, lost data, or a changed model
name slips through.

## Architecture

Deterministic-first. GPT is a controlled refinement step, never the primary
translator, and **never silently falls back to the German source** — a failed or
incomplete GPT call flags the cell and blocks export.

**Pipeline per segment** (`engines/nl/localization_engine.py`):

1. Human-reviewed correction / glossary exact match
2. Spec terminology phrases (decor combos, compounds) — authoritative
3. Adaptive TM — exact, or a model-preserving *adaptation* (never a blind copy)
4. Terminology brain (full DE→NL map)
5. GPT (gpt-4o) — only when German still remains, with model names masked
6. Restore model names → abbreviations → terminology enforcement
7. Product-name engine (40-char limit, forbidden endings) for the `name` column

**Then, across all cells:**
- Multi-pass self-correction — re-fixes only the cells that fail the gate
- German residue gate (curated lexicon + ä/ö/ü/ß orthographic signal)
- Information-preservation validator (numbers, colors, model names, abbreviations)
- Final quality gate — export is allowed only when zero issues remain

### Key safeguards

- **Model-name protection** — likely model names ("Paku", "Fit Move II") are masked
  before TM/GPT and restored after; a lost or altered model name is a blocking error.
- **Adaptive TM** — `Tischleuchte Paku` matched against `Tischleuchte Ledo → Tafellamp
  Baldo` yields `Tafellamp Paku`, never the wrong model.
- **No black-box ML** — TF-IDF, KMeans clustering and the category classifier were
  removed; every decision is explainable.

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
OPENAI_MODEL=gpt-4o
TM_FUZZY_THRESHOLD=0.75
```

## Features

- **Translation Memory** — ~38k Home24 NL segments; exact + model-preserving adaptation
- **Terminology brain** — explainable DE→NL rule set (PART 11 Home24 vocabulary)
- **Dutch Glossary** — auto-built from TM, editable via UI; human review overrides GPT
- **Model-name protection** — model names are never translated, lost, or swapped
- **Residue gate** — no exported cell may contain German (ä/ö/ü/ß = hard blocker)
- **Information preservation** — numbers, dimensions, colors and models must survive
- **Abbreviation resolver** — MW → magnetron, BxHxT → B x H x D, 3er-Set → set van 3
- **Product-name engine** — 40-char limit, no brackets/commas, no forbidden endings
- **Multi-pass self-correction** — fixes only failing cells, then a final quality gate
- **Editable preview + learning loop** — edits are saved as HUMAN_REVIEW and reused
- **Export** — XLSX (keeps `name`) + UTF-8 CSV (optionally without `name`), prefixed `NL-<filename>`

## Project structure

```
app.py                       Main Streamlit entry point
database/
  database.py                SQLite connection manager
  migrations.py              Schema and indexes
engines/
  nl/                        Localization engine (deterministic-first)
    localization_engine.py   DutchLocalizationEngine — orchestrator
    terminology.py           Home24TerminologyBrain — DE→NL rule set
    model_protector.py       ModelNameProtector — mask/restore model names
    adaptive_tm.py           AdaptiveTranslationMemoryEngine — no blind copy
    abbreviations.py         DutchAbbreviationResolver
    segmentation.py          <br> / label segmentation
    product_name_engine.py   DutchProductNameEngine — name rules
    residue_gate.py          GermanResidueGateNL
    info_preservation.py     InformationPreservationValidator
    naturalness_refiner.py   DutchNaturalnessRefiner (gpt-4o, conservative)
    quality_gate.py          QualityGate — final pass/fail
    gpt_client.py            NLGptClient — gpt-4o, no silent German fallback
    types.py                 CellResult
  tm_matcher.py              TM search (TM browser UI)
  glossary_engine.py         DutchGlossaryManager
  residue_detector.py        Legacy QA-page residue tool
  qa_engine.py               Dutch QA validation (QA-page tool)
  phrase_memory.py           Seeded phrase memory
importers/
  tm_importer.py             Home24 TM Excel → SQLite
  glossary_importer.py       Glossary builder from TM
  excel_importer.py          Robust Excel workbook parser
  seed_glossary.py           Critical DE→NL vocabulary seed
exporters/
  xlsx_export.py             NL-*.xlsx export
  csv_export.py              UTF-8 CSV export (csv module; optional column exclude)
ui/
  pages/                     Dashboard, Translate, TM, Glossary, QA, Settings
  components/                Shared UI components
  styling/                   Custom CSS theme
tests/
  test_localization.py       Engine + component regression suite (PART 17)
```

## Tests

```bash
python3 -m pytest tests/ -q
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
