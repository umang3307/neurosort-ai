import importlib
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).parent.parent))


@pytest.fixture()
def storage_module(tmp_path, monkeypatch):
    """
    Reload storage.py pointed at a temp DB file so tests never touch the
    real data/neurosort.db used by the running app.
    """
    import storage as storage_mod

    importlib.reload(storage_mod)
    monkeypatch.setattr(storage_mod, "DB_PATH", tmp_path / "test.db")
    storage_mod.init_db()
    return storage_mod


def test_init_db_creates_file(storage_module, tmp_path):
    assert (tmp_path / "test.db").exists()


def test_add_and_get_open_tasks(storage_module):
    storage_module.add_task("do_now", "Reply to Sarah")
    storage_module.add_task("schedule", "Dentist", detail="next Tuesday")

    open_tasks = storage_module.get_open_tasks()
    contents = {row["content"] for row in open_tasks}
    assert "Reply to Sarah" in contents
    assert "Dentist" in contents


def test_get_open_tasks_filters_by_category(storage_module):
    storage_module.add_task("do_now", "Task A")
    storage_module.add_task("archive", "Idea B")

    only_archive = storage_module.get_open_tasks(category="archive")
    assert len(only_archive) == 1
    assert only_archive[0]["content"] == "Idea B"


def test_update_task_status(storage_module):
    task_id = storage_module.add_task("do_now", "Finish report")
    storage_module.update_task_status(task_id, "done")

    open_tasks = storage_module.get_open_tasks("do_now")
    assert all(row["id"] != task_id for row in open_tasks)


def test_log_session_and_stats(storage_module):
    storage_module.add_task("do_now", "A")
    storage_module.add_task("archive", "B")
    storage_module.log_session("some brain dump", 72)

    stats = storage_module.get_stats()
    assert stats["total_tasks"] == 2
    assert stats["by_category"]["do_now"] == 1
    assert stats["by_category"]["archive"] == 1
    assert stats["avg_cognitive_load"] == 72.0


def test_get_history_orders_most_recent_first(storage_module):
    storage_module.add_task("do_now", "First")
    storage_module.add_task("do_now", "Second")

    history = storage_module.get_history(limit=10)
    assert history[0]["content"] == "Second"
    assert history[1]["content"] == "First"
