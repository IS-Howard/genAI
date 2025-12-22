"""
Line Bot Main Application
FastAPI server with webhook handling
"""
import subprocess
from contextlib import asynccontextmanager
from fastapi import FastAPI, Request, HTTPException
from linebot.v3 import WebhookHandler
from linebot.v3.exceptions import InvalidSignatureError
from linebot.v3.webhooks import MessageEvent, TextMessageContent, ImageMessageContent, AudioMessageContent, JoinEvent
from linebot.v3.messaging import ApiClient, MessagingApi, Configuration, ReplyMessageRequest, TextMessage
from loguru import logger
from typing import Optional
import sys

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


# FastAPI app with lifespan
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
        elif text.startswith('看圖片') or text.startswith('聽音檔'):
            return {
                'route': 'ignore',
                'text': text,
                'original_text': text
            }
        # Normal 1-on-1 chat
        elif source_type == 'user':
            return {
                'route': 'normal',
                'text': text,
                'original_text': text
            }
        # Group chat with mention
        elif source_type in ['group', 'room'] and 'HOWN' in text.upper():
            return {
                'route': 'group',
                'text': text.replace('@HOWN_BOT', '').strip(),
                'original_text': text
            }
        else:
            if source_type in ['group', 'room']:
                logger.info(f"Ignored group/room message (no mention): {text[:20]}")
            else:
                logger.info(f"Ignored message from {source_type}")
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
                history = await db.get_group_history(group_id)
            else:
                history = await db.get_user_history(user_id)

            response_text = None

            # Route to appropriate handler
            if routing['route'] == 'normal':
                response_text = await ai_service.normal_chat(routing['text'], user_name, history)

            elif routing['route'] == 'group':
                response_text = await ai_service.group_chat(routing['text'], user_name, history)

            elif routing['route'] == 'train':
                response_text = await MessageRouter.book_train(routing['text'])

            # Save to database
            if response_text:
                await db.save_message(
                    user_id=user_id,
                    user_name=user_name,
                    user_message=text,
                    bot_message=response_text,
                    group_id=group_id
                )

                # Send reply
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
        """Handle image message"""
        try:
            # Get image data
            image_data = await line_service.get_message_content(message_id)
            if not image_data:
                await line_service.reply_message(reply_token, "無法取得圖片")
                return

            # Get last message for context
            if group_id:
                history = await db.get_group_history(group_id, limit=1)
            else:
                history = await db.get_user_history(user_id, limit=1)

            prompt = "請描述這張圖片"
            if history and history[-1].get('user_message'):
                last_msg = history[-1]['user_message']
                if last_msg.startswith('看圖片'):
                    prompt = last_msg.replace('看圖片', '').strip() or prompt

            # Analyze image
            response_text = await ai_service.analyze_image(image_data, prompt)

            # Save and reply
            await db.save_message(
                user_id=user_id,
                user_name=user_name,
                user_message="[圖片]",
                bot_message=response_text,
                group_id=group_id
            )

            await line_service.reply_message(reply_token, response_text)

        except Exception as e:
            logger.error(f"Error handling image: {e}")
            await line_service.reply_message(reply_token, "圖片處理失敗")

    @staticmethod
    async def handle_audio_message(
        message_id: str,
        user_id: str,
        user_name: str,
        reply_token: str,
        group_id: Optional[str] = None
    ):
        """Handle audio message"""
        try:
            # Get audio data
            audio_data = await line_service.get_message_content(message_id)
            if not audio_data:
                await line_service.reply_message(reply_token, "無法取得音檔")
                return

            # Get last message for context
            if group_id:
                history = await db.get_group_history(group_id, limit=1)
            else:
                history = await db.get_user_history(user_id, limit=1)

            # Get prompt from last message if available
            prompt = "請分析這段音檔"
            if history and history[-1].get('user_message'):
                last_msg = history[-1]['user_message']
                if last_msg.startswith('聽音檔'):
                    prompt = last_msg.replace('聽音檔', '').strip() or prompt

            # Process audio
            response_text = await ai_service.analyze_audio(audio_data, prompt)

            # Save and reply
            await db.save_message(
                user_id=user_id,
                user_name=user_name,
                user_message="[音檔]",
                bot_message=response_text,
                group_id=group_id
            )

            await line_service.reply_message(reply_token, response_text)

        except Exception as e:
            logger.error(f"Error handling audio: {e}")
            await line_service.reply_message(reply_token, "音檔處理失敗")

    @staticmethod
    async def book_train(params: str) -> str:
        """
        Book train using Docker command
        """
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


# Startup and shutdown now handled by lifespan context manager above


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

    try:
        # Verify signature
        handler.handle(body_str, signature)
    except InvalidSignatureError:
        logger.error("Invalid signature")
        raise HTTPException(status_code=400, detail="Invalid signature")

    return "OK"


@handler.add(MessageEvent, message=TextMessageContent)
def handle_text(event):
    """Handle text message event"""
    import asyncio

    user_id = event.source.user_id
    text = event.message.text
    reply_token = event.reply_token

    # Get source type and group_id
    source_type = event.source.type
    group_id = getattr(event.source, 'group_id', None)
    if not group_id:
        group_id = getattr(event.source, 'room_id', None)

    logger.debug(f"Event: {event.type} | Source: {source_type} | Group/Room ID: {group_id}")

    # Get or create user name
    async def process():
        try:
            user_mapping = await db.get_user_mapping(user_id)

            if not user_mapping:
                # Fetch from Line API
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
            logger.error(f"Error in background process: {e}")

    asyncio.create_task(process())


@handler.add(MessageEvent, message=ImageMessageContent)
def handle_image(event):
    """Handle image message event"""
    import asyncio

    user_id = event.source.user_id
    message_id = event.message.id
    reply_token = event.reply_token
    group_id = getattr(event.source, 'group_id', None)

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
    import asyncio

    user_id = event.source.user_id
    message_id = event.message.id
    reply_token = event.reply_token
    group_id = getattr(event.source, 'group_id', None)

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


@handler.add(JoinEvent)
def handle_join(event):
    """Handle bot join group event"""
    import asyncio

    reply_token = event.reply_token

    async def process():
        await line_service.reply_message(
            reply_token,
            "哈囉，加我好友可以直接聊天，如果是在群組裡要@HOWN_BOT我才會回應喔。"
        )

    asyncio.create_task(process())


if __name__ == "__main__":
    import uvicorn

    uvicorn.run(
        "main:app",
        host="0.0.0.0",
        port=settings.port,
        reload=settings.debug
    )
