import os
import sys
import unittest.mock as mock

# Block SQLAlchemy import by pre-mocking shared.database
_shared_db = mock.MagicMock()
_shared_db.get_db_connection.return_value = None
_shared_db.init_db.return_value = False
_shared_db.store_job_result.return_value = None
_shared_db.update_job_status.return_value = None
_shared_db.get_job_record.return_value = None
_shared_db.get_submissions_by_batch.return_value = []
_shared_db.create_user.return_value = None
_shared_db.get_user.return_value = None
_shared_db.verify_user.return_value = None
_shared_db.SimilarityMatrix = mock.MagicMock()

sys.modules['shared.database'] = _shared_db

_worker_dir = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
if _worker_dir not in sys.path:
    sys.path.insert(0, _worker_dir)

_root = os.path.abspath(os.path.join(_worker_dir, ".."))
if _root not in sys.path:
    sys.path.insert(0, _root)
