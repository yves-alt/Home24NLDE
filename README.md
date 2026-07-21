# Home24 DE → NL Localization Engine

A production-grade, deterministic-first Dutch localization engine for Home24
product content. It is built to fail loudly rather than ship German: the
official DE→NL glossary and Translation Memory do the bulk of the work, GPT
only refines or fills genuine gaps, and a severity-classified quality gate
blocks export whenever a CRITICAL issue — German residue, lost data, a
changed model name, a malformed product name — slips through.

## Architecture

Deterministic-first. GPT is a controlled refinement step, never the primary
translator, and **never silently falls back to German** — a failed or
incomplete GPT call flags the cell and (unless later resolved) blocks export.

**Pipeline per segment** (`engines/nl/localization_engine.py`):

1. Human-reviewed correction / glossary exact match
2. Spec terminology phrases (decor combos, compounds) — authoritative
3. Adaptive TM — exact, or a model-preserving *adaptation* (never a blind copy)
4. Terminology brain — official DE→NL glossary + curated rules, merged
5. GPT — only when German still remains, with model names masked
6. Restore model names → abbreviations → terminology enforcement
7. Product-name compression engine (40-char limit) for the `name` column

**Then, across all cells:**
- Multi-pass self-correction — re-fixes only the cells that fail the gate
- Glossary compliance validation — checks the *finished* output against every
  approved term, not just what ran during translation
- File-level consistency harmonization — the same source in the same column
  converges on one target throughout a file
- Final quality gate — severity-classified (INFO/WARNING/CRITICAL); export is
  blocked only on CRITICAL, warnings are visible but non-blocking

### Key safeguards

- **Official glossary, authoritative** — ~14k DE→NL furniture terms imported
  via the Glossary page, split into colon-labels, `ProductType ModelName`
  patterns (fed to Translation Memory), and general vocabulary (fed to the
  terminology brain). Re-importing is idempotent.
- **Model-name protection** — likely model names ("Paku", "Fit Move II") are
  masked before TM/GPT and restored after; a lost, duplicated, or substituted
  model name is a CRITICAL, blocking error (`model_integrity.py`).
- **Adaptive TM** — `Tischleuchte Paku` matched against `Tischleuchte Ledo →
  Tafellamp Baldo` yields `Tafellamp Paku`, never the wrong model.
- **Dynamic column classification** — unknown German-prose columns (e.g.
  `careInstructions`) translate via a generic profile automatically;
  technical/protected columns pass through unchanged; genuinely ambiguous
  columns are surfaced for an explicit choice before translation starts. No
  non-empty column is ever silently skipped. Protected-header matching is
  normalized, so `Jira Key` / `JiraKey` / `jira_key` are recognized as the
  same column everywhere.
- **Product-name compression** — when a name exceeds 40 characters, several
  candidates are generated (connector compression, drop lowest-priority
  clause, principal-feature-only, GPT rewrite as a last resort) and scored;
  never a blind truncation. `opt.` is preserved when the source has it, or
  the loss is escalated to CRITICAL. Word-boundary truncation is the
  absolute last resort and always raises a CRITICAL review event.
- **No black-box ML** — every decision is explainable: regex/dictionary
  terminology, structural TM matching, rule-based name compression.

## Requirements

- Python 3.11+
- OpenAI API key (optional — the engine runs deterministic-only without one;
  cells that genuinely need GPT are flagged and block export until resolved)

## Installation

```bash
git clone git@github.com:yves-alt/Home24NLDE.git
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

1. Go to **Glossary → Import Official Glossary** and upload the DE→NL
   furniture glossary (two columns: German term, Dutch term)
2. Go to **Settings → Import TM** to additionally import a Translation Memory
   export, if you have one
3. Go to **Translate** and upload any German product Excel (`.xlsx` or `.xls`)

## Configuration

All secrets are loaded from `.env` (locally) or Streamlit secrets (deployed).
Never hardcoded. Three roles are supported — set the pairs you need:

```
OPENAI_API_KEY=sk-...
OPENAI_MODEL=gpt-4.1

ADMIN_EMAIL=you@home24.de
ADMIN_PASSWORD=...

JUSTUS_EMAIL=editor@home24.de      # role: editor
JUSTUS_PASSWORD=...

