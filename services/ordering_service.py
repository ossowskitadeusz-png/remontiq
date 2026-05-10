# services/ordering_service.py
# =====================================================
# ORDERING SERVICE - Zarządzanie kolejnością i zależnościami zadań
# =====================================================

from datetime import datetime, timedelta
from typing import List, Dict, Optional, Tuple

class TaskDependencyError(Exception):
    """Błąd walidacji zależności między zadaniami."""
    pass

class OrderingService:
    """
    Serwis odpowiedzialny za:
    1. Zmianę kolejności zadań w fazie
    2. Ustawianie zależności między zadaniami
    3. Automatyczne obliczanie dat startu/końca
    4. Walidacja logiki (brak cykli, logiczny porządek)
    """
    
    def __init__(self, supabase, task_service):
        self.supabase = supabase
        self.task_service = task_service
    
    # =====================================================
    # 1. ZMIANA KOLEJNOŚCI (Drag & Drop / Strzałki)
    # =====================================================
    
    def reorder_tasks_in_phase(self, phase_id: str, task_ids: List[str]) -> Tuple[bool, str]:
        """Zmienia sort_order dla wszystkich zadań w fazie."""
        try:
            tasks_res = self.supabase.table("tasks").select("id").eq("phase_id", phase_id).execute()
            existing_ids = {t['id'] for t in (tasks_res.data or [])}
            provided_ids = set(task_ids)
            
            if existing_ids != provided_ids:
                return False, "❌ Lista zadań nie zgadza się z fazą"
            
            for index, task_id in enumerate(task_ids):
                self.supabase.table("tasks").update({"sort_order": index}).eq("id", task_id).execute()
            
            self._recalculate_timeline_for_phase(phase_id)
            return True, f"✅ Zmieniono kolejność {len(task_ids)} zadań"
        except Exception as e:
            return False, f"❌ Błąd: {str(e)}"
    
    def move_task_up(self, task_id: str) -> Tuple[bool, str]:
        """Przenosi zadanie wyżej (zmniejsza sort_order o 1)."""
        try:
            task_res = self.supabase.table("tasks").select("*").eq("id", task_id).execute()
            if not task_res.data: return False, "❌ Zadanie nie znalezione"
            
            task = task_res.data[0]
            phase_id = task['phase_id']
            current_order = task['sort_order']
            
            if current_order <= 0: return False, "❌ To zadanie jest już na górze"
            
            prev_task_res = self.supabase.table("tasks").select("id").eq("phase_id", phase_id).eq("sort_order", current_order - 1).execute()
            if not prev_task_res.data: return False, "❌ Nie można znaleźć zadania wyżej"
            
            self.supabase.table("tasks").update({"sort_order": current_order - 1}).eq("id", task_id).execute()
            self.supabase.table("tasks").update({"sort_order": current_order}).eq("id", prev_task_res.data[0]['id']).execute()
            
            self._recalculate_timeline_for_phase(phase_id)
            return True, "✅ Zadanie przeniesiono wyżej"
        except Exception as e:
            return False, f"❌ Błąd: {str(e)}"
    
    def move_task_down(self, task_id: str) -> Tuple[bool, str]:
        """Przenosi zadanie niżej (zwiększa sort_order o 1)."""
        try:
            task_res = self.supabase.table("tasks").select("*").eq("id", task_id).execute()
            if not task_res.data: return False, "❌ Zadanie nie znalezione"
            
            task = task_res.data[0]
            phase_id = task['phase_id']
            current_order = task['sort_order']
            
            last_task_res = self.supabase.table("tasks").select("sort_order").eq("phase_id", phase_id).order("sort_order", desc=True).limit(1).execute()
            if not last_task_res.data or current_order >= last_task_res.data[0]['sort_order']:
                return False, "❌ To zadanie jest już na dnie"
            
            next_task_res = self.supabase.table("tasks").select("id").eq("phase_id", phase_id).eq("sort_order", current_order + 1).execute()
            if not next_task_res.data: return False, "❌ Nie można znaleźć zadania poniżej"
            
            self.supabase.table("tasks").update({"sort_order": current_order + 1}).eq("id", task_id).execute()
            self.supabase.table("tasks").update({"sort_order": current_order}).eq("id", next_task_res.data[0]['id']).execute()
            
            self._recalculate_timeline_for_phase(phase_id)
            return True, "✅ Zadanie przeniesiono niżej"
        except Exception as e:
            return False, f"❌ Błąd: {str(e)}"
    
    def set_task_dependency(self, task_id: str, depends_on_task_id: Optional[str]) -> Tuple[bool, str]:
        """Ustawia zależność: to zadanie czeka na tamto."""
        try:
            if depends_on_task_id and self._has_circular_dependency(task_id, depends_on_task_id):
                return False, "❌ Zmieniłoby się w cykl (A→B→C→A)"
            
            self.supabase.table("tasks").update({"depends_on_task_id": depends_on_task_id}).eq("id", task_id).execute()
            
            task_res = self.supabase.table("tasks").select("phase_id").eq("id", task_id).execute()
            if task_res.data:
                self._recalculate_timeline_for_phase(task_res.data[0]['phase_id'])
            return True, "✅ Zależność ustawiona"
        except Exception as e:
            return False, f"❌ Błąd: {str(e)}"
    
    def _has_circular_dependency(self, task_id: str, depends_on_task_id: str) -> bool:
        visited = set()
        current = depends_on_task_id
        while current:
            if current in visited: return True
            visited.add(current)
            task_res = self.supabase.table("tasks").select("depends_on_task_id").eq("id", current).execute()
            if not task_res.data: break
            current = task_res.data[0].get('depends_on_task_id')
            if current == task_id: return True
        return False
    
    def _recalculate_timeline_for_phase(self, phase_id: str):
        try:
            phase_res = self.supabase.table("project_phases").select("*").eq("id", phase_id).execute()
            if not phase_res.data: return
            
            phase = phase_res.data[0]
            phase_start = datetime.fromisoformat(phase['planned_start_date'].replace('Z', '+00:00'))
            tasks = self.supabase.table("tasks").select("*").eq("phase_id", phase_id).order("sort_order").execute().data or []
            
            task_end_dates = {}
            for task in tasks:
                task_id = task['id']
                depends_on = task.get('depends_on_task_id')
                duration = task.get('estimated_duration_days', 1) or 1
                
                start_date = task_end_dates[depends_on] + timedelta(days=1) if depends_on and depends_on in task_end_dates else phase_start
                end_date = start_date + timedelta(days=duration)
                task_end_dates[task_id] = end_date
                
                self.supabase.table("tasks").update({
                    "estimated_start_date": start_date.isoformat(),
                    "estimated_end_date": end_date.isoformat()
                }).eq("id", task_id).execute()
        except Exception as e:
            print(f"⚠️ Błąd przeliczania timeline: {str(e)}")
    
    def get_ordered_tasks(self, phase_id: str) -> List[Dict]:
        tasks = self.supabase.table("tasks").select("*").eq("phase_id", phase_id).order("sort_order").execute().data or []
        result = []
        for task in tasks:
            result.append({
                'id': task['id'],
                'name': task['name'],
                'sort_order': task['sort_order'],
                'depends_on_task_id': task.get('depends_on_task_id'),
                'estimated_start': task.get('estimated_start_date'),
                'estimated_end': task.get('estimated_end_date'),
                'final_price': task.get('final_approved_price'),
                'status': self._get_task_status(task),
                'duration_days': task.get('estimated_duration_days', 1)
            })
        return result
    
    def _get_task_status(self, task: Dict) -> str:
        if not task.get('final_approved_price'): return "PENDING"
        if task.get('depends_on_task_id'):
            prev_res = self.supabase.table("tasks").select("final_approved_price").eq("id", task['depends_on_task_id']).execute()
            if prev_res.data and not prev_res.data[0].get('final_approved_price'): return "BLOCKED"
        return "READY"

    def validate_phase_order(self, phase_id: str) -> Tuple[bool, List[str]]:
        warnings = []
        tasks = self.get_ordered_tasks(phase_id)
        for task in tasks:
            if not task['final_price'] and task['depends_on_task_id']:
                warnings.append(f"⚠️ {task['name']}: Czeka na poprzednie, ale samo bez wyceny")
        return len(warnings) == 0, warnings
