"""M4 任务状态机：成功、重试、找不到、超时。"""

from modkit import mission
from modkit.vision import Detection


class World:
    def __init__(self):
        self.p = (0.0, 0.0)
        self.t = 0.0
        self.held = False
        self.look_results = []
        self.pick_results = []
        self.nav_ok = True
        self.dt_nav = 2.0

    def now(self):
        return self.t

    def drive(self, x, y, theta):
        self.t += self.dt_nav
        if self.nav_ok:
            self.p = (x, y)
        return self.nav_ok

    def look(self):
        if self.look_results:
            return self.look_results.pop(0)
        return Detection(10, 10, 100, (0, 0, 9, 9)) if self.at_pick else None

    @property
    def at_pick(self):
        return abs(self.p[0] - 200) < 1

    def pick(self, det):
        ok = self.pick_results.pop(0) if self.pick_results else True
        if ok:
            self.held = True
        return ok

    def drop(self):
        self.held = False
        return True


def run(w, cfg=None):
    return mission.Mission(w.drive, w.look, w.pick, w.drop,
                           cfg=cfg, now=w.now).run()


def test_happy_path():
    w = World()
    r = run(w)
    assert r.success and w.held is False
    assert r.states == ["nav_pick:try1", "look:1", "pick:try1",
                        "nav_drop:try1", "drop"]
    assert r.attempts == 3


def test_search_then_find():
    w = World()
    w.look_results = [None, None, Detection(1, 1, 10, (0, 0, 1, 1))]
    r = run(w)
    assert r.success
    assert "look:3" in r.states


def test_pick_retries_once():
    w = World()
    w.pick_results = [False, True]
    r = run(w)
    assert r.success
    assert "pick:try2" in r.states
    assert r.attempts == 4


def test_nav_fails_after_retry():
    w = World()
    w.nav_ok = False
    r = run(w)
    assert not r.success
    assert r.reason == "导航到抓取点失败"
    assert r.attempts == 2


def test_not_found_after_all_turns():
    w = World()
    w.look_results = [None] * 10
    r = run(w, mission.MissionConfig(search_turns=3))
    assert not r.success
    assert r.reason == "没找到目标"
    assert r.states[-1] == "look:3"


def test_timeout_stops():
    w = World()
    w.dt_nav = 100.0
    r = run(w, mission.MissionConfig(max_seconds=50))
    assert not r.success
    assert "超时" in r.reason


def test_queue_two_tasks():
    w = World()
    w.cubes = [(200, 0), (200, 100)]
    w.look = lambda: Detection(1, 1, 10, (0, 0, 1, 1)) if w.p in w.cubes else None
    tasks = [((200, 0), (-150, 0)), ((200, 100), (-150, 100))]
    r = mission.run_tasks(w.drive, w.look, w.pick, w.drop, tasks, now=w.now)
    assert r["success"] and r["tasks"] == 2
    assert [x["success"] for x in r["results"]] == [True, True]


def test_queue_stops_on_failure():
    w = World()
    w.nav_ok = False
    tasks = [((200, 0), (-150, 0)), ((200, 100), (-150, 100))]
    r = mission.run_tasks(w.drive, w.look, w.pick, w.drop, tasks, now=w.now)
    assert not r["success"]
    assert r["tasks"] == 1


def test_queue_total_budget():
    w = World()
    tasks = [((200, 0), (-150, 0))]
    r = mission.run_tasks(w.drive, w.look, w.pick, w.drop, tasks,
                          now=w.now, total_seconds=-1)
    assert not r["success"]
    assert r["results"][0]["reason"] == "总预算超时"
