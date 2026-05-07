-- ============================================
-- SPRINT 6: PACKAGE 1 — NOWA LOGIKA ZADAŃ
-- ============================================

-- KROK 1: Dodaj nowe kolumny do tabeli TASKS
ALTER TABLE tasks ADD COLUMN IF NOT EXISTS depends_on_tasks TEXT[] DEFAULT ARRAY[]::TEXT[];
ALTER TABLE tasks ADD COLUMN IF NOT EXISTS created_by_crew BOOLEAN DEFAULT FALSE;
ALTER TABLE tasks ADD COLUMN IF NOT EXISTS investor_note TEXT;
ALTER TABLE tasks ADD COLUMN IF NOT EXISTS depends_on_task_ids UUID[] DEFAULT ARRAY[]::UUID[];
ALTER TABLE tasks ADD COLUMN IF NOT EXISTS task_phase VARCHAR(50) DEFAULT 'EXECUTION';

-- Uzupełnienie brakujących kolumn ze specyfikacji (Paczka 1)
ALTER TABLE tasks ADD COLUMN IF NOT EXISTS description TEXT;
ALTER TABLE tasks ADD COLUMN IF NOT EXISTS planned_start_date DATE;
ALTER TABLE tasks ADD COLUMN IF NOT EXISTS planned_end_date DATE;
ALTER TABLE tasks ADD COLUMN IF NOT EXISTS actual_start_date DATE;
ALTER TABLE tasks ADD COLUMN IF NOT EXISTS actual_end_date DATE;
ALTER TABLE tasks ADD COLUMN IF NOT EXISTS progress_percent INT DEFAULT 0;
ALTER TABLE tasks ADD COLUMN IF NOT EXISTS assigned_to TEXT;

-- KROK 2: Dodaj nowe kolumny do tabeli CREW_REQUESTS
ALTER TABLE crew_requests ADD COLUMN IF NOT EXISTS linked_task_id UUID REFERENCES tasks(id) ON DELETE SET NULL;
ALTER TABLE crew_requests ADD COLUMN IF NOT EXISTS is_blocker_for_task_ids UUID[] DEFAULT ARRAY[]::UUID[];
ALTER TABLE crew_requests ADD COLUMN IF NOT EXISTS priority_score INT DEFAULT 50;

-- KROK 3: Stwórz VIEW do pobierania zadań z informacją o zależnościach
CREATE OR REPLACE VIEW tasks_with_dependencies AS
SELECT 
    t.id,
    t.name,
    t.description,
    t.status,
    t.planned_start_date,
    t.planned_end_date,
    t.actual_start_date,
    t.actual_end_date,
    t.progress_percent,
    t.assigned_to,
    t.created_by_crew,
    t.investor_note,
    t.depends_on_tasks,
    t.depends_on_task_ids,
    t.task_phase,
    (
        SELECT COUNT(*) = 0 
        FROM UNNEST(t.depends_on_task_ids) AS dep_id
        WHERE EXISTS (
            SELECT 1 FROM tasks t2 
            WHERE t2.id = dep_id 
            AND t2.status NOT IN ('Done', 'Completed')
        )
    ) AS all_dependencies_met,
    (
        SELECT COUNT(*)
        FROM tasks t2
        WHERE t2.depends_on_task_ids @> ARRAY[t.id]
    ) AS dependent_tasks_count
FROM tasks t
WHERE t.is_deleted = false;

-- KROK 4: Stwórz TRIGGER do walidacji zależności
CREATE OR REPLACE FUNCTION validate_task_dependencies()
RETURNS TRIGGER AS $$
BEGIN
    IF NEW.depends_on_task_ids && ARRAY[NEW.id] THEN
        RAISE EXCEPTION 'Zadanie nie może zależeć od samego siebie!';
    END IF;
    RETURN NEW;
END;
$$ LANGUAGE plpgsql;

DROP TRIGGER IF EXISTS check_task_dependencies ON tasks;
CREATE TRIGGER check_task_dependencies BEFORE INSERT OR UPDATE ON tasks
FOR EACH ROW EXECUTE FUNCTION validate_task_dependencies();

-- KROK 5: Indeksy dla szybkości
CREATE INDEX IF NOT EXISTS idx_tasks_created_by_crew ON tasks(created_by_crew);
CREATE INDEX IF NOT EXISTS idx_tasks_depends_on ON tasks USING GIN(depends_on_task_ids);
CREATE INDEX IF NOT EXISTS idx_tasks_phase ON tasks(task_phase);

-- KROK 6: Aktualizuj stare dane
UPDATE tasks SET created_by_crew = FALSE WHERE created_by_crew IS NULL;
