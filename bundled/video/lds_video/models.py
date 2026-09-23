"""Video-owned ORM mappings over the durable historical table schema."""
from sqlalchemy import event
from lds_sdk.database import for_plugin
from lds_sdk.video_data import delete_dataset_links, delete_clip_links

db = for_plugin("video", tables=("video_bank", "video_source", "video_clip", "video_dataset", "video_dataset_clip", "video_test_clip", "video_checkpoint_preview"))

class VideoBank(db.BaseMapped):
    __table__ = db.table('video_bank')

    def __repr__(self):
        return f'<VideoBank {self.id} {self.name}>'

class VideoSource(db.BaseMapped):
    __table__ = db.table('video_source')

    def __repr__(self):
        return f'<VideoSource {self.id} bank={self.bank_id} {self.relpath}>'

class VideoClip(db.BaseMapped):
    __table__ = db.table('video_clip')

    def __repr__(self):
        return f'<VideoClip {self.id} src={self.source_id} {self.start_s}-{self.end_s}>'

class VideoDataset(db.BaseMapped):
    __table__ = db.table('video_dataset')

    def __repr__(self):
        return f'<VideoDataset {self.id} {self.name} {self.target_profile}>'

class VideoDatasetClip(db.BaseMapped):
    __table__ = db.table('video_dataset_clip')

    def __repr__(self):
        return f'<VideoDatasetClip {self.id} ds={self.dataset_id} {self.filename}>'

class VideoTestClip(db.BaseMapped):
    __table__ = db.table('video_test_clip')

    def __repr__(self):
        return f'<VideoTestClip {self.id} {self.status} lora={self.lora}>'

class VideoCheckpointPreview(db.BaseMapped):
    __table__ = db.table('video_checkpoint_preview')


@event.listens_for(VideoDataset, 'before_delete')
def _delete_dataset_links(_mapper, connection, dataset):
    delete_dataset_links(connection, dataset.id)


@event.listens_for(VideoTestClip, 'before_delete')
def _delete_clip_links(_mapper, connection, clip):
    delete_clip_links(connection, clip.id)
