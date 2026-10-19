"""${message}."""

from alembic import op
import sqlalchemy as sa

revision = ${repr(up_revision)}
down_revision = ${repr(down_revision)}
branch_labels = ${repr(branch_labels)}
depends_on = ${repr(depends_on)}


def upgrade() -> None:
    """Apply schema changes."""
    ${upgrades if upgrades else "pass"}


def downgrade() -> None:
    """Reverse schema changes only when explicitly requested."""
    ${downgrades if downgrades else "pass"}
