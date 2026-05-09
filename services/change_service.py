"""
ChangeService — Zarządzanie zmianami w planie (opóźnienia, wzrosty budżetu, itp.)
Odpowiada za: zgłaszanie zmian, zatwierdzanie, historia, kaskadowe przesunięcia
"""

from typing import List, Dict, Optional
from datetime import datetime, timedelta
import json
import uuid
from supabase import Client


class ChangeService:
    """
    Serwis do obsługi zmian w planie remontowym.
    Umożliwia Karolowi żądanie zmian (czasu/budżetu), Tobie zatwierdzanie.
    """
    
    def __init__(self, supabase: Client):
        """Inicjalizacja serwisu z połączeniem do Supabase"""
        self.supabase = supabase
        self.changes_table = "plan_changes"
        self.tasks_table = "tasks"
        self.phases_table = "project_phases"
    
    # ============================================================================
    # 1. ZGŁASZANIE ZMIAN (Karol mówi: "Potrzebujemy więcej czasu/pieniędzy")
    # ============================================================================
    
    def request_change(
        self,
        project_id: str,
        change_type: str,
        phase_id: Optional[str] = None,
        task_id: Optional[str] = None,
        old_value: Dict = None,
        new_value: Dict = None,
        reason: str = "",
        requested_by_role: str = "crew"
    ) -> Dict:
        """
        Karol żąda zmiany w planie (np. +2 dni, +5000 PLN).
        
        Args:
            project_id: ID projektu
            change_type: Typ zmiany ('DURATION_EXTENDED', 'BUDGET_INCREASED', 'SCOPE_CHANGE')
            phase_id: ID fazy (opcjonalne)
            task_id: ID zadania (opcjonalne)
            old_value: Dict ze starymi wartościami {'duration_days': 10, 'budget': 5000}
            new_value: Dict z nowymi wartościami
            reason: Powód zmiany (np. "Materiały niedostępne", "Praca bardziej skomplikowana")
            requested_by_role: 'crew' lub 'investor'
        
        Returns:
            Dict z rezultatem zgłoszenia
        """
        
        try:
            change_id = str(uuid.uuid4())
            
            if old_value is None:
                old_value = {}
            if new_value is None:
                new_value = {}
            
            payload = {
                "id": change_id,
                "project_id": project_id,
                "phase_id": phase_id,
                "task_id": task_id,
                "change_type": change_type,
                "old_value": json.dumps(old_value),
                "new_value": json.dumps(new_value),
                "reason": reason,
                "requested_by_role": requested_by_role,
                "status": "PENDING",
                "created_at": datetime.now().isoformat()
            }
            
            response = self.supabase.table(self.changes_table).insert(payload).execute()
            
            if response.data:
                return {
                    "success": True,
                    "change_id": change_id,
                    "message": f"Zgłoszona zmiana: {change_type}",
                    "details": {
                        "old_value": old_value,
                        "new_value": new_value,
                        "reason": reason,
                        "status": "PENDING"
                    }
                }
            else:
                return {
                    "success": False,
                    "error": "Nie udało się zgłosić zmiany"
                }
        
        except Exception as e:
            return {
                "success": False,
                "error": f"Błąd: {str(e)}"
            }
    
    def request_time_extension(
        self,
        phase_id: str,
        additional_days: int,
        reason: str = ""
    ) -> Dict:
        """
        Karol żąda rozszerzenia czasu fazy.
        
        Args:
            phase_id: ID fazy
            additional_days: O ile dni rozszerzyć
            reason: Powód
        
        Returns:
            Dict z rezultatem
        """
        
        try:
            # Pobierz fazę aby uzyskać obecne daty
            phase_response = self.supabase.table(self.phases_table).select(
                "id, project_id, planned_end_date"
            ).eq("id", phase_id).single().execute()
            
            phase = phase_response.data
            if not phase:
                return {
                    "success": False,
                    "error": "Faza nie znaleziona"
                }
            
            old_end = phase["planned_end_date"]
            new_end = (
                datetime.fromisoformat(old_end) + timedelta(days=additional_days)
            ).date().isoformat()
            
            return self.request_change(
                project_id=phase["project_id"],
                change_type="DURATION_EXTENDED",
                phase_id=phase_id,
                old_value={"planned_end_date": old_end, "days": 0},
                new_value={"planned_end_date": new_end, "additional_days": additional_days},
                reason=reason or f"Rozszerzenie o {additional_days} dni",
                requested_by_role="crew"
            )
        
        except Exception as e:
            return {
                "success": False,
                "error": f"Błąd: {str(e)}"
            }
    
    def request_budget_increase(
        self,
        phase_id: str,
        additional_amount: float,
        reason: str = ""
    ) -> Dict:
        """
        Karol żąda wzrostu budżetu.
        
        Args:
            phase_id: ID fazy
            additional_amount: O ile zwiększyć budżet (PLN)
            reason: Powód
        
        Returns:
            Dict z rezultatem
        """
        
        try:
            phase_response = self.supabase.table(self.phases_table).select(
                "id, project_id, estimated_budget"
            ).eq("id", phase_id).single().execute()
            
            phase = phase_response.data
            if not phase:
                return {
                    "success": False,
                    "error": "Faza nie znaleziona"
                }
            
            old_budget = float(phase["estimated_budget"] or 0)
            new_budget = old_budget + additional_amount
            
            return self.request_change(
                project_id=phase["project_id"],
                change_type="BUDGET_INCREASED",
                phase_id=phase_id,
                old_value={"budget": old_budget},
                new_value={"budget": new_budget},
                reason=reason or f"Wzrost budżetu o {additional_amount} PLN",
                requested_by_role="crew"
            )
        
        except Exception as e:
            return {
                "success": False,
                "error": f"Błąd: {str(e)}"
            }
    
    # ============================================================================
    # 2. ZATWIERDZANIE ZMIAN (Ty decydujesz: OK czy NIE)
    # ============================================================================
    
    def approve_change(
        self,
        change_id: str,
        approval_notes: str = ""
    ) -> Dict:
        """
        Zatwierdzasz zmianę zaproponowaną przez Karola.
        
        Args:
            change_id: ID zmiany
            approval_notes: Twoje notatki
        
        Returns:
            Dict z rezultatem
        """
        
        try:
            # Pobierz zmianę
            change_response = self.supabase.table(self.changes_table).select(
                "*"
            ).eq("id", change_id).single().execute()
            
            change = change_response.data
            if not change:
                return {
                    "success": False,
                    "error": "Zmiana nie znaleziona"
                }
            
            # Aktualizuj status zmiany
            update_payload = {
                "status": "APPROVED",
                "approved_by_id": "INVESTOR"  # Możesz tu dodać ID użytkownika
            }
            
            response = self.supabase.table(self.changes_table).update(
                update_payload
            ).eq("id", change_id).execute()
            
            if not response.data:
                return {
                    "success": False,
                    "error": "Nie udało się zatwierdzić zmiany"
                }
            
            # TERAZ: Zastosuj zmianę w bazie
            phase_id = change.get("phase_id")
            task_id = change.get("task_id")
            change_type = change.get("change_type")
            new_value = json.loads(change.get("new_value", "{}"))
            
            applied = self._apply_change(phase_id, task_id, change_type, new_value)
            
            if not applied["success"]:
                return {
                    "success": False,
                    "error": f"Zmiana zatwierdzona, ale nie zastosowana: {applied['error']}"
                }
            
            # Jeśli zmiana była czasowa, wykonaj kaskadę
            if change_type == "DURATION_EXTENDED" and phase_id:
                self._cascade_dependent_phases(phase_id, change)
            
            return {
                "success": True,
                "change_id": change_id,
                "message": "Zmiana zatwierdzona i zastosowana",
                "change_type": change_type,
                "applied_to": {
                    "phase_id": phase_id,
                    "task_id": task_id
                },
                "approval_notes": approval_notes
            }
        
        except Exception as e:
            return {
                "success": False,
                "error": f"Błąd: {str(e)}"
            }
    
    def reject_change(
        self,
        change_id: str,
        rejection_reason: str = ""
    ) -> Dict:
        """
        Odrzucasz zmianę zaproponowaną przez Karola.
        
        Args:
            change_id: ID zmiany
            rejection_reason: Powód odrzucenia
        
        Returns:
            Dict z rezultatem
        """
        
        try:
            update_payload = {
                "status": "REJECTED"
            }
            
            response = self.supabase.table(self.changes_table).update(
                update_payload
            ).eq("id", change_id).execute()
            
            if response.data:
                return {
                    "success": True,
                    "change_id": change_id,
                    "message": "Zmiana odrzucona",
                    "rejection_reason": rejection_reason
                }
            else:
                return {
                    "success": False,
                    "error": "Nie udało się odrzucić zmiany"
                }
        
        except Exception as e:
            return {
                "success": False,
                "error": f"Błąd: {str(e)}"
            }
    
    # ============================================================================
    # 3. ZASTOSOWANIE ZMIAN (Wewnętrzne)
    # ============================================================================
    
    def _apply_change(
        self,
        phase_id: Optional[str],
        task_id: Optional[str],
        change_type: str,
        new_value: Dict
    ) -> Dict:
        """
        Wewnętrzna funkcja: faktycznie zastosuj zmianę do bazy.
        """
        
        try:
            if phase_id:
                # Zmiana dotyczy fazy
                update_data = {}
                
                if change_type == "DURATION_EXTENDED":
                    update_data["planned_end_date"] = new_value.get("planned_end_date")
                
                elif change_type == "BUDGET_INCREASED":
                    update_data["estimated_budget"] = new_value.get("budget")
                
                if update_data:
                    response = self.supabase.table(self.phases_table).update(
                        update_data
                    ).eq("id", phase_id).execute()
                    
                    if response.data:
                        return {"success": True}
            
            elif task_id:
                # Zmiana dotyczy zadania
                update_data = {}
                
                if change_type == "DURATION_EXTENDED":
                    update_data["planned_end_date"] = new_value.get("planned_end_date")
                
                if update_data:
                    response = self.supabase.table(self.tasks_table).update(
                        update_data
                    ).eq("id", task_id).execute()
                    
                    if response.data:
                        return {"success": True}
            
            return {"success": False, "error": "Nie można zastosować zmiany"}
        
        except Exception as e:
            return {"success": False, "error": str(e)}
    
    def _cascade_dependent_phases(self, phase_id: str, change: Dict) -> Dict:
        """
        Wewnętrzna funkcja: gdy faza jest przedłużona, przesunąć fazy zależne.
        """
        
        try:
            new_value = json.loads(change.get("new_value", "{}"))
            old_value = json.loads(change.get("old_value", "{}"))
            
            old_end = old_value.get("planned_end_date")
            new_end = new_value.get("planned_end_date")
            
            if not old_end or not new_end:
                return {"success": False, "error": "Brakuje dat"}
            
            old_end_date = datetime.fromisoformat(old_end).date()
            new_end_date = datetime.fromisoformat(new_end).date()
            days_shift = (new_end_date - old_end_date).days
            
            # Pobierz wszystkie fazy projektu
            all_phases = self.supabase.table(self.phases_table).select(
                "id, depends_on_phase_ids"
            ).eq("project_id", change.get("project_id")).execute().data or []
            
            # Znajdź fazy zależne
            shifted_count = 0
            for other_phase in all_phases:
                deps = other_phase.get("depends_on_phase_ids", "[]")
                if isinstance(deps, str):
                    try:
                        deps = json.loads(deps)
                    except:
                        deps = []
                
                if phase_id in deps:
                    # Ta faza zależy od zmienionej fazy, przesunięcie
                    shift_result = self._shift_phase_dates(
                        other_phase["id"], days_shift
                    )
                    if shift_result["success"]:
                        shifted_count += 1
            
            return {
                "success": True,
                "shifted_dependent_phases": shifted_count,
                "days_shift": days_shift
            }
        
        except Exception as e:
            return {"success": False, "error": str(e)}
    
    def _shift_phase_dates(self, phase_id: str, days: int) -> Dict:
        """
        Wewnętrzna funkcja: przesunięcie dat fazy.
        """
        
        try:
            phase = self.supabase.table(self.phases_table).select(
                "planned_start_date, planned_end_date"
            ).eq("id", phase_id).single().execute().data
            
            if not phase:
                return {"success": False, "error": "Faza nie znaleziona"}
            
            start = datetime.fromisoformat(phase["planned_start_date"]).date()
            end = datetime.fromisoformat(phase["planned_end_date"]).date()
            
            new_start = (start + timedelta(days=days)).isoformat()
            new_end = (end + timedelta(days=days)).isoformat()
            
            response = self.supabase.table(self.phases_table).update({
                "planned_start_date": new_start,
                "planned_end_date": new_end
            }).eq("id", phase_id).execute()
            
            return {"success": bool(response.data)}
        
        except Exception as e:
            return {"success": False, "error": str(e)}
    
    # ============================================================================
    # 4. POBIERANIE HISTORII ZMIAN
    # ============================================================================
    
    def get_pending_changes(self, project_id: str = None) -> List[Dict]:
        """
        Pobiera wszystkie oczekujące na zatwierdzenie zmiany.
        
        Returns:
            Lista zmian w statusie PENDING
        """
        
        try:
            query = self.supabase.table(self.changes_table).select(
                "id, change_type, old_value, new_value, reason, "
                "requested_by_role, created_at, phase_id, task_id"
            ).eq("status", "PENDING")
            
            if project_id:
                query = query.eq("project_id", project_id)
            
            response = query.order("created_at", desc=True).execute()
            
            changes = response.data or []
            
            # Parsuj JSON
            for change in changes:
                change["old_value"] = json.loads(change.get("old_value", "{}"))
                change["new_value"] = json.loads(change.get("new_value", "{}"))
            
            return changes
        
        except Exception as e:
            print(f"Błąd: {str(e)}")
            return []
    
    def get_change_history(self, project_id: str = None, limit: int = 50) -> List[Dict]:
        """
        Pobiera historię wszystkich zmian (zatwierdzone i odrzucone).
        
        Returns:
            Lista zmian posortowana chronologicznie
        """
        
        try:
            query = self.supabase.table(self.changes_table).select(
                "id, change_type, status, old_value, new_value, reason, "
                "requested_by_role, created_at, phase_id, task_id"
            )
            
            if project_id:
                query = query.eq("project_id", project_id)
            
            response = query.order("created_at", desc=True).limit(limit).execute()
            
            changes = response.data or []
            
            for change in changes:
                change["old_value"] = json.loads(change.get("old_value", "{}"))
                change["new_value"] = json.loads(change.get("new_value", "{}"))
            
            return changes
        
        except Exception as e:
            print(f"Błąd: {str(e)}")
            return []
    
    def get_phase_change_history(self, phase_id: str) -> List[Dict]:
        """
        Pobiera historię zmian dla konkretnej fazy.
        """
        
        try:
            response = self.supabase.table(self.changes_table).select(
                "*"
            ).eq("phase_id", phase_id).order("created_at", desc=True).execute()
            
            changes = response.data or []
            
            for change in changes:
                change["old_value"] = json.loads(change.get("old_value", "{}"))
                change["new_value"] = json.loads(change.get("new_value", "{}"))
            
            return changes
        
        except Exception as e:
            print(f"Błąd: {str(e)}")
            return []
    
    # ============================================================================
    # 5. STATYSTYKI ZMIAN
    # ============================================================================
    
    def get_change_statistics(self, project_id: str = None) -> Dict:
        """
        Zwraca statystyki zmian w projekcie.
        
        Returns:
            Dict ze statystykami (liczba zatwierdzeń, odrzuceń, itp.)
        """
        
        try:
            query = self.supabase.table(self.changes_table).select("status, change_type")
            
            if project_id:
                query = query.eq("project_id", project_id)
            
            response = query.execute()
            changes = response.data or []
            
            pending = sum(1 for c in changes if c.get("status") == "PENDING")
            approved = sum(1 for c in changes if c.get("status") == "APPROVED")
            rejected = sum(1 for c in changes if c.get("status") == "REJECTED")
            
            time_changes = sum(1 for c in changes if c.get("change_type") == "DURATION_EXTENDED")
            budget_changes = sum(1 for c in changes if c.get("change_type") == "BUDGET_INCREASED")
            
            return {
                "total_changes": len(changes),
                "pending": pending,
                "approved": approved,
                "rejected": rejected,
                "time_extension_requests": time_changes,
                "budget_increase_requests": budget_changes,
                "approval_rate": round(
                    (approved / (approved + rejected) * 100) 
                    if (approved + rejected) > 0 else 0, 1
                )
            }
        
        except Exception as e:
            return {"error": str(e)}
    
    # ============================================================================
    # 6. EXPORT ZMIAN
    # ============================================================================
    
    def export_changes_to_dict(self, project_id: str = None) -> List[Dict]:
        """
        Eksportuje wszystkie zmiany do formatu słownika.
        """
        
        try:
            query = self.supabase.table(self.changes_table).select("*")
            
            if project_id:
                query = query.eq("project_id", project_id)
            
            response = query.execute()
            changes = response.data or []
            
            export_data = []
            for change in changes:
                export_data.append({
                    "Change ID": change.get("id"),
                    "Type": change.get("change_type"),
                    "Status": change.get("status"),
                    "Phase ID": change.get("phase_id"),
                    "Task ID": change.get("task_id"),
                    "Requested By": change.get("requested_by_role"),
                    "Reason": change.get("reason"),
                    "Created": change.get("created_at")
                })
            
            return export_data
        
        except Exception as e:
            print(f"Błąd: {str(e)}")
            return []


# ============================================================================
# TEST
# ============================================================================

if __name__ == "__main__":
    print("ChangeService loaded successfully")
