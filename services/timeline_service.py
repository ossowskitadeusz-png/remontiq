# services/timeline_service.py
# =====================================================
# TIMELINE SERVICE - Logika prognozy i postępu
# =====================================================

from datetime import datetime, timedelta
from typing import List, Dict, Optional
import pandas as pd

class TimelineService:
    """
    Serwis odpowiedzialny za obliczenia postępu faz i zadań.
    Integruje się z TaskService i NegotiationService.
    """
    
    def __init__(self, supabase, task_service=None, negotiation_service=None):
        self.supabase = supabase
        self.task_service = task_service
        self.negotiation_service = negotiation_service
    
    # =====================================================
    # 1. PROGRESS TASK'ów (% ukończenia fazy)
    # =====================================================
    
    def get_phase_progress(self, phase_id: str) -> Dict:
        """
        Oblicza progres pojedynczej fazy na podstawie statusów zadań.
        """
        
        # Pobierz fazę
        phase_res = self.supabase.table("project_phases").select("*").eq("id", phase_id).execute()
        if not phase_res.data:
            return {}
        
        phase = phase_res.data[0]
        
        # Pobierz wszystkie zadania w fazie
        tasks_res = self.supabase.table("tasks").select("*").eq("phase_id", phase_id).execute()
        tasks = tasks_res.data or []
        
        # Zliczanie statusów
        completed = sum(1 for t in tasks if self._is_task_completed(t))
        in_progress = sum(1 for t in tasks if self._is_task_in_progress(t))
        pending = sum(1 for t in tasks if self._is_task_pending(t))
        delayed = sum(1 for t in tasks if self._is_task_delayed(t))
        
        total = len(tasks)
        progress_percent = (completed / total * 100) if total > 0 else 0
        
        # Oblicz dni - obsługa braku dat
        try:
            start_date = datetime.fromisoformat(phase.get('planned_start_date', '').replace('Z', '+00:00')) if phase.get('planned_start_date') else datetime.now()
            end_date = datetime.fromisoformat(phase.get('planned_end_date', '').replace('Z', '+00:00')) if phase.get('planned_end_date') else start_date + timedelta(days=7)
        except:
            start_date = datetime.now()
            end_date = start_date + timedelta(days=7)
            
        today = datetime.now().astimezone(start_date.tzinfo) if start_date.tzinfo else datetime.now()
        
        estimated_days = (end_date - start_date).days
        elapsed_days = max(0, (today - start_date).days)
        remaining_days = max(0, (end_date - today).days)
        
        # Określ status fazy
        if total > 0 and progress_percent == 100:
            phase_status = "COMPLETED"
        elif total > 0 and progress_percent == 0 and elapsed_days < 1:
            phase_status = "PLANNING"
        elif today > end_date and progress_percent < 100:
            phase_status = "DELAYED"
        else:
            phase_status = "IN_PROGRESS"
        
        return {
            'phase_id': phase_id,
            'phase_name': phase.get('phase_name', 'Nieznana faza'),
            'total_tasks': total,
            'completed_tasks': completed,
            'in_progress_tasks': in_progress,
            'pending_tasks': pending,
            'delayed_tasks': delayed,
            'progress_percent': round(progress_percent, 1),
            'estimated_days': estimated_days,
            'elapsed_days': elapsed_days,
            'remaining_days': remaining_days,
            'status': phase_status,
            'start_date': phase.get('planned_start_date'),
            'end_date': phase.get('planned_end_date'),
            'tasks': self._get_task_details(tasks)
        }
    
    # =====================================================
    # 2. SEKWENCYJNE DATY ZADAŃ (integracja z OrderingService)
    # =====================================================

    def calculate_sequential_dates_for_phase(self, phase_id: str, ordering_service=None) -> List[Dict]:
        """
        Liczy datę startu i końca każdego zadania kaskadowo,
        bazując na kolejności Karola (sort_order) i planned_start_date fazy.

        Logika:
          zadanie #1 → start = planned_start_date fazy
          zadanie #2 → start = koniec zadania #1
          zadanie #3 → start = koniec zadania #2
          itd.

        Returns: lista zadań wzbogacona o klucze:
          'seq_start'      - datetime obliczony start
          'seq_end'        - datetime obliczony koniec
          'seq_start_str'  - czytelny string "DD Mon"
          'seq_end_str'    - czytelny string "DD Mon"
          'duration_days'  - liczba dni (z bazy lub domyślnie 1)
        """
        try:
            # 1. Pobierz datę startu fazy
            phase_res = self.supabase.table("project_phases").select(
                "planned_start_date"
            ).eq("id", phase_id).single().execute()

            phase_data = phase_res.data
            if not phase_data or not phase_data.get("planned_start_date"):
                # Fallback: zaczynamy od dziś
                phase_start = datetime.now().replace(hour=0, minute=0, second=0, microsecond=0)
            else:
                raw = phase_data["planned_start_date"]
                phase_start = datetime.fromisoformat(raw.replace("Z", "+00:00")).replace(tzinfo=None)

            # 2. Pobierz zadania posortowane (przez OrderingService jeśli dostępny)
            if ordering_service:
                tasks = ordering_service.get_ordered_tasks(phase_id)
            else:
                res = self.supabase.table("tasks").select(
                    "id, name, estimated_duration_days, sort_order, kanban_status, final_approved_price, commercial_status"
                ).eq("phase_id", phase_id).order("sort_order").execute()
                tasks = res.data or []

            # 3. Oblicz kaskadowo daty
            current_start = phase_start
            result = []

            for task in tasks:
                duration = int(task.get("estimated_duration_days") or 1)
                task_end = current_start + timedelta(days=duration)

                enriched = dict(task)
                enriched["seq_start"]     = current_start
                enriched["seq_end"]       = task_end
                enriched["seq_start_str"] = current_start.strftime("%d %b")
                enriched["seq_end_str"]   = task_end.strftime("%d %b")
                enriched["duration_days"] = duration
                result.append(enriched)

                # Następne zadanie zaczyna się po zakończeniu tego
                current_start = task_end

            return result

        except Exception as e:
            print(f"⚠️ calculate_sequential_dates_for_phase error: {e}")
            return []

    # =====================================================
    # 3. TIMELINE CAŁEGO PROJEKTU
    # =====================================================
    
    def get_project_timeline(self, project_id: str, ordering_service=None) -> Dict:
        """
        Pobiera wszystkie fazy projektu z ich progresem.
        Jeśli przekazany ordering_service, dołącza sekwencyjne daty zadań.
        """
        
        phases_res = self.supabase.table("project_phases").select("*").eq(
            "project_id", project_id
        ).order("phase_number").execute()
        
        phases = phases_res.data or []
        
        if not phases:
            return {'phases': [], 'overall_progress': 0, 'status': 'NO_PHASES'}
        
        phase_details = []
        total_progress = 0
        
        for phase in phases:
            progress = self.get_phase_progress(phase['id'])
            # Dołącz sekwencyjne daty zadań jeśli mamy ordering_service
            if ordering_service:
                progress['sequential_tasks'] = self.calculate_sequential_dates_for_phase(
                    phase['id'], ordering_service
                )
            else:
                progress['sequential_tasks'] = []
            phase_details.append(progress)
            total_progress += progress['progress_percent']
        
        overall_progress = total_progress / len(phases) if phases else 0
        
        # Status całego projektu
        if overall_progress == 100:
            project_status = "UKOŃCZONY"
        elif overall_progress == 0:
            project_status = "PLANOWANIE"
        else:
            project_status = "W TRAKCIE"
        
        # Filtrowanie dat do min/max
        valid_starts = [p.get('start_date') for p in phase_details if p.get('start_date')]
        valid_ends = [p.get('end_date') for p in phase_details if p.get('end_date')]
        
        return {
            'project_id': project_id,
            'phases': phase_details,
            'overall_progress': round(overall_progress, 1),
            'total_phases': len(phases),
            'completed_phases': sum(1 for p in phase_details if p['status'] == 'COMPLETED'),
            'status': project_status,
            'earliest_start': min(valid_starts) if valid_starts else None,
            'latest_end': max(valid_ends) if valid_ends else None
        }
    
    # =====================================================
    # 3. STATUS POJEDYNCZEGO ZADANIA
    # =====================================================
    
    def _is_task_completed(self, task: Dict) -> bool:
        """Zadanie fizycznie ukończone i odebrane przez Inwestora."""
        status = str(
            task.get('kanban_status')
            or task.get('completion_status')
            or task.get('status')
            or ''
        ).upper()
        return status in ('DONE', 'COMPLETED', 'ARCHIVED')
    
    def _is_task_in_progress(self, task: Dict) -> bool:
        """Zadanie w trakcie fizycznej realizacji."""
        return task.get('kanban_status') in ('IN_PROGRESS', 'AWAITING_INSPECTION')
    
    def _is_task_pending(self, task: Dict) -> bool:
        """Zadanie oczekujące = nie zostało jeszcze rozpoczęte."""
        ks = task.get('kanban_status') or 'TODO'
        return ks in ('TODO', None)
    
    def _is_task_delayed(self, task: Dict) -> bool:
        """Zadanie opóźnione — ma datę zakończenia, która już minęła i nie jest ukończone."""
        if self._is_task_completed(task):
            return False
        pd = task.get('planned_end_date')
        if not pd:
            return False
        try:
            end = datetime.fromisoformat(pd)
            return datetime.now() > end
        except:
            return False
    
    def _get_task_details(self, tasks: List[Dict]) -> List[Dict]:
        """Mapuje szczegóły zadań do formatu czytelnego dla UI."""
        return [
            {
                'id': t['id'],
                'name': t['name'],
                'status': 'completed' if self._is_task_completed(t) 
                         else 'in_progress' if self._is_task_in_progress(t)
                         else 'pending',
                'price': t.get('final_approved_price', 0),
                'created_at': t.get('created_at')
            }
            for t in tasks
        ]
    
    def get_phase_delay_warning(self, phase_id: str) -> Dict:
        """
        Sprawdza, czy zadania w fazie przekraczają zadeklarowaną datę zakończenia.
        Zwraca ostrzeżenie z liczbą dni przekroczenia i listą winnych zadań.
        """
        phase_res = self.supabase.table("project_phases").select(
            "phase_name, planned_start_date, planned_end_date"
        ).eq("id", phase_id).single().execute()
        if not phase_res.data:
            return {"has_warning": False}
        
        phase = phase_res.data
        planned_end_str = phase.get("planned_end_date")
        planned_start_str = phase.get("planned_start_date")
        if not planned_end_str or not planned_start_str:
            return {"has_warning": False}
        
        try:
            planned_start = datetime.fromisoformat(planned_start_str)
            planned_end = datetime.fromisoformat(planned_end_str)
            planned_days = (planned_end - planned_start).days
        except:
            return {"has_warning": False}
        
        # Suma szacowanych dni wszystkich zadań w fazie
        tasks_res = self.supabase.table("tasks").select(
            "id, name, estimated_duration_days, created_at"
        ).eq("phase_id", phase_id).order("created_at").execute()
        tasks = tasks_res.data or []
        
        total_estimated_days = sum(t.get("estimated_duration_days") or 1 for t in tasks)
        
        if total_estimated_days <= planned_days:
            return {"has_warning": False, "total_estimated_days": total_estimated_days, "planned_days": planned_days}
        
        delay_days = total_estimated_days - planned_days
        
        # Znajdź zadania "winne" — te dodane po zapełnieniu limitu
        cumulative = 0
        culprit_tasks = []
        for t in tasks:
            d = t.get("estimated_duration_days") or 1
            if cumulative + d > planned_days:
                culprit_tasks.append(t['name'])
            cumulative += d
        
        return {
            "has_warning": True,
            "delay_days": delay_days,
            "planned_days": planned_days,
            "total_estimated_days": total_estimated_days,
            "planned_end": planned_end_str,
            "culprit_tasks": culprit_tasks,
            "phase_name": phase.get("phase_name")
        }
    
    # =====================================================
    # 4. METRYKI PROJEKTU (KPI)
    # =====================================================
    
    def get_project_metrics(self, project_id: str) -> Dict:
        """
        Pobiera KPI całego projektu (na-czas, na-budżet, ryzyko).
        """
        
        timeline = self.get_project_timeline(project_id)
        
        # Pobierz budżet projektu
        project_res = self.supabase.table("project_metadata").select("*").eq(
            "id", project_id
        ).execute()
        
        if not project_res.data:
            return {}
            
        project = project_res.data[0]
        total_budget = project.get('total_budget', 0) or 0
        
        # Suma zatwierdzonych cen
        all_tasks_res = self.supabase.table("tasks").select("*").eq(
            "project_id", project_id
        ).execute()
        all_tasks = all_tasks_res.data or []
        
        spent = sum(t.get('final_approved_price', 0) or 0 for t in all_tasks)
        remaining_budget = total_budget - spent
        budget_percent = (spent / total_budget * 100) if total_budget > 0 else 0
        
        # Status ryzyka
        if remaining_budget < 0:
            budget_status = "🔴 PRZEKROCZONY"
        elif remaining_budget < total_budget * 0.1:  # Poniżej 10%
            budget_status = "🟡 RYZYKO"
        else:
            budget_status = "🟢 OK"
        
        return {
            'total_budget': total_budget,
            'spent': spent,
            'remaining': remaining_budget,
            'budget_percent': round(budget_percent, 1),
            'budget_status': budget_status,
            'overall_progress': timeline['overall_progress'],
            'project_status': timeline['status'],
            'on_time': "✅ Na ścieżce" if timeline['overall_progress'] > 0 else "⏳ Planowanie",
            'estimated_completion': timeline.get('latest_end')
        }
