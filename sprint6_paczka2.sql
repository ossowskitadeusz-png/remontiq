-- ============================================
-- SPRINT 6 PART 2: KANBAN + BLOCKERS LOGIC
-- ============================================

-- KROK 1: Rozszerz tabele TASKS o status bardziej granularny
ALTER TABLE tasks ADD COLUMN IF NOT EXISTS kanban_status VARCHAR(50) DEFAULT 'BACKLOG';
ALTER TABLE tasks ADD COLUMN IF NOT EXISTS task_priority INT DEFAULT 3;
ALTER TABLE tasks ADD COLUMN IF NOT EXISTS is_blocked BOOLEAN DEFAULT FALSE;
ALTER TABLE tasks ADD COLUMN IF NOT EXISTS blocker_reason TEXT;
ALTER TABLE tasks ADD COLUMN IF NOT EXISTS blocker_type VARCHAR(50);

-- KROK 2: Nowa tabela dla BLOCKERS
CREATE TABLE IF NOT EXISTS task_blockers (
    id BIGSERIAL PRIMARY KEY,
    task_id UUID NOT NULL REFERENCES tasks(id) ON DELETE CASCADE,
    blocker_type VARCHAR(50) NOT NULL,
    description TEXT NOT NULL,
    reported_by VARCHAR(100),
    reported_at TIMESTAMP DEFAULT NOW(),
    resolved_at TIMESTAMP,
    priority INT DEFAULT 3,
    is_resolved BOOLEAN DEFAULT FALSE,
    resolution_note TEXT
);

-- KROK 3: Nowa tabela TASK_INSPECTION (Odbiór prac)
CREATE TABLE IF NOT EXISTS task_inspection (
    id BIGSERIAL PRIMARY KEY,
    task_id UUID NOT NULL REFERENCES tasks(id) ON DELETE CASCADE,
    submitted_by VARCHAR(100),
    submitted_at TIMESTAMP DEFAULT NOW(),
    submission_photos TEXT[],
    submission_notes TEXT,
    inspection_status VARCHAR(50) DEFAULT 'PENDING',
    inspected_by VARCHAR(100),
    inspected_at TIMESTAMP,
    inspection_notes TEXT,
    rework_description TEXT
);

-- KROK 4: Indeksy
CREATE INDEX IF NOT EXISTS idx_tasks_kanban_status ON tasks(kanban_status);
CREATE INDEX IF NOT EXISTS idx_tasks_is_blocked ON tasks(is_blocked);
CREATE INDEX IF NOT EXISTS idx_task_blockers_task_id ON task_blockers(task_id);
CREATE INDEX IF NOT EXISTS idx_task_blockers_resolved ON task_blockers(is_resolved);
CREATE INDEX IF NOT EXISTS idx_task_inspection_status ON task_inspection(inspection_status);

-- KROK 5: Disable RLS for new tables
ALTER TABLE task_blockers DISABLE ROW LEVEL SECURITY;
ALTER TABLE task_inspection DISABLE ROW LEVEL SECURITY;
