import { describe, expect, it, vi } from "vitest";
import { render, screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import App from "../App";
import { setStoredToken } from "../api/client";
import { DEPARTMENTS, makeToken, makeUser, mockApi } from "./mockApi";

function renderAt(path: string) {
  setStoredToken(makeToken());
  window.history.replaceState(null, "", path);
  return render(<App />);
}

const base = {
  "GET /api/v1/users/me": () => ({ body: makeUser() }),
  "GET /api/v1/departments": () => ({ body: DEPARTMENTS }),
};

describe("Sprint 2 Student Workflow — Feature A: Enhanced Raise Complaint Form", () => {
  it("defaults to private visibility and allows switching to public", async () => {
    let capturedBody: any = null;
    mockApi({
      ...base,
      "POST /api/v1/complaints": (req) => {
        capturedBody = req.body;
        return {
          status: 201,
          body: {
            id: 201,
            title: "Test private complaint",
            description: "Test description for private complaint",
            department_id: 2,
            department_name: "IT Services",
            created_by_id: 1,
            status: "submitted",
            is_public: false,
            created_at: "2026-10-23T10:00:00Z",
          },
        };
      },
    });

    const user = userEvent.setup();
    renderAt("/complaints/new");

    await user.type(await screen.findByLabelText(/complaint title/i), "Test private complaint");
    await user.type(
      screen.getByLabelText(/description/i, { selector: "textarea" }),
      "Test description for private complaint"
    );
    await user.selectOptions(await screen.findByLabelText(/^department/i, { selector: "select" }), "2");

    // Verify private radio is checked by default
    const privateRadio = screen.getByLabelText(/private complaint/i);
    expect(privateRadio).toBeChecked();

    // Submit and verify is_public: false in payload
    await user.click(screen.getByRole("button", { name: /submit complaint/i }));
    await screen.findByRole("heading", { name: /complaint submitted/i });

    expect(capturedBody.is_public).toBe(false);
  });

  it("sends is_public: true when public visibility is chosen", async () => {
    let capturedBody: any = null;
    mockApi({
      ...base,
      "POST /api/v1/complaints": (req) => {
        capturedBody = req.body;
        return {
          status: 201,
          body: {
            id: 202,
            title: "Public library issue",
            description: "Terminals not working in the library main hall.",
            department_id: 3,
            department_name: "Library",
            created_by_id: 1,
            status: "submitted",
            is_public: true,
            created_at: "2026-10-23T10:00:00Z",
          },
        };
      },
    });

    const user = userEvent.setup();
    renderAt("/complaints/new");

    await user.type(await screen.findByLabelText(/complaint title/i), "Public library issue");
    await user.type(
      screen.getByLabelText(/description/i, { selector: "textarea" }),
      "Terminals not working in the library main hall."
    );
    await user.selectOptions(await screen.findByLabelText(/^department/i, { selector: "select" }), "3");

    // Select public visibility
    const publicRadio = screen.getByLabelText(/public complaint/i);
    await user.click(publicRadio);
    expect(publicRadio).toBeChecked();

    await user.click(screen.getByRole("button", { name: /submit complaint/i }));
    await screen.findByRole("heading", { name: /complaint submitted/i });

    expect(capturedBody.is_public).toBe(true);
    expect(screen.getByText(/public \(visible in campus feed\)/i)).toBeInTheDocument();
  });

  it("conditionally shows accommodation fields for Hostel department and sends them in payload", async () => {
    let capturedBody: any = null;
    mockApi({
      ...base,
      "POST /api/v1/complaints": (req) => {
        capturedBody = req.body;
        return {
          status: 201,
          body: {
            id: 203,
            title: "Leaking shower tap",
            description: "Shower tap in hostel has been dripping continuously.",
            department_id: 1,
            department_name: "Hostel",
            created_by_id: 1,
            status: "submitted",
            hostel: "Block C",
            wing: "Wing B",
            floor: "2nd Floor",
            created_at: "2026-10-23T10:00:00Z",
          },
        };
      },
    });

    const user = userEvent.setup();
    renderAt("/complaints/new");

    // When department is not hostel, accommodation fields are hidden
    expect(screen.queryByLabelText(/hostel building/i)).not.toBeInTheDocument();

    await user.type(await screen.findByLabelText(/complaint title/i), "Leaking shower tap");
    await user.type(
      screen.getByLabelText(/description/i, { selector: "textarea" }),
      "Shower tap in hostel has been dripping continuously."
    );

    // Select Hostel department (id 1)
    await user.selectOptions(await screen.findByLabelText(/^department/i, { selector: "select" }), "1");

    // Accommodation fields should now be visible
    expect(await screen.findByLabelText(/hostel building/i)).toBeInTheDocument();
    expect(screen.getByLabelText(/wing/i)).toBeInTheDocument();
    expect(screen.getByLabelText(/floor/i)).toBeInTheDocument();

    // Fill optional accommodation fields
    await user.type(screen.getByLabelText(/hostel building/i), "Block C");
    await user.type(screen.getByLabelText(/wing/i), "Wing B");
    await user.type(screen.getByLabelText(/floor/i), "2nd Floor");

    await user.click(screen.getByRole("button", { name: /submit complaint/i }));
    await screen.findByRole("heading", { name: /complaint submitted/i });

    expect(capturedBody.hostel).toBe("Block C");
    expect(capturedBody.wing).toBe("Wing B");
    expect(capturedBody.floor).toBe("2nd Floor");
    expect(screen.getByText("Block C")).toBeInTheDocument();
  });
});

describe("Sprint 2 Student Workflow — Feature B: Duplicate Complaint Warning", () => {
  it("renders duplicate warning panel and allows user to submit anyway", async () => {
    let submitted = false;
    mockApi({
      ...base,
      "POST /api/v1/complaints/duplicate-suggestions": () => ({
        status: 200,
        body: {
          matches: [
            {
              id: 99,
              title: "Broken Wi-Fi in Hostel Block C",
              department_id: 1,
              department_name: "Hostel",
              status: "in_progress",
              similarity_score: 0.88,
              description_snippet: "Wi-Fi is not working on 2nd floor since yesterday.",
            },
          ],
        },
      }),
      "POST /api/v1/complaints": () => {
        submitted = true;
        return {
          status: 201,
          body: {
            id: 204,
            title: "Wi-Fi issue in Hostel Block C",
            description: "The internet connection keeps dropping in Block C common room.",
            department_id: 1,
            department_name: "Hostel",
            created_by_id: 1,
            status: "submitted",
            created_at: "2026-10-23T10:00:00Z",
          },
        };
      },
    });

    const user = userEvent.setup();
    renderAt("/complaints/new");

    await user.type(await screen.findByLabelText(/complaint title/i), "Wi-Fi issue in Hostel Block C");
    await user.type(
      screen.getByLabelText(/description/i, { selector: "textarea" }),
      "The internet connection keeps dropping in Block C common room."
    );
    await user.selectOptions(await screen.findByLabelText(/^department/i, { selector: "select" }), "1");

    // Wait for debounced duplicate warning panel to appear
    const warning = await screen.findByRole("region", { name: /duplicate complaints warning/i });
    expect(warning).toBeInTheDocument();
    expect(within(warning).getByText("Broken Wi-Fi in Hostel Block C")).toBeInTheDocument();
    expect(within(warning).getByText("88%")).toBeInTheDocument();

    // Click "Submit anyway" action
    const submitAnywayBtn = within(warning).getByRole("button", { name: /submit anyway/i });
    await user.click(submitAnywayBtn);

    await screen.findByRole("heading", { name: /complaint submitted/i });
    expect(submitted).toBe(true);
  });

  it("submits smoothly if duplicate suggestions API returns error (non-blocking)", async () => {
    let submitted = false;
    mockApi({
      ...base,
      "POST /api/v1/complaints/duplicate-suggestions": () => ({
        status: 503,
        body: { detail: "Service temporarily unavailable" },
      }),
      "POST /api/v1/complaints": () => {
        submitted = true;
        return {
          status: 201,
          body: {
            id: 205,
            title: "Water filter leakage",
            description: "Water cooler on 1st floor is leaking heavily.",
            department_id: 1,
            department_name: "Hostel",
            created_by_id: 1,
            status: "submitted",
            created_at: "2026-10-23T10:00:00Z",
          },
        };
      },
    });

    const user = userEvent.setup();
    renderAt("/complaints/new");

    await user.type(await screen.findByLabelText(/complaint title/i), "Water filter leakage");
    await user.type(
      screen.getByLabelText(/description/i, { selector: "textarea" }),
      "Water cooler on 1st floor is leaking heavily."
    );
    await user.selectOptions(await screen.findByLabelText(/^department/i, { selector: "select" }), "1");

    // Click submit - should submit without being blocked by duplicate error
    await user.click(screen.getByRole("button", { name: /submit complaint/i }));
    await screen.findByRole("heading", { name: /complaint submitted/i });
    expect(submitted).toBe(true);
  });
});

describe("Sprint 2 Student Workflow — Feature C: Complaint Status History Timeline", () => {
  it("displays status events in chronological order with timestamps and remarks", async () => {
    mockApi({
      ...base,
      "GET /api/v1/complaints/10": () => ({
        body: {
          id: 10,
          title: "Lab printer out of paper",
          description: "Printer 2 in Lab 1 has no paper.",
          department_id: 2,
          department_name: "IT Services",
          created_by_id: 1,
          status: "in_progress",
          created_at: "2026-10-20T08:00:00Z",
        },
      }),
      "GET /api/v1/complaints/10/history": () => ({
        body: [
          {
            id: 1,
            from_status: null,
            to_status: "submitted",
            actor_id: 1,
            remark: null,
            created_at: "2026-10-20T08:00:00Z",
          },
          {
            id: 2,
            from_status: "submitted",
            to_status: "in_progress",
            actor_id: 4,
            remark: "Investigation started by IT staff.",
            created_at: "2026-10-20T09:30:00Z",
          },
        ],
      }),
    });

    renderAt("/complaints/10");

    await screen.findByRole("heading", { name: "Lab printer out of paper" });
    const timeline = await screen.findByRole("region", { name: /status history timeline/i });
    expect(timeline).toBeInTheDocument();

    expect(within(timeline).getAllByText("Submitted").length).toBeGreaterThanOrEqual(1);
    expect(within(timeline).getByText("In progress")).toBeInTheDocument();
    expect(within(timeline).getByText(/Investigation started by IT staff/)).toBeInTheDocument();
  });

  it("handles empty history gracefully", async () => {
    mockApi({
      ...base,
      "GET /api/v1/complaints/11": () => ({
        body: {
          id: 11,
          title: "New grievance",
          description: "New issue description here.",
          department_id: 2,
          department_name: "IT Services",
          created_by_id: 1,
          status: "submitted",
          created_at: "2026-10-23T08:00:00Z",
        },
      }),
      "GET /api/v1/complaints/11/history": () => ({
        body: [],
      }),
    });

    renderAt("/complaints/11");

    await screen.findByRole("heading", { name: "New grievance" });
    expect(await screen.findByText(/no status change events recorded yet/i)).toBeInTheDocument();
  });
});

describe("Sprint 2 Student Workflow — Feature D: Conditional Reopen Button", () => {
  it("shows Reopen button only when complaint status is resolved", async () => {
    mockApi({
      ...base,
      "GET /api/v1/complaints/12": () => ({
        body: {
          id: 12,
          title: "Resolved classroom projector",
          description: "Projector bulb replaced.",
          department_id: 2,
          department_name: "IT Services",
          created_by_id: 1,
          status: "resolved",
          reopen_count: 0,
          resolved_at: new Date().toISOString(),
          created_at: "2026-10-18T10:00:00Z",
        },
      }),
      "GET /api/v1/complaints/12/history": () => ({
        body: [],
      }),
    });

    renderAt("/complaints/12");

    await screen.findByRole("heading", { name: "Resolved classroom projector" });
    expect(screen.getByRole("button", { name: /reopen complaint/i })).toBeInTheDocument();
  });

  it("hides Reopen button when complaint is already in_progress or submitted", async () => {
    mockApi({
      ...base,
      "GET /api/v1/complaints/13": () => ({
        body: {
          id: 13,
          title: "In progress complaint",
          description: "Work ongoing.",
          department_id: 2,
          department_name: "IT Services",
          created_by_id: 1,
          status: "in_progress",
          created_at: "2026-10-20T10:00:00Z",
        },
      }),
      "GET /api/v1/complaints/13/history": () => ({
        body: [],
      }),
    });

    renderAt("/complaints/13");

    await screen.findByRole("heading", { name: "In progress complaint" });
    expect(screen.queryByRole("button", { name: /reopen complaint/i })).not.toBeInTheDocument();
  });

  it("successfully reopens a resolved complaint, sends remark, and refreshes status", async () => {
    let reopened = false;
    let complaintStatus = "resolved";

    mockApi({
      ...base,
      "GET /api/v1/complaints/14": () => ({
        body: {
          id: 14,
          title: "Flickering tube light",
          description: "Tube light in Lab 2 still flickers intermittently.",
          department_id: 2,
          department_name: "IT Services",
          created_by_id: 1,
          status: complaintStatus,
          reopen_count: complaintStatus === "reopened" ? 1 : 0,
          resolved_at: complaintStatus === "resolved"
            ? new Date().toISOString()
            : null,
          created_at: "2026-10-19T10:00:00Z",
        },
      }),
      "GET /api/v1/complaints/14/history": () => ({
        body:
          complaintStatus === "reopened"
            ? [
                {
                  id: 1,
                  from_status: "resolved",
                  to_status: "reopened",
                  actor_id: 1,
                  remark: "Issue recurred after two days.",
                  created_at: "2026-10-23T11:00:00Z",
                },
              ]
            : [],
      }),
      "POST /api/v1/complaints/14/reopen": (req) => {
        reopened = true;
        complaintStatus = "reopened";
        return {
          status: 200,
          body: {
            id: 14,
            status: "reopened",
            reopen_count: 1,
            updated_at: "2026-10-23T11:00:00Z",
            resolved_at: null,
          },
        };
      },
    });

    const user = userEvent.setup();
    renderAt("/complaints/14");

    await screen.findByRole("heading", { name: "Flickering tube light" });

    // Click Reopen button to show form
    const reopenBtn = screen.getByRole("button", { name: /reopen complaint/i });
    await user.click(reopenBtn);

    // Enter optional remark
    const remarkInput = screen.getByLabelText(/reason for reopening/i);
    await user.type(remarkInput, "Issue recurred after two days.");

    // Submit reopen
    await user.click(screen.getByRole("button", { name: /confirm reopen/i }));

    expect(reopened).toBe(true);
    expect(await screen.findByText(/complaint reopened successfully/i)).toBeInTheDocument();
  });
});

describe("Sprint 2 Student Workflow — Reopen Policy Restrictions", () => {
  it.each([
    {
      name: "resolution older than seven days",
      reopen_count: 0,
      resolved_at: new Date(Date.now() - 8 * 86400000).toISOString(),
    },
    {
      name: "maximum of two reopens reached",
      reopen_count: 2,
      resolved_at: new Date().toISOString(),
    },
    {
      name: "missing resolution timestamp",
      reopen_count: 0,
      resolved_at: null,
    },
    {
      name: "resolution timestamp in the future",
      reopen_count: 0,
      resolved_at: new Date(Date.now() + 86400000).toISOString(),
    },
  ])("hides the reopen button when $name", async ({
    reopen_count,
    resolved_at,
  }) => {
    mockApi({
      ...base,
      "GET /api/v1/complaints/15": () => ({
        body: {
          id: 15,
          title: "Resolved hostel maintenance complaint",
          description: "Maintenance was completed earlier.",
          department_id: 1,
          department_name: "Hostel",
          created_by_id: 1,
          status: "resolved",
          reopen_count,
          resolved_at,
          created_at: "2026-10-01T10:00:00Z",
        },
      }),
      "GET /api/v1/complaints/15/history": () => ({
        body: [],
      }),
    });

    renderAt("/complaints/15");

    await screen.findByRole("heading", {
      name: "Resolved hostel maintenance complaint",
    });

    expect(
      screen.queryByRole("button", {
        name: /reopen complaint/i,
      })
    ).not.toBeInTheDocument();
  });
});
