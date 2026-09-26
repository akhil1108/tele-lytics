"""initial schema

Revision ID: 0001_initial_schema
Revises: 
Create Date: 2026-08-26 07:14:58.631805
"""
from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = "0001_initial_schema"
down_revision: str | None = None
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table('organizations',
    sa.Column('id', sa.String(length=36), nullable=False),
    sa.Column('name', sa.String(length=160), nullable=False),
    sa.Column('slug', sa.String(length=80), nullable=False),
    sa.Column('timezone', sa.String(length=64), nullable=False),
    sa.Column('retention_days', sa.Integer(), nullable=False),
    sa.Column('settings', sa.JSON(), nullable=False),
    sa.Column('created_at', sa.DateTime(timezone=True), nullable=False),
    sa.Column('updated_at', sa.DateTime(timezone=True), nullable=False),
    sa.PrimaryKeyConstraint('id'),
    sa.UniqueConstraint('slug')
    )
    op.create_table('audit_logs',
    sa.Column('id', sa.String(length=36), nullable=False),
    sa.Column('org_id', sa.String(length=36), nullable=False),
    sa.Column('actor_user_id', sa.String(length=36), nullable=True),
    sa.Column('actor_type', sa.String(length=20), nullable=False),
    sa.Column('action', sa.String(length=80), nullable=False),
    sa.Column('entity_type', sa.String(length=40), nullable=True),
    sa.Column('entity_id', sa.String(length=36), nullable=True),
    sa.Column('payload', sa.JSON(), nullable=False),
    sa.Column('ip_address', sa.String(length=64), nullable=True),
    sa.Column('created_at', sa.DateTime(timezone=True), nullable=False),
    sa.ForeignKeyConstraint(['org_id'], ['organizations.id'], ondelete='CASCADE'),
    sa.PrimaryKeyConstraint('id')
    )
    with op.batch_alter_table('audit_logs', schema=None) as batch_op:
        batch_op.create_index(batch_op.f('ix_audit_logs_org_id'), ['org_id'], unique=False)
        batch_op.create_index('ix_audit_org_created', ['org_id', 'created_at'], unique=False)

    op.create_table('users',
    sa.Column('id', sa.String(length=36), nullable=False),
    sa.Column('org_id', sa.String(length=36), nullable=False),
    sa.Column('email', sa.String(length=254), nullable=False),
    sa.Column('full_name', sa.String(length=160), nullable=False),
    sa.Column('password_hash', sa.String(length=255), nullable=False),
    sa.Column('role', sa.String(length=20), nullable=False),
    sa.Column('is_active', sa.Boolean(), nullable=False),
    sa.Column('last_login_at', sa.DateTime(timezone=True), nullable=True),
    sa.Column('created_at', sa.DateTime(timezone=True), nullable=False),
    sa.Column('updated_at', sa.DateTime(timezone=True), nullable=False),
    sa.ForeignKeyConstraint(['org_id'], ['organizations.id'], ondelete='CASCADE'),
    sa.PrimaryKeyConstraint('id'),
    sa.UniqueConstraint('org_id', 'email', name='uq_users_org_email')
    )
    with op.batch_alter_table('users', schema=None) as batch_op:
        batch_op.create_index(batch_op.f('ix_users_org_id'), ['org_id'], unique=False)

    op.create_table('agents',
    sa.Column('id', sa.String(length=36), nullable=False),
    sa.Column('org_id', sa.String(length=36), nullable=False),
    sa.Column('user_id', sa.String(length=36), nullable=True),
    sa.Column('employee_code', sa.String(length=40), nullable=True),
    sa.Column('display_name', sa.String(length=160), nullable=False),
    sa.Column('phone_number', sa.String(length=20), nullable=False),
    sa.Column('team', sa.String(length=80), nullable=True),
    sa.Column('status', sa.String(length=20), nullable=False),
    sa.Column('status_changed_at', sa.DateTime(timezone=True), nullable=True),
    sa.Column('last_seen_at', sa.DateTime(timezone=True), nullable=True),
    sa.Column('current_call_id', sa.String(length=36), nullable=True),
    sa.Column('is_active', sa.Boolean(), nullable=False),
    sa.Column('created_at', sa.DateTime(timezone=True), nullable=False),
    sa.Column('updated_at', sa.DateTime(timezone=True), nullable=False),
    sa.ForeignKeyConstraint(['org_id'], ['organizations.id'], ondelete='CASCADE'),
    sa.ForeignKeyConstraint(['user_id'], ['users.id'], ondelete='SET NULL'),
    sa.PrimaryKeyConstraint('id'),
    sa.UniqueConstraint('org_id', 'employee_code', name='uq_agents_org_code'),
    sa.UniqueConstraint('org_id', 'phone_number', name='uq_agents_org_number')
    )
    with op.batch_alter_table('agents', schema=None) as batch_op:
        batch_op.create_index(batch_op.f('ix_agents_org_id'), ['org_id'], unique=False)
        batch_op.create_index('ix_agents_org_status', ['org_id', 'status'], unique=False)
        batch_op.create_index(batch_op.f('ix_agents_user_id'), ['user_id'], unique=False)

    op.create_table('calls',
    sa.Column('id', sa.String(length=36), nullable=False),
    sa.Column('org_id', sa.String(length=36), nullable=False),
    sa.Column('agent_id', sa.String(length=36), nullable=False),
    sa.Column('external_ref', sa.String(length=80), nullable=True),
    sa.Column('direction', sa.String(length=16), nullable=False),
    sa.Column('agent_number', sa.String(length=20), nullable=False),
    sa.Column('customer_number', sa.String(length=20), nullable=False),
    sa.Column('customer_name', sa.String(length=160), nullable=True),
    sa.Column('started_at', sa.DateTime(timezone=True), nullable=False),
    sa.Column('ended_at', sa.DateTime(timezone=True), nullable=True),
    sa.Column('duration_seconds', sa.Integer(), nullable=True),
    sa.Column('status', sa.String(length=20), nullable=False),
    sa.Column('disposition', sa.String(length=80), nullable=True),
    sa.Column('recording_expected', sa.Boolean(), nullable=False),
    sa.Column('recording_skipped_reason', sa.String(length=120), nullable=True),
    sa.Column('has_recording', sa.Boolean(), nullable=False),
    sa.Column('call_metadata', sa.JSON(), nullable=False),
    sa.Column('created_at', sa.DateTime(timezone=True), nullable=False),
    sa.Column('updated_at', sa.DateTime(timezone=True), nullable=False),
    sa.ForeignKeyConstraint(['agent_id'], ['agents.id'], ondelete='CASCADE'),
    sa.ForeignKeyConstraint(['org_id'], ['organizations.id'], ondelete='CASCADE'),
    sa.PrimaryKeyConstraint('id'),
    sa.UniqueConstraint('org_id', 'external_ref', name='uq_calls_org_external_ref')
    )
    with op.batch_alter_table('calls', schema=None) as batch_op:
        batch_op.create_index(batch_op.f('ix_calls_agent_id'), ['agent_id'], unique=False)
        batch_op.create_index(batch_op.f('ix_calls_customer_number'), ['customer_number'], unique=False)
        batch_op.create_index('ix_calls_org_agent_started', ['org_id', 'agent_id', 'started_at'], unique=False)
        batch_op.create_index(batch_op.f('ix_calls_org_id'), ['org_id'], unique=False)
        batch_op.create_index('ix_calls_org_started', ['org_id', 'started_at'], unique=False)
        batch_op.create_index('ix_calls_org_status', ['org_id', 'status'], unique=False)

    op.create_table('devices',
    sa.Column('id', sa.String(length=36), nullable=False),
    sa.Column('org_id', sa.String(length=36), nullable=False),
    sa.Column('agent_id', sa.String(length=36), nullable=False),
    sa.Column('platform', sa.String(length=16), nullable=False),
    sa.Column('device_name', sa.String(length=120), nullable=True),
    sa.Column('os_version', sa.String(length=40), nullable=True),
    sa.Column('app_version', sa.String(length=40), nullable=True),
    sa.Column('push_token', sa.String(length=255), nullable=True),
    sa.Column('token_hash', sa.String(length=64), nullable=False),
    sa.Column('paired_at', sa.DateTime(timezone=True), nullable=False),
    sa.Column('last_seen_at', sa.DateTime(timezone=True), nullable=True),
    sa.Column('revoked_at', sa.DateTime(timezone=True), nullable=True),
    sa.ForeignKeyConstraint(['agent_id'], ['agents.id'], ondelete='CASCADE'),
    sa.ForeignKeyConstraint(['org_id'], ['organizations.id'], ondelete='CASCADE'),
    sa.PrimaryKeyConstraint('id'),
    sa.UniqueConstraint('token_hash')
    )
    with op.batch_alter_table('devices', schema=None) as batch_op:
        batch_op.create_index(batch_op.f('ix_devices_agent_id'), ['agent_id'], unique=False)
        batch_op.create_index('ix_devices_org_agent', ['org_id', 'agent_id'], unique=False)
        batch_op.create_index(batch_op.f('ix_devices_org_id'), ['org_id'], unique=False)

    op.create_table('pairing_codes',
    sa.Column('id', sa.String(length=36), nullable=False),
    sa.Column('org_id', sa.String(length=36), nullable=False),
    sa.Column('agent_id', sa.String(length=36), nullable=False),
    sa.Column('code_hash', sa.String(length=64), nullable=False),
    sa.Column('expires_at', sa.DateTime(timezone=True), nullable=False),
    sa.Column('used_at', sa.DateTime(timezone=True), nullable=True),
    sa.Column('created_by_user_id', sa.String(length=36), nullable=True),
    sa.Column('created_at', sa.DateTime(timezone=True), nullable=False),
    sa.ForeignKeyConstraint(['agent_id'], ['agents.id'], ondelete='CASCADE'),
    sa.ForeignKeyConstraint(['created_by_user_id'], ['users.id'], ondelete='SET NULL'),
    sa.ForeignKeyConstraint(['org_id'], ['organizations.id'], ondelete='CASCADE'),
    sa.PrimaryKeyConstraint('id'),
    sa.UniqueConstraint('code_hash')
    )
    with op.batch_alter_table('pairing_codes', schema=None) as batch_op:
        batch_op.create_index(batch_op.f('ix_pairing_codes_agent_id'), ['agent_id'], unique=False)
        batch_op.create_index(batch_op.f('ix_pairing_codes_created_by_user_id'), ['created_by_user_id'], unique=False)
        batch_op.create_index(batch_op.f('ix_pairing_codes_org_id'), ['org_id'], unique=False)

    op.create_table('phone_number_policies',
    sa.Column('id', sa.String(length=36), nullable=False),
    sa.Column('org_id', sa.String(length=36), nullable=False),
    sa.Column('e164', sa.String(length=20), nullable=False),
    sa.Column('label', sa.String(length=160), nullable=True),
    sa.Column('kind', sa.String(length=20), nullable=False),
    sa.Column('owner_agent_id', sa.String(length=36), nullable=True),
    sa.Column('recording_enabled', sa.Boolean(), nullable=False),
    sa.Column('record_inbound', sa.Boolean(), nullable=False),
    sa.Column('record_outbound', sa.Boolean(), nullable=False),
    sa.Column('consent_required', sa.Boolean(), nullable=False),
    sa.Column('consent_prompt', sa.Text(), nullable=True),
    sa.Column('retention_days', sa.Integer(), nullable=True),
    sa.Column('notes', sa.Text(), nullable=True),
    sa.Column('created_by_user_id', sa.String(length=36), nullable=True),
    sa.Column('created_at', sa.DateTime(timezone=True), nullable=False),
    sa.Column('updated_at', sa.DateTime(timezone=True), nullable=False),
    sa.ForeignKeyConstraint(['created_by_user_id'], ['users.id'], ondelete='SET NULL'),
    sa.ForeignKeyConstraint(['org_id'], ['organizations.id'], ondelete='CASCADE'),
    sa.ForeignKeyConstraint(['owner_agent_id'], ['agents.id'], ondelete='SET NULL'),
    sa.PrimaryKeyConstraint('id'),
    sa.UniqueConstraint('org_id', 'e164', name='uq_number_policy_org_e164')
    )
    with op.batch_alter_table('phone_number_policies', schema=None) as batch_op:
        batch_op.create_index('ix_number_policy_org_enabled', ['org_id', 'recording_enabled'], unique=False)
        batch_op.create_index(batch_op.f('ix_phone_number_policies_created_by_user_id'), ['created_by_user_id'], unique=False)
        batch_op.create_index(batch_op.f('ix_phone_number_policies_org_id'), ['org_id'], unique=False)
        batch_op.create_index(batch_op.f('ix_phone_number_policies_owner_agent_id'), ['owner_agent_id'], unique=False)

    op.create_table('analyses',
    sa.Column('id', sa.String(length=36), nullable=False),
    sa.Column('org_id', sa.String(length=36), nullable=False),
    sa.Column('call_id', sa.String(length=36), nullable=False),
    sa.Column('provider', sa.String(length=40), nullable=False),
    sa.Column('model', sa.String(length=120), nullable=True),
    sa.Column('summary', sa.Text(), nullable=False),
    sa.Column('sentiment_overall', sa.String(length=20), nullable=False),
    sa.Column('sentiment_score', sa.Float(), nullable=False),
    sa.Column('customer_satisfied', sa.Boolean(), nullable=True),
    sa.Column('csat_score', sa.Integer(), nullable=True),
    sa.Column('csat_confidence', sa.Float(), nullable=True),
    sa.Column('csat_evidence', sa.Text(), nullable=True),
    sa.Column('agent_talk_ratio', sa.Float(), nullable=True),
    sa.Column('interruption_count', sa.Integer(), nullable=True),
    sa.Column('resolution_status', sa.String(length=40), nullable=True),
    sa.Column('topics', sa.JSON(), nullable=False),
    sa.Column('keywords', sa.JSON(), nullable=False),
    sa.Column('stopword_stats', sa.JSON(), nullable=False),
    sa.Column('filler_stats', sa.JSON(), nullable=False),
    sa.Column('risk_flags', sa.JSON(), nullable=False),
    sa.Column('coaching', sa.JSON(), nullable=False),
    sa.Column('sentiment_timeline', sa.JSON(), nullable=False),
    sa.Column('tone_summary', sa.JSON(), nullable=False),
    sa.Column('token_usage', sa.JSON(), nullable=False),
    sa.Column('processing_ms', sa.Integer(), nullable=True),
    sa.Column('raw', sa.JSON(), nullable=False),
    sa.Column('created_at', sa.DateTime(timezone=True), nullable=False),
    sa.ForeignKeyConstraint(['call_id'], ['calls.id'], ondelete='CASCADE'),
    sa.ForeignKeyConstraint(['org_id'], ['organizations.id'], ondelete='CASCADE'),
    sa.PrimaryKeyConstraint('id'),
    sa.UniqueConstraint('call_id', name='uq_analyses_call')
    )
    with op.batch_alter_table('analyses', schema=None) as batch_op:
        batch_op.create_index(batch_op.f('ix_analyses_call_id'), ['call_id'], unique=False)
        batch_op.create_index('ix_analyses_org_created', ['org_id', 'created_at'], unique=False)
        batch_op.create_index(batch_op.f('ix_analyses_org_id'), ['org_id'], unique=False)

    op.create_table('processing_jobs',
    sa.Column('id', sa.String(length=36), nullable=False),
    sa.Column('org_id', sa.String(length=36), nullable=False),
    sa.Column('call_id', sa.String(length=36), nullable=False),
    sa.Column('stage', sa.String(length=20), nullable=False),
    sa.Column('status', sa.String(length=16), nullable=False),
    sa.Column('attempts', sa.Integer(), nullable=False),
    sa.Column('max_attempts', sa.Integer(), nullable=False),
    sa.Column('last_error', sa.Text(), nullable=True),
    sa.Column('scheduled_at', sa.DateTime(timezone=True), nullable=False),
    sa.Column('started_at', sa.DateTime(timezone=True), nullable=True),
    sa.Column('finished_at', sa.DateTime(timezone=True), nullable=True),
    sa.Column('locked_by', sa.String(length=64), nullable=True),
    sa.Column('locked_at', sa.DateTime(timezone=True), nullable=True),
    sa.Column('created_at', sa.DateTime(timezone=True), nullable=False),
    sa.Column('updated_at', sa.DateTime(timezone=True), nullable=False),
    sa.ForeignKeyConstraint(['call_id'], ['calls.id'], ondelete='CASCADE'),
    sa.ForeignKeyConstraint(['org_id'], ['organizations.id'], ondelete='CASCADE'),
    sa.PrimaryKeyConstraint('id'),
    sa.UniqueConstraint('call_id', 'stage', name='uq_job_call_stage')
    )
    with op.batch_alter_table('processing_jobs', schema=None) as batch_op:
        batch_op.create_index('ix_jobs_claim', ['status', 'scheduled_at'], unique=False)
        batch_op.create_index('ix_jobs_org_status', ['org_id', 'status'], unique=False)
        batch_op.create_index(batch_op.f('ix_processing_jobs_call_id'), ['call_id'], unique=False)
        batch_op.create_index(batch_op.f('ix_processing_jobs_org_id'), ['org_id'], unique=False)

    op.create_table('recordings',
    sa.Column('id', sa.String(length=36), nullable=False),
    sa.Column('org_id', sa.String(length=36), nullable=False),
    sa.Column('call_id', sa.String(length=36), nullable=False),
    sa.Column('storage_backend', sa.String(length=16), nullable=False),
    sa.Column('storage_key', sa.String(length=512), nullable=True),
    sa.Column('mime_type', sa.String(length=80), nullable=False),
    sa.Column('size_bytes', sa.Integer(), nullable=True),
    sa.Column('duration_seconds', sa.Float(), nullable=True),
    sa.Column('sample_rate', sa.Integer(), nullable=True),
    sa.Column('channels', sa.Integer(), nullable=True),
    sa.Column('checksum_sha256', sa.String(length=64), nullable=True),
    sa.Column('status', sa.String(length=20), nullable=False),
    sa.Column('consent_captured', sa.Boolean(), nullable=False),
    sa.Column('uploaded_at', sa.DateTime(timezone=True), nullable=True),
    sa.Column('purge_after', sa.DateTime(timezone=True), nullable=True),
    sa.Column('purged_at', sa.DateTime(timezone=True), nullable=True),
    sa.Column('created_at', sa.DateTime(timezone=True), nullable=False),
    sa.Column('updated_at', sa.DateTime(timezone=True), nullable=False),
    sa.ForeignKeyConstraint(['call_id'], ['calls.id'], ondelete='CASCADE'),
    sa.ForeignKeyConstraint(['org_id'], ['organizations.id'], ondelete='CASCADE'),
    sa.PrimaryKeyConstraint('id'),
    sa.UniqueConstraint('call_id', name='uq_recordings_call')
    )
    with op.batch_alter_table('recordings', schema=None) as batch_op:
        batch_op.create_index(batch_op.f('ix_recordings_call_id'), ['call_id'], unique=False)
        batch_op.create_index(batch_op.f('ix_recordings_org_id'), ['org_id'], unique=False)
        batch_op.create_index('ix_recordings_org_status', ['org_id', 'status'], unique=False)
        batch_op.create_index(batch_op.f('ix_recordings_purge_after'), ['purge_after'], unique=False)

    op.create_table('transcripts',
    sa.Column('id', sa.String(length=36), nullable=False),
    sa.Column('org_id', sa.String(length=36), nullable=False),
    sa.Column('call_id', sa.String(length=36), nullable=False),
    sa.Column('provider', sa.String(length=40), nullable=False),
    sa.Column('model', sa.String(length=120), nullable=True),
    sa.Column('language', sa.String(length=20), nullable=True),
    sa.Column('full_text', sa.Text(), nullable=False),
    sa.Column('word_count', sa.Integer(), nullable=False),
    sa.Column('confidence', sa.Float(), nullable=True),
    sa.Column('tone_overall', sa.String(length=40), nullable=True),
    sa.Column('processing_ms', sa.Integer(), nullable=True),
    sa.Column('raw', sa.JSON(), nullable=False),
    sa.Column('created_at', sa.DateTime(timezone=True), nullable=False),
    sa.ForeignKeyConstraint(['call_id'], ['calls.id'], ondelete='CASCADE'),
    sa.ForeignKeyConstraint(['org_id'], ['organizations.id'], ondelete='CASCADE'),
    sa.PrimaryKeyConstraint('id'),
    sa.UniqueConstraint('call_id', name='uq_transcripts_call')
    )
    with op.batch_alter_table('transcripts', schema=None) as batch_op:
        batch_op.create_index(batch_op.f('ix_transcripts_call_id'), ['call_id'], unique=False)
        batch_op.create_index(batch_op.f('ix_transcripts_org_id'), ['org_id'], unique=False)

    op.create_table('action_items',
    sa.Column('id', sa.String(length=36), nullable=False),
    sa.Column('org_id', sa.String(length=36), nullable=False),
    sa.Column('call_id', sa.String(length=36), nullable=False),
    sa.Column('analysis_id', sa.String(length=36), nullable=True),
    sa.Column('kind', sa.String(length=16), nullable=False),
    sa.Column('title', sa.String(length=300), nullable=False),
    sa.Column('description', sa.Text(), nullable=True),
    sa.Column('owner_role', sa.String(length=20), nullable=True),
    sa.Column('assignee_agent_id', sa.String(length=36), nullable=True),
    sa.Column('priority', sa.String(length=16), nullable=False),
    sa.Column('due_at', sa.DateTime(timezone=True), nullable=True),
    sa.Column('due_hint', sa.String(length=120), nullable=True),
    sa.Column('status', sa.String(length=16), nullable=False),
    sa.Column('source_quote', sa.Text(), nullable=True),
    sa.Column('created_at', sa.DateTime(timezone=True), nullable=False),
    sa.Column('updated_at', sa.DateTime(timezone=True), nullable=False),
    sa.Column('completed_at', sa.DateTime(timezone=True), nullable=True),
    sa.ForeignKeyConstraint(['analysis_id'], ['analyses.id'], ondelete='SET NULL'),
    sa.ForeignKeyConstraint(['assignee_agent_id'], ['agents.id'], ondelete='SET NULL'),
    sa.ForeignKeyConstraint(['call_id'], ['calls.id'], ondelete='CASCADE'),
    sa.ForeignKeyConstraint(['org_id'], ['organizations.id'], ondelete='CASCADE'),
    sa.PrimaryKeyConstraint('id')
    )
    with op.batch_alter_table('action_items', schema=None) as batch_op:
        batch_op.create_index(batch_op.f('ix_action_items_analysis_id'), ['analysis_id'], unique=False)
        batch_op.create_index(batch_op.f('ix_action_items_assignee_agent_id'), ['assignee_agent_id'], unique=False)
        batch_op.create_index(batch_op.f('ix_action_items_call_id'), ['call_id'], unique=False)
        batch_op.create_index('ix_action_items_org_due', ['org_id', 'due_at'], unique=False)
        batch_op.create_index(batch_op.f('ix_action_items_org_id'), ['org_id'], unique=False)
        batch_op.create_index('ix_action_items_org_status', ['org_id', 'status'], unique=False)

    op.create_table('transcript_segments',
    sa.Column('id', sa.String(length=36), nullable=False),
    sa.Column('transcript_id', sa.String(length=36), nullable=False),
    sa.Column('idx', sa.Integer(), nullable=False),
    sa.Column('speaker', sa.String(length=16), nullable=False),
    sa.Column('start_ms', sa.Integer(), nullable=False),
    sa.Column('end_ms', sa.Integer(), nullable=False),
    sa.Column('text', sa.Text(), nullable=False),
    sa.Column('confidence', sa.Float(), nullable=True),
    sa.Column('tone_label', sa.String(length=40), nullable=True),
    sa.Column('tone_confidence', sa.Float(), nullable=True),
    sa.Column('valence', sa.Float(), nullable=True),
    sa.Column('arousal', sa.Float(), nullable=True),
    sa.Column('sentiment', sa.String(length=20), nullable=True),
    sa.ForeignKeyConstraint(['transcript_id'], ['transcripts.id'], ondelete='CASCADE'),
    sa.PrimaryKeyConstraint('id'),
    sa.UniqueConstraint('transcript_id', 'idx', name='uq_segment_transcript_idx')
    )
    with op.batch_alter_table('transcript_segments', schema=None) as batch_op:
        batch_op.create_index('ix_segments_transcript_start', ['transcript_id', 'start_ms'], unique=False)
        batch_op.create_index(batch_op.f('ix_transcript_segments_transcript_id'), ['transcript_id'], unique=False)



