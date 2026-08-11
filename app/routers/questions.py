from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import select
from sqlalchemy.orm import Session, selectinload

from ..activity import grant_xp, record_activity
from ..daily_quests import record_daily_quest_progress
from ..database import get_db
from ..deps import get_current_user
from ..models import Answer, Notification, Quest, Question, User
from ..realtime import manager
from ..schemas import AnswerCreate, QuestionCreate
from ..serializers import question_public

router = APIRouter(prefix="/questions", tags=["Ask Seniors"])


def question_query():
    return select(Question).options(
        selectinload(Question.author),
        selectinload(Question.answers).selectinload(Answer.author),
    )


@router.get("")
def list_questions(current_user: User = Depends(get_current_user), db: Session = Depends(get_db)) -> list[dict]:
    questions = db.scalars(question_query().order_by(Question.created_at.desc()).limit(100)).all()
    return [question_public(item) for item in questions]


@router.get("/{question_id}")
def get_question(
    question_id: int,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> dict:
    question = db.scalar(question_query().where(Question.id == question_id))
    if question is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Question not found")
    return question_public(question, include_answers=True)


@router.post("", status_code=status.HTTP_201_CREATED)
async def create_question(
    payload: QuestionCreate,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> dict:
    question = Question(
        title=payload.title.strip(),
        body=payload.body.strip(),
        tags=",".join(tag.strip().lower() for tag in payload.tags if tag.strip()),
        author_id=current_user.id,
    )
    db.add(question)
    quest = db.scalar(select(Quest).where(Quest.user_id == current_user.id, Quest.title == "Ask Your First Question"))
    if quest:
        quest.current = quest.target
    grant_xp(db, current_user, 10)
    record_activity(db, current_user.id, 2)
    record_daily_quest_progress(db, current_user, "ask_question")
    db.commit()
    question = db.scalar(question_query().where(Question.id == question.id))
    await manager.broadcast({"type": "question.created", "message": f"{current_user.name} asked for help: {question.title}"})
    return question_public(question, include_answers=True)


@router.post("/{question_id}/answers", status_code=status.HTTP_201_CREATED)
async def create_answer(
    question_id: int,
    payload: AnswerCreate,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> dict:
    question = db.get(Question, question_id)
    if question is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Question not found")
    answer = Answer(body=payload.body.strip(), author_id=current_user.id, question_id=question.id)
    db.add(answer)
    grant_xp(db, current_user, 15)
    record_activity(db, current_user.id, 2)
    record_daily_quest_progress(db, current_user, "answer_question")
    if question.author_id != current_user.id:
        db.add(Notification(user_id=question.author_id, message=f"{current_user.name} answered your question.", kind="answer"))
    db.commit()
    await manager.send_to_user(question.author_id, {"type": "question.answered", "message": f"{current_user.name} answered your question."})
    question = db.scalar(question_query().where(Question.id == question_id))
    return question_public(question, include_answers=True)


@router.patch("/{question_id}/answers/{answer_id}/accept")
def accept_answer(
    question_id: int,
    answer_id: int,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> dict:
    question = db.scalar(question_query().where(Question.id == question_id))
    if question is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Question not found")
    if question.author_id != current_user.id:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Only the question owner can accept an answer")
    answer = next((item for item in question.answers if item.id == answer_id), None)
    if answer is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Answer not found")
    for item in question.answers:
        item.is_accepted = item.id == answer_id
    question.solved = True
    grant_xp(db, answer.author, 50)
    record_activity(db, answer.author_id, 3)
    db.add(Notification(user_id=answer.author_id, message="Your answer was accepted. +50 XP", kind="achievement"))
    db.commit()
    question = db.scalar(question_query().where(Question.id == question_id))
    return question_public(question, include_answers=True)
