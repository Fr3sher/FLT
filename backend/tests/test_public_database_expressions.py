"""SQL expression helpers retain the plugin's table boundary."""
import pytest

pytestmark = pytest.mark.plugins('canvas')


def test_owned_aggregates_and_boolean_filters_use_the_host_transaction(app):
    from app.extensions import db
    from app.models import FaceDataset
    from lds_canvas.models import CanvasNodePosition as Position, db as owner
    with app.app_context():
        dataset = FaceDataset(name='Expression fixture', trigger_word='fixture')
        db.session.add(dataset)
        db.session.commit()
        owner.session.add_all([
            Position(dataset_id=dataset.id, record_id=1, x=12, y=34),
            Position(dataset_id=dataset.id, record_id=2, x=56, y=78),
        ])
        owner.session.commit()
        query = owner.session.query(owner.func.count(Position.id))
        assert query.filter(owner.or_(Position.x == 12, Position.y == 99)).scalar() == 1
        assert owner.session.query(Position.dataset_id, owner.func.count(Position.id)).group_by(
            Position.dataset_id).all() == [(dataset.id, 2)]


def test_expression_helpers_cannot_query_another_owners_table(app):
    from app.models import FaceDataset
    from lds_canvas.models import CanvasNodePosition as Position, db as owner
    with app.app_context():
        with pytest.raises(ValueError, match='does not belong'):
            owner.session.query(owner.func.count(FaceDataset.id))
        with pytest.raises(ValueError, match='does not belong'):
            owner.session.query(Position).filter(owner.or_(Position.x == 1, FaceDataset.id == 1))
