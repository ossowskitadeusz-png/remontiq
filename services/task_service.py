import streamlit as st
from datetime import datetime
from typing import List, Dict, Optional

class TaskService:
    def __init__(self, supabase_client):
        self.supabase = supabase_client

    def create_task(self, project_id: str, phase_id: str, name: str, description: str = "", estimated_duration_days: int = None) -> Dict:
        """Tworzy nowe zadanie w wybranym pokoju/fazie."""
        # Domyślny stempel Handshake dla nowego zadania
        initial_handshake = (
            "--- DANE NEGOCJACYJNE ---\n"
            "COMMERCIAL: TO_BE_VALUED\n"
            "EXECUTION: NOT_READY\n"
            "LOCKED_PRICE: 0.0\n"
            "LAST_COMMENT: Nowe zadanie do wyceny\n"
            "------------------------\n\n"
        )
        
        data = {
            "project_id": project_id,
            "phase_id": phase_id,
            "name": name,
            "description": initial_handshake + description,
            "kanban_status": "TODO",
            "state": "TODO",
            "commercial_status": "pending",
            "created_at": datetime.now().isoformat()
        }

        
        res = self.supabase.table("tasks").insert(data).execute()
        return res.data[0] if res.data else {}

    def get_tasks_by_project(self, project_id: str) -> List[Dict]:
        """Pobiera wszystkie zadania dla projektu."""
        res = self.supabase.table("tasks").select("*").eq("project_id", project_id).execute()
        return res.data or []

    def get_tasks_by_phase(self, phase_id: str) -> List[Dict]:
        """Pobiera zadania dla konkretnego pokoju/fazy."""
        res = self.supabase.table("tasks").select("*").eq("phase_id", phase_id).execute()
        return res.data or []

    def update_task(self, task_id: str, update_data: Dict) -> Dict:
        """Aktualizuje dane zadania."""
        update_data["updated_at"] = datetime.now().isoformat()
        res = self.supabase.table("tasks").update(update_data).eq("id", task_id).execute()
        return res.data[0] if res.data else {}

    def delete_task(self, task_id: str) -> bool:
        """Usuwa zadanie z bazy."""
        try:
            self.supabase.table("tasks").delete().eq("id", task_id).execute()
            return True
        except:
            return False

    def sync_handshake_status(self, task_id: str, commercial_status: str, price: float, comment: str = ""):
        """
        Kluczowa metoda: Synchronizuje stary system tekstowy Handshake 
        z nowymi polami w bazie danych.
        """
        task = self.supabase.table("tasks").select("description").eq("id", task_id).single().execute().data
        if not task: return
        
        desc = task.get('description', '') or ''
        # Czyścimy stary stempel jeśli istnieje
        if "--- DANE NEGOCJACYJNE ---" in desc:
            desc = desc.split("------------------------")[-1].strip()
            
        execution_status = "TODO" if commercial_status == "ACCEPTED_LOCKED" else "NOT_READY"
        
        meta_tag = (
            f"--- DANE NEGOCJACYJNE ---\n"
            f"COMMERCIAL: {commercial_status}\n"
            f"EXECUTION: {execution_status}\n"
            f"LOCKED_PRICE: {price}\n"
            f"LAST_COMMENT: {comment}\n"
            f"------------------------\n\n"
        )
        
        update_payload = {
            "description": meta_tag + desc,
            "final_approved_price": price if commercial_status == "ACCEPTED_LOCKED" else None,
            "commercial_status": "approved" if commercial_status == "ACCEPTED_LOCKED" else "pending",
            "updated_at": datetime.now().isoformat()
        }
        
        self.supabase.table("tasks").update(update_payload).eq("id", task_id).execute()
