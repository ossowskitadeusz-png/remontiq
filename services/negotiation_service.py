# services/negotiation_service.py
# =====================================================
# NEGOTIATION SERVICE - HANDSHAKE 2.0
# Zarządzanie negocjacjami cen między Ekipą a Inwestorem
# =====================================================

import streamlit as st
from datetime import datetime
from typing import List, Dict, Optional, Tuple
import json
from supabase import create_client
import os

class NegotiationService:
    """
    Serwis do zarządzania negocjacjami.
    
    Workflow:
    1. Karol proponuje cenę → INSERT do negotiations
    2. Inwestor ogląda → SELECT z negotiations WHERE status='pending'
    3. Inwestor akceptuje/odrzuca/kontruje → UPDATE negotiations
    4. Historia zapisywana w negotiation_history (audit trail)
    """
    
    def __init__(self, supabase_client=None, task_service=None):
        """
        Inicjalizacja połączenia z Supabase.
        """
        self.task_service = task_service
        if supabase_client:
            self.supabase = supabase_client
        else:
            from services.supabase_client import get_supabase_client
            self.supabase = get_supabase_client()
    
    # =====================================================
    # CORE OPERATIONS - PROPOZYCJE
    # =====================================================
    
    def propose_price(
        self,
        task_id: str,
        proposed_by: str,  # 'crew' lub 'investor'
        price: float,
        duration_days: Optional[int] = None,
        notes: Optional[str] = None
    ) -> Tuple[bool, str, Optional[str]]:
        """
        Złoż propozycję ceny.
        
        Args:
            task_id: ID zadania
            proposed_by: 'crew' lub 'investor'
            price: Proponowana cena
            duration_days: Czas (opcjonalnie)
            notes: Notatki (opcjonalnie)
        
        Returns:
            (success, message, negotiation_id)
        """
        try:
            # 1. Sprawdź czy jest aktywna negocjacja
            existing = self.supabase.table('negotiations').select('*').eq(
                'task_id', task_id
            ).eq('status', 'pending').execute()
            
            if existing.data and len(existing.data) > 0:
                return False, "Już istnieje otwarta negocjacja dla tego zadania", None
            
            # 2. Utwórz nową negocjację
            negotiation_data = {
                'task_id': task_id,
                'proposed_by': proposed_by,
                'proposed_price': price,
                'proposed_duration_days': duration_days,
                'proposed_notes': notes,
                'status': 'pending',
                'created_at': datetime.now().isoformat()
            }
            
            response = self.supabase.table('negotiations').insert(
                negotiation_data
            ).execute()
            
            if not response.data:
                return False, "Błąd przy tworzeniu negocjacji", None
            
            negotiation_id = response.data[0]['id']
            
            # 3. Dodaj wpis do historii
            self._log_action(
                negotiation_id=negotiation_id,
                action='proposed',
                actor=proposed_by,
                details={
                    'price': price,
                    'duration_days': duration_days,
                    'notes': notes
                }
            )
            
            # 4. Zaktualizuj task
            self.supabase.table('tasks').update({
                'current_negotiation_id': negotiation_id,
                'commercial_status': 'in_negotiation'
            }).eq('id', task_id).execute()
            
            return True, f"Propozycja wysłana: {price} zł", negotiation_id
        
        except Exception as e:
            return False, f"Błąd: {str(e)}", None
    
    # =====================================================
    # OPERACJE INWESTORA
    # =====================================================
    
    def accept_proposal(
        self,
        negotiation_id: str,
        investor_notes: Optional[str] = None
    ) -> Tuple[bool, str]:
        """
        Inwestor akceptuje propozycję.
        """
        try:
            # 1. Pobierz negocjację
            neg = self.supabase.table('negotiations').select('*').eq(
                'id', negotiation_id
            ).single().execute()
            
            if not neg.data:
                return False, "Negocjacja nie znaleziona"
            
            neg_data = neg.data
            
            # 2. Aktualizuj negocjację
            self.supabase.table('negotiations').update({
                'status': 'accepted',
                'responded_at': datetime.now().isoformat(),
                'response_by': 'investor',
                'response_notes': investor_notes,
                'updated_at': datetime.now().isoformat()
            }).eq('id', negotiation_id).execute()
            
            # 3. Zaloguj akcję
            self._log_action(
                negotiation_id=negotiation_id,
                action='accepted',
                actor='investor',
                details={'notes': investor_notes}
            )
            
            # 4. Zaktualizuj task korzystając z dedykowanego serwisu zadań (Single Source of Truth)
            if self.task_service:
                self.task_service.sync_handshake_status(
                    task_id=neg_data['task_id'],
                    commercial_status="ACCEPTED_LOCKED",
                    price=neg_data['proposed_price'],
                    comment="Zaakceptowano ofertę"
                )
            else:
                # Fallback
                self.supabase.table('tasks').update({
                    'commercial_status': 'approved',
                    'kanban_status': 'TODO',
                    'updated_at': datetime.now().isoformat()
                }).eq('id', neg_data['task_id']).execute()
            
            return True, "✅ Propozycja zaakceptowana!"
        
        except Exception as e:
            return False, f"Błąd: {str(e)}"
    
    def reject_proposal(
        self,
        negotiation_id: str,
        investor_notes: Optional[str] = None
    ) -> Tuple[bool, str]:
        """
        Inwestor odrzuca propozycję.
        """
        try:
            # 1. Pobierz negocjację
            neg = self.supabase.table('negotiations').select('*').eq(
                'id', negotiation_id
            ).single().execute()
            
            if not neg.data:
                return False, "Negocjacja nie znaleziona"
            
            neg_data = neg.data
            
            # 2. Aktualizuj negocjację
            self.supabase.table('negotiations').update({
                'status': 'rejected',
                'responded_at': datetime.now().isoformat(),
                'response_by': 'investor',
                'response_notes': investor_notes,
                'updated_at': datetime.now().isoformat()
            }).eq('id', negotiation_id).execute()
            
            # 3. Zaloguj
            self._log_action(
                negotiation_id=negotiation_id,
                action='rejected',
                actor='investor',
                details={'reason': investor_notes}
            )
            
            # 4. Zaktualizuj task
            self.supabase.table('tasks').update({
                'commercial_status': 'rejected',
                'updated_at': datetime.now().isoformat()
            }).eq('id', neg_data['task_id']).execute()
            
            return True, "❌ Propozycja odrzucona. Karol może wysłać nową."
        
        except Exception as e:
            return False, f"Błąd: {str(e)}"
    
    def counter_offer(
        self,
        negotiation_id: str,
        counter_price: float,
        counter_duration_days: Optional[int] = None,
        counter_notes: Optional[str] = None
    ) -> Tuple[bool, str]:
        """
        Inwestor wysyła kontrofertę.
        """
        try:
            # 1. Pobierz negocjację
            neg = self.supabase.table('negotiations').select('*').eq(
                'id', negotiation_id
            ).single().execute()
            
            if not neg.data:
                return False, "Negocjacja nie znaleziona"
            
            neg_data = neg.data
            
            # 2. Aktualizuj negocjację
            self.supabase.table('negotiations').update({
                'status': 'counter_offer',
                'response_price': counter_price,
                'response_duration_days': counter_duration_days,
                'response_notes': counter_notes,
                'response_by': 'investor',
                'responded_at': datetime.now().isoformat(),
                'updated_at': datetime.now().isoformat()
            }).eq('id', negotiation_id).execute()
            
            # 3. Zaloguj
            self._log_action(
                negotiation_id=negotiation_id,
                action='counter_offered',
                actor='investor',
                details={
                    'counter_price': counter_price,
                    'counter_duration_days': counter_duration_days,
                    'counter_notes': counter_notes
                }
            )
            
            # 4. Zaktualizuj task
            self.supabase.table('tasks').update({
                'commercial_status': 'in_negotiation',
                'updated_at': datetime.now().isoformat()
            }).eq('id', neg_data['task_id']).execute()
            
            return True, f"💬 Kontrpropozycja wysłana: {counter_price} zł"
        
        except Exception as e:
            return False, f"Błąd: {str(e)}"
    
    # =====================================================
    # OPERACJE EKIPY (odpowiedź na kontrofertę)
    # =====================================================
    
    def crew_accept_counter_offer(
        self,
        negotiation_id: str,
        crew_notes: Optional[str] = None
    ) -> Tuple[bool, str]:
        """
        Karol akceptuje kontrofertę od Inwestora.
        """
        try:
            # 1. Pobierz negocjację
            neg = self.supabase.table('negotiations').select('*').eq(
                'id', negotiation_id
            ).single().execute()
            
            if not neg.data:
                return False, "Negocjacja nie znaleziona"
            
            neg_data = neg.data
            
            if neg_data['status'] != 'counter_offer':
                return False, "To nie jest kontrpropozycja do akceptacji"
            
            # 2. Aktualizuj - KONIEC NEGOCJACJI
            self.supabase.table('negotiations').update({
                'status': 'accepted',
                'responded_at': datetime.now().isoformat(),
                'response_by': 'crew',
                'updated_at': datetime.now().isoformat()
            }).eq('id', negotiation_id).execute()
            
            # 3. Zaloguj
            self._log_action(
                negotiation_id=negotiation_id,
                action='accepted',
                actor='crew',
                details={'notes': crew_notes}
            )
            
            # 4. Zaktualizuj task korzystając z dedykowanego serwisu zadań (Single Source of Truth)
            if self.task_service:
                self.task_service.sync_handshake_status(
                    task_id=neg_data['task_id'],
                    commercial_status="ACCEPTED_LOCKED",
                    price=neg_data['response_price'],
                    comment="Akceptacja kontroferty przez ekipę"
                )
            else:
                # Fallback jeśli serwis nie został wstrzyknięty (dla kompatybilności)
                self.supabase.table('tasks').update({
                    'commercial_status': 'approved',
                    'kanban_status': 'TODO',
                    'updated_at': datetime.now().isoformat()
                }).eq('id', neg_data['task_id']).execute()
            
            return True, "✅ Kontrpropozycja zaakceptowana!"
        
        except Exception as e:
            return False, f"Błąd: {str(e)}"
    
    def crew_counter_counter_offer(
        self,
        negotiation_id: str,
        crew_counter_price: float,
        crew_counter_duration_days: Optional[int] = None,
        crew_notes: Optional[str] = None
    ) -> Tuple[bool, str]:
        """
        Karol wysyła swoją kontrofertę na kontrofertę Inwestora.
        """
        try:
            # 1. Pobierz negocjację
            neg = self.supabase.table('negotiations').select('*').eq(
                'id', negotiation_id
            ).single().execute()
            
            if not neg.data:
                return False, "Negocjacja nie znaleziona"
            
            neg_data = neg.data
            
            # 2. "Flip" - teraz Karol zaproponował, a Inwestor odpowiada
            # Status wraca na counter_offer, ale proposed_by zmienia się kontekstowo
            # W rzeczywistości to jest "ping-pong" - nie zmieniamy struktury,
            # ale interpretujemy kto czeka na odpowiedź
            
            self.supabase.table('negotiations').update({
                'status': 'pending',  # ← Zmieniono z counter_offer! Piłeczka wraca do Inwestora

                'proposed_price': crew_counter_price,  # ← Karol zmienia swoją propozycję
                'proposed_duration_days': crew_counter_duration_days,
                'proposed_notes': crew_notes,
                'response_price': None,  # ← Czyścimy odpowiedź Inwestora
                'response_duration_days': None,
                'response_notes': None,
                'response_by': None,
                'responded_at': None,
                'updated_at': datetime.now().isoformat()
            }).eq('id', negotiation_id).execute()
            
            # 3. Zaloguj
            self._log_action(
                negotiation_id=negotiation_id,
                action='counter_offered',
                actor='crew',
                details={
                    'counter_price': crew_counter_price,
                    'counter_duration_days': crew_counter_duration_days,
                    'notes': crew_notes
                }
            )
            
            return True, f"💬 Karol zaproponował: {crew_counter_price} zł"
        
        except Exception as e:
            return False, f"Błąd: {str(e)}"
    
    # =====================================================
    # POBIERANIE DANYCH - DLA PANELI
    # =====================================================
    
    def get_pending_for_investor(self, project_id: str) -> List[Dict]:
        """
        Pobierz wszystkie negocjacje czekające na decyzję Inwestora.
        
        Panel Inwestora wyświetla tylko te, które wymagają jego akcji.
        """
        try:
            response = self.supabase.table('negotiations').select(
                '''
                id, task_id, proposed_by, proposed_price, proposed_duration_days,
                proposed_notes, response_price, response_duration_days, response_notes, 
                status, created_at,
                tasks!negotiations_task_id_fkey(id, name, project_id, description)
                '''
            ).eq('status', 'pending').execute()
            
            # Filtruj po project_id
            results = []
            for neg in response.data:
                if neg['tasks'] and neg['tasks'].get('project_id') == project_id:
                    results.append(neg)
            
            return results
        
        except Exception as e:
            st.error(f"Błąd pobierania: {str(e)}")
            return []
    
    def get_pending_for_crew(self, project_id: str) -> List[Dict]:
        """
        Pobierz negocjacje czekające na odpowiedź Ekipy (kontrpropozycje od Inwestora).
        """
        try:
            response = self.supabase.table('negotiations').select(
                '''
                id, task_id, proposed_by, proposed_price, response_price,
                response_duration_days, response_notes, status, created_at,
                tasks!negotiations_task_id_fkey(id, name, project_id)
                '''
            ).eq('status', 'counter_offer').execute()
            
            results = []
            for neg in response.data:
                if neg['tasks'] and neg['tasks'].get('project_id') == project_id:
                    results.append(neg)
            
            return results
        
        except Exception as e:
            st.error(f"Błąd pobierania: {str(e)}")
            return []
    
    def get_negotiation_details(self, negotiation_id: str) -> Optional[Dict]:
        """
        Pobierz pełne szczegóły negocjacji z historią.
        """
        try:
            # Negocjacja
            neg_response = self.supabase.table('negotiations').select('*').eq(
                'id', negotiation_id
            ).single().execute()
            
            if not neg_response.data:
                return None
            
            neg_data = neg_response.data
            
            # Historia
            history_response = self.supabase.table('negotiation_history').select('*').eq(
                'negotiation_id', negotiation_id
            ).order('created_at', desc=False).execute()
            
            neg_data['history'] = history_response.data if history_response.data else []
            
            return neg_data
        
        except Exception as e:
            st.error(f"Błąd: {str(e)}")
            return None
    
    def get_all_negotiations_for_project(self, project_id: str) -> List[Dict]:
        """
        Pobierz wszystkie negocjacje dla projektu (do historii/raportu).
        """
        try:
            response = self.supabase.table('negotiations').select(
                '''
                id, task_id, proposed_by, proposed_price, proposed_duration_days, 
                response_price, response_duration_days, status, created_at, responded_at,
                tasks!negotiations_task_id_fkey(id, name, project_id)
                '''
            ).order('created_at', desc=True).execute()
            
            results = []
            for neg in response.data:
                linked_task = neg.get("tasks") or {}
                if linked_task.get("project_id") == project_id:
                    results.append(neg)
            
            return results
        
        except Exception as e:
            st.error(f"Błąd: {str(e)}")
            return []
    
    # =====================================================
    # STATYSTYKI & RAPORTY
    # =====================================================
    
    def get_negotiation_statistics(self, project_id: str) -> Dict:
        """
        Oblicz statystyki negocjacji (ile zaoszczędzono, ile otwartych, itp).
        """
        try:
            all_negs = self.get_all_negotiations_for_project(project_id)
            
            total_crew_proposals = sum(
                float(n['proposed_price']) for n in all_negs if n['proposed_by'] == 'crew'
            )
            
            total_approved = sum(
                float(n['proposed_price']) for n in all_negs 
                if n['status'] == 'accepted' and n['proposed_by'] == 'crew'
            )
            
            total_rejected = len([n for n in all_negs if n['status'] == 'rejected'])
            
            pending_count = len([n for n in all_negs if n['status'] == 'pending'])
            
            return {
                'total_negotiations': len(all_negs),
                'approved': total_approved,
                'pending': pending_count,
                'rejected': total_rejected,
                'savings': total_crew_proposals - total_approved if total_approved > 0 else 0
            }
        
        except Exception as e:
            st.error(f"Błąd obliczania: {str(e)}")
            return {}
    
    # =====================================================
    # HELPER METHODS
    # =====================================================
    
    def _log_action(
        self,
        negotiation_id: str,
        action: str,
        actor: str,
        details: Optional[Dict] = None
    ) -> bool:
        """
        Zaloguj akcję do negotiation_history (audit trail).
        """
        try:
            self.supabase.table('negotiation_history').insert({
                'negotiation_id': negotiation_id,
                'action': action,
                'actor': actor,
                'details': details or {},
                'created_at': datetime.now().isoformat()
            }).execute()
            
            return True
        except Exception as e:
            st.warning(f"Błąd logowania: {str(e)}")
            return False
    
    def export_to_dict(self, negotiation_id: str) -> Optional[Dict]:
        """
        Eksportuj negocjację do słownika (np. dla JSON-a).
        """
        neg = self.get_negotiation_details(negotiation_id)
        if not neg:
            return None
        
        return {
            'id': neg['id'],
            'task_id': neg['task_id'],
            'proposed_by': neg['proposed_by'],
            'proposed_price': float(neg['proposed_price']),
            'proposed_duration_days': neg['proposed_duration_days'],
            'proposed_notes': neg['proposed_notes'],
            'status': neg['status'],
            'response_price': float(neg['response_price']) if neg['response_price'] else None,
            'response_duration_days': neg['response_duration_days'],
            'response_notes': neg['response_notes'],
            'response_by': neg['response_by'],
            'created_at': neg['created_at'],
            'responded_at': neg['responded_at'],
            'history': [
                {
                    'action': h['action'],
                    'actor': h['actor'],
                    'created_at': h['created_at'],
                    'details': h['details']
                }
                for h in neg.get('history', [])
            ]
        }
