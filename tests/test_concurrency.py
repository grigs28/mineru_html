"""v0.9.0 队列 2 并发工人模型测试（无 GPU 降级模式，走模拟处理路径）"""
import asyncio
import os
import time
from pathlib import Path

from src.task.manager import TaskManager
from src.task.models import TaskStatus

REPO_ROOT = Path(__file__).parent.parent


def test_two_workers_overlap():
    """3 个模拟任务（每个约 3s）：2 并发时总时长应远小于串行的 9s，且出现同时处理"""
    # test_startup.py 在导入期把 cwd 切到 tests/，process_single_task 用相对路径 ./output，
    # 这里切回仓库根保证找到输出目录
    old_cwd = os.getcwd()
    os.chdir(REPO_ROOT)
    try:
        _run_overlap_case()
    finally:
        os.chdir(old_cwd)


def _run_overlap_case():
    async def run():
        tm = TaskManager()
        # 测试不写 git 跟踪的 file_list.json
        tm.sync_task_to_file_list = lambda task: None

        task_ids = [tm.create_task(f"bench_{i}.pdf") for i in range(3)]
        max_overlap = 0

        async def watch():
            nonlocal max_overlap
            for _ in range(300):
                n = sum(1 for t in tm.tasks.values() if t.status == TaskStatus.PROCESSING)
                max_overlap = max(max_overlap, n)
                if all(t.status == TaskStatus.COMPLETED for t in tm.tasks.values()):
                    return
                await asyncio.sleep(0.1)

        for tid in task_ids:
            tm.add_to_queue(tid)

        t0 = time.monotonic()
        watcher = asyncio.create_task(watch())
        await watcher
        wall = time.monotonic() - t0
        return wall, max_overlap, tm

    wall, max_overlap, tm = asyncio.run(run())

    assert all(t.status == TaskStatus.COMPLETED for t in tm.tasks.values()), "所有任务应完成"
    assert max_overlap == 2, f"应出现 2 任务同时处理，实际最大并行 {max_overlap}"
    assert wall < 8, f"2 并发 3 任务应明显快于串行 9s，实际 {wall:.1f}s"
    print(f"✅ 2 并发验证通过：墙钟 {wall:.1f}s，最大并行 {max_overlap}（串行需 ~9s）")


def test_pick_next_task_atomic():
    """原子取任务：连续取两个不能是同一个"""
    tm = TaskManager()
    tm.sync_task_to_file_list = lambda task: None
    a = tm.create_task("a.pdf")
    b = tm.create_task("b.pdf")
    tm.tasks[a].status = TaskStatus.QUEUED
    tm.tasks[b].status = TaskStatus.QUEUED

    first = tm._pick_next_task()
    second = tm._pick_next_task()
    assert first != second and {first, second} == {a, b}, "两个工人不能取到同一任务"
    assert tm._pick_next_task() is None, "取空后应返回 None"
    print("✅ 原子取任务验证通过")


if __name__ == "__main__":
    test_pick_next_task_atomic()
    test_two_workers_overlap()
