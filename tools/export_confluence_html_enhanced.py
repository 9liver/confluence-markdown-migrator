#!/usr/bin/env python3
"""
Export Confluence page as raw HTML - Enhanced version with SSL debugging.

This enhanced version provides better SSL certificate handling and debugging
for environments with internal/self-signed certificates.
"""

import sys
import os
import requests
import warnings
from pathlib import Path
from urllib.parse import urljoin

# Optional: Use system CA certificates if requested
use_system_ca = os.getenv('USE_SYSTEM_CA') in ('1', 'true', 'True', 'TRUE')

if use_system_ca:
    try:
        import truststore
        truststore.inject_into_ssl()
        print("Using system CA certificate store via truststore")
    except ImportError:
        print("Warning: USE_SYSTEM_CA=1 but truststore not installed")
        print("  Install with: pip install truststore")
        print("  Or use: export REQUESTS_CA_BUNDLE=/path/to/ca-bundle.crt")
    except Exception as e:
        print(f"Warning: Could not enable system CA store: {e}")

# Check for custom CA bundle
ca_bundle_path = os.getenv('REQUESTS_CA_BUNDLE')
if ca_bundle_path:
    if os.path.exists(ca_bundle_path):
        print(f"Using custom CA bundle: {ca_bundle_path}")
    else:
        print(f"Warning: REQUESTS_CA_BUNDLE file not found: {ca_bundle_path}")
        ca_bundle_path = None


def get_api_token():
    """Get Confluence API token from environment or prompt user."""
    token = os.getenv('CONFLUENCE_TOKEN')
    if not token:
        token = input("Enter Confluence API Token: ").strip()
    return token


def debug_ssl_error(url, error):
    """Provide detailed SSL error debugging information."""
    print("\n" + "=" * 70)
    print("SSL ERROR DEBUGGING")
    print("=" * 70)
    print(f"\nURL: {url}")
    print(f"Error: {error}")
    
    error_str = str(error)
    
    if "self signed certificate" in error_str:
        print("\n🔍 DIAGNOSIS: Self-signed certificate detected")
        print("\nThis usually means one of:")
        print("  1. The server uses a self-signed certificate (not CA-signed)")
        print("  2. The CA certificate is not in the system trust store")
        print("  3. The CA bundle path is incorrect")
        
        print("\n💡 SOLUTIONS:")
        print("\nOption 1: Use system certificates (if CA is installed)")
        print("  export USE_SYSTEM_CA=1")
        print("  python export_confluence_html_enhanced.py <page_id>")
        
        print("\nOption 2: Specify CA bundle directly")
        print("  # Find your CA bundle first:")
        print("  # Ubuntu/Debian: /etc/ssl/certs/ca-certificates.crt")
        print("  # RHEL/CentOS: /etc/pki/tls/certs/ca-bundle.crt")
        print("  export REQUESTS_CA_BUNDLE=/path/to/ca-bundle.crt")
        print("  python export_confluence_html_enhanced.py <page_id>")
        
        print("\nOption 3: Extract and specify the specific CA certificate")
        print("  # Get the CA certificate from your browser or IT team")
        print("  export REQUESTS_CA_BUNDLE=/path/to/internal-ca.crt")
        
        print("\nOption 4: Disable SSL verification (NOT RECOMMENDED for production)")
        print("  export CONFLUENCE_VERIFY_SSL=false")
        print("  # ⚠️ This makes you vulnerable to MITM attacks")
        
    elif "unable to get local issuer certificate" in error_str:
        print("\n🔍 DIAGNOSIS: Certificate Authority not found")
        print("\nThe certificate is signed by a CA that is not trusted by your system.")
        
        print("\n💡 SOLUTIONS:")
        print("  Use the same solutions as above (Options 1-3)")
        
    else:
        print("\n🔍 General SSL error - check the full error message above")
    
    # Show current configuration
    print("\n📋 CURRENT CONFIGURATION:")
    print(f"  USE_SYSTEM_CA: {os.getenv('USE_SYSTEM_CA', 'not set')}")
    print(f"  REQUESTS_CA_BUNDLE: {os.getenv('REQUESTS_CA_BUNDLE', 'not set')}")
    print(f"  CONFLUENCE_VERIFY_SSL: {os.getenv('CONFLUENCE_VERIFY_SSL', 'not set')}")
    
    return False


def fetch_confluence_html(page_id, confluence_url, token, verify_ssl=True):
    """Fetch raw HTML content of a Confluence page via REST API."""
    api_url = urljoin(confluence_url, f"/rest/api/content/{page_id}")
    params = {
        'expand': 'body.export_view,space'
    }
    headers = {
        'Authorization': f'Bearer {token}',
        'Accept': 'application/json'
    }
    
    # Determine SSL verification settings
    if ca_bundle_path:
        verify = ca_bundle_path
    elif not verify_ssl:
        verify = False
    else:
        verify = True
    
    # Make the request
    response = requests.get(
        api_url, 
        params=params, 
        headers=headers, 
        timeout=30,
        verify=verify
    )
    
    response.raise_for_status()
    return response.json()


