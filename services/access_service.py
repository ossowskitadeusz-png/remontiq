import os
import random
import string
import hashlib

def generate_access_code(length=8):
    """Generuje losowy kod dostępu w formacie EKIPA-XXXX-XXXX."""
    chars = ''.join(random.choices(string.ascii_uppercase + string.digits, k=length))
    return f"EKIPA-{chars[:4]}-{chars[4:]}"

def normalize_access_code(code: str) -> str:
    """Normalizuje kod dostępu (usuwa spacje, wielkie litery)."""
    if not code: return ""
    return str(code).strip().upper()

def hash_access_code(code: str) -> str:
    """Ze względu na konieczność pokazywania kodu inwestorowi, rezygnujemy z hashowania i zapisujemy znormalizowany kod."""
    return normalize_access_code(code)

def create_crew_access_code(project_id: str, supabase_client, label: str = "Domyślna Ekipa") -> str:
    """Tworzy nowy kod dostępu dla ekipy i zapisuje hash w bazie."""
    code = generate_access_code()
    code_hash = hash_access_code(code)
    
    # Dezaktywacja starych kodów
    deactivate_project_crew_codes(project_id, supabase_client)
    
    # Zapis nowego kodu
    supabase_client.table("project_access_codes").insert({
        "project_id": project_id,
        "role": "crew",
        "label": label,
        "code_hash": code_hash,
        "active": True
    }).execute()
    
    return code

def deactivate_project_crew_codes(project_id: str, supabase_client):
    """Dezaktywuje wszystkie dotychczasowe kody dla danego projektu."""
    supabase_client.table("project_access_codes").update({"active": False}).eq("project_id", project_id).eq("role", "crew").execute()

def get_active_crew_code(project_id: str, supabase_client) -> str:
    """Pobiera aktywny kod dla ekipy, jeśli istnieje."""
    res = supabase_client.table("project_access_codes").select("code_hash").eq("project_id", project_id).eq("role", "crew").eq("active", True).execute()
    if res.data and len(res.data) > 0:
        return res.data[0]["code_hash"]
    return None

def active_crew_code_exists(project_id: str, supabase_client) -> bool:
    """Sprawdza czy projekt posiada aktywny kod dla ekipy."""
    return bool(get_active_crew_code(project_id, supabase_client))

def validate_crew_access_code(code: str, supabase_client) -> dict:
    """Weryfikuje wpisany kod i ewentualnie zwraca rekord z bazy, jeśli kod jest prawidłowy i aktywny."""
    code_hash = hash_access_code(code)
    res = supabase_client.table("project_access_codes").select("*").eq("code_hash", code_hash).eq("active", True).eq("role", "crew").execute()
    if res.data and len(res.data) > 0:
        return res.data[0]
    return None
