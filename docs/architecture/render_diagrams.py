"""Render the S5-28 architecture diagrams.

    python docs/architecture/render_diagrams.py

Writes system-design.png and object-design-package.png next to this file.
Needs only matplotlib. The package-diagram arrows were taken from the real
`import` statements in backend/app and frontend/src (see design.md, section 3);
re-check them if the package structure changes.
"""

from pathlib import Path

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt  # noqa: E402
from matplotlib.patches import FancyBboxPatch, Polygon  # noqa: E402

OUT = Path(__file__).resolve().parent

INK = "#1f2933"
MUTED = "#52606d"
LINE = "#3e4c59"
FILL = {
    "client": "#e3f2fd",
    "frontend": "#e8f5e9",
    "backend": "#fff8e1",
    "layer": "#ffffff",
    "data": "#ede7f6",
    "external": "#fce4ec",
    "ci": "#eceff1",
}
EDGE = {
    "client": "#1e88e5",
    "frontend": "#43a047",
    "backend": "#f9a825",
    "layer": "#9aa5b1",
    "data": "#5e35b1",
    "external": "#d81b60",
    "ci": "#607d8b",
}


# --------------------------------------------------------------------------
# Small drawing helpers
# --------------------------------------------------------------------------


class Box:
    def __init__(self, x, y, w, h):
        self.x, self.y, self.w, self.h = x, y, w, h

    @property
    def cx(self):
        return self.x + self.w / 2

    @property
    def cy(self):
        return self.y + self.h / 2

    def edge_toward(self, tx, ty):
        """Point on this box's border on the line from its centre to (tx, ty)."""
        dx, dy = tx - self.cx, ty - self.cy
        if dx == 0 and dy == 0:
            return self.cx, self.cy
        sx = (self.w / 2) / abs(dx) if dx else float("inf")
        sy = (self.h / 2) / abs(dy) if dy else float("inf")
        s = min(sx, sy)
        return self.cx + dx * s, self.cy + dy * s


def box(ax, x, y, w, h, kind, title=None, lines=(), title_size=11, line_size=8.6, radius=0.12, z=2):
    ax.add_patch(
        FancyBboxPatch(
            (x, y), w, h,
            boxstyle=f"round,pad=0,rounding_size={radius}",
            facecolor=FILL[kind], edgecolor=EDGE[kind], linewidth=1.6, zorder=z,
        )
    )
    if title:
        ty = y + h - 0.28 if lines else y + h / 2
        va = "top" if lines else "center"
        ax.text(x + w / 2, ty + (0.08 if lines else 0), title, ha="center", va=va,
                fontsize=title_size, fontweight="bold", color=INK, zorder=z + 1)
    for i, line in enumerate(lines):
        ax.text(x + w / 2, y + h - 0.68 - i * 0.30, line, ha="center", va="top",
                fontsize=line_size, color=MUTED, zorder=z + 1)
    return Box(x, y, w, h)


def frame(ax, x, y, w, h, kind, label):
    ax.add_patch(
        FancyBboxPatch(
            (x, y), w, h, boxstyle="round,pad=0,rounding_size=0.2",
            facecolor=FILL[kind], edgecolor=EDGE[kind], linewidth=2.0, zorder=0,
        )
    )
    ax.text(x + 0.2, y + h - 0.2, label, ha="left", va="top", fontsize=12.5,
            fontweight="bold", color=EDGE[kind], zorder=1)
    return Box(x, y, w, h)


def arrow(ax, a, b, label=None, dashed=False, color=LINE, both=False, label_offset=(0, 0),
          rad=0.0, lw=1.4, label_size=8.3, start=None, end=None):
    p1 = start or a.edge_toward(b.cx, b.cy)
    p2 = end or b.edge_toward(a.cx, a.cy)
    ax.annotate(
        "", xy=p2, xytext=p1,
        arrowprops=dict(
            arrowstyle="<|-|>" if both else "-|>", color=color, lw=lw,
            linestyle=(0, (5, 3)) if dashed else "-", shrinkA=2, shrinkB=2,
            mutation_scale=13, connectionstyle=f"arc3,rad={rad}",
        ),
        zorder=4,
    )
    if label:
        mx = (p1[0] + p2[0]) / 2 + label_offset[0]
        my = (p1[1] + p2[1]) / 2 + label_offset[1]
        ax.text(mx, my, label, ha="center", va="center", fontsize=label_size, color=INK,
                zorder=5, bbox=dict(boxstyle="round,pad=0.18", fc="white", ec="none", alpha=0.92))


