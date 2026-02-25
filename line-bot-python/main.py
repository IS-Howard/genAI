"""
Line Bot Main Application
FastAPI server with webhook handling
"""
import sys
import asyncio
import subprocess
from contextlib import asynccontextmanager
from typing import Optional
from collections import deque

from fastapi import FastAPI, Request, HTTPException
from linebot.v3 import WebhookHandler
from linebot.v3.exceptions import InvalidSignatureError
from linebot.v3.messaging import Configuration
from linebot.v3.webhooks import (
    MessageEvent, TextMessageContent, ImageMessageContent,
    AudioMessageContent, JoinEvent, VideoMessageContent,
    FileMessageContent, LocationMessageContent, StickerMessageContent
)
from loguru import logger

from config import settings
from database import db
from ai_service import ai_service
from line_service import line_service


# Configure logging
logger.remove()
logger.add(
    sys.stdout,
    format="<green>{time:YYYY-MM-DD HH:mm:ss}</green> | <level>{level: <8}</level> | <cyan>{name}</cyan>:<cyan>{function}</cyan> - <level>{message}</level>",
    level=settings.log_level
)


# Deduplication: Track recent message IDs to prevent double processing
_processed_messages = deque(maxlen=100)

def is_duplicate(message_id: str) -> bool:
    """Check if message was already processed"""
    if not message_id:
        return False
    if message_id in _processed_messages:
        return True
    _processed_messages.append(message_id)
    return False


# Line Bot SDK v3
configuration = Configuration(access_token=settings.line_channel_access_token)
handler = WebhookHandler(settings.line_channel_secret)


# Lifespan context manager for startup/shutdown
@asynccontextmanager
async def lifespan(app: FastAPI):
    """Initialize services on startup and cleanup on shutdown"""
    logger.info("Starting Line Bot...")
    await db.connect()
    logger.info("Line Bot ready!")
    yield
    logger.info("Shutting down...")
    await db.close()


# FastAPI app
app = FastAPI(title="Line Bot", version="1.0.0", lifespan=lifespan)


