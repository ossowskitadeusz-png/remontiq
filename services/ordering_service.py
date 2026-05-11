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
    def __init__(self, supabase: Client):
        self.supabase = supabase
        logger.info(f"OrderingService v2.2 initialized. USE_NEW_DEPENDENCIES={USE_NEW_DEPENDENCIES}")

    # ========================================================================
    # UI METHODS (Dla Panelu Karola)
    # ========================================================================
    
    def get_ordered_tasks(self, phase_id: str) -> List[Dict]:
        try:
            res = self.supabase.table("tasks")\
                .select("id, name, state, sort_order, final_approved_price, commercial_status, kanban_status")\
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
            task_res = self.supabase.table("tasks").select("id, phase_id, sort_order").eq("id", task_id).single().execute()
            task = task_res.data
            if not task: return False
            
            neighbor_order = task['sort_order'] + direction
            neighbor_res = self.supabase.table("tasks")\
                .select("id, sort_order")\
                .eq("phase_id", task['phase_id'])\
                .eq("sort_order", neighbor_order)\
                .execute()
            
            if neighbor_res.data:
                neighbor = neighbor_res.data[0]
                updates = [
                    {"id": task['id'], "sort_order": neighbor_order},
                    {"id": neighbor['id'], "sort_order": task['sort_order']}
                ]
                self.supabase.table("tasks").upsert(updates).execute()
                return True
            return False
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