def package(ax, x, y, w, h, name, note=None, kind="layer"):
    """UML package: a folder with a name tab."""
    tab_w, tab_h = min(1.3, w * 0.45), 0.24
    ax.add_patch(Polygon(
        [(x, y + h), (x, y + h + tab_h), (x + tab_w, y + h + tab_h), (x + tab_w, y + h)],
        closed=True, facecolor=FILL[kind], edgecolor=EDGE[kind], linewidth=1.3, zorder=2,
    ))
    ax.add_patch(FancyBboxPatch((x, y), w, h, boxstyle="square,pad=0", facecolor=FILL[kind],
                                edgecolor=EDGE[kind], linewidth=1.3, zorder=2))
    ax.text(x + w / 2, y + h / 2 + (0.13 if note else 0), name, ha="center", va="center",
            fontsize=11, fontweight="bold", color=INK, zorder=3, family="monospace")
    if note:
        ax.text(x + w / 2, y + h / 2 - 0.2, note, ha="center", va="center", fontsize=7.8,
                color=MUTED, zorder=3)
    return Box(x, y, w, h)


def canvas(w, h):
    fig, ax = plt.subplots(figsize=(w, h), dpi=160)
    ax.set_xlim(0, w)
    ax.set_ylim(0, h)
    ax.set_aspect("equal")
    ax.axis("off")
    fig.patch.set_facecolor("white")
    return fig, ax


# --------------------------------------------------------------------------
# 1. System design
# --------------------------------------------------------------------------


