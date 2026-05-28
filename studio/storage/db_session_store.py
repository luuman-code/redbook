"""Database-based SessionStore implementation"""
import json
from datetime import datetime
from typing import Any, Dict, List, Optional

from sqlalchemy import select, delete
from sqlalchemy.ext.asyncio import AsyncSession

from ..db.connection import get_db
from ..db.models import Session as DBSession, SessionItem as DBItem, SessionVersion as DBVersion


class DBSessionStore:
    """Database SessionStore"""

    async def save(self, session, user_id: int = 1) -> None:
        """Save or update Session"""
        async with get_db() as db:
            result = await db.execute(
                select(DBSession).where(DBSession.session_id == session.session_id)
            )
            db_session = result.scalar_one_or_none()

            if db_session:
                # Update
                db_session.brief_json = session.brief.to_dict() if hasattr(session.brief, 'to_dict') else session.brief
                db_session.plan_json = session.current_plan.to_dict() if hasattr(session.current_plan, 'to_dict') else {}
                db_session.status = session.status.value if hasattr(session.status, 'value') else str(session.status)
                db_session.current_version = session.current_version
            else:
                # Create (use user_id parameter, default 1)
                db_session = DBSession(
                    user_id=user_id,
                    session_id=session.session_id,
                    brief_json=session.brief.to_dict() if hasattr(session.brief, 'to_dict') else session.brief,
                    plan_json=session.current_plan.to_dict() if hasattr(session.current_plan, 'to_dict') else {},
                    status=session.status.value if hasattr(session.status, 'value') else str(session.status),
                    current_version=session.current_version,
                )
                db.add(db_session)

            await db.commit()

    async def get(self, session_id: str) -> Optional[Any]:
        """Get Session"""
        async with get_db() as db:
            result = await db.execute(
                select(DBSession).where(DBSession.session_id == session_id)
            )
            db_session = result.scalar_one_or_none()
            if not db_session:
                return None
            return self._db_to_session(db_session)

    async def list(self) -> List[str]:
        """List all Session IDs"""
        async with get_db() as db:
            result = await db.execute(select(DBSession.session_id))
            return [row[0] for row in result.fetchall()]

    async def delete(self, session_id: str) -> bool:
        """Delete Session"""
        async with get_db() as db:
            await db.execute(
                delete(DBSession).where(DBSession.session_id == session_id)
            )
            await db.commit()
            return True

    def _db_to_session(self, db_session: DBSession) -> Any:
        """Convert database model to Session model"""
        from ..models.session import Session, SessionStatus
        from ..models.brief import Brief
        from ..models.content_plan import ContentPlan

        session = Session(
            session_id=db_session.session_id,
            brief=Brief.from_dict(db_session.brief_json) if db_session.brief_json else Brief(),
            current_plan=ContentPlan.from_dict(db_session.plan_json) if db_session.plan_json else ContentPlan(),
        )
        session.status = SessionStatus(db_session.status)
        session.current_version = db_session.current_version
        session.created_at = db_session.created_at
        session.updated_at = db_session.updated_at

        # Load items
        session.items = []
        for db_item in db_session.items:
            from ..models.content_item import ContentItem, ContentType, ItemStatus
            item = ContentItem(
                item_id=db_item.item_id,
                item_type=ContentType(db_item.item_type),
                content=db_item.content,
                metadata=db_item.metadata_json or {},
                status=ItemStatus(db_item.status),
                position=db_item.position,
                generation_prompt=db_item.generation_prompt,
                local_path=db_item.local_path,
            )
            session.items.append(item)

        # Load versions
        session.versions = []
        for db_version in db_session.versions:
            from ..models.version import Version
            version = Version(
                version_number=db_version.version_number,
                created_at=db_version.created_at,
                created_by=db_version.created_by,
                change_summary=db_version.change_summary,
                items_snapshot=db_version.items_snapshot_json,
                plan_snapshot=db_version.plan_snapshot_json,
            )
            session.versions.append(version)

        return session