"""
seed_governance.py — demo users, roles, and one active freeze window.

Run from backend/:
    py -3.13 seed_governance.py
"""
from __future__ import annotations

import os
import sys
import uuid
from datetime import datetime, timedelta, timezone

sys.path.insert(0, os.path.dirname(__file__))

from sqlalchemy import select

from app.db import SyncSessionLocal, create_tables_sync
from app.models.freeze_window import FreezeScope, FreezeWindow
from app.models.tenant import Tenant
from app.models.user import Role, User, UserRole


DEMO_TENANT_SLUG = "acme-logistics"


DEMO_USERS = [
    ("alice@acme.com",   "Alice Viewer",   [Role.VIEWER.value]),
    ("bob@acme.com",     "Bob Editor",     [Role.EDITOR.value]),
    ("carol@acme.com",   "Carol Approver", [Role.APPROVER.value]),
    ("dave@acme.com",    "Dave Admin",     [Role.ADMIN.value]),
    ("eve@acme.com",     "Eve Auditor",    [Role.AUDITOR.value]),
]


def seed() -> None:
    create_tables_sync()
    with SyncSessionLocal() as db:
        tenant = db.execute(
            select(Tenant).where(Tenant.slug == DEMO_TENANT_SLUG)
        ).scalar_one_or_none()
        if tenant is None:
            print(f"Demo tenant {DEMO_TENANT_SLUG!r} not found. Run seed_demo.py first.")
            return

        # --- users (idempotent upsert by email)
        for email, name, roles in DEMO_USERS:
            user = db.execute(
                select(User).where(User.tenant_id == tenant.id, User.email == email)
            ).scalar_one_or_none()
            if user is None:
                user = User(
                    id=uuid.uuid4(),
                    tenant_id=tenant.id,
                    email=email,
                    display_name=name,
                    active=True,
                )
                db.add(user)
                db.flush()
            else:
                user.display_name = name
                user.active = True

            # Reset roles to match seed list
            db.query = None  # type: ignore
            existing = db.execute(
                select(UserRole).where(UserRole.user_id == user.id)
            ).scalars().all()
            keep = set(roles)
            for ra in existing:
                if ra.role not in keep:
                    db.delete(ra)
            present = {ra.role for ra in existing if ra.role in keep}
            for r in roles:
                if r not in present:
                    db.add(UserRole(id=uuid.uuid4(), user_id=user.id, role=r))

        db.commit()

        # --- one active freeze window: billing tag, next 3 days, admin can bypass
        existing_window = db.execute(
            select(FreezeWindow).where(
                FreezeWindow.tenant_id == tenant.id,
                FreezeWindow.name == "Month-end billing freeze (demo)",
            )
        ).scalar_one_or_none()
        now = datetime.now(timezone.utc)
        if existing_window is None:
            db.add(FreezeWindow(
                id=uuid.uuid4(),
                tenant_id=tenant.id,
                name="Month-end billing freeze (demo)",
                description="No non-admin edits to billing-tagged rules until month-end close.",
                start_at=now - timedelta(hours=1),
                end_at=now + timedelta(days=3),
                scope=FreezeScope.BY_TAG.value,
                scope_values=["billing", "Billing"],
                bypass_roles=[Role.ADMIN.value],
                active=True,
                created_by_email="dave@acme.com",
            ))
        else:
            existing_window.start_at = now - timedelta(hours=1)
            existing_window.end_at = now + timedelta(days=3)
            existing_window.active = True

        db.commit()
        print(f"Seeded {len(DEMO_USERS)} users + 1 freeze window for tenant {tenant.slug}.")


if __name__ == "__main__":
    seed()
