CREATE TABLE IF NOT EXISTS sources (
    id BIGINT PRIMARY KEY,
    name TEXT NOT NULL,
    type TEXT NOT NULL,
    status TEXT NOT NULL,
    api_key_hash TEXT NOT NULL UNIQUE,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    CONSTRAINT sources_status_check CHECK (
        status IN ('active', 'inactive', 'disabled')
    )
);

CREATE TABLE IF NOT EXISTS breaches (
    id BIGINT PRIMARY KEY,
    source_id BIGINT NOT NULL REFERENCES sources(id),
    name TEXT NOT NULL,
    description TEXT,
    collected_at TIMESTAMPTZ,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE TABLE IF NOT EXISTS ingestion_jobs (
    id BIGINT PRIMARY KEY,
    source_id BIGINT NOT NULL REFERENCES sources(id),
    breach_id BIGINT REFERENCES breaches(id),

    original_filename TEXT NOT NULL,
    stored_filename TEXT NOT NULL,
    local_path TEXT NOT NULL,

    checksum_sha256 TEXT NOT NULL,
    file_size_bytes BIGINT NOT NULL,

    status TEXT NOT NULL,

    total_lines BIGINT NOT NULL DEFAULT 0,
    parsed_lines BIGINT NOT NULL DEFAULT 0,
    rejected_lines BIGINT NOT NULL DEFAULT 0,
    inserted_lines BIGINT NOT NULL DEFAULT 0,

    error_message TEXT,

    started_at TIMESTAMPTZ,
    finished_at TIMESTAMPTZ,

    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    CONSTRAINT ingestion_jobs_status_check CHECK (
        status IN ('pending', 'running', 'completed', 'failed', 'canceled')
    ),
    CONSTRAINT ingestion_jobs_file_size_check CHECK (file_size_bytes >= 0),
    CONSTRAINT ingestion_jobs_line_counts_check CHECK (
        total_lines >= 0
        AND parsed_lines >= 0
        AND rejected_lines >= 0
        AND inserted_lines >= 0
    )
);

CREATE TABLE IF NOT EXISTS ingestion_job_errors (
    id BIGINT PRIMARY KEY,
    job_id BIGINT NOT NULL REFERENCES ingestion_jobs(id),
    line_number BIGINT,
    error_type TEXT NOT NULL,
    error_message TEXT NOT NULL,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    CONSTRAINT ingestion_job_errors_line_number_check CHECK (
        line_number IS NULL OR line_number > 0
    )
);

CREATE INDEX IF NOT EXISTS idx_sources_status ON sources(status);
CREATE INDEX IF NOT EXISTS idx_sources_type ON sources(type);

CREATE INDEX IF NOT EXISTS idx_breaches_source_id ON breaches(source_id);
CREATE INDEX IF NOT EXISTS idx_breaches_collected_at ON breaches(collected_at);

CREATE INDEX IF NOT EXISTS idx_ingestion_jobs_source_id ON ingestion_jobs(source_id);
CREATE INDEX IF NOT EXISTS idx_ingestion_jobs_breach_id ON ingestion_jobs(breach_id);
CREATE INDEX IF NOT EXISTS idx_ingestion_jobs_status ON ingestion_jobs(status);
CREATE INDEX IF NOT EXISTS idx_ingestion_jobs_checksum_sha256
    ON ingestion_jobs(checksum_sha256);
CREATE INDEX IF NOT EXISTS idx_ingestion_jobs_created_at
    ON ingestion_jobs(created_at);

CREATE INDEX IF NOT EXISTS idx_ingestion_job_errors_job_id
    ON ingestion_job_errors(job_id);
CREATE INDEX IF NOT EXISTS idx_ingestion_job_errors_error_type
    ON ingestion_job_errors(error_type);
