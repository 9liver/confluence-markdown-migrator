"""Cache manager for Confluence API responses with TTL support."""

import hashlib
import json
import logging
import os
import time
from datetime import datetime, timedelta
from enum import Enum
from typing import Any, Dict, List, Optional, Union, Callable

logger = logging.getLogger('confluence_markdown_migrator.fetcher.cache')


class CacheMode(Enum):
    """Cache operation modes."""
    DISABLE = "disable"
    ALWAYS_USE = "always_use"
    VALIDATE = "validate"


class CacheManager:
    """Manages local caching of Confluence API responses with TTL support."""
    
    def __init__(self, config: Dict[str, Any], mode: str = "validate"):
        """
        Initialize cache manager.
        
        Args:
            config: Configuration dictionary with cache settings
            mode: Cache mode (disable, always_use, validate)
        """
        cache_config = config.get('advanced', {}).get('cache', {})
        
        self.enabled = cache_config.get('enabled', False)
        if self.enabled:
            self.mode = CacheMode[mode.upper()]
        else:
            self.mode = CacheMode.DISABLE
            
        self.cache_dir = os.path.abspath(cache_config.get('directory', './.cache'))
        self.ttl_seconds = int(cache_config.get('ttl_seconds', 86400))  # 1 day default
        self.validate_with_headers = cache_config.get('validate_with_headers', True)
        self.cache_attachments = cache_config.get('cache_attachments', True)
        self.verify_checksums = cache_config.get('verify_checksums', True)
        
        # Statistics tracking
        self.stats = {
            'hits': 0,
            'misses': 0,
            'validations': 0,
            'invalidations': 0
        }
        
        # Ensure cache directory exists
        if self.enabled:
            os.makedirs(self.cache_dir, exist_ok=True)
            logger.info(f"Cache enabled: mode={self.mode.value}, directory={self.cache_dir}, TTL={self.ttl_seconds}s")
        else:
            logger.debug("Cache disabled")
    
    def get(self, key: str) -> Optional[Any]:
        """
        Retrieve data from cache if available and not expired.
        
        Args:
            key: Cache key
            
        Returns:
            Cached data or None if not found/expired
        """
        if self.mode == CacheMode.DISABLE:
            return None
            
        if self.mode == CacheMode.ALWAYS_USE:
            # Skip TTL check in ALWAYS_USE mode
            cache_file = self._get_cache_file_path(key)
            if not os.path.exists(cache_file):
                self.stats['misses'] += 1
                logger.debug(f"Cache miss: {key} (file not found)")
                return None
            
            try:
                with open(cache_file, 'r', encoding='utf-8') as f:
                    cache_entry = json.load(f)
                self.stats['hits'] += 1
                logger.debug(f"Cache hit (ALWAYS_USE mode): {key}")
                return cache_entry['data']
            except Exception as e:
                self.stats['misses'] += 1
                logger.warning(f"Cache read error for {key}: {str(e)}")
                return None
        
        # Default VALIDATE mode - respect TTL
        cache_file = self._get_cache_file_path(key)
        
        if not os.path.exists(cache_file):
            self.stats['misses'] += 1
            logger.debug(f"Cache miss: {key} (file not found)")
            return None
        
        try:
            with open(cache_file, 'r', encoding='utf-8') as f:
                cache_entry = json.load(f)
            
            # Check TTL
            cached_time = datetime.fromisoformat(cache_entry['timestamp'])
            age = datetime.utcnow() - cached_time
            
            if age.total_seconds() > self.ttl_seconds:
                self.stats['misses'] += 1
                logger.debug(f"Cache expired: {key} (age: {age.total_seconds():.0f}s > {self.ttl_seconds}s)")
                # Delete expired cache file
                try:
                    os.remove(cache_file)
                except OSError:
                    pass
                return None
            
            self.stats['hits'] += 1
            logger.debug(f"Cache hit: {key} (age: {age.total_seconds():.0f}s)")
            return cache_entry['data']
            
        except (json.JSONDecodeError, KeyError, OSError) as e:
            self.stats['misses'] += 1
            logger.warning(f"Cache read error for {key}: {str(e)}")
            # Remove corrupted cache file
            try:
                os.remove(cache_file)
            except OSError:
                pass
            return None
    
    def get_with_validation(self, key: str, validation_callback: Callable[[Dict[str, Any]], bool]) -> Optional[Any]:
        """
        Retrieve cached data with validation callback.
        
        Args:
            key: Cache key
            validation_callback: Function that takes cache metadata and returns True if valid
            
        Returns:
            Cached data if valid, None otherwise
        """
        if self.mode == CacheMode.DISABLE:
            return None
        
        if self.mode == CacheMode.ALWAYS_USE:
            # Skip validation in ALWAYS_USE mode
            return self.get(key)
        
        self.stats['validations'] += 1
        
        cache_file = self._get_cache_file_path(key)
        if not os.path.exists(cache_file):
            self.stats['misses'] += 1
            return None
        
        try:
            with open(cache_file, 'r', encoding='utf-8') as f:
                cache_entry = json.load(f)
            
            # Check TTL first
            cached_time = datetime.fromisoformat(cache_entry['timestamp'])
            age = datetime.utcnow() - cached_time
            
            if age.total_seconds() > self.ttl_seconds:
                self.stats['misses'] += 1
                logger.debug(f"Cache expired: {key}")
                try:
                    os.remove(cache_file)
                except OSError:
                    pass
                return None
            
            # Run validation callback
            validation_metadata = cache_entry.get('validation_metadata', {})
            if validation_callback(validation_metadata):
                self.stats['hits'] += 1
                logger.debug(f"Cache validation passed: {key}")
                return cache_entry['data']
            else:
                self.stats['invalidations'] += 1
                self.stats['misses'] += 1
                logger.debug(f"Cache invalidated: {key}")
                try:
                    os.remove(cache_file)
                except OSError:
                    pass
                return None
                
        except Exception as e:
            self.stats['misses'] += 1
            logger.warning(f"Cache validation error for {key}: {str(e)}")
            try:
                os.remove(cache_file)
            except OSError:
                pass
            return None
    
    def set(self, key: str, data: Any, validation_metadata: Optional[Dict[str, Any]] = None) -> bool:
        """
        Store data in cache.
        
        Args:
            key: Cache key
            data: Data to cache (must be JSON serializable)
            validation_metadata: Optional metadata for validation (ETag, Last-Modified, etc.)
            
        Returns:
            True if successful, False otherwise
        """
        if self.mode == CacheMode.DISABLE:
            return False
        
        cache_file = self._get_cache_file_path(key)
        
        try:
            cache_entry = {
                'timestamp': datetime.utcnow().isoformat(),
                'ttl_seconds': self.ttl_seconds,
                'data': data
            }
            
            if validation_metadata:
                cache_entry['validation_metadata'] = validation_metadata
            
            with open(cache_file, 'w', encoding='utf-8') as f:
                json.dump(cache_entry, f, ensure_ascii=False, indent=2)
            
            logger.debug(f"Cache stored: {key}")
            return True
            
        except (OSError, TypeError) as e:
            logger.warning(f"Cache write error for {key}: {str(e)}")
            return False
    
    def get_binary(self, key: str) -> Optional[bytes]:
        """
        Retrieve binary data from cache with checksum verification.
        
        Args:
            key: Cache key
            
        Returns:
            Binary data if valid, None otherwise
        """
        if self.mode == CacheMode.DISABLE or not self.cache_attachments:
            return None
        
        binary_file = self._get_binary_cache_path(key)
        metadata_file = self._get_binary_metadata_path(key)
        
        if not os.path.exists(binary_file) or not os.path.exists(metadata_file):
            self.stats['misses'] += 1
            logger.debug(f"Binary cache miss: {key}")
            return None
        
        try:
            # Load metadata
            with open(metadata_file, 'r', encoding='utf-8') as f:
                metadata = json.load(f)
            
            # Check TTL
            cached_time = datetime.fromisoformat(metadata['timestamp'])
            age = datetime.utcnow() - cached_time
            
            if age.total_seconds() > self.ttl_seconds:
                self.stats['misses'] += 1
                logger.debug(f"Binary cache expired: {key}")
                try:
                    os.remove(binary_file)
                    os.remove(metadata_file)
                except OSError:
                    pass
                return None
            
            # Read binary data
            with open(binary_file, 'rb') as f:
                binary_data = f.read()
            
            # Verify checksum if enabled
            if self.verify_checksums:
                expected_checksum = metadata.get('checksum')
                if expected_checksum:
                    if not self._verify_checksum(binary_data, expected_checksum):
                        logger.warning(f"Checksum mismatch for cached binary: {key}")
                        try:
                            os.remove(binary_file)
                            os.remove(metadata_file)
                        except OSError:
                            pass
                        self.stats['misses'] += 1
                        return None
            
            self.stats['hits'] += 1
            logger.debug(f"Binary cache hit: {key}")
            return binary_data
            
        except Exception as e:
            self.stats['misses'] += 1
            logger.warning(f"Binary cache read error for {key}: {str(e)}")
            try:
                os.remove(binary_file)
                os.remove(metadata_file)
            except OSError:
                pass
            return None
    
    def set_binary(self, key: str, data: bytes, metadata: Optional[Dict[str, Any]] = None) -> bool:
        """
        Store binary data in cache with metadata.
        
        Args:
            key: Cache key
            data: Binary data to cache
            metadata: Additional metadata (media_type, etc.)
            
        Returns:
            True if successful, False otherwise
        """
        if self.mode == CacheMode.DISABLE or not self.cache_attachments:
            return False
        
        binary_file = self._get_binary_cache_path(key)
        metadata_file = self._get_binary_metadata_path(key)
        
        try:
            # Compute checksum
            checksum = hashlib.sha256(data).hexdigest()
            
            # Save binary data
            with open(binary_file, 'wb') as f:
                f.write(data)
            
            # Save metadata
            cache_metadata = {
                'timestamp': datetime.utcnow().isoformat(),
                'ttl_seconds': self.ttl_seconds,
                'checksum': checksum,
                'size_bytes': len(data)
            }
            
            if metadata:
                cache_metadata.update(metadata)
            
            with open(metadata_file, 'w', encoding='utf-8') as f:
                json.dump(cache_metadata, f, ensure_ascii=False, indent=2)
            
            logger.debug(f"Binary cache stored: {key} ({len(data)} bytes)")
            return True
            
        except Exception as e:
            logger.warning(f"Binary cache write error for {key}: {str(e)}")
            try:
                os.remove(binary_file)
                os.remove(metadata_file)
            except OSError:
                pass
            return False
    
    def clear(self, pattern: Optional[str] = None) -> int:
        """
        Clear cache entries matching pattern.
        
        Args:
            pattern: Optional pattern to match cache keys (supports wildcards)
                    If None, clears all cache entries
                    
        Returns:
            Number of entries cleared
        """
        if self.mode == CacheMode.DISABLE or not os.path.exists(self.cache_dir):
            return 0
        
        cleared = 0
        
        try:
            for filename in os.listdir(self.cache_dir):
                if filename.endswith('.json') or filename.endswith('.bin'):
                    # Extract cache key from filename
                    if filename.endswith('.json'):
                        cache_key = filename[:-5]
                    else:  # .bin
                        cache_key = filename[:-4]
                    
                    if pattern is None or self._match_pattern(cache_key, pattern):
                        file_path = os.path.join(self.cache_dir, filename)
                        try:
                            os.remove(file_path)
                            cleared += 1
                            logger.debug(f"Cleared cache: {cache_key}")
                        except OSError as e:
                            logger.warning(f"Failed to clear cache file {file_path}: {str(e)}")
            
        except OSError as e:
            logger.error(f"Failed to list cache directory: {str(e)}")
        
        self.reset_stats()
        logger.info(f"Cleared {cleared} cache entries" + (f" matching '{pattern}'" if pattern else ""))
        return cleared
    
    def get_stats(self) -> Dict[str, Any]:
        """
        Get enhanced cache statistics.
        
        Returns:
            Dictionary with cache statistics
        """
        if self.mode == CacheMode.DISABLE or not os.path.exists(self.cache_dir):
            return {
                'enabled': False,
                'mode': self.mode.value if hasattr(self, 'mode') else 'disable',
                'total_entries': 0,
                'total_size_bytes': 0,
                'hits': 0,
                'misses': 0,
                'validations': 0,
                'invalidations': 0,
                'hit_rate': 0.0,
                'api_calls_saved': 0
            }
        
        total_entries = 0
        total_size = 0
        expired_entries = 0
        
        try:
            for filename in os.listdir(self.cache_dir):
                if filename.endswith('.json') or filename.endswith('.bin'):
                    file_path = os.path.join(self.cache_dir, filename)
                    
                    try:
                        file_size = os.path.getsize(file_path)
                        total_size += file_size
                        total_entries += 1
                        
                        # Check if expired for JSON files
                        if filename.endswith('.json'):
                            try:
                                with open(file_path, 'r', encoding='utf-8') as f:
                                    cache_entry = json.load(f)
                                
                                cached_time = datetime.fromisoformat(cache_entry['timestamp'])
                                age = datetime.utcnow() - cached_time
                                
                                if age.total_seconds() > cache_entry['ttl_seconds']:
                                    expired_entries += 1
                            except:
                                expired_entries += 1
                                
                    except OSError:
                        expired_entries += 1
        
        except OSError:
            pass
        
        # Calculate hit rate
        total_requests = self.stats['hits'] + self.stats['misses']
        hit_rate = self.stats['hits'] / total_requests if total_requests > 0 else 0.0
        
        return {
            'enabled': True,
            'mode': self.mode.value,
            'cache_dir': self.cache_dir,
            'ttl_seconds': self.ttl_seconds,
            'total_entries': total_entries,
            'total_size_bytes': total_size,
            'total_size_mb': round(total_size / (1024 * 1024), 2),
            'expired_entries': expired_entries,
            'hits': self.stats['hits'],
            'misses': self.stats['misses'],
            'validations': self.stats['validations'],
            'invalidations': self.stats['invalidations'],
            'hit_rate': hit_rate,
            'api_calls_saved': self.stats['hits']  # Each hit saves one API call
        }
    
    def reset_stats(self) -> None:
        """Reset statistics counters."""
        self.stats = {
            'hits': 0,
            'misses': 0,
            'validations': 0,
            'invalidations': 0
        }
    
    def _get_cache_file_path(self, key: str) -> str:
        """Get file path for cache key."""
        safe_key = self._sanitize_key(key)
        return os.path.join(self.cache_dir, f"{safe_key}.json")
    
    def _get_binary_cache_path(self, key: str) -> str:
        """Get file path for binary cache key."""
        safe_key = self._sanitize_key(key)
        return os.path.join(self.cache_dir, f"{safe_key}.bin")
    
    def _get_binary_metadata_path(self, key: str) -> str:
        """Get file path for binary cache metadata."""
        safe_key = self._sanitize_key(key)
        return os.path.join(self.cache_dir, f"{safe_key}_meta.json")
    
    def _verify_checksum(self, data: bytes, expected_checksum: str) -> bool:
        """
        Verify data checksum matches expected value.
        
        Args:
            data: Binary data to verify
            expected_checksum: Expected SHA256 checksum
            
        Returns:
            True if checksum matches
        """
        actual_checksum = hashlib.sha256(data).hexdigest()
        return actual_checksum == expected_checksum
    
    def _sanitize_key(self, key: str) -> str:
        """
        Sanitize cache key to create valid filename.
        
        Args:
            key: Cache key
            
        Returns:
            Sanitized key safe for use as filename
        """
        # Use hash for long keys
        if len(key) > 200:
            key_hash = hashlib.md5(key.encode('utf-8')).hexdigest()[:16]
            key = key[:100] + "_" + key_hash
        
        # Replace problematic characters
        safe_key = "".join(c for c in key if c.isalnum() or c in "._-")
        return safe_key or "cache_key"
    
    def _match_pattern(self, key: str, pattern: str) -> bool:
        """
        Check if key matches pattern with wildcard support.
        
        Args:
            key: Cache key to check
            pattern: Pattern with * and ? wildcards
            
        Returns:
            True if matches
        """
        import fnmatch
        return fnmatch.fnmatch(key, pattern)
    
    @staticmethod
    def generate_cache_key(endpoint: str, **params) -> str:
        """
        Generate cache key from endpoint and parameters.
        
        Args:
            endpoint: API endpoint name
            **params: Parameters to include in key
            
        Returns:
            Cache key string
        """
        # Sort parameters for consistent key generation
        sorted_params = sorted(params.items())
        param_str = "_".join(f"{k}={v}" for k, v in sorted_params)
        
        if param_str:
            return f"{endpoint}_{param_str}"
        else:
            return endpoint