def test_confluence_connection(confluence_url, timeout=10):
    """Test if we can connect to Confluence."""
    try:
        # Determine SSL verification settings
        if ca_bundle_path:
            verify = ca_bundle_path
        else:
            verify = True
            
        response = requests.get(confluence_url, timeout=timeout, verify=verify)
        print(f"✓ Successfully connected to {confluence_url}")
        print(f"  Status: {response.status_code}")
        return True
    except requests.exceptions.SSLError as e:
        print(f"✗ SSL Error connecting to {confluence_url}")
        debug_ssl_error(confluence_url, e)
        return False
    except Exception as e:
        print(f"✗ Connection error: {e}")
        return False


def main():
    """Main entry point."""
    # Check for help flag
    if len(sys.argv) > 1 and sys.argv[1] in ['-h', '--help']:
        print(__doc__)
        print("\nUsage:")
        print("  python export_confluence_html_enhanced.py <page_id> [output_file] [confluence_url]")
        print("\nArguments:")
        print("  page_id          The Confluence page ID (required)")
        print("  output_file      Output filename (optional, default: raw_html_<page_id>.html)")
        print("  confluence_url   Confluence base URL (optional, default: https://confluence.oediv.lan)")
        print("\nEnvironment Variables:")
        print("  CONFLUENCE_TOKEN    API token for authentication (will prompt if not set)")
        print("  USE_SYSTEM_CA=1     Use system CA certificates (for internal CAs)")
        print("  REQUESTS_CA_BUNDLE  Path to custom CA bundle file")
        print("  CONFLUENCE_VERIFY_SSL=false  Disable SSL verification (NOT RECOMMENDED)")
        print("\nExamples:")
        print("  python export_confluence_html_enhanced.py 244744731")
        print("  USE_SYSTEM_CA=1 python export_confluence_html_enhanced.py 244744731")
        print("  REQUESTS_CA_BUNDLE=/etc/ssl/certs/ca-bundle.crt python export_confluence_html_enhanced.py 244744731")
        return 0
    
    # Parse arguments
    if len(sys.argv) < 2:
        print("Error: page_id is required", file=sys.stderr)
        print("Usage: python export_confluence_html_enhanced.py <page_id> [output_file] [confluence_url]", file=sys.stderr)
        return 1
    
    page_id = sys.argv[1]
    output_file = sys.argv[2] if len(sys.argv) > 2 else f"raw_html_{page_id}.html"
    confluence_url = sys.argv[3] if len(sys.argv) > 3 else "https://confluence.oediv.lan"
    
    # Check for SSL verification override
    verify_ssl = os.getenv('CONFLUENCE_VERIFY_SSL', 'true').lower() != 'false'
    
    # Test connection first
    print(f"Testing connection to {confluence_url}...")
    if not test_confluence_connection(confluence_url):
        response = input("\nContinue anyway? (y/N): ")
        if response.lower() != 'y':
            return 1
    
    # Get API token
    token = get_api_token()
    if not token:
        print("Error: API token is required.", file=sys.stderr)
        return 1
    
    try:
        print(f"\nFetching page {page_id}...")
        
        # Fetch data from Confluence
        data = fetch_confluence_html(page_id, confluence_url, token, verify_ssl)
        
        # Extract HTML and metadata
        html_content = data['body']['export_view']['value']
        page_title = data.get('title', 'Unknown')
        space_key = data.get('space', {}).get('key', 'Unknown')
        
        # Save to file
        with open(output_file, 'w', encoding='utf-8') as f:
            f.write(html_content)
        
        # Report success
        print(f"\n✅ Successfully exported Confluence page!")
        print(f"   Page: {page_title} (ID: {page_id})")
        print(f"   Space: {space_key}")
        print(f"   File: {output_file}")
        print(f"   Size: {len(html_content)} characters")
        
        return 0
        
    except requests.exceptions.HTTPError as e:
        if e.response.status_code == 401:
            print(f"\n❌ Authentication failed: Check your API token", file=sys.stderr)
        elif e.response.status_code == 404:
            print(f"\n❌ Page {page_id} not found", file=sys.stderr)
        else:
            print(f"\n❌ API request failed: {e}", file=sys.stderr)
        return 1
    except requests.exceptions.SSLError as e:
        print(f"\n❌ SSL Error during API request", file=sys.stderr)
        debug_ssl_error(confluence_url, e)
        return 1
    except requests.exceptions.RequestException as e:
        print(f"\n❌ Connection error: {e}", file=sys.stderr)
        return 1
    except KeyError as e:
        print(f"\n❌ Unexpected response format: missing {e}", file=sys.stderr)
        print(f"Response keys: {list(data.keys()) if 'data' in locals() else 'N/A'}" , file=sys.stderr)
        return 1
    except Exception as e:
        print(f"\n❌ Unexpected error: {e}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    sys.exit(main())
