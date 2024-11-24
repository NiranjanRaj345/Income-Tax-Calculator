"""Update admin model with first_name and last_name fields

Revision ID: e3e43f401db3
Revises: 
Create Date: 2024-11-22 10:37:43.935646

"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.sql import text


# revision identifiers, used by Alembic.
revision = 'e3e43f401db3'
down_revision = None
branch_labels = None
depends_on = None


def upgrade():
    # Update existing records: split name into first_name and last_name
    connection = op.get_bind()
    
    # Update first_name and last_name from name
    connection.execute(
        text("""
            UPDATE admin 
            SET first_name = substr(name, 1, instr(name || ' ', ' ') - 1),
                last_name = substr(name, instr(name || ' ', ' ') + 1)
            WHERE first_name IS NULL OR last_name IS NULL
        """)
    )

    # Make columns non-nullable
    with op.batch_alter_table('admin', schema=None) as batch_op:
        batch_op.alter_column('first_name',
            existing_type=sa.String(length=80),
            nullable=False
        )
        batch_op.alter_column('last_name',
            existing_type=sa.String(length=80),
            nullable=False
        )
        batch_op.drop_column('name')


def downgrade():
    # Create name column
    with op.batch_alter_table('admin', schema=None) as batch_op:
        batch_op.add_column(sa.Column('name', sa.VARCHAR(length=120), nullable=True))

    # Combine first_name and last_name back into name
    connection = op.get_bind()
    connection.execute(
        text("UPDATE admin SET name = first_name || ' ' || last_name")
    )

    # Make name non-nullable and drop first_name, last_name
    with op.batch_alter_table('admin', schema=None) as batch_op:
        batch_op.alter_column('name',
            existing_type=sa.VARCHAR(length=120),
            nullable=False
        )
        batch_op.drop_column('last_name')
        batch_op.drop_column('first_name')
