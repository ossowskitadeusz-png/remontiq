import logging
import sys
from typing import Set, Tuple
from supabase import create_client, Client

# Setup logging
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

def run_migration(supabase: Client) -> Tuple[int, int, int]:
    logger.info("=" * 80)
    logger.info("🚀 START MIGRACJI: depends_on_task_ids -> task_dependencies")
    logger.info("=" * 80)
    
    # KROK 1: Pobierz wszystkie task IDs (do walidacji)
    logger.info("📋 Pobieranie listy wszystkich tasków...")
    try:
        all_tasks = supabase.table("tasks").select("id").execute().data or []
        valid_task_ids: Set[str] = {t['id'] for t in all_tasks}
        logger.info(f"   ✅ Found {len(valid_task_ids)} valid task IDs")
    except Exception as e:
        logger.error(f"   ❌ Failed to fetch task IDs: {e}")
        return 0, 1, 0
    
    # KROK 2: Pobierz taski z zależnościami
    logger.info("📋 Pobieranie tasków z zależnościami...")
    try:
        tasks = supabase.table("tasks").select("id, depends_on_task_ids").execute().data or []
        logger.info(f"   ✅ Found {len(tasks)} tasks")
    except Exception as e:
        logger.error(f"   ❌ Failed to fetch tasks: {e}")
        return 0, 1, 0
    
    # KROK 3: Migruj relacje (z walidacją)
    logger.info("🔄 Migrowanie relacji...")
    migrated = 0
    errors = 0
    skipped = 0
    
    for task in tasks:
        task_id = task.get('id')
        deps = task.get('depends_on_task_ids', [])
        
        if not deps or not isinstance(deps, list):
            skipped += 1
            continue
        
        for dep_id in deps:
            # WALIDACJA 1: Czy zależne zadanie istnieje?
            if dep_id not in valid_task_ids:
                logger.error(f"   ❌ Task {task_id} ma zależ do nieistniejącego ID: {dep_id}")
                errors += 1
                continue
            
            # WALIDACJA 2: Czy to nie self-dependency?
            if dep_id == task_id:
                logger.warning(f"   ⚠️  Pomijam self-dependency: {task_id} → {task_id}")
                skipped += 1
                continue
            
            # MIGRACJA
            try:
                supabase.table("task_dependencies").upsert({
                    "task_id": task_id,
                    "depends_on_task_id": dep_id,
                    "dependency_type": "finish_to_start"
                }).execute()
                migrated += 1
            except Exception as e:
                logger.error(f"   ❌ Error migrating {task_id} → {dep_id}: {e}")
                errors += 1
    
    logger.info("=" * 80)
    logger.info("📊 RAPORT MIGRACJI:")
    logger.info(f"   ✅ Zmigrowano: {migrated} relacji")
    logger.info(f"   ❌ Błędy: {errors}")
    logger.info(f"   ⏭️  Pominięte: {skipped}")
    logger.info(f"   📊 RAZEM: {migrated + errors + skipped}")
    logger.info("=" * 80)
    
    return migrated, errors, skipped

if __name__ == "__main__":
    url = "https://mgrrsrgnalxtbrvzqyid.supabase.co"
    key = "eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.eyJpc3MiOiJzdXBhYmFzZSIsInJlZiI6Im1ncnJzcmduYWx4dGJydnpxeWlkIiwicm9sZSI6ImFub24iLCJpYXQiOjE3NzgwOTQ4NTksImV4cCI6MjA5MzY3MDg1OX0.LtzUjbFOb9uV3T4ptJFbNcp3UHiKl2EDbvw1d1ZZZX0"
    supabase: Client = create_client(url, key)
    migrated, errors, skipped = run_migration(supabase)
    sys.exit(0 if errors == 0 else 1)
