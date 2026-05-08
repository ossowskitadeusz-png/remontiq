-- ============================================
-- SPRINT 7: Activity Log (Alert Banner)
-- ============================================

CREATE TABLE IF NOT EXISTS activity_log (
    id          UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    event_type  TEXT NOT NULL,
    -- 'task_started', 'inspection_submitted', 'inspection_approved',
    -- 'inspection_rework', 'blocker_reported', 'request_confirmed',
    -- 'request_delivered', 'request_cancelled', 'task_completed'
    description TEXT NOT NULL,
    task_id     UUID REFERENCES tasks(id) ON DELETE SET NULL,
    created_by  TEXT NOT NULL,   -- 'Karol' lub 'Inwestor'
    visible_to  TEXT NOT NULL,   -- 'investor', 'crew', 'both'
    created_at  TIMESTAMP WITH TIME ZONE DEFAULT NOW()
);

ALTER TABLE activity_log DISABLE ROW LEVEL SECURITY;

-- Indeksy dla wydajności
CREATE INDEX IF NOT EXISTS idx_activity_log_visible_to ON activity_log(visible_to, created_at DESC);
CREATE INDEX IF NOT EXISTS idx_activity_log_created_at ON activity_log(created_at DESC);
