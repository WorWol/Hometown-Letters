from __future__ import annotations

from fastapi import APIRouter, Depends
from pydantic import BaseModel, Field
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from auth.dependencies import get_current_user
from db.database import get_db
from db.models import Letter, Mail, Postcard, User
from .common import mail_dict

router = APIRouter(tags=["mail"])


class MailSendReq(BaseModel):
    recipient_username: str
    title: str = ""
    content: str
    attached_postcard_id: int | None = None
    attached_letter_id: int | None = None


def _page(page: int, page_size: int) -> tuple[int, int, int]:
    page = max(1, page)
    page_size = max(1, min(page_size, 50))
    return page, page_size, (page - 1) * page_size


def _mail_query():
    return select(Mail).options(selectinload(Mail.sender), selectinload(Mail.recipient), selectinload(Mail.attached_postcard), selectinload(Mail.attached_letter))


@router.post("/mail/send")
async def send_mail(body: MailSendReq, user: User = Depends(get_current_user), db: AsyncSession = Depends(get_db)):
    recipient = await db.scalar(select(User).where(User.username == body.recipient_username))
    if recipient is None:
        return {"ok": False, "error": "收件人不存在"}
    if recipient.id == user.id:
        return {"ok": False, "error": "不能给自己发信"}
    if body.attached_postcard_id is not None and await db.scalar(select(Postcard).where(Postcard.id == body.attached_postcard_id, Postcard.user_id == user.id)) is None:
        return {"ok": False, "error": "附带明信片不存在或不属于你"}
    if body.attached_letter_id is not None and await db.scalar(select(Letter).where(Letter.id == body.attached_letter_id, Letter.user_id == user.id)) is None:
        return {"ok": False, "error": "附带信件不存在或不属于你"}
    mail = Mail(sender_id=user.id, recipient_id=recipient.id, title=body.title, content=body.content, attached_postcard_id=body.attached_postcard_id, attached_letter_id=body.attached_letter_id)
    db.add(mail)
    await db.flush()
    return {"ok": True, "data": {"id": str(mail.id), "sentAt": mail.sent_at.isoformat() if mail.sent_at else ""}}


@router.get("/mail/inbox")
async def get_inbox(page: int = 1, page_size: int = 20, user: User = Depends(get_current_user), db: AsyncSession = Depends(get_db)):
    page, page_size, offset = _page(page, page_size)
    where = (Mail.recipient_id == user.id, Mail.recipient_deleted.is_(False))
    unread = await db.scalar(select(func.count(Mail.id)).where(*where, Mail.is_read.is_(False))) or 0
    rows = (await db.scalars(_mail_query().where(*where).order_by(Mail.sent_at.desc()).offset(offset).limit(page_size))).all()
    total = await db.scalar(select(func.count(Mail.id)).where(*where)) or 0
    return {"ok": True, "data": {"mails": [mail_dict(row) for row in rows], "unreadCount": unread, "total": total, "page": page, "pageSize": page_size}}


@router.get("/mail/outbox")
async def get_outbox(page: int = 1, page_size: int = 20, user: User = Depends(get_current_user), db: AsyncSession = Depends(get_db)):
    page, page_size, offset = _page(page, page_size)
    where = (Mail.sender_id == user.id, Mail.sender_deleted.is_(False))
    rows = (await db.scalars(_mail_query().where(*where).order_by(Mail.sent_at.desc()).offset(offset).limit(page_size))).all()
    total = await db.scalar(select(func.count(Mail.id)).where(*where)) or 0
    return {"ok": True, "data": {"mails": [mail_dict(row) for row in rows], "total": total, "page": page, "pageSize": page_size}}


@router.get("/mail/{mail_id}")
async def get_mail_detail(mail_id: int, user: User = Depends(get_current_user), db: AsyncSession = Depends(get_db)):
    mail = await db.scalar(_mail_query().where(Mail.id == mail_id))
    if mail is None:
        return {"ok": False, "error": "信件不存在"}
    if mail.sender_id != user.id and mail.recipient_id != user.id:
        return {"ok": False, "error": "无权查看此信件"}
    return {"ok": True, "data": mail_dict(mail)}


@router.put("/mail/{mail_id}/read")
async def mark_mail_read(mail_id: int, user: User = Depends(get_current_user), db: AsyncSession = Depends(get_db)):
    mail = await db.scalar(select(Mail).where(Mail.id == mail_id))
    if mail is None:
        return {"ok": False, "error": "信件不存在"}
    if mail.recipient_id != user.id:
        return {"ok": False, "error": "只有收件人可以标记已读"}
    mail.is_read = True
    await db.flush()
    return {"ok": True, "data": {"id": str(mail.id), "isRead": True}}


@router.delete("/mail/{mail_id}")
async def delete_mail(mail_id: int, user: User = Depends(get_current_user), db: AsyncSession = Depends(get_db)):
    mail = await db.scalar(select(Mail).where(Mail.id == mail_id))
    if mail is None:
        return {"ok": False, "error": "信件不存在"}
    if mail.sender_id != user.id and mail.recipient_id != user.id:
        return {"ok": False, "error": "无权删除此信件"}
    if mail.sender_id == user.id:
        mail.sender_deleted = True
    if mail.recipient_id == user.id:
        mail.recipient_deleted = True
    await db.flush()
    return {"ok": True, "data": {"id": str(mail.id)}}


@router.get("/users/lookup")
async def lookup_users(q: str = "", user: User = Depends(get_current_user), db: AsyncSession = Depends(get_db)):
    if not q.strip():
        return {"ok": True, "data": {"users": []}}
    rows = (await db.scalars(select(User).where(User.username.contains(q.strip()), User.id != user.id).limit(20))).all()
    return {"ok": True, "data": {"users": [{"id": row.id, "username": row.username} for row in rows]}}
