# CCMS Documentation

This folder brings together the API handoff material and Software Engineering diagrams used during our first sprint. It is meant to help teammates understand both **what the code currently does** and **what the wider system is intended to become**.

## Where to look

| Resource | Purpose |
| --- | --- |
| [`API_CONTRACT.md`](API_CONTRACT.md) | HTTP routes, payload shapes, authentication and error responses |
| [`FRONTEND_HANDOFF.md`](FRONTEND_HANDOFF.md) | Instructions for connecting the React UI to FastAPI |
| [`architecture/uml/`](architecture/uml/) | Class, use-case, activity and sequence diagrams from the design team |
| [`../Documents/`](../Documents/) | Requirements, user stories, stakeholder analysis and course deliverables |

Some diagrams represent the intended system rather than just the features implemented in Sprint 1. For the actual API, check the FastAPI route files and its generated `/docs` endpoint.

## Documentation status

The contract and handoff guides came from the earlier assembled backend. They contain detailed examples, but a few examples and labels can lag behind the latest code. In particular:

- Department names are **provisional**, not an official university-approved taxonomy.
- The current department suggestion service uses a keyword-based heuristic (`v1.2.0-keyword` in the reviewed code), not a trained ML model.
- Google Sign-In needs valid local OAuth settings and has not been claimed as end-to-end verified in the final integrated revision.
- Do not copy example response values or development credentials into a real system without checking them.

We should periodically compare these documents with `backend/app/api/v1/endpoints/`, `backend/app/schemas/` and the generated OpenAPI specification, and update stale examples as part of regular review.

To run the application locally, start with the [project README](../README.md) and the [backend](../backend/README.md) and [frontend](../frontend/README.md) guides.
