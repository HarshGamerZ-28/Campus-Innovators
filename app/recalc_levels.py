"""One-time maintenance script: recompute `level` and `next_xp` for every
existing user using the current LEVEL_XP_THRESHOLDS table.

Why this is needed: `next_xp` is stored on the user row and is only ever
recalculated when a user earns XP (see `apply_level_up` in activity.py).
Users who haven't earned XP since the thresholds were last tuned can be
left with a stale `next_xp` (e.g. showing 1000 instead of the correct
250 for level 2).

Usage (run from the backend/ directory, with the same env vars/DATABASE_URL
as the running app):

    python -m app.recalc_levels

It's safe to re-run — it's idempotent and only updates rows that changed.
"""

from __future__ import annotations

from sqlalchemy import select

from .activity import xp_threshold_for_level
from .database import SessionLocal
from .models import User


def main() -> None:
    updated = 0
    with SessionLocal() as db:
        users = db.scalars(select(User)).all()
        for user in users:
            # Recompute level from scratch based on total xp, in case level
            # itself had drifted too, then set the correct next_xp for it.
            level = max(user.level, 1)

            # Walk level down if xp doesn't actually support the stored level.
            while level > 1 and user.xp < xp_threshold_for_level(level - 1):
                level -= 1

            # Walk level up for any xp that clears the current threshold.
            while user.xp >= xp_threshold_for_level(level):
                level += 1

            correct_next_xp = xp_threshold_for_level(level)

            if user.level != level or user.next_xp != correct_next_xp:
                print(
                    f"user {user.id} ({user.username}): "
                    f"level {user.level}->{level}, next_xp {user.next_xp}->{correct_next_xp}"
                )
                user.level = level
                user.next_xp = correct_next_xp
                updated += 1

        db.commit()

    print(f"Done. Updated {updated} user(s).")


if __name__ == "__main__":
    main()
