"""Persistent schemas of migrated products, never their Python ORM models.

All declarations use the host metadata so db.create_all and historical
cleanup work even when the product is absent. No plugin is imported here.
Mapped classes and publication policy belong to the product package.
"""

from app.extensions import db
from ._schema_extend import persistent_table
from app.utils.timestamps import naive_utcnow

civitai_link = persistent_table('civitai_link',
    db.Column('id', db.Integer, primary_key=True),
    db.Column('record_id', db.Integer, nullable=True, index=True),
    db.Column('step', db.Integer, nullable=False),
    db.Column('filename', db.String(255), nullable=False, default=''),
    db.Column('dataset_id', db.Integer, nullable=False, index=True),
    db.Column('model_id', db.Integer, nullable=False),
    db.Column('version_id', db.Integer, nullable=False),
    db.Column('model_name', db.String(255), nullable=False, default=''),
    db.Column('version_name', db.String(255), nullable=False, default=''),
    db.Column('base_model', db.String(64), nullable=True),
    db.Column('published', db.Boolean, nullable=True),
    db.Column('created_at', db.DateTime, default=naive_utcnow),
    db.Column('updated_at', db.DateTime, default=naive_utcnow, onupdate=naive_utcnow),
    db.UniqueConstraint('record_id', 'step', 'filename', name='uq_civitai_link')
)

video_civitai_link = persistent_table('video_civitai_link',
    db.Column('id', db.Integer, primary_key=True),
    db.Column('dataset_id', db.Integer, nullable=False, index=True),
    db.Column('source_key', db.String(48), nullable=False),
    db.Column('save_key', db.String(48), nullable=False),
    db.Column('fingerprint', db.String(64), nullable=False),
    db.Column('filenames', db.Text, nullable=False),
    db.Column('model_id', db.Integer, nullable=False),
    db.Column('version_id', db.Integer, nullable=False),
    db.Column('model_name', db.String(255), nullable=True),
    db.Column('version_name', db.String(255), nullable=True),
    db.Column('base_model', db.String(80), nullable=True),
    db.Column('published', db.Boolean, nullable=True),
    db.Column('complete', db.Boolean, nullable=False, default=True),
    db.Column('created_at', db.DateTime, default=db.func.current_timestamp()),
    db.UniqueConstraint('dataset_id', 'source_key', 'save_key')
)

cloud_training_run = persistent_table('cloud_training_run',
    db.Column('video_preview_key', db.String(36), nullable=True),
    db.Column('id', db.Integer, primary_key=True),
    db.Column('dataset_id', db.Integer, nullable=False),
    db.Column('dataset_table', db.String(32)),
    db.Column('run_name', db.String(255)),
    db.Column('job_name', db.String(255)),
    db.Column('status', db.String(32), default='preparing'),
    db.Column('phase_detail', db.Text, default=''),
    db.Column('vast_instance_id', db.String(32)),
    db.Column('vast_label', db.String(64)),
    db.Column('gpu_name', db.String(64)),
    db.Column('price_per_hour', db.Float),
    db.Column('remote_job_id', db.String(64)),
    db.Column('base_url', db.String(255)),
    db.Column('auth_token', db.String(128)),
    db.Column('staging_dir', db.Text),
    db.Column('checkpoint_local_path', db.Text),
    db.Column('train_params', db.Text),
    db.Column('error', db.Text),
    db.Column('created_at', db.DateTime, default=naive_utcnow),
    db.Column('updated_at', db.DateTime, default=naive_utcnow, onupdate=naive_utcnow),
    db.Column('stop_requested_at', db.DateTime),
    db.Column('finished_at', db.DateTime)
)
