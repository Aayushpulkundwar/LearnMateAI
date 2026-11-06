"""store mastery scores as percentages

Revision ID: 0007_concept_mastery_scores
Revises: 0006_assessment_evaluations
"""
from alembic import op
import sqlalchemy as sa
revision='0007_concept_mastery_scores'; down_revision='0006_assessment_evaluations'; branch_labels=None; depends_on=None
def upgrade():
    op.drop_constraint('ck_topic_mastery_score','topic_mastery',type_='check'); op.drop_constraint('ck_topic_mastery_confidence','topic_mastery',type_='check')
    op.alter_column('topic_mastery','mastery_score',type_=sa.Numeric(5,2),postgresql_using='mastery_score * 100')
    op.alter_column('topic_mastery','confidence_level',type_=sa.String(30),postgresql_using="'Insufficient Evidence'")
    op.create_check_constraint('ck_topic_mastery_score','topic_mastery','mastery_score >= 0 AND mastery_score <= 100')
    op.drop_constraint('ck_mastery_history_previous_score','mastery_history',type_='check'); op.drop_constraint('ck_mastery_history_updated_score','mastery_history',type_='check')
    op.alter_column('mastery_history','previous_score',type_=sa.Numeric(5,2),postgresql_using='previous_score * 100'); op.alter_column('mastery_history','updated_score',type_=sa.Numeric(5,2),postgresql_using='updated_score * 100')
    op.create_check_constraint('ck_mastery_history_previous_score','mastery_history','previous_score >= 0 AND previous_score <= 100'); op.create_check_constraint('ck_mastery_history_updated_score','mastery_history','updated_score >= 0 AND updated_score <= 100')
def downgrade(): pass
