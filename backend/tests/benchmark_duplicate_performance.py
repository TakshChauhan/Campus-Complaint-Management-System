"""Opt-in local benchmark for duplicate suggestions with 1,000 complaints."""

from datetime import datetime, timezone
from math import ceil
from statistics import mean, median
from time import perf_counter

from app.models.complaint import Complaint
from app.models.hostel import Hostel
from app.models.hostel_wing import HostelWing
from app.models.hostel_floor import HostelFloor
from app.models.student_residence import StudentResidence

URL = "/api/v1/complaints/duplicate-suggestions"
REQUEST = {
    "title": "Hostel wifi router broken",
    "description": "The hostel wifi router is broken and internet is unavailable.",
}


def test_benchmark_duplicate_endpoint_with_1000_complaints(
    client, db, seeded_departments, student_user, student_b_user,
    student_headers,
):
    # Build an active, verified residence for the requesting student.
    hostel = Hostel(code="BENCH_HOSTEL", name="Benchmark Hostel", is_active=True)
    db.add(hostel)
    db.flush()

    wing = HostelWing(
        hostel_id=hostel.id, code="A", name="Wing A", is_active=True
    )
    db.add(wing)
    db.flush()

    floor = HostelFloor(
        wing_id=wing.id, code="F1", name="Floor 1", is_active=True
    )
    db.add(floor)
    db.flush()

    db.add(
        StudentResidence(
            student_id=student_user.id,
            floor_id=floor.id,
            status="verified",
            verified_by_id=student_b_user.id,
            verified_at=datetime.now(timezone.utc),
        )
    )

    # Seed 1,000 eligible public complaints on the same floor.
    complaints = []
    for i in range(1000):
        complaints.append(
            Complaint(
                title=f"Hostel Wi-Fi router connectivity issue {i}",
                description=(
                    f"Internet connection is unstable in hostel room {i}. "
                    "The Wi-Fi router disconnects frequently."
                ),
                department_id=seeded_departments["hostel"].id,
                created_by_id=student_b_user.id,
                status="submitted",
                is_public=True,
                floor_id=floor.id,
            )
        )

    db.add_all(complaints)
    db.commit()

    # Warm-up request: exclude it from the reported timings.
    warmup = client.post(URL, json=REQUEST, headers=student_headers)
    assert warmup.status_code == 200, warmup.text

    timings_ms = []
    for _ in range(10):
        start = perf_counter()
        response = client.post(URL, json=REQUEST, headers=student_headers)
        elapsed_ms = (perf_counter() - start) * 1000

        assert response.status_code == 200, response.text
        timings_ms.append(elapsed_ms)

    ordered = sorted(timings_ms)
    p95 = ordered[ceil(0.95 * len(ordered)) - 1]

    print("\n=== Duplicate API Benchmark ===")
    print("Eligible complaints: 1,000")
    print("Timed requests: 10 (plus 1 warm-up)")
    print(f"Average: {mean(timings_ms):.2f} ms")
    print(f"Median:  {median(timings_ms):.2f} ms")
    print(f"P95:     {p95:.2f} ms")
    print(f"Maximum: {max(timings_ms):.2f} ms")
