-- FAZA 1: Migracja struktury, bez NOT NULL

-- A. Tabela Wydatków
ALTER TABLE public.expenses ADD COLUMN IF NOT EXISTS project_id UUID;
ALTER TABLE public.expenses ADD COLUMN IF NOT EXISTS material_id UUID;
ALTER TABLE public.expenses ADD COLUMN IF NOT EXISTS is_deleted BOOLEAN DEFAULT FALSE;

UPDATE public.expenses
SET is_deleted = FALSE
WHERE is_deleted IS NULL;

-- B. Tabela Materiałów
CREATE TABLE IF NOT EXISTS public.materials (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    project_id UUID,
    name TEXT NOT NULL,
    room_id UUID REFERENCES public.rooms(id),
    status TEXT DEFAULT 'Do zamówienia',
    location TEXT,
    available_for_crew BOOLEAN DEFAULT FALSE,
    crew_confirmed BOOLEAN DEFAULT FALSE,
    needed_by DATE,
    lead_time_days INTEGER DEFAULT 0,
    cost_actual NUMERIC DEFAULT 0,
    notes TEXT,
    quantity_planned NUMERIC DEFAULT 0,
    quantity_received NUMERIC DEFAULT 0,
    unit TEXT DEFAULT 'szt',
    created_at TIMESTAMPTZ DEFAULT NOW(),
    updated_at TIMESTAMPTZ DEFAULT NOW(),
    is_deleted BOOLEAN DEFAULT FALSE
);

-- C. Crew Requests
ALTER TABLE public.crew_requests ADD COLUMN IF NOT EXISTS project_id UUID;

-- D. Klucze obce
DO $$
BEGIN
    IF NOT EXISTS (
        SELECT 1 FROM pg_constraint
        WHERE conname = 'expenses_project_id_fkey'
          AND conrelid = 'public.expenses'::regclass
    ) THEN
        ALTER TABLE public.expenses
        ADD CONSTRAINT expenses_project_id_fkey
        FOREIGN KEY (project_id)
        REFERENCES public.project_metadata(id)
        ON DELETE CASCADE;
    END IF;

    IF NOT EXISTS (
        SELECT 1 FROM pg_constraint
        WHERE conname = 'materials_project_id_fkey'
          AND conrelid = 'public.materials'::regclass
    ) THEN
        ALTER TABLE public.materials
        ADD CONSTRAINT materials_project_id_fkey
        FOREIGN KEY (project_id)
        REFERENCES public.project_metadata(id)
        ON DELETE CASCADE;
    END IF;

    IF NOT EXISTS (
        SELECT 1 FROM pg_constraint
        WHERE conname = 'expenses_material_id_fkey'
          AND conrelid = 'public.expenses'::regclass
    ) THEN
        ALTER TABLE public.expenses
        ADD CONSTRAINT expenses_material_id_fkey
        FOREIGN KEY (material_id)
        REFERENCES public.materials(id)
        ON DELETE SET NULL;
    END IF;

    IF NOT EXISTS (
        SELECT 1 FROM pg_constraint
        WHERE conname = 'crew_requests_project_id_fkey'
          AND conrelid = 'public.crew_requests'::regclass
    ) THEN
        ALTER TABLE public.crew_requests
        ADD CONSTRAINT crew_requests_project_id_fkey
        FOREIGN KEY (project_id)
        REFERENCES public.project_metadata(id)
        ON DELETE CASCADE;
    END IF;
END $$;

-- E. Indeksy
CREATE INDEX IF NOT EXISTS idx_expenses_project_id ON public.expenses(project_id);
CREATE INDEX IF NOT EXISTS idx_expenses_material_id ON public.expenses(material_id);
CREATE INDEX IF NOT EXISTS idx_materials_project_id ON public.materials(project_id);
CREATE INDEX IF NOT EXISTS idx_crew_requests_project_id ON public.crew_requests(project_id);
CREATE INDEX IF NOT EXISTS idx_project_logs_project_id ON public.project_logs(project_id);

-- FAZA 2: Backfill dla JEDNEGO testowego projektu

UPDATE public.expenses 
SET project_id = '8feb8f23-868a-449f-85b7-1c10a4c42e46' 
WHERE project_id IS NULL;

UPDATE public.crew_requests cr
SET project_id = t.project_id
FROM public.tasks t
WHERE cr.task_id = t.id
  AND cr.project_id IS NULL;
  
-- Dla osieroconych crew requests, gdzie task_id jest null lub brak w tasks
UPDATE public.crew_requests
SET project_id = '8feb8f23-868a-449f-85b7-1c10a4c42e46'
WHERE project_id IS NULL;

UPDATE public.project_logs
SET project_id = '8feb8f23-868a-449f-85b7-1c10a4c42e46'
WHERE project_id IS NULL;

-- FAZA 3: Zapytania do ręcznej weryfikacji po backfillu (powinny zwrócić wszędzie 0)
-- SELECT COUNT(*) AS expenses_without_project FROM public.expenses WHERE project_id IS NULL;
-- SELECT COUNT(*) AS crew_requests_without_project FROM public.crew_requests WHERE project_id IS NULL;
-- SELECT COUNT(*) AS project_logs_without_project FROM public.project_logs WHERE project_id IS NULL;
-- SELECT COUNT(*) AS expenses_deleted_null FROM public.expenses WHERE is_deleted IS NULL;
