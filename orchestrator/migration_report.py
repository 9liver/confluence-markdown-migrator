"""
Migration report generator for aggregating statistics and formatting reports.

This module generates comprehensive migration reports from phase statistics,
formatting them for console display, JSON export, and CSV export.
"""

import logging
import json
import csv
from typing import Dict, List, Any, Union, Optional
from datetime import datetime

from models import DocumentationTree, ConfluenceSpace, ConfluencePage

logger = logging.getLogger(__name__)


class MigrationReport:
    """Generates comprehensive migration reports aggregating statistics from all phases."""
    
    def __init__(self, logger: Optional[logging.Logger] = None):
        """
        Initialize migration report generator.
        
        Args:
            logger: Optional logger instance
        """
        self.logger = logger or logging.getLogger(__name__)
    
    def generate_report(
        self,
        tree: DocumentationTree,
        phase_stats: Dict[str, Any],
        migration_duration: float,
        export_target: str,
        integrity_report: Optional[Dict[str, Any]] = None
    ) -> Dict[str, Any]:
        """
        Generate comprehensive migration report.
        
        Args:
            tree: DocumentationTree that was migrated
            phase_stats: Statistics from all phases
            migration_duration: Total migration duration in seconds
            export_target: Target export type
            
        Returns:
            Migration report dictionary
        """
        self.logger.info("Generating migration report")
        
        # Build report sections
        report = {
            'summary': self._build_summary(tree, phase_stats, migration_duration, export_target),
            'phases': self._build_phase_breakdown(phase_stats, export_target),
            'integrity_verification': self._build_integrity_verification(integrity_report or tree.integrity_report),
            'cache': self._build_cache_stats(tree),
            'errors': self._build_error_summary(phase_stats),
            'spaces': self._build_space_breakdown(tree),
            'export_target': export_target,
            'timestamp': datetime.now().isoformat()
        }
        
        self.logger.info(
            f"Report generated: {report['summary'].get('pages', 0)} pages, "
            f"{report['summary'].get('total_errors', 0)} errors"
        )
        
        return report
    
    def _build_summary(
        self,
        tree: DocumentationTree,
        phase_stats: Dict[str, Any],
        duration: float,
        export_target: str
    ) -> Dict[str, Any]:
        """Build high-level summary section."""
        summary = {
            'spaces': len(tree.spaces),
            'pages': tree.metadata.get('total_pages_fetched', 0),
            'attachments': tree.metadata.get('total_attachments_fetched', 0),
            'export_target': export_target,
            'duration_seconds': duration,
            'duration_formatted': self._format_duration(duration)
        }
        
        # Extract statistics based on export target
        if export_target == 'markdown_files':
            export_stats = phase_stats.get('markdown_export', {})
            summary['pages_exported'] = export_stats.get('pages_exported', 0)
            summary['attachments_downloaded'] = export_stats.get('attachments_downloaded', 0)
            
        elif export_target == 'wikijs':
            import_stats = phase_stats.get('wikijs_import', {})
            summary['created'] = import_stats.get('created', 0)
            summary['updated'] = import_stats.get('updated', 0)
            summary['skipped'] = import_stats.get('skipped', 0)
            summary['failed'] = import_stats.get('failed', 0)
            summary['attachments_uploaded'] = import_stats.get('attachments_uploaded', 0)
            
            # Include export stats if export-then-import workflow
            if 'markdown_export' in phase_stats:
                export_stats = phase_stats['markdown_export']
                summary['pages_exported'] = export_stats.get('pages_exported', 0)
                summary['files_created'] = True
            
        elif export_target == 'bookstack':
            import_stats = phase_stats.get('bookstack_import', {})
            summary['shelves'] = import_stats.get('shelves', 0)
            summary['books'] = import_stats.get('books', 0)
            summary['chapters'] = import_stats.get('chapters', 0)
            summary['pages_created'] = import_stats.get('pages', 0)
            summary['images_uploaded'] = import_stats.get('images_uploaded', 0)
            summary['skipped'] = import_stats.get('skipped', 0)
            summary['failed'] = import_stats.get('failed', 0)
            
        elif export_target == 'both_wikis':
            # Aggregate both wiki imports
            wikijs_stats = phase_stats.get('wikijs_import', {})
            bookstack_stats = phase_stats.get('bookstack_import', {})
            
            summary['wikijs'] = {
                'created': wikijs_stats.get('created', 0),
                'updated': wikijs_stats.get('updated', 0),
                'failed': wikijs_stats.get('failed', 0)
            }
            summary['bookstack'] = {
                'shelves': bookstack_stats.get('shelves', 0),
                'books': bookstack_stats.get('books', 0),
                'chapters': bookstack_stats.get('chapters', 0),
                'pages': bookstack_stats.get('pages', 0),
                'failed': bookstack_stats.get('failed', 0)
            }
            summary['total_attachments'] = (
                wikijs_stats.get('attachments_uploaded', 0) +
                bookstack_stats.get('images_uploaded', 0)
            )
        
        # Count total errors and warnings
        summary['total_errors'] = self._count_total_errors(phase_stats)
        summary['total_warnings'] = self._count_total_warnings(phase_stats)
        
        # Calculate success rate
        if summary['pages'] > 0:
            summary['success_rate'] = (summary['pages'] - summary['total_errors']) / summary['pages']
        else:
            summary['success_rate'] = 1.0
        
        # Add cache summary if available
        cache_stats = tree.metadata.get('cache_stats', {})
        if cache_stats.get('enabled'):
            summary['cache_enabled'] = True
            summary['cache_mode'] = cache_stats.get('mode')
            summary['cache_hit_rate'] = cache_stats.get('hit_rate', 0)
            if 'api_calls_made' in cache_stats:
                summary['api_calls_made'] = cache_stats['api_calls_made']
                summary['api_calls_saved'] = cache_stats.get('api_calls_saved', 0)
                summary['total_requests'] = cache_stats.get('total_requests', 0)
        
        # Add rollback summary if any phase executed rollback
        for phase_name, stats in phase_stats.items():
            if stats.get('rollback_executed'):
                if 'rollback_summary' not in summary:
                    summary['rollback_summary'] = {
                        'executed': True,
                        'entities_deleted': stats.get('rollback_deleted', 0)
                    }
        
        return summary
    
    def _build_integrity_verification(self, integrity_report: Optional[Dict[str, Any]]) -> Dict[str, Any]:
        """Build integrity verification section from report data.
        
        Args:
            integrity_report: Integrity verification report dictionary
            
        Returns:
            Dictionary with integrity verification statistics
        """
        if not integrity_report:
            return {
                'enabled': False,
                'message': 'Integrity verification was not performed'
            }
        
        if 'failed' in integrity_report:
            return {
                'enabled': True,
                'failed': integrity_report.get('failed', False),
                'error': integrity_report.get('error', 'Unknown error')
            }
        
        # Build comprehensive integrity section
        stats = {
            'enabled': True,
            'integrity_score': integrity_report.get('summary', {}).get('integrity_score', 0.0),
            'total_issues': integrity_report.get('summary', {}).get('total_issues', 0),
            'verification_depth': integrity_report.get('verification_depth', 'standard'),
            'verification_duration': integrity_report.get('verification_duration', 0.0)
        }
        
        # Add attachment verification
        attachment_results = integrity_report.get('attachment_verification', {})
        if attachment_results:
            stats['attachment_verification'] = {
                'total_refs': attachment_results.get('total_refs', 0),
                'found': attachment_results.get('found', 0),
                'missing': attachment_results.get('missing', 0),
                'checksum_mismatches': attachment_results.get('checksum_mismatches', 0),
                'missing_details': attachment_results.get('missing_details', [])
            }
        
        # Add hierarchy verification
        hierarchy_results = integrity_report.get('hierarchy_verification', {})
        if hierarchy_results:
            stats['hierarchy_verification'] = {
                'total_pages': hierarchy_results.get('total_pages', 0),
                'orphans': hierarchy_results.get('orphans', 0),
                'circular_refs': hierarchy_results.get('circular_refs', 0),
                'invalid_spaces': hierarchy_results.get('invalid_spaces', 0),
                'duplicates': hierarchy_results.get('duplicates', 0),
                'orphan_details': hierarchy_results.get('orphan_details', []),
                'circular_ref_details': hierarchy_results.get('circular_ref_details', [])
            }
        
        # Add link verification
        link_results = integrity_report.get('link_verification', {})
        if link_results:
            stats['link_verification'] = {
                'total_links': link_results.get('total_links', 0),
                'internal_valid': link_results.get('internal_valid', 0),
                'internal_broken': link_results.get('internal_broken', 0),
                'external_valid': link_results.get('external_valid', 0),
                'external_broken': link_results.get('external_broken', 0),
                'attachment_valid': link_results.get('attachment_valid', 0),
                'attachment_missing': link_results.get('attachment_missing', 0),
                'broken_link_details': link_results.get('broken_link_details', [])
            }
        
        # Add checksum verification
        checksum_results = integrity_report.get('checksum_verification', {})
        if checksum_results:
            stats['checksum_verification'] = {
                'pages_processed': checksum_results.get('pages_processed', 0),
                'checksums_computed': checksum_results.get('checksums_computed', 0),
                'checksum_mismatches': checksum_results.get('checksum_mismatches', 0),
                'errors': checksum_results.get('errors', 0)
            }
        
        # Add backup info
        backup_results = integrity_report.get('backup_info', {})
        if backup_results:
            stats['backup_info'] = {
                'enabled': backup_results.get('enabled', False),
                'files_saved': backup_results.get('files_saved', 0),
                'total_size_mb': backup_results.get('total_size_bytes', 0) / 1024 / 1024,
                'backup_path': backup_results.get('backup_path', ''),
                'backup_duration': backup_results.get('backup_duration', 0.0)
            }
        
        # Add recommendations
        stats['recommendations'] = integrity_report.get('recommendations', [])
        
        return stats

    def _build_phase_breakdown(self, phase_stats: Dict[str, Any], export_target: str) -> Dict[str, Any]:
        """Build detailed breakdown by phase."""
        breakdown = {}
        
        # Content conversion phase
        if 'content_conversion' in phase_stats:
            conv_stats = phase_stats['content_conversion']
            breakdown['content_conversion'] = {
                'pages_processed': conv_stats.get('pages_processed', 0),
                'pages_success': conv_stats.get('pages_success', 0),
                'pages_failed': conv_stats.get('pages_failed', 0),
                'pages_partial': conv_stats.get('pages_partial', 0),
                'errors': len(conv_stats.get('errors', []))
            }
        
        # Export/Import phase based on target
        if export_target == 'markdown_files' and 'markdown_export' in phase_stats:
            export_stats = phase_stats['markdown_export']
            breakdown['markdown_export'] = {
                'pages_exported': export_stats.get('pages_exported', 0),
                'attachments_downloaded': export_stats.get('attachments_downloaded', 0),
                'index_files_created': export_stats.get('index_files_created', 0),
                'failed': export_stats.get('failed', False),
                'errors': export_stats.get('errors', [])
            }
        
        elif export_target == 'wikijs' and 'wikijs_import' in phase_stats:
            import_stats = phase_stats['wikijs_import']
            breakdown['wikijs_import'] = {
                'created': import_stats.get('created', 0),
                'updated': import_stats.get('updated', 0),
                'skipped': import_stats.get('skipped', 0),
                'failed': import_stats.get('failed', 0),
                'attachments_uploaded': import_stats.get('attachments_uploaded', 0),
                'errors': import_stats.get('errors', [])
            }
        
        elif export_target == 'bookstack' and 'bookstack_import' in phase_stats:
            import_stats = phase_stats['bookstack_import']
            breakdown['bookstack_import'] = {
                'shelves': import_stats.get('shelves', 0),
                'books': import_stats.get('books', 0),
                'chapters': import_stats.get('chapters', 0),
                'pages': import_stats.get('pages', 0),
                'skipped': import_stats.get('skipped', 0),
                'failed': import_stats.get('failed', 0),
                'images_uploaded': import_stats.get('images_uploaded', 0),
                'errors': import_stats.get('errors', [])
            }
        
        elif export_target == 'both_wikis':
            # Include both imports
            if 'wikijs_import' in phase_stats:
                wj_stats = phase_stats['wikijs_import']
                breakdown['wikijs_import'] = {
                    'created': wj_stats.get('created', 0),
                    'updated': wj_stats.get('updated', 0),
                    'failed': wj_stats.get('failed', 0),
                    'errors': wj_stats.get('errors', [])
                }
            
            if 'bookstack_import' in phase_stats:
                bs_stats = phase_stats['bookstack_import']
                breakdown['bookstack_import'] = {
                    'shelves': bs_stats.get('shelves', 0),
                    'books': bs_stats.get('books', 0),
                    'chapters': bs_stats.get('chapters', 0),
                    'pages': bs_stats.get('pages', 0),
                    'failed': bs_stats.get('failed', 0),
                    'errors': bs_stats.get('errors', [])
                }
        
        return breakdown
    
    def _build_cache_stats(self, tree: DocumentationTree) -> Dict[str, Any]:
        """Build cache statistics section from tree metadata."""
        cache_stats = tree.metadata.get('cache_stats', {})
        
        if not cache_stats or not cache_stats.get('enabled'):
            return {'enabled': False}
        
        stats = {
            'enabled': True,
            'mode': cache_stats.get('mode', 'unknown'),
            'cache_dir': cache_stats.get('cache_dir'),
            'hits': cache_stats.get('hits', 0),
            'misses': cache_stats.get('misses', 0),
            'validations': cache_stats.get('validations', 0),
            'invalidations': cache_stats.get('invalidations', 0),
            'total_entries': cache_stats.get('total_entries', 0),
            'total_size_mb': cache_stats.get('total_size_mb', 0),
            'api_calls_made': cache_stats.get('api_calls_made', 0)
        }
        
        # Calculate derived metrics
        total_requests = stats['hits'] + stats['misses']
        if total_requests > 0:
            stats['hit_rate'] = stats['hits'] / total_requests
            stats['api_calls_saved'] = stats['hits']
        else:
            stats['hit_rate'] = 0.0
            stats['api_calls_saved'] = 0
        
        # Include total requests if available (for API mode)
        if 'total_requests' in cache_stats:
            stats['total_requests'] = cache_stats['total_requests']
        else:
            stats['total_requests'] = total_requests
        
        # Add savings rate for API mode
        if 'api_calls_made' in cache_stats and stats['total_requests'] > 0:
            stats['savings_rate'] = stats['api_calls_saved'] / stats['total_requests']
        else:
            stats['savings_rate'] = 0.0
        
        return stats
    
    def _build_error_summary(self, phase_stats: Dict[str, Any]) -> List[Dict[str, Any]]:
        """Aggregate errors from all phases."""
        all_errors = []
        
        for phase_name, stats in phase_stats.items():
            errors = stats.get('errors', [])
            for error in errors:
                error_copy = error.copy()
                error_copy['phase'] = phase_name
                all_errors.append(error_copy)
        
        return all_errors
    
    def _build_space_breakdown(self, tree: DocumentationTree) -> List[Dict[str, Any]]:
        """Build per-space statistics."""
        space_breakdown = []
        
        for space_key, space in sorted(tree.spaces.items()):
            all_pages = self._get_all_pages(space.pages)
            
            # Count pages by status
            total_pages = len(all_pages)
            converted_pages = sum(
                1 for page in all_pages
                if page.conversion_metadata.get('conversion_status') == 'success'
            )
            failed_pages = sum(
                1 for page in all_pages
                if page.conversion_metadata.get('conversion_status') == 'failed'
            )
            
            # Count attachments
            attachment_count = sum(len(page.attachments) for page in all_pages)
            
            space_breakdown.append({
                'key': space_key,
                'name': space.name,
                'pages_total': total_pages,
                'pages_converted': converted_pages,
                'pages_failed': failed_pages,
                'attachments': attachment_count
            })
        
        return space_breakdown
    
    def _get_all_pages(self, pages) -> list:
        """Recursively get all pages including children."""
        all_pages = []
        
        def collect(pages_list):
            for page in pages_list:
                all_pages.append(page)
                if page.children:
                    collect(page.children)
        
        collect(pages)
        return all_pages
    
    def _format_duration(self, seconds: float) -> str:
        """Format duration in human-readable format."""
        if seconds < 60:
            return f"{seconds:.1f}s"
        elif seconds < 3600:
            minutes = int(seconds // 60)
            secs = int(seconds % 60)
            return f"{minutes}m {secs}s"
        else:
            hours = int(seconds // 3600)
            minutes = int((seconds % 3600) // 60)
            secs = int(seconds % 60)
            return f"{hours}h {minutes}m {secs}s"
    
    def _count_total_errors(self, phase_stats: Dict[str, Any]) -> int:
        """Count total errors across all phases, avoiding double-counting."""
        total_errors = 0
        for stats in phase_stats.values():
            # Prefer 'errors' list when available (detailed errors)
            if 'errors' in stats and isinstance(stats['errors'], list):
                total_errors += len(stats['errors'])
            # Fall back to 'failed' counter if no detailed errors
            elif 'failed' in stats:
                if isinstance(stats['failed'], int):
                    total_errors += stats['failed']
                elif stats['failed'] is True:
                    total_errors += 1
        return total_errors
    
    def _count_total_warnings(self, phase_stats: Dict[str, Any]) -> int:
        """Count total warnings across all phases."""
        total_warnings = 0
        for stats in phase_stats.values():
            # Check for warning-related fields
            if 'warnings' in stats:
                total_warnings += len(stats['warnings'])
            if 'pages_partial' in stats:
                total_warnings += stats['pages_partial']
        return total_warnings
    
    def format_console_report(self, report: Dict[str, Any]) -> str:
        """
        Format report for console display.
        
        Args:
            report: Migration report dictionary
            
        Returns:
            Formatted console string
        """
        sections = []
        
        # Header
        sections.append("=" * 60)
        sections.append("MIGRATION REPORT")
        sections.append("=" * 60)
        sections.append("")
        
        # Summary section
        summary = report.get('summary', {})
        sections.append("Summary:")
        sections.append(f"  Spaces:      {summary.get('spaces', 0)}")
        sections.append(f"  Pages:       {summary.get('pages', 0)}")
        sections.append(f"  Attachments: {summary.get('attachments', 0)}")
        sections.append(f"  Export:      {summary.get('export_target', 'unknown')}")
        sections.append(f"  Duration:    {summary.get('duration_formatted', '0s')}")
        
        if 'success_rate' in summary:
            success_rate = summary['success_rate'] * 100
            sections.append(f"  Success:     {success_rate:.1f}%")
        
        if summary.get('total_warnings', 0) > 0:
            sections.append(f"  Warnings:    {summary['total_warnings']}")
        
        sections.append("")
        
        # Phase breakdown
        phases = report.get('phases', {})
        sections.append("Phase Breakdown:")
        sections.append("-" * 60)
        
        if 'content_conversion' in phases:
            conv = phases['content_conversion']
            sections.append("  Content Conversion:")
            sections.append(
                f"    Pages: {conv.get('pages_success', 0)} success, "
                f"{conv.get('pages_failed', 0)} failed, "
                f"{conv.get('pages_partial', 0)} partial"
            )
        
        if 'markdown_export' in phases:
            export = phases['markdown_export']
            # Show different header for combined workflow
            if report.get('export_target') != 'markdown_files':
                sections.append("  Export Phase (Combined Workflow):")
            else:
                sections.append("  Markdown Export:")
            sections.append(
                f"    Pages: {export.get('pages_exported', 0)} exported, "
                f"{export.get('attachments_downloaded', 0)} attachments"
            )
            if export.get('failed'):
                sections.append("    Status: FAILED")
        
        if 'wikijs_import' in phases:
            wj = phases['wikijs_import']
            sections.append("  Wiki.js Import:")
            sections.append(
                f"    Pages: {wj.get('created', 0)} created, "
                f"{wj.get('updated', 0)} updated, "
                f"{wj.get('failed', 0)} failed"
            )
            if wj.get('attachments_uploaded'):
                sections.append(
                    f"    Attachments: {wj.get('attachments_uploaded', 0)} uploaded"
                )
        
        if 'bookstack_import' in phases:
            bs = phases['bookstack_import']
            sections.append("  BookStack Import:")
            sections.append(
                f"    Shelves: {bs.get('shelves', 0)}, "
                f"Books: {bs.get('books', 0)}, "
                f"Chapters: {bs.get('chapters', 0)}, "
                f"Pages: {bs.get('pages', 0)}"
            )
            if bs.get('images_uploaded'):
                sections.append(
                    f"    Images: {bs.get('images_uploaded', 0)} uploaded"
                )
        
        sections.append("")
        
        # Integrity verification section
        integrity = report.get('integrity_verification', {})
        if integrity.get('enabled'):
            sections.append("Integrity Verification:")
            sections.append("-" * 60)
            sections.append(f"  Score:       {integrity.get('integrity_score', 0):.1%}")
            sections.append(f"  Issues:      {integrity.get('total_issues', 0)}")
            sections.append(f"  Depth:       {integrity.get('verification_depth', 'standard')}")
            
            # Attachment verification
            att_verify = integrity.get('attachment_verification', {})
            if att_verify:
                sections.append(f"\n  Attachments: {att_verify.get('found', 0)}/{att_verify.get('total_refs', 0)} found")
                if att_verify.get('missing', 0) > 0:
                    sections.append(f"  WARNING:     {att_verify['missing']} missing attachments")
            
            # Hierarchy verification
            hier_verify = integrity.get('hierarchy_verification', {})
            if hier_verify:
                sections.append(f"\n  Hierarchy:   {hier_verify.get('total_pages', 0)} pages checked")
                if hier_verify.get('orphans', 0) > 0:
                    sections.append(f"  WARNING:     {hier_verify['orphans']} orphan pages")
                if hier_verify.get('circular_refs', 0) > 0:
                    sections.append(f"  ERROR:       {hier_verify['circular_refs']} circular references")
            
            # Link verification
            link_verify = integrity.get('link_verification', {})
            if link_verify:
                sections.append(f"\n  Links:       {link_verify.get('total_links', 0)} total")
                if link_verify.get('internal_broken', 0) > 0:
                    sections.append(f"  WARNING:     {link_verify['internal_broken']} broken internal links")
                if link_verify.get('attachment_missing', 0) > 0:
                    sections.append(f"  WARNING:     {link_verify['attachment_missing']} missing attachment links")
            
            # Backup info
            backup_info = integrity.get('backup_info', {})
            if backup_info.get('enabled'):
                backup_size_mb = backup_info.get('total_size_mb', 0)
                sections.append(f"\n  Backup:      {backup_info.get('files_saved', 0)} files ({backup_size_mb:.1f} MB)")
                sections.append(f"  Duration:    {backup_info.get('backup_duration', 0):.2f}s")
            
            # Recommendations
            recommendations = integrity.get('recommendations', [])
            if recommendations:
                sections.append("\n  Recommendations:")
                for i, rec in enumerate(recommendations[:3], 1):  # Show top 3
                    sections.append(f"    {i}. {rec}")
            
            sections.append("")
        
        # Cache statistics
        cache = report.get('cache', {})
        if cache.get('enabled'):
            sections.append("Cache Statistics:")
            sections.append("-" * 60)
            sections.append(f"  Mode:        {cache.get('mode', 'unknown')}")
            sections.append(f"  Hits:        {cache.get('hits', 0)}")
            sections.append(f"  Misses:      {cache.get('misses', 0)}")
            
            hit_rate = cache.get('hit_rate', 0) * 100
            sections.append(f"  Hit Rate:    {hit_rate:.1f}%")
            
            # Show API-specific stats if available (API mode)
            if 'api_calls_made' in cache and cache['api_calls_made'] > 0:
                sections.append(f"  API Made:    {cache.get('api_calls_made', 0)} calls")
                sections.append(f"  API Saved:   {cache.get('api_calls_saved', 0)} calls")
                
                total_requests = cache.get('total_requests', 0)
                if total_requests > 0:
                    savings_rate = cache.get('savings_rate', 0) * 100
                    sections.append(f"  Savings:     {savings_rate:.1f}% ({cache.get('api_calls_saved', 0)}/{total_requests})")
            
            # Show validation stats if available (API validation mode)
            if cache.get('validations', 0) > 0:
                sections.append(f"  Validations: {cache.get('validations', 0)}")
                sections.append(f"  Invalidated: {cache.get('invalidations', 0)}")
            
            sections.append(f"  Entries:     {cache.get('total_entries', 0)}")
            sections.append(f"  Cache Size:  {cache.get('total_size_mb', 0):.2f} MB")
            sections.append("")
        
        # Error summary
        errors = report.get('errors', [])
        if errors:
            sections.append("Error Summary:")
            sections.append(f"  Total errors: {len(errors)}")
            
            # Group errors by phase
            errors_by_phase = {}
            for error in errors:
                phase = error.get('phase', 'unknown')
                if phase not in errors_by_phase:
                    errors_by_phase[phase] = 0
                errors_by_phase[phase] += 1
            
            for phase, count in sorted(errors_by_phase.items()):
                sections.append(f"  {phase}: {count} errors")
            
            # Show rollback information if executed
            if any(phase_stats.get('rollback_executed', False) for phase_stats in report.get('phases', {}).values()):
                sections.append("")
                sections.append("  Rollback: Partial cleanup performed - check logs for details.")
            
            sections.append("")
        
        # Space breakdown (if multiple spaces)
        spaces = report.get('spaces', [])
        if len(spaces) > 1:
            sections.append("Space Breakdown:")
            sections.append("-" * 60)
            for space in spaces:
                sections.append(
                    f"  {space['key']}: {space['name']}"
                )
                sections.append(
                    f"    Pages: {space['pages_converted']}/{space['pages_total']}"
                )
                if space['attachments'] > 0:
                    sections.append(f"    Attachments: {space['attachments']}")
                if space['pages_failed'] > 0:
                    sections.append(f"    Failed: {space['pages_failed']}")
            sections.append("")
        
        # Footer
        sections.append("=" * 60)
        
        return "\n".join(sections)
    
    def export_json_report(self, report: Dict[str, Any], filepath: str) -> None:
        """
        Export report to JSON file.
        
        Args:
            report: Migration report dictionary
            filepath: Output file path
        """
        try:
            with open(filepath, 'w', encoding='utf-8') as f:
                json.dump(report, f, indent=2, ensure_ascii=False, default=str)
            
            self.logger.info(f"JSON report exported to {filepath}")
            
        except Exception as e:
            self.logger.error(f"Failed to export JSON report: {str(e)}")
    
    def export_csv_summary(self, report: Dict[str, Any], filepath: str) -> None:
        """
        Export summary statistics to CSV.
        
        Args:
            report: Migration report dictionary
            filepath: Output file path
        """
        try:
            spaces = report.get('spaces', [])
            
            with open(filepath, 'w', newline='', encoding='utf-8') as f:
                writer = csv.writer(f)
                writer.writerow([
                    'space_key', 'space_name', 'pages_total',
                    'pages_converted', 'attachments', 'errors'
                ])
                
                for space in spaces:
                    writer.writerow([
                        space['key'],
                        space['name'],
                        space['pages_total'],
                        space['pages_converted'],
                        space['attachments'],
                        space['pages_failed']
                    ])
            
            self.logger.info(f"CSV summary exported to {filepath}")
            
            # Export integrity issues CSV if verification was performed
            if report.get('integrity_verification', {}).get('enabled'):
                integrity_filepath = filepath.replace('.csv', '_integrity_issues.csv')
                self._export_integrity_issues_csv(report, integrity_filepath)
            
        except Exception as e:
            self.logger.error(f"Failed to export CSV summary: {str(e)}")
    
    def _export_integrity_issues_csv(self, report: Dict[str, Any], filepath: str) -> None:
        """Export integrity issues to CSV file.
        
        Args:
            report: Migration report dictionary
            filepath: Output file path for integrity issues
        """
        try:
            integrity = report.get('integrity_verification', {})
            issues = []
            
            # Collect attachment issues
            att_verify = integrity.get('attachment_verification', {})
            for detail in att_verify.get('missing_details', []):
                issues.append({
                    'issue_type': 'missing_attachment',
                    'page_id': detail.get('page_id', ''),
                    'page_title': detail.get('page_title', ''),
                    'description': f"Missing attachment: {detail.get('attachment_title', '')}",
                    'severity': 'high',
                    'recommendation': 'Re-run fetch with attachment download enabled or check Confluence permissions'
                })
            
            # Collect hierarchy issues
            hier_verify = integrity.get('hierarchy_verification', {})
            for detail in hier_verify.get('orphan_details', []):
                issues.append({
                    'issue_type': 'orphan_page',
                    'page_id': detail.get('page_id', ''),
                    'page_title': detail.get('page_title', ''),
                    'description': f"Orphan page: {detail.get('issue', '')}",
                    'severity': 'medium',
                    'recommendation': 'Verify parent page exists or set parent_id to None'
                })
            
            for detail in hier_verify.get('circular_ref_details', []):
                issues.append({
                    'issue_type': 'circular_reference',
                    'page_id': '',  # Circular refs involve multiple pages
                    'page_title': '',
                    'description': detail.get('issue', ''),
                    'severity': 'critical',
                    'recommendation': 'Review circular reference paths and fix parent-child relationships'
                })
            
            # Collect link issues
            link_verify = integrity.get('link_verification', {})
            for detail in link_verify.get('broken_link_details', []):
                severity = 'medium'
                if detail.get('link_type') == 'attachment':
                    severity = 'high'
                
                issues.append({
                    'issue_type': 'broken_link',
                    'page_id': detail.get('page_id', ''),
                    'page_title': detail.get('page_title', ''),
                    'description': f"Broken {detail.get('link_type', 'link')}: {detail.get('link_url', '')}",
                    'severity': severity,
                    'recommendation': 'Update link to valid page ID or remove broken reference'
                })
            
            if issues:
                with open(filepath, 'w', newline='', encoding='utf-8') as f:
                    writer = csv.DictWriter(f, fieldnames=[
                        'issue_type', 'page_id', 'page_title', 'description',
                        'severity', 'recommendation'
                    ])
                    writer.writeheader()
                    writer.writerows(issues)
                
                self.logger.info(f"Integrity issues CSV exported to {filepath}")
            
        except Exception as e:
            self.logger.warning(f"Failed to export integrity issues CSV: {str(e)}")