GAST_EMAIL=guest@home24.de          # role: guest (read-only)
GAST_PASSWORD=...
```

## Features

- **Official glossary** — ~14k-term DE→NL furniture glossary, authoritative
  over built-in rules on conflict; importable/re-importable from the UI
- **Translation Memory** — exact + model-preserving structural adaptation,
  never a blind fuzzy copy
- **Terminology brain** — DE→NL rule set merging curated defaults with the
  imported glossary; tokenizer-based matching, not per-term regex, so it
  stays fast at glossary scale
- **Dynamic column classification** — known/unknown/technical/protected/
  ambiguous, with an explicit review step for anything uncertain
- **Model-name protection & integrity** — model names are never translated,
  lost, duplicated, or swapped for another known model
- **Product-name compression engine** — multi-candidate, priority-scored
  40-character compression with a GPT last resort and structured
  removed-segment reporting; never a blind truncation
- **Residue gate** — no exported cell may contain German (curated lexicon +
  ä/ö/ü/ß orthographic signal + broad prose markers)
- **Post-translation glossary compliance** — the *finished* output is
  re-checked against every applicable approved term
- **Information preservation** — numbers, dimensions, colors, models,
  abbreviations, and `<br>` structure must survive; suspicious identical
  output and suspiciously short output are flagged
- **Consistency harmonization** — the same source in the same column
  converges on one target throughout a file
- **Severity-classified quality gate** — PASSED / PASSED WITH REVIEW
  WARNINGS / FAILED — CRITICAL ISSUES; only CRITICAL blocks export; a
  filterable review panel (by severity and category) with Excel highlighting
- **Translation coverage reconciliation** — non-empty source cells, protected
  cells, successful/failed/review-required counts must add up
- **Editable preview + learning loop** — edits are saved as HUMAN_REVIEW and
  reused, propagated to identical source segments in the same file
- **Export** — XLSX (keeps every column, review-highlighted) + UTF-8 CSV
  (always excludes `name` and `Jira Key`), prefixed `NL-<filename>`

## Project structure

```
app.py                       Main Streamlit entry point
database/
  database.py                SQLite connection manager
  migrations.py              Schema, indexes, additive column migrations
engines/
  nl/                        Localization engine (deterministic-first)
    localization_engine.py   DutchLocalizationEngine — orchestrator
    terminology.py           Home24TerminologyBrain — glossary + curated rules
    column_classifier.py     Dynamic column classification
    consistency_engine.py    File-level consistency harmonization
    glossary_validator.py    Post-translation glossary compliance
    model_protector.py       ModelNameProtector — mask/restore model names
    model_integrity.py       ModelNameIntegrityValidator
    adaptive_tm.py           AdaptiveTranslationMemoryEngine — no blind copy
    abbreviations.py         DutchAbbreviationResolver
    segmentation.py          <br> / label segmentation
    product_name_engine.py   Product-name compression engine
    residue_gate.py          GermanResidueGateNL
    info_preservation.py     InformationPreservationValidator
    naturalness_refiner.py   DutchNaturalnessRefiner (GPT, conservative)
    quality_gate.py          QualityGate — severity-classified pass/fail
    gpt_client.py            NLGptClient — no silent German fallback
    types.py                 CellResult, Severity, NameCompressionEvent
  glossary_engine.py         DutchGlossaryManager (Glossary page CRUD)
  phrase_memory.py           Unused legacy module — not wired into the
                              pipeline, kept for a future cleanup pass
  residue_detector.py        Unused legacy module — superseded by
                              engines/nl/residue_gate.py
importers/
  tm_importer.py             Home24 TM Excel/CSV → SQLite
  glossary_importer.py       Official glossary import + TM-derived builder
  excel_importer.py          Robust Excel workbook parser
  seed_glossary.py           Small curated DE→NL vocabulary seed
exporters/
  xlsx_export.py             NL-*.xlsx export, severity-highlighted
  csv_export.py              UTF-8 CSV export (csv module; excludes name/Jira Key)
ui/
  pages/                     Dashboard, Translate, TM, Glossary, QA, Settings
  components/                Shared UI components
  styling/                   Custom CSS theme
tests/
  conftest.py                Isolated test database (never the shared dev DB)
  test_localization.py       Engine + component regression suite
  test_product_name_engine.py, test_severity_gate.py, test_model_integrity.py,
  test_glossary_validator.py, test_column_classifier.py,
  test_consistency_engine.py, test_glossary_import.py
```

## Tests

```bash
python3 -m pytest tests/ -q
```

Tests run against an isolated SQLite database (`tests/conftest.py`), never
the shared development database — results don't depend on what's been
imported locally.

## Deployment

Compatible with Streamlit Cloud, deployed from `main`. Add secrets via the
Streamlit dashboard using the same keys as `.env` above.

## Author

Yves Reuel Valery Koulle Banga
