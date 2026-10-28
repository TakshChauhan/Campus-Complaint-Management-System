import { describe, expect, it } from "vitest";
import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import App from "../App";
import { setStoredToken } from "../api/client";
import {
  DEPARTMENTS,
  HOSTEL_LOCATIONS,
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

describe("Sprint 3 Student Workflow — Feature A: Hostel Location Picker in Complaint Form", () => {
  it("renders dependent dropdowns and fetches hostel locations", async () => {
    mockApi(baseStudent);
    renderAt("/complaints/new");

    // Select Hostel department (id: 1)
    const deptSelect = await screen.findByLabelText(/^department/i, { selector: "select" });
    const user = userEvent.setup();
    await user.selectOptions(deptSelect, "1");

    // Location picker should appear with Hostel building selector
    const hostelSelect = await screen.findByLabelText(/hostel building/i, { selector: "select" });
    expect(hostelSelect).toBeInTheDocument();

    const wingSelect = screen.getByLabelText(/wing \/ block/i, { selector: "select" });
    const floorSelect = screen.getByLabelText(/floor/i, { selector: "select" });

    // Wing and floor selects should be disabled before selecting a hostel
    expect(wingSelect).toBeDisabled();
    expect(floorSelect).toBeDisabled();

    // Verify hostel options are populated from HOSTEL_LOCATIONS
    expect(screen.getByRole("option", { name: "Hostel A" })).toBeInTheDocument();
    expect(screen.getByRole("option", { name: "Hostel B" })).toBeInTheDocument();
  });

  it("handles location loading error and allows retry", async () => {
    let callCount = 0;
    mockApi({
      ...baseStudent,
      "GET /api/v1/locations/hostels": () => {
        callCount++;
        if (callCount === 1) {
          return { status: 500, body: { detail: "Failed to load locations" } };
        }
        return { body: HOSTEL_LOCATIONS };
      },
    });

    renderAt("/complaints/new");
    const user = userEvent.setup();
    const deptSelect = await screen.findByLabelText(/^department/i, { selector: "select" });
    await user.selectOptions(deptSelect, "1");

    // Should display error alert with retry button
    const retryBtn = await screen.findByRole("button", { name: /retry/i });
    expect(screen.getByText(/couldn't load hostel locations/i)).toBeInTheDocument();

    // Click retry
    await user.click(retryBtn);

    // Locations should load successfully
    expect(await screen.findByRole("option", { name: "Hostel A" })).toBeInTheDocument();
  });

  it("populates wings upon hostel selection and cascades resets when parent changes", async () => {
    mockApi(baseStudent);
    renderAt("/complaints/new");
    const user = userEvent.setup();

    const deptSelect = await screen.findByLabelText(/^department/i, { selector: "select" });
    await user.selectOptions(deptSelect, "1");

    const hostelSelect = await screen.findByLabelText(/hostel building/i, { selector: "select" });
    const wingSelect = screen.getByLabelText(/wing \/ block/i, { selector: "select" });
    const floorSelect = screen.getByLabelText(/floor/i, { selector: "select" });

    // 1. Select Hostel A (id: 1)
    await user.selectOptions(hostelSelect, "1");
    expect(wingSelect).toBeEnabled();
    expect(floorSelect).toBeDisabled();

    // Wings for Hostel A: East Wing (id: 11) and West Wing (id: 12)
    expect(screen.getByRole("option", { name: "East Wing" })).toBeInTheDocument();
    expect(screen.getByRole("option", { name: "West Wing" })).toBeInTheDocument();

    // 2. Select East Wing (id: 11)
    await user.selectOptions(wingSelect, "11");
    expect(floorSelect).toBeEnabled();

    // Floors for East Wing: First Floor (id: 101) and Second Floor (id: 102)
    expect(screen.getByRole("option", { name: "First Floor" })).toBeInTheDocument();
    expect(screen.getByRole("option", { name: "Second Floor" })).toBeInTheDocument();

    // 3. Select Second Floor (id: 102)
    await user.selectOptions(floorSelect, "102");
    expect(floorSelect).toHaveValue("102");

    // 4. Changing Wing resets Floor selection
    await user.selectOptions(wingSelect, "12"); // Switch to West Wing
    expect(floorSelect).toHaveValue("");

    // 5. Select a floor in West Wing (id: 103)
    await user.selectOptions(floorSelect, "103");
    expect(floorSelect).toHaveValue("103");

    // 6. Changing Hostel resets both Wing and Floor
    await user.selectOptions(hostelSelect, "2"); // Switch to Hostel B
    expect(wingSelect).toHaveValue("");
    expect(floorSelect).toHaveValue("");
    expect(floorSelect).toBeDisabled();
  });

  it("requires floor selection for Hostel complaints and blocks submission if missing", async () => {
    let capturedBody: any = null;
    mockApi({
      ...baseStudent,
      "POST /api/v1/complaints": (req) => {
        capturedBody = req.body;
        return {
          status: 201,
          body: {
            id: 301,
            title: "Hostel water issue",
            description: "No water in washroom since 6 AM.",
            department_id: 1,
            department_name: "Hostel",
            created_by_id: 1,
            status: "submitted",
            floor_id: 101,
            created_at: "2026-10-28T08:00:00Z",
          },
        };
      },
    });

    renderAt("/complaints/new");
    const user = userEvent.setup();

    await user.type(await screen.findByLabelText(/complaint title/i), "Hostel water issue");
    await user.type(
      screen.getByLabelText(/description/i, { selector: "textarea" }),
      "No water in washroom since 6 AM."
    );
    await user.selectOptions(screen.getByLabelText(/^department/i, { selector: "select" }), "1");

    // Try submitting without choosing a floor
    await user.click(screen.getByRole("button", { name: /submit complaint/i }));

    // Should display validation error and NOT call API
    expect(await screen.findByText(/choose your hostel floor/i)).toBeInTheDocument();
    expect(capturedBody).toBeNull();

    // Now select Hostel A -> East Wing -> First Floor (101)
    const hostelSelect = screen.getByLabelText(/hostel building/i, { selector: "select" });
    await user.selectOptions(hostelSelect, "1");

    const wingSelect = screen.getByLabelText(/wing \/ block/i, { selector: "select" });
    await user.selectOptions(wingSelect, "11");

    const floorSelect = screen.getByLabelText(/floor/i, { selector: "select" });
    await user.selectOptions(floorSelect, "101");

    // Submit now
    await user.click(screen.getByRole("button", { name: /submit complaint/i }));

    // Success screen
    expect(await screen.findByRole("heading", { name: /complaint submitted/i })).toBeInTheDocument();
    expect(capturedBody).not.toBeNull();
    expect(capturedBody.department_id).toBe(1);
    expect(capturedBody.floor_id).toBe(101);
  });

  it("submits non-hostel complaints without requiring floor_id", async () => {
    let capturedBody: any = null;
    mockApi({
      ...baseStudent,
      "POST /api/v1/complaints": (req) => {
        capturedBody = req.body;
        return {
          status: 201,
          body: {
            id: 302,
            title: "Library book catalog issue",
            description: "Terminals not turning on in library main section.",
            department_id: 3,
            department_name: "Library",
            created_by_id: 1,
            status: "submitted",
            created_at: "2026-10-28T09:00:00Z",
          },
        };
      },
    });

    renderAt("/complaints/new");
    const user = userEvent.setup();

    await user.type(await screen.findByLabelText(/complaint title/i), "Library book catalog issue");
    await user.type(
      screen.getByLabelText(/description/i, { selector: "textarea" }),
      "Terminals not turning on in library main section."
    );
    // Department 3 is Library (non-hostel)
    await user.selectOptions(screen.getByLabelText(/^department/i, { selector: "select" }), "3");

    // Submit directly without selecting hostel
    await user.click(screen.getByRole("button", { name: /submit complaint/i }));

    expect(await screen.findByRole("heading", { name: /complaint submitted/i })).toBeInTheDocument();
    expect(capturedBody.department_id).toBe(3);
    expect(capturedBody.floor_id).toBeUndefined();
  });

  it("allows optional floor_id on non-hostel complaints affecting hostel facilities", async () => {
    let capturedBody: any = null;
    mockApi({
      ...baseStudent,
      "POST /api/v1/complaints": (req) => {
        capturedBody = req.body;
        return {
          status: 201,
          body: {
            id: 303,
            title: "Wi-Fi router dead in room",
            description: "Wi-Fi access point in corridor is powered off.",
            department_id: 2,
            department_name: "IT Services",
            created_by_id: 1,
            status: "submitted",
            floor_id: 102,
            created_at: "2026-10-28T10:00:00Z",
          },
        };
      },
    });

    renderAt("/complaints/new");
    const user = userEvent.setup();

    await user.type(await screen.findByLabelText(/complaint title/i), "Wi-Fi router dead in room");
    await user.type(
      screen.getByLabelText(/description/i, { selector: "textarea" }),
      "Wi-Fi access point in corridor is powered off."
    );
    // Department 2 is IT Services
    await user.selectOptions(screen.getByLabelText(/^department/i, { selector: "select" }), "2");

    // Select optional location: Hostel A -> East Wing -> Second Floor (102)
    const hostelSelect = await screen.findByLabelText(/hostel building/i, { selector: "select" });
    await user.selectOptions(hostelSelect, "1");

    const wingSelect = screen.getByLabelText(/wing \/ block/i, { selector: "select" });
    await user.selectOptions(wingSelect, "11");

    const floorSelect = screen.getByLabelText(/floor/i, { selector: "select" });
    await user.selectOptions(floorSelect, "102");

    // Submit
    await user.click(screen.getByRole("button", { name: /submit complaint/i }));

    expect(await screen.findByRole("heading", { name: /complaint submitted/i })).toBeInTheDocument();
    expect(capturedBody.department_id).toBe(2);
    expect(capturedBody.floor_id).toBe(102);
  });
});
