"""JSON file storage migration to database"""
import json
import os
import sys
from pathlib import Path

# Add project root to path
project_root = Path(__file__).parent.parent
sys.path.insert(0, str(project_root))

import asyncio
from sqlalchemy import select

from studio.db.connection import init_db, get_db, engine
from studio.db.models import Session as DBSession, SessionItem as DBItem, SessionVersion as DBVersion


async def migrate_sessions():
    """Migrate all JSON files to database"""
    data_dir = Path(project_root) / "data" / "studio" / "sessions"

    if not data_dir.exists():
        print(f"Data directory does not exist: {data_dir}")
        return

    # Initialize database
    await init_db()
    print("Database tables created")

    migrated_count = 0

    async with get_db() as db:
        for session_dir in data_dir.iterdir():
            if not session_dir.is_dir():
                continue

            session_file = session_dir / "session.json"
            if not session_file.exists():
                continue

            try:
                with open(session_file, 'r', encoding='utf-8') as f:
                    session_data = json.load(f)

                # Create database record
                # Note: JSON data has no user info, default to 1
                db_session = DBSession(
                    user_id=1,
                    session_id=session_data['session_id'],
                    brief_json=session_data.get('brief', {}),
                    plan_json=session_data.get('plan', {}),
                    status=session_data.get('status', 'created'),
                    current_version=session_data.get('current_version', 1),
                )
                db.add(db_session)
                await db.flush()

                # Migrate items
                for item_data in session_data.get('items', []):
                    db_item = DBItem(
                        session_id=db_session.id,
                        item_id=item_data['item_id'],
                        item_type=item_data['item_type'],
                        content=item_data.get('content'),
                        metadata_json=item_data.get('metadata', {}),
                        status=item_data.get('status', 'pending'),
                        position=item_data.get('position', 0),
                        generation_prompt=item_data.get('generation_prompt'),
                        local_path=item_data.get('local_path'),
                    )
                    db.add(db_item)

                # Migrate versions
                for version_data in session_data.get('versions', []):
                    db_version = DBVersion(
                        session_id=db_session.id,
                        version_number=version_data['version_number'],
                        items_snapshot_json=version_data.get('items_snapshot', []),
                        plan_snapshot_json=version_data.get('plan_snapshot', {}),
                        change_summary=version_data.get('change_summary'),
                        created_by=version_data.get('created_by', 'system'),
                    )
                    db.add(db_version)

                migrated_count += 1
                print(f"Migration complete: {session_data['session_id']}")

            except Exception as e:
                print(f"Migration failed {session_dir.name}: {e}")

        await db.commit()

    print(f"\nMigration complete! Total sessions migrated: {migrated_count}")


if __name__ == "__main__":
    asyncio.run(migrate_sessions())