def system_design():
    fig, ax = canvas(17, 11)
    ax.text(8.5, 10.7, "CCMS v1.0 — System design", ha="center", va="center",
            fontsize=17, fontweight="bold", color=INK)
    ax.text(8.5, 10.33, "Runtime components, hosting and delivery pipeline",
            ha="center", va="center", fontsize=10.5, color=MUTED)

    # Users
    users = box(ax, 0.3, 6.2, 2.4, 2.6, "client", "Users", [
        "Student", "Department staff", "Hostel staff", "Admin", "(web browser)",
    ])

    # Frontend
    frame(ax, 3.3, 5.0, 3.7, 4.9, "frontend", "Frontend · Vercel *")
    spa = box(ax, 3.6, 7.25, 3.1, 1.95, "layer", "React SPA", [
        "React 18 + TypeScript, Vite build",
        "pages · components · layouts",
        "routes/guards (role-based)",
    ])
    feclient = box(ax, 3.6, 5.3, 3.1, 1.6, "layer", "api/ client", [
        "fetch + JWT bearer header",
        "base: VITE_API_BASE_URL",
    ])
    arrow(ax, spa, feclient)

    # Backend
    frame(ax, 7.7, 1.2, 5.4, 8.7, "backend", "Backend · FastAPI on Render *")
    mw = box(ax, 8.0, 8.25, 4.8, 0.95, "layer", "main.py: CORS, rate limit, /health")
    routers = box(ax, 8.0, 6.95, 4.8, 1.0, "layer", "Routers  (api/v1/endpoints)",
                  ["HTTP only: parse, validate, call a service"], title_size=10.5)
    deps = box(ax, 8.0, 5.75, 4.8, 0.9, "layer", "Dependencies  (FastAPI Depends)",
               ["get_current_user · RoleChecker · get_db"], title_size=10.5)
    services = box(ax, 8.0, 4.2, 4.8, 1.25, "layer", "Services", [
        "business rules + access checks",
        "lifecycle · hostel scope · feeds · comments",
    ], title_size=10.5)
    repos = box(ax, 8.0, 2.95, 4.8, 0.95, "layer", "Repositories + SQLAlchemy models",
                ["schemas (Pydantic) shape every response"], title_size=10.5)
    alembic = box(ax, 8.0, 1.5, 4.8, 1.15, "layer", "Alembic migrations", [
        "run on boot: alembic upgrade head",
    ], title_size=10.5)
    for upper, lower in ((mw, routers), (routers, deps), (deps, services), (services, repos)):
        arrow(ax, upper, lower)

    # Data + external services
    db = box(ax, 13.8, 1.5, 2.9, 2.4, "data", "PostgreSQL 16", [
        "Supabase *",
        "SQLite for local dev/tests",
    ])
    email = box(ax, 13.8, 7.55, 2.9, 1.55, "external", "Email provider", [
        "SMTP or Resend",
        "verification links",
    ])
    ml = box(ax, 13.8, 4.45, 2.9, 1.65, "external", "Duplicate detector", [
        "scikit-learn TF-IDF",
        "in-process (services)",
    ])
    google = box(ax, 0.3, 3.2, 2.4, 1.7, "external", "Google OAuth", [
        "optional sign-in",
        "off in production",
    ])

    arrow(ax, users, spa, "HTTPS", both=True)
    arrow(ax, feclient, routers, "HTTPS · JSON\nREST /api/v1", both=True, label_offset=(0, 0.5))
    arrow(ax, repos, db, "SQL (psycopg 3)", both=True, label_offset=(0, 0.22),
          start=(12.8, 3.42), end=(13.8, 3.42))
    arrow(ax, alembic, db, "DDL", start=(12.8, 2.0), end=(13.8, 2.0), dashed=True, label_offset=(0, 0.22))
    arrow(ax, services, email, "send email", start=(12.8, 5.1), end=(13.8, 7.85), label_offset=(0.05, 0.2))
    arrow(ax, services, ml, "similarity", start=(12.8, 4.85), end=(13.8, 4.85), label_offset=(0, 0.22))
    arrow(ax, google, routers, "OAuth callback (auth routes)", dashed=True, start=(2.7, 4.3),
          end=(7.7, 4.6), label_offset=(0, 0.2))

    # CI / delivery
    frame(ax, 0.3, 0.2, 7.0, 2.6, "ci", "Delivery")
    gh = box(ax, 0.55, 0.45, 1.9, 1.7, "ci", "GitHub", ["PR + 1 review", "→ main"], title_size=10.5)
    ci = box(ax, 2.75, 0.45, 2.3, 1.7, "ci", "GitHub Actions", [
        "pytest: SQLite + PG 16",
        "vitest · tsc · build",
    ], title_size=10.5, line_size=8)
    deploy = box(ax, 5.35, 0.45, 1.75, 1.7, "ci", "Auto-deploy", ["staging from", "main"], title_size=10.5)
    arrow(ax, gh, ci)
    arrow(ax, ci, deploy)
    arrow(ax, deploy, alembic, dashed=True, start=(7.1, 1.3), end=(8.0, 1.9), color=EDGE["ci"])

    ax.text(16.7, 0.25, "* hosting planned in S5-17 (staging 20 Nov, production 2 Dec);\n"
            "  not deployed when this diagram was drawn (17 Nov 2026)",
            ha="right", va="bottom", fontsize=8.5, color=MUTED, style="italic")
    fig.savefig(OUT / "system-design.png", bbox_inches="tight", pad_inches=0.15)
    plt.close(fig)


# --------------------------------------------------------------------------
# 2. Object design: package diagram
# --------------------------------------------------------------------------


