# OpenOrganoid Server Deployment Guide

This guide covers deploying the OpenOrganoid Server to Railway with DataLad integration, S3 storage, and comprehensive monitoring.

## Architecture Overview

The system implements a FastAPI-based data repository platform with:
- **DataLad Integration**: Version control for datasets using git and git-annex
- **S3 Storage**: DigitalOcean Spaces for file storage with CDN
- **PostgreSQL**: Metadata and relationship storage
- **Redis**: Caching and task queues
- **Railway**: Container deployment platform

## Prerequisites

1. **Railway Account**: Sign up at [railway.app](https://railway.app)
2. **DigitalOcean Spaces**: Create a Spaces bucket for file storage
3. **PostgreSQL Database**: Railway will provision this automatically
4. **Redis Instance**: Railway will provision this automatically

## Environment Variables

Configure these environment variables in Railway:

### Database Configuration
```bash
DATABASE_URL=postgresql://user:password@host:port/database
REDIS_URL=redis://host:port/0
```

### Security Configuration
```bash
SECRET_KEY=your-super-secret-key-change-in-production
ALGORITHM=HS256
ACCESS_TOKEN_EXPIRE_MINUTES=60
```

### Application Configuration
```bash
ENVIRONMENT=production
DEBUG=false
APP_NAME=OpenOrganoid Data Repository
APP_VERSION=1.0.0
```

### S3/DigitalOcean Spaces Configuration
```bash
S3_ENDPOINT_URL=https://nyc3.digitaloceanspaces.com
S3_ACCESS_KEY_ID=your-spaces-access-key
S3_SECRET_ACCESS_KEY=your-spaces-secret-key
S3_BUCKET_NAME=your-bucket-name
S3_REGION=nyc3
```

### Storage Configuration
```bash
STORAGE_PATH=/app/data/storage
UPLOAD_PATH=/app/data/uploads
DATALAD_PATH=/app/data/datalad
MAX_FILE_SIZE=107374182400  # 100GB
```

### API Configuration
```bash
API_V1_PREFIX=/api/v1
CORS_ORIGINS=["https://your-frontend-domain.com"]
PORT=8000
```

## Railway Deployment Steps

### 1. Prepare Repository

Ensure your repository has the following structure:
```
OpenOrganoid-Server/
├── railway.json          # Railway configuration
├── api/
│   ├── Dockerfile        # Production dockerfile
│   ├── pyproject.toml    # Dependencies
│   └── app/             # FastAPI application
├── DEPLOYMENT_GUIDE.md  # This file
└── README.md           # Project documentation
```

### 2. Create Railway Project

1. Connect your GitHub repository to Railway
2. Create a new project from the repository
3. Railway will automatically detect the `railway.json` configuration

### 3. Add Required Services

Railway will auto-detect and create:
- **PostgreSQL Database**: For metadata storage
- **Redis**: For caching and task queues

### 4. Configure Environment Variables

In Railway dashboard:
1. Go to your service settings
2. Add all environment variables listed above
3. Ensure database and Redis URLs are properly set

### 5. Deploy

1. Railway will automatically build and deploy from your main branch
2. Monitor deployment logs for any issues
3. Verify health check endpoint: `https://your-app.railway.app/health`

## Service Configuration

### PostgreSQL Setup

Railway will automatically provision PostgreSQL. The application will:
- Create tables on first startup
- Run migrations automatically
- Handle connection pooling

### Redis Configuration

Redis is used for:
- Dataset metadata caching
- User session storage
- Background task queues
- Access tracking and analytics

### DigitalOcean Spaces Setup

1. Create a Spaces bucket in your preferred region
2. Generate Spaces access keys
3. Configure CORS policy for web access:

```json
[
  {
    "AllowedOrigins": ["*"],
    "AllowedMethods": ["GET", "PUT", "POST", "DELETE"],
    "AllowedHeaders": ["*"],
    "MaxAgeSeconds": 3600
  }
]
```

## Health Checks and Monitoring

### Health Check Endpoints

- `GET /health` - Basic health check
- `GET /health/detailed` - Detailed service status
- `GET /ready` - Kubernetes readiness probe
- `GET /live` - Kubernetes liveness probe

### Monitoring

The application includes:
- Structured logging with `structlog`
- Prometheus metrics (production only)
- Request/response logging
- Error tracking and alerting

### Log Analysis

All logs are structured JSON for easy parsing:
```json
{
  "event": "Dataset created",
  "dataset_id": "123e4567-e89b-12d3-a456-426614174000",
  "user_id": "456e7890-e89b-12d3-a456-426614174001",
  "timestamp": "2024-01-15T10:30:00Z",
  "level": "info"
}
```

## API Documentation

Once deployed, API documentation is available at:
- Swagger UI: `https://your-app.railway.app/docs` (development only)
- ReDoc: `https://your-app.railway.app/redoc` (development only)

For production, API documentation should be provided separately for security.

## Security Considerations

### Authentication
- JWT-based authentication with configurable expiration
- API key support for programmatic access
- Role-based access control (RBAC)

### Data Protection
- All passwords hashed with bcrypt
- API keys securely hashed before storage
- Signed URLs for secure file access
- HTTPS enforcement in production

### Input Validation
- Comprehensive request validation with Pydantic
- File type validation and size limits
- SQL injection prevention with parameterized queries

## Performance Optimization

### Database
- Connection pooling with SQLAlchemy
- Proper indexing for common queries
- Async database operations

### Caching
- Redis-based caching for frequently accessed data
- Cache warming on application startup
- Intelligent cache invalidation

### File Storage
- Multipart uploads for large files
- CDN integration for faster access
- Intelligent upload strategies

## Troubleshooting

### Common Issues

1. **Database Connection Errors**
   - Verify `DATABASE_URL` environment variable
   - Check database service status in Railway
   - Ensure database allows connections

2. **Redis Connection Errors**
   - Verify `REDIS_URL` environment variable
   - Check Redis service status in Railway

3. **S3/Spaces Upload Errors**
   - Verify S3 credentials and bucket configuration
   - Check bucket CORS policy
   - Ensure bucket exists and is accessible

4. **DataLad Errors**
   - Verify git and git-annex are installed in container
   - Check file system permissions
   - Ensure sufficient disk space

### Debug Mode

For debugging, set `DEBUG=true` to enable:
- Detailed SQL query logging
- Enhanced error messages
- Development-only endpoints

### Log Collection

All application logs are available in Railway's log viewer:
1. Go to your service in Railway dashboard
2. Click on "Deployments" tab
3. View real-time logs and historical data

## Scaling Considerations

### Horizontal Scaling
- Application is stateless and can be scaled horizontally
- File uploads are handled through S3, not local storage
- Database connections are pooled and managed

### Resource Requirements
- Minimum: 1 CPU, 512MB RAM
- Recommended: 2 CPU, 2GB RAM for production
- Storage: Ephemeral only (files stored in S3)

### Load Testing
Before production deployment:
1. Test file upload performance
2. Verify database query performance
3. Test concurrent user scenarios
4. Monitor memory usage under load

## Maintenance

### Database Backups
Railway automatically backs up PostgreSQL databases. For additional safety:
- Regular export of critical data
- Test restoration procedures
- Monitor backup integrity

### Application Updates
1. Test changes in development environment
2. Deploy to staging environment
3. Verify all services are operational
4. Deploy to production
5. Monitor deployment health

### Security Updates
- Regularly update Python dependencies
- Monitor security advisories
- Apply security patches promptly
- Review access logs regularly

## Support and Documentation

For issues or questions:
1. Check application logs in Railway dashboard
2. Review this deployment guide
3. Consult API documentation
4. Contact development team

## Next Steps

After successful deployment:
1. Set up monitoring and alerting
2. Configure automated backups
3. Implement CI/CD pipeline
4. Set up staging environment
5. Plan disaster recovery procedures