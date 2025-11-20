# Troubleshooting SSL Certificate Errors

This guide helps you resolve SSL certificate errors when connecting to Confluence servers with internal/self-signed certificates.

## Quick Start: Use the Enhanced Debug Tool

We've created an enhanced version with better SSL debugging:

```bash
# Use the enhanced version
python tools/export_confluence_html_enhanced.py 244744731

# Or with system CA enabled
USE_SYSTEM_CA=1 python tools/export_confluence_html_enhanced.py 244744731

# Disable SSL verification (NOT recommended for production)
CONFLUENCE_VERIFY_SSL=false python tools/export_confluence_html_enhanced.py 244744731
```

## Check Your SSL Configuration

Run our SSL diagnostic tool to see what's happening:

```bash
python tools/check_ssl.py https://confluence.yourcompany.com
```

This will show you:
- ✅ What certificate stores are available
- ✅ Whether truststore is installed
- ✅ Current environment variable settings
- ✅ Direct SSL connection test results
- ✅ Certificate chain information

## Common Issues and Solutions

### ❌ "[SSL: CERTIFICATE_VERIFY_FAILED] certificate verify failed: self signed certificate"

This error means the certificate is either:
1. Actually self-signed (not signed by any CA)
2. Signed by an internal CA that's not trusted

**Solution 1: Use System Certificates (if CA is installed)**

```bash
# Install truststore if not already installed
pip install truststore

# Use system certificate store (includes corporate CAs)
USE_SYSTEM_CA=1 python tools/export_confluence_html_enhanced.py 244744731
```

**Solution 2: Specify CA Bundle Directly**

Find your CA bundle file:

```bash
# Ubuntu/Debian
ls -la /etc/ssl/certs/ca-certificates.crt

# RHEL/CentOS
ls -la /etc/pki/tls/certs/ca-bundle.crt

# Check if your internal CA is in there
grep "YourCompanyName" /etc/ssl/certs/ca-certificates.crt
```

Then use it:

```bash
# Ubuntu/Debian
export REQUESTS_CA_BUNDLE=/etc/ssl/certs/ca-certificates.crt
python tools/export_confluence_html_enhanced.py 244744731

# RHEL/CentOS
export REQUESTS_CA_BUNDLE=/etc/pki/tls/certs/ca-bundle.crt
python tools/export_confluence_html_enhanced.py 244744731
```

**Solution 3: Get the CA Certificate from IT**

If the CA is not in the system store, get it from your IT team:

```bash
# Save the CA certificate
# (Get this from your IT team or export from browser)
cat > internal-ca.crt << 'EOF'
-----BEGIN CERTIFICATE-----
MIID... (your CA certificate)
-----END CERTIFICATE-----
EOF

# Use it
export REQUESTS_CA_BUNDLE=./internal-ca.crt
python tools/export_confluence_html_enhanced.py 244744731
```

**Solution 4: Extract Certificate from Confluence**

Download the certificate from your browser:

1. Open Chrome/Firefox and go to your Confluence URL
2. Click the lock icon in the address bar
3. View certificate details
4. Export the root/CA certificate
5. Save as `confluence-ca.crt`
6. Use it:

```bash
export REQUESTS_CA_BUNDLE=./confluence-ca.crt
python tools/export_confluence_html_enhanced.py 244744731
```

### ❌ "[SSL: CERTIFICATE_VERIFY_FAILED] unable to get local issuer certificate"

This means the CA certificate is missing from the trust store.

**Solution:** Same as above - use one of the CA bundle methods or add the CA to your system store.

### ❌ "hostname doesn't match certificate"

The certificate is for a different hostname than you're connecting to.

**Solution:** Check the URL:

```bash
# This might fail if cert is for confluence.company.com
# but you're using an IP or different hostname
python tools/check_ssl.py https://192.168.1.100

# Use the correct hostname
python tools/export_confluence_html_enhanced.py 244744731 output.html https://confluence.company.com
```

### ❌ Still Getting Errors with USE_SYSTEM_CA=1

Your internal CA might not be in the system store. Let's check:

```bash
# Check what's in system store
python -c "
import truststore
import ssl
ctx = truststore.SSLContext(ssl.PROTOCOL_TLS_CLIENT)
print('truststore SSL context created successfully')
"

# Test connection directly
python -c "
import os
import requests
os.environ['USE_SYSTEM_CA'] = '1'
import truststore
truststore.inject_into_ssl()
response = requests.get('https://confluence.yourcompany.com', timeout=10)
print(f'Success! Status: {response.status_code}')
"
```

If this still fails, your CA is not in the system store - use the CA bundle method instead.

### ❌ Python Can't Find CA Bundle Files

Python might be looking in the wrong place. Let's find where the CA bundle should be:

```bash
# Find all CA bundle locations
find /etc -name "*.crt" -o -name "ca-bundle*" 2>/dev/null | head -20

# Check Python's default paths
python -c "import ssl; print(ssl.get_default_verify_paths())"

# On Ubuntu/Debian
ls -la /etc/ssl/certs/

# On RHEL/CentOS
ls -la /etc/pki/tls/certs/
```

## Testing Different Options

### Test 1: Check with system CA

