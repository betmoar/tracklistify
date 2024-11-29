"""
Command execution framework for development tools.
"""

import asyncio
import signal
import shlex
from dataclasses import dataclass
from enum import Enum
from typing import List, Dict, Optional, Any, Callable, Union
from pathlib import Path
import subprocess
import threading
import queue
import time

from ..logging import DevCliLogger
from ..exceptions import ToolExecutionError


class ExecutionStatus(Enum):
    """Status of command execution."""

    PENDING = "pending"
    RUNNING = "running"
    COMPLETED = "completed"
    FAILED = "failed"
    CANCELLED = "cancelled"


@dataclass
class ExecutionResult:
    """Result of command execution."""

    status: ExecutionStatus
    exit_code: Optional[int] = None
    stdout: str = ""
    stderr: str = ""
    start_time: Optional[float] = None
    end_time: Optional[float] = None
    error: Optional[Exception] = None

    @property
    def duration(self) -> Optional[float]:
        """Get execution duration in seconds."""
        if self.start_time and self.end_time:
            return self.end_time - self.start_time
        return None

    def to_dict(self) -> Dict[str, Any]:
        """Convert result to dictionary."""
        return {
            "status": self.status.value,
            "exit_code": self.exit_code,
            "stdout": self.stdout,
            "stderr": self.stderr,
            "start_time": self.start_time,
            "end_time": self.end_time,
            "duration": self.duration,
            "error": str(self.error) if self.error else None,
        }


class CommandExecutor:
    """Executes shell commands with proper process management."""

    def __init__(self, working_dir: Optional[Path] = None):
        self.working_dir = working_dir or Path.cwd()
        self.logger = DevCliLogger().get_context_logger(
            executor_class=self.__class__.__name__
        )
        self._active_processes: Dict[int, subprocess.Popen] = {}
        self._output_queues: Dict[int, queue.Queue] = {}
        self._stop_events: Dict[int, threading.Event] = {}

    def _setup_signal_handlers(self):
        """Set up signal handlers for graceful shutdown."""

        def signal_handler(signum, frame):
            self.logger.warning(f"Received signal {signum}, cleaning up...")
            self.cleanup()

        signal.signal(signal.SIGINT, signal_handler)
        signal.signal(signal.SIGTERM, signal_handler)

    def cleanup(self):
        """Clean up all running processes."""
        for process in self._active_processes.values():
            try:
                process.terminate()
                process.wait(timeout=5)
            except subprocess.TimeoutExpired:
                process.kill()
            except Exception as e:
                self.logger.error(f"Error cleaning up process {process.pid}: {e}")

    def _output_reader(
        self, pipe: Any, queue: queue.Queue, stop_event: threading.Event
    ):
        """Read output from a pipe and put it in a queue."""
        try:
            while not stop_event.is_set():
                line = pipe.readline()
                if not line:
                    break
                queue.put(line.decode().rstrip())
        except Exception as e:
            self.logger.error(f"Error reading output: {e}")
        finally:
            pipe.close()

    async def execute_command(
        self,
        command: Union[str, List[str]],
        env: Optional[Dict[str, str]] = None,
        timeout: Optional[float] = None,
        output_callback: Optional[Callable[[str], None]] = None,
    ) -> ExecutionResult:
        """Execute a command asynchronously."""
        if isinstance(command, str):
            command = shlex.split(command)

        result = ExecutionResult(status=ExecutionStatus.PENDING)
        result.start_time = time.time()

        try:
            # Start process
            process = await asyncio.create_subprocess_exec(
                *command,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                env=env,
                cwd=self.working_dir,
            )

            self._active_processes[process.pid] = process
            output_queue = queue.Queue()
            stop_event = threading.Event()
            self._output_queues[process.pid] = output_queue
            self._stop_events[process.pid] = stop_event

            # Start output readers
            stdout_thread = threading.Thread(
                target=self._output_reader,
                args=(process.stdout, output_queue, stop_event),
            )
            stderr_thread = threading.Thread(
                target=self._output_reader,
                args=(process.stderr, output_queue, stop_event),
            )
            stdout_thread.start()
            stderr_thread.start()

            result.status = ExecutionStatus.RUNNING
            self.logger.info(f"Started process {process.pid}: {' '.join(command)}")

            # Process output
            try:
                while True:
                    try:
                        line = output_queue.get_nowait()
                        if output_callback:
                            output_callback(line)
                        result.stdout += line + "\n"
                    except queue.Empty:
                        if process.returncode is not None:
                            break
                        await asyncio.sleep(0.1)

                exit_code = await process.wait()
                result.exit_code = exit_code
                result.status = (
                    ExecutionStatus.COMPLETED
                    if exit_code == 0
                    else ExecutionStatus.FAILED
                )

            except asyncio.TimeoutError:
                process.terminate()
                result.status = ExecutionStatus.CANCELLED
                raise TimeoutError(
                    f"Command timed out after {timeout} seconds"
                ) from None

            finally:
                stop_event.set()
                stdout_thread.join()
                stderr_thread.join()

        except Exception as e:
            result.status = ExecutionStatus.FAILED
            result.error = e
            self.logger.error(f"Command execution failed: {e}")
            raise ToolExecutionError(
                "command", " ".join(command), result.exit_code or -1, str(e)
            ) from e

        finally:
            result.end_time = time.time()
            if process.pid in self._active_processes:
                del self._active_processes[process.pid]
                del self._output_queues[process.pid]
                del self._stop_events[process.pid]

        return result


class CommandPipeline:
    """Execute multiple commands in a pipeline."""

    def __init__(self):
        self.executor = CommandExecutor()
        self.logger = DevCliLogger().get_context_logger(
            pipeline_class=self.__class__.__name__
        )
        self.commands: List[Dict[str, Any]] = []

    def add_command(
        self,
        command: Union[str, List[str]],
        env: Optional[Dict[str, str]] = None,
        timeout: Optional[float] = None,
        output_callback: Optional[Callable[[str], None]] = None,
    ) -> "CommandPipeline":
        """Add a command to the pipeline."""
        self.commands.append(
            {
                "command": command,
                "env": env,
                "timeout": timeout,
                "output_callback": output_callback,
            }
        )
        return self

    async def execute(self) -> List[ExecutionResult]:
        """Execute all commands in the pipeline."""
        results = []

        for cmd_config in self.commands:
            try:
                result = await self.executor.execute_command(**cmd_config)
                results.append(result)

                # If a command fails, stop the pipeline
                if result.status != ExecutionStatus.COMPLETED:
                    self.logger.error(
                        f"Pipeline failed at command: {cmd_config['command']}"
                    )
                    break

            except Exception as e:
                self.logger.error(f"Pipeline execution failed: {e}")
                raise

        return results
