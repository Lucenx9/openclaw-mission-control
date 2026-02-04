from __future__ import annotations

from datetime import datetime
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy import asc, desc
from sqlmodel import Session, col, select

from app.api.deps import (
    ActorContext,
    get_board_or_404,
    get_task_or_404,
    require_admin_auth,
    require_admin_or_agent,
)
from app.core.auth import AuthContext
from app.db.session import get_session
from app.models.activity_events import ActivityEvent
from app.models.agents import Agent
from app.models.boards import Board
from app.models.tasks import Task
from app.schemas.tasks import TaskCommentCreate, TaskCommentRead, TaskCreate, TaskRead, TaskUpdate
from app.services.activity_log import record_activity

router = APIRouter(prefix="/boards/{board_id}/tasks", tags=["tasks"])

REQUIRED_COMMENT_FIELDS = ("summary:", "details:", "next:")
ALLOWED_STATUSES = {"inbox", "in_progress", "review", "done"}


def validate_task_status(status_value: str) -> None:
    if status_value not in ALLOWED_STATUSES:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail="Unsupported task status.",
        )


def is_valid_markdown_comment(message: str) -> bool:
    content = message.strip()
    if not content:
        return False
    lowered = content.lower()
    if not all(field in lowered for field in REQUIRED_COMMENT_FIELDS):
        return False
    if "- " not in content and "* " not in content:
        return False
    return True


def has_valid_recent_comment(
    session: Session,
    task: Task,
    agent_id: UUID | None,
    since: datetime | None,
) -> bool:
    if agent_id is None or since is None:
        return False
    statement = (
        select(ActivityEvent)
        .where(col(ActivityEvent.task_id) == task.id)
        .where(col(ActivityEvent.event_type) == "task.comment")
        .where(col(ActivityEvent.agent_id) == agent_id)
        .where(col(ActivityEvent.created_at) >= since)
        .order_by(desc(col(ActivityEvent.created_at)))
    )
    event = session.exec(statement).first()
    if event is None or event.message is None:
        return False
    return is_valid_markdown_comment(event.message)


@router.get("", response_model=list[TaskRead])
def list_tasks(
    status_filter: str | None = Query(default=None, alias="status"),
    assigned_agent_id: UUID | None = None,
    unassigned: bool | None = None,
    limit: int | None = Query(default=None, ge=1, le=200),
    board: Board = Depends(get_board_or_404),
    session: Session = Depends(get_session),
    actor: ActorContext = Depends(require_admin_or_agent),
) -> list[Task]:
    statement = select(Task).where(Task.board_id == board.id)
    if status_filter:
        statuses = [s.strip() for s in status_filter.split(",") if s.strip()]
        if statuses:
            if any(status not in ALLOWED_STATUSES for status in statuses):
                raise HTTPException(
                    status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
                    detail="Unsupported task status filter.",
                )
            statement = statement.where(col(Task.status).in_(statuses))
    if assigned_agent_id is not None:
        statement = statement.where(col(Task.assigned_agent_id) == assigned_agent_id)
    if unassigned:
        statement = statement.where(col(Task.assigned_agent_id).is_(None))
    if limit is not None:
        statement = statement.limit(limit)
    return list(session.exec(statement))


@router.post("", response_model=TaskRead)
def create_task(
    payload: TaskCreate,
    board: Board = Depends(get_board_or_404),
    session: Session = Depends(get_session),
    auth: AuthContext = Depends(require_admin_auth),
) -> Task:
    validate_task_status(payload.status)
    task = Task.model_validate(payload)
    task.board_id = board.id
    if task.created_by_user_id is None and auth.user is not None:
        task.created_by_user_id = auth.user.id
    session.add(task)
    session.commit()
    session.refresh(task)

    record_activity(
        session,
        event_type="task.created",
        task_id=task.id,
        message=f"Task created: {task.title}.",
    )
    session.commit()
    return task


