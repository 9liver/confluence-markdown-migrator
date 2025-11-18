"""
Integrity Verifier Module

Provides comprehensive content validation for fetched Confluence content,
ensuring completeness and correctness before conversion.
"""

import hashlib
import json
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path
from typing import Any, Dict, List, Optional, Set, Union

import requests
from bs4 import BeautifulSoup

from converters.link_processor import LinkProcessor
from models import ConfluenceAttachment, ConfluencePage, DocumentationTree


class IntegrityVerifier:
    """Comprehensive integrity verification for DocumentationTree."""
    
    def __init__(self, config: Dict[str, Any], tree: DocumentationTree, logger: Any):
        """Initialize the IntegrityVerifier.
        
        Args:
            config: Configuration dictionary
            tree: DocumentationTree to verify
            logger: Logger instance
        """
        self.config = config
        self.tree = tree
        self.logger = logger
        
        # Extract verification settings from config
        integrity_config = config.get('advanced', {}).get('integrity_verification', {})
        
        self.enabled = integrity_config.get('enabled', False)
        self.backup_dir = Path(integrity_config.get('backup_directory', './integrity-backup'))
        self.create_backup = integrity_config.get('create_backup', True)
        self.verification_depth = integrity_config.get('verification_depth', 'standard')
        self.verify_external_links = integrity_config.get('verify_external_links', False)
        self.compute_checksums = integrity_config.get('compute_checksums', True)
        self.checksum_workers = integrity_config.get('checksum_workers', 3)
        self.save_report = integrity_config.get('save_report', True)
        self.report_formats = integrity_config.get('report_formats', ['json'])
        
        self.dry_run = config.get('migration', {}).get('dry_run', False)
        
        self.link_processor = LinkProcessor()
        
    def verify_tree(self, tree: DocumentationTree) -> Dict[str, Any]:
        """Perform comprehensive integrity verification of the documentation tree.
        
        Args:
            tree: DocumentationTree to verify
            
        Returns:
            Comprehensive verification report dictionary
        """
        self.logger.info(f"Starting integrity verification (depth: {self.verification_depth})")
        
        start_time = time.time()
        results = {
            'timestamp': time.time(),
            'verification_depth': self.verification_depth,
        }
        
        try:
            # Run verification checks in order
            self.logger.info("Verifying attachments...")
            attachment_results = self._verify_attachments(tree)
            results['attachment_verification'] = attachment_results
            
            if self.compute_checksums:
                self.logger.info("Computing page checksums...")
                checksum_results = self._verify_page_checksums(tree)
                results['checksum_verification'] = checksum_results
            
            self.logger.info("Verifying hierarchy integrity...")
            hierarchy_results = self._verify_hierarchy_integrity(tree)
            results['hierarchy_verification'] = hierarchy_results
            
            if self.verification_depth in ['standard', 'full']:
                self.logger.info("Verifying link references...")
                link_results = self._verify_link_references(tree)
                results['link_verification'] = link_results
            
            # Create backup if enabled
            if self.create_backup and not self.dry_run:
                self.logger.info("Creating local backup...")
                backup_results = self._create_backup(tree, self.backup_dir)
                results['backup_info'] = backup_results
            else:
                results['backup_info'] = {'enabled': False}
            
            # Generate final report
            report = self._generate_verification_report(results)
            results.update(report)
            
            verification_duration = time.time() - start_time
            results['verification_duration'] = verification_duration
            
            self.logger.info(
                f"Integrity verification complete: score {report['summary']['integrity_score']:.1%}, "
                f"{report['summary']['total_issues']} issues found in {verification_duration:.2f}s"
            )
            
            # Save/print report based on configured formats
            if not self.dry_run:
                for fmt in self.report_formats:
                    if fmt == 'json' and self.save_report:
                        self._save_report_to_file(results)
                    elif fmt == 'csv':
                        self._export_csv_report(results, self.backup_dir / 'integrity_issues.csv')
                    elif fmt == 'console':
                        self._print_console_summary(results)
            
            return results
            
        except Exception as e:
            self.logger.error(f"Integrity verification failed: {str(e)}", exc_info=True)
            return {
                'failed': True,
                'error': str(e),
                'summary': {
                    'integrity_score': 0.0,
                    'total_issues': -1
                }
            }
    
    def _verify_attachments(self, tree: DocumentationTree) -> Dict[str, Any]:
        """Cross-check attachment references against downloaded files.
        
        Args:
            tree: DocumentationTree to verify
            
        Returns:
            Dictionary with attachment verification statistics
        """
        stats = {
            'total_refs': 0,
            'found': 0,
            'missing': 0,
            'checksum_mismatches': 0,
            'missing_details': [],
            'checksum_mismatch_details': []
        }
        
        try:
            all_pages = list(tree.get_all_pages())
            self.logger.info(f"Verifying attachments for {len(all_pages)} pages")
            
            for page in all_pages:
                if not page.content:
                    continue
                
                try:
                    soup = BeautifulSoup(page.content, 'html.parser')
                    
                    # Find img tags
                    img_tags = soup.find_all('img')
                    # Find a tags with common attachment file extensions
                    attachment_links = []
                    for a in soup.find_all('a', href=True):
                        href = a['href'].lower()
                        if any(ext in href for ext in ['.pdf', '.zip', '.doc', '.xls', '.ppt', '.txt']):
                            attachment_links.append(a)
                    
                    all_refs = img_tags + attachment_links
                    stats['total_refs'] += len(all_refs)
                    
                    # Check each reference
                    for ref in all_refs:
                        ref_url = ref.get('src', '') or ref.get('href', '')
                        
                        # Look for matching attachment in page.attachments
                        found = False
                        for attachment in page.attachments:
                            if attachment.download_url and attachment.download_url in ref_url:
                                found = True
                                stats['found'] += 1
                                
                                # Verify file exists and compute/check checksum
                                if attachment.local_path:
                                    if self._check_file_exists(Path(attachment.local_path)):
                                        if self.compute_checksums:
                                            computed_checksum = self._compute_checksum_from_file(Path(attachment.local_path))
                                            if attachment.content_checksum:
                                                # Check for mismatch
                                                if attachment.content_checksum != computed_checksum:
                                                    stats['checksum_mismatches'] += 1
                                                    stats['checksum_mismatch_details'].append({
                                                        'page_id': page.id,
                                                        'page_title': page.title,
                                                        'attachment_id': attachment.id,
                                                        'attachment_title': attachment.title,
                                                        'reason': f'Checksum mismatch: stored={attachment.content_checksum[:16]}..., computed={computed_checksum[:16]}...'
                                                    })
                                            else:
                                                # No existing checksum, set it
                                                attachment.content_checksum = computed_checksum
                                    else:
                                        stats['missing'] += 1
                                        stats['missing_details'].append({
                                            'page_id': page.id,
                                            'page_title': page.title,
                                            'attachment_url': ref_url,
                                            'attachment_title': attachment.title if attachment.title else 'Unknown',
                                            'reason': 'File not found on disk'
                                        })
                                else:
                                    stats['missing'] += 1
                                    stats['missing_details'].append({
                                        'page_id': page.id,
                                        'page_title': page.title,
                                        'attachment_url': ref_url,
                                        'attachment_title': attachment.title if attachment.title else 'Unknown',
                                        'reason': 'No local_path set'
                                    })
                                break
                        
                        if not found:
                            stats['missing'] += 1
                            stats['missing_details'].append({
                                'page_id': page.id,
                                'page_title': page.title,
                                'attachment_url': ref_url,
                                'attachment_title': 'Unknown',
                                'reason': 'No matching attachment in page.attachments'
                            })
                except Exception as e:
                    self.logger.warning(f"Failed to parse links for page {page.id}: {str(e)}")
                    continue
                
                # Update per-page attachment verification metadata
                page_total = len(all_refs)
                page_found = sum(1 for att in page.attachments if att.local_path and self._check_file_exists(Path(att.local_path)))
                page_missing = page_total - page_found
                
                # Get existing attachment verification dict or create new one
                if 'attachment_verification' not in page.conversion_metadata:
                    page.conversion_metadata['attachment_verification'] = {}
                
                page.conversion_metadata['attachment_verification'].update({
                    'total_refs': page_total,
                    'found': page_found,
                    'missing': page_missing
                })
                
                # Add missing details filtered to this page
                page_missing_details = [
                    detail for detail in stats['missing_details']
                    if detail['page_id'] == page.id
                ]
                page.conversion_metadata['attachment_verification']['missing_details'] = page_missing_details
                continue
            
            self.logger.info(
                f"Attachment verification: {stats['found']}/{stats['total_refs']} found, "
                f"{stats['missing']} missing"
            )
            
        except Exception as e:
            self.logger.error(f"Attachment verification failed: {str(e)}", exc_info=True)
            stats['error'] = str(e)
        
        return stats
    
    def _verify_page_checksums(self, tree: DocumentationTree) -> Dict[str, Any]:
        """Compute and store SHA256 checksums for page content.
        
        Args:
            tree: DocumentationTree to verify
            
        Returns:
            Dictionary with checksum verification statistics
        """
        stats = {
            'pages_processed': 0,
            'checksums_computed': 0,
            'checksum_mismatches': 0,
            'mismatch_details': [],
            'errors': 0
        }
        
        try:
            all_pages = list(tree.get_all_pages())
            self.logger.info(f"Computing checksums for {len(all_pages)} pages")
            
            # Use ThreadPoolExecutor for parallel checksum computation
            if self.checksum_workers > 1 and len(all_pages) > 10:
                with ThreadPoolExecutor(max_workers=self.checksum_workers) as executor:
                    future_to_page = {
                        executor.submit(self._compute_page_checksum, page): page 
                        for page in all_pages
                    }
                    
                    for future in as_completed(future_to_page):
                        page = future_to_page[future]
                        try:
                            result = future.result()
                            stats['pages_processed'] += 1
                            stats['checksums_computed'] += 1
                            # Count mismatches
                            if result['mismatches']:
                                stats['checksum_mismatches'] += len(result['mismatches'])
                                stats['mismatch_details'].extend(result['mismatches'])
                                # Update page integrity status
                                page.integrity_status = 'partial' if hasattr(page, 'integrity_status') else None
                        except Exception as e:
                            self.logger.warning(f"Failed to compute checksum for page {page.id}: {str(e)}")
                            stats['errors'] += 1
            else:
                # Synchronous computation
                for page in all_pages:
                    try:
                        result = self._compute_page_checksum(page)
                        stats['pages_processed'] += 1
                        stats['checksums_computed'] += 1
                        # Count mismatches
                        if result['mismatches']:
                            stats['checksum_mismatches'] += len(result['mismatches'])
                            stats['mismatch_details'].extend(result['mismatches'])
                            # Update page integrity status
                            page.integrity_status = 'partial' if hasattr(page, 'integrity_status') else None
                    except Exception as e:
                        self.logger.warning(f"Failed to compute checksum for page {page.id}: {str(e)}")
                        stats['errors'] += 1
            
            self.logger.info(f"Checksum verification: {stats['checksums_computed']} checksums computed, {stats['errors']} errors")
            
        except Exception as e:
            self.logger.error(f"Checksum verification failed: {str(e)}", exc_info=True)
            stats['error'] = str(e)
        
        return stats
    
    def _verify_hierarchy_integrity(self, tree: DocumentationTree) -> Dict[str, Any]:
        """Validate tree hierarchy integrity (orphans, cycles, duplicates).
        
        Args:
            tree: DocumentationTree to verify
            
        Returns:
            Dictionary with hierarchy verification statistics
        """
        stats = {
            'total_pages': 0,
            'orphans': 0,
            'circular_refs': 0,
            'invalid_spaces': 0,
            'duplicates': 0,
            'orphan_details': [],
            'circular_ref_details': [],
            'duplicate_details': []
        }
        
        try:
            all_pages = list(tree.get_all_pages())
            stats['total_pages'] = len(all_pages)
            
            # Build ID map for quick lookup
            page_id_map = {page.id: page for page in all_pages}
            visited = set()
            
            # Check for orphans
            for page in all_pages:
                if page.parent_id and page.parent_id not in page_id_map:
                    stats['orphans'] += 1
                    stats['orphan_details'].append({
                        'page_id': page.id,
                        'page_title': page.title,
                        'parent_id': page.parent_id,
                        'issue': 'Parent page not found in tree'
                    })
            
            # Check for circular references
            for page in all_pages:
                if page.id not in visited:
                    cycle = self._detect_circular_reference(page, page_id_map, set())
                    if cycle:
                        stats['circular_refs'] += 1
                        stats['circular_ref_details'].append({
                            'cycle_path': cycle,
                            'issue': f'Circular reference detected: {" -> ".join(cycle)}'
                        })
                visited.add(page.id)
            
            # Check for duplicate page IDs
            page_ids = [page.id for page in all_pages]
            seen = set()
            for page_id in page_ids:
                if page_id in seen:
                    stats['duplicates'] += 1
                    stats['duplicate_details'].append({
                        'page_id': page_id,
                        'issue': 'Duplicate page ID found'
                    })
                seen.add(page_id)
            
            # Validate space assignments
            valid_spaces = {space.key for space in tree.spaces}
            for page in all_pages:
                if page.space_key not in valid_spaces:
                    stats['invalid_spaces'] += 1
            
            self.logger.info(
                f"Hierarchy verification: {stats['total_pages']} pages checked, "
                f"{stats['orphans']} orphans, {stats['circular_refs']} cycles"
            )
            
        except Exception as e:
            self.logger.error(f"Hierarchy verification failed: {str(e)}", exc_info=True)
            stats['error'] = str(e)
        
        return stats
    
    def _verify_link_references(self, tree: DocumentationTree) -> Dict[str, Any]:
        """Validate internal and external link references.
        
        Args:
            tree: DocumentationTree to verify
            
        Returns:
            Dictionary with link verification statistics
        """
        stats = {
            'total_links': 0,
            'internal_valid': 0,
            'internal_broken': 0,
            'external_valid': 0,
            'external_broken': 0,
            'attachment_valid': 0,
            'attachment_missing': 0,
            'broken_link_details': []
        }
        
        try:
            all_pages = list(tree.get_all_pages())
            page_id_map = {page.id: page for page in all_pages}
            
            self.logger.info(f"Verifying links for {len(all_pages)} pages")
            
            for page in all_pages:
                if not page.content:
                    continue
                
                try:
                    soup = BeautifulSoup(page.content, 'html.parser')
                    
                    # Extract links using LinkProcessor
                    links = self.link_processor.extract_links(soup)
                    images = self.link_processor.extract_images(soup)
                    all_refs = links + images
                    
                    stats['total_links'] += len(all_refs)
                    
                    # Verify each link
                    for link in all_refs:
                        link_url = link['url']
                        link_type = link['type']  # e.g., 'attachment', 'page', 'external'
                        
                        if link_type == 'page' and 'page_id' in link:
                            target_page_id = link['page_id']
                            if target_page_id in page_id_map:
                                stats['internal_valid'] += 1
                            else:
                                stats['internal_broken'] += 1
                                stats['broken_link_details'].append({
                                    'page_id': page.id,
                                    'page_title': page.title,
                                    'link_url': link_url,
                                    'link_type': link_type,
                                    'reason': 'Target page not found in tree'
                                })
                        
                        elif link_type == 'attachment':
                            # Check if attachment exists in page
                            found = any(att.download_url and att.download_url in link_url 
                                      for att in page.attachments)
                            if found:
                                stats['attachment_valid'] += 1
                            else:
                                stats['attachment_missing'] += 1
                                stats['broken_link_details'].append({
                                    'page_id': page.id,
                                    'page_title': page.title,
                                    'link_url': link_url,
                                    'link_type': link_type,
                                    'reason': 'Attachment not found'
                                })
                        
                        elif self.verify_external_links and link_type == 'external':
                            # External link validation (optional, slower)
                            try:
                                # Use HEAD request with timeout to minimize data transfer
                                response = requests.head(link_url, timeout=10, allow_redirects=True)
                                if response.status_code < 400:
                                    stats['external_valid'] += 1
                                else:
                                    stats['external_broken'] += 1
                                    stats['broken_link_details'].append({
                                        'page_id': page.id,
                                        'page_title': page.title,
                                        'link_url': link_url,
                                        'link_type': link_type,
                                        'reason': f'HTTP {response.status_code}'
                                    })
                            except Exception as e:
                                # Treat any exception (timeout, connection error, etc.) as broken
                                stats['external_broken'] += 1
                                stats['broken_link_details'].append({
                                    'page_id': page.id,
                                    'page_title': page.title,
                                    'link_url': link_url,
                                    'link_type': link_type,
                                    'reason': f'Error: {str(e)}'
                                })
                        else:
                            # Other link types (external without verification enabled)
                            if link_type == 'external':
                                stats['external_valid'] += 1
                
                except Exception as e:
                    self.logger.warning(f"Failed to parse links for page {page.id}: {str(e)}")
                    continue
            
                
                # Update per-page link verification metadata
                page_broken_links = [
                detail for detail in stats["broken_link_details"]
                if detail["page_id"] == page.id
                ]
                    
                # Get existing link verification dict or create new one
                if "link_verification" not in page.conversion_metadata:
                    page.conversion_metadata["link_verification"] = {}
                    
                page.conversion_metadata["link_verification"].update({
                "total_links": len(all_refs),
                "internal_links_valid": sum(1 for link in all_refs if link["type"] == "page"),
                "internal_links_broken": sum(1 for detail in page_broken_links if detail["link_type"] == "page"),
                "external_links_valid": stats["external_valid"],
                "external_links_broken": stats["external_broken"],
                "attachment_links_valid": stats["attachment_valid"],
                "attachment_links_broken": stats["attachment_missing"],
                "broken_link_details": page_broken_links
                })
                self.logger.info(
                f"Link verification: {stats['total_links']} total, "
                f"{stats['internal_broken']} broken internal, {stats['attachment_missing']} missing attachments"
                )
            
        except Exception as e:
            self.logger.error(f"Link verification failed: {str(e)}", exc_info=True)
            stats['error'] = str(e)
        
        return stats
    
    def _create_backup(self, tree: DocumentationTree, backup_dir: Path) -> Dict[str, Any]:
        """Create complete local backup of fetched content.
        
        Args:
            tree: DocumentationTree to backup
            backup_dir: Directory path for backup
            
        Returns:
            Dictionary with backup statistics
        """
        stats = {
            'enabled': True,
            'files_saved': 0,
            'total_size_bytes': 0,
            'backup_path': str(backup_dir),
            'errors': 0
        }
        
        try:
            start_time = time.time()
            
            # Create backup directory structure
            backup_dir.mkdir(parents=True, exist_ok=True)
            
            all_pages = list(tree.get_all_pages())
            
            for page in all_pages:
                try:
                    space_dir = backup_dir / page.space_key
                    space_dir.mkdir(exist_ok=True)
                    
                    raw_dir = space_dir / 'raw'
                    raw_dir.mkdir(exist_ok=True)
                    
                    metadata_dir = space_dir / 'metadata'
                    metadata_dir.mkdir(exist_ok=True)
                    
                    attachments_dir = space_dir / 'attachments'
                    attachments_dir.mkdir(exist_ok=True)
                    
                    # Save raw HTML content
                    if page.content:
                        html_file = raw_dir / f"{page.id}.html"
                        html_file.write_text(page.content, encoding='utf-8')
                        stats['files_saved'] += 1
                        stats['total_size_bytes'] += html_file.stat().st_size
                    
                    # Save page metadata
                    metadata_file = metadata_dir / f"{page.id}.json"
                    page_dict = page.to_dict()
                    metadata_file.write_text(json.dumps(page_dict, indent=2), encoding='utf-8')
                    stats['files_saved'] += 1
                    stats['total_size_bytes'] += metadata_file.stat().st_size
                    
                    # Copy attachments
                    for attachment in page.attachments:
                        if attachment.local_path and Path(attachment.local_path).exists():
                            src_path = Path(attachment.local_path)
                            dst_path = attachments_dir / f"{attachment.id}_{src_path.name}"
                            
                            if not dst_path.exists():
                                dst_path.write_bytes(src_path.read_bytes())
                                stats['files_saved'] += 1
                                stats['total_size_bytes'] += dst_path.stat().st_size
                
                except Exception as e:
                    self.logger.warning(f"Failed to backup page {page.id}: {str(e)}")
                    stats['errors'] += 1
                    continue
            
            # Save tree metadata
            tree_metadata_file = backup_dir / 'tree_metadata.json'
            tree_metadata = {
                'fetch_timestamp': time.time(),
                'filters': self.config.get('filters', {}),
                'statistics': tree.get_statistics(),
                'spaces': [space.to_dict() for space in tree.spaces]
            }
            tree_metadata_file.write_text(json.dumps(tree_metadata, indent=2), encoding="utf-8")
            stats['files_saved'] += 1
            stats['total_size_bytes'] += tree_metadata_file.stat().st_size
            
            # Set backup path in tree metadata
            tree.metadata['backup_path'] = str(backup_dir)
            
            backup_duration = time.time() - start_time
            stats['backup_duration'] = backup_duration
            
            self.logger.info(
                f"Backup complete: {stats['files_saved']} files, "
                f"{stats['total_size_bytes'] / 1024 / 1024:.2f} MB in {backup_duration:.2f}s"
            )
            
        except Exception as e:
            self.logger.error(f"Backup creation failed: {str(e)}", exc_info=True)
            stats['error'] = str(e)
        
        return stats
    
    def _generate_verification_report(self, results: Dict[str, Any]) -> Dict[str, Any]:
        """Generate comprehensive verification report.
        
        Args:
            results: Results from all verification methods
            
        Returns:
            Dictionary with report summary and recommendations
        """
        summary = {
            'integrity_score': 0.0,
            'total_issues': 0,
            'checks_performed': 0,
            'checks_passed': 0
        }
        
        issues = []
        recommendations = []
        
        try:
            # Calculate score based on attachment verification
            attachment_results = results.get('attachment_verification', {})
            if attachment_results:
                summary['checks_performed'] += 1
                total_refs = attachment_results.get('total_refs', 0)
                missing = attachment_results.get('missing', 0)
                
                if total_refs > 0:
                    attachment_score = (total_refs - missing) / total_refs
                    summary['integrity_score'] += attachment_score
                    summary['total_issues'] += missing
                    
                    if missing > 0:
                        issues.append(f"{missing} missing attachments")
                        recommendations.append(
                            "Re-run fetch with attachment download enabled or "
                            "check Confluence permissions for missing files"
                        )
                    else:
                        summary['checks_passed'] += 1
            
            # Calculate score based on hierarchy verification
            hierarchy_results = results.get('hierarchy_verification', {})
            if hierarchy_results:
                summary['checks_performed'] += 1
                total_pages = hierarchy_results.get('total_pages', 0)
                orphans = hierarchy_results.get('orphans', 0)
                circular_refs = hierarchy_results.get('circular_refs', 0)
                
                if total_pages > 0:
                    hierarchy_issues = orphans + circular_refs
                    hierarchy_score = (total_pages - hierarchy_issues) / total_pages
                    summary['integrity_score'] += hierarchy_score
                    summary['total_issues'] += hierarchy_issues
                    
                    if orphans > 0:
                        issues.append(f"{orphans} orphan pages")
                        recommendations.append(
                            "Verify parent pages exist or set parent_id to None for top-level pages"
                        )
                    
                    if circular_refs > 0:
                        issues.append(f"{circular_refs} circular references")
                        recommendations.append(
                            "Review circular reference paths and fix parent-child relationships"
                        )
                    
                    if orphans == 0 and circular_refs == 0:
                        summary['checks_passed'] += 1
            
            # Calculate score based on link verification
            link_results = results.get('link_verification', {})
            if link_results and self.verification_depth in ['standard', 'full']:
                summary['checks_performed'] += 1
                total_links = link_results.get('total_links', 0)
                internal_broken = link_results.get('internal_broken', 0)
                attachment_missing = link_results.get('attachment_missing', 0)
                
                if total_links > 0:
                    link_issues = internal_broken + attachment_missing
                    link_score = (total_links - link_issues) / total_links
                    summary['integrity_score'] += link_score
                    summary['total_issues'] += link_issues
                    
                    if internal_broken > 0:
                        issues.append(f"{internal_broken} broken internal links")
                        recommendations.append(
                            "Update links to valid page IDs or remove broken references"
                        )
                    
                    if attachment_missing > 0:
                        issues.append(f"{attachment_missing} missing attachment links")
                        recommendations.append(
                            "Download missing attachments or update link references"
                        )
                    
                    if internal_broken == 0 and attachment_missing == 0:
                        summary['checks_passed'] += 1
            
            # Calculate score based on checksum verification
            checksum_results = results.get('checksum_verification', {})
            if checksum_results.get('checksums_computed', 0) > 0:
                summary['checks_performed'] += 1
                checksum_mismatches = checksum_results.get('checksum_mismatches', 0)
                pages_computed = checksum_results.get('checksums_computed', 0)
                
                # Checksum score: pages without mismatches / total pages processed
                if pages_computed > 0:
                    checksum_score = (pages_computed - checksum_mismatches) / pages_computed
                    summary['integrity_score'] += checksum_score
                    summary['total_issues'] += checksum_mismatches
                    
                    if checksum_mismatches > 0:
                        issues.append(f"{checksum_mismatches} page checksum mismatches")
                        recommendations.append(
                            "Re-fetch affected pages or verify conversion integrity; "
                            "check `mismatch_details` for specifics"
                        )
                    else:
                        summary['checks_passed'] += 1
            
            # Normalize final score
            if summary['checks_performed'] > 0:
                summary['integrity_score'] = summary['integrity_score'] / summary['checks_performed']
            
            # Deduplicate recommendations
            recommendations = list(dict.fromkeys(recommendations))
            
        except Exception as e:
            self.logger.error(f"Report generation failed: {str(e)}", exc_info=True)
            summary['error'] = str(e)
        
        return {
            'summary': summary,
            'issues': issues,
            'recommendations': recommendations
        }
    
    def _save_report_to_file(self, report: Dict[str, Any]) -> None:
        """Save verification report to file.
        
        Args:
            report: Verification report dictionary
        """
        try:
            if not self.backup_dir.exists():
                self.backup_dir.mkdir(parents=True, exist_ok=True)
            
            report_file = self.backup_dir / 'integrity_report.json'
            report_file.write_text(json.dumps(report, indent=2), encoding='utf-8')
            self.logger.info(f"Verification report saved to {report_file}")
            
        except Exception as e:
            self.logger.warning(f"Failed to save verification report: {str(e)}")
    
    def _compute_page_checksum(self, page: ConfluencePage) -> Dict[str, Any]:
        """Compute checksums for page content and detect mismatches.
        
        Args:
            page: ConfluencePage to compute checksums for
            
        Returns:
            Dictionary with mismatch information
        """
        mismatches = []
        
        if page.content:
            new_checksum = self._compute_checksum(page.content)
            existing = page.metadata.get('content_checksum') if page.metadata else None
            
            if existing and existing != new_checksum:
                # Record checksum mismatch
                mismatches.append({
                    'page_id': page.id,
                    'page_title': page.title,
                    'type': 'html',
                    'old_checksum': existing,
                    'new_checksum': new_checksum,
                    'reason': 'Content changed since last computation'
                })
                # Also store in page metadata for debugging
                if 'checksum_mismatch' not in page.metadata:
                    page.metadata['checksum_mismatch'] = []
                page.metadata['checksum_mismatch'].append({
                    'type': 'html',
                    'old': existing,
                    'new': new_checksum
                })
            else:
                # No mismatch or first time computing - set the checksum
                if page.metadata is None:
                    page.metadata = {}
                page.metadata['content_checksum'] = new_checksum
        
        # Check markdown checksum if available
        if hasattr(page, 'markdown_content') and page.markdown_content:
            if page.conversion_metadata is None:
                page.conversion_metadata = {}
            
            new_markdown_checksum = self._compute_checksum(page.markdown_content)
            existing_markdown = page.conversion_metadata.get('markdown_checksum')
            
            if existing_markdown and existing_markdown != new_markdown_checksum:
                mismatches.append({
                    'page_id': page.id,
                    'page_title': page.title,
                    'type': 'markdown',
                    'old_checksum': existing_markdown,
                    'new_checksum': new_markdown_checksum,
                    'reason': 'Markdown content changed since last computation'
                })
                if 'checksum_mismatch' not in page.conversion_metadata:
                    page.conversion_metadata['checksum_mismatch'] = []
                page.conversion_metadata['checksum_mismatch'].append({
                    'type': 'markdown',
                    'old': existing_markdown,
                    'new': new_markdown_checksum
                })
            else:
                page.conversion_metadata['markdown_checksum'] = new_markdown_checksum
        
        return {
            'mismatches': mismatches,
            'computed': True
        }
    
    def _compute_checksum(self, content: Union[str, bytes]) -> str:
        """Compute SHA256 checksum for content.
        
        Args:
            content: String or bytes to checksum
            
        Returns:
            Hex digest of SHA256 hash
        """
        if isinstance(content, str):
            content = content.encode('utf-8')
        
        return hashlib.sha256(content).hexdigest()
    
    def _compute_checksum_from_file(self, file_path: Path) -> str:
        """Compute SHA256 checksum from file.
        
        Args:
            file_path: Path to file
            
        Returns:
            Hex digest of SHA256 hash
        """
        hash_sha256 = hashlib.sha256()
        with open(file_path, 'rb') as f:
            for chunk in iter(lambda: f.read(4096), b""):
                hash_sha256.update(chunk)
        return hash_sha256.hexdigest()
    
    def _check_file_exists(self, path: Path) -> bool:
        """Check if file exists and is readable.
        
        Args:
            path: Path to check
            
        Returns:
            True if file exists and is readable
        """
        try:
            return path.exists() and path.is_file()
        except Exception:
            return False
    
    def _print_console_summary(self, results: Dict[str, Any]) -> None:
        """Print verification summary to console.
        
        Args:
            results: Verification results dictionary
        """
        try:
            summary = results.get('summary', {})
            print("\n" + "=" * 60)
            print("INTEGRITY VERIFICATION SUMMARY")
            print("=" * 60)
            print(f"Integrity Score: {summary.get('integrity_score', 0):.1%}")
            print(f"Total Issues: {summary.get('total_issues', 0)}")
            print(f"Checks Performed: {summary.get('checks_performed', 0)}")
            
            # Show issues by category
            for issue in summary.get('issues', []):
                print(f"  • {issue}")
            
            if summary.get('recommendations'):
                print("\nTop Recommendations:")
                for i, rec in enumerate(summary['recommendations'][:3], 1):
                    print(f"  {i}. {rec}")
            
            print("=" * 60)
            
        except Exception as e:
            self.logger.warning(f"Failed to print console summary: {str(e)}")
    
    def _export_csv_report(self, results: Dict[str, Any], filepath: Path) -> None:
        """Export verification issues to CSV file.
        
        Args:
            results: Verification results dictionary
            filepath: Output CSV file path
        """
        try:
            import csv
            
            issues = []
            
            # Collect attachment missing details
            att_results = results.get('attachment_verification', {})
            for detail in att_results.get('missing_details', []):
                issues.append({
                    'issue_type': 'missing_attachment',
                    'page_id': detail.get('page_id', ''),
                    'page_title': detail.get('page_title', ''),
                    'description': f"Missing attachment: {detail.get('attachment_title', '')}",
                    'severity': 'high',
                    'recommendation': 'Re-run fetch with attachment download enabled or check Confluence permissions'
                })
            
            # Collect checksum mismatch details
            for detail in results.get('checksum_verification', {}).get('mismatch_details', []):
                issues.append({
                    'issue_type': 'checksum_mismatch',
                    'page_id': detail.get('page_id', ''),
                    'page_title': detail.get('page_title', ''),
                    'description': f"Checksum mismatch ({detail.get('type', '')}): {detail.get('old_checksum', '')[:16]}... vs {detail.get('new_checksum', '')[:16]}...",
                    'severity': 'medium',
                    'recommendation': 'Re-fetch affected pages or verify conversion integrity'
                })
            
            # Collect hierarchy issues
            hier_results = results.get('hierarchy_verification', {})
            for detail in hier_results.get('orphan_details', []):
                issues.append({
                    'issue_type': 'orphan_page',
                    'page_id': detail.get('page_id', ''),
                    'page_title': detail.get('page_title', ''),
                    'description': detail.get('issue', ''),
                    'severity': 'medium',
                    'recommendation': 'Verify parent page exists or set parent_id to None'
                })
            
            # Collect link issues
            link_results = results.get('link_verification', {})
            for detail in link_results.get('broken_link_details', []):
                severity = 'medium'
                if detail.get('link_type') == 'attachment':
                    severity = 'high'
                
                issues.append({
                    'issue_type': 'broken_link',
                    'page_id': detail.get('page_id', ''),
                    'page_title': detail.get('page_title', ''),
                    'description': f"Broken {detail.get('link_type', 'link')}: {detail.get('link_url', '')[:100]}",
                    'severity': severity,
                    'recommendation': 'Update link to valid page ID or remove broken reference'
                })
            
            # Write CSV if there are issues
            if issues:
                with open(filepath, 'w', newline='', encoding='utf-8') as f:
                    writer = csv.DictWriter(f, fieldnames=[
                        'issue_type', 'page_id', 'page_title', 'description',
                        'severity', 'recommendation'
                    ])
                    writer.writeheader()
                    writer.writerows(issues)
                
                self.logger.info(f"Verification issues CSV exported to {filepath}")
            
        except Exception as e:
            self.logger.warning(f"Failed to export CSV report: {str(e)}")
    def _detect_circular_reference(self, page: ConfluencePage, page_id_map: Dict[str, ConfluencePage], 
                                  visited: Set[str]) -> Optional[List[str]]:
        """Detect circular references in page hierarchy.
        
        Args:
            page: Starting page
            page_id_map: Map of page ID to ConfluencePage
            visited: Set of visited page IDs
            
        Returns:
            List of page IDs forming a cycle, or None if no cycle
        """
        if page.id in visited:
            return list(visited) + [page.id]
        
        if not page.parent_id:
            return None
        
        if page.parent_id not in page_id_map:
            return None
        
        visited.add(page.id)
        parent = page_id_map[page.parent_id]
        result = self._detect_circular_reference(parent, page_id_map, visited.copy())
        return result