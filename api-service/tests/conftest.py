import importlib.metadata as _im_meta
import os
import sys
import unittest.mock as mock

# pre-mock shared.database so main.py module-level init_db() is a no-op
_shared_db = mock.MagicMock()
_shared_db.init_db.return_value = False
_shared_db.create_assignment.return_value = None
_shared_db.create_job_record.return_value = None
_shared_db.create_notification.return_value = None
_shared_db.create_submission.return_value = None
_shared_db.create_user.return_value = None
_shared_db.delete_assignment.return_value = None
_shared_db.get_admin_stats.return_value = {}
_shared_db.get_assignment.return_value = None
_shared_db.get_assignment_by_access_code.return_value = None
_shared_db.get_cross_batch_comparisons.return_value = []
_shared_db.get_job_record.return_value = None
_shared_db.get_paginated_users.return_value = []
_shared_db.get_pending_notifications.return_value = []
_shared_db.get_similarity_matrix.return_value = {}
_shared_db.get_student_comparison_details.return_value = []
_shared_db.get_submission_by_id.return_value = None
_shared_db.get_submissions_by_batch.return_value = []
_shared_db.get_submissions_count_by_batch.return_value = 0
_shared_db.get_user_by_email.return_value = None
_shared_db.get_user_by_id.return_value = None
_shared_db.list_assignments.return_value = []
_shared_db.mark_notification_sent.return_value = None
_shared_db.update_assignment.return_value = None
_shared_db.update_job_status.return_value = None
_shared_db.update_user_role.return_value = None
sys.modules["shared.database"] = _shared_db

# mock modules that requirementsall.txt does not include
# pydantic calls importlib.metadata.version('email-validator') to check the version,
# so we must patch that too (MagicMock in sys.modules lacks package metadata)
_orig_version = _im_meta.version


def _mock_version(name):
    if name == "email-validator":
        return "2.0.0"
    return _orig_version(name)


_im_meta.version = _mock_version

for _mod_name in ("bcrypt", "jose", "email_validator"):
    _m = mock.MagicMock()
    _m.__name__ = _mod_name
    sys.modules[_mod_name] = _m

# Note: shared.queue_client is NOT mocked globally because that would leak
# into shared/tests/test_queue.py when run in the same session.
# Instead, test_routes.py patches main.queue_client on the specific tests
# that need it (test_result_not_found).

# set env vars needed by main.py
os.environ.setdefault("JWT_SECRET", "test-secret-for-unit-tests")
os.environ.setdefault("DB_HOST", "localhost")
os.environ.setdefault("REDIS_HOST", "localhost")
os.environ.setdefault("REDIS_PASSWORD", "plagio_redis_pass")

_api_dir = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
if _api_dir not in sys.path:
    sys.path.insert(0, _api_dir)

_root = os.path.abspath(os.path.join(_api_dir, ".."))
if _root not in sys.path:
    sys.path.insert(0, _root)
