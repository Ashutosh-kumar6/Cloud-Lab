from dataclasses import dataclass

import docker
from docker.types import LogConfig

SANDBOX_IMAGE = "cloudlab-python-sandbox"
TIME_LIMIT_SECONDS = 5
HARD_WAIT_SECONDS = 20
MAX_OUTPUT_CHARS = 10_000
WORK_DIR = "/work"

RUN_SCRIPT = (
    'printf "%s" "$CODE" > /work/main.py && '
    'printf "%s" "$INPUT_TEXT" > /work/input.txt && '
    "unset CODE INPUT_TEXT && "
    f"timeout {TIME_LIMIT_SECONDS} python /work/main.py < /work/input.txt"
)


@dataclass
class RunResult:
    stdout: str
    stderr: str
    exit_code: int | None
    timed_out: bool


def run_python(code: str, input_text: str) -> RunResult:
    client = docker.from_env()
    container = None
    try:
        container = client.containers.create(
            SANDBOX_IMAGE,
            command=["sh", "-c", RUN_SCRIPT],
            working_dir=WORK_DIR,
            user="1000:1000",
            network_disabled=True,
            mem_limit="128m",
            memswap_limit="128m",
            nano_cpus=500_000_000,
            pids_limit=64,
            read_only=True,
            tmpfs={
                WORK_DIR: "size=16m,uid=1000,gid=1000,mode=0755",
                "/tmp": "size=16m,noexec",
            },
            cap_drop=["ALL"],
            security_opt=["no-new-privileges"],
            environment={
                "PYTHONDONTWRITEBYTECODE": "1",
                "CODE": code,
                "INPUT_TEXT": input_text,
            },
            log_config=LogConfig(
                type=LogConfig.types.JSON, config={"max-size": "200k", "max-file": "1"}
            ),
        )
        container.start()

        exit_code = None
        killed = False
        try:
            exit_code = container.wait(timeout=HARD_WAIT_SECONDS).get("StatusCode")
        except Exception:
            killed = True
            try:
                container.kill()
            except Exception:
                pass

        timed_out = killed or exit_code == 124
        stdout = container.logs(stdout=True, stderr=False).decode("utf-8", errors="replace")
        stderr = container.logs(stdout=False, stderr=True).decode("utf-8", errors="replace")
        return RunResult(
            stdout=stdout[:MAX_OUTPUT_CHARS],
            stderr=stderr[:MAX_OUTPUT_CHARS],
            exit_code=exit_code,
            timed_out=timed_out,
        )
    finally:
        if container is not None:
            try:
                container.remove(force=True)
            except Exception:
                pass
