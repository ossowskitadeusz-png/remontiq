-- ============================================
-- SPRINT 5: PROJECT CHARTER IMPLEMENTATION
-- ============================================

DROP TABLE IF EXISTS project_metadata CASCADE;

CREATE TABLE project_metadata (
    id BIGSERIAL PRIMARY KEY,
    project_name VARCHAR(255) NOT NULL,
    project_description TEXT,
    
    -- 🎯 GŁÓWNE DATY
    planned_start_date DATE NOT NULL,
    planned_end_date DATE NOT NULL,
    actual_start_date DATE,
    actual_end_date DATE,
    
    -- 📊 GŁÓWNY BUDŻET
    total_budget DECIMAL(12, 2) NOT NULL,
    
    -- 👥 ZESPÓŁ
    investor_name VARCHAR(255),
    crew_lead_name VARCHAR(255),
    crew_contact VARCHAR(20),
    investor_contact VARCHAR(20),
    
    -- 📝 NOTATKI
    scope_of_work TEXT,
    special_conditions TEXT,
    
    -- ⚙️ STATUS
    status VARCHAR(50) DEFAULT 'PLANNING',
    
    created_at TIMESTAMP WITH TIME ZONE DEFAULT NOW(),
    updated_at TIMESTAMP WITH TIME ZONE DEFAULT NOW(),
    created_by VARCHAR(255),
    is_deleted BOOLEAN DEFAULT FALSE
);

CREATE INDEX idx_project_status ON project_metadata(status);
CREATE INDEX idx_project_dates ON project_metadata(planned_start_date, planned_end_date);
CREATE INDEX idx_project_created ON project_metadata(created_at DESC);

-- Disable RLS to match current MVP security model
ALTER TABLE project_metadata DISABLE ROW LEVEL SECURITY;