class MessageRouter:
    """Routes messages to appropriate handlers"""

    @staticmethod
    def parse_message(text: str, user_id: str, source_type: str) -> dict:
        """
        Parse message and determine routing
        Returns: {route, text, original_text}
        """
        text = text.strip() if text else ""

        # Check for special commands
        if text.startswith('訂火車'):
            return {
                'route': 'train',
                'text': text.replace('訂火車', '').strip(),
                'original_text': text
            }

        # Normal 1-on-1 chat
        if source_type == 'user':
            return {
                'route': 'normal',
                'text': text,
                'original_text': text
            }

        # Group chat with mention
        if source_type in ['group', 'room'] and 'HOWN' in text.upper():
            return {
                'route': 'group',
                'text': text.replace('@HOWN_BOT', '').strip(),
                'original_text': text
            }

        # Ignore other messages
        if source_type in ['group', 'room']:
            logger.debug(f"Ignored group/room message (no mention): {text[:20]}")
        return {
            'route': 'ignore',
            'text': text,
            'original_text': text
        }

    @staticmethod
    async def handle_text_message(
        text: str,
        user_id: str,
        user_name: str,
        reply_token: str,
        source_type: str,
        group_id: Optional[str] = None
    ):
        """Handle incoming text message"""
        # Parse message to determine route
        routing = MessageRouter.parse_message(text, user_id, source_type)

        if routing['route'] == 'ignore':
            return

        logger.info(f"Routing: {routing['route']} | User: {user_name} | Text: {text[:50]}")

        try:
            # Get conversation history
            if group_id:
                history = await db.get_group_history(group_id, limit=settings.max_history_items)
            else:
                history = await db.get_user_history(user_id, limit=settings.max_history_items)

            response_text = None

            # Route to appropriate handler
            if routing['route'] == 'normal':
                response_text = await ai_service.normal_chat(routing['text'], user_name, history)

            elif routing['route'] == 'group':
                response_text = await ai_service.group_chat(routing['text'], user_name, group_id, history)

            elif routing['route'] == 'train':
                response_text = await MessageRouter.book_train(routing['text'])

            # Save to database and reply
            if response_text:
                await db.save_message(
                    user_id=user_id,
                    user_name=user_name,
                    user_message=text,
                    bot_message=response_text,
                    group_id=group_id
                )
                await line_service.reply_message(reply_token, response_text)

        except Exception as e:
            logger.error(f"Error handling message: {e}")
            await line_service.reply_message(reply_token, "抱歉，處理訊息時發生錯誤。")

    @staticmethod
    async def handle_image_message(
        message_id: str,
        user_id: str,
        user_name: str,
        reply_token: str,
        group_id: Optional[str] = None
    ):
        """Handle image message - SILENT SAVE (GROUP ONLY)"""
        await MessageRouter._save_attachment(message_id, user_id, 'image', 'image/jpeg', group_id)

    @staticmethod
    async def handle_audio_message(
        message_id: str,
        user_id: str,
        user_name: str,
        reply_token: str,
        group_id: Optional[str] = None
    ):
        """Handle audio message - SILENT SAVE (GROUP ONLY)"""
        await MessageRouter._save_attachment(message_id, user_id, 'audio', 'audio/mpeg', group_id)

    @staticmethod
    async def handle_video_message(
        message_id: str,
        user_id: str,
        user_name: str,
        reply_token: str,
        group_id: Optional[str] = None
    ):
        """Handle video message - SILENT SAVE (GROUP ONLY)"""
        await MessageRouter._save_attachment(message_id, user_id, 'video', 'video/mp4', group_id)

    @staticmethod
    async def handle_file_message(
        message_id: str,
        user_id: str,
        user_name: str,
        reply_token: str,
        file_name: str,
        file_size: int,
        group_id: Optional[str] = None
    ):
        """Handle file message - Detect type and SILENT SAVE (GROUP ONLY)"""
        if not group_id:
            return

        # Detect type from extension
        ext = file_name.split('.')[-1].lower() if '.' in file_name else ''
        file_type = 'file'
        mime_type = 'application/octet-stream'

        if ext in ['jpg', 'jpeg', 'png', 'gif']:
            file_type = 'image'
            mime_type = f'image/{ext if ext != "jpg" else "jpeg"}'
        elif ext in ['mp3', 'm4a', 'wav']:
            file_type = 'audio'
            mime_type = 'audio/mpeg' if ext != 'wav' else 'audio/wav'
        elif ext in ['mp4', 'mov', 'avi']:
            file_type = 'video'
            mime_type = 'video/mp4'

        await MessageRouter._save_attachment(message_id, user_id, file_type, mime_type, group_id)

    @staticmethod
    async def _save_attachment(message_id: str, user_id: str, file_type: str, mime_type: str, group_id: Optional[str]):
        """Helper to save media/file content to DB"""
        if not group_id:
            logger.debug(f"Ignoring {file_type} upload (not in a group)")
            return

        try:
            # Get data
            data = await line_service.get_message_content(message_id)
            if not data:
                return

            # Save to database
            await db.save_file(
                group_id=group_id,
                user_id=user_id,
                file_type=file_type,
                mime_type=mime_type,
                file_data=data,
                message_id=message_id
            )
            logger.info(f"{file_type.capitalize()} saved for group {group_id} by {user_id}")

        except Exception as e:
            logger.error(f"Error handling group {file_type}: {e}")

    @staticmethod
    async def book_train(params: str) -> str:
        """Book train using Docker command"""
        try:
            cmd = f"docker run --rm {settings.train_booker_image} {params}"
            result = subprocess.run(
                cmd,
                shell=True,
                capture_output=True,
                text=True,
                timeout=60
            )

            if result.returncode == 0:
                return "完成"
            else:
                return "失敗 (訂火車<身分證> <起站> <終站> <日期> <車次> <座位偏好(n/a/w)> <目標車廂>)"

        except subprocess.TimeoutExpired:
            return "訂票逾時"
        except Exception as e:
            logger.error(f"Train booking error: {e}")
            return "訂票失敗"


