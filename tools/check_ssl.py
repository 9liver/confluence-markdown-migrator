#!/usr/bin/env python3
"""
Debug SSL certificate validation for Confluence connections.
Helps diagnose certificate trust issues with internal CAs.
"""

import os
import sys
import ssl
import socket
from urllib.parse import urlparse
import requests

def check_system_certs():
    """Check system certificate store configuration."""
    print("=" * 70)
    print("SYSTEM CERTIFICATE STORE CHECK")
    print("=" * 70)
    
    # Check if truststore is available and configured
    try:
        import truststore
        print("✓ truststore library is installed")
        print(f"  Version: {truststore.__version__}")
    except ImportError:
        print("✗ truststore library NOT installed")
        print("  Install with: pip install truststore")
    
    # Check environment variables
    print("\nEnvironment Variables:")
    use_system_ca = os.getenv('USE_SYSTEM_CA')
    print(f"  USE_SYSTEM_CA: {use_system_ca}")
    
    ca_bundle = os.getenv('REQUESTS_CA_BUNDLE')
    print(f"  REQUESTS_CA_BUNDLE: {ca_bundle}")
    if ca_bundle and os.path.exists(ca_bundle):
        print(f"    File exists: {ca_bundle}")
    elif ca_bundle:
        print(f"    ⚠ File NOT found: {ca_bundle}")
    
    # Check Python SSL default paths
    print(f"\nPython SSL Configuration:")
    print(f"  Default CA file: {ssl.get_default_verify_paths().cafile}")
    print(f"  Default CA path: {ssl.get_default_verify_paths().capath}")
    
    # Check common system CA locations
    print(f"\nCommon System CA Locations:")
    common_paths = [
        '/etc/ssl/certs/ca-certificates.crt',  # Debian/Ubuntu
        '/etc/pki/tls/certs/ca-bundle.crt',    # RHEL/CentOS
        '/etc/ssl/ca-bundle.pem',              # SUSE
        '/usr/local/etc/openssl/cert.pem',     # macOS Homebrew
        '/etc/ssl/cert.pem',                   # Alpine
    ]
    
    for path in common_paths:
        if os.path.exists(path):
            size = os.path.getsize(path)
            print(f"  ✓ {path} ({size:,} bytes)")
        else:
            print(f"  ✗ {path}")

def test_confluence_ssl(url):
    """Test SSL connection to Confluence."""
    print("\n" + "=" * 70)
    print(f"SSL CONNECTION TEST: {url}")
    print("=" * 70)
    
    try:
        # Parse URL
        parsed = urlparse(url)
        hostname = parsed.hostname
        port = parsed.port or 443
        
        print(f"Testing connection to {hostname}:{port}")
        
        # Test with requests
        print("\n1. Testing with 'requests' library:")
        try:
            response = requests.get(url, timeout=10)
            print(f"  ✓ Success! Status: {response.status_code}")
            print(f"  ✓ SSL verification: PASSED")
        except requests.exceptions.SSLError as e:
            print(f"  ✗ SSL Error: {e}")
            
            # Try to get more details
            if "self signed certificate" in str(e):
                print("\n  ⚠ Certificate appears to be self-signed")
                print("  → This usually means the CA is not trusted by the system")
            elif "unable to get local issuer certificate" in str(e):
                print("\n  ⚠ Cannot find the Certificate Authority in trust store")
                print("  → The CA certificate needs to be added to system store")
        except Exception as e:
            print(f"  ✗ Error: {e}")
        
        # Test with raw SSL
        print("\n2. Testing with raw SSL/TLS:")
        try:
            context = ssl.create_default_context()
            with socket.create_connection((hostname, port), timeout=10) as sock:
                with context.wrap_socket(sock, server_hostname=hostname) as ssock:
                    cert = ssock.getpeercert()
                    print(f"  ✓ SSL handshake successful")
                    print(f"  Certificate info:")
                    print(f"    Subject: {dict(x[0] for x in cert['subject'])}")
                    print(f"    Issuer: {dict(x[0] for x in cert['issuer'])}")
                    print(f"    Version: {cert['version']}")
                    print(f"    Serial: {cert['serialNumber']}")
        except ssl.SSLError as e:
            print(f"  ✗ SSL Error: {e}")
        except Exception as e:
            print(f"  ✗ Error: {e}")
            
    except Exception as e:
        print(f"✗ Failed to parse URL: {e}")

def test_certificate_chain(url):
    """Test and display certificate chain."""
    print("\n" + "=" * 70)
    print(f"CERTIFICATE CHAIN: {url}")
    print("=" * 70)
    
    try:
        # Use openssl to get certificate chain
        import subprocess
        parsed = urlparse(url)
        hostname = parsed.hostname
        port = parsed.port or 443
        
        cmd = f"echo | openssl s_client -connect {hostname}:{port} -showcerts 2>/dev/null"
        result = subprocess.run(cmd, shell=True, capture_output=True, text=True)
        
        if result.returncode == 0:
            print("Certificate chain (from openssl):")
            print(result.stdout[:1000])  # Show first 1000 chars
        else:
            print("Failed to get certificate chain with openssl")
            
    except Exception as e:
        print(f"Could not check certificate chain: {e}")

def main():
    if len(sys.argv) < 2:
        print("Usage: python check_ssl.py <confluence_url>")
        print("Example: python check_ssl.py https://confluence.company.com")
        return 1
    
    url = sys.argv[1]
    
    print("Confluence SSL Certificate Checker")
    print("This tool helps diagnose SSL certificate issues with internal CAs.\n")
    
    check_system_certs()
    test_confluence_ssl(url)
    test_certificate_chain(url)
    
    print("\n" + "=" * 70)
    print("RECOMMENDATIONS")
    print("=" * 70)
    print("\nIf you're getting SSL errors:")
    print("1. Install truststore: pip install truststore")
    print("2. Enable system CA: export USE_SYSTEM_CA=1")
    print("3. Or specify CA bundle: export REQUESTS_CA_BUNDLE=/path/to/ca-bundle.crt")
    print("4. Test again with the export tool")
    
    try:
        import truststore
        print("\n✓ truststore is available - USE_SYSTEM_CA=1 should work")
    except ImportError:
        print("\n✗ truststore not installed - install it first")
    
    return 0

if __name__ == "__main__":
    sys.exit(main())
