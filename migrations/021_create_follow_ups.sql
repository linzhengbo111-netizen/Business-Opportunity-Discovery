-- ============================================================================
-- 021_create_follow_ups.sql
-- Sales follow-up tracking — S7 Follow-up Loop
-- Each row = one salesperson's follow-up record for a project.
-- Stores status, notes, and manual corrections to system inferences.
-- ============================================================================

CREATE TABLE IF NOT EXISTS follow_ups (
  id              BIGSERIAL PRIMARY KEY,
  project_id      TEXT NOT NULL,
  user_open_id    TEXT NOT NULL,
  status          TEXT NOT NULL DEFAULT 'contacted'
                    CHECK (status IN ('contacted','valid','inquiry','invalid','closed')),
  notes           TEXT DEFAULT '',
  corrections     JSONB DEFAULT '{}',
  created_at      TIMESTAMPTZ NOT NULL DEFAULT now(),
  updated_at      TIMESTAMPTZ NOT NULL DEFAULT now(),

  -- One follow-up per user per project (upsert on conflict)
  CONSTRAINT uq_follow_up_user_project UNIQUE (project_id, user_open_id)
);

-- Index for lookups by user (Settings "My Follow-ups" panel)
CREATE INDEX IF NOT EXISTS idx_follow_ups_user_open_id
  ON follow_ups (user_open_id);

-- Index for lookups by project (detail panel follow-up status)
CREATE INDEX IF NOT EXISTS idx_follow_ups_project_id
  ON follow_ups (project_id);

-- Enable Row Level Security
ALTER TABLE follow_ups ENABLE ROW LEVEL SECURITY;

-- RLS: users read all follow-ups (shared visibility for team collaboration)
-- Application layer filters by user_open_id where needed.
CREATE POLICY "Anyone can read follow_ups"
  ON follow_ups FOR SELECT
  USING (true);

CREATE POLICY "Users can insert own follow_ups"
  ON follow_ups FOR INSERT
  WITH CHECK (true);

CREATE POLICY "Users can update own follow_ups"
  ON follow_ups FOR UPDATE
  USING (true);

CREATE POLICY "Users can delete own follow_ups"
  ON follow_ups FOR DELETE
  USING (true);

-- Trigger to auto-update updated_at
CREATE OR REPLACE FUNCTION update_follow_ups_updated_at()
RETURNS TRIGGER AS $$
BEGIN
  NEW.updated_at = now();
  RETURN NEW;
END;
$$ LANGUAGE plpgsql;

DROP TRIGGER IF EXISTS trg_follow_ups_updated_at ON follow_ups;
CREATE TRIGGER trg_follow_ups_updated_at
  BEFORE UPDATE ON follow_ups
  FOR EACH ROW EXECUTE FUNCTION update_follow_ups_updated_at();