def package_diagram():
    fig, ax = canvas(17, 11.2)
    ax.text(8.5, 10.9, "CCMS v1.0 — Object design (package diagram)", ha="center",
            va="center", fontsize=17, fontweight="bold", color=INK)
    ax.text(8.5, 10.52, "Arrows are «import» dependencies measured from the source; "
            "a dependency points from the user to the package it uses",
            ha="center", va="center", fontsize=10, color=MUTED)

    # ---- Backend --------------------------------------------------------
    frame(ax, 0.25, 0.3, 8.6, 9.85, "backend", "backend/app  (Python · FastAPI)")
    W, H = 2.35, 0.9
    api = package(ax, 3.35, 8.1, W, H, "api", "routers /api/v1")
    dependencies = package(ax, 0.55, 6.15, W, H, "dependencies", "auth, roles")
    services = package(ax, 3.35, 6.15, W, H, "services", "rules + access")
    schemas = package(ax, 6.2, 6.15, W, H, "schemas", "Pydantic DTOs")
    repositories = package(ax, 1.9, 3.9, W, H, "repositories", "query helpers")
    core = package(ax, 6.2, 3.65, W, H, "core", "config, security")
    models = package(ax, 3.35, 2.55, W, H, "models", "SQLAlchemy ORM")
    db = package(ax, 3.35, 0.65, W, H, "db", "Base, session")

    solid = [
        (api, services, None), (api, schemas, None), (api, dependencies, None),
        (services, repositories, None), (services, models, None), (services, schemas, None),
        (services, core, None), (repositories, models, None), (models, db, None),
        (dependencies, core, None), (schemas, core, None),
    ]
    for a, b, lbl in solid:
        arrow(ax, a, b, lbl)
    arrow(ax, dependencies, models, start=(0.95, 6.15), end=(3.35, 2.95), rad=0.28)
    arrow(ax, dependencies, db, start=(0.75, 6.15), end=(3.35, 1.0), rad=0.25)
    # Known shortcut: a few routers still query models directly.
    arrow(ax, api, models, "direct ORM query\n(e.g. /history)", dashed=True, color="#c62828",
          start=(5.55, 8.1), end=(5.2, 3.45), rad=-0.35, label_offset=(1.0, 0.0), label_size=7.6)
    # db/base.py imports every model so Alembic sees the metadata.
    arrow(ax, db, models, "registers all\nmodels (Alembic)", dashed=True, color=MUTED,
          start=(5.4, 1.4), end=(5.4, 2.55), label_offset=(1.05, 0.0), label_size=7.6)

    # ---- Frontend -------------------------------------------------------
    frame(ax, 9.15, 0.3, 7.6, 9.85, "frontend", "frontend/src  (TypeScript · React)")
    FW = 2.0
    app = package(ax, 12.0, 8.1, FW, H, "App", "main.tsx, routes", kind="layer")
    routes = package(ax, 9.45, 6.55, FW, H, "routes", "role guards")
    pages = package(ax, 12.0, 6.55, FW, H, "pages", "11 screens")
    layouts = package(ax, 9.45, 4.65, FW, H, "layouts", "AppShell")
    context = package(ax, 12.0, 4.65, FW, H, "context", "AuthContext")
    hooks = package(ax, 14.5, 4.65, FW, H, "hooks")
    components = package(ax, 9.45, 2.65, FW, H, "components", "+ components/ui")
    fe_api = package(ax, 12.0, 2.65, FW, H, "api", "typed REST calls")
    lib = package(ax, 14.5, 2.65, FW, H, "lib", "format, access")
    types = package(ax, 12.0, 0.65, FW, H, "types", "types.ts")

    for a, b in (
        (app, pages), (app, routes), (routes, layouts), (pages, layouts), (pages, context),
        (pages, hooks), (pages, components), (pages, lib), (layouts, components),
        (context, fe_api), (components, fe_api), (fe_api, types), (lib, types),
    ):
        arrow(ax, a, b)
    arrow(ax, components, types, start=(10.45, 2.65), end=(12.0, 1.1), rad=0.2)
    arrow(ax, pages, fe_api, start=(13.75, 6.55), end=(13.75, 3.55), rad=-0.35)


    # Legend
    lx, ly = 0.55, 9.55
    ax.annotate("", xy=(lx + 0.6, ly), xytext=(lx, ly),
                arrowprops=dict(arrowstyle="-|>", color=LINE, lw=1.4, mutation_scale=12))
    ax.text(lx + 0.7, ly, "«import»", va="center", fontsize=8.3, color=INK)
    ax.annotate("", xy=(lx + 2.3, ly), xytext=(lx + 1.7, ly),
                arrowprops=dict(arrowstyle="-|>", color="#c62828", lw=1.4, linestyle=(0, (5, 3)),
                                mutation_scale=12))
    ax.text(lx + 2.4, ly, "layer shortcut", va="center", fontsize=8.3, color=INK)
    ax.text(9.45, 9.55, "frontend api  →  backend api over HTTPS/JSON (REST /api/v1), not an import",
            va="center", fontsize=8.3, color=EDGE["client"], style="italic")

    fig.savefig(OUT / "object-design-package.png", bbox_inches="tight", pad_inches=0.15)
    plt.close(fig)


if __name__ == "__main__":
    system_design()
    package_diagram()
    print("wrote", OUT / "system-design.png", "and", OUT / "object-design-package.png")
