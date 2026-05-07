-- MIGRACJA BAZY DANYCH DLA SPRINTU 4 (Sekcje 7-10)

-- 1. Aktualizacja Decyzji (Decisions)
ALTER TABLE decisions ADD COLUMN IF NOT EXISTS room_id UUID REFERENCES rooms(id) ON DELETE CASCADE;
ALTER TABLE decisions ADD COLUMN IF NOT EXISTS description TEXT;
ALTER TABLE decisions ADD COLUMN IF NOT EXISTS decision_result TEXT;

-- 2. Aktualizacja Ryzyk / Problemów (Issues)
ALTER TABLE issues ADD COLUMN IF NOT EXISTS room_id UUID REFERENCES rooms(id) ON DELETE CASCADE;
ALTER TABLE issues ADD COLUMN IF NOT EXISTS description TEXT;
ALTER TABLE issues ADD COLUMN IF NOT EXISTS severity TEXT DEFAULT 'Średnie'; -- Opcje: Niskie, Średnie, Krytyczne
ALTER TABLE issues ADD COLUMN IF NOT EXISTS assigned_to_task_id UUID REFERENCES tasks(id) ON DELETE SET NULL;
ALTER TABLE issues ADD COLUMN IF NOT EXISTS resolved_at TIMESTAMP;

-- 3. Nowa tabela: Dziennik Remontu (Daily Logs)
CREATE TABLE IF NOT EXISTS daily_logs (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    date DATE NOT NULL DEFAULT CURRENT_DATE,
    content TEXT NOT NULL,
    room_id UUID REFERENCES rooms(id) ON DELETE CASCADE,
    author_role TEXT NOT NULL DEFAULT 'investor', -- 'investor' lub 'crew'
    source TEXT DEFAULT 'manual', -- 'manual', 'crew_report'
    weather TEXT,
    created_at TIMESTAMPTZ DEFAULT NOW(),
    updated_at TIMESTAMPTZ DEFAULT NOW(),
    is_deleted BOOLEAN DEFAULT FALSE
);

-- 4. Aktualizacja Zadań (aby móc wiązać zadania z pokojami jak w analizie)
ALTER TABLE tasks ADD COLUMN IF NOT EXISTS room_id UUID REFERENCES rooms(id) ON DELETE CASCADE;
