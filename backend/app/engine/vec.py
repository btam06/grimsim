from __future__ import annotations

import multiprocessing as mp
import multiprocessing.connection

# Several GameEnvs (see app/engine/env.py) at once, each in a process of its
# own - games are CPU-bound, so that's how they run in parallel:
#
#     envs = VecEnv(4, saves="saves/1/r1-s2-start_of_round.json", seat=1, seed=0)
#     obs, infos = envs.reset()
#     obs, rewards, terminated, truncated, infos = envs.step([index, ...])
#     envs.close()
#
# Lists, one entry per env. An env whose episode ends is reset straight
# away (Gymnasium's "next step" autoreset aside): its observation and info
# are the new episode's first - with the last episode's final ones in
# infos[i]["final_obs"] and infos[i]["final_info"].
# Env i is seeded `seed + i`. Each process takes a few hundred MB.
#
# step() waits for every env - so runs at the slowest one's pace (decisions
# take from milliseconds to seconds). To keep each process busy, step envs
# one at a time and take whichever are done:
#
#     for i, info in enumerate(infos):
#         envs.send(i, index_for(i))
#     while training:
#         for i, (obs, reward, terminated, truncated, info) in envs.poll():
#             envs.send(i, index_for(i))
#
# The processes are started fresh ("spawn"), each importing the script that
# made them: a script making a VecEnv needs `if __name__ == "__main__":`.


def _work(conn, kwargs: dict) -> None:
    from app.engine.env import GameEnv

    env = GameEnv(**kwargs)
    try:
        while True:
            command, arg = conn.recv()
            if command == "reset":
                conn.send(env.reset(seed=arg))
            elif command == "step":
                obs, reward, terminated, truncated, info = env.step(arg)
                if terminated or truncated:
                    final_obs, final_info = obs, info
                    obs, info = env.reset()
                    info["final_obs"], info["final_info"] = final_obs, final_info
                conn.send((obs, reward, terminated, truncated, info))
            elif command == "close":
                break
    finally:
        env.close()
        conn.close()


class VecEnv:
    def __init__(self, n: int, seed: int | None = None, **env_kwargs) -> None:
        # `env_kwargs`: GameEnv's (an opponent must be picklable - a function
        # defined at module level).
        ctx = mp.get_context("spawn")
        self.conns = []
        self.processes = []
        # The envs sent an action that haven't answered yet.
        self.pending: set[int] = set()
        for i in range(n):
            here, there = ctx.Pipe()
            kwargs = {**env_kwargs, "seed": None if seed is None else seed + i}
            process = ctx.Process(target=_work, args=(there, kwargs), daemon=True)
            process.start()
            there.close()
            self.conns.append(here)
            self.processes.append(process)

    def __len__(self) -> int:
        return len(self.conns)

    def reset(self, seed: int | None = None) -> tuple[list, list]:
        for i, conn in enumerate(self.conns):
            conn.send(("reset", None if seed is None else seed + i))
        results = [conn.recv() for conn in self.conns]
        return [r[0] for r in results], [r[1] for r in results]

    def step(self, indexes: list[int]) -> tuple[list, list, list, list, list]:
        for i, index in enumerate(indexes):
            self.send(i, index)
        results = [conn.recv() for conn in self.conns]
        self.pending.clear()
        return tuple([r[i] for r in results] for i in range(5))  # type: ignore[return-value]

    def send(self, i: int, index: int) -> None:
        # Env i takes action `index` (its result comes from poll).
        if i in self.pending:
            raise RuntimeError(f"env {i} is still taking its last action")
        self.conns[i].send(("step", index))
        self.pending.add(i)

    def poll(self, timeout: float | None = None) -> list[tuple[int, tuple]]:
        # The envs that have taken their actions since: (i, step's result)
        # each - waiting until one has (or `timeout` seconds pass).
        waiting = {self.conns[i]: i for i in self.pending}
        done = []
        for conn in mp.connection.wait(list(waiting), timeout):
            i = waiting[conn]
            self.pending.discard(i)
            done.append((i, conn.recv()))
        return done

    def close(self) -> None:
        for conn in self.conns:
            try:
                conn.send(("close", None))
            except (BrokenPipeError, OSError):
                pass
        for process in self.processes:
            process.join(timeout=10)
            if process.is_alive():
                process.terminate()
