CREATE EXTENSION IF NOT EXISTS pgcrypto;
CREATE EXTENSION IF NOT EXISTS vector;

CREATE TABLE IF NOT EXISTS projects (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    name TEXT NOT NULL,
    repository_url TEXT NOT NULL,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE TABLE IF NOT EXISTS requirements (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    project_id UUID NOT NULL REFERENCES projects(id) ON DELETE CASCADE,
    external_key TEXT NOT NULL,
    title TEXT NOT NULL,
    body TEXT NOT NULL,
    source_url TEXT,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    UNIQUE (project_id, external_key)
);

CREATE TABLE IF NOT EXISTS pull_requests (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    project_id UUID NOT NULL REFERENCES projects(id) ON DELETE CASCADE,
    requirement_id UUID REFERENCES requirements(id) ON DELETE SET NULL,
    branch_name TEXT NOT NULL,
    commit_sha TEXT NOT NULL,
    review_route TEXT NOT NULL DEFAULT 'full_read'
        CHECK (review_route IN ('light_check', 'focused_read', 'full_read')),
    status TEXT NOT NULL DEFAULT 'pending'
        CHECK (status IN ('pending', 'reviewed', 'signed', 'rejected')),
    changed_lines INTEGER NOT NULL DEFAULT 0 CHECK (changed_lines >= 0),
    lines_to_read INTEGER NOT NULL DEFAULT 0 CHECK (lines_to_read >= 0),
    review_cost_usd NUMERIC(10, 4),
    review_duration_seconds INTEGER,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    UNIQUE (project_id, branch_name, commit_sha)
);

CREATE TABLE IF NOT EXISTS claims (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    pull_request_id UUID NOT NULL REFERENCES pull_requests(id) ON DELETE CASCADE,
    claim_text TEXT NOT NULL,
    requirement_quote TEXT NOT NULL,
    cited_paths JSONB NOT NULL DEFAULT '[]'::jsonb,
    model_confidence NUMERIC(5, 4) CHECK (model_confidence BETWEEN 0 AND 1),
    state TEXT NOT NULL DEFAULT 'pending'
        CHECK (state IN ('pending', 'verified', 'disputed', 'refused')),
    created_at TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE TABLE IF NOT EXISTS evidence_checks (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    claim_id UUID NOT NULL REFERENCES claims(id) ON DELETE CASCADE,
    check_type TEXT NOT NULL
        CHECK (check_type IN ('test', 'static', 'citation', 'breaker', 'scope', 'manual')),
    result TEXT NOT NULL CHECK (result IN ('passed', 'failed', 'skipped')),
    details JSONB NOT NULL DEFAULT '{}'::jsonb,
    checked_at TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE TABLE IF NOT EXISTS signoffs (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    pull_request_id UUID NOT NULL REFERENCES pull_requests(id) ON DELETE CASCADE,
    owner_name TEXT NOT NULL,
    decision TEXT NOT NULL CHECK (decision IN ('accepted', 'rejected')),
    acknowledged_refusals JSONB NOT NULL DEFAULT '[]'::jsonb,
    residual_risk TEXT NOT NULL,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE TABLE IF NOT EXISTS trust_ledger (
    project_id UUID NOT NULL REFERENCES projects(id) ON DELETE CASCADE,
    code_area TEXT NOT NULL,
    level TEXT NOT NULL DEFAULT 'full_read'
        CHECK (level IN ('light_check', 'focused_read', 'full_read')),
    clean_signoffs INTEGER NOT NULL DEFAULT 0 CHECK (clean_signoffs >= 0),
    escaped_bugs INTEGER NOT NULL DEFAULT 0 CHECK (escaped_bugs >= 0),
    false_alarms INTEGER NOT NULL DEFAULT 0 CHECK (false_alarms >= 0),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    PRIMARY KEY (project_id, code_area)
);

-- Vector part: similar feedback grouped into one cluster with a severity score.
CREATE TABLE IF NOT EXISTS clusters (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    project_id UUID NOT NULL REFERENCES projects(id) ON DELETE CASCADE,
    label TEXT NOT NULL,
    severity NUMERIC(8, 2) NOT NULL DEFAULT 0,  -- reports + reactions + comments, weighted
    requirement_id UUID REFERENCES requirements(id) ON DELETE SET NULL,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE TABLE IF NOT EXISTS feedback (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    project_id UUID NOT NULL REFERENCES projects(id) ON DELETE CASCADE,
    source TEXT NOT NULL,
    external_id TEXT NOT NULL,
    body TEXT NOT NULL,
    metadata JSONB NOT NULL DEFAULT '{}'::jsonb,  -- author, url, reactions, comments
    cluster_id UUID REFERENCES clusters(id) ON DELETE SET NULL,
    embedding vector(384),  -- fastembed BAAI/bge-small-en-v1.5, runs locally, no API key
    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    UNIQUE (project_id, source, external_id)
);

CREATE INDEX IF NOT EXISTS feedback_embedding_idx
    ON feedback USING hnsw (embedding vector_cosine_ops)
    WHERE embedding IS NOT NULL;

CREATE TABLE IF NOT EXISTS review_events (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    event_type TEXT NOT NULL,
    aggregate_type TEXT NOT NULL,
    aggregate_id UUID,
    payload JSONB NOT NULL DEFAULT '{}'::jsonb,
    occurred_at TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE INDEX IF NOT EXISTS review_events_occurred_at_idx
    ON review_events (occurred_at DESC);

