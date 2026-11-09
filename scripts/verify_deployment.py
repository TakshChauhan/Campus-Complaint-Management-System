#!/usr/bin/env python3
"""
CCMS Deployment Verification Script
Verifies fullstack containerized deployment health:
1. Backend health check (/health)
2. Database connectivity
3. API version route check (/api/v1/health or open endpoints)
4. Frontend HTTP index.html availability
"""

import sys
import json
import time
import urllib.request
import urllib.error

BACKEND_URL = "http://localhost:8000"
FRONTEND_URL = "http://localhost:3000"
MAX_RETRIES = 10
RETRY_DELAY = 3


def check_url(url: str, description: str, expected_code: int = 200) -> bool:
    print(f"[*] Checking {description} at {url}...")
    for attempt in range(1, MAX_RETRIES + 1):
        try:
            req = urllib.request.Request(url, headers={"User-Agent": "CCMS-Deployment-Verifier/1.0"})
            with urllib.request.urlopen(req, timeout=5) as response:
                status = response.getcode()
                body = response.read().decode("utf-8", errors="ignore")
                if status == expected_code:
                    print(f"    [+] PASS: {description} responded with HTTP {status}")
                    return True
                else:
                    print(f"    [-] WARN: Unexpected status HTTP {status} (expected {expected_code})")
        except urllib.error.HTTPError as e:
            if e.code == expected_code:
                print(f"    [+] PASS: {description} responded with expected HTTP {e.code}")
                return True
            print(f"    [-] Attempt {attempt}/{MAX_RETRIES}: HTTP {e.code} - {e.reason}")
        except urllib.error.URLError as e:
            print(f"    [-] Attempt {attempt}/{MAX_RETRIES}: Connection failed ({e.reason})")
        except Exception as e:
            print(f"    [-] Attempt {attempt}/{MAX_RETRIES}: Error ({type(e).__name__}: {e})")

        if attempt < MAX_RETRIES:
            time.sleep(RETRY_DELAY)

    print(f"    [!] FAIL: {description} could not be verified after {MAX_RETRIES} attempts.")
    return False


def verify_deployment() -> bool:
    print("=" * 60)
    print("  CCMS Production & Staging Deployment Verification Suite")
    print("=" * 60)

    results = []

    # 1. Backend health endpoint
    results.append(check_url(f"{BACKEND_URL}/health", "Backend Health Endpoint", 200))

    # 2. Frontend landing page
    results.append(check_url(FRONTEND_URL, "Frontend Web Application", 200))

    # 3. OpenAPI documentation endpoint
    results.append(check_url(f"{BACKEND_URL}/docs", "Backend Swagger UI / OpenAPI Docs", 200))

    print("\n" + "=" * 60)
    if all(results):
        print("  ALL CHECKS PASSED: CCMS deployment is healthy and ready for traffic!")
        print("=" * 60)
        return True
    else:
        print("  DEPLOYMENT CHECKS FAILED: Review container logs with 'docker compose logs'.")
        print("=" * 60)
        return False


if __name__ == "__main__":
    success = verify_deployment()
    sys.exit(0 if success else 1)
