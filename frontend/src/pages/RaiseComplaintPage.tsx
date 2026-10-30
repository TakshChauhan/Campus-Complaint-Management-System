import React, { useCallback, useEffect, useRef, useState } from "react";
import { getDepartmentsApi, suggestDepartmentApi } from "../api/departments";
import { createComplaintApi, getDuplicateSuggestionsApi } from "../api/complaints";
import { ApiClientError, errorMessage, fieldFromLoc } from "../api/client";
import {
  ComplaintCreatePayload,
  ComplaintResponse,
  Department,
  DepartmentSuggestionResponse,
  DuplicateComplaintItem,
} from "../types";
import { DuplicateComplaintWarning } from "../components/DuplicateComplaintWarning";
import { LocationPicker } from "../components/LocationPicker";
import {
  Alert,
  Button,
  ButtonLink,
  CopyButton,
  DetailList,
  Icon,
  PageHeader,
  Panel,
  SelectField,
  Skeleton,
  StatusBadge,
  TextAreaField,
  TextField,
} from "../components/ui";
import { LIMITS } from "../lib/config";
import { complaintReference, formatDateTime } from "../lib/format";
import { useDocumentTitle } from "../hooks/useMediaState";

type FieldName = "title" | "description" | "department_id" | "floor_id";
type Errors = Partial<Record<FieldName, string>>;

/** Writing guidance, shown beside the form. These are examples of phrasing, not records. */
const EXAMPLES: { area: string; text: string }[] = [
  { area: "Hostel", text: "Washroom tap in Hostel Block C, Room 214, has been leaking since Monday morning." },
  { area: "IT Services", text: "Campus Wi-Fi drops every few minutes in Lab 3 of the Faculty Block, since yesterday." },
  { area: "Library", text: "Two catalogue terminals on the first floor of the Resource Centre do not start." },
  { area: "Mess & Cafeteria", text: "Serving counter at the mess was not cleaned before dinner on 12 October." },
  { area: "Sports & Gymnasium", text: "The badminton court net is torn and one floodlight is not working." },
  { area: "Campus Security", text: "Street light near the main gate parking has been off for three nights." },
];

function validate(title: string, description: string, departmentId: string, isAccommodation: boolean, floorId: number | null): Errors {
  const errors: Errors = {};
  const t = title.trim();
  const d = description.trim();
  if (t.length < LIMITS.titleMin) errors.title = "Give the complaint a title of at least 3 characters.";
  else if (t.length > LIMITS.titleMax) errors.title = "Title can be at most 120 characters.";
  if (d.length < LIMITS.descriptionMin) errors.description = "Describe the issue in at least 10 characters.";
  else if (d.length > LIMITS.descriptionMax) errors.description = "Description can be at most 2000 characters.";
  if (!departmentId) errors.department_id = "Choose the department that should handle this.";
  if (isAccommodation && !floorId) errors.floor_id = "Choose your hostel floor.";
  return errors;
}

