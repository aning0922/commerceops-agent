"""Owned V4 QA process groups only; no Docker discovery or implicit environment."""

import os
import signal
import subprocess
import threading
import time
from dataclasses import dataclass, field
from datetime import UTC, datetime
from pathlib import Path
from typing import BinaryIO, Literal

Role = Literal["api", "web", "pg", "probe"]


@dataclass(frozen=True)
class Budget:
    """One absolute Root window converted once to a monotonic ceiling."""

    starts_at: datetime
    deadline: datetime
    reserve: float
    monotonic_deadline: float

    @classmethod
    def bind(cls, start: datetime, end: datetime, reserve: float = 180) -> "Budget":
        if start.utcoffset() != UTC.utcoffset(start) or end.utcoffset() != UTC.utcoffset(end):
            raise ValueError("explicit UTC window required")
        now = datetime.now(UTC)
        if reserve < 180 or not start <= now < end or (end - now).total_seconds() <= reserve:
            raise ValueError("Root work window inactive or cleanup reserve unavailable")
        return cls(start, end, reserve, time.monotonic() + (end - now).total_seconds())

    def remaining(self, *, cleanup: bool = False) -> float:
        wall = (self.deadline - datetime.now(UTC)).total_seconds()
        mono = self.monotonic_deadline - time.monotonic()
        return max(0.0, min(wall, mono) - (0 if cleanup else self.reserve))

    def timeout(self, cap: float, *, cleanup: bool = False) -> float:
        left = min(cap, self.remaining(cleanup=cleanup))
        if left <= 0:
            raise TimeoutError("V4 QA deadline reached; no extension")
        return left


@dataclass
class OwnedProcess:
    role: Role
    process: subprocess.Popen[bytes]
    log: BinaryIO
    native_exit: int | None = None
    stopped: bool = False
    signal_errors: list[tuple[int, int | None]] = field(default_factory=list)


