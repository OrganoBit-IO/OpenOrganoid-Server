import asyncio
import hashlib
import mimetypes
from datetime import datetime, timedelta
from pathlib import Path
from typing import Optional, Dict, Any, List, Callable, AsyncGenerator
import structlog
import aiofiles
from urllib.parse import quote

import aioboto3
from botocore.exceptions import ClientError, NoCredentialsError
from botocore.config import Config

logger = structlog.get_logger()


class FileManagementService:
    """S3-compatible file management service for DigitalOcean Spaces"""
    
    def __init__(self, s3_config: Dict[str, str]):
        self.endpoint_url = s3_config.get('endpoint_url')
        self.access_key_id = s3_config.get('access_key_id')
        self.secret_access_key = s3_config.get('secret_access_key')
        self.bucket_name = s3_config.get('bucket_name')
        self.region = s3_config.get('region', 'us-east-1')
        
        self.session = None
        self._initialized = False
        
        # Configuration
        self.multipart_threshold = 100 * 1024 * 1024  # 100MB
        self.multipart_chunksize = 10 * 1024 * 1024   # 10MB chunks
        self.max_concurrency = 10
        
        # Configure boto3 with retry and timeout settings
        self.config = Config(
            region_name=self.region,
            retries={
                'max_attempts': 3,
                'mode': 'adaptive'
            },
            max_pool_connections=50
        )
    
    async def initialize(self) -> None:
        """Initialize the S3 session and verify connectivity"""
        if self._initialized:
            return
        
        if not all([self.access_key_id, self.secret_access_key, self.bucket_name]):
            logger.warning("S3 credentials not configured, file operations will be limited")
            return
        
        try:
            self.session = aioboto3.Session(
                aws_access_key_id=self.access_key_id,
                aws_secret_access_key=self.secret_access_key,
                region_name=self.region
            )
            
            # Test connection
            async with self.session.client('s3', 
                                         endpoint_url=self.endpoint_url,
                                         config=self.config) as s3:
                await s3.head_bucket(Bucket=self.bucket_name)
            
            self._initialized = True
            logger.info("File management service initialized", bucket=self.bucket_name)
            
        except NoCredentialsError:
            logger.error("S3 credentials not found")
            raise
        except ClientError as e:
            error_code = e.response['Error']['Code']
            if error_code == 'NoSuchBucket':
                logger.error("S3 bucket not found", bucket=self.bucket_name)
            else:
                logger.error("S3 connection failed", error=str(e))
            raise
        except Exception as e:
            logger.error("File management service initialization failed", error=str(e))
            raise
    
    async def cleanup(self) -> None:
        """Cleanup resources"""
        self._initialized = False
        logger.info("File management service cleaned up")
    
    def _ensure_initialized(self):
        """Ensure service is initialized"""
        if not self._initialized:
            raise RuntimeError("File management service not initialized")
    
    async def upload_file(self, 
                         file_path: Path, 
                         s3_key: str,
                         metadata: Optional[Dict[str, str]] = None,
                         progress_callback: Optional[Callable] = None) -> Dict[str, Any]:
        """Upload file to S3 with progress tracking"""
        self._ensure_initialized()
        
        if not file_path.exists():
            raise FileNotFoundError(f"File not found: {file_path}")
        
        file_size = file_path.stat().st_size
        
        try:
            # Calculate checksums
            md5_hash = await self._calculate_md5(file_path)
            sha256_hash = await self._calculate_sha256(file_path)
            
            # Determine content type
            content_type, _ = mimetypes.guess_type(str(file_path))
            content_type = content_type or 'application/octet-stream'
            
            # Prepare metadata
            upload_metadata = {
                'uploaded-by': 'openorganoid-system',
                'upload-timestamp': datetime.utcnow().isoformat(),
                'original-filename': file_path.name,
                'md5-checksum': md5_hash,
                'sha256-checksum': sha256_hash,
            }
            
            if metadata:
                upload_metadata.update(metadata)
            
            # Choose upload method based on file size
            if file_size > self.multipart_threshold:
                result = await self._upload_large_file(
                    file_path, s3_key, content_type, upload_metadata, progress_callback
                )
            else:
                result = await self._upload_small_file(
                    file_path, s3_key, content_type, upload_metadata, progress_callback
                )
            
            logger.info("File uploaded successfully", 
                       s3_key=s3_key, size=file_size, method=result.get('method'))
            
            return {
                "s3_key": s3_key,
                "bucket": self.bucket_name,
                "size": file_size,
                "content_type": content_type,
                "md5_checksum": md5_hash,
                "sha256_checksum": sha256_hash,
                "upload_method": result.get('method'),
                "etag": result.get('etag'),
                "status": "success"
            }
            
        except Exception as e:
            logger.error("File upload failed", s3_key=s3_key, error=str(e))
            raise
    
    async def _upload_small_file(self, 
                               file_path: Path, 
                               s3_key: str,
                               content_type: str,
                               metadata: Dict[str, str],
                               progress_callback: Optional[Callable] = None) -> Dict[str, Any]:
        """Upload small file in single operation"""
        
        async with self.session.client('s3', 
                                     endpoint_url=self.endpoint_url,
                                     config=self.config) as s3:
            
            async with aiofiles.open(file_path, 'rb') as f:
                file_data = await f.read()
            
            if progress_callback:
                await progress_callback(len(file_data), len(file_data))
            
            response = await s3.put_object(
                Bucket=self.bucket_name,
                Key=s3_key,
                Body=file_data,
                ContentType=content_type,
                Metadata=metadata
            )
            
            return {
                "method": "single_upload",
                "etag": response['ETag'].strip('"')
            }
    
    async def _upload_large_file(self, 
                               file_path: Path, 
                               s3_key: str,
                               content_type: str,
                               metadata: Dict[str, str],
                               progress_callback: Optional[Callable] = None) -> Dict[str, Any]:
        """Upload large file using multipart upload"""
        
        async with self.session.client('s3', 
                                     endpoint_url=self.endpoint_url,
                                     config=self.config) as s3:
            
            # Initiate multipart upload
            response = await s3.create_multipart_upload(
                Bucket=self.bucket_name,
                Key=s3_key,
                ContentType=content_type,
                Metadata=metadata
            )
            
            upload_id = response['UploadId']
            parts = []
            
            try:
                file_size = file_path.stat().st_size
                uploaded_bytes = 0
                
                async for part_num, chunk in self._read_file_chunks(file_path, self.multipart_chunksize):
                    part_response = await s3.upload_part(
                        Bucket=self.bucket_name,
                        Key=s3_key,
                        PartNumber=part_num,
                        UploadId=upload_id,
                        Body=chunk
                    )
                    
                    parts.append({
                        'ETag': part_response['ETag'],
                        'PartNumber': part_num
                    })
                    
                    uploaded_bytes += len(chunk)
                    
                    if progress_callback:
                        await progress_callback(uploaded_bytes, file_size)
                
                # Complete multipart upload
                complete_response = await s3.complete_multipart_upload(
                    Bucket=self.bucket_name,
                    Key=s3_key,
                    UploadId=upload_id,
                    MultipartUpload={'Parts': parts}
                )
                
                return {
                    "method": "multipart_upload",
                    "etag": complete_response['ETag'].strip('"'),
                    "parts_count": len(parts)
                }
                
            except Exception as e:
                # Abort multipart upload on failure
                try:
                    await s3.abort_multipart_upload(
                        Bucket=self.bucket_name,
                        Key=s3_key,
                        UploadId=upload_id
                    )
                except Exception:
                    pass  # Best effort cleanup
                raise e
    
    async def _read_file_chunks(self, file_path: Path, chunk_size: int) -> AsyncGenerator[tuple, None]:
        """Read file in chunks for multipart upload"""
        part_num = 1
        
        async with aiofiles.open(file_path, 'rb') as f:
            while True:
                chunk = await f.read(chunk_size)
                if not chunk:
                    break
                yield part_num, chunk
                part_num += 1
    
    async def download_file(self, 
                          s3_key: str, 
                          local_path: Path,
                          progress_callback: Optional[Callable] = None) -> Dict[str, Any]:
        """Download file from S3"""
        self._ensure_initialized()
        
        try:
            async with self.session.client('s3', 
                                         endpoint_url=self.endpoint_url,
                                         config=self.config) as s3:
                
                # Get object metadata
                head_response = await s3.head_object(Bucket=self.bucket_name, Key=s3_key)
                file_size = head_response['ContentLength']
                
                # Ensure local directory exists
                local_path.parent.mkdir(parents=True, exist_ok=True)
                
                # Download file
                async with aiofiles.open(local_path, 'wb') as f:
                    response = await s3.get_object(Bucket=self.bucket_name, Key=s3_key)
                    
                    downloaded_bytes = 0
                    async for chunk in response['Body']:
                        await f.write(chunk)
                        downloaded_bytes += len(chunk)
                        
                        if progress_callback:
                            await progress_callback(downloaded_bytes, file_size)
                
                logger.info("File downloaded successfully", s3_key=s3_key, size=file_size)
                
                return {
                    "s3_key": s3_key,
                    "local_path": str(local_path),
                    "size": file_size,
                    "status": "success"
                }
                
        except ClientError as e:
            if e.response['Error']['Code'] == 'NoSuchKey':
                raise FileNotFoundError(f"S3 object not found: {s3_key}")
            else:
                logger.error("File download failed", s3_key=s3_key, error=str(e))
                raise
    
    async def delete_file(self, s3_key: str) -> Dict[str, Any]:
        """Delete file from S3"""
        self._ensure_initialized()
        
        try:
            async with self.session.client('s3', 
                                         endpoint_url=self.endpoint_url,
                                         config=self.config) as s3:
                
                await s3.delete_object(Bucket=self.bucket_name, Key=s3_key)
                
                logger.info("File deleted successfully", s3_key=s3_key)
                
                return {
                    "s3_key": s3_key,
                    "status": "deleted"
                }
                
        except Exception as e:
            logger.error("File deletion failed", s3_key=s3_key, error=str(e))
            raise
    
    async def list_files(self, 
                        prefix: str = "", 
                        max_keys: int = 1000) -> List[Dict[str, Any]]:
        """List files with given prefix"""
        self._ensure_initialized()
        
        try:
            async with self.session.client('s3', 
                                         endpoint_url=self.endpoint_url,
                                         config=self.config) as s3:
                
                response = await s3.list_objects_v2(
                    Bucket=self.bucket_name,
                    Prefix=prefix,
                    MaxKeys=max_keys
                )
                
                files = []
                for obj in response.get('Contents', []):
                    files.append({
                        "key": obj['Key'],
                        "size": obj['Size'],
                        "last_modified": obj['LastModified'].isoformat(),
                        "etag": obj['ETag'].strip('"')
                    })
                
                return files
                
        except Exception as e:
            logger.error("File listing failed", prefix=prefix, error=str(e))
            raise
    
    async def generate_presigned_url(self, 
                                   s3_key: str, 
                                   expiration: int = 3600,
                                   method: str = "GET") -> str:
        """Generate presigned URL for file access"""
        self._ensure_initialized()
        
        try:
            async with self.session.client('s3', 
                                         endpoint_url=self.endpoint_url,
                                         config=self.config) as s3:
                
                if method.upper() == "GET":
                    url = await s3.generate_presigned_url(
                        'get_object',
                        Params={'Bucket': self.bucket_name, 'Key': s3_key},
                        ExpiresIn=expiration
                    )
                elif method.upper() == "PUT":
                    url = await s3.generate_presigned_url(
                        'put_object',
                        Params={'Bucket': self.bucket_name, 'Key': s3_key},
                        ExpiresIn=expiration
                    )
                else:
                    raise ValueError(f"Unsupported HTTP method: {method}")
                
                logger.debug("Presigned URL generated", s3_key=s3_key, method=method)
                return url
                
        except Exception as e:
            logger.error("Presigned URL generation failed", s3_key=s3_key, error=str(e))
            raise
    
    async def get_file_metadata(self, s3_key: str) -> Dict[str, Any]:
        """Get file metadata from S3"""
        self._ensure_initialized()
        
        try:
            async with self.session.client('s3', 
                                         endpoint_url=self.endpoint_url,
                                         config=self.config) as s3:
                
                response = await s3.head_object(Bucket=self.bucket_name, Key=s3_key)
                
                return {
                    "key": s3_key,
                    "size": response['ContentLength'],
                    "content_type": response['ContentType'],
                    "last_modified": response['LastModified'].isoformat(),
                    "etag": response['ETag'].strip('"'),
                    "metadata": response.get('Metadata', {})
                }
                
        except ClientError as e:
            if e.response['Error']['Code'] == '404':
                raise FileNotFoundError(f"S3 object not found: {s3_key}")
            else:
                logger.error("Failed to get file metadata", s3_key=s3_key, error=str(e))
                raise
    
    async def _calculate_md5(self, file_path: Path) -> str:
        """Calculate MD5 hash of file"""
        hash_md5 = hashlib.md5()
        
        async with aiofiles.open(file_path, 'rb') as f:
            async for chunk in self._read_file_in_chunks(f, 8192):
                hash_md5.update(chunk)
        
        return hash_md5.hexdigest()
    
    async def _calculate_sha256(self, file_path: Path) -> str:
        """Calculate SHA256 hash of file"""
        hash_sha256 = hashlib.sha256()
        
        async with aiofiles.open(file_path, 'rb') as f:
            async for chunk in self._read_file_in_chunks(f, 8192):
                hash_sha256.update(chunk)
        
        return hash_sha256.hexdigest()
    
    async def _read_file_in_chunks(self, file_handle, chunk_size: int):
        """Read file in chunks asynchronously"""
        while True:
            chunk = await file_handle.read(chunk_size)
            if not chunk:
                break
            yield chunk
    
    async def health_check(self) -> Dict[str, Any]:
        """Perform health check on S3 service"""
        if not self._initialized:
            return {"status": "not_configured"}
        
        try:
            async with self.session.client('s3', 
                                         endpoint_url=self.endpoint_url,
                                         config=self.config) as s3:
                
                # Test bucket access
                await s3.head_bucket(Bucket=self.bucket_name)
                
                return {
                    "status": "healthy",
                    "bucket": self.bucket_name,
                    "endpoint": self.endpoint_url
                }
                
        except Exception as e:
            logger.error("S3 health check failed", error=str(e))
            return {
                "status": "unhealthy",
                "error": str(e)
            }