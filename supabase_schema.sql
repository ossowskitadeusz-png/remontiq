-- Krok 1: Tabele Główne

CREATE TABLE IF NOT EXISTS settings (
    key TEXT PRIMARY KEY,
    value TEXT
);

CREATE TABLE IF NOT EXISTS rooms (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    name TEXT NOT NULL UNIQUE,
    budget NUMERIC DEFAULT 0,
    created_at TIMESTAMPTZ DEFAULT NOW(),
    updated_at TIMESTAMPTZ DEFAULT NOW(),
    is_deleted BOOLEAN DEFAULT FALSE
);

CREATE TABLE IF NOT EXISTS materials (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    name TEXT NOT NULL,
    room_id UUID REFERENCES rooms(id),
    status TEXT DEFAULT 'Do zamówienia',
    location TEXT,
    available_for_crew BOOLEAN DEFAULT FALSE,
    crew_confirmed BOOLEAN DEFAULT FALSE,
    needed_by DATE,
    lead_time_days INTEGER DEFAULT 0,
    cost_actual NUMERIC DEFAULT 0, -- TO JEST CACHE
    notes TEXT,
    quantity_planned NUMERIC DEFAULT 0,
    quantity_received NUMERIC DEFAULT 0, -- TO JEST CACHE
    unit TEXT DEFAULT 'szt',
    created_at TIMESTAMPTZ DEFAULT NOW(),
    updated_at TIMESTAMPTZ DEFAULT NOW(),
    is_deleted BOOLEAN DEFAULT FALSE
);

CREATE TABLE IF NOT EXISTS expenses (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    description TEXT NOT NULL,
    amount NUMERIC DEFAULT 0,
    quantity NUMERIC DEFAULT 0,
    date DATE,
    material_id UUID REFERENCES materials(id),
    created_at TIMESTAMPTZ DEFAULT NOW(),
    updated_at TIMESTAMPTZ DEFAULT NOW(),
    is_deleted BOOLEAN DEFAULT FALSE
);

CREATE TABLE IF NOT EXISTS crew_requests (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    title TEXT NOT NULL,
    needed_by DATE,
    status TEXT DEFAULT 'Do zrobienia',
    is_blocker BOOLEAN DEFAULT FALSE,
    created_at TIMESTAMPTZ DEFAULT NOW(),
    updated_at TIMESTAMPTZ DEFAULT NOW(),
    is_deleted BOOLEAN DEFAULT FALSE
);

CREATE TABLE IF NOT EXISTS tasks (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    name TEXT NOT NULL,
    status TEXT DEFAULT 'Backlog',
    priority TEXT DEFAULT 'Normalny',
    planned_start DATE,
    assignee TEXT,
    progress INTEGER DEFAULT 0,
    notes TEXT,
    created_at TIMESTAMPTZ DEFAULT NOW(),
    updated_at TIMESTAMPTZ DEFAULT NOW(),
    is_deleted BOOLEAN DEFAULT FALSE
);

CREATE TABLE IF NOT EXISTS decisions (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    title TEXT NOT NULL,
    due_date DATE,
    status TEXT DEFAULT 'Do podjęcia',
    impact TEXT DEFAULT 'Średni',
    created_at TIMESTAMPTZ DEFAULT NOW(),
    updated_at TIMESTAMPTZ DEFAULT NOW(),
    is_deleted BOOLEAN DEFAULT FALSE
);

CREATE TABLE IF NOT EXISTS issues (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    title TEXT NOT NULL,
    status TEXT DEFAULT 'Otwarte',
    created_at TIMESTAMPTZ DEFAULT NOW(),
    updated_at TIMESTAMPTZ DEFAULT NOW(),
    is_deleted BOOLEAN DEFAULT FALSE
);

-- Krok 2: Automatyczna aktualizacja `updated_at`
CREATE OR REPLACE FUNCTION update_updated_at_column()
RETURNS TRIGGER AS $$
BEGIN
   NEW.updated_at = NOW();
   RETURN NEW;
