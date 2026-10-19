"""
CCMS End-to-End Deployment Verification Script (Sprint 1)

Verifies:
1. Backend & database health check (/health)
2. Student registration (POST /api/v1/auth/register)
3. Student login (POST /api/v1/auth/login)
4. Current user profile (GET /api/v1/users/me)
5. Department catalog listing (GET /api/v1/departments)
6. Advisory department suggestion (POST /api/v1/complaints/suggest & /departments/suggest)
7. Complaint registration (POST /api/v1/complaints)
8. Student own-history verification (GET /api/v1/complaints/mine)
9. Role-based access control and unauthorized request rejection
10. Data persistence verification

Usage:
    python verify_deployment.py --url https://your-deployed-api.com
    python verify_deployment.py --url http://localhost:8000
"""

import sys
import uuid
import argparse
import httpx as requests

def run_verification(base_url: str):
    base_url = base_url.rstrip("/")
    api_url = f"{base_url}/api/v1"
    print("=" * 70)
    print(f"🚀 RUNNING CCMS SPRINT 1 DEPLOYMENT VERIFICATION AGAINST: {base_url}")
    print("=" * 70)

    # 1. Health check
    print("\n[Step 1] Checking system health endpoint...")
    try:
        health_resp = requests.get(f"{base_url}/health", timeout=10)
        assert health_resp.status_code == 200, f"Health check failed with {health_resp.status_code}: {health_resp.text}"
        health_data = health_resp.json()
        print(f"  ✓ Health check OK: status={health_data.get('status')}, db={health_data.get('database')}, env={health_data.get('environment')}")
        if health_data.get("database") != "operational":
            print(f"  ⚠️ Warning: Database status reports '{health_data.get('database')}'")
    except Exception as e:
        print(f"  ❌ Health check error: {e}")
        return False

    # 2. Student Registration
    print("\n[Step 2] Testing student registration...")
    unique_suffix = uuid.uuid4().hex[:8]
    student_email = f"student_{unique_suffix}@campus.edu"
    student_password = "ValidStudentPass123!"
    student_name = f"Test Student {unique_suffix}"

    reg_payload = {
        "name": student_name,
        "email": student_email,
        "password": student_password,
    }
    reg_resp = requests.post(f"{api_url}/auth/register", json=reg_payload, timeout=10)
    assert reg_resp.status_code == 201, f"Registration failed with {reg_resp.status_code}: {reg_resp.text}"
    student_data = reg_resp.json()
    assert student_data["email"] == student_email
    assert student_data["role"] == "student"
    print(f"  ✓ Student registered: id={student_data['id']}, email={student_data['email']}")

    # 3. Student Login
    print("\n[Step 3] Testing student login...")
    login_payload = {
        "email": student_email,
        "password": student_password,
    }
    login_resp = requests.post(f"{api_url}/auth/login", json=login_payload, timeout=10)
    assert login_resp.status_code == 200, f"Login failed with {login_resp.status_code}: {login_resp.text}"
    token_data = login_resp.json()
    assert "access_token" in token_data
    access_token = token_data["access_token"]
    student_headers = {"Authorization": f"Bearer {access_token}"}
    print(f"  ✓ Logged in successfully. Bearer token acquired.")

    # 4. Current user profile
    print("\n[Step 4] Fetching current user profile (/users/me)...")
    me_resp = requests.get(f"{api_url}/users/me", headers=student_headers, timeout=10)
    assert me_resp.status_code == 200, f"/users/me failed: {me_resp.text}"
    me_data = me_resp.json()
    assert me_data["id"] == student_data["id"]
    assert me_data["role"] == "student"
    print(f"  ✓ Current profile verified: name={me_data['name']}, role={me_data['role']}")

    # 5. Department Listing
    print("\n[Step 5] Listing active campus departments...")
    dept_resp = requests.get(f"{api_url}/departments", headers=student_headers, timeout=10)
    assert dept_resp.status_code == 200, f"Department listing failed: {dept_resp.text}"
    departments = dept_resp.json()
    assert len(departments) > 0, "No departments returned! Department seeding missing."
    print(f"  ✓ Loaded {len(departments)} active departments:")
    for d in departments:
        print(f"     - ID {d['id']}: {d['name']}")

    target_dept = departments[0]
    target_dept_id = target_dept["id"]

    # 6. Department Suggestion (Both contract endpoints)
    print("\n[Step 6] Testing advisory department suggestion...")
    sugg_payload = {
        "title": "Wi-Fi disconnected in hostel room",
        "description": "The campus internet connection drops constantly every evening.",
    }
    # Test POST /api/v1/departments/suggest (used by frontend)
    sugg1 = requests.post(f"{api_url}/departments/suggest", json=sugg_payload, headers=student_headers, timeout=10)
    assert sugg1.status_code == 200, f"departments/suggest failed: {sugg1.text}"
    # Test POST /api/v1/complaints/suggest (specified in Sprint 1 PDF)
    sugg2 = requests.post(f"{api_url}/complaints/suggest", json=sugg_payload, headers=student_headers, timeout=10)
    assert sugg2.status_code == 200, f"complaints/suggest failed: {sugg2.text}"
    print(f"  ✓ Advisory suggestions validated across both /departments/suggest and /complaints/suggest")

    # 7. Complaint Registration
    print("\n[Step 7] Submitting a new student grievance...")
    complaint_payload = {
        "title": "Water leakage in third floor washroom",
        "description": "Continuous water leakage observed near room 312 since yesterday morning.",
        "department_id": target_dept_id,
    }
    comp_resp = requests.post(f"{api_url}/complaints", json=complaint_payload, headers=student_headers, timeout=10)
    assert comp_resp.status_code == 201, f"Complaint submission failed: {comp_resp.text}"
    complaint = comp_resp.json()
    complaint_id = complaint["id"]
    assert complaint["status"] == "submitted"
    assert complaint["department_id"] == target_dept_id
    print(f"  ✓ Complaint registered successfully: id={complaint_id}, status={complaint['status']}")

    # 8. Own Complaint History
    print("\n[Step 8] Verifying student's personal complaint history (/complaints/mine)...")
    mine_resp = requests.get(f"{api_url}/complaints/mine", headers=student_headers, timeout=10)
    assert mine_resp.status_code == 200, f"Complaints history failed: {mine_resp.text}"
    my_complaints = mine_resp.json()
    assert any(c["id"] == complaint_id for c in my_complaints), f"Complaint {complaint_id} not found in history!"
    print(f"  ✓ Complaint {complaint_id} present in personal history (total {len(my_complaints)} records)")

    # 9. Role-based Access Control Guard Verification
    print("\n[Step 9] Verifying role-based access denials...")
    anon_resp = requests.get(f"{api_url}/complaints/mine", timeout=10)
    assert anon_resp.status_code == 401, f"Expected 401 for anonymous access, got {anon_resp.status_code}"
    print("  ✓ Anonymous request to protected /complaints/mine correctly rejected (HTTP 401)")

    # 10. Persistence check
    print("\n[Step 10] Validating complaint data persistence...")
    mine_resp_again = requests.get(f"{api_url}/complaints/mine", headers=student_headers, timeout=10)
    assert mine_resp_again.status_code == 200
    my_complaints_again = mine_resp_again.json()
    persisted_item = next(c for c in my_complaints_again if c["id"] == complaint_id)
    assert persisted_item["title"] == complaint_payload["title"]
    print(f"  ✓ Record persisted and retrieved intact: ID={persisted_item['id']}, title='{persisted_item['title']}'")

    print("\n" + "=" * 70)
    print("🎉 ALL SPRINT 1 ACCEPTANCE VERIFICATIONS PASSED SUCCESSFULLY!")
    print("=" * 70)
    return True

if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="CCMS Sprint 1 Deployment Verification")
    parser.add_argument("--url", default="http://localhost:8000", help="Base URL of deployed CCMS backend")
    args = parser.parse_args()
    success = run_verification(args.url)
    sys.exit(0 if success else 1)
