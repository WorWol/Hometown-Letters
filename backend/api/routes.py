"""API 路由 — 全部需要 Bearer Token 认证，通过 DI 注入服务"""
from __future__ import annotations

import logging
from datetime import datetime, timezone

from fastapi import APIRouter, Depends, HTTPException, Request, status
from pydantic import BaseModel
from sqlalchemy import and_, select, update
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from auth.dependencies import get_current_user
from db.database import get_db
from db.models import Hometown, Letter, LetterLike, Mail, Memory, PastSelfProfile, Postcard, SystemEvent, User
from services import image_storage

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api", tags=["api"])


# ──────────── 请求模型 ────────────

class HometownInitReq(BaseModel):
    province: str = ""
    city: str = ""
    county: str = ""
    hometown_name: str = ""


class LetterSendReq(BaseModel):
    text: str
    place_hint: str = ""
    mood_hint: str = ""


class MemorySaveReq(BaseModel):
    text: str
    tags: list[str] = []
    place_hint: str = ""


class MailSendReq(BaseModel):
    recipient_username: str
    title: str = ""
    content: str
    attached_postcard_id: int | None = None
    attached_letter_id: int | None = None


# ──────────── DI 依赖 ────────────

def get_llm(request: Request):
    return request.app.state.llm


def get_search(request: Request):
    return request.app.state.search


def get_pipeline(request: Request):
    return request.app.state.pipeline


# ──────────── 端点 ────────────