END;
$$ language 'plpgsql';

DROP TRIGGER IF EXISTS trg_rooms_updated_at ON rooms;
CREATE TRIGGER trg_rooms_updated_at BEFORE UPDATE ON rooms FOR EACH ROW EXECUTE PROCEDURE update_updated_at_column();

DROP TRIGGER IF EXISTS trg_materials_updated_at ON materials;
CREATE TRIGGER trg_materials_updated_at BEFORE UPDATE ON materials FOR EACH ROW EXECUTE PROCEDURE update_updated_at_column();

DROP TRIGGER IF EXISTS trg_expenses_updated_at ON expenses;
CREATE TRIGGER trg_expenses_updated_at BEFORE UPDATE ON expenses FOR EACH ROW EXECUTE PROCEDURE update_updated_at_column();

DROP TRIGGER IF EXISTS trg_crew_requests_updated_at ON crew_requests;
CREATE TRIGGER trg_crew_requests_updated_at BEFORE UPDATE ON crew_requests FOR EACH ROW EXECUTE PROCEDURE update_updated_at_column();

DROP TRIGGER IF EXISTS trg_tasks_updated_at ON tasks;
CREATE TRIGGER trg_tasks_updated_at BEFORE UPDATE ON tasks FOR EACH ROW EXECUTE PROCEDURE update_updated_at_column();

-- Krok 3: TRANSAKCYJNY SYNC ENGINE (Supabase Triggers)
-- Funkcja przeliczająca materiał "Źródło Prawdy"
CREATE OR REPLACE FUNCTION recalculate_material_totals(p_material_id UUID)
RETURNS VOID AS $$
BEGIN
    UPDATE materials
    SET 
        cost_actual = COALESCE((SELECT SUM(amount) FROM expenses WHERE material_id = p_material_id AND is_deleted = FALSE), 0),
        quantity_received = COALESCE((SELECT SUM(quantity) FROM expenses WHERE material_id = p_material_id AND is_deleted = FALSE), 0)
    WHERE id = p_material_id;
END;
$$ LANGUAGE plpgsql;

-- Trigger dbający o to, by przy każdej zmianie wydatku automatycznie uruchomiła się synchronizacja!
CREATE OR REPLACE FUNCTION trg_sync_expense_to_material()
RETURNS TRIGGER AS $$
BEGIN
    IF (TG_OP = 'INSERT' OR TG_OP = 'UPDATE') THEN
        IF NEW.material_id IS NOT NULL THEN
            PERFORM recalculate_material_totals(NEW.material_id);
        END IF;
        -- Jeśli przepięto wydatek na inny materiał, trzeba zaktualizować ten stary
        IF TG_OP = 'UPDATE' AND OLD.material_id IS NOT NULL AND OLD.material_id != NEW.material_id THEN
            PERFORM recalculate_material_totals(OLD.material_id);
        END IF;
    ELSIF (TG_OP = 'DELETE') THEN
        IF OLD.material_id IS NOT NULL THEN
            PERFORM recalculate_material_totals(OLD.material_id);
        END IF;
    END IF;
    RETURN NULL;
END;
$$ LANGUAGE plpgsql;

DROP TRIGGER IF EXISTS expense_sync_trigger ON expenses;
CREATE TRIGGER expense_sync_trigger
AFTER INSERT OR UPDATE OR DELETE ON expenses
FOR EACH ROW EXECUTE PROCEDURE trg_sync_expense_to_material();

-- Krok 4: BEZPIECZNY WIDOK DLA EKIPY (Bez dostępu do wydatków i budżetu)
CREATE OR REPLACE VIEW crew_materials_view AS
SELECT 
    id as material_id, name, status, location, quantity_received, unit, 
    available_for_crew, crew_confirmed
FROM materials 
WHERE is_deleted = FALSE AND available_for_crew = TRUE;
