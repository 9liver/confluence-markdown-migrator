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

try:
    # For package imports
    from ..models import DocumentationTree, ConfluenceSpace, ConfluencePage
except ImportError:
    # For direct script execution
    import sys
    import os
    sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))
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
        export_target: str
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
        
        # Add rollback summary if any phase executed rollback
        for phase_name, stats in phase_stats.items():
            if stats.get('rollback_executed'):
                if 'rollback_summary' not in summary:
                    summary['rollback_summary'] = {
                        'executed': True,
                        'entities_deleted': stats.get('rollback_deleted', 0)
                    }
        
        return summary
    
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
            
        except Exception as e:
            self.logger.error(f"Failed to export CSV summary: {str(e)}")