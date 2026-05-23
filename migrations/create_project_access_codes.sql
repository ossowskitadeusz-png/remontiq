-- Skrypt do utworzenia tabeli na kody dostępu (Gatekeeper) dla ekip remontowych

CREATE TABLE IF NOT EXISTS public.project_access_codes (
    id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    project_id uuid NOT NULL REFERENCES public.project_metadata(id) ON DELETE CASCADE,
    role text NOT NULL CHECK (role IN ('crew')),
    label text,
    code_hash text NOT NULL UNIQUE,
    active boolean NOT NULL DEFAULT true,
    created_at timestamptz NOT NULL DEFAULT now(),
    used_at timestamptz
);

CREATE INDEX IF NOT EXISTS idx_project_access_codes_project_id
ON public.project_access_codes(project_id);

CREATE INDEX IF NOT EXISTS idx_project_access_codes_code_hash
ON public.project_access_codes(code_hash);

CREATE INDEX IF NOT EXISTS idx_project_access_codes_active
ON public.project_access_codes(active);
