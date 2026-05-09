"""
NegotiationService — Zarządzanie negocjacjami cena/czas między Karolem a Tobą
Odpowiada za: propozycje cen, kontroferty, historię negocjacji, finalizację
"""

from typing import List, Dict, Optional
from datetime import datetime
import json
import uuid
from supabase import Client


class NegotiationService:
    """
    Serwis do obsługi negocjacji finansowych dla tasków.
    Umożliwia Karolowi propozycję ceny, Tobie kontrpropozycję, i finalizację.
    """
    
    def __init__(self, supabase: Client):
        """Inicjalizacja serwisu z połączeniem do Supabase"""
        self.supabase = supabase
        self.tasks_table = "tasks"
    
    # ============================================================================
    # 1. PROPOZYCJA CENY (Karol proponuje cenę za zadanie)
    # ============================================================================
    
    def propose_crew_price(
        self,
        task_id: str,
        proposed_price: float,
        proposed_hours: int,
        notes: str = ""
    ) -> Dict:
        """
        Karol proponuje cenę za wykonanie zadania.
        
        Args:
            task_id: ID zadania
            proposed_price: Proponowana cena (PLN)
            proposed_hours: Proponowana liczba godzin
            notes: Uwagi Karola dotyczące propozycji
        
        Returns:
            Dict z rezultatem operacji
        """
        
        try:
            # Pobierz obecne dane zadania
            task_response = self.supabase.table(self.tasks_table).select(
                "*"
            ).eq("id", task_id).single().execute()
            
            task = task_response.data
            if not task:
                return {
                    "success": False,
                    "error": "Zadanie nie znalezione"
                }
            
            # Aktualizuj zadanie z propozycją Karola
            update_payload = {
                "crew_price": proposed_price,
                "estimated_hours": proposed_hours,
                "negotiation_notes": notes,
                "commercial_status": "PROPOSED_BY_CREW",
                "created_by_crew": True,
                "updated_at": datetime.now().isoformat()
            }
            
            response = self.supabase.table(self.tasks_table).update(
                update_payload
            ).eq("id", task_id).execute()
            
            if response.data:
                return {
                    "success": True,
                    "task_id": task_id,
                    "message": f"Propozycja ceny: {proposed_price} PLN za {proposed_hours}h",
                    "data": {
                        "crew_price": proposed_price,
                        "estimated_hours": proposed_hours,
                        "commercial_status": "PROPOSED_BY_CREW",
                        "notes": notes
                    }
                }
            else:
                return {
                    "success": False,
                    "error": "Nie udało się zapisać propozycji"
                }
        
        except Exception as e:
            return {
                "success": False,
                "error": f"Błąd przy propozycji ceny: {str(e)}"
            }
    
    # ============================================================================
    # 2. KONTROFERTA (Ty robisz kontrpropozycję na cenę Karola)
    # ============================================================================
    
    def make_counter_offer(
        self,
        task_id: str,
        counter_price: float,
        counter_hours: Optional[int] = None,
        reason: str = ""
    ) -> Dict:
        """
        Jako inwestor, robisz kontrpropozycję na cenę proponowaną przez Karola.
        
        Args:
            task_id: ID zadania
            counter_price: Twoja kontroferta ceny
            counter_hours: Twoja kontroferta godzin (opcjonalne)
            reason: Powód kontrpropozycji (np. "Za drogo", "Czasowo realne")
        
        Returns:
            Dict z rezultatem
        """
        
        try:
            task_response = self.supabase.table(self.tasks_table).select(
                "*"
            ).eq("id", task_id).single().execute()
            
            task = task_response.data
            if not task:
                return {
                    "success": False,
                    "error": "Zadanie nie znalezione"
                }
            
            # Sprawdzenie: czy jest coś do kontroferty
            if task.get("commercial_status") != "PROPOSED_BY_CREW":
                return {
                    "success": False,
                    "error": "Brak propozycji do kontroferty",
                    "current_status": task.get("commercial_status")
                }
            
            # Przygotuj kontropropozcję
            update_payload = {
                "investor_counter_price": counter_price,
                "commercial_status": "COUNTER_OFFERED_BY_INVESTOR",
                "updated_at": datetime.now().isoformat()
            }
            
            if counter_hours:
                update_payload["actual_hours"] = counter_hours
            
            # Dodaj powód do notatek
            current_notes = task.get("negotiation_notes", "")
            new_notes = f"{current_notes}\n[KONTRPROPOZYCJA INWESTORA] {reason}" if reason else current_notes
            update_payload["negotiation_notes"] = new_notes
            
            response = self.supabase.table(self.tasks_table).update(
                update_payload
            ).eq("id", task_id).execute()
            
            if response.data:
                difference = task.get("crew_price", 0) - counter_price
                return {
                    "success": True,
                    "task_id": task_id,
                    "message": f"Kontrpropozycja: {counter_price} PLN",
                    "original_price": task.get("crew_price"),
                    "counter_price": counter_price,
                    "difference": difference,
                    "percentage_change": round((difference / task.get("crew_price", 1) * 100), 1) if task.get("crew_price") else 0,
                    "data": response.data[0]
                }
            else:
                return {
                    "success": False,
                    "error": "Nie udało się zapisać kontrpropozycji"
                }
        
        except Exception as e:
            return {
                "success": False,
                "error": f"Błąd: {str(e)}"
            }
    
    # ============================================================================
    # 3. AKCEPTACJA (Finalizacja negocjacji)
    # ============================================================================
    
    def accept_negotiation(
        self,
        task_id: str,
        accepted_price: float,
        accepted_hours: Optional[int] = None,
        final_notes: str = ""
    ) -> Dict:
        """
        Finalizuje negocjację — cena i czas zostają "zablokowane".
        
        Args:
            task_id: ID zadania
            accepted_price: Ostateczna cena (PLN)
            accepted_hours: Ostateczna liczba godzin
            final_notes: Notatki końcowe
        
        Returns:
            Dict z rezultatem finalizacji
        """
        
        try:
            task_response = self.supabase.table(self.tasks_table).select(
                "*"
            ).eq("id", task_id).single().execute()
            
            task = task_response.data
            if not task:
                return {
                    "success": False,
                    "error": "Zadanie nie znalezione"
                }
            
            # Przygotuj finalizację
            update_payload = {
                "locked_price": accepted_price,
                "commercial_status": "ACCEPTED_LOCKED",
                "execution_status": "READY",
                "updated_at": datetime.now().isoformat()
            }
            
            if accepted_hours:
                update_payload["estimated_hours"] = accepted_hours
            
            if final_notes:
                current_notes = task.get("negotiation_notes", "")
                update_payload["negotiation_notes"] = f"{current_notes}\n[ZAAKCEPTOWANO] {final_notes}"
            
            response = self.supabase.table(self.tasks_table).update(
                update_payload
            ).eq("id", task_id).execute()
            
            if response.data:
                return {
                    "success": True,
                    "task_id": task_id,
                    "message": "Negocjacja finalizowana",
                    "locked_price": accepted_price,
                    "locked_hours": accepted_hours,
                    "status": "ACCEPTED_LOCKED",
                    "data": response.data[0]
                }
            else:
                return {
                    "success": False,
                    "error": "Nie udało się zaakceptować negocjacji"
                }
        
        except Exception as e:
            return {
                "success": False,
                "error": f"Błąd: {str(e)}"
            }
    
    # ============================================================================
    # 4. ODRZUCENIE PROPOZYCJI
    # ============================================================================
    
    def reject_proposal(
        self,
        task_id: str,
        reason: str
    ) -> Dict:
        """
        Odrzucasz propozycję ceny Karola.
        
        Args:
            task_id: ID zadania
            reason: Powód odrzucenia
        
        Returns:
            Dict z rezultatem
        """
        
        try:
            task_response = self.supabase.table(self.tasks_table).select(
                "*"
            ).eq("id", task_id).single().execute()
            
            task = task_response.data
            if not task:
                return {
                    "success": False,
                    "error": "Zadanie nie znalezione"
                }
            
            update_payload = {
                "commercial_status": "REJECTED_BY_INVESTOR",
                "updated_at": datetime.now().isoformat()
            }
            
            current_notes = task.get("negotiation_notes", "")
            new_notes = f"{current_notes}\n[ODRZUCONO] {reason}" if reason else current_notes
            update_payload["negotiation_notes"] = new_notes
            
            response = self.supabase.table(self.tasks_table).update(
                update_payload
            ).eq("id", task_id).execute()
            
            if response.data:
                return {
                    "success": True,
                    "task_id": task_id,
                    "message": "Propozycja odrzucona",
                    "reason": reason,
                    "data": response.data[0]
                }
            else:
                return {
                    "success": False,
                    "error": "Nie udało się odrzucić propozycji"
                }
        
        except Exception as e:
            return {
                "success": False,
                "error": f"Błąd: {str(e)}"
            }
    
    # ============================================================================
    # 5. POBIERANIE HISTORII NEGOCJACJI
    # ============================================================================
    
    def get_negotiation_history(self, task_id: str) -> Dict:
        """
        Zwraca całą historię negocjacji dla zadania.
        
        Returns:
            Dict z listą wszystkich zmian statusu i ceny
        """
        
        try:
            task_response = self.supabase.table(self.tasks_table).select(
                "id, name, crew_price, investor_counter_price, locked_price, "
                "commercial_status, execution_status, negotiation_notes, "
                "estimated_hours, actual_hours, created_at, updated_at"
            ).eq("id", task_id).single().execute()
            
            task = task_response.data
            if not task:
                return {
                    "success": False,
                    "error": "Zadanie nie znalezione"
                }
            
            # Parsuj notatki aby wydobyć historię
            history_lines = []
            notes = task.get("negotiation_notes", "")
            
            if notes:
                for line in notes.split("\n"):
                    if line.strip():
                        history_lines.append(line.strip())
            
            return {
                "success": True,
                "task_id": task_id,
                "task_name": task.get("name"),
                "current_status": task.get("commercial_status"),
                "prices": {
                    "crew_proposal": task.get("crew_price"),
                    "investor_counter": task.get("investor_counter_price"),
                    "locked_final": task.get("locked_price")
                },
                "hours": {
                    "crew_proposal": task.get("estimated_hours"),
                    "actual_locked": task.get("actual_hours")
                },
                "history_notes": history_lines,
                "timestamps": {
                    "created": task.get("created_at"),
                    "last_updated": task.get("updated_at")
                }
            }
        
        except Exception as e:
            return {
                "success": False,
                "error": f"Błąd: {str(e)}"
            }
    
    # ============================================================================
    # 6. ZADANIA OCZEKUJĄCE NA NEGOCJACJE
    # ============================================================================
    
    def get_pending_negotiations(self, project_id: str = None) -> List[Dict]:
        """
        Pobiera wszystkie zadania oczekujące na negocjacje.
        
        Args:
            project_id: Opcjonalnie filtruj po projekcie
        
        Returns:
            Lista zadań w statusach PROPOSED_BY_CREW lub COUNTER_OFFERED
        """
        
        try:
            query = self.supabase.table(self.tasks_table).select(
                "id, name, phase_id, crew_price, investor_counter_price, "
                "commercial_status, estimated_hours, created_at"
            )
            
            # Filtruj po projektach jeśli podano
            if project_id:
                query = query.eq("project_id", project_id)
            
            response = query.in_(
                "commercial_status",
                ["PROPOSED_BY_CREW", "COUNTER_OFFERED_BY_INVESTOR"]
            ).order("created_at", desc=True).execute()
            
            return response.data or []
        
        except Exception as e:
            print(f"Błąd przy pobieraniu negocjacji: {str(e)}")
            return []
    
    def get_accepted_negotiations(self, project_id: str = None) -> List[Dict]:
        """
        Pobiera wszystkie zadania ze sfinalizowanymi negocjacjami.
        
        Returns:
            Lista zadań w statusie ACCEPTED_LOCKED
        """
        
        try:
            query = self.supabase.table(self.tasks_table).select(
                "id, name, phase_id, locked_price, estimated_hours, "
                "commercial_status, created_at"
            )
            
            if project_id:
                query = query.eq("project_id", project_id)
            
            response = query.eq(
                "commercial_status", "ACCEPTED_LOCKED"
            ).order("created_at", desc=True).execute()
            
            return response.data or []
        
        except Exception as e:
            print(f"Błąd: {str(e)}")
            return []
    
    # ============================================================================
    # 7. STATYSTYKI NEGOCJACJI
    # ============================================================================
    
    def get_negotiation_statistics(self, project_id: str = None) -> Dict:
        """
        Zwraca statystyki negocjacji dla projektu.
        
        Returns:
            Dict ze statystykami (liczba zmian, średnia różnica ceny, itp.)
        """
        
        try:
            query = self.supabase.table(self.tasks_table).select(
                "id, crew_price, investor_counter_price, locked_price, commercial_status"
            )
            
            if project_id:
                query = query.eq("project_id", project_id)
            
            response = query.execute()
            tasks = response.data or []
            
            pending = sum(1 for t in tasks if t.get("commercial_status") in [
                "PROPOSED_BY_CREW", "COUNTER_OFFERED_BY_INVESTOR"
            ])
            accepted = sum(1 for t in tasks if t.get("commercial_status") == "ACCEPTED_LOCKED")
            rejected = sum(1 for t in tasks if t.get("commercial_status") == "REJECTED_BY_INVESTOR")
            
            # Oblicz średnią różnicę ceny
            price_differences = []
            for task in tasks:
                crew = task.get("crew_price", 0)
                counter = task.get("investor_counter_price") or crew
                if crew > 0:
                    diff = crew - counter
                    price_differences.append(diff)
            
            avg_difference = sum(price_differences) / len(price_differences) if price_differences else 0
            
            return {
                "total_tasks": len(tasks),
                "pending_negotiations": pending,
                "accepted_negotiations": accepted,
                "rejected_negotiations": rejected,
                "average_price_reduction": round(avg_difference, 2),
                "total_savings": round(sum(price_differences), 2)
            }
        
        except Exception as e:
            return {"error": str(e)}
    
    # ============================================================================
    # 8. EXPORT NEGOCJACJI
    # ============================================================================
    
    def export_negotiations_to_dict(self, project_id: str = None) -> List[Dict]:
        """
        Eksportuje wszystkie negocjacje do formatu słownika (do CSV/Excel).
        
        Returns:
            Lista słowników gotowych do export
        """
        
        try:
            query = self.supabase.table(self.tasks_table).select(
                "id, name, crew_price, investor_counter_price, locked_price, "
                "commercial_status, estimated_hours, actual_hours, "
                "negotiation_notes, created_at"
            )
            
            if project_id:
                query = query.eq("project_id", project_id)
            
            response = query.execute()
            tasks = response.data or []
            
            export_data = []
            for task in tasks:
                export_data.append({
                    "Task ID": task.get("id"),
                    "Task Name": task.get("name"),
                    "Crew Proposal (PLN)": task.get("crew_price"),
                    "Investor Counter (PLN)": task.get("investor_counter_price"),
                    "Final Locked (PLN)": task.get("locked_price"),
                    "Status": task.get("commercial_status"),
                    "Estimated Hours": task.get("estimated_hours"),
                    "Actual Hours": task.get("actual_hours"),
                    "Notes": task.get("negotiation_notes"),
                    "Created": task.get("created_at")
                })
            
            return export_data
        
        except Exception as e:
            print(f"Błąd przy exportcie: {str(e)}")
            return []


# ============================================================================
# TEST
# ============================================================================

if __name__ == "__main__":
    print("NegotiationService loaded successfully")
