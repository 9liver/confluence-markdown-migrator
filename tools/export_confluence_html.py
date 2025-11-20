#!/usr/bin/env python3
"""
Export Confluence page as raw HTML for debugging markdown converter.

This script fetches a Confluence page using the REST API and saves the raw HTML
(export_view) to a file for analysis and debugging purposes.

For environments with internal CAs, you can use system certificates by either:
- Setting USE_SYSTEM_CA=1 environment variable
- Or setting REQUESTS_CA_BUNDLE environment variable to your CA bundle path
"""

import sys
import os
import requests
from pathlib import Path
from urllib.parse import urljoin

# Optional: Use system CA certificates if requested
try:
    if os.getenv('USE_SYSTEM_CA') in ('1', 'true', 'True', 'TRUE'):
        import truststore
        truststore.inject_into_ssl()
        print("Using system CA certificate store")
except ImportError:
    if os.getenv('USE_SYSTEM_CA'):
        print("Warning: truststore not installed. Install with: pip install truststore")
except Exception:
    pass  # Silently continue if truststore fails


def fetch_confluence_html(page_id, confluence_url, token, insecure=False):
    """Fetch raw HTML content of a Confluence page via REST API."""
    api_url = urljoin(confluence_url, f"/rest/api/content/{page_id}")
    params = {
        'expand': 'body.export_view,space'
    }
    headers = {
        'Authorization': f'Bearer {token}',
        'Accept': 'application/json'
    }
    
    # Handle SSL verification
    if insecure:
        import urllib3
        urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)
        verify = False
    elif ca_bundle_path:
        verify = ca_bundle_path
    else:
        verify = True
    
    response = requests.get(api_url, params=params, headers=headers, timeout=30, verify=verify)
    response.raise_for_status()
    
    return response.json()


def save_html_to_file(html_content, output_file):
    """Save HTML content to file."""
    with open(output_file, 'w', encoding='utf-8') as f:
        f.write(html_content)


def get_token():
    """Get Confluence API token from environment or prompt user."""
    token = os.getenv('CONFLUENCE_TOKEN')
    if not token:
        token = input("Enter Confluence API Token: ").strip()
    return token


def main():
    """Main entry point."""
    # Check for help flag
    if len(sys.argv) > 1 and sys.argv[1] in ['-h', '--help']:
        print(__doc__)
        print("\nUsage:")
        print("  python export_confluence_html.py [--insecure] <page_id> [output_file] [confluence_url]")
        print("\nArguments:")
        print("  --insecure        Disable SSL certificate verification (NOT RECOMMENDED)")
        print("  page_id           The Confluence page ID (required)")
        print("  output_file       Output filename (optional, default: raw_html_<page_id>.html)")
        print("  confluence_url    Confluence base URL (optional, default: https://confluence.oediv.lan)")
        print("\nEnvironment Variables:")
        print("  CONFLUENCE_TOKEN     API token for authentication (will prompt if not set)")
        print("  USE_SYSTEM_CA=1      Use system CA certificates (for internal CAs)")
        print("  REQUESTS_CA_BUNDLE   Path to custom CA bundle file (alternative to USE_SYSTEM_CA)")
        print("  CONFLUENCE_INSECURE  Set to '1' to disable SSL verification")
        print("\nExamples:")
        print("  python export_confluence_html.py 244744731")
        print("  USE_SYSTEM_CA=1 python export_confluence_html.py 244744731")
        print("  python export_confluence_html.py --insecure 244744731")
        print("  CONFLUENCE_INSECURE=1 python export_confluence_html.py 244744731")
        print("\nFor internal CAs, install: pip install truststore")
        return 0
    
    # Check for insecure flag
    insecure = False
    if '--insecure' in sys.argv:
        insecure = True
        sys.argv.remove('--insecure')
    
    # Also check environment variable
    if os.getenv('CONFLUENCE_INSECURE') in ('1', 'true', 'True', 'TRUE'):
        insecure = True
    
    # Parse arguments
    if len(sys.argv) < 2:
        print("Error: page_id is required", file=sys.stderr)
        print("Usage: python export_confluence_html.py [--insecure] <page_id> [output_file] [confluence_url]", file=sys.stderr)
        print("  --insecure    Disable SSL certificate verification (NOT RECOMMENDED)" , file=sys.stderr)
        return 1
    
    page_id = sys.argv[1]
    output_file = sys.argv[2] if len(sys.argv) > 2 else f"raw_html_{page_id}.html"
    confluence_url = sys.argv[3] if len(sys.argv) > 3 else "https://confluence.oediv.lan"
    
    # Get API token
    token = get_token()
    if not token:
        print("Error: API token is required.", file=sys.stderr)
        return 1
    
    try:
        print(f"Fetching page {page_id} from {confluence_url}...")
        
        # Fetch data from Confluence
        if insecure:
            print("⚠️  WARNING: SSL verification disabled (insecure mode)")
            
        data = fetch_confluence_html(page_id, confluence_url, token, insecure)
        
        # Extract HTML and metadata
        html_content = data['body']['export_view']['value']
        page_title = data.get('title', 'Unknown')
        space_key = data.get('space', {}).get('key', 'Unknown')
        
        # Save to file
        save_html_to_file(html_content, output_file)
        
        # Report success
        print(f"\n✅ Successfully exported Confluence page!")
        print(f"   Page: {page_title} (ID: {page_id})")
        print(f"   Space: {space_key}")
        print(f"   File: {output_file}")
        print(f"   Size: {len(html_content)} characters")
        
        return 0
        
    except requests.exceptions.HTTPError as e:
        if e.response.status_code == 401:
            print(f"❌ Authentication failed: Check your API token", file=sys.stderr)
        elif e.response.status_code == 404:
            print(f"❌ Page {page_id} not found", file=sys.stderr)
        else:
            print(f"❌ API request failed: {e}", file=sys.stderr)
        return 1
    except requests.exceptions.RequestException as e:
        print(f"❌ Connection error: {e}", file=sys.stderr)
        return 1
    except KeyError as e:
        print(f"❌ Unexpected response format: missing {e}", file=sys.stderr)
        print(f"Response keys: {list(data.keys()) if 'data' in locals() else 'N/A'}" , file=sys.stderr)
        return 1
    except Exception as e:
        print(f"❌ Unexpected error: {e}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    sys.exit(main())
