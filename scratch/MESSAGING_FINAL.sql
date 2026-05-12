-- ============================================================================
-- MESSAGING SYSTEM v1.0 (PRODUCTION)
-- ============================================================================

-- CZĘŚĆ 1: TABELA WIADOMOŚCI
CREATE TABLE IF NOT EXISTS public.messages (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    project_id UUID NOT NULL REFERENCES public.project_metadata(id) ON DELETE CASCADE,
    task_id UUID REFERENCES public.tasks(id) ON DELETE CASCADE,
    sender_id UUID REFERENCES auth.users(id) ON DELETE SET NULL,
    sender_role TEXT NOT NULL DEFAULT 'SYSTEM' CHECK (sender_role IN ('INVESTOR', 'CREW_LEAD', 'CREW_MEMBER', 'SYSTEM')),
    sender_display_name TEXT,
    recipient_role TEXT NOT NULL DEFAULT 'BOTH' CHECK (recipient_role IN ('INVESTOR', 'CREW', 'BOTH')),
    content TEXT NOT NULL,
    message_type TEXT NOT NULL DEFAULT 'TEXT' CHECK (message_type IN ('TEXT', 'SYSTEM', 'PRICE_UPDATE', 'STATUS_CHANGE')),
    metadata JSONB DEFAULT '{}',
    is_read BOOLEAN DEFAULT FALSE,
    read_by_investor_at TIMESTAMPTZ,
    read_by_crew_at TIMESTAMPTZ,
    created_at TIMESTAMPTZ DEFAULT now(),
    updated_at TIMESTAMPTZ DEFAULT now(),
    CONSTRAINT valid_task_or_global CHECK ((task_id IS NOT NULL) OR (recipient_role IS NOT NULL))
);

CREATE INDEX IF NOT EXISTS idx_messages_project_id ON public.messages(project_id);
CREATE INDEX IF NOT EXISTS idx_messages_task_id ON public.messages(task_id);
CREATE INDEX IF NOT EXISTS idx_messages_created_at ON public.messages(created_at DESC);

-- CZĘŚĆ 2: TRIGGER NA ZMIANY STANU
CREATE OR REPLACE FUNCTION public.log_task_state_change() RETURNS TRIGGER AS $$
DECLARE
    v_old_state TEXT; v_new_state TEXT; v_changer_name TEXT;
BEGIN
    IF NEW.state IS DISTINCT FROM OLD.state THEN
        v_old_state := COALESCE(OLD.state, 'N/A');
        v_new_state := COALESCE(NEW.state, 'N/A');
        SELECT full_name INTO v_changer_name FROM auth.users WHERE id = NEW.state_changed_by LIMIT 1;
        v_changer_name := COALESCE(v_changer_name, 'System');
        INSERT INTO public.messages (project_id, task_id, sender_id, sender_role, sender_display_name, recipient_role, content, message_type, metadata, created_at)
        VALUES (NEW.project_id, NEW.id, NEW.state_changed_by, CASE WHEN NEW.state_changed_by IS NULL THEN 'SYSTEM' ELSE 'CREW_LEAD' END, v_changer_name, 'BOTH', format('Status: %s → %s', v_old_state, v_new_state), 'STATUS_CHANGE', jsonb_build_object('old_state', v_old_state, 'new_state', v_new_state, 'changed_by_id', NEW.state_changed_by, 'changed_reason', NEW.state_changed_reason), now());
    END IF;
    RETURN NEW;
END;
$$ LANGUAGE plpgsql;

DROP TRIGGER IF EXISTS trg_log_state_change ON public.tasks;
CREATE TRIGGER trg_log_state_change BEFORE UPDATE OF state ON public.tasks FOR EACH ROW EXECUTE FUNCTION public.log_task_state_change();

-- CZĘŚĆ 3: TRIGGER NA ZMIANY CENY
CREATE OR REPLACE FUNCTION public.log_task_price_change() RETURNS TRIGGER AS $$
DECLARE
    v_old_price NUMERIC; v_new_price NUMERIC;
BEGIN
    IF NEW.final_approved_price IS DISTINCT FROM OLD.final_approved_price THEN
        v_old_price := OLD.final_approved_price;
        v_new_price := NEW.final_approved_price;
        INSERT INTO public.messages (project_id, task_id, sender_id, sender_role, sender_display_name, recipient_role, content, message_type, metadata, created_at)
        VALUES (NEW.project_id, NEW.id, NEW.state_changed_by, 'CREW_LEAD', (SELECT full_name FROM auth.users WHERE id = NEW.state_changed_by LIMIT 1), 'INVESTOR', format('Zmiana ceny: %s PLN → %s PLN', v_old_price, v_new_price), 'PRICE_UPDATE', jsonb_build_object('old_price', v_old_price, 'new_price', v_new_price, 'price_diff_pct', ROUND(((v_new_price - v_old_price) / NULLIF(v_old_price, 0)) * 100, 2)), now());
    END IF;
    RETURN NEW;
END;
$$ LANGUAGE plpgsql;

DROP TRIGGER IF EXISTS trg_log_price_change ON public.tasks;
CREATE TRIGGER trg_log_price_change BEFORE UPDATE OF final_approved_price ON public.tasks FOR EACH ROW EXECUTE FUNCTION public.log_task_price_change();

-- CZĘŚĆ 4: RPC FUNCTIONS
CREATE OR REPLACE FUNCTION public.get_unread_messages_for_user(p_user_id UUID, p_user_role TEXT) RETURNS TABLE (id UUID, project_id UUID, task_id UUID, sender_display_name TEXT, message_type TEXT, content TEXT, created_at TIMESTAMPTZ) AS $$
BEGIN
    RETURN QUERY
    SELECT m.id, m.project_id, m.task_id, m.sender_display_name, m.message_type, m.content, m.created_at
    FROM public.messages m
    WHERE m.project_id IN (SELECT p.id FROM public.project_metadata p WHERE p.user_id = p_user_id UNION SELECT t.project_id FROM public.teams t WHERE t.user_id = p_user_id)
    AND m.recipient_role IN (p_user_role, 'BOTH')
    AND ((p_user_role = 'INVESTOR' AND m.read_by_investor_at IS NULL) OR (p_user_role = 'CREW_LEAD' AND m.read_by_crew_at IS NULL))
    ORDER BY m.created_at DESC;
END;
$$ LANGUAGE plpgsql;

CREATE OR REPLACE FUNCTION public.mark_messages_as_read(p_message_ids UUID[], p_user_role TEXT) RETURNS INT AS $$
DECLARE v_count INT;
BEGIN
    UPDATE public.messages SET is_read = TRUE, read_by_investor_at = CASE WHEN p_user_role = 'INVESTOR' THEN now() ELSE read_by_investor_at END, read_by_crew_at = CASE WHEN p_user_role = 'CREW_LEAD' THEN now() ELSE read_by_crew_at END WHERE id = ANY(p_message_ids);
    GET DIAGNOSTICS v_count = ROW_COUNT;
    RETURN v_count;
END;
$$ LANGUAGE plpgsql;