@router.get("/state")
async def get_state(
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """获取完整游戏状态"""
    result = await db.execute(select(Hometown).where(Hometown.user_id == user.id))
    h = result.scalar_one_or_none()
    hometown = {
        "province": h.province if h else "",
        "city": h.city if h else "",
        "county": h.county if h else "",
        "hometownName": h.hometown_name if h else "",
    }

    # Postcards
    result = await db.execute(
        select(Postcard)
        .where(Postcard.user_id == user.id)
        .order_by(Postcard.created_at.desc())
        .limit(100)
    )
    postcards = []
    for pc in result.scalars().all():
        image_url = image_storage.get_image_url(pc.image_card_key)
        image_thumb_url = image_storage.get_image_url(pc.image_thumb_key)
        image_original_url = image_storage.get_image_url(pc.image_original_key)
        postcards.append({
            "id": str(pc.id),
            "title": pc.title,
            "body": pc.body,
            "poem": pc.poem,
            "place": pc.place,
            "landmarkId": pc.landmark_id,
            "landmarkDescription": pc.landmark_description,
            "mood": pc.mood,
            "imageUrl": image_url,
            "imageThumbUrl": image_thumb_url,
            "imageOriginalUrl": image_original_url,
            "imagePrompt": pc.image_prompt,
            "searchImageUrls": pc.search_image_urls,
            "createdAt": pc.created_at.isoformat() if pc.created_at else "",
            "letterText": pc.letter_text,
            "tags": pc.tags,
        })

    # Letters
    result = await db.execute(
        select(Letter)
        .where(Letter.user_id == user.id)
        .order_by(Letter.timestamp.desc())
        .limit(20)
    )
    letters = []
    for lt in result.scalars().all():
        letters.append({
            "id": f"ltr-{lt.id}",
            "text": lt.text,
            "place": lt.place,
            "mood": lt.mood,
            "timestamp": lt.timestamp.isoformat() if lt.timestamp else "",
        })

    # Memories
    result = await db.execute(
        select(Memory)
        .where(Memory.user_id == user.id)
        .order_by(Memory.timestamp.desc())
        .limit(40)
    )
    memories = []
    for mem in result.scalars().all():
        memories.append({
            "id": f"mem-{mem.id}",
            "text": mem.text,
            "tags": mem.tags,
            "placeHint": mem.place_hint,
            "timestamp": mem.timestamp.isoformat() if mem.timestamp else "",
            "analysisStatus": mem.analysis_status,
            "summary": mem.summary,
        })

    # Past self profile
    result = await db.execute(
        select(PastSelfProfile).where(PastSelfProfile.user_id == user.id)
    )
    psp = result.scalar_one_or_none()
    past_self = {}
    if psp:
        past_self = {
            "summary": psp.summary,
            "latent_place_affinities": psp.latent_place_affinities,
            "sensory_biases": psp.sensory_biases,
            "identity_signals": psp.identity_signals,
            "recent_memory_signals": psp.recent_memory_signals,
        }

    # Liked community letters
    liked_result = await db.execute(
        select(LetterLike, Letter, Postcard, User)
        .join(Letter, LetterLike.letter_id == Letter.id)
        .outerjoin(
            Postcard,
            and_(
                Postcard.user_id == Letter.user_id,
                Postcard.letter_text == Letter.text,
            ),
        )
        .join(User, Letter.user_id == User.id)
        .where(LetterLike.user_id == user.id)
        .order_by(LetterLike.created_at.desc())
        .limit(20)
    )
    liked_items = []
    for lk, lt, pc, u in liked_result.all():
        h_result = await db.execute(select(Hometown).where(Hometown.user_id == u.id))
        ht = h_result.scalar_one_or_none()
        item = {
            "id": f"ltr-{lt.id}",
            "text": lt.text,
            "place": lt.place or "",
            "mood": lt.mood or "",
            "timestamp": lt.timestamp.isoformat() if lt.timestamp else "",
            "author": {
                "username": u.username,
                "hometown": ht.hometown_name or ht.city or "" if ht else "",
            },
        }
        if pc:
            item["postcard"] = _build_postcard_dict(pc)
        liked_items.append(item)

    return {
        "ok": True,
        "data": {
            "current_day": user.current_day,
            "postcard_limit": user.postcard_limit,
            "postcard_count": user.postcard_count,
            "hometown": hometown,
            "profile": {"hometownName": hometown.get("hometownName", "")},
            "letters": letters,
            "memories": memories,
            "postcards": postcards,
            "past_self_profile": past_self,
            "likedItems": liked_items,
        },
    }


@router.post("/hometown/init")
async def init_hometown(
    body: HometownInitReq,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """初始化/更新故乡"""
    result = await db.execute(select(Hometown).where(Hometown.user_id == user.id))
    h = result.scalar_one_or_none()

    if h:
        h.province = body.province
        h.city = body.city
        h.county = body.county
        h.hometown_name = body.hometown_name or f"{body.province}{body.city}{body.county}"
    else:
        h = Hometown(
            user_id=user.id,
            province=body.province,
            city=body.city,
            county=body.county,
            hometown_name=body.hometown_name or f"{body.province}{body.city}{body.county}",
        )
        db.add(h)

    await db.flush()

    hometown_dict = {
        "province": h.province, "city": h.city,
        "county": h.county, "hometownName": h.hometown_name,
    }
    return {
        "ok": True,
        "data": {
            "hometown": hometown_dict,
            "profile": {"hometownName": h.hometown_name or ""},
        },
    }


@router.post("/letter/send")
async def send_letter(
    body: LetterSendReq,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
    pipeline=Depends(get_pipeline),
):
    """发信核心流程"""
    reservation = await db.execute(
        update(User)
        .where(User.id == user.id, User.postcard_count < User.postcard_limit)
        .values(postcard_count=User.postcard_count + 1)
    )
    if reservation.rowcount != 1:
        db.add(SystemEvent(
            level="warning",
            event_type="postcard_quota_rejected",
            message="postcard quota exhausted",
            user_id=user.id,
            event_metadata={"limit": user.postcard_limit},
        ))
        raise HTTPException(
            status_code=status.HTTP_429_TOO_MANY_REQUESTS,
            detail=f"每位用户最多生成 {user.postcard_limit} 张明信片",
        )
    await db.flush()
    try:
        result = await pipeline.process(
            db=db,
            user=user,
            text=body.text,
            place_hint=body.place_hint,
            mood_hint=body.mood_hint,
        )
        if not result.get("ok"):
            await db.execute(
                update(User).where(User.id == user.id).values(postcard_count=User.postcard_count - 1)
            )
            db.add(SystemEvent(
                level="error",
                event_type="postcard_failed",
                message=result.get("error", "postcard pipeline failed"),
                user_id=user.id,
            ))
        else:
            db.add(SystemEvent(
                level="info",
                event_type="postcard_created",
                message="postcard created",
                user_id=user.id,
                event_metadata={"postcard_id": result.get("data", {}).get("id")},
            ))
        return result
    except Exception:
        await db.execute(
            update(User).where(User.id == user.id).values(postcard_count=User.postcard_count - 1)
        )
        raise


@router.post("/memory/save")
async def save_memory(
    body: MemorySaveReq,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
    llm=Depends(get_llm),
):
    """保存记忆"""
    memory = Memory(
        user_id=user.id,
        text=body.text,
        tags=body.tags,
        place_hint=body.place_hint,
        timestamp=datetime.now(timezone.utc),
        analysis_status="pending",
    )
    db.add(memory)
    await db.flush()

    summary = llm.chat(
        "用一句话概括这段记忆的核心场景和情感。",
        body.text, temperature=0.5, max_tokens=100,
    )
    memory.analysis_status = "completed"
    memory.summary = summary

    await db.flush()

    return {
        "ok": True,
        "data": {
            "id": f"mem-{memory.id}",
            "text": memory.text,
            "tags": memory.tags,
            "placeHint": memory.place_hint,
            "timestamp": memory.timestamp.isoformat(),
            "analysisStatus": memory.analysis_status,
            "summary": memory.summary,
        },
    }


@router.get("/postcards")
async def get_postcards(
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    result = await db.execute(
        select(Postcard)
        .where(Postcard.user_id == user.id)
        .order_by(Postcard.created_at.desc())
    )
    postcards = []
    for pc in result.scalars().all():
        image_url = image_storage.get_image_url(pc.image_card_key)
        image_thumb_url = image_storage.get_image_url(pc.image_thumb_key)
        image_original_url = image_storage.get_image_url(pc.image_original_key)
        postcards.append({
            "id": str(pc.id),
            "title": pc.title,
            "body": pc.body,
            "poem": pc.poem,
            "place": pc.place,
            "landmarkId": pc.landmark_id,
            "landmarkDescription": pc.landmark_description,
            "mood": pc.mood,
            "imageUrl": image_url,
            "imageThumbUrl": image_thumb_url,
            "imageOriginalUrl": image_original_url,
            "imagePrompt": pc.image_prompt,
            "searchImageUrls": pc.search_image_urls,
            "createdAt": pc.created_at.isoformat() if pc.created_at else "",
            "letterText": pc.letter_text,
            "tags": pc.tags,
        })
    return {"ok": True, "data": postcards}


@router.delete("/postcards/{postcard_id}")
async def delete_postcard(
    postcard_id: int,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """删除当前用户的明信片，并删除对应的本地或 OSS 图片对象。"""
    result = await db.execute(
        select(Postcard).where(Postcard.id == postcard_id, Postcard.user_id == user.id)
    )
    postcard = result.scalar_one_or_none()
    if postcard is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="明信片不存在")

    keys = {
        "thumb": postcard.image_thumb_key,
        "card": postcard.image_card_key,
        "original": postcard.image_original_key,
    }
    try:
        await image_storage.delete_image_variants(keys)
    except Exception as error:
        logger.exception("postcard image deletion failed postcard=%s user=%s", postcard_id, user.id)
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail="图片存储删除失败，明信片未删除",
        ) from error

    await db.execute(
        update(Mail)
        .where(Mail.attached_postcard_id == postcard.id)
        .values(attached_postcard_id=None)
    )
    await db.delete(postcard)
    db.add(SystemEvent(
        level="info",
        event_type="postcard_deleted",
        message="postcard and image objects deleted",
        user_id=user.id,
        event_metadata={"postcard_id": postcard_id, "object_keys": [key for key in keys.values() if key]},
    ))
    await db.flush()
    return {"ok": True, "data": {"id": str(postcard_id)}}


@router.get("/community-letters")
async def get_community_letters(
    limit: int = 5,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """获取其他用户的公开信件，供新用户作为写作灵感参考。

    前端通过 limit 参数控制获取数量。
    返回其他用户最近写过的信（含故乡省市信息），排除当前用户自己的信。
    """
    from sqlalchemy import func as sa_func

    # 先查当前用户的总信件数
    total_result = await db.execute(
        select(sa_func.count(Letter.id)).where(Letter.user_id == user.id)
    )
    my_count = total_result.scalar() or 0

    # 查其他用户的最近信件，联表 hometown 获取地理位置
    result = await db.execute(
        select(Letter, Hometown)
        .join(Hometown, Letter.user_id == Hometown.user_id, isouter=True)
        .where(Letter.user_id != user.id)
        .order_by(Letter.timestamp.desc())
        .limit(max(1, min(limit, 20)))
    )
    rows = result.all()

    letters = []
    for lt, ht in rows:
        letters.append({
            "id": f"ltr-{lt.id}",
            "text": lt.text,
            "place": lt.place or "",
            "mood": lt.mood or "",
            "timestamp": lt.timestamp.isoformat() if lt.timestamp else "",
            "hometown": {
                "province": ht.province if ht else "",
                "city": ht.city if ht else "",
                "hometownName": ht.hometown_name if ht else "",
            } if ht else None,
        })

    return {
        "ok": True,
        "data": {
            "letters": letters,
            "myLetterCount": my_count,
        },
    }


# ──────────── 辅助函数 ────────────

def _build_postcard_dict(pc: Postcard) -> dict:
    """将 Postcard ORM 对象转换为前端使用的字典格式"""
    image_url = image_storage.get_image_url(pc.image_card_key)
    image_thumb_url = image_storage.get_image_url(pc.image_thumb_key)
    image_original_url = image_storage.get_image_url(pc.image_original_key)
    return {
        "id": str(pc.id),
        "title": pc.title,
        "body": pc.body,
        "poem": pc.poem,
        "place": pc.place,
        "landmarkId": pc.landmark_id,
        "landmarkDescription": pc.landmark_description,
        "mood": pc.mood,
        "imageUrl": image_url,
        "imageThumbUrl": image_thumb_url,
        "imageOriginalUrl": image_original_url,
        "imagePrompt": pc.image_prompt,
        "searchImageUrls": pc.search_image_urls,
        "createdAt": pc.created_at.isoformat() if pc.created_at else "",
        "letterText": pc.letter_text,
        "tags": pc.tags,
    }


def _build_letter_dict(lt: Letter) -> dict:
    """将 Letter ORM 对象转换为前端使用的字典格式"""
    return {
        "id": f"ltr-{lt.id}",
        "text": lt.text,
        "place": lt.place,
        "mood": lt.mood,
        "timestamp": lt.timestamp.isoformat() if lt.timestamp else "",
    }


def _build_mail_dict(mail: Mail) -> dict:
    """将 Mail ORM 对象转换为前端使用的字典格式"""
    result = {
        "id": str(mail.id),
        "senderId": mail.sender_id,
        "senderUsername": mail.sender.username if mail.sender else "",
        "recipientId": mail.recipient_id,
        "recipientUsername": mail.recipient.username if mail.recipient else "",
        "title": mail.title,
        "content": mail.content,
        "isRead": mail.is_read,
        "sentAt": mail.sent_at.isoformat() if mail.sent_at else "",
    }
    if mail.attached_postcard:
        result["attachedPostcard"] = _build_postcard_dict(mail.attached_postcard)
    else:
        result["attachedPostcard"] = None
    if mail.attached_letter:
        result["attachedLetter"] = _build_letter_dict(mail.attached_letter)
    else:
        result["attachedLetter"] = None
    return result


# ──────────── 邮件端点 ────────────

@router.post("/mail/send")
async def send_mail(
    body: MailSendReq,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """向其他用户邮寄信件，可附带明信片或历史信件"""
    # 查找收件人
    result = await db.execute(
        select(User).where(User.username == body.recipient_username)
    )
    recipient = result.scalar_one_or_none()
    if recipient is None:
        return {"ok": False, "error": "收件人不存在"}

    # 不能给自己发信
    if recipient.id == user.id:
        return {"ok": False, "error": "不能给自己寄信"}

    # 附带资源归属校验
    if body.attached_postcard_id is not None:
        pc_result = await db.execute(
            select(Postcard).where(
                Postcard.id == body.attached_postcard_id,
                Postcard.user_id == user.id,
            )
        )
        if pc_result.scalar_one_or_none() is None:
            return {"ok": False, "error": "附带明信片不存在或不属于你"}

    if body.attached_letter_id is not None:
        lt_result = await db.execute(
            select(Letter).where(
                Letter.id == body.attached_letter_id,
                Letter.user_id == user.id,
            )
        )
        if lt_result.scalar_one_or_none() is None:
            return {"ok": False, "error": "附带信件不存在或不属于你"}

    mail = Mail(
        sender_id=user.id,
        recipient_id=recipient.id,
        title=body.title,
        content=body.content,
        attached_postcard_id=body.attached_postcard_id,
        attached_letter_id=body.attached_letter_id,
    )
    db.add(mail)
    await db.flush()

    return {
        "ok": True,
        "data": {
            "id": str(mail.id),
            "sentAt": mail.sent_at.isoformat() if mail.sent_at else "",
        },
    }


@router.get("/mail/inbox")
async def get_inbox(
    page: int = 1,
    page_size: int = 20,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """获取收件箱 — 收到的信件列表"""
    page = max(1, page)
    page_size = max(1, min(page_size, 50))

    # 未读数
    from sqlalchemy import func as sa_func
    unread_result = await db.execute(
        select(sa_func.count(Mail.id)).where(
            Mail.recipient_id == user.id,
            Mail.is_read == False,
            Mail.recipient_deleted == False,
        )
    )
    unread_count = unread_result.scalar() or 0

    # 收件列表
    offset = (page - 1) * page_size
    result = await db.execute(
        select(Mail)
        .options(
            selectinload(Mail.sender),
            selectinload(Mail.recipient),
            selectinload(Mail.attached_postcard),
            selectinload(Mail.attached_letter),
        )
        .where(Mail.recipient_id == user.id, Mail.recipient_deleted == False)
        .order_by(Mail.sent_at.desc())
        .offset(offset)
        .limit(page_size)
    )
    mails = [_build_mail_dict(m) for m in result.scalars().all()]

    # 总数
    total_result = await db.execute(
        select(sa_func.count(Mail.id)).where(
            Mail.recipient_id == user.id,
            Mail.recipient_deleted == False,
        )
    )
    total = total_result.scalar() or 0

    return {
        "ok": True,
        "data": {
            "mails": mails,
            "unreadCount": unread_count,
            "total": total,
            "page": page,
            "pageSize": page_size,
        },
    }


@router.get("/mail/outbox")
async def get_outbox(
    page: int = 1,
    page_size: int = 20,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """获取发件箱 — 发出的信件列表"""
    page = max(1, page)
    page_size = max(1, min(page_size, 50))

    offset = (page - 1) * page_size
    result = await db.execute(
        select(Mail)
        .options(
            selectinload(Mail.sender),
            selectinload(Mail.recipient),
            selectinload(Mail.attached_postcard),
            selectinload(Mail.attached_letter),
        )
        .where(Mail.sender_id == user.id, Mail.sender_deleted == False)
        .order_by(Mail.sent_at.desc())
        .offset(offset)
        .limit(page_size)
    )
    mails = [_build_mail_dict(m) for m in result.scalars().all()]

    from sqlalchemy import func as sa_func
    total_result = await db.execute(
        select(sa_func.count(Mail.id)).where(
            Mail.sender_id == user.id,
            Mail.sender_deleted == False,
        )
    )
    total = total_result.scalar() or 0

    return {
        "ok": True,
        "data": {
            "mails": mails,
            "total": total,
            "page": page,
            "pageSize": page_size,
        },
    }


@router.get("/mail/{mail_id}")
async def get_mail_detail(
    mail_id: int,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """获取单封信件的详情"""
    result = await db.execute(
        select(Mail)
        .options(
            selectinload(Mail.sender),
            selectinload(Mail.recipient),
            selectinload(Mail.attached_postcard),
            selectinload(Mail.attached_letter),
        )
        .where(Mail.id == mail_id)
    )
    mail = result.scalar_one_or_none()
    if mail is None:
        return {"ok": False, "error": "信件不存在"}

    # 只有发件人或收件人能查看
    if mail.sender_id != user.id and mail.recipient_id != user.id:
        return {"ok": False, "error": "无权查看此信件"}

    return {"ok": True, "data": _build_mail_dict(mail)}


@router.put("/mail/{mail_id}/read")
async def mark_mail_read(
    mail_id: int,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """将信件标记为已读"""
    result = await db.execute(
        select(Mail).where(Mail.id == mail_id)
    )
    mail = result.scalar_one_or_none()
    if mail is None:
        return {"ok": False, "error": "信件不存在"}

    # 只有收件人可以标记已读
    if mail.recipient_id != user.id:
        return {"ok": False, "error": "只有收件人可以标记已读"}

    mail.is_read = True
    await db.flush()

    return {"ok": True, "data": {"id": str(mail.id), "isRead": True}}


@router.delete("/mail/{mail_id}")
async def delete_mail(
    mail_id: int,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """删除信件（软删除）"""
    result = await db.execute(
        select(Mail).where(Mail.id == mail_id)
    )
    mail = result.scalar_one_or_none()
    if mail is None:
        return {"ok": False, "error": "信件不存在"}

    # 只有发件人或收件人可以删除
    if mail.sender_id != user.id and mail.recipient_id != user.id:
        return {"ok": False, "error": "无权删除此信件"}

    if mail.sender_id == user.id:
        mail.sender_deleted = True
    if mail.recipient_id == user.id:
        mail.recipient_deleted = True

    await db.flush()

    return {"ok": True, "data": {"id": str(mail.id)}}


@router.get("/users/lookup")
async def lookup_users(
    q: str = "",
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """按用户名搜索其他用户（用于选择收件人）"""
    if not q or len(q.strip()) < 1:
        return {"ok": True, "data": {"users": []}}

    result = await db.execute(
        select(User)
        .where(
            User.username.contains(q.strip()),
            User.id != user.id,
        )
        .limit(20)
    )
    users = [
        {"id": u.id, "username": u.username}
        for u in result.scalars().all()
    ]

    return {"ok": True, "data": {"users": users}}


# ──────────── 社区发现 ────────────

@router.get("/community/feed")
async def get_community_feed(
    limit: int = 10,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """随机获取其他用户的信件（含明信片），用于社区发现"""
    from sqlalchemy import func as sa_func

    result = await db.execute(
        select(Letter, Postcard, User)
        .outerjoin(
            Postcard,
            and_(
                Postcard.user_id == Letter.user_id,
                Postcard.letter_text == Letter.text,
            ),
        )
        .join(User, Letter.user_id == User.id)
        .where(Letter.user_id != user.id)
        .order_by(sa_func.random())
        .limit(max(1, min(limit, 30)))
    )
    rows = result.all()

    liked_result = await db.execute(
        select(LetterLike.letter_id).where(LetterLike.user_id == user.id)
    )
    liked_ids = set(r[0] for r in liked_result.all())

    items = []
    for lt, pc, u in rows:
        hometown_name = ""
        h_result = await db.execute(
            select(Hometown).where(Hometown.user_id == u.id)
        )
        ht = h_result.scalar_one_or_none()
        if ht:
            hometown_name = ht.hometown_name or ht.city or ""

        item = {
            "id": f"ltr-{lt.id}",
            "text": lt.text,
            "place": lt.place or "",
            "mood": lt.mood or "",
            "timestamp": lt.timestamp.isoformat() if lt.timestamp else "",
            "author": {"username": u.username, "hometown": hometown_name},
            "liked": lt.id in liked_ids,
        }
        if pc:
            item["postcard"] = _build_postcard_dict(pc)
        items.append(item)

    return {"ok": True, "data": {"items": items}}


@router.post("/community/like/{letter_id}")
async def like_community_letter(
    letter_id: int,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """点赞一封社区信件，收藏到桌面"""
    result = await db.execute(
        select(Letter).where(Letter.id == letter_id, Letter.user_id != user.id)
    )
    letter = result.scalar_one_or_none()
    if letter is None:
        return {"ok": False, "error": "信件不存在"}

    exist = await db.execute(
        select(LetterLike).where(
            LetterLike.user_id == user.id, LetterLike.letter_id == letter_id
        )
    )
    if exist.scalar_one_or_none():
        return {"ok": True, "data": {"liked": True}}

    db.add(LetterLike(user_id=user.id, letter_id=letter_id))
    await db.flush()
    return {"ok": True, "data": {"liked": True}}


@router.delete("/community/like/{letter_id}")
async def unlike_community_letter(
    letter_id: int,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """取消点赞"""
    result = await db.execute(
        select(LetterLike).where(
            LetterLike.user_id == user.id, LetterLike.letter_id == letter_id
        )
    )
    existing = result.scalar_one_or_none()
    if existing:
        await db.delete(existing)
        await db.flush()
    return {"ok": True, "data": {"liked": False}}
