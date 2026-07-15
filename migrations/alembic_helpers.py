"""
Alembic database migration utilities
"""

from alembic import op
import sqlalchemy as sa
from geoalchemy2 import Geometry


def create_base_tables():
    """Create base tables with PostGIS support"""
    
    # Create extensions
    op.execute('CREATE EXTENSION IF NOT EXISTS "uuid-ossp"')
    op.execute('CREATE EXTENSION IF NOT EXISTS "postgis"')
    
    # Assets table
    op.create_table(
        'transmission_assets',
        sa.Column('id', sa.String(36), primary_key=True, default='uuid_generate_v4()'),
        sa.Column('name', sa.String(255), nullable=False),
        sa.Column('asset_type', sa.String(50), nullable=False),
        sa.Column('status', sa.String(50), default='active'),
        sa.Column('geom', Geometry('POINT', srid=4326), nullable=False),
        sa.Column('description', sa.Text()),
        sa.Column('metadata', sa.JSON()),
        sa.Column('created_at', sa.DateTime, default=sa.func.now()),
        sa.Column('updated_at', sa.DateTime, default=sa.func.now(), onupdate=sa.func.now()),
        sa.Column('deleted_at', sa.DateTime),
        sa.Index('idx_assets_asset_type', 'asset_type'),
        sa.Index('idx_assets_status', 'status'),
        sa.Index('idx_assets_geom', 'geom', postgresql_using='gist'),
    )
    
    # Health scores table
    op.create_table(
        'asset_health_scores',
        sa.Column('id', sa.String(36), primary_key=True),
        sa.Column('asset_id', sa.String(36), sa.ForeignKey('transmission_assets.id')),
        sa.Column('health_score', sa.Float),
        sa.Column('health_status', sa.String(50)),
        sa.Column('structural_integrity', sa.Float),
        sa.Column('thermal_condition', sa.Float),
        sa.Column('operational_performance', sa.Float),
        sa.Column('calculated_at', sa.DateTime, default=sa.func.now()),
    )
    
    # Imagery metadata table
    op.create_table(
        'satellite_imagery_metadata',
        sa.Column('id', sa.String(36), primary_key=True),
        sa.Column('source', sa.String(50)),
        sa.Column('acquisition_date', sa.DateTime),
        sa.Column('cloud_cover', sa.Float),
        sa.Column('s3_path', sa.String(500)),
        sa.Column('geom', Geometry('POLYGON', srid=4326)),
        sa.Column('metadata', sa.JSON()),
        sa.Column('created_at', sa.DateTime, default=sa.func.now()),
    )


def create_alert_tables():
    """Create alert-related tables"""
    
    op.create_table(
        'alerts',
        sa.Column('id', sa.String(36), primary_key=True),
        sa.Column('asset_id', sa.String(36), sa.ForeignKey('transmission_assets.id')),
        sa.Column('alert_type', sa.String(50)),
        sa.Column('severity', sa.String(20)),
        sa.Column('status', sa.String(20), default='open'),
        sa.Column('description', sa.Text()),
        sa.Column('geom', Geometry('POINT', srid=4326)),
        sa.Column('created_at', sa.DateTime, default=sa.func.now()),
        sa.Column('acknowledged_at', sa.DateTime),
        sa.Column('resolved_at', sa.DateTime),
        sa.Index('idx_alerts_severity', 'severity'),
        sa.Index('idx_alerts_status', 'status'),
    )
