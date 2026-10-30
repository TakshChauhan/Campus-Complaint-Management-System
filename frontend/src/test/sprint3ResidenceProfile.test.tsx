import { describe, expect, it } from "vitest";
import { render, screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import App from "../App";
import { setStoredToken } from "../api/client";
import {
  DEPARTMENTS,
  HOSTEL_LOCATIONS,
  makeResidence,
  makeToken,
  makeUser,
  mockApi,
} from "./mockApi";

function renderAt(path: string) {
  setStoredToken(makeToken());
  window.history.replaceState(null, "", path);
  return render(<App />);
}

const baseStudent = {
  "GET /api/v1/users/me": () => ({ body: makeUser({ role: "student" }) }),
  "GET /api/v1/departments": () => ({ body: DEPARTMENTS }),
  "GET /api/v1/locations/hostels": () => ({ body: HOSTEL_LOCATIONS }),
  "GET /api/v1/users/me/residence": () => ({ status: 404, body: null }),
};

describe("Sprint 3 Student Workflow — Feature B: Student Residence Profile", () => {
  it("renders empty residence state when student has not declared residence yet", async () => {
    mockApi(baseStudent);
    renderAt("/profile");

    expect(await screen.findByText(/no residence declared/i)).toBeInTheDocument();
    expect(screen.getByRole("button", { name: /declare residence/i })).toBeInTheDocument();
  });

  it("displays saved verified residence with verification badge", async () => {
    mockApi({
      ...baseStudent,
      "GET /api/v1/users/me/residence": () => ({
        body: makeResidence({
          floor_id: 102,
          hostel: "Hostel A",
          wing: "East Wing",
          floor: "Second Floor",
          status: "verified",
        }),
      }),
    });

    renderAt("/profile");

    expect(await screen.findByText("Hostel A")).toBeInTheDocument();
    expect(screen.getByText("East Wing")).toBeInTheDocument();
    expect(screen.getByText("Second Floor")).toBeInTheDocument();
    const residenceSection = screen.getByRole("heading", { name: /hostel residence/i }).closest("section")!;
    expect(within(residenceSection).getByText("Verified")).toBeInTheDocument();
    expect(screen.getByRole("button", { name: /change residence/i })).toBeInTheDocument();
  });

  it("displays rejected status with staff remark prominently", async () => {
    mockApi({
      ...baseStudent,
      "GET /api/v1/users/me/residence": () => ({
        body: makeResidence({
          floor_id: 102,
          hostel: "Hostel A",
          wing: "East Wing",
          floor: "Second Floor",
          status: "rejected",
          remark: "Room allotment shows student in Block B, not Block A.",
        }),
      }),
    });

    renderAt("/profile");

    expect(await screen.findByText(/residence verification rejected/i)).toBeInTheDocument();
    expect(
      screen.getByText(/Room allotment shows student in Block B, not Block A./i)
    ).toBeInTheDocument();
  });

  it("displays pending status with review notice", async () => {
    mockApi({
      ...baseStudent,
      "GET /api/v1/users/me/residence": () => ({
        body: makeResidence({
          floor_id: 101,
          hostel: "Hostel A",
          wing: "East Wing",
          floor: "First Floor",
          status: "pending",
          remark: null,
        }),
      }),
    });

    renderAt("/profile");

    expect(await screen.findByText(/verification pending/i)).toBeInTheDocument();
    expect(screen.getByText(/under review by hostel administration/i)).toBeInTheDocument();
  });

  it("allows student to declare initial residence via PATCH /api/v1/users/me/residence", async () => {
    let capturedBody: any = null;
    mockApi({
      ...baseStudent,
      "GET /api/v1/users/me/residence": () => ({ status: 404, body: null }),
      "PATCH /api/v1/users/me/residence": (req) => {
        capturedBody = req.body;
        return {
          status: 200,
          body: {
            floor_id: 202,
            hostel: "Hostel B",
            wing: "North Wing",
            floor: "First Floor",
            status: "pending",
            remark: null,
          },
        };
      },
    });

    renderAt("/profile");
    const user = userEvent.setup();

    // Click "Declare residence"
    const declareBtn = await screen.findByRole("button", { name: /declare residence/i });
    await user.click(declareBtn);

    // Verification notice should be visible
    expect(screen.getByText(/verification reset notice/i)).toBeInTheDocument();

    // Select Hostel B (2) -> North Wing (21) -> First Floor (202)
    const hostelSelect = await screen.findByLabelText(/hostel building/i, { selector: "select" });
    await user.selectOptions(hostelSelect, "2");

    const wingSelect = screen.getByLabelText(/wing \/ block/i, { selector: "select" });
    await user.selectOptions(wingSelect, "21");

    const floorSelect = screen.getByLabelText(/floor/i, { selector: "select" });
    await user.selectOptions(floorSelect, "202");

    // Save
    await user.click(screen.getByRole("button", { name: /save residence/i }));

    // Expect PATCH request with floor_id: 202
    await waitFor(() => {
      expect(capturedBody).toEqual({ floor_id: 202 });
    });

    // Success banner & updated state
    expect(await screen.findByText(/residence updated successfully/i)).toBeInTheDocument();
    expect(screen.getByText("Hostel B")).toBeInTheDocument();
    expect(screen.getByText("North Wing")).toBeInTheDocument();
  });

  it("allows changing an existing residence and resets status to pending", async () => {
    let patchCount = 0;
    mockApi({
      ...baseStudent,
      "GET /api/v1/users/me/residence": () => ({
        body: makeResidence({
          floor_id: 101,
          hostel: "Hostel A",
          wing: "East Wing",
          floor: "First Floor",
          status: "verified",
        }),
      }),
      "PATCH /api/v1/users/me/residence": (req) => {
        patchCount++;
        return {
          status: 200,
          body: {
            floor_id: 104,
            hostel: "Hostel A",
            wing: "West Wing",
            floor: "Second Floor",
            status: "pending",
            remark: null,
          },
        };
      },
    });

    renderAt("/profile");
    const user = userEvent.setup();

    // Click "Change residence"
    const changeBtn = await screen.findByRole("button", { name: /change residence/i });
    await user.click(changeBtn);

    // Notice explaining reset to pending
    expect(screen.getByText(/verification reset notice/i)).toBeInTheDocument();

    // Switch to West Wing (12) -> Second Floor (104)
    const wingSelect = await screen.findByLabelText(/wing \/ block/i, { selector: "select" });
    await user.selectOptions(wingSelect, "12");

    const floorSelect = screen.getByLabelText(/floor/i, { selector: "select" });
    await user.selectOptions(floorSelect, "104");

    // Click "Save residence"
    await user.click(screen.getByRole("button", { name: /save residence/i }));

    await waitFor(() => {
      expect(patchCount).toBe(1);
    });

    expect(await screen.findByText(/residence updated successfully/i)).toBeInTheDocument();
    expect(screen.getByText("West Wing")).toBeInTheDocument();
  });

  it("handles residence save failure gracefully without losing form state", async () => {
    mockApi({
      ...baseStudent,
      "GET /api/v1/users/me/residence": () => ({ status: 404, body: null }),
      "PATCH /api/v1/users/me/residence": () => ({
        status: 422,
        body: { detail: "Invalid or inactive floor_id." },
      }),
    });

    renderAt("/profile");
    const user = userEvent.setup();

    const declareBtn = await screen.findByRole("button", { name: /declare residence/i });
    await user.click(declareBtn);

    const hostelSelect = await screen.findByLabelText(/hostel building/i, { selector: "select" });
    await user.selectOptions(hostelSelect, "1");

    const wingSelect = screen.getByLabelText(/wing \/ block/i, { selector: "select" });
    await user.selectOptions(wingSelect, "11");

    const floorSelect = screen.getByLabelText(/floor/i, { selector: "select" });
    await user.selectOptions(floorSelect, "101");

    await user.click(screen.getByRole("button", { name: /save residence/i }));

    // Error message from API
    expect(await screen.findByText(/invalid or inactive floor_id/i)).toBeInTheDocument();

    // Form should still be open with selections intact
    expect(screen.getByRole("button", { name: /save residence/i })).toBeInTheDocument();
  });
});
