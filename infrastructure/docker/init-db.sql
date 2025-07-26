-- Initialize OpenOrganoid Database
-- Create extensions
CREATE EXTENSION IF NOT EXISTS "uuid-ossp";
CREATE EXTENSION IF NOT EXISTS "pg_trgm";

-- Create full text search configuration
CREATE TEXT SEARCH CONFIGURATION english_stem (COPY = english);

-- Grant permissions
GRANT ALL PRIVILEGES ON DATABASE openorganoid TO openorganoid;
GRANT ALL PRIVILEGES ON SCHEMA public TO openorganoid;