class Supervisor:
    """No shell, inherited secrets, PID adoption, container teardown or retries."""

    def __init__(self, budget: Budget, cwd: Path, evidence: Path) -> None:
        self.budget = budget
        self.cwd = cwd.resolve(strict=True)
        evidence.mkdir(mode=0o700, parents=False, exist_ok=False)
        self.evidence = evidence
        self.owned: list[OwnedProcess] = []
        self._lock = threading.RLock()
        self._timers: list[threading.Timer] = []
        self.watchdog_errors: list[str] = []
        self._closing = False

    def _watchdog(self, final: bool) -> None:
        with self._lock:
            for owned in reversed(self.owned):
                if not final and owned.role == "pg":
                    continue
                try:
                    self.stop(owned)
                except (OSError, TimeoutError, subprocess.TimeoutExpired, RuntimeError):
                    self.watchdog_errors.append(owned.role)

    def _arm(self) -> None:
        if self._timers:
            return
        for delay, final in (
            (self.budget.remaining(), False),
            (max(0, self.budget.remaining(cleanup=True) - 5), True),
        ):
            timer = threading.Timer(delay, self._watchdog, args=(final,))
            timer.daemon = True
            timer.start()
            self._timers.append(timer)

    def start(self, role: Role, argv: tuple[str, ...], env: dict[str, str]) -> OwnedProcess:
        self.budget.timeout(1)
        if self._closing:
            raise ValueError("cleanup has begun; no new process")
        if role not in {"api", "web", "pg", "probe"} or any(p.role == role for p in self.owned):
            raise ValueError("one owned process per V4 role, no automatic restart")
        if not argv or not Path(argv[0]).is_absolute():
            raise ValueError("reviewed absolute executable required")
        log_path = self.evidence / f"{role}.raw.log"
        log = log_path.open("xb")
        os.chmod(log_path, 0o600)
        try:
            process = subprocess.Popen(
                argv,
                cwd=self.cwd,
                env=env,
                stdin=subprocess.DEVNULL,
                stdout=log,
                stderr=subprocess.STDOUT,
                start_new_session=True,
            )
        except BaseException:
            log.close()
            raise
        owned = OwnedProcess(role, process, log)
        self.owned.append(owned)
        self._arm()
        return owned

    def wait(self, owned: OwnedProcess, cap: float) -> int:
        if not any(owned is item for item in self.owned):
            raise ValueError("unowned process refused")
        owned.native_exit = owned.process.wait(timeout=self.budget.timeout(cap))
        return owned.native_exit

    def stop(self, owned: OwnedProcess) -> int:
        with self._lock:
            return self._stop(owned)

    def _no_live_group(self, owned: OwnedProcess) -> bool:
        # Inspect only the group created here; no machine-wide process inventory.
        observed = subprocess.run(
            ["/bin/ps", "-g", str(owned.process.pid), "-o", "stat="],
            capture_output=True,
            text=True,
            env={},
            timeout=self.budget.timeout(1, cleanup=True),
            check=False,
        )
        if observed.returncode == 1 and not observed.stdout.strip() and not observed.stderr.strip():
            return True
        if observed.returncode != 0 or observed.stderr.strip():
            raise RuntimeError("owned process group inspection failed")
        states = observed.stdout.split()
        return bool(states) and all(state.startswith("Z") for state in states)

    def _signal(self, owned: OwnedProcess, sig: signal.Signals) -> None:
        try:
            os.killpg(owned.process.pid, sig)
        except ProcessLookupError:
            pass
        except PermissionError as exc:
            owned.signal_errors.append((int(sig), exc.errno))
            # Preserve the syscall failure. Accept cleanup only with independent
            # evidence that this exact group has no live writer, never by errno alone.
            if not self._no_live_group(owned):
                raise

    def _stop(self, owned: OwnedProcess) -> int:
        if not any(owned is item for item in self.owned):
            raise ValueError("unowned process refused")
        if owned.stopped:
            if owned.native_exit is None:
                raise RuntimeError("previous cleanup incomplete")
            return owned.native_exit
        # The session/process group was created here. Never signal an adopted PID.
        # Kill the group even if its leader exited: descendants may still be writers.
        self._signal(owned, signal.SIGTERM)
        try:
            owned.native_exit = owned.process.wait(timeout=self.budget.timeout(2, cleanup=True))
        except subprocess.TimeoutExpired:
            owned.native_exit = None
        finally:
            try:
                self._signal(owned, signal.SIGKILL)
            finally:
                owned.log.close()
        # Always reap the child, including after TERM is ignored.
        owned.native_exit = owned.process.wait(timeout=self.budget.timeout(2, cleanup=True))
        until = time.monotonic() + self.budget.timeout(1, cleanup=True)
        while not self._no_live_group(owned):
            if time.monotonic() >= until:
                raise RuntimeError("owned descendant group still has live writers")
            time.sleep(0.01)
        owned.stopped = True
        return owned.native_exit

    def stop_writers(self) -> dict[str, int | None]:
        self._closing = True
        result: dict[str, int | None] = {}
        failures: list[str] = []
        for owned in reversed(self.owned):
            if owned.role == "pg":
                continue  # Keep PG alive for final read-only facts.
            try:
                result[owned.role] = self.stop(owned)
            except (OSError, TimeoutError, subprocess.TimeoutExpired, RuntimeError) as exc:
                result[owned.role] = None
                failures.append(
                    f"{owned.role}:{type(exc).__name__}:errno={getattr(exc, 'errno', None)}"
                )
        if failures:
            raise RuntimeError("owned writer cleanup incomplete: " + ",".join(failures))
        return result

    def close_pg(self) -> None:
        for owned in self.owned:
            if owned.role != "pg" and not owned.stopped:
                raise RuntimeError("writer group not cleaned; PG must remain available")
        for owned in self.owned:
            if owned.role == "pg":
                self.stop(owned)
        for timer in self._timers:
            timer.cancel()