```bash
# Check if system CA works
USE_SYSTEM_CA=1 python tools/check_ssl.py https://confluence.yourcompany.com

# If successful, use the export tool
USE_SYSTEM_CA=1 python tools/export_confluence_html_enhanced.py 244744731
```

### Test 2: Check with explicit CA bundle

```bash
# Find your CA bundle
# Ubuntu/Debian:
export REQUESTS_CA_BUNDLE=/etc/ssl/certs/ca-certificates.crt

# RHEL/CentOS:
export REQUESTS_CA_BUNDLE=/etc/pki/tls/certs/ca-bundle.crt

# Test
python tools/check_ssl.py https://confluence.yourcompany.com

# If successful, use the export tool
python tools/export_confluence_html_enhanced.py 244744731
```

### Test 3: Check with your internal CA

```bash
# If you have a specific CA certificate
export REQUESTS_CA_BUNDLE=/path/to/your/internal-ca.crt
python tools/check_ssl.py https://confluence.yourcompany.com

# If successful
python tools/export_confluence_html_enhanced.py 244744731
```

### Test 4: Disable SSL verification (NOT recommended)

⚠️ Only for testing/debugging!

```bash
CONFLUENCE_VERIFY_SSL=false python tools/export_confluence_html_enhanced.py 244744731
```

## Debugging with Python Repl

Let's test interactively:

```bash
# Start Python with system CA enabled
USE_SYSTEM_CA=1 python
```

Then in Python:

```python
>>> import os
>>> import requests
>>> 
>>> # Check if truststore worked
>>> try:
...     import truststore
...     print("truststore imported")
... except ImportError:
...     print("truststore not installed")
... 
>>> # Test connection
>>> url = "https://confluence.yourcompany.com"
>>> try:
...     response = requests.get(url, timeout=10)
...     print(f"Success! Status: {response.status_code}")
... except Exception as e:
...     print(f"Error: {e}")
...
>>> # If that fails, try with explicit CA bundle
>>> os.environ['REQUESTS_CA_BUNDLE'] = '/etc/ssl/certs/ca-certificates.crt'
>>> try:
...     response = requests.get(url, timeout=10)
...     print(f"Success! Status: {response.status_code}")
... except Exception as e:
...     print(f"Error: {e}")
...
>>> # Last resort: disable verification (NOT recommended)
>>> try:
...     response = requests.get(url, timeout=10, verify=False)
...     print(f"Success with verify=False! Status: {response.status_code}")
... except Exception as e:
...     print(f"Error: {e}")
```

## Platform-Specific Issues

### Ubuntu/Debian

```bash
# Check if ca-certificates is installed
dpkg -l | grep ca-certificates

# Update certificate store
sudo apt update
sudo apt install ca-certificates
sudo update-ca-certificates

# Check contents
ls -la /etc/ssl/certs/ca-certificates.crt
```

### RHEL/CentOS/Fedora

```bash
# Check if ca-certificates is installed
rpm -qa | grep ca-certificates

# Update certificate store
sudo yum install ca-certificates
sudo update-ca-trust

# Check contents
ls -la /etc/pki/tls/certs/ca-bundle.crt
```

### Docker Containers

```bash
# When running in Docker, install CA certificates
FROM python:3.11

# Install CA certificates for Debian/Ubuntu
RUN apt-get update && apt-get install -y ca-certificates

# Or for RHEL/CentOS
RUN yum install -y ca-certificates

# For self-signed certs, copy your CA
COPY internal-ca.crt /usr/local/share/ca-certificates/
RUN update-ca-certificates

# Then use system CA
ENV USE_SYSTEM_CA=1
```

## Getting Help From IT

If none of these solutions work, ask your IT team for:

1. **The CA certificate file** (usually a `.crt` or `.pem` file)
2. **The correct Confluence URL** to use
3. **Any proxy configuration** needed
4. **VPN requirements** if connecting remotely

## Full Working Examples

### Example 1: With system CA (if CA is installed system-wide)

```bash
# Install requirements
pip install -r requirements.txt

# Enable system CA
export USE_SYSTEM_CA=1

# Export the page
python tools/export_confluence_html_enhanced.py 244744731
```

### Example 2: With custom CA bundle

```bash
# Find or get CA bundle
export REQUESTS_CA_BUNDLE=/etc/ssl/certs/ca-certificates.crt

# Export the page
python tools/export_confluence_html_enhanced.py 244744731
```

### Example 3: With specific CA certificate

```bash
# Get CA cert from IT
# Save as internal-ca.crt

# Use it
export REQUESTS_CA_BUNDLE=./internal-ca.crt

# Export the page
python tools/export_confluence_html_enhanced.py 244744731 my_page.html https://confluence.company.com
```

### Example 4: Quick test with SSL disabled (debug only)

```bash
# NOT RECOMMENDED for production
export CONFLUENCE_TOKEN="your_token"
CONFLUENCE_VERIFY_SSL=false python tools/export_confluence_html_enhanced.py 244744731
```

## Run Diagnostics

Before trying any of these, run our diagnostic tool to see what's available:

```bash
python tools/check_ssl.py https://confluence.yourcompany.com
```

This will tell you exactly what's wrong and recommend the best solution.
