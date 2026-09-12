"""Video mappings over the six historical public table schemas."""
from lds_sdk.database import for_plugin

db = for_plugin("video", tables=('video_bank', 'video_source', 'video_clip', 'video_dataset', 'video_dataset_clip', 'video_test_clip'))

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
