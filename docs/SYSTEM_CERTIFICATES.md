# Using System Certificates with Internal/Corporate CAs

This guide explains how to configure Python to use system certificates when working with Confluence servers that use internal or corporate Certificate Authorities (CAs).

## Problem

When connecting to Confluence servers with certificates signed by internal CAs (common in corporate environments), you may encounter SSL verification errors like:

```
SSL: CERTIFICATE_VERIFY_FAILED
unable to get local issuer certificate
```

## Solutions

### Solution 1: Use System Certificate Store (Recommended)

This method uses the operating system's native certificate store, which automatically includes your organization's internal CAs.

#### Install truststore

```bash
pip install truststore
```

Or add it to your requirements:
```bash
pip install -r requirements.txt  # truststore is already listed as optional dependency
```

#### Enable System CA Usage

Set the environment variable before running any scripts:

```bash
export USE_SYSTEM_CA=1
```

#### Usage Examples

**Export Confluence HTML:**
```bash
USE_SYSTEM_CA=1 python tools/export_confluence_html.py 123456789
```

**Full Migration:**
```bash
USE_SYSTEM_CA=1 python migrate.py --config config.yaml
```

**Run Tests:**
```bash
USE_SYSTEM_CA=1 python -m pytest tests/
```

#### How It Works

The `truststore` library injects system certificate support into Python's SSL module:
- **macOS**: Uses Security framework
- **Windows**: Uses CryptoAPI
- **Linux**: Uses OpenSSL with system certificate stores

This means:
- ✅ Certificates are managed by your IT team
- ✅ Updates happen automatically with system updates
- ✅ No manual certificate bundle management
- ✅ Works across all Python libraries (requests, urllib3, etc.)

### Solution 2: Specify Custom CA Bundle

If you prefer to manually specify a CA certificate file:

#### Find Your System CA Bundle

**Ubuntu/Debian:**
```bash
export REQUESTS_CA_BUNDLE=/etc/ssl/certs/ca-certificates.crt
```

**RHEL/CentOS/Fedora:**
```bash
export REQUESTS_CA_BUNDLE=/etc/pki/tls/certs/ca-bundle.crt
```

**macOS (if using Homebrew OpenSSL):**
```bash
export REQUESTS_CA_BUNDLE=/usr/local/etc/openssl/cert.pem
```

#### Usage Examples

```bash
# Export Confluence HTML
REQUESTS_CA_BUNDLE=/etc/ssl/certs/ca-certificates.crt python tools/export_confluence_html.py 123456789

# Or set globally
export REQUESTS_CA_BUNDLE=/etc/ssl/certs/ca-certificates.crt
python tools/export_confluence_html.py 123456789
python migrate.py --config config.yaml
```

### Solution 3: Disable SSL Verification (Not Recommended)

⚠️ **Warning**: This disables SSL security and makes you vulnerable to man-in-the-middle attacks. Use only for testing/debugging in secure environments.

Set `verify_ssl: false` in your `config.yaml`:

```yaml
confluence:
  url: "https://confluence.company.com"
  verify_ssl: false  # ⚠️ Not recommended for production
```

Or in the client initialization:
```python
from confluence_client import ConfluenceClient

client = ConfluenceClient(
    base_url="https://confluence.company.com",
    verify_ssl=False  # ⚠️ Not recommended
)
```

## Platform-Specific Notes

### Linux

On Linux, `truststore` uses OpenSSL and looks for certificates in standard system locations. If your organization uses custom certificate stores, you may need to specify the path via `REQUESTS_CA_BUNDLE`.

**Check available certificates:**
```bash
# List installed CA certificates
ls /etc/ssl/certs/

# Check if your internal CA is present
grep -r "YourCompany" /etc/ssl/certs/
```

### macOS

On macOS, `truststore` uses the Keychain, which should automatically include any certificates installed by your organization. You can verify:

1. Open "Keychain Access"
2. Look in "System" or "System Roots" keychains
3. Check if your internal CA certificate is present

### Windows

On Windows, `truststore` uses the Windows Certificate Store, which should include domain/enterprise certificates. Check via:

1. Run `certmgr.msc`
2. Look in "Trusted Root Certification Authorities"
3. Check if your internal CA certificate is present

## Testing Your Configuration

### Test System CA Detection

```bash
# Test with a simple HTTPS request
python -c "import requests; print(requests.get('https://confluence.company.com', timeout=5).status_code)"

# With system CA enabled
USE_SYSTEM_CA=1 python -c "import requests; print(requests.get('https://confluence.company.com', timeout=5).status_code)"
```

### Test Confluence Connection

Use the export tool to verify connectivity:

```bash
USE_SYSTEM_CA=1 python tools/export_confluence_html.py YOUR_PAGE_ID
```

## Troubleshooting

### "truststore not installed" Warning

Install it:
```bash
pip install truststore
```

### ImportError with truststore

Check Python version:
```bash
python --version  # Must be 3.10 or higher
```

### Still getting SSL errors with USE_SYSTEM_CA=1

1. Verify your internal CA is installed in the system store:
   ```bash
   # Linux
   openssl s_client -connect confluence.company.com:443 -showcerts

   # Check if cert is in system store
   openssl verify -CApath /etc/ssl/certs/ -untrusted <(echo | openssl s_client -connect confluence.company.com:443 2>/dev/null | openssl x509) <(echo | openssl s_client -connect confluence.company.com:443 2>/dev/null | openssl x509)
   ```

2. Try specifying the CA bundle directly:
   ```bash
   # Find your CA bundle
   # Ubuntu/Debian
   export REQUESTS_CA_BUNDLE=/etc/ssl/certs/ca-certificates.crt

   # Or use your organization's specific CA file
   export REQUESTS_CA_BUNDLE=/path/to/your/internal-ca.crt
   ```

3. Check certificate chain:
   ```bash
   echo | openssl s_client -servername confluence.company.com -connect confluence.company.com:443 2>/dev/null | openssl x509 -noout -subject -issuer
   ```

### conda Environment Issues

If using conda, it may have its own certificate store:

```bash
# Check conda certs
ls $CONDA_PREFIX/ssl/certs/

# Either use conda certs
export REQUESTS_CA_BUNDLE=$CONDA_PREFIX/ssl/certs/ca-bundle.crt

# Or use system certs
export USE_SYSTEM_CA=1
```

## Environment Variables Summary

| Variable | Description | Example |
|----------|-------------|---------|
| `USE_SYSTEM_CA=1` | Use system certificate store (recommended) | `USE_SYSTEM_CA=1` |
| `REQUESTS_CA_BUNDLE` | Path to custom CA bundle file | `/etc/ssl/certs/ca-certificates.crt` |
| `CONFLUENCE_TOKEN` | API token for authentication | `your_token_here` |

## Docker/Kubernetes Usage

When running in containers, you may need to mount CA certificates:

```dockerfile
FROM python:3.11

# Install your internal CA
COPY my-internal-ca.crt /usr/local/share/ca-certificates/
RUN update-ca-certificates

# Or mount at runtime
```

Then use:
```bash
docker run -e USE_SYSTEM_CA=1 your-image
```

## Security Best Practices

1. ✅ **Use system CA store** (`USE_SYSTEM_CA=1`)
2. ✅ **Keep certificates updated** via system updates
3. ❌ **Avoid disabling SSL verification** in production
4. ✅ **Test SSL connections** before running migrations
5. ✅ **Use API tokens** instead of passwords when possible
6. ✅ **Follow principle of least privilege** for service accounts