# ===== FastAPI Routes =====

@app.get("/")
async def root():
    """Health check endpoint"""
    return {"status": "ok", "service": "Line Bot"}


@app.post("/webhook")
async def webhook(request: Request):
    """
    Line webhook endpoint
    Receives events from Line platform
    """
    signature = request.headers.get("X-Line-Signature", "")
    body = await request.body()
    body_str = body.decode("utf-8")

    logger.debug(f"Received webhook: {body_str}")

    try:
        handler.handle(body_str, signature)
    except InvalidSignatureError:
        logger.error("Invalid signature")
        raise HTTPException(status_code=400, detail="Invalid signature")

    return "OK"


# ===== Line Bot Event Handlers =====

@handler.add(MessageEvent, message=TextMessageContent)
def handle_text(event):
    """Handle text message event"""
    message_id = event.message.id
    if is_duplicate(message_id):
        logger.warning(f"Duplicate TextMessage {message_id} ignored")
        return

    user_id = event.source.user_id
    text = event.message.text
    reply_token = event.reply_token
    source_type = event.source.type
    group_id = getattr(event.source, 'group_id', None) or getattr(event.source, 'room_id', None)

    logger.info(f"Received TextMessage: {text[:50]}... from {user_id} in {source_type} {group_id or ''}")

    async def process():
        try:
            # Get or create user mapping
            user_mapping = await db.get_user_mapping(user_id)

            if not user_mapping:
                profile = await line_service.get_user_profile(user_id, group_id, source_type)
                user_name = profile.get('displayName', user_id[-4:]) if profile else user_id[-4:]
                await db.save_user_mapping(user_id, user_name)
            else:
                user_name = user_mapping['user_name']

            # Handle message
            await MessageRouter.handle_text_message(
                text=text,
                user_id=user_id,
                user_name=user_name,
                reply_token=reply_token,
                source_type=source_type,
                group_id=group_id
            )
        except Exception as e:
            logger.error(f"Error in text handler: {e}")

    asyncio.create_task(process())


@handler.add(MessageEvent, message=ImageMessageContent)
def handle_image(event):
    """Handle image message event"""
    message_id = event.message.id
    if is_duplicate(message_id):
        logger.warning(f"Duplicate ImageMessage {message_id} ignored")
        return

    user_id = event.source.user_id
    reply_token = event.reply_token
    group_id = getattr(event.source, 'group_id', None)
    source_type = event.source.type

    logger.info(f"Received ImageMessage: {message_id} from {user_id} in {source_type} {group_id or ''}")

    async def process():
        user_mapping = await db.get_user_mapping(user_id)
        user_name = user_mapping['user_name'] if user_mapping else user_id[-4:]

        await MessageRouter.handle_image_message(
            message_id=message_id,
            user_id=user_id,
            user_name=user_name,
            reply_token=reply_token,
            group_id=group_id
        )

    asyncio.create_task(process())


@handler.add(MessageEvent, message=AudioMessageContent)
def handle_audio(event):
    """Handle audio message event"""
    message_id = event.message.id
    if is_duplicate(message_id):
        logger.warning(f"Duplicate AudioMessage {message_id} ignored")
        return

    user_id = event.source.user_id
    reply_token = event.reply_token
    group_id = getattr(event.source, 'group_id', None)
    source_type = event.source.type

    logger.info(f"Received AudioMessage: {message_id} from {user_id} in {source_type} {group_id or ''}")

    async def process():
        user_mapping = await db.get_user_mapping(user_id)
        user_name = user_mapping['user_name'] if user_mapping else user_id[-4:]

        await MessageRouter.handle_audio_message(
            message_id=message_id,
            user_id=user_id,
            user_name=user_name,
            reply_token=reply_token,
            group_id=group_id
        )

    asyncio.create_task(process())


