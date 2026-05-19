#!/usr/bin/env python3
import os
import sys
import json
import urllib.request
import urllib.error
import getpass
import argparse

def get_token(url: str, password: str, insecure: bool = False) -> str:
    """Fetch the bearer token from Kargo API."""
    endpoint = f"{url.rstrip('/')}/v1beta1/login"
    
    req = urllib.request.Request(
        endpoint, 
        data=b'{}', # Empty body 
        headers={
            "Content-Type": "application/json",
            "Authorization": f"Bearer {password}"
        },
        method="POST"
    )
    
    # Handle self-signed certs if --insecure is passed
    ctx = None
    if insecure:
        import ssl
        ctx = ssl.create_default_context()
        ctx.check_hostname = False
        ctx.verify_mode = ssl.CERT_NONE

    try:
        with urllib.request.urlopen(req, context=ctx) as response:
            data = json.loads(response.read().decode('utf-8'))
            return data.get("idToken") # Kargo returns 'idToken' for this endpoint
    except urllib.error.HTTPError as e:
        error_msg = e.read().decode('utf-8')
        print(f"❌ HTTP Error {e.code}: {e.reason}", file=sys.stderr)
        print(f"Response: {error_msg}", file=sys.stderr)
        sys.exit(1)
    except urllib.error.URLError as e:
        print(f"❌ Connection Error: Failed to reach {url}", file=sys.stderr)
        print(f"Details: {e.reason}", file=sys.stderr)
        sys.exit(1)

def main():
    parser = argparse.ArgumentParser(description="Generate a Kargo static bearer token via API.")
    parser.add_argument("--url", "-u", default=os.getenv("KARGO_BASE_URL", "http://localhost:8080"),
                        help="Kargo API URL (default: $KARGO_BASE_URL or http://localhost:8080)")
    parser.add_argument("--insecure", "-k", action="store_true",
                        help="Allow insecure server connections when using SSL (ignore cert validation)")
    
    args = parser.parse_args()
    
    print(f"🔌 Connecting to Kargo API at: {args.url}")
    
    password = os.getenv("KARGO_ADMIN_PASSWORD")
    if password:
        print("🔑 Using password from KARGO_ADMIN_PASSWORD environment variable.")
    else:
        password = getpass.getpass("🔑 Enter Kargo Admin Password: ")
    
    if not password:
        print("❌ Error: Password cannot be empty.")
        sys.exit(1)
        
    print("⏳ Authenticating via API...")
    token = get_token(args.url, password, args.insecure)
    
    if token:
        print("\n✅ Successfully generated remote bearer token!\n")
        print("="*60)
        print(token)
        print("="*60)
        print("\nSet this as your environment variable for the MCP server:")
        print(f"export KARGO_STATIC_BEARER_TOKEN=\"{token}\"")
        print("export KARGO_AUTH_MODE=\"static\"")
    else:
        print("❌ Error: idToken not found in the response payload.", file=sys.stderr)

if __name__ == "__main__":
    main()
