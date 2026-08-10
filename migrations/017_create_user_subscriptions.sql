-- ============================================================================
-- 017_create_user_subscriptions.sql
-- User subscription settings for push notifications on new/updated projects.
-- Each row = one user's subscription preferences.
-- ============================================================================

CREATE TABLE IF NOT EXISTS user_subscriptions (
  id              BIGSERIAL PRIMARY KEY,
  user_open_id    TEXT NOT NULL UNIQUE,
  subscribed_industries TEXT[] DEFAULT '{}',
  subscribed_countries  TEXT[] DEFAULT '{}',
  followed_project_ids  TEXT[] DEFAULT '{}',
  webhook_url     TEXT DEFAULT '',
  created_at      TIMESTAMPTZ NOT NULL DEFAULT now(),
  updated_at      TIMESTAMPTZ NOT NULL DEFAULT now()
);

-- Index for lookups by user_open_id (used in every notification scan)
CREATE INDEX IF NOT EXISTS idx_user_subscriptions_open_id
  ON user_subscriptions (user_open_id);

-- Enable Row Level Security
ALTER TABLE user_subscriptions ENABLE ROW LEVEL SECURITY;

-- RLS policy: users can only read/update their own row
-- The user_open_id column must match the authenticated user's open_id.
-- Accept authenticated and anon requests (Supabase auth not enforced for Feishu users;
-- application layer validates user_open_id matches the logged-in user).
CREATE POLICY "Users can read own subscription"
  ON user_subscriptions FOR SELECT
  USING (true);  -- application-layer filtering by user_open_id

CREATE POLICY "Users can insert own subscription"
  ON user_subscriptions FOR INSERT
  WITH CHECK (true);

CREATE POLICY "Users can update own subscription"
  ON user_subscriptions FOR UPDATE
  USING (true);

CREATE POLICY "Users can delete own subscription"
  ON user_subscriptions FOR DELETE
  USING (true);

-- Trigger to auto-update updated_at
CREATE OR REPLACE FUNCTION update_user_subscriptions_updated_at()
RETURNS TRIGGER AS $$
BEGIN
  NEW.updated_at = now();
  RETURN NEW;
END;
$$ LANGUAGE plpgsql;

DROP TRIGGER IF EXISTS trg_user_subscriptions_updated_at ON user_subscriptions;
CREATE TRIGGER trg_user_subscriptions_updated_at
  BEFORE UPDATE ON user_subscriptions
  FOR EACH ROW EXECUTE FUNCTION update_user_subscriptions_updated_at();
