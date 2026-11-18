"""The runner's process: commands on stdin, events on stdout (runner/protocol.py), one start or one scan, then it ends.

Exit code 0 when the command succeeded, 1 when it did not, 2 when the first command broke the protocol.
"""
from __future__ import annotations

import os
import sys
import threading

from runner import protocol
from runner.session import Commands, Out, Session, pump, read_lines


def serve(out: Out, lines, framework, **session) -> int:
    """Run the first command of lines; a stop comes from the lines that follow it."""
    out.send("ready", pid=os.getpid())
    commands = Commands(lines)
    first = commands.get()
    problem = ("stdin ended before a command" if first == Commands.EOF else str(first)
               if isinstance(first, protocol.ProtocolError) else "stop: no run to stop" if first["cmd"] == "stop" else None)
    if problem:
        out.send("error", kind="protocol", message=problem)
        out.settle()
        out.send("end", result="failed")
        return 2
    s = Session(out, framework, commands, **session)
    result = s.scan() if first["cmd"] == "scan" else s.start(first)
    return 0 if result == "succeeded" else 1


def take_stdin() -> int:
    """The fd the protocol's commands come on: stdin's pipe moved off fd 0, which then reads NUL (and so does the
    process's standard input handle). On Windows the C runtime's fstat and lseek of a pipe's fd wait for a read pending
    on it: behind the runtime's lock on the fd and, were it read with a plain ReadFile, behind the kernel's on a
    synchronous pipe. numpy's OpenBLAS, which `import maa` loads, carries libgfortran, which looks at fd 0 as it loads,
    so the import waited for the next command (#829). The new fd is not inheritable (os.dup)."""
    fd = os.dup(0)
    nul = os.open(os.devnull, os.O_RDONLY)
    os.dup2(nul, 0)
    os.close(nul)
    return fd


def take_stdout():
    """(the protocol's stream, the read end of the console pipe). The protocol keeps its own handle on stdout; fds 1 and
    2 then go to a pipe, so whatever else this process prints, MaaFramework's native code and its controller included
    (the `x: ..., width: ...` lines of a tap), comes back as console lines, never into the protocol. The protocol's
    handle is not inheritable (os.dup): no child holds stdout open after the runner ends (#663)."""
    proto = os.fdopen(os.dup(1), "w", encoding="utf-8", newline="\n")
    read, write = os.pipe()
    os.dup2(write, 1)
    os.dup2(write, 2)
    os.close(write)
    sys.stdout = open(1, "w", encoding="utf-8", errors="replace", buffering=1, closefd=False)
    sys.stderr = open(2, "w", encoding="utf-8", errors="replace", buffering=1, closefd=False)
    return proto, read


class Console:
    """The console pipe's lines as console log lines. settle() writes a mark into the pipe and waits (up to SETTLE s)
    until the reader has passed it: every line printed before it is then out, the run log's last taps included."""
    MARK = "\x00runner-settle"
    SETTLE = 1.0

    def __init__(self, fd: int, out: Out):
        self.out, self.passed = out, threading.Event()
        threading.Thread(target=pump, args=(fd, self.line), daemon=True).start()

    def line(self, text: str) -> None:
        if text == self.MARK:
            self.passed.set()
        elif text:  # the newline settle() puts before its mark ends a line left open; an empty one is no line
            self.out.log("console", text)

    def settle(self) -> None:
        self.passed.clear()
        sys.stdout.flush()
        sys.stderr.flush()
        os.write(1, f"\n{self.MARK}\n".encode())
        self.passed.wait(self.SETTLE)


def main(framework=None) -> int:
    command_fd = take_stdin()
    proto, console = take_stdout()

    def write(text: str) -> None:
        proto.write(text + "\n")
        proto.flush()

    out = Out(write)
    out.before_end = Console(console, out).settle
    if framework is None:
        from runner.framework import Framework as framework
    try:
        return serve(out, read_lines(command_fd), framework)
    finally:
        sys.stdout.flush()
        sys.stderr.flush()
