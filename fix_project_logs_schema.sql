
-- MIGRACJA DLA TABELI project_logs (Sprint 23)
ALTER TABLE project_logs ADD COLUMN IF NOT EXISTS project_id UUID REFERENCES project_metadata(id) ON DELETE CASCADE;
ALTER TABLE project_logs ADD COLUMN IF NOT EXISTS description TEXT;
ALTER TABLE project_logs ADD COLUMN IF NOT EXISTS data JSONB;

-- Upewnienie się, że RLS nie blokuje zapisów
ALTER TABLE project_logs DISABLE ROW LEVEL SECURITY;
