CREATE SCHEMA IF NOT EXISTS public;

-- -- Extension uuid-ossp to generate UUID
-- CREATE EXTENSION IF NOT EXISTS "uuid-ossp";

-- -- Drop tables if exists
-- DROP TABLE IF EXISTS youtube_videos CASCADE;

-- -- Create table youtube_videos
-- CREATE TABLE youtube_videos (
--     id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
--     video_id VARCHAR(255) NOT NULL,
--     url VARCHAR(500) NOT NULL,
--     transcript TEXT,
--     content TEXT,
--     status VARCHAR(50),
--     task_id VARCHAR(100),
--     created_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
--     updated_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP
-- );

-- CREATE OR REPLACE FUNCTION update_timestamp()
-- RETURNS TRIGGER AS $$
-- BEGIN
--     NEW.updated_at = NOW();
--     RETURN NEW;
-- END;
-- $$ LANGUAGE plpgsql;

-- -- Trigger call func update_timestamp() before UPDATE
-- CREATE TRIGGER set_timestamp
-- BEFORE UPDATE ON youtube_videos
-- FOR EACH ROW
-- EXECUTE PROCEDURE update_timestamp();