#!/usr/bin/env python3
"""
ArgoCD Token Fetcher and Validator

This script fetches an authentication token from an ArgoCD server and validates it
by making a test API call. It is designed to be used as a helper for setting up
the ArgoCD MCP server environment.

Usage:
    python3 fetch_argocd_token.py [--server URL] [--username USER] [--password PASS] [--verify-tls]

Environment Variables:
    ARGOCD_SERVER
    ARGOCD_USERNAME
    ARGOCD_PASSWORD
    ARGOCD_VERIFY_TLS (default: true)
"""

import os
import sys
import json
import logging
import argparse
import requests
from typing import Optional, Dict, Any
from urllib.parse import urljoin

# Configure logging to stderr so stdout can be used for the token
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s',
    stream=sys.stderr
)
logger = logging.getLogger("argocd-token-fetcher")

class ArgoCDTokenFetcher:
    """Helper class to fetch and validate ArgoCD authentication tokens."""
    
    def __init__(self, server_url: str, username: str, password: str, verify_tls: bool = True):
        self.server_url = server_url.rstrip('/')
        self.username = username
        self.password = password
        self.verify_tls = verify_tls
        self.session = requests.Session()
        self.token = None
        
    def fetch_token(self) -> Optional[str]:
        """Fetch authentication token from ArgoCD server."""
        try:
            session_url = urljoin(self.server_url, '/api/v1/session')
            payload = {
                'username': self.username,
                'password': self.password
            }
            
            logger.info(f"Connecting to {self.server_url}...")
            response = self.session.post(
                session_url,
                json=payload,
                verify=self.verify_tls,
                timeout=30
            )
            response.raise_for_status()
            
            data = response.json()
            self.token = data.get('token')
            
            if not self.token:
                logger.error("Token not found in response")
                return None
                
            logger.info("Successfully fetched ArgoCD token")
            return self.token
            
        except requests.exceptions.RequestException as e:
            logger.error(f"Failed to fetch token: {str(e)}")
            if hasattr(e.response, 'text') and e.response:
                logger.debug(f"Response: {e.response.text}")
            return None
        except Exception as e:
            logger.error(f"Unexpected error: {str(e)}")
            return None

    def validate_token(self) -> bool:
        """Validate the fetched token by making a test API call."""
        if not self.token:
            logger.error("No token to validate")
            return False
            
        try:
            # We use list applications with a limit of 1 to validate access
            # This is a lightweight check that proves we are authenticated
            test_url = urljoin(self.server_url, '/api/v1/applications?limit=1')
            headers = {'Authorization': f'Bearer {self.token}'}
            
            logger.info("Validating token...")
            response = self.session.get(
                test_url,
                headers=headers,
                verify=self.verify_tls,
                timeout=30
            )
            response.raise_for_status()
            return True
            
        except requests.exceptions.RequestException as e:
            logger.error(f"Token validation failed: {str(e)}")
            return False

def parse_args():
    parser = argparse.ArgumentParser(description="Fetch and validate ArgoCD token")
    parser.add_argument("--server", help="ArgoCD server URL (env: ARGOCD_SERVER)")
    parser.add_argument("--username", help="ArgoCD username (env: ARGOCD_USERNAME)")
    parser.add_argument("--password", help="ArgoCD password (env: ARGOCD_PASSWORD)")
    parser.add_argument("--verify-tls", action="store_true", default=None, 
                       help="Verify TLS certificates (default: True, env: ARGOCD_VERIFY_TLS)")
    parser.add_argument("--insecure", action="store_true", help="Skip TLS verification")
    parser.add_argument("--output", choices=['text', 'json', 'env'], default='text',
                       help="Output format (default: text)")
    return parser.parse_args()

def main():
    args = parse_args()
    
    # Resolve configuration from args or env
    server = args.server or os.environ.get('ARGOCD_SERVER')
    username = args.username or os.environ.get('ARGOCD_USERNAME')
    password = args.password or os.environ.get('ARGOCD_PASSWORD')
    
    # TLS logic
    verify_tls = True
    if args.insecure:
        verify_tls = False
    elif args.verify_tls is not None:
        verify_tls = args.verify_tls
    elif os.environ.get('ARGOCD_VERIFY_TLS', 'true').lower() == 'false':
        verify_tls = False

    if not all([server, username, password]):
        logger.error("Missing required configuration")
        logger.error("Please provide server, username, and password via arguments or environment variables")
        sys.exit(1)

    if not verify_tls:
        import urllib3
        urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)

    fetcher = ArgoCDTokenFetcher(server, username, password, verify_tls)
    
    # 1. Fetch Token
    token = fetcher.fetch_token()
    if not token:
        sys.exit(1)
        
    # 2. Validate Token
    if not fetcher.validate_token():
        logger.error("Token fetched but failed validation check")
        sys.exit(1)
        
    logger.info("Token verified successfully")
    
    # 3. Output
    if args.output == 'json':
        print(json.dumps({'token': token, 'valid': True}))
    elif args.output == 'env':
        print(f"export ARGOCD_AUTH_TOKEN='{token}'")
    else:
        print(token)

if __name__ == '__main__':
    main()
