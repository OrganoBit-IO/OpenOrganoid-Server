import asyncio
import os
import shutil
import subprocess
from pathlib import Path
from typing import Optional, Dict, Any, List
import uuid
import structlog
from datetime import datetime

import datalad.api as dl
from datalad.api import Dataset
from datalad.support.exceptions import CommandError

logger = structlog.get_logger()


class DataLadService:
    """Service for managing DataLad repositories and operations"""
    
    def __init__(self, workspace_root: Path):
        self.workspace_root = Path(workspace_root)
        self.active_repos: Dict[str, Path] = {}
        self._initialized = False
        
    async def initialize(self) -> None:
        """Initialize the DataLad service"""
        if self._initialized:
            return
            
        # Ensure workspace directory exists
        self.workspace_root.mkdir(parents=True, exist_ok=True)
        
        # Configure git for DataLad operations
        await self._configure_git()
        
        # Set up git-annex if needed
        await self._setup_git_annex()
        
        self._initialized = True
        logger.info("DataLad service initialized", workspace=str(self.workspace_root))
    
    async def _configure_git(self) -> None:
        """Configure git for DataLad operations"""
        try:
            # Set global git configuration
            git_commands = [
                ['git', 'config', '--global', 'user.name', 'OpenOrganoid System'],
                ['git', 'config', '--global', 'user.email', 'system@openorganoid.com'],
                ['git', 'config', '--global', 'init.defaultBranch', 'main']
            ]
            
            for cmd in git_commands:
                result = await self._run_command(cmd)
                if result.returncode != 0:
                    logger.warning("Git config command failed", cmd=cmd, error=result.stderr)
                    
        except Exception as e:
            logger.error("Failed to configure git", error=str(e))
            raise
    
    async def _setup_git_annex(self) -> None:
        """Setup git-annex configuration"""
        try:
            # Check if git-annex is available
            result = await self._run_command(['git-annex', 'version'])
            if result.returncode == 0:
                logger.info("Git-annex available", version=result.stdout.split('\n')[0])
            else:
                logger.warning("Git-annex not available")
        except Exception as e:
            logger.warning("Could not check git-annex availability", error=str(e))
    
    async def _run_command(self, cmd: List[str], cwd: Optional[Path] = None) -> subprocess.CompletedProcess:
        """Run shell command asynchronously"""
        try:
            process = await asyncio.create_subprocess_exec(
                *cmd,
                cwd=cwd or self.workspace_root,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE
            )
            stdout, stderr = await process.communicate()
            
            return subprocess.CompletedProcess(
                args=cmd,
                returncode=process.returncode,
                stdout=stdout.decode() if stdout else '',
                stderr=stderr.decode() if stderr else ''
            )
        except Exception as e:
            logger.error("Command execution failed", cmd=cmd, error=str(e))
            raise
    
    async def create_dataset(self, 
                           dataset_id: str, 
                           metadata: Dict[str, Any],
                           s3_config: Optional[Dict[str, str]] = None) -> Dict[str, Any]:
        """Create new DataLad dataset with S3 remote"""
        
        if not self._initialized:
            await self.initialize()
        
        repo_path = self.workspace_root / dataset_id
        
        try:
            # Remove existing directory if it exists
            if repo_path.exists():
                shutil.rmtree(repo_path)
            
            logger.info("Creating DataLad dataset", dataset_id=dataset_id, path=str(repo_path))
            
            # Create dataset using DataLad API
            dataset = dl.create(
                path=str(repo_path),
                description=metadata.get('description', ''),
                dataset=None,
                force=True
            )
            
            # Add metadata file
            await self._add_dataset_metadata(repo_path, metadata)
            
            # Configure S3 remote if provided
            if s3_config:
                await self._setup_s3_remote(repo_path, dataset_id, s3_config)
            
            # Register in tracking system
            self.active_repos[dataset_id] = repo_path
            
            logger.info("DataLad dataset created successfully", dataset_id=dataset_id)
            
            return {
                "dataset_id": dataset_id,
                "path": str(repo_path),
                "status": "created",
                "remote_configured": s3_config is not None,
                "commit_hash": await self._get_current_commit_hash(repo_path)
            }
            
        except Exception as e:
            logger.error("Dataset creation failed", dataset_id=dataset_id, error=str(e))
            # Cleanup on failure
            if repo_path.exists():
                shutil.rmtree(repo_path)
            raise
    
    async def _add_dataset_metadata(self, repo_path: Path, metadata: Dict[str, Any]) -> None:
        """Add metadata file to dataset"""
        metadata_file = repo_path / ".datalad" / "metadata.json"
        metadata_file.parent.mkdir(exist_ok=True)
        
        import json
        with open(metadata_file, 'w') as f:
            json.dump({
                **metadata,
                "created_at": datetime.utcnow().isoformat(),
                "datalad_version": "0.19.0"  # Should get from datalad
            }, f, indent=2)
        
        # Add and commit metadata
        dataset = Dataset(repo_path)
        dataset.save(metadata_file, message="Add dataset metadata")
    
    async def _setup_s3_remote(self, repo_path: Path, dataset_id: str, s3_config: Dict[str, str]) -> None:
        """Configure S3 remote for dataset"""
        try:
            dataset = Dataset(repo_path)
            
            # Configure git-annex S3 remote
            s3_remote_name = "s3-storage"
            s3_url = f"s3://{s3_config['bucket_name']}/{dataset_id}/"
            
            # Add S3 remote
            remote_config = [
                'git', 'annex', 'initremote', s3_remote_name,
                'type=S3',
                f'bucket={s3_config["bucket_name"]}',
                f'prefix={dataset_id}/',
                'encryption=none'
            ]
            
            if s3_config.get('endpoint_url'):
                remote_config.append(f'host={s3_config["endpoint_url"].replace("https://", "")}')
            
            result = await self._run_command(remote_config, cwd=repo_path)
            
            if result.returncode == 0:
                logger.info("S3 remote configured", dataset_id=dataset_id, remote=s3_remote_name)
            else:
                logger.error("Failed to configure S3 remote", 
                           dataset_id=dataset_id, error=result.stderr)
                
        except Exception as e:
            logger.error("S3 remote setup failed", dataset_id=dataset_id, error=str(e))
            # Non-fatal error, dataset can still be used locally
    
    async def add_files(self, 
                       dataset_id: str, 
                       file_paths: List[Path],
                       commit_message: Optional[str] = None) -> Dict[str, Any]:
        """Add files to DataLad dataset"""
        
        repo_path = self.active_repos.get(dataset_id)
        if not repo_path or not repo_path.exists():
            raise ValueError(f"Dataset {dataset_id} not found")
        
        try:
            dataset = Dataset(repo_path)
            
            # Copy files to dataset directory
            added_files = []
            for file_path in file_paths:
                if not file_path.exists():
                    logger.warning("File not found", file_path=str(file_path))
                    continue
                
                # Determine target path within dataset
                target_path = repo_path / "data" / file_path.name
                target_path.parent.mkdir(parents=True, exist_ok=True)
                
                # Copy file
                shutil.copy2(file_path, target_path)
                added_files.append(target_path)
            
            if added_files:
                # Add files to dataset
                dataset.save(
                    path=[str(f.relative_to(repo_path)) for f in added_files],
                    message=commit_message or f"Add {len(added_files)} files"
                )
                
                logger.info("Files added to dataset", 
                           dataset_id=dataset_id, count=len(added_files))
            
            return {
                "dataset_id": dataset_id,
                "files_added": len(added_files),
                "commit_hash": await self._get_current_commit_hash(repo_path),
                "status": "success"
            }
            
        except Exception as e:
            logger.error("Failed to add files", dataset_id=dataset_id, error=str(e))
            raise
    
    async def create_version(self, 
                           dataset_id: str, 
                           version_name: str,
                           description: Optional[str] = None) -> Dict[str, Any]:
        """Create a new version (git tag) of the dataset"""
        
        repo_path = self.active_repos.get(dataset_id)
        if not repo_path or not repo_path.exists():
            raise ValueError(f"Dataset {dataset_id} not found")
        
        try:
            # Create git tag
            tag_message = description or f"Version {version_name}"
            cmd = ['git', 'tag', '-a', version_name, '-m', tag_message]
            
            result = await self._run_command(cmd, cwd=repo_path)
            
            if result.returncode == 0:
                commit_hash = await self._get_current_commit_hash(repo_path)
                
                logger.info("Version created", 
                           dataset_id=dataset_id, version=version_name, commit=commit_hash)
                
                return {
                    "dataset_id": dataset_id,
                    "version": version_name,
                    "commit_hash": commit_hash,
                    "status": "created"
                }
            else:
                raise Exception(f"Failed to create version: {result.stderr}")
                
        except Exception as e:
            logger.error("Version creation failed", 
                        dataset_id=dataset_id, version=version_name, error=str(e))
            raise
    
    async def get_dataset_info(self, dataset_id: str) -> Dict[str, Any]:
        """Get information about a dataset"""
        
        repo_path = self.active_repos.get(dataset_id)
        if not repo_path or not repo_path.exists():
            raise ValueError(f"Dataset {dataset_id} not found")
        
        try:
            dataset = Dataset(repo_path)
            
            # Get basic info
            info = {
                "dataset_id": dataset_id,
                "path": str(repo_path),
                "commit_hash": await self._get_current_commit_hash(repo_path),
                "status": "active"
            }
            
            # Get file count and size
            data_dir = repo_path / "data"
            if data_dir.exists():
                files = list(data_dir.rglob("*"))
                files = [f for f in files if f.is_file()]
                info["file_count"] = len(files)
                info["total_size"] = sum(f.stat().st_size for f in files)
            else:
                info["file_count"] = 0
                info["total_size"] = 0
            
            # Get versions (git tags)
            tags_result = await self._run_command(['git', 'tag', '-l'], cwd=repo_path)
            if tags_result.returncode == 0:
                info["versions"] = [tag.strip() for tag in tags_result.stdout.split('\n') if tag.strip()]
            else:
                info["versions"] = []
            
            return info
            
        except Exception as e:
            logger.error("Failed to get dataset info", dataset_id=dataset_id, error=str(e))
            raise
    
    async def _get_current_commit_hash(self, repo_path: Path) -> str:
        """Get current commit hash"""
        try:
            result = await self._run_command(['git', 'rev-parse', 'HEAD'], cwd=repo_path)
            if result.returncode == 0:
                return result.stdout.strip()
            return ""
        except Exception:
            return ""
    
    async def cleanup_dataset(self, dataset_id: str) -> None:
        """Clean up dataset resources"""
        repo_path = self.active_repos.get(dataset_id)
        if repo_path and repo_path.exists():
            try:
                shutil.rmtree(repo_path)
                del self.active_repos[dataset_id]
                logger.info("Dataset cleaned up", dataset_id=dataset_id)
            except Exception as e:
                logger.error("Dataset cleanup failed", dataset_id=dataset_id, error=str(e))
    
    async def cleanup(self) -> None:
        """Cleanup all resources"""
        logger.info("Cleaning up DataLad service")
        
        # Cleanup active repositories
        for dataset_id in list(self.active_repos.keys()):
            await self.cleanup_dataset(dataset_id)
        
        self._initialized = False
        logger.info("DataLad service cleanup completed")

    def get_dataset_path(self, dataset_id: str) -> Optional[Path]:
        """Get the path to a dataset"""
        return self.active_repos.get(dataset_id)