@handler.add(MessageEvent, message=VideoMessageContent)
def handle_video(event):
    """Handle video message event"""
    message_id = event.message.id
    if is_duplicate(message_id):
        logger.warning(f"Duplicate VideoMessage {message_id} ignored")
        return

    user_id = event.source.user_id
    reply_token = event.reply_token
    group_id = getattr(event.source, 'group_id', None)
    source_type = event.source.type

    logger.info(f"Received VideoMessage: {message_id} from {user_id} in {source_type} {group_id or ''}")

    async def process():
        user_mapping = await db.get_user_mapping(user_id)
        user_name = user_mapping['user_name'] if user_mapping else user_id[-4:]

        await MessageRouter.handle_video_message(
            message_id=message_id,
            user_id=user_id,
            user_name=user_name,
            reply_token=reply_token,
            group_id=group_id
        )

    asyncio.create_task(process())


@handler.add(MessageEvent, message=FileMessageContent)
def handle_file(event):
    """Handle file message event"""
    message_id = event.message.id
    if is_duplicate(message_id):
        logger.warning(f"Duplicate FileMessage {message_id} ignored")
        return

    user_id = event.source.user_id
    reply_token = event.reply_token
    group_id = getattr(event.source, 'group_id', None)
    source_type = event.source.type
    file_name = event.message.file_name
    file_size = event.message.file_size

    logger.info(f"Received FileMessage: {file_name} ({file_size} bytes) from {user_id} in {source_type} {group_id or ''}")

    async def process():
        user_mapping = await db.get_user_mapping(user_id)
        user_name = user_mapping['user_name'] if user_mapping else user_id[-4:]

        await MessageRouter.handle_file_message(
            message_id=message_id,
            user_id=user_id,
            user_name=user_name,
            reply_token=reply_token,
            file_name=file_name,
            file_size=file_size,
            group_id=group_id
        )

    asyncio.create_task(process())


@handler.add(MessageEvent, message=StickerMessageContent)
def handle_sticker(event):
    """Handle sticker message event"""
    message_id = event.message.id
    if is_duplicate(message_id): return

    user_id = event.source.user_id
    source_type = event.source.type
    group_id = getattr(event.source, 'group_id', None)
    package_id = event.message.package_id
    sticker_id = event.message.sticker_id

    logger.info(f"Received StickerMessage: Package={package_id} Sticker={sticker_id} from {user_id} in {source_type} {group_id or ''}")


@handler.add(MessageEvent, message=LocationMessageContent)
def handle_location(event):
    """Handle location message event"""
    message_id = event.message.id
    if is_duplicate(message_id): return

    user_id = event.source.user_id
    source_type = event.source.type
    group_id = getattr(event.source, 'group_id', None)
    title = event.message.title
    address = event.message.address

    logger.info(f"Received LocationMessage: {title} ({address}) from {user_id} in {source_type} {group_id or ''}")


@handler.add(MessageEvent)
def handle_message(event):
    """Generic fallback for unhandled message types"""
    message_id = getattr(event.message, 'id', 'N/A')
    message_type = event.message.type
    user_id = event.source.user_id
    source_type = event.source.type
    group_id = getattr(event.source, 'group_id', None)

    logger.info(f"Received {message_type} (unhandled): {message_id} from {user_id} in {source_type} {group_id or ''}")


@handler.add(JoinEvent)
def handle_join(event):
    """Handle bot join group event"""
    reply_token = event.reply_token

    async def process():
        await line_service.reply_message(
            reply_token,
            "哈囉，加我好友可以直接聊天，如果是在群組裡要@HOWN_BOT我才會回應喔。"
        )

    asyncio.create_task(process())


# ===== Application Entry Point =====

if __name__ == "__main__":
    import uvicorn

    uvicorn.run(
        app,
        host="0.0.0.0",
        port=settings.port,
        log_config=None  # Use Loguru instead
    )
