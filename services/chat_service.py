# services/chat_service.py
"""
Chat Service v3.0 - NATIVE INTEGRATION
Obsługuje task_comments oraz activity_log.
"""

import logging
from datetime import datetime
from typing import List, Dict, Optional, Tuple
from supabase import Client

logger = logging.getLogger(__name__)

class ChatService:
    def __init__(self, supabase: Client):
        self.supabase = supabase

    def send_message(
        self,
        project_id: str,
        content: str,
        task_id: str,
        sender_id: str,
        sender_role: str,
        sender_display_name: str,
        recipient_role: str = "BOTH"
    ) -> Dict:
        """Wysyła wiadomość do tabeli task_comments."""
        try:
            message_data = {
                "task_id": task_id,
                "author_name": sender_display_name,
                "author_role": sender_role,
                "content": content.strip(),
                "created_at": datetime.now().isoformat()
            }
            
            response = self.supabase.table("task_comments").insert(message_data).execute()
            
            if response.data:
                return {"success": True, "message_id": response.data[0]["id"]}
            return {"success": False, "error": "Błąd zapisu w task_comments"}
        except Exception as e:
            logger.error(f"send_message error: {e}")
            return {"success": False, "error": str(e)}

    def get_chat_history(self, task_id: str, limit: int = 50) -> Tuple[List[Dict], int]:
        """Pobiera historię z task_comments."""
        try:
            response = self.supabase.table("task_comments")\
                .select("*", count="exact")\
                .eq("task_id", task_id)\
                .eq("is_deleted", False)\
                .order("created_at", desc=False)\
                .limit(limit)\
                .execute()
            
            return response.data or [], response.count or 0
        except Exception as e:
            logger.error(f"get_chat_history error: {e}")
            return [], 0

    def get_project_chat_history(self, project_id: str, limit: int = 100) -> List[Dict]:
        """Pobiera wszystkie komentarze dla wszystkich zadań w projekcie."""
        try:
            # Najpierw pobieramy ID wszystkich zadań w projekcie
            tasks_req = self.supabase.table("tasks").select("id").eq("project_id", project_id).execute()
            task_ids = [t['id'] for t in tasks_req.data] if tasks_req.data else []
            
            if not task_ids:
                return []

            # Pobieramy komentarze dla tych zadań
            response = self.supabase.table("task_comments")\
                .select("*")\
                .in_("task_id", task_ids)\
                .order("created_at", desc=False)\
                .limit(limit)\
                .execute()
            
            return response.data or []
        except Exception as e:
            logger.error(f"get_project_chat_history error: {e}")
            return []

    def get_activity_log(self, project_id: str, task_id: Optional[str] = None, limit: int = 50) -> Tuple[List[Dict], int]:
        """Pobiera zdarzenia z tabeli activity_log."""
        try:
            query = self.supabase.table("activity_log").select("*", count="exact")
            
            if task_id:
                query = query.eq("task_id", task_id)
            else:
                query = query.eq("project_id", project_id)
                
            response = query.order("created_at", desc=True).limit(limit).execute()
            
            # Mapowanie pól dla komponentu
            mapped_data = []
            for item in (response.data or []):
                mapped_data.append({
                    "content": f"{item.get('event_type', 'INFO')}: {item.get('description', '')}",
                    "created_at": item.get("created_at"),
                    "author": item.get("author_name")
                })
                
            return mapped_data, response.count or 0
        except Exception as e:
            logger.error(f"get_activity_log error: {e}")
            return [], 0
