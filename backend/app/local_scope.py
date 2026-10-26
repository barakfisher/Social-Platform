from uuid import UUID

from sqlalchemy.orm import Session

from app.models import User, Workspace

LOCAL_USER_ID = UUID("00000000-0000-4000-8000-000000000001")
LOCAL_WORKSPACE_ID = UUID("00000000-0000-4000-8000-000000000002")


def seed_local_scope(session: Session) -> None:
    from sqlalchemy.dialects.postgresql import insert

    session.execute(
        insert(User).values(id=LOCAL_USER_ID, name="Local user").on_conflict_do_nothing()
    )
    session.execute(
        insert(Workspace)
        .values(
            id=LOCAL_WORKSPACE_ID,
            user_id=LOCAL_USER_ID,
            name="My brand",
        )
        .on_conflict_do_nothing()
    )
