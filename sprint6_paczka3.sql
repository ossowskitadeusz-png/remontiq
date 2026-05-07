-- ============================================
-- SPRINT 6 PACZKA 3: Crew Requests v2
-- ============================================

ALTER TABLE crew_requests ADD COLUMN IF NOT EXISTS investor_note TEXT;
ALTER TABLE crew_requests ADD COLUMN IF NOT EXISTS expected_delivery_date DATE;
ALTER TABLE crew_requests ADD COLUMN IF NOT EXISTS confirmed_at TIMESTAMP;
ALTER TABLE crew_requests ADD COLUMN IF NOT EXISTS delivered_at TIMESTAMP;

-- Upewnij się że status ma sensowne wartości (nie zepsuje starych danych)
UPDATE crew_requests SET status = 'Nowe' WHERE status IS NULL OR status = 'Do zrobienia';

ALTER TABLE crew_requests DISABLE ROW LEVEL SECURITY;
