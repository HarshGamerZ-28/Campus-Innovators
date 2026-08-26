from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy import select
from sqlalchemy.orm import Session, selectinload

from ..database import get_db
from ..deps import get_current_user
from ..habits import recalc_subtask_progress, set_task_status, task_stats
from ..models import Subtask, Task, User
from ..schemas import (
    SubtaskCreate,
    SubtaskResponse,
    TaskCreate,
    TaskResponse,
    TaskStatsResponse,
    TaskStatusUpdate,
    TaskUpdate,
)

router = APIRouter(prefix="/tasks", tags=["Tasks"])
subtasks_router = APIRouter(prefix="/subtasks", tags=["Tasks"])


def _get_owned_task(db: Session, task_id: int, user_id: int) -> Task:
    task = db.scalar(select(Task).options(selectinload(Task.subtasks)).where(Task.id == task_id))
    if task is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Task not found")
    if task.user_id != user_id:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="You cannot access another member's task")
    return task


def _get_owned_subtask(db: Session, subtask_id: int, user_id: int) -> tuple[Subtask, Task]:
    subtask = db.scalar(select(Subtask).options(selectinload(Subtask.task).selectinload(Task.subtasks)).where(Subtask.id == subtask_id))
    if subtask is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Subtask not found")
    if subtask.task.user_id != user_id:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="You cannot access another member's task")
    return subtask, subtask.task


@router.get("/stats", response_model=TaskStatsResponse)
def get_task_stats(current_user: User = Depends(get_current_user), db: Session = Depends(get_db)) -> dict:
    return task_stats(db, current_user.id)


@router.post("", response_model=TaskResponse, status_code=status.HTTP_201_CREATED)
def create_task(payload: TaskCreate, current_user: User = Depends(get_current_user), db: Session = Depends(get_db)) -> Task:
    task = Task(user_id=current_user.id, **payload.model_dump())
    db.add(task)
    db.commit()
    db.refresh(task)
    return task


@router.get("", response_model=list[TaskResponse])
def list_tasks(
    status_filter: str | None = Query(default=None, alias="status"),
    category: str | None = None,
    priority: str | None = None,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> list[Task]:
    query = select(Task).options(selectinload(Task.subtasks)).where(Task.user_id == current_user.id)
    if status_filter:
        query = query.where(Task.status == status_filter)
    if category:
        query = query.where(Task.category == category)
    if priority:
        query = query.where(Task.priority == priority)
    return list(db.scalars(query.order_by(Task.created_at.desc())).all())


@router.get("/{task_id}", response_model=TaskResponse)
def get_task(task_id: int, current_user: User = Depends(get_current_user), db: Session = Depends(get_db)) -> Task:
    return _get_owned_task(db, task_id, current_user.id)


@router.put("/{task_id}", response_model=TaskResponse)
def update_task(task_id: int, payload: TaskUpdate, current_user: User = Depends(get_current_user), db: Session = Depends(get_db)) -> Task:
    task = _get_owned_task(db, task_id, current_user.id)
    for field, value in payload.model_dump(exclude_unset=True).items():
        setattr(task, field, value)
    db.commit()
    db.refresh(task)
    return task


@router.delete("/{task_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_task(task_id: int, current_user: User = Depends(get_current_user), db: Session = Depends(get_db)) -> None:
    task = _get_owned_task(db, task_id, current_user.id)
    db.delete(task)
    db.commit()


@router.patch("/{task_id}/status", response_model=TaskResponse)
def update_task_status(task_id: int, payload: TaskStatusUpdate, current_user: User = Depends(get_current_user), db: Session = Depends(get_db)) -> Task:
    task = _get_owned_task(db, task_id, current_user.id)
    set_task_status(db, current_user, task, payload.status)
    db.commit()
    db.refresh(task)
    return task


@router.post("/{task_id}/subtasks", response_model=SubtaskResponse, status_code=status.HTTP_201_CREATED)
def create_subtask(task_id: int, payload: SubtaskCreate, current_user: User = Depends(get_current_user), db: Session = Depends(get_db)) -> Subtask:
    task = _get_owned_task(db, task_id, current_user.id)
    subtask = Subtask(task_id=task.id, title=payload.title)
    task.subtasks.append(subtask)
    db.flush()
    recalc_subtask_progress(db, current_user, task)
    db.commit()
    db.refresh(subtask)
    return subtask


@subtasks_router.patch("/{subtask_id}", response_model=SubtaskResponse)
def toggle_subtask(subtask_id: int, current_user: User = Depends(get_current_user), db: Session = Depends(get_db)) -> Subtask:
    subtask, task = _get_owned_subtask(db, subtask_id, current_user.id)
    subtask.is_completed = not subtask.is_completed
    recalc_subtask_progress(db, current_user, task)
    db.commit()
    db.refresh(subtask)
    return subtask


@subtasks_router.delete("/{subtask_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_subtask(subtask_id: int, current_user: User = Depends(get_current_user), db: Session = Depends(get_db)) -> None:
    subtask, task = _get_owned_subtask(db, subtask_id, current_user.id)
    task.subtasks.remove(subtask)
    db.flush()
    recalc_subtask_progress(db, current_user, task)
    db.commit()
