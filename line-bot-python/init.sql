-- Database initialization script
-- Run automatically when PostgreSQL container starts

-- Create user_mapping table
CREATE TABLE IF NOT EXISTS user_mapping (
    user_id VARCHAR(100) PRIMARY KEY,
    user_name VARCHAR(255) NOT NULL,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

-- Create chat_history table
CREATE TABLE IF NOT EXISTS chat_history (
    id SERIAL PRIMARY KEY,
    user_id VARCHAR(100) NOT NULL,
    user_name VARCHAR(255) NOT NULL,
    user_message TEXT NOT NULL,
    bot_message TEXT,
    group_id VARCHAR(100),
    timestamp TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

-- Create optimized indexes
-- For user chat history lookup (1-on-1)
CREATE INDEX IF NOT EXISTS idx_chat_history_user_timestamp
ON chat_history(user_id, timestamp DESC)
WHERE group_id IS NULL;

-- For group chat history lookup
CREATE INDEX IF NOT EXISTS idx_chat_history_group_timestamp
ON chat_history(group_id, timestamp DESC)
WHERE group_id IS NOT NULL;

-- For user mapping lookup
CREATE INDEX IF NOT EXISTS idx_user_mapping_user_id
ON user_mapping(user_id);

-- Create function to update updated_at timestamp
CREATE OR REPLACE FUNCTION update_updated_at_column()
RETURNS TRIGGER AS $$
BEGIN
    NEW.updated_at = CURRENT_TIMESTAMP;
    RETURN NEW;
END;
$$ language 'plpgsql';

-- Create trigger for user_mapping
CREATE TRIGGER update_user_mapping_updated_at
BEFORE UPDATE ON user_mapping
FOR EACH ROW
EXECUTE FUNCTION update_updated_at_column();


-- Create stored_files table for file management (GROUP ONLY)
CREATE TABLE IF NOT EXISTS stored_files (
    id SERIAL PRIMARY KEY,
    group_id VARCHAR(100) NOT NULL, -- Mandatory now as per group-only constraint
    user_id VARCHAR(100) NOT NULL,  -- Uploader
    file_type VARCHAR(20) NOT NULL,  -- 'image', 'audio'
    mime_type VARCHAR(50) NOT NULL,  -- 'image/jpeg', 'audio/mpeg', etc.
    file_data BYTEA NOT NULL,        -- Binary file content
    file_size_bytes INTEGER NOT NULL,
    original_message_id VARCHAR(100),
    uploaded_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

-- Index for fast group file lookup (ordered by upload time)
CREATE INDEX IF NOT EXISTS idx_stored_files_group
ON stored_files(group_id, uploaded_at DESC);

-- Grant permissions (if using specific user)
-- GRANT ALL PRIVILEGES ON ALL TABLES IN SCHEMA public TO line_bot_user;
-- GRANT USAGE, SELECT ON ALL SEQUENCES IN SCHEMA public TO line_bot_user;
