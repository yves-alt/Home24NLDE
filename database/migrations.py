from database.database import get_connection


SCHEMA = """
CREATE TABLE IF NOT EXISTS translation_memory (
    id              INTEGER PRIMARY KEY AUTOINCREMENT,
    source_segment  TEXT NOT NULL,
    target_segment  TEXT NOT NULL,
    normalized_source TEXT NOT NULL,
    normalized_target TEXT NOT NULL,
    frequency       INTEGER DEFAULT 0,
    category        TEXT DEFAULT 'general',
    confidence      REAL DEFAULT 1.0,
    created_at      TEXT,
    modified_at     TEXT,
    created_by      TEXT,
    source_id       INTEGER
);

CREATE INDEX IF NOT EXISTS idx_tm_normalized_source ON translation_memory(normalized_source);
CREATE INDEX IF NOT EXISTS idx_tm_frequency ON translation_memory(frequency DESC);
CREATE INDEX IF NOT EXISTS idx_tm_category ON translation_memory(category);

CREATE TABLE IF NOT EXISTS glossary (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    source_term TEXT NOT NULL,
    target_term TEXT NOT NULL,
    category    TEXT DEFAULT 'general',
    frequency   INTEGER DEFAULT 0,
    confidence  REAL DEFAULT 1.0,
    source_type TEXT DEFAULT 'TM',
    active      INTEGER DEFAULT 1,
    created_at  TEXT DEFAULT (datetime('now')),
    UNIQUE(source_term, target_term)
);

CREATE INDEX IF NOT EXISTS idx_glossary_source ON glossary(source_term);
CREATE INDEX IF NOT EXISTS idx_glossary_active ON glossary(active);

CREATE TABLE IF NOT EXISTS home24_nl_corpus (
    id              INTEGER PRIMARY KEY AUTOINCREMENT,
    category        TEXT NOT NULL,
    product_type    TEXT DEFAULT 'general',
    source          TEXT NOT NULL,
    text            TEXT NOT NULL,
    normalized_text TEXT NOT NULL,
    frequency       INTEGER DEFAULT 1,
    created_at      TEXT DEFAULT (datetime('now'))
);

CREATE INDEX IF NOT EXISTS idx_corpus_category    ON home24_nl_corpus(category);
CREATE INDEX IF NOT EXISTS idx_corpus_norm_text   ON home24_nl_corpus(normalized_text);
CREATE INDEX IF NOT EXISTS idx_corpus_product_type ON home24_nl_corpus(product_type);

CREATE TABLE IF NOT EXISTS phrase_memory (
    id              INTEGER PRIMARY KEY AUTOINCREMENT,
    source_phrase   TEXT NOT NULL,
    target_phrase   TEXT NOT NULL,
    normalized_src  TEXT NOT NULL,
    category        TEXT DEFAULT 'general',
    frequency       INTEGER DEFAULT 1,
    confidence      REAL DEFAULT 0.97,
    active          INTEGER DEFAULT 1,
    created_at      TEXT DEFAULT (datetime('now')),
    UNIQUE(source_phrase)
);

CREATE INDEX IF NOT EXISTS idx_phrase_norm_src ON phrase_memory(normalized_src);
CREATE INDEX IF NOT EXISTS idx_phrase_category ON phrase_memory(category);

CREATE TABLE IF NOT EXISTS export_log (
    id              INTEGER PRIMARY KEY AUTOINCREMENT,
    filename        TEXT,
    rows_processed  INTEGER DEFAULT 0,
    tm_hits         INTEGER DEFAULT 0,
    fuzzy_hits      INTEGER DEFAULT 0,
    glossary_hits   INTEGER DEFAULT 0,
    ai_hits         INTEGER DEFAULT 0,
    qa_corrections  INTEGER DEFAULT 0,
    consistency_score REAL DEFAULT 0.0,
    token_usage     INTEGER DEFAULT 0,
    processing_time REAL DEFAULT 0.0,
    exported_at     TEXT DEFAULT (datetime('now'))
);

CREATE TABLE IF NOT EXISTS qa_log (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    filename    TEXT,
    row_num     INTEGER,
    issue_type  TEXT,
    original    TEXT,
    corrected   TEXT,
    auto_fixed  INTEGER DEFAULT 0,
    logged_at   TEXT DEFAULT (datetime('now'))
);

CREATE TABLE IF NOT EXISTS consistency_log (
    id              INTEGER PRIMARY KEY AUTOINCREMENT,
    filename        TEXT,
    source_term     TEXT,
    chosen_target   TEXT,
    alternatives    TEXT,
    logged_at       TEXT DEFAULT (datetime('now'))
);
"""


def run_migrations():
    with get_connection() as conn:
        conn.executescript(SCHEMA)
    return True