def downgrade() -> None:
    with op.batch_alter_table('transcript_segments', schema=None) as batch_op:
        batch_op.drop_index(batch_op.f('ix_transcript_segments_transcript_id'))
        batch_op.drop_index('ix_segments_transcript_start')

    op.drop_table('transcript_segments')
    with op.batch_alter_table('action_items', schema=None) as batch_op:
        batch_op.drop_index('ix_action_items_org_status')
        batch_op.drop_index(batch_op.f('ix_action_items_org_id'))
        batch_op.drop_index('ix_action_items_org_due')
        batch_op.drop_index(batch_op.f('ix_action_items_call_id'))
        batch_op.drop_index(batch_op.f('ix_action_items_assignee_agent_id'))
        batch_op.drop_index(batch_op.f('ix_action_items_analysis_id'))

    op.drop_table('action_items')
    with op.batch_alter_table('transcripts', schema=None) as batch_op:
        batch_op.drop_index(batch_op.f('ix_transcripts_org_id'))
        batch_op.drop_index(batch_op.f('ix_transcripts_call_id'))

    op.drop_table('transcripts')
    with op.batch_alter_table('recordings', schema=None) as batch_op:
        batch_op.drop_index(batch_op.f('ix_recordings_purge_after'))
        batch_op.drop_index('ix_recordings_org_status')
        batch_op.drop_index(batch_op.f('ix_recordings_org_id'))
        batch_op.drop_index(batch_op.f('ix_recordings_call_id'))

    op.drop_table('recordings')
    with op.batch_alter_table('processing_jobs', schema=None) as batch_op:
        batch_op.drop_index(batch_op.f('ix_processing_jobs_org_id'))
        batch_op.drop_index(batch_op.f('ix_processing_jobs_call_id'))
        batch_op.drop_index('ix_jobs_org_status')
        batch_op.drop_index('ix_jobs_claim')

    op.drop_table('processing_jobs')
    with op.batch_alter_table('analyses', schema=None) as batch_op:
        batch_op.drop_index(batch_op.f('ix_analyses_org_id'))
        batch_op.drop_index('ix_analyses_org_created')
        batch_op.drop_index(batch_op.f('ix_analyses_call_id'))

    op.drop_table('analyses')
    with op.batch_alter_table('phone_number_policies', schema=None) as batch_op:
        batch_op.drop_index(batch_op.f('ix_phone_number_policies_owner_agent_id'))
        batch_op.drop_index(batch_op.f('ix_phone_number_policies_org_id'))
        batch_op.drop_index(batch_op.f('ix_phone_number_policies_created_by_user_id'))
        batch_op.drop_index('ix_number_policy_org_enabled')

    op.drop_table('phone_number_policies')
    with op.batch_alter_table('pairing_codes', schema=None) as batch_op:
        batch_op.drop_index(batch_op.f('ix_pairing_codes_org_id'))
        batch_op.drop_index(batch_op.f('ix_pairing_codes_created_by_user_id'))
        batch_op.drop_index(batch_op.f('ix_pairing_codes_agent_id'))

    op.drop_table('pairing_codes')
    with op.batch_alter_table('devices', schema=None) as batch_op:
        batch_op.drop_index(batch_op.f('ix_devices_org_id'))
        batch_op.drop_index('ix_devices_org_agent')
        batch_op.drop_index(batch_op.f('ix_devices_agent_id'))

    op.drop_table('devices')
    with op.batch_alter_table('calls', schema=None) as batch_op:
        batch_op.drop_index('ix_calls_org_status')
        batch_op.drop_index('ix_calls_org_started')
        batch_op.drop_index(batch_op.f('ix_calls_org_id'))
        batch_op.drop_index('ix_calls_org_agent_started')
        batch_op.drop_index(batch_op.f('ix_calls_customer_number'))
        batch_op.drop_index(batch_op.f('ix_calls_agent_id'))

    op.drop_table('calls')
    with op.batch_alter_table('agents', schema=None) as batch_op:
        batch_op.drop_index(batch_op.f('ix_agents_user_id'))
        batch_op.drop_index('ix_agents_org_status')
        batch_op.drop_index(batch_op.f('ix_agents_org_id'))

    op.drop_table('agents')
    with op.batch_alter_table('users', schema=None) as batch_op:
        batch_op.drop_index(batch_op.f('ix_users_org_id'))

    op.drop_table('users')
    with op.batch_alter_table('audit_logs', schema=None) as batch_op:
        batch_op.drop_index('ix_audit_org_created')
        batch_op.drop_index(batch_op.f('ix_audit_logs_org_id'))

    op.drop_table('audit_logs')
    op.drop_table('organizations')