@router.patch("/{task_id}", response_model=TaskRead)
def update_task(
    payload: TaskUpdate,
    task: Task = Depends(get_task_or_404),
    session: Session = Depends(get_session),
    actor: ActorContext = Depends(require_admin_or_agent),
) -> Task:
    previous_status = task.status
    updates = payload.model_dump(exclude_unset=True)
    comment = updates.pop("comment", None)
    if actor.actor_type == "agent":
        if actor.agent and actor.agent.board_id and task.board_id:
            if actor.agent.board_id != task.board_id:
                raise HTTPException(status_code=status.HTTP_403_FORBIDDEN)
        allowed_fields = {"status", "comment"}
        if not set(updates).issubset(allowed_fields):
            raise HTTPException(status_code=status.HTTP_403_FORBIDDEN)
        if "status" in updates:
            validate_task_status(updates["status"])
            if updates["status"] == "inbox":
                task.assigned_agent_id = None
                task.in_progress_at = None
            else:
                task.assigned_agent_id = actor.agent.id if actor.agent else None
                if updates["status"] == "in_progress":
                    task.in_progress_at = datetime.utcnow()
    elif "status" in updates:
        validate_task_status(updates["status"])
        if updates["status"] == "inbox":
            task.assigned_agent_id = None
            task.in_progress_at = None
        elif updates["status"] == "in_progress":
            task.in_progress_at = datetime.utcnow()
    if "assigned_agent_id" in updates and updates["assigned_agent_id"]:
        agent = session.get(Agent, updates["assigned_agent_id"])
        if agent is None:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND)
        if agent.board_id and task.board_id and agent.board_id != task.board_id:
            raise HTTPException(status_code=status.HTTP_409_CONFLICT)
    for key, value in updates.items():
        setattr(task, key, value)
    task.updated_at = datetime.utcnow()

    if "status" in updates and updates["status"] == "review":
        if comment is not None and comment.strip():
            if not is_valid_markdown_comment(comment):
                raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY)
        else:
            if not has_valid_recent_comment(
                session,
                task,
                task.assigned_agent_id,
                task.in_progress_at,
            ):
                raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY)

    session.add(task)
    session.commit()
    session.refresh(task)

    if comment is not None and comment.strip():
        if actor.actor_type == "agent" and not is_valid_markdown_comment(comment):
            raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY)
        event = ActivityEvent(
            event_type="task.comment",
            message=comment.strip(),
            task_id=task.id,
            agent_id=actor.agent.id if actor.actor_type == "agent" and actor.agent else None,
        )
        session.add(event)
        session.commit()

    if "status" in updates and task.status != previous_status:
        event_type = "task.status_changed"
        message = f"Task moved to {task.status}: {task.title}."
    else:
        event_type = "task.updated"
        message = f"Task updated: {task.title}."
    record_activity(
        session,
        event_type=event_type,
        task_id=task.id,
        message=message,
        agent_id=actor.agent.id if actor.actor_type == "agent" and actor.agent else None,
    )
    session.commit()
    return task


@router.delete("/{task_id}")
def delete_task(
    session: Session = Depends(get_session),
    task: Task = Depends(get_task_or_404),
    auth: AuthContext = Depends(require_admin_auth),
) -> dict[str, bool]:
    session.delete(task)
    session.commit()
    return {"ok": True}


@router.get("/{task_id}/comments", response_model=list[TaskCommentRead])
def list_task_comments(
    task: Task = Depends(get_task_or_404),
    session: Session = Depends(get_session),
    actor: ActorContext = Depends(require_admin_or_agent),
) -> list[ActivityEvent]:
    if actor.actor_type == "agent" and actor.agent:
        if actor.agent.board_id and task.board_id and actor.agent.board_id != task.board_id:
            raise HTTPException(status_code=status.HTTP_403_FORBIDDEN)
    statement = (
        select(ActivityEvent)
        .where(col(ActivityEvent.task_id) == task.id)
        .where(col(ActivityEvent.event_type) == "task.comment")
        .order_by(asc(col(ActivityEvent.created_at)))
    )
    return list(session.exec(statement))


@router.post("/{task_id}/comments", response_model=TaskCommentRead)
def create_task_comment(
    payload: TaskCommentCreate,
    task: Task = Depends(get_task_or_404),
    session: Session = Depends(get_session),
    actor: ActorContext = Depends(require_admin_or_agent),
) -> ActivityEvent:
    if actor.actor_type == "agent" and actor.agent:
        if actor.agent.board_id and task.board_id and actor.agent.board_id != task.board_id:
            raise HTTPException(status_code=status.HTTP_403_FORBIDDEN)
    if not payload.message.strip():
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY)
    if actor.actor_type == "agent" and not is_valid_markdown_comment(payload.message):
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY)
    event = ActivityEvent(
        event_type="task.comment",
        message=payload.message.strip(),
        task_id=task.id,
        agent_id=actor.agent.id if actor.actor_type == "agent" and actor.agent else None,
    )
    session.add(event)
    session.commit()
    session.refresh(event)
    return event
