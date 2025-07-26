#!/bin/bash

# OpenOrganoid Server Development Startup Script

set -e

echo "🚀 Starting OpenOrganoid Server Development Environment"

# Change to project root
cd "$(dirname "$0")/../.."

# Create data directories if they don't exist
mkdir -p data/storage data/datalad data/uploads

# Start Docker Compose services
echo "📦 Starting Docker services..."
docker-compose -f infrastructure/docker/docker-compose.dev.yml up -d postgres redis

# Wait for PostgreSQL to be ready
echo "⏳ Waiting for PostgreSQL to be ready..."
until docker-compose -f infrastructure/docker/docker-compose.dev.yml exec postgres pg_isready -U openorganoid -d openorganoid; do
  echo "PostgreSQL is not ready yet, waiting..."
  sleep 2
done

echo "✅ PostgreSQL is ready!"

# Run database migrations
echo "🔄 Running database migrations..."
cd api
if [ -d "alembic" ]; then
    uv run alembic upgrade head
else
    echo "⚠️  No migrations found. Run 'uv run alembic init alembic' first."
fi
cd ..

# Start all services
echo "🎯 Starting all services..."
docker-compose -f infrastructure/docker/docker-compose.dev.yml up -d

echo "🎉 OpenOrganoid Server is now running!"
echo ""
echo "📋 Available services:"
echo "  • API Gateway: http://localhost:8000"
echo "  • API Documentation: http://localhost:8000/docs"
echo "  • Flower (Celery Monitor): http://localhost:5555"
echo "  • PostgreSQL: localhost:5432"
echo "  • Redis: localhost:6379"
echo ""
echo "📝 To view logs: docker-compose -f infrastructure/docker/docker-compose.dev.yml logs -f"
echo "🛑 To stop: docker-compose -f infrastructure/docker/docker-compose.dev.yml down"