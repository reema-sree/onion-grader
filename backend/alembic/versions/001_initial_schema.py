"""Initial database schema migration for AgriGrade.

Revision ID: 001_initial_schema
Revises:
Create Date: 2026-10-03 21:00:00.000000

"""
from typing import Sequence, Union
from alembic import op
import sqlalchemy as sa

revision: str = '001_initial_schema'
down_revision: Union[str, None] = None
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # 1. Centres table
    op.create_table(
        'centres',
        sa.Column('id', sa.Integer(), primary_key=True, nullable=False),
        sa.Column('name', sa.String(length=255), nullable=False, unique=True),
        sa.Column('address', sa.String(length=500), nullable=True),
        sa.Column('created_at', sa.DateTime(), nullable=False),
    )
    op.create_index(op.f('ix_centres_name'), 'centres', ['name'], unique=True)
    op.create_index(op.f('ix_centres_id'), 'centres', ['id'], unique=False)

    # 2. Users table
    op.create_table(
        'users',
        sa.Column('id', sa.Integer(), primary_key=True, nullable=False),
        sa.Column('name', sa.String(length=255), nullable=False),
        sa.Column('phone', sa.String(length=50), nullable=True),
        sa.Column('email', sa.String(length=255), nullable=False, unique=True),
        sa.Column('hashed_password', sa.String(length=255), nullable=False),
        sa.Column('role', sa.String(length=50), nullable=False),
        sa.Column('centre_id', sa.Integer(), sa.ForeignKey('centres.id', ondelete='SET NULL'), nullable=True),
        sa.Column('preferred_language', sa.String(length=10), nullable=False, server_default='en'),
        sa.Column('is_active', sa.Boolean(), nullable=False, server_default='1'),
        sa.Column('created_at', sa.DateTime(), nullable=False),
    )
    op.create_index(op.f('ix_users_email'), 'users', ['email'], unique=True)
    op.create_index(op.f('ix_users_id'), 'users', ['id'], unique=False)

    # 3. Lots table
    op.create_table(
        'lots',
        sa.Column('id', sa.Integer(), primary_key=True, nullable=False),
        sa.Column('lot_number', sa.String(length=100), nullable=True, unique=True),
        sa.Column('farmer_name', sa.String(length=255), nullable=False),
        sa.Column('centre_id', sa.Integer(), sa.ForeignKey('centres.id', ondelete='RESTRICT'), nullable=False),
        sa.Column('weight_kg', sa.Float(), nullable=False, server_default='0.0'),
        sa.Column('status', sa.String(length=50), nullable=False, server_default='draft'),
        sa.Column('created_at', sa.DateTime(), nullable=False),
    )
    op.create_index(op.f('ix_lots_lot_number'), 'lots', ['lot_number'], unique=True)
    op.create_index(op.f('ix_lots_id'), 'lots', ['id'], unique=False)

    # 4. Images table
    op.create_table(
        'images',
        sa.Column('id', sa.Integer(), primary_key=True, nullable=False),
        sa.Column('lot_id', sa.Integer(), sa.ForeignKey('lots.id', ondelete='CASCADE'), nullable=False),
        sa.Column('storage_key', sa.String(length=500), nullable=False),
        sa.Column('sha256', sa.String(length=64), nullable=False),
        sa.Column('width', sa.Integer(), nullable=True),
        sa.Column('height', sa.Integer(), nullable=True),
        sa.Column('source', sa.String(length=50), nullable=False, server_default='camera'),
        sa.Column('captured_at', sa.DateTime(), nullable=False),
        sa.Column('capture_mode', sa.String(length=50), nullable=False, server_default='online'),
    )
    op.create_index(op.f('ix_images_sha256'), 'images', ['sha256'], unique=False)
    op.create_index(op.f('ix_images_id'), 'images', ['id'], unique=False)

    # 5. Grade results table
    op.create_table(
        'grade_results',
        sa.Column('id', sa.Integer(), primary_key=True, nullable=False),
        sa.Column('lot_id', sa.Integer(), sa.ForeignKey('lots.id', ondelete='CASCADE'), nullable=False),
        sa.Column('grade_a_pct', sa.Float(), nullable=False),
        sa.Column('urs_pct', sa.Float(), nullable=False),
        sa.Column('total_count', sa.Integer(), nullable=False, server_default='0'),
        sa.Column('raw_counts', sa.JSON(), nullable=False),
        sa.Column('defect_breakdown', sa.JSON(), nullable=False),
        sa.Column('rule_version', sa.String(length=50), nullable=False),
        sa.Column('computed_at', sa.DateTime(), nullable=False),
    )
    op.create_index(op.f('ix_grade_results_lot_id'), 'grade_results', ['lot_id'], unique=False)
    op.create_index(op.f('ix_grade_results_id'), 'grade_results', ['id'], unique=False)

    # 6. Reports table
    op.create_table(
        'reports',
        sa.Column('id', sa.Integer(), primary_key=True, nullable=False),
        sa.Column('lot_id', sa.Integer(), sa.ForeignKey('lots.id', ondelete='CASCADE'), nullable=False),
        sa.Column('version', sa.Integer(), nullable=False, server_default='1'),
        sa.Column('superseded_by', sa.Integer(), sa.ForeignKey('reports.id', ondelete='SET NULL'), nullable=True),
        sa.Column('pdf_path', sa.String(length=500), nullable=True),
        sa.Column('report_hash', sa.String(length=64), nullable=True),
        sa.Column('rule_version', sa.String(length=50), nullable=False),
        sa.Column('is_mock', sa.Boolean(), nullable=False, server_default='0'),
        sa.Column('generated_by', sa.Integer(), sa.ForeignKey('users.id', ondelete='SET NULL'), nullable=True),
        sa.Column('generated_at', sa.DateTime(), nullable=False),
    )
    op.create_index(op.f('ix_reports_lot_id'), 'reports', ['lot_id'], unique=False)
    op.create_index(op.f('ix_reports_id'), 'reports', ['id'], unique=False)

    # 7. Audit log table
    op.create_table(
        'audit_log',
        sa.Column('id', sa.Integer(), primary_key=True, nullable=False),
        sa.Column('actor_id', sa.Integer(), sa.ForeignKey('users.id', ondelete='SET NULL'), nullable=True),
        sa.Column('action', sa.String(length=100), nullable=False),
        sa.Column('entity_type', sa.String(length=100), nullable=False),
        sa.Column('entity_id', sa.Integer(), nullable=False),
        sa.Column('before', sa.JSON(), nullable=True),
        sa.Column('after', sa.JSON(), nullable=True),
        sa.Column('reason', sa.String(length=500), nullable=True),
        sa.Column('created_at', sa.DateTime(), nullable=False),
    )
    op.create_index(op.f('ix_audit_log_actor_id'), 'audit_log', ['actor_id'], unique=False)
    op.create_index(op.f('ix_audit_log_entity_id'), 'audit_log', ['entity_id'], unique=False)
    op.create_index(op.f('ix_audit_log_id'), 'audit_log', ['id'], unique=False)

    # 8. Onion detections table
    op.create_table(
        'onion_detections',
        sa.Column('id', sa.Integer(), primary_key=True, nullable=False),
        sa.Column('lot_id', sa.Integer(), sa.ForeignKey('lots.id', ondelete='CASCADE'), nullable=False),
        sa.Column('image_id', sa.Integer(), sa.ForeignKey('images.id', ondelete='CASCADE'), nullable=False),
        sa.Column('bbox', sa.JSON(), nullable=False),
        sa.Column('mask_polygon', sa.JSON(), nullable=True),
        sa.Column('original_class', sa.String(length=50), nullable=False),
        sa.Column('current_class', sa.String(length=50), nullable=False),
        sa.Column('confidence', sa.Float(), nullable=False, server_default='1.0'),
        sa.Column('diameter_cm', sa.Float(), nullable=True),
        sa.Column('is_overridden', sa.Boolean(), nullable=False, server_default='0'),
        sa.Column('created_at', sa.DateTime(), nullable=False),
    )
    op.create_index(op.f('ix_onion_detections_lot_id'), 'onion_detections', ['lot_id'], unique=False)
    op.create_index(op.f('ix_onion_detections_image_id'), 'onion_detections', ['image_id'], unique=False)
    op.create_index(op.f('ix_onion_detections_id'), 'onion_detections', ['id'], unique=False)


def downgrade() -> None:
    op.drop_table('onion_detections')
    op.drop_table('audit_log')
    op.drop_table('reports')
    op.drop_table('grade_results')
    op.drop_table('images')
    op.drop_table('lots')
    op.drop_table('users')
    op.drop_table('centres')
