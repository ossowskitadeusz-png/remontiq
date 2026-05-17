"""
PhaseService — Zarządzanie fazami projektu remontowego
Odpowiada za: tworzenie faz, zmianę statusów, obliczanie postępu, kaskadowe przesunięcia
"""

from typing import List, Dict, Optional, Tuple
from datetime import datetime, timedelta
import json
import uuid
from supabase import Client


class PhaseService:
    """
    Serwis do obsługi faz remontowych.
    Każda faza to logiczna część projektu (np. Elektryka, Hydraulika, Panele).
    """
    
    def __init__(self, supabase: Client):
        """Inicjalizacja serwisu z połączeniem do Supabase"""
        self.supabase = supabase
        self.table_name = "project_phases"
        self.tasks_table = "tasks"
    
    # ============================================================================
    # 1. TWORZENIE I POBIERANIE FAZ
    # ============================================================================
    
    def create_phase(
        self,
        project_id: str,
        phase_name: str,
        phase_number: int = 1,
        planned_start_date: str = None,
        planned_end_date: str = None,
        description: str = "",
        estimated_budget: float = 0.0,
        created_by_crew_id: str = None,
        depends_on_phase_ids: List[str] = None
    ) -> Dict:
        """
        Tworzy nową fazę w projekcie.
        
        Args:
            project_id: ID projektu
            phase_name: Nazwa fazy (np. "Elektryka")
            phase_number: Numer porządkowy (1, 2, 3...)
            planned_start_date: Data rozpoczęcia (format: "YYYY-MM-DD")
            planned_end_date: Data zakończenia (format: "YYYY-MM-DD")
            description: Opis fazy
            estimated_budget: Szacunkowy budżet
            created_by_crew_id: ID osoby, która tworzy fazę (Karol)
            depends_on_phase_ids: Lista ID faz, od których ta zależy
        
        Returns:
            Dict z danymi nowej fazy lub error
        """
        
        if depends_on_phase_ids is None:
            depends_on_phase_ids = []
        
        try:
            phase_id = str(uuid.uuid4())
            
            payload = {
                "id": phase_id,
                "project_id": project_id,
                "phase_name": phase_name,
                "phase_number": phase_number,
                "description": description,
                "planned_start_date": planned_start_date or datetime.now().date().isoformat(),
                "planned_end_date": planned_end_date or (datetime.now() + timedelta(days=14)).date().isoformat(),
                "status": "PLANNING",
                "estimated_budget": estimated_budget,
                "actual_spent": 0.0,
                "depends_on_phase_ids": depends_on_phase_ids,
                "created_at": datetime.now().isoformat(),
                "updated_at": datetime.now().isoformat()
            }
            
            response = self.supabase.table(self.table_name).insert(payload).execute()
            
            if response.data:
                return {
                    "success": True,
                    "phase_id": phase_id,
                    "message": f"Faza '{phase_name}' utworzona pomyślnie",
                    "data": response.data[0]
                }
            else:
                return {
                    "success": False,
                    "error": "Nie udało się utworzyć fazy",
                    "details": str(response)
                }
        
        except Exception as e:
            return {
                "success": False,
                "error": f"Błąd przy tworzeniu fazy: {str(e)}"
            }
    
    def get_phases(self, project_id: str) -> List[Dict]:
        """
        Pobiera wszystkie fazy dla danego projektu.
        
        Args:
            project_id: ID projektu
        
        Returns:
            Lista faz posortowana po phase_number
        """
        try:
            response = self.supabase.table(self.table_name).select(
                "*"
            ).eq("project_id", project_id).order("phase_number").execute()
            
            phases = response.data or []
            
            # Parsuj depends_on_phase_ids z JSON
            for phase in phases:
                if isinstance(phase.get("depends_on_phase_ids"), str):
                    try:
                        phase["depends_on_phase_ids"] = json.loads(
                            phase["depends_on_phase_ids"]
                        )
                    except:
                        phase["depends_on_phase_ids"] = []
            
            return phases
        
        except Exception as e:
            print(f"Błąd przy pobieraniu faz: {str(e)}")
            return []
    
    def get_phase_by_id(self, phase_id: str) -> Optional[Dict]:
        """
        Pobiera szczegóły konkretnej fazy.
        
        Args:
            phase_id: ID fazy
        
        Returns:
            Dict z danymi fazy lub None
        """
        try:
            response = self.supabase.table(self.table_name).select(
                "*"
            ).eq("id", phase_id).single().execute()
            
            phase = response.data
            if phase and isinstance(phase.get("depends_on_phase_ids"), str):
                try:
                    phase["depends_on_phase_ids"] = json.loads(
                        phase["depends_on_phase_ids"]
                    )
                except:
                    phase["depends_on_phase_ids"] = []
            
            return phase
        
        except Exception as e:
            print(f"Błąd przy pobieraniu fazy: {str(e)}")
            return None
    
    # ============================================================================
    # 2. ZMIANA STATUSÓW I DANYCH FAZ
    # ============================================================================
    
    def update_phase_status(self, phase_id: str, new_status: str) -> Dict:
        """
        Zmienia status fazy (PLANNING -> IN_PROGRESS -> COMPLETED).
        
        Args:
            phase_id: ID fazy
            new_status: Nowy status (PLANNING, IN_PROGRESS, COMPLETED, PAUSED)
        
        Returns:
            Dict z rezultatem operacji
        """
        
        valid_statuses = ["PLANNING", "IN_PROGRESS", "COMPLETED", "PAUSED"]
        
        if new_status not in valid_statuses:
            return {
                "success": False,
                "error": f"Niepoprawny status. Dozwolone: {valid_statuses}"
            }
        
        try:
            update_payload = {
                "status": new_status,
                "updated_at": datetime.now().isoformat()
            }
            
            # Jeśli zmiana na IN_PROGRESS, ustaw actual_start_date
            if new_status == "IN_PROGRESS":
                update_payload["actual_start_date"] = datetime.now().date().isoformat()
            
            # Jeśli zmiana na COMPLETED, ustaw actual_end_date
            if new_status == "COMPLETED":
                update_payload["actual_end_date"] = datetime.now().date().isoformat()
            
            response = self.supabase.table(self.table_name).update(
                update_payload
            ).eq("id", phase_id).execute()
            
            if response.data:
                return {
                    "success": True,
                    "message": f"Status fazy zmieniony na {new_status}",
                    "data": response.data[0]
                }
            else:
                return {
                    "success": False,
                    "error": "Nie udało się zmienić statusu"
                }
        
        except Exception as e:
            return {
                "success": False,
                "error": f"Błąd przy zmianie statusu: {str(e)}"
            }
    
    def update_phase_dates(
        self,
        phase_id: str,
        planned_start: Optional[str] = None,
        planned_end: Optional[str] = None
    ) -> Dict:
        """
        Aktualizuje daty planów fazy.
        
        Args:
            phase_id: ID fazy
            planned_start: Nowa data rozpoczęcia
            planned_end: Nowa data zakończenia
        
        Returns:
            Dict z rezultatem
        """
        
        try:
            update_payload = {"updated_at": datetime.now().isoformat()}
            
            if planned_start:
                update_payload["planned_start_date"] = planned_start
            if planned_end:
                update_payload["planned_end_date"] = planned_end
            
            response = self.supabase.table(self.table_name).update(
                update_payload
            ).eq("id", phase_id).execute()
            
            if response.data:
                return {
                    "success": True,
                    "message": "Daty fazy zaktualizowane",
                    "data": response.data[0]
                }
            else:
                return {
                    "success": False,
                    "error": "Nie udało się zaktualizować dat"
                }
        
        except Exception as e:
            return {
                "success": False,
                "error": f"Błąd: {str(e)}"
            }
    
    # ============================================================================
    # 3. OBLICZANIE POSTĘPU I STATUSÓW
    # ============================================================================
    
    def get_phase_progress(self, phase_id: str) -> Dict:
        """
        Oblicza postęp fazy na podstawie tasków w niej zawartych.
        
        Returns:
            Dict z procentem ukończenia i liczbą tasków
        """
        
        try:
            response = self.supabase.table(self.tasks_table).select(
                "id, completion_status, kanban_status"
            ).eq("phase_id", phase_id).execute()
            
            tasks = response.data or []
            
            if not tasks:
                return {
                    "phase_id": phase_id,
                    "total_tasks": 0,
                    "completed_tasks": 0,
                    "progress_percent": 0,
                    "in_progress": 0
                }
            
            total = len(tasks)
            completed = sum(1 for t in tasks if t.get("completion_status") == "COMPLETED")
            in_progress = sum(1 for t in tasks if t.get("kanban_status") == "IN_PROGRESS")
            
            progress = (completed / total * 100) if total > 0 else 0
            
            return {
                "phase_id": phase_id,
                "total_tasks": total,
                "completed_tasks": completed,
                "progress_percent": round(progress, 1),
                "in_progress": in_progress,
                "remaining": total - completed
            }
        
        except Exception as e:
            print(f"Błąd przy obliczaniu postępu: {str(e)}")
            return {
                "phase_id": phase_id,
                "error": str(e)
            }
    
    def get_phase_financial_status(self, phase_id: str) -> Dict:
        """
        Oblicza status finansowy fazy (budżet vs rzeczywiste).
        
        Returns:
            Dict z budżetem, wydatkami, resztą
        """
        
        try:
            phase = self.get_phase_by_id(phase_id)
            if not phase:
                return {"error": "Faza nie znaleziona"}
            
            estimated_budget = float(phase.get("estimated_budget") or 0)
            actual_spent = float(phase.get("actual_spent") or 0)
            
            remaining = estimated_budget - actual_spent
            overrun = max(0, actual_spent - estimated_budget)
            
            return {
                "phase_id": phase_id,
                "estimated_budget": estimated_budget,
                "actual_spent": actual_spent,
                "remaining_budget": remaining,
                "overrun": overrun,
                "budget_utilization_percent": (
                    (actual_spent / estimated_budget * 100) 
                    if estimated_budget > 0 else 0
                ),
                "status": "UNDER_BUDGET" if remaining > 0 else "OVER_BUDGET"
            }
        
        except Exception as e:
            return {"error": str(e)}
    
    # ============================================================================
    # 4. WALIDACJE I ZALEŻNOŚCI FAZ
    # ============================================================================
    
    def check_phase_dependencies(self, phase_id: str) -> Dict:
        """
        Sprawdza, czy wszystkie fazy zależne są gotowe.
        
        Returns:
            Dict z informacją czy można zacząć fazę
        """
        
        try:
            phase = self.get_phase_by_id(phase_id)
            if not phase:
                return {"error": "Faza nie znaleziona"}
            
            depends_on = phase.get("depends_on_phase_ids", [])
            
            if not depends_on:
                return {
                    "phase_id": phase_id,
                    "can_start": True,
                    "dependencies": [],
                    "message": "Brak zależności"
                }
            
            dependency_statuses = []
            all_ready = True
            
            for dep_phase_id in depends_on:
                dep_phase = self.get_phase_by_id(dep_phase_id)
                if not dep_phase:
                    dependency_statuses.append({
                        "phase_id": dep_phase_id,
                        "status": "NOT_FOUND"
                    })
                    all_ready = False
                else:
                    is_completed = dep_phase.get("status") == "COMPLETED"
                    dependency_statuses.append({
                        "phase_id": dep_phase_id,
                        "phase_name": dep_phase.get("phase_name"),
                        "status": dep_phase.get("status"),
                        "is_completed": is_completed
                    })
                    if not is_completed:
                        all_ready = False
            
            return {
                "phase_id": phase_id,
                "can_start": all_ready,
                "dependencies": dependency_statuses,
                "message": "Wszystkie fazy zależne są gotowe" if all_ready else "Oczekiwanie na fazy zależne"
            }
        
        except Exception as e:
            return {"error": str(e)}
    
    def get_dependent_phases(self, phase_id: str) -> List[Dict]:
        """
        Zwraca fazy, które zależą od tej fazy.
        
        Returns:
            Lista faz, które czekają na zakończenie tej fazy
        """
        
        try:
            all_phases = self.supabase.table(self.table_name).select(
                "id, phase_name, status, depends_on_phase_ids"
            ).execute().data or []
            
            dependent = []
            for phase in all_phases:
                deps = phase.get("depends_on_phase_ids", "[]")
                if isinstance(deps, str):
                    try:
                        deps = json.loads(deps)
                    except:
                        deps = []
                
                if phase_id in deps:
                    dependent.append(phase)
            
            return dependent
        
        except Exception as e:
            print(f"Błąd: {str(e)}")
            return []
    
    # ============================================================================
    # 5. AUTOMATYCZNE PRZESUNIĘCIA (Kaskada)
    # ============================================================================
    
    def cascade_phase_dates(self, phase_id: str, days_shift: int) -> Dict:
        """
        Przesuwamy fazę i ALL fazy zależne (efekt domino).
        
        Args:
            phase_id: ID fazy do przesunięcia
            days_shift: Liczba dni (dodatnia = opóźnienie)
        
        Returns:
            Dict z listą przesuniętych faz
        """
        
        try:
            shifted_phases = []
            
            # Przesunięcie głównej fazy
            phase = self.get_phase_by_id(phase_id)
            if not phase:
                return {"error": "Faza nie znaleziona"}
            
            start = datetime.fromisoformat(phase["planned_start_date"])
            end = datetime.fromisoformat(phase["planned_end_date"])
            
            new_start = (start + timedelta(days=days_shift)).date().isoformat()
            new_end = (end + timedelta(days=days_shift)).date().isoformat()
            
            result = self.update_phase_dates(phase_id, new_start, new_end)
            if result["success"]:
                shifted_phases.append({
                    "phase_id": phase_id,
                    "phase_name": phase["phase_name"],
                    "new_start": new_start,
                    "new_end": new_end
                })
            
            # Rekurencyjnie przesunąć fazy zależne
            dependent = self.get_dependent_phases(phase_id)
            for dep_phase in dependent:
                self.cascade_phase_dates(dep_phase["id"], days_shift)
                shifted_phases.append({
                    "phase_id": dep_phase["id"],
                    "phase_name": dep_phase["phase_name"],
                    "cascaded": True
                })
            
            return {
                "success": True,
                "shifted_phases": shifted_phases,
                "days_shift": days_shift
            }
        
        except Exception as e:
            return {
                "success": False,
                "error": str(e)
            }
    
    # ============================================================================
    # 6. RAPORT I DASHBOARD
    # ============================================================================
    
    def get_project_timeline(self, project_id: str) -> Dict:
        """
        Zwraca całą linię czasu projektu (wszystkie fazy z datami).
        
        Returns:
            Dict z chronologicznym porządkiem faz
        """
        
        try:
            phases = self.get_phases(project_id)
            
            timeline = []
            for phase in phases:
                progress = self.get_phase_progress(phase["id"])
                financial = self.get_phase_financial_status(phase["id"])
                
                timeline.append({
                    "phase_id": phase["id"],
                    "phase_name": phase["phase_name"],
                    "phase_number": phase["phase_number"],
                    "status": phase["status"],
                    "planned_start": phase["planned_start_date"],
                    "planned_end": phase["planned_end_date"],
                    "actual_start": phase.get("actual_start_date"),
                    "actual_end": phase.get("actual_end_date"),
                    "progress_percent": progress.get("progress_percent", 0),
                    "budget_status": financial.get("status"),
                    "budget_utilization": financial.get("budget_utilization_percent", 0)
                })
            
            return {
                "project_id": project_id,
                "timeline": timeline,
                "total_phases": len(timeline),
                "completed_phases": sum(1 for p in timeline if p["status"] == "COMPLETED")
            }
        
        except Exception as e:
            return {"error": str(e)}

    def delete_phase(self, phase_id: str) -> Dict:
        """
        Usuwa fazę z bazy danych.
        
        Args:
            phase_id: ID fazy do usunięcia
            
        Returns:
            Dict z informacją o rezultacie
        """
        try:
            self.supabase.table(self.table_name).delete().eq("id", phase_id).execute()
            return {
                "success": True,
                "message": "Pomieszczenie zostało usunięte"
            }
        except Exception as e:
            return {
                "success": False,
                "error": f"Błąd podczas usuwania pomieszczenia: {str(e)}"
            }


# ============================================================================
# TEST (Do debugowania w Streamlicie)
# ============================================================================

if __name__ == "__main__":
    # Testowanie (gdy uruchomisz ten plik bezpośrednio)
    print("PhaseService loaded successfully")
