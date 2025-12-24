"""
Line API Service
Handles Line Bot API interactions
"""
import httpx
from typing import Optional, Dict
from loguru import logger
from config import settings


class LineService:
    """Line Bot API client"""

    def __init__(self):
        self.base_url = "https://api.line.me/v2/bot"
        self.headers = {
            "Authorization": f"Bearer {settings.line_channel_access_token}",
            "Content-Type": "application/json"
        }

    async def reply_message(self, reply_token: str, text: str) -> bool:
        """
        Send reply message via Line API
        """
        url = f"{self.base_url}/message/reply"
        payload = {
            "replyToken": reply_token,
            "messages": [
                {
                    "type": "text",
                    "text": text
                }
            ]
        }

        try:
            async with httpx.AsyncClient() as client:
                response = await client.post(
                    url,
                    json=payload,
                    headers=self.headers,
                    timeout=10.0
                )
                response.raise_for_status()
                logger.info(f"Reply sent successfully")
                return True
        except Exception as e:
            logger.error(f"Failed to send reply: {e}")
            return False

    async def get_user_profile(self, user_id: str, group_id: Optional[str] = None, source_type: str = 'user') -> Optional[dict]:
        """
        Get user profile from Line API
        Adjusts endpoint based on source type (group/room member vs direct user)
        """
        if source_type == 'group' and group_id:
            url = f"{self.base_url}/group/{group_id}/member/{user_id}"
        elif source_type == 'room' and group_id:
            url = f"{self.base_url}/room/{group_id}/member/{user_id}"
        else:
            url = f"{self.base_url}/profile/{user_id}"

        try:
            async with httpx.AsyncClient() as client:
                response = await client.get(
                    url,
                    headers=self.headers,
                    timeout=10.0
                )
                if response.status_code == 200:
                    data = response.json()
                    return {
                        'displayName': data.get('displayName', '使用者'),
                        'pictureUrl': data.get('pictureUrl'),
                        'statusMessage': data.get('statusMessage')
                    }
                return None
        except Exception as e:
            logger.error(f"Failed to get user profile: {e}")
            return None


    async def get_message_content(self, message_id: str) -> Optional[bytes]:
        """
        Get message content (for images, audio, etc.)
        """
        url = f"https://api-data.line.me/v2/bot/message/{message_id}/content"

        try:
            async with httpx.AsyncClient() as client:
                response = await client.get(
                    url,
                    headers=self.headers,
                    timeout=30.0
                )
                response.raise_for_status()
                return response.content
        except Exception as e:
            logger.error(f"Failed to get message content: {e}")
            return None


# Global Line service instance
line_service = LineService()
