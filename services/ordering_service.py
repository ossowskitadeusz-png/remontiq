import logging
from datetime import datetime, timedelta
from typing import List, Dict, Optional
from supabase import Client

# ============================================================================
# FEATURE FLAG
# ============================================================================
USE_NEW_DEPENDENCIES = True 

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

class OrderingService:
    def __init__(self, supabase: Client, task_service=None):
        self.supabase = supabase
        self.task_service = task_service
        logger.info(f"OrderingService v2.2 initialized. USE_NEW_DEPENDENCIES={USE_NEW_DEPENDENCIES}")

    # ========================================================================
    # HELPER LOGIC FOR SELF-HEALING
    # ========================================================================

    def _stable_task_sort_key(self, task: Dict):
        """Klucz do stabilnego sortowania zadań: najpierw poprawny sort_order, potem czas utworzenia, na końcu ID."""
        sort_order = task.get("sort_order")
        has_valid_order = isinstance(sort_order, int) and sort_order is not None
        return (
            not has_valid_order,
            sort_order if has_valid_order else 999999,
            str(task.get("created_at") or ""),
            str(task.get("id") or "")
        )

    def _needs_sort_order_healing(self, tasks: List[Dict]) -> bool:
        """Sprawdza, czy zadania w danej fazie wymagają uzdrowienia kolejności."""
        if not tasks:
            return False
        
        orders = []
        for t in tasks:
            val = t.get("sort_order")
            if val is None or not isinstance(val, int):
                return True
            orders.append(val)
            
        if len(set(orders)) != len(tasks):
            return True
            
        orders.sort()
        if orders != list(range(len(tasks))):
            return True
            
        return False

    def _ensure_valid_sort_orders(self, phase_id: str) -> bool:
        """Upewnia się, że zadania w danej fazie mają ciągłe, bezduplikatowe indeksy sort_order (0..N-1)."""
        try:
            res = self.supabase.table("tasks")\
                .select("id, sort_order, created_at")\
                .eq("phase_id", phase_id)\
                .execute()
            tasks = res.data or []
            if not tasks:
                return True
                
            if self._needs_sort_order_healing(tasks):
                sorted_tasks = sorted(tasks, key=self._stable_task_sort_key)
                for idx, t in enumerate(sorted_tasks):
                    if t.get("sort_order") != idx:
                        self.supabase.table("tasks").update({"sort_order": idx}).eq("id", t["id"]).execute()
            return True
        except Exception as e:
            logger.error(f"Failed to ensure valid sort orders: {e}")
            return False

    # ========================================================================
    # UI METHODS (Dla Panelu Karola)
    # ========================================================================
    
    def get_ordered_tasks(self, phase_id: str) -> List[Dict]:
        try:
            # Samoleczenie przed pobraniem
            self._ensure_valid_sort_orders(phase_id)
            
            res = self.supabase.table("tasks")\
                .select("id, name, state, sort_order, final_approved_price, commercial_status, kanban_status, description")\
                .eq("phase_id", phase_id)\
                .order("sort_order")\
                .execute()
            
            tasks = res.data or []
            for t in tasks:
                t['status'] = self._calculate_ui_status(t)
                t['final_price'] = t.get('final_approved_price')
            return tasks
        except Exception as e:
            logger.error(f"Failed to get ordered tasks: {e}")
            return []

    def reorder_tasks_in_phase(self, phase_id: str, task_ids_ordered: List[str]) -> bool:
        """Atomowa zmiana kolejności wielu zadań naraz."""
        try:
            updates = [
                {"id": tid, "sort_order": idx, "updated_at": datetime.now().isoformat()}
                for idx, tid in enumerate(task_ids_ordered)
            ]
            self.supabase.table("tasks").upsert(updates).execute()
            return True
        except Exception as e:
            logger.error(f"Batch reorder failed: {e}")
            return False

    def move_task_up(self, task_id: str) -> bool:
        return self._move_task(task_id, -1)

    def move_task_down(self, task_id: str) -> bool:
        return self._move_task(task_id, 1)

    def _move_task(self, task_id: str, direction: int) -> bool:
        try:
            task_res = self.supabase.table("tasks").select("id, phase_id").eq("id", task_id).single().execute()
            task = task_res.data
            if not task: 
                logger.error(f"Task {task_id} not found.")
                return False
            
            phase_id = task["phase_id"]
            self._ensure_valid_sort_orders(phase_id)
            
            res = self.supabase.table("tasks")\
                .select("id, sort_order")\
                .eq("phase_id", phase_id)\
                .order("sort_order")\
                .execute()
            tasks = res.data or []
            
            task_index = -1
            for idx, t in enumerate(tasks):
                if t["id"] == task_id:
                    task_index = idx
                    break
                    
            if task_index == -1:
                logger.error(f"Task {task_id} not found after healing.")
                return False
                
            neighbor_index = task_index + direction
            if neighbor_index < 0 or neighbor_index >= len(tasks):
                # Poza zakresem - no-op (zwracamy True)
                return True
                
            task_to_move = tasks[task_index]
            neighbor_task = tasks[neighbor_index]
            
            # Zamiana indeksów sort_order
            self.supabase.table("tasks").update({"sort_order": neighbor_task["sort_order"]}).eq("id", task_to_move["id"]).execute()
            self.supabase.table("tasks").update({"sort_order": task_to_move["sort_order"]}).eq("id", neighbor_task["id"]).execute()
            return True
        except Exception as e:
            logger.error(f"Move task failed: {e}")
            return False

    # ========================================================================
    # CORE LOGIC
    # ========================================================================

    def get_task_dependencies(self, task_id: str) -> List[str]:
        try:
            if USE_NEW_DEPENDENCIES:
                res = self.supabase.table("task_dependencies").select("depends_on_task_id").eq("task_id", task_id).execute()
                return [r['depends_on_task_id'] for r in (res.data or [])]
            else:
                res = self.supabase.table("tasks").select("depends_on_task_ids").eq("id", task_id).single().execute()
                deps = res.data.get('depends_on_task_ids', []) if res.data else []
                return deps if isinstance(deps, list) else []
        except Exception as e:
            logger.error(f"Failed to get deps: {e}")
            return []

    def _calculate_ui_status(self, task: Dict) -> str:
        state = task.get('state')
        if state == 'APPROVED': return 'READY'
        if state in ['DRAFT', 'PRICED']: return 'PENDING'
        if state == 'BLOCKED': return 'BLOCKED'
        return 'READY' if state in ['IN_PROGRESS', 'DONE'] else 'PENDING'

    def diagnose_dependencies(self, task_id: str) -> Dict:
        return {"current_source": "table" if USE_NEW_DEPENDENCIES else "json"}

