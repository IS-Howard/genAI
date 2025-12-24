"""
Database operations for Line Bot
Optimized queries with proper indexes and limits
"""
import asyncpg
from typing import List, Dict, Optional
from loguru import logger
from config import settings


class Database:
    """Database connection and operations"""

    def __init__(self):
        self.pool: Optional[asyncpg.Pool] = None

    async def connect(self):
        """Create database connection pool"""
        try:
            self.pool = await asyncpg.create_pool(
                settings.db_url,
                min_size=2,
                max_size=10,
                command_timeout=30
            )
            logger.info("Database connected successfully")
        except Exception as e:
            logger.error(f"Database connection failed: {e}")
            raise

    async def close(self):
        """Close database connection pool"""
        if self.pool:
            await self.pool.close()
            logger.info("Database connection closed")

    async def get_user_mapping(self, user_id: str) -> Optional[Dict]:
        """Get user name from mapping table"""
        async with self.pool.acquire() as conn:
            row = await conn.fetchrow(
                "SELECT user_id, user_name FROM user_mapping WHERE user_id = $1",
                user_id
            )
            return dict(row) if row else None

    async def save_user_mapping(self, user_id: str, user_name: str) -> bool:
        """Save user mapping (insert or update)"""
        try:
            async with self.pool.acquire() as conn:
                await conn.execute(
                    """
                    INSERT INTO user_mapping (user_id, user_name)
                    VALUES ($1, $2)
                    ON CONFLICT (user_id) DO UPDATE SET user_name = $2
                    """,
                    user_id, user_name
                )
            return True
        except Exception as e:
            logger.error(f"Failed to save user mapping: {e}")
            return False

    async def get_user_history(self, user_id: str, limit: int = None) -> List[Dict]:
        """
        Get user chat history (optimized query)
        Only returns necessary columns with limit
        """
        limit = limit or settings.max_history_items
        async with self.pool.acquire() as conn:
            rows = await conn.fetch(
                """
                SELECT user_id, user_name, user_message, bot_message, timestamp, id
                FROM chat_history
                WHERE user_id = $1 AND group_id IS NULL
                ORDER BY timestamp DESC
                LIMIT $2
                """,
                user_id, limit
            )
            # Reverse to get chronological order (oldest first)
            return [dict(row) for row in reversed(rows)]

    async def get_group_history(self, group_id: str, limit: int = None) -> List[Dict]:
        """
        Get group chat history (optimized query)
        """
        limit = limit or settings.max_history_items
        async with self.pool.acquire() as conn:
            rows = await conn.fetch(
                """
                SELECT user_id, user_name, user_message, bot_message, timestamp, id
                FROM chat_history
                WHERE group_id = $1
                ORDER BY timestamp DESC
                LIMIT $2
                """,
                group_id, limit
            )
            return [dict(row) for row in reversed(rows)]

    async def save_message(
        self,
        user_id: str,
        user_name: str,
        user_message: str,
        bot_message: str = "",
        group_id: Optional[str] = None
    ) -> Optional[int]:
        """Save chat message to history"""
        try:
            async with self.pool.acquire() as conn:
                row = await conn.fetchrow(
                    """
                    INSERT INTO chat_history
                    (user_id, user_name, user_message, bot_message, group_id)
                    VALUES ($1, $2, $3, $4, $5)
                    RETURNING id
                    """,
                    user_id, user_name, user_message, bot_message, group_id
                )
                return row['id']
        except Exception as e:
            logger.error(f"Failed to save message: {e}")
            return None

    async def update_bot_message(self, message_id: int, bot_message: str) -> bool:
        """Update bot message in existing history record"""
        try:
            async with self.pool.acquire() as conn:
                await conn.execute(
                    "UPDATE chat_history SET bot_message = $1 WHERE id = $2",
                    bot_message, message_id
                )
            return True
        except Exception as e:
            logger.error(f"Failed to update bot message: {e}")
            return False


    async def save_file(
        self,
        group_id: str,
        user_id: str,
        file_type: str,
        mime_type: str,
        file_data: bytes,
        message_id: Optional[str] = None
    ) -> Optional[int]:
        """Save file with FIFO cleanup (GROUP ONLY)"""
        try:
            file_size = len(file_data)
            async with self.pool.acquire() as conn:
                row = await conn.fetchrow(
                    """
                    INSERT INTO stored_files
                    (group_id, user_id, file_type, mime_type, file_data, file_size_bytes, original_message_id)
                    VALUES ($1, $2, $3, $4, $5, $6, $7)
                    RETURNING id
                    """,
                    group_id, user_id, file_type, mime_type, file_data, file_size, message_id
                )
                
                # FIFO cleanup based on global config
                await conn.execute(
                    "DELETE FROM stored_files WHERE id IN (SELECT id FROM stored_files WHERE group_id = $1 ORDER BY uploaded_at DESC OFFSET $2)",
                    group_id, settings.max_files_per_group
                )
                return row['id'] if row else None
        except Exception as e:
            logger.error(f"Failed to save group file: {e}")
            return None

    async def get_latest_group_file(self, group_id: str, file_type: Optional[str] = None) -> Optional[Dict]:
        """Get latest file for a group"""
        async with self.pool.acquire() as conn:
            if file_type:
                row = await conn.fetchrow(
                    "SELECT id, file_type, mime_type, file_data, file_size_bytes, uploaded_at FROM stored_files WHERE group_id = $1 AND file_type = $2 ORDER BY uploaded_at DESC LIMIT 1",
                    group_id, file_type
                )
            else:
                row = await conn.fetchrow(
                    "SELECT id, file_type, mime_type, file_data, file_size_bytes, uploaded_at FROM stored_files WHERE group_id = $1 ORDER BY uploaded_at DESC LIMIT 1",
                    group_id
                )
            return dict(row) if row else None


# Global database instance
db = Database()
