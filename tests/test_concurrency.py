"""v0.9.x 队列并发测试（无 GPU 降级模式，走模拟处理路径）

v0.9.0: 2 工人模型；v0.9.2: UI/API 双道各 2 并发（总 4）
"""
import asyncio
import os
import time
from pathlib import Path

from src.task.manager import TaskManager
from src.task.models import TaskStatus, QueueStatus

REPO_ROOT = Path(__file__).parent.parent
SIM_TASK_SEC = 3.0  # 模拟处理路径约 3s


def _make_tm():
    tm = TaskManager()
    tm.sync_task_to_file_list = lambda task: None  # 不写 git 跟踪的 file_list.json
    return tm


async def _run_and_watch(tm, task_ids, watch_sec=30):
    """入队并观察最大并行数（按道统计）"""
    max_overlap = {"ui": 0, "api": 0, "total": 0}
    for tid in task_ids:
        tm.add_to_queue(tid)

    t0 = time.monotonic()
    while time.monotonic() - t0 < watch_sec:
        processing = [t for t in tm.tasks.values() if t.status == TaskStatus.PROCESSING]
        max_overlap["total"] = max(max_overlap["total"], len(processing))
        for lane in ("ui", "api"):
            n = sum(1 for t in processing if (t.origin or "api") == lane)
            max_overlap[lane] = max(max_overlap[lane], n)
        if all(t.status == TaskStatus.COMPLETED for t in tm.tasks.values()):
            break
        await asyncio.sleep(0.1)
    return time.monotonic() - t0, max_overlap


def test_two_workers_overlap():
    """同道 3 任务：2 并发，总时长明显小于串行"""
    old_cwd = os.getcwd()
    os.chdir(REPO_ROOT)
    try:
        async def run():
            tm = _make_tm()
            ids = [tm.create_task(f"api_{i}.pdf") for i in range(3)]
            return tm, await _run_and_watch(tm, ids)

        tm, (wall, overlap) = asyncio.run(run())
    finally:
        os.chdir(old_cwd)

    assert all(t.status == TaskStatus.COMPLETED for t in tm.tasks.values())
    assert overlap["api"] == 2, f"API 道应 2 并发，实际 {overlap['api']}"
    assert wall < 8, f"2 并发 3 任务应明显快于串行 9s，实际 {wall:.1f}s"
    print(f"✅ 同道 2 并发：墙钟 {wall:.1f}s，API 道最大并行 {overlap['api']}")


def test_lanes_isolated():
    """双道隔离：API 道占满 2 个时，UI 任务仍立即开始（总并行 3）"""
    old_cwd = os.getcwd()
    os.chdir(REPO_ROOT)
    try:
        async def run():
            tm = _make_tm()
            ids = [tm.create_task(f"api_{i}.pdf", origin="api") for i in range(3)]
            ids.append(tm.create_task("ui_0.pdf", origin="ui"))
            return tm, await _run_and_watch(tm, ids)

        tm, (wall, overlap) = asyncio.run(run())
    finally:
        os.chdir(old_cwd)

    assert all(t.status == TaskStatus.COMPLETED for t in tm.tasks.values())
    assert overlap["api"] == 2 and overlap["ui"] == 1, f"双道应同时跑，实际 {overlap}"
    assert overlap["total"] == 3, f"API 占满时 UI 应并行，实际总并行 {overlap['total']}"
    print(f"✅ 双道隔离：{overlap}，墙钟 {wall:.1f}s")


def test_pick_next_task_atomic():
    """原子取任务 + 按道过滤：同道不重复取，他道任务不被本道取走"""
    tm = _make_tm()
    a1 = tm.create_task("a1.pdf", origin="api")
    u1 = tm.create_task("u1.pdf", origin="ui")
    a2 = tm.create_task("a2.pdf", origin="api")
    for tid in (a1, u1, a2):
        tm.tasks[tid].status = TaskStatus.QUEUED

    assert tm._pick_next_task("ui") == u1, "UI 道应取到 UI 任务"
    assert tm._pick_next_task("ui") is None, "UI 道取空"
    first = tm._pick_next_task("api")
    second = tm._pick_next_task("api")
    assert {first, second} == {a1, a2}, "同道两次取不能重复"
    assert tm._pick_next_task("api") is None
    print("✅ 原子取任务 + 按道过滤验证通过")


def test_stop_queue_resets_workers_flag():
    """v0.9.6 回归：清空/停止队列后 _workers_started 必须重置，
    否则工人退出后队列空转（任务永远 QUEUED）"""
    tm = _make_tm()
    tm._workers_started = True  # 模拟工人曾启动
    tm.queue_status = QueueStatus.RUNNING
    tm.stop_queue()
    assert tm._workers_started is False, "stop_queue 必须重置工人标志"
    assert tm.current_processing_tasks == []
    print("✅ stop_queue 重置工人标志验证通过")


if __name__ == "__main__":
    test_stop_queue_resets_workers_flag()
    test_pick_next_task_atomic()
    test_lanes_isolated()
    test_two_workers_overlap()
