"""Product-owned mappings over the historical Canvas tables."""
from lds_sdk.database import for_plugin

db = for_plugin('canvas', tables=('canvas_node_position', 'canvas_image_node',
                                 'canvas_lane_placement', 'canvas_layout_preset'))

class CanvasNodePosition(db.BaseMapped):
    __table__ = db.table('canvas_node_position')

class CanvasImageNode(db.BaseMapped):
    __table__ = db.table('canvas_image_node')

class CanvasLanePlacement(db.BaseMapped):
    __table__ = db.table('canvas_lane_placement')

class CanvasLayoutPreset(db.BaseMapped):
    __table__ = db.table('canvas_layout_preset')
