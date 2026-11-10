PRAGMA foreign_keys = ON;

CREATE TABLE IF NOT EXISTS sessions (
    id INTEGER PRIMARY KEY,
    mode TEXT NOT NULL,
    started_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE IF NOT EXISTS messages (
    id INTEGER PRIMARY KEY,
    session_id INTEGER NOT NULL REFERENCES sessions(id),
    role TEXT NOT NULL CHECK (role IN ('user', 'assistant')),
    content TEXT NOT NULL,
    created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE IF NOT EXISTS ideas (
    id INTEGER PRIMARY KEY,
    title TEXT NOT NULL,
    description TEXT NOT NULL,
    problem TEXT,
    assumption_changed TEXT,
    status TEXT NOT NULL DEFAULT 'captured'
        CHECK (status IN ('captured', 'exploring', 'testing', 'killed', 'shipped')),
    stage TEXT NOT NULL DEFAULT 'early' CHECK (stage IN ('early', 'later')),
    kill_reason TEXT,
    session_id INTEGER REFERENCES sessions(id),
    created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE IF NOT EXISTS runs (
    id INTEGER PRIMARY KEY,
    mode TEXT NOT NULL,
    idea_id INTEGER REFERENCES ideas(id),
    session_id INTEGER REFERENCES sessions(id),
    status TEXT NOT NULL DEFAULT 'running',
    verdict TEXT,
    total_cost REAL NOT NULL DEFAULT 0,
    search_count INTEGER NOT NULL DEFAULT 0,
    duration_s REAL,
    prompt_version TEXT,
    notes TEXT,
    started_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
    ended_at TEXT
);

CREATE TABLE IF NOT EXISTS llm_calls (
    id INTEGER PRIMARY KEY,
    run_id INTEGER NOT NULL REFERENCES runs(id),
    agent TEXT NOT NULL,
    model TEXT NOT NULL,
    effort TEXT,
    input_tokens INTEGER,
    output_tokens INTEGER,
    cache_read_tokens INTEGER,
    cache_write_tokens INTEGER,
    cost REAL,
    latency_s REAL,
    status TEXT NOT NULL,
    input_text TEXT,
    output_text TEXT,
    created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE IF NOT EXISTS searches (
    id INTEGER PRIMARY KEY,
    run_id INTEGER NOT NULL REFERENCES runs(id),
    query TEXT NOT NULL,
    result_count INTEGER,
    created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE IF NOT EXISTS claims (
    id INTEGER PRIMARY KEY,
    idea_id INTEGER NOT NULL REFERENCES ideas(id),
    run_id INTEGER REFERENCES runs(id),
    text TEXT NOT NULL,
    critical INTEGER NOT NULL DEFAULT 0,
    status TEXT NOT NULL DEFAULT 'HYPOTHESIS'
        CHECK (status IN ('FACT', 'EVIDENCE_BASED_INFERENCE', 'HYPOTHESIS', 'SPECULATION')),
    reasoning TEXT,
    created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE IF NOT EXISTS claim_events (
    id INTEGER PRIMARY KEY,
    claim_id INTEGER NOT NULL REFERENCES claims(id),
    run_id INTEGER REFERENCES runs(id),
    from_status TEXT,
    to_status TEXT NOT NULL,
    attempted_status TEXT,
    cause TEXT NOT NULL,
    created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE IF NOT EXISTS evidence (
    id INTEGER PRIMARY KEY,
    claim_id INTEGER NOT NULL REFERENCES claims(id),
    run_id INTEGER REFERENCES runs(id),
    source_type TEXT NOT NULL DEFAULT 'web' CHECK (source_type IN ('web', 'user_experiment')),
    url TEXT,
    title TEXT,
    organization TEXT,
    published_date TEXT,
    retrieved_date TEXT,
    summary TEXT NOT NULL,
    direction TEXT NOT NULL CHECK (direction IN ('supporting', 'contradicting', 'analogous')),
    verification TEXT NOT NULL DEFAULT 'pending'
        CHECK (verification IN ('pending', 'supported', 'partial', 'unsupported')),
    verification_note TEXT,
    created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE IF NOT EXISTS stress_results (
    id INTEGER PRIMARY KEY,
    idea_id INTEGER NOT NULL REFERENCES ideas(id),
    run_id INTEGER NOT NULL REFERENCES runs(id),
    result_json TEXT NOT NULL,
    created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE IF NOT EXISTS baseline_comparisons (
    id INTEGER PRIMARY KEY,
    idea_id INTEGER NOT NULL REFERENCES ideas(id),
    stress_result_id INTEGER NOT NULL REFERENCES stress_results(id),
    project_output TEXT NOT NULL,
    prototype_label TEXT NOT NULL CHECK (prototype_label IN ('A', 'B')),
    winner TEXT CHECK (winner IN ('A', 'B', 'tie')),
    changed_decision INTEGER,
    caught_flaw INTEGER,
    notes TEXT,
    created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
    scored_at TEXT
);

CREATE TABLE IF NOT EXISTS gate_evals (
    id INTEGER PRIMARY KEY,
    correct INTEGER NOT NULL,
    total INTEGER NOT NULL,
    seeds_rejected INTEGER NOT NULL,
    cost REAL,
    misses_json TEXT,
    created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
);

-- Phase 4 and 5 tables. Created now so later phases need no migration.
CREATE TABLE IF NOT EXISTS experiments (
    id INTEGER PRIMARY KEY,
    idea_id INTEGER NOT NULL REFERENCES ideas(id),
    run_id INTEGER REFERENCES runs(id),
    hypothesis TEXT NOT NULL,
    success_criteria TEXT NOT NULL,
    failure_criteria TEXT NOT NULL,
    result TEXT,
    result_date TEXT,
    created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE IF NOT EXISTS concepts (
    id INTEGER PRIMARY KEY,
    title TEXT NOT NULL,
    content TEXT NOT NULL,
    tags TEXT,
    epistemic_status TEXT NOT NULL DEFAULT 'HYPOTHESIS',
    origin_idea_id INTEGER REFERENCES ideas(id),
    approved INTEGER NOT NULL DEFAULT 0,
    created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE IF NOT EXISTS lessons (
    id INTEGER PRIMARY KEY,
    idea_id INTEGER REFERENCES ideas(id),
    experiment_id INTEGER REFERENCES experiments(id),
    content TEXT NOT NULL,
    conditions TEXT,
    approved INTEGER NOT NULL DEFAULT 0,
    created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE IF NOT EXISTS relationships (
    id INTEGER PRIMARY KEY,
    from_type TEXT NOT NULL,
    from_id INTEGER NOT NULL,
    to_type TEXT NOT NULL,
    to_id INTEGER NOT NULL,
    kind TEXT NOT NULL,
    created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
);