export default function RaiseComplaintPage() {
  useDocumentTitle("Raise a complaint");

  const [departments, setDepartments] = useState<Department[]>([]);
  const [deptState, setDeptState] = useState<"loading" | "ready" | "error">("loading");
  const [deptError, setDeptError] = useState<string | null>(null);

  const [title, setTitle] = useState("");
  const [description, setDescription] = useState("");
  const [departmentId, setDepartmentId] = useState("");
  const [isPublic, setIsPublic] = useState(false);
  const [floorId, setFloorId] = useState<number | null>(null);
  const [hostel, setHostel] = useState("");
  const [wing, setWing] = useState("");
  const [floor, setFloor] = useState("");

  const [touched, setTouched] = useState<Partial<Record<FieldName, boolean>>>({});
  const [attempted, setAttempted] = useState(false);
  const [serverErrors, setServerErrors] = useState<Errors>({});

  const [suggestion, setSuggestion] = useState<DepartmentSuggestionResponse | null>(null);
  const [suggesting, setSuggesting] = useState(false);
  const [suggestError, setSuggestError] = useState<string | null>(null);
  const [suggestedFor, setSuggestedFor] = useState("");

  // Duplicate warning states
  const [duplicateMatches, setDuplicateMatches] = useState<DuplicateComplaintItem[]>([]);
  const [duplicateWarningDismissed, setDuplicateWarningDismissed] = useState(false);

  const [submitting, setSubmitting] = useState(false);
  const [submitError, setSubmitError] = useState<string | null>(null);
  const [created, setCreated] = useState<ComplaintResponse | null>(null);
  const inFlight = useRef(false);
  const successHeadingRef = useRef<HTMLHeadingElement>(null);

  const loadDepartments = useCallback((signal?: AbortSignal) => {
    setDeptState("loading");
    setDeptError(null);
    getDepartmentsApi(signal)
      .then((data) => {
        setDepartments(data);
        setDeptState("ready");
      })
      .catch((err) => {
        if (signal?.aborted) return;
        setDeptError(errorMessage(err, "Couldn't load departments."));
        setDeptState("error");
      });
  }, []);

  useEffect(() => {
    const controller = new AbortController();
    loadDepartments(controller.signal);
    return () => controller.abort();
  }, [loadDepartments]);

  useEffect(() => {
    if (created) successHeadingRef.current?.focus();
  }, [created]);

  const selectedDept = departments.find((d) => String(d.id) === departmentId);
  const isAccommodationDept = Boolean(
    selectedDept &&
      (selectedDept.name.toLowerCase().includes("hostel") ||
        selectedDept.name.toLowerCase().includes("hmc") ||
        (selectedDept.description && selectedDept.description.toLowerCase().includes("residential")))
  );

  // Debounced duplicate detection
  useEffect(() => {
    const t = title.trim();
    const d = description.trim();
    if (t.length < LIMITS.titleMin || d.length < LIMITS.descriptionMin) {
      setDuplicateMatches([]);
      return;
    }

    const controller = new AbortController();
    const timer = window.setTimeout(() => {
      getDuplicateSuggestionsApi(t, d, controller.signal)
        .then((res) => {
          if (res.matches && res.matches.length > 0) {
            setDuplicateMatches(res.matches);
            setDuplicateWarningDismissed(false);
          } else {
            setDuplicateMatches([]);
          }
        })
        .catch((err) => {
          if (controller.signal.aborted) return;
          // Graceful fallback: never let duplicate errors break the form
          setDuplicateMatches([]);
        });
    }, 500);

    return () => {
      window.clearTimeout(timer);
      controller.abort();
    };
  }, [title, description]);

  const clientErrors = validate(title, description, departmentId, isAccommodationDept, floorId);
  const errorFor = (field: FieldName) =>
    serverErrors[field] ?? ((touched[field] || attempted) ? clientErrors[field] : undefined);
  const touch = (field: FieldName) => () => setTouched((t) => ({ ...t, [field]: true }));

  const draftKey = `${title.trim()}\u0000${description.trim()}`;
  const suggestionStale = suggestion !== null && suggestedFor !== draftKey;
  const canSuggest = title.trim().length >= LIMITS.titleMin && description.trim().length >= LIMITS.descriptionMin;

  const requestSuggestion = async () => {
    if (!canSuggest || suggesting) return;
    setSuggesting(true);
    setSuggestError(null);
    try {
      const res = await suggestDepartmentApi(title.trim(), description.trim());
      setSuggestion(res);
      setSuggestedFor(draftKey);
    } catch (err) {
      setSuggestion(null);
      setSuggestError(errorMessage(err, "Couldn't get a suggestion. Choose a department yourself."));
    } finally {
      setSuggesting(false);
    }
  };

  const applyDepartment = (id: number) => {
    setDepartmentId(String(id));
    setServerErrors((s) => ({ ...s, department_id: undefined, floor_id: undefined }));
  };

  const executeSubmission = async () => {
    if (inFlight.current) return;
    setAttempted(true);
    setSubmitError(null);
    if (Object.keys(clientErrors).length > 0) return;

    inFlight.current = true;
    setSubmitting(true);
    try {
      const payload: ComplaintCreatePayload = {
        title: title.trim(),
        description: description.trim(),
        department_id: Number(departmentId),
        is_public: isPublic,
      };

      if (floorId) {
        payload.floor_id = floorId;
      }
      if (hostel.trim()) payload.hostel = hostel.trim();
      if (wing.trim()) payload.wing = wing.trim();
      if (floor.trim()) payload.floor = floor.trim();

      const saved = await createComplaintApi(payload);
      setCreated(saved);
    } catch (err) {
      if (err instanceof ApiClientError && err.validationErrors?.length) {
        const mapped: Errors = {};
        for (const item of err.validationErrors) {
          const field = fieldFromLoc(item.field) as FieldName;
          if (field === "title" || field === "description" || field === "department_id" || field === "floor_id") {
            mapped[field] = item.message;
          }
        }
        setServerErrors(mapped);
        if (!Object.keys(mapped).length) setSubmitError(err.message);
      } else if (err instanceof ApiClientError && (err.status === 404 || err.status === 400)) {
        setServerErrors({ department_id: err.message });
        loadDepartments();
      } else {
        setSubmitError(errorMessage(err, "Your complaint wasn't submitted. Try again."));
      }
    } finally {
      inFlight.current = false;
      setSubmitting(false);
    }
  };

  const handleSubmit = (e: React.FormEvent) => {
    e.preventDefault();
    executeSubmission();
  };

  const resetForm = () => {
    setCreated(null);
    setTitle("");
    setDescription("");
    setDepartmentId("");
    setIsPublic(false);
    setFloorId(null);
    setHostel("");
    setWing("");
    setFloor("");
    setTouched({});
    setAttempted(false);
    setServerErrors({});
    setSuggestion(null);
    setSuggestedFor("");
    setDuplicateMatches([]);
    setDuplicateWarningDismissed(false);
    setSubmitError(null);
    window.scrollTo({ top: 0 });
  };

  if (created) {
    const reference = complaintReference(created.id);
    const detailItems: { label: string; value: React.ReactNode }[] = [
      { label: "Title", value: created.title },
      { label: "Department", value: created.department_name },
      { label: "Visibility", value: created.is_public ? "Public (visible in campus feed)" : "Private (only assigned staff)" },
      { label: "Status", value: <StatusBadge status={created.status} /> },
      { label: "Submitted", value: formatDateTime(created.created_at) },
    ];

    if (created.location) {
      detailItems.push({
        label: "Hostel location",
        value: `${created.location.hostel}, ${created.location.wing}, ${created.location.floor}`,
      });
    } else {
      if (created.hostel) {
        detailItems.push({ label: "Hostel building", value: created.hostel });
      }
      if (created.wing) {
        detailItems.push({ label: "Wing / Block", value: created.wing });
      }
      if (created.floor) {
        detailItems.push({ label: "Floor", value: created.floor });
      }
    }
    if (created.floor) {
      detailItems.push({ label: "Floor", value: created.floor });
    }

    return (
      <div className="complaint-success">
        <Panel>
          <div className="complaint-success__head">
            <span className="complaint-success__icon" aria-hidden="true">
              <Icon name="check" size={26} />
            </span>
            <div>
              <h1 ref={successHeadingRef} tabIndex={-1} className="complaint-success__title">
                Complaint submitted
              </h1>
              <p className="complaint-success__text">
                It's saved and routed to {created.department_name}. Keep this reference to follow up.
              </p>
            </div>
          </div>

          <div className="reference-box">
            <span className="reference-box__label">Complaint reference</span>
            <span className="reference-box__value">{reference}</span>
            <CopyButton value={reference} label="Copy reference" />
          </div>

          <DetailList items={detailItems} />

          <div className="complaint-success__actions">
            <ButtonLink to="/complaints" icon="list">
              View my complaints
            </ButtonLink>
            <ButtonLink to="/dashboard" variant="secondary">
              Return to dashboard
            </ButtonLink>
            <Button variant="ghost" icon="plus" onClick={resetForm}>
              Raise another complaint
            </Button>
          </div>
        </Panel>
      </div>
    );
  }

  const topSuggestion =
    suggestion && suggestion.status === "provisional_advisory" && suggestion.suggestions.length > 0
      ? suggestion.suggestions[0]
      : null;
  const tiedSuggestions =
    suggestion && suggestion.status === "uncertain" && suggestion.suggestions.length > 1 ? suggestion.suggestions : [];
  const selectedName = departments.find((d) => String(d.id) === departmentId)?.name;

  const showDuplicateWarning = duplicateMatches.length > 0 && !duplicateWarningDismissed;

  return (
    <div>
      <PageHeader
        title="Raise a complaint"
        description="Describe one issue per complaint. Say where it is and since when, so the department can act without asking again."
      />

      <div className="raise-layout">
        <Panel className="raise-form-panel">
          <form onSubmit={handleSubmit} noValidate className="raise-form">
            {submitError ? (
              <Alert tone="error" title="Your complaint wasn't submitted">
                {submitError} Your text is still here.
              </Alert>
            ) : null}
            <p className="form-legend">
              Fields marked <span aria-hidden="true" className="field__required">*</span>
              <span className="visually-hidden">with an asterisk</span> are required.
            </p>

            <TextField
              label="Complaint title"
              name="title"
              placeholder="Leaking tap in Hostel Block C washroom"
              value={title}
              onChange={(e) => {
                setTitle(e.target.value);
                setServerErrors((s) => ({ ...s, title: undefined }));
              }}
              onBlur={touch("title")}
              error={errorFor("title")}
              hint="A short summary, 3–120 characters."
              maxLength={LIMITS.titleMax}
              showCounter
              required
              disabled={submitting}
            />

            <TextAreaField
              label="Description"
              name="description"
              placeholder="What is wrong, exactly where (block, floor, room or facility), and since when."
              value={description}
              onChange={(e) => {
                setDescription(e.target.value);
                setServerErrors((s) => ({ ...s, description: undefined }));
              }}
              onBlur={touch("description")}
              error={errorFor("description")}
              hint="10–2000 characters."
              maxLength={LIMITS.descriptionMax}
              rows={7}
              showCounter
              required
              disabled={submitting}
            />

            {/* Keyword department suggestion */}
            <div className="suggest-box" aria-live="polite">
              <div className="suggest-box__head">
                <div>
                  <p className="suggest-box__title">Not sure which department?</p>
                  <p className="suggest-box__text">
                    CCMS can suggest one by matching keywords in your title and description. You make the final choice.
                  </p>
                </div>
                <Button
                  variant="secondary"
                  size="sm"
                  icon="lightbulb"
                  onClick={requestSuggestion}
                  loading={suggesting}
                  disabled={!canSuggest || submitting}
                >
                  {suggestion && !suggestionStale ? "Suggest again" : "Suggest a department"}
                </Button>
              </div>
              {!canSuggest ? (
                <p className="suggest-box__hint">Write a title and a short description first.</p>
              ) : null}

              {suggestError ? <Alert tone="warning">{suggestError}</Alert> : null}

              {suggestion && !suggestionStale ? (
                <div className="suggestion">
                  {topSuggestion ? (
                    <>
                      <p className="suggestion__line">
                        Suggested department: <strong>{topSuggestion.department_name}</strong>
                      </p>
                      {topSuggestion.rationale ? <p className="suggestion__why">{topSuggestion.rationale}.</p> : null}
                      {String(topSuggestion.department_id) === departmentId ? (
                        <p className="suggestion__applied">
                          <Icon name="check" size={16} /> Selected below
                        </p>
                      ) : (
                        <Button size="sm" onClick={() => applyDepartment(topSuggestion.department_id)}>
                          Use {topSuggestion.department_name}
                        </Button>
                      )}
                    </>
                  ) : tiedSuggestions.length > 0 ? (
                    <>
                      <p className="suggestion__line">Your description matches more than one department equally:</p>
                      <div className="suggestion__choices">
                        {tiedSuggestions.map((s) => (
                          <Button
                            key={s.department_id}
                            size="sm"
                            variant={String(s.department_id) === departmentId ? "primary" : "secondary"}
                            onClick={() => applyDepartment(s.department_id)}
                          >
                            {s.department_name}
                          </Button>
                        ))}
                      </div>
                      <p className="suggestion__why">Pick the one responsible for the location you described.</p>
                    </>
                  ) : (
                    <p className="suggestion__line">
                      No department keywords matched. Choose the department yourself from the list below.
                    </p>
                  )}
                </div>
              ) : suggestionStale ? (
                <p className="suggest-box__hint">You've edited the text since the last suggestion. Ask again to refresh it.</p>
              ) : null}
            </div>

            {deptState === "loading" ? (
              <div className="field">
                <span className="field__label">Department</span>
                <Skeleton height={46} />
              </div>
            ) : deptState === "error" ? (
              <Alert
                tone="error"
                title="Departments couldn't be loaded"
                action={
                  <Button size="sm" variant="secondary" icon="refresh" onClick={() => loadDepartments()}>
                    Retry
                  </Button>
                }
              >
                {deptError}
              </Alert>
            ) : (
              <SelectField
                label="Department"
                name="department_id"
                value={departmentId}
                onChange={(e) => {
                  setDepartmentId(e.target.value);
                  setServerErrors((s) => ({ ...s, department_id: undefined }));
                }}
                onBlur={touch("department_id")}
                error={errorFor("department_id")}
                hint={
                  selectedName
                    ? departments.find((d) => String(d.id) === departmentId)?.description ?? undefined
                    : "The department that will receive this complaint."
                }
                required
                disabled={submitting}
              >
                <option value="">Choose a department</option>
                {departments.map((dept) => (
                  <option key={dept.id} value={dept.id}>
                    {dept.name}
                  </option>
                ))}
              </SelectField>
            )}

            {/* Location selector for accommodation complaints (required) or general complaints (optional) */}
            {departmentId ? (
              <div className="accommodation-box" role="region" aria-label="Hostel location details">
                <div className="accommodation-box__head">
                  <Icon name="building" size={18} />
                  <h3 className="accommodation-box__title">Hostel location</h3>
                  <span className="accommodation-box__badge">
                    {isAccommodationDept ? `Required for ${selectedName}` : "Optional"}
                  </span>
                </div>
                <p className="field__hint" style={{ marginBottom: "var(--space-3)" }}>
                  {isAccommodationDept
                    ? "Select the hostel, wing, and floor where the issue is located."
                    : "If this issue is located in or affects a hostel building, select the location."}
                </p>
                <LocationPicker
                  value={floorId}
                  onChange={(fid, details) => {
                    setFloorId(fid);
                    if (details) {
                      setHostel(details.hostelName);
                      setWing(details.wingName);
                      setFloor(details.floorName);
                    } else {
                      setHostel("");
                      setWing("");
                      setFloor("");
                    }
                    setServerErrors((s) => ({ ...s, floor_id: undefined }));
                  }}
                  onBlur={touch("floor_id")}
                  required={isAccommodationDept}
                  error={errorFor("floor_id")}
                  disabled={submitting}
                />
              </div>
            ) : null}

            {/* Visibility Option */}
            <div className="visibility-group">
              <span className="visibility-label">Complaint visibility</span>
              <div className="visibility-options">
                <label className={`visibility-card ${!isPublic ? "visibility-card--selected" : ""}`}>
                  <input
                    type="radio"
                    name="visibility"
                    value="private"
                    checked={!isPublic}
                    onChange={() => setIsPublic(false)}
                    disabled={submitting}
                  />
                  <div className="visibility-card__body">
                    <span className="visibility-card__title">Private complaint</span>
                    <span className="visibility-card__desc">
                      Visible only to you and assigned campus staff handling the issue.
                    </span>
                  </div>
                </label>

                <label className={`visibility-card ${isPublic ? "visibility-card--selected" : ""}`}>
                  <input
                    type="radio"
                    name="visibility"
                    value="public"
                    checked={isPublic}
                    onChange={() => setIsPublic(true)}
                    disabled={submitting}
                  />
                  <div className="visibility-card__body">
                    <span className="visibility-card__title">Public complaint</span>
                    <span className="visibility-card__desc">
                      Shared in the campus feed. Your name and identity remain private.
                    </span>
                  </div>
                </label>
              </div>
            </div>

            {/* Duplicate complaint warning panel */}
            {showDuplicateWarning ? (
              <DuplicateComplaintWarning
                matches={duplicateMatches}
                onSubmitAnyway={executeSubmission}
                onDismiss={() => setDuplicateWarningDismissed(true)}
                submitting={submitting}
              />
            ) : null}

            <div className="raise-form__actions">
              <Button type="submit" loading={submitting} disabled={submitting || deptState !== "ready"}>
                {submitting ? "Submitting…" : "Submit complaint"}
              </Button>
            </div>
          </form>
        </Panel>

        <aside className="raise-aside" aria-labelledby="examples-heading">
          <h2 id="examples-heading" className="raise-aside__title">
            What a clear complaint looks like
          </h2>
          <p className="raise-aside__text">Examples of the detail that helps a department act quickly:</p>
          <ul className="examples">
            {EXAMPLES.map((ex) => (
              <li key={ex.area}>
                <span className="examples__area">{ex.area}</span>
                <span className="examples__text">{ex.text}</span>
              </li>
            ))}
          </ul>
        </aside>
      </div>
    </div>
  );
}
