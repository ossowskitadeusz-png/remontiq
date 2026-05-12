# services/chat_service.py
"""
Chat Service – Obsługa wiadomości, Activity Log i notyfikacji.

Korzysta z Supabase RPC functions dla wydajności.
Wspiera: Direct messages, Task-based channels, Global messages.
"""

import logging
from datetime import datetime
from typing import List, Dict, Optional, Tuple
from supabase import Client

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

class ChatService:
    """
    Serwis do obsługi komunikacji w RemontIQ.
    """
    
    def __init__(self, supabase: Client):
        self.supabase = supabase
        logger.info("ChatService initialized")
    
    def send_message(
        self,
        project_id: str,
        content: str,
        task_id: Optional[str] = None,
        sender_id: Optional[str] = None,
        sender_role: str = "CREW_LEAD",
        sender_display_name: Optional[str] = None,
        recipient_role: str = "BOTH",
        message_type: str = "TEXT"
    ) -> Dict:
        """Wysyła wiadomość tekstową do czatu lub globalnego kanału."""
        try:
            if not content or len(content.strip()) == 0:
                return {"success": False, "error": "Content cannot be empty"}
            
            message_data = {
                "project_id": project_id,
                "task_id": task_id,
                "sender_id": sender_id,
                "sender_role": sender_role,
                "sender_display_name": sender_display_name,
                "recipient_role": recipient_role,
                "content": content.strip(),
                "message_type": message_type,
                "created_at": datetime.now().isoformat()
            }
            
            response = self.supabase.table("messages").insert(message_data).execute()
            
            if response.data:
                return {
                    "success": True,
                    "message_id": response.data[0]["id"],
                    "created_at": response.data[0]["created_at"]
                }
            return {"success": False, "error": "Database insert failed"}
        except Exception as e:
            logger.error(f"send_message error: {str(e)}")
            return {"success": False, "error": str(e)}
    
    def get_activity_log(self, task_id: str, limit: int = 50, offset: int = 0) -> Tuple[List[Dict], int]:
        """Pobiera Activity Log dla zadania."""
        try:
            response = self.supabase.table("messages")\
                .select("*", count="exact")\
                .eq("task_id", task_id)\
                .in_("message_type", ["SYSTEM", "STATUS_CHANGE", "PRICE_UPDATE"])\
                .order("created_at", desc=True)\
                .range(offset, offset + limit - 1)\
                .execute()
            
            return response.data or [], response.count or 0
        except Exception as e:
            logger.error(f"get_activity_log error: {str(e)}")
            return [], 0
    
    def get_chat_history(self, task_id: str, limit: int = 50, offset: int = 0) -> Tuple[List[Dict], int]:
        """Pobiera historię rozmowy (tylko TEXT messages)."""
        try:
            response = self.supabase.table("messages")\
                .select("*", count="exact")\
                .eq("task_id", task_id)\
                .eq("message_type", "TEXT")\
                .order("created_at", desc=True)\
                .range(offset, offset + limit - 1)\
                .execute()
            
            messages = response.data or []
            messages.reverse() # Oldest first
            return messages, response.count or 0
        except Exception as e:
            logger.error(f"get_chat_history error: {str(e)}")
            return [], 0
    
    def get_unread_count(self, user_id: str, user_role: str) -> Dict:
        """Licznik nieodczytanych wiadomości przez RPC."""
        try:
            response = self.supabase.rpc("get_unread_messages_for_user", {
                "p_user_id": user_id,
                "p_user_role": user_role
            }).execute()
            
            if response.data:
                unread_by_task = {}
                global_unread = 0
                for msg in response.data:
                    if msg.get("task_id"):
                        tid = msg["task_id"]
                        unread_by_task[tid] = unread_by_task.get(tid, 0) + 1
                    else:
                        global_unread += 1
                return {"total": len(response.data), "by_task": unread_by_task, "global": global_unread}
            return {"total": 0, "by_task": {}, "global": 0}
        except Exception as e:
            logger.error(f"get_unread_count error: {str(e)}")
            return {"total": 0, "by_task": {}, "global": 0}

    def mark_as_read(self, message_ids: List[str], user_role: str) -> Dict:
        """Oznacza wiadomości jako przeczytane przez RPC."""
        try:
            response = self.supabase.rpc("mark_messages_as_read", {
                "p_message_ids": message_ids,
                "p_user_role": user_role
            }).execute()
            return {"success": True, "updated_count": response.data}
        except Exception as e:
            logger.error(f"mark_as_read error: {str(e)}")
            return {"success": False, "error": str(e)}
