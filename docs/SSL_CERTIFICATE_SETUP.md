# SSL Certificate Setup for CI/CD

## Problem

The CI/CD pipeline runs in a Docker container (`python:3.12-slim`) that doesn't include DoD root CA certificates by default. This causes SSL verification failures when connecting to `git.example.com`.

## Solution

Add the DoD root CA certificate as a CI/CD variable so it can be installed during pipeline execution.

## Setup Instructions

### Step 1: Extract DoD Root CA Certificate

On a system that has the DoD certificates installed (like your local WSL2 environment):

```bash
# Display the DoD root CA certificate
cat /usr/local/share/ca-certificates/dod.crt
```

Copy the entire output, including the `-----BEGIN CERTIFICATE-----` and `-----END CERTIFICATE-----` lines.

### Step 2: Add CI/CD Variable in GitLab

1. Navigate to your project in GitLab: `Settings > CI/CD > Variables`
2. Click **Add variable**
3. Configure the variable:
   - **Key**: `DOD_CA_CERT`
   - **Type**: **File** (REQUIRED for certificate bundles with multiple certs)
   - **Value**: Upload the `dod.crt` file OR paste the entire content
   - **Flags**:
     - ☑ Protect variable (recommended - only available on protected branches)
     - ☐ Mask variable (cannot mask certificates, they're too long)
     - ☐ Expand variable reference
4. Click **Add variable**

**Important**: The DoD certificate bundle contains ~49 certificates. Using **File** type is strongly recommended as it handles large multi-certificate bundles better than Variable type.

### Step 3: Test the Pipeline

After adding the variable:

1. Trigger a manual `backfill` job, or
2. Wait for the scheduled `scheduled_update` to run

The pipeline should now:
- Detect the `DOD_CA_CERT` variable
- Install it into the container's CA bundle
- Enable SSL verification (`GITLAB_SSL_VERIFY=true`)
- Successfully connect to git.example.com with proper certificate validation

### Step 4: Verify Success

Check the job logs. You should see:
```
Installing DoD CA certificate from CI/CD variable...
Updating certificates in /etc/ssl/certs...
1 added, 0 removed; done.
Running hooks in /etc/ca-certificates/update.d...
done.
✓ SSL verification enabled with DoD certificates
```

And no SSL error messages during script execution.

## Certificate Bundle Details

The DoD certificate file (`dod.crt`) contains approximately **49 certificates** forming the complete DoD PKI certificate chain. This includes:
- Root CA certificates
- Intermediate CA certificates
- Various DoD component CA certificates

The pipeline script automatically:
- Detects whether you used File or Variable type
- Handles multi-certificate bundles (all 49 certificates)
- Counts and reports how many certificates were installed
- Updates the system CA bundle to include all DoD certificates

## Troubleshooting

### Certificate Format Issues

If you see errors like "unable to load certificate", ensure:
- The certificate starts with `-----BEGIN CERTIFICATE-----`
- The certificate ends with `-----END CERTIFICATE-----`
- There are no extra spaces or characters
- The file is in PEM format (not DER)

### Converting DER to PEM (if needed)

If you have a `.der` file:
```bash
openssl x509 -inform DER -in dod_cert.der -out dod_cert.pem
```

### Still Getting SSL Errors

If SSL verification still fails:
1. Check that `DOD_CA_CERT` variable is actually set in CI/CD settings
2. Look for the "Installing DoD CA certificate" message in job logs
3. Verify the certificate chain includes the root CA that signed git.example.com's certificate

### Fall Back to Disabled SSL (Not Recommended)

If you cannot get the certificate working, the pipeline will automatically fall back to SSL verification bypass (current behavior). You'll see:
```
⚠ DOD_CA_CERT not set, using SSL verification bypass
```

## Security Benefits of Proper SSL Verification

Once configured:
- ✅ Proper certificate chain validation
- ✅ Protection against man-in-the-middle attacks
- ✅ No urllib3 InsecureRequestWarning in logs
- ✅ Compliance with security best practices
- ✅ Aligns with DoD security requirements

## References

- DoD PKI: https://public.cyber.mil/pki-pke/
- GitLab CI/CD Variables: https://docs.gitlab.com/ee/ci/variables/
- Python requests SSL verification: https://requests.readthedocs.io/en/latest/user/advanced/#ssl-cert-verification
