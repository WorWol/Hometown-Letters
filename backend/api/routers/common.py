"""业务 API 共用请求模型、依赖和序列化。"""
from __future__ import annotations

from fastapi import Request

import storage
from db.models import Letter, Mail, Postcard


def get_llm(request: Request):
    return request.app.state.llm


def get_pipeline(request: Request):
    return request.app.state.pipeline


def postcard_dict(postcard: Postcard) -> dict:
    return {
        "id": str(postcard.id),
        "title": postcard.title,
        "body": postcard.body,
        "poem": postcard.poem,
        "place": postcard.place,
        "generationPlace": postcard.generation_place,
        "mood": postcard.mood,
        "imageUrl": storage.image_url(postcard.image_card_key),
        "imageThumbUrl": storage.image_url(postcard.image_thumb_key),
        "imageOriginalUrl": storage.image_url(postcard.image_original_key),
        "referenceImageUrl": storage.image_url(postcard.reference_image_key),
        "imagePrompt": postcard.image_prompt,
        "searchImageUrls": postcard.search_image_urls,
        "createdAt": postcard.created_at.isoformat() if postcard.created_at else "",
        "letterText": postcard.letter_text,
        "tags": postcard.tags,
    }


def letter_dict(letter: Letter) -> dict:
    return {
        "id": f"ltr-{letter.id}",
        "text": letter.text,
        "place": letter.place,
        "mood": letter.mood,
        "timestamp": letter.timestamp.isoformat() if letter.timestamp else "",
    }


def mail_dict(mail: Mail) -> dict:
    return {
        "id": str(mail.id),
        "senderId": mail.sender_id,
        "senderUsername": mail.sender.username if mail.sender else "",
        "recipientId": mail.recipient_id,
        "recipientUsername": mail.recipient.username if mail.recipient else "",
        "title": mail.title,
        "content": mail.content,
        "isRead": mail.is_read,
        "sentAt": mail.sent_at.isoformat() if mail.sent_at else "",
        "attachedPostcard": postcard_dict(mail.attached_postcard) if mail.attached_postcard else None,
        "attachedLetter": letter_dict(mail.attached_letter) if mail.attached_letter else None,
    }
