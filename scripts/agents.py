import argparse
import hashlib
import hmac
import json
import os
import secrets
import subprocess
import sys
from pathlib import Path
from time import time

REPO_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO_ROOT))
sys.path.insert(0, str(REPO_ROOT / "server-iot"))

from security import generate_ed25519_keypair, public_key_id  # noqa: E402
from security.encoding import b64encode  # noqa: E402

COMPOSE_FILE = "docker-compose.agents.yml"
COMPOSE_PROJECT = "agents"
ENROLLMENT_TTL_SECONDS = 120


def load_dotenv(path=".env") -> dict:
    env = {}
    try:
        with open(path) as f:
            for line in f:
                line = line.strip()
                if line and not line.startswith("#") and "=" in line:
                    key, _, val = line.partition("=")
                    env[key.strip()] = val.strip().strip('"').strip("'")
    except FileNotFoundError:
        pass
    return env


def get_agent_label() -> str:
    label = load_dotenv().get("AGENT_LABEL", "sicc.role=agent")
    return label.removeprefix("label=")


def run_cmd(cmd: list[str], env_extra: dict | None = None) -> int:
    env = os.environ.copy()
    if env_extra:
        env.update(env_extra)
    return subprocess.run(cmd, env=env).returncode


def looks_like_env_path(value: str) -> bool:
    path = Path(value)
    return (
        "/" in value
        or "\\" in value
        or value.endswith(".env")
        or value.startswith(".env")
        or path.exists()
    )


def parse_start_specs(items: list[str]) -> list[tuple[str, str | None]]:
    specs = []
    index = 0
    while index < len(items):
        name = items[index]
        if looks_like_env_path(name):
            raise SystemExit(f"Expected agent name, got env path: {name}")

        env_path = None
        next_index = index + 1
        if next_index < len(items) and looks_like_env_path(items[next_index]):
            env_path = items[next_index]
            index += 2
        else:
            index += 1

        specs.append((name, env_path))
    return specs


def load_agent_env_file(path: str | None) -> dict:
    env = load_dotenv("env/.env.agent")
    if path is None:
        return env

    resolved = Path(path)
    if not resolved.is_file():
        raise SystemExit(f"Agent env file not found: {path}")
    env.update(load_dotenv(str(resolved)))
    return env


def parse_bool(value: str) -> bool:
    normalized = value.strip().lower()
    if normalized in {"1", "true", "yes", "on"}:
        return True
    if normalized in {"0", "false", "no", "off", ""}:
        return False
    raise SystemExit(f"Invalid SECURE_MODE value: {value}")


def load_enrollment_secret() -> str:
    secret = os.environ.get("SICC_AGENT_ENROLLMENT_SECRET") or load_dotenv(
        "env/.env.server-iot"
    ).get("SICC_AGENT_ENROLLMENT_SECRET")
    if not secret:
        raise SystemExit(
            "SICC_AGENT_ENROLLMENT_SECRET is required in the environment or env/.env.server-iot"
        )
    return secret


def create_enrollment_token(
    secret: str,
    agent_name: str,
    ttl_seconds: int = ENROLLMENT_TTL_SECONDS,
) -> str:
    issued_at = int(time())
    expires_at = issued_at + ttl_seconds
    if expires_at <= issued_at:
        raise ValueError("time is broken")

    payload = {
        "v": 1,
        "iss": "agents.py",
        "agent_id": agent_name,
        "jti": secrets.token_urlsafe(32),
        "iat": issued_at,
        "exp": expires_at,
    }

    payload_bytes = json.dumps(payload, sort_keys=True, separators=(",", ":")).encode(
        "utf-8"
    )
    payload_part = b64encode(payload_bytes)
    signature = hmac.new(
        secret.encode("utf-8"), payload_part.encode("ascii"), hashlib.sha256
    ).digest()
    return f"{payload_part}.{b64encode(signature)}"


def build_generated_agent_env(
    agent_name: str,
) -> dict[str, str]:
    keypair = generate_ed25519_keypair()
    token = create_enrollment_token(
        load_enrollment_secret(),
        agent_name,
        ttl_seconds=ENROLLMENT_TTL_SECONDS,
    )
    return {
        "AGENT_ENROLLMENT_TOKEN": token,
        "AGENT_NAME": agent_name,
        "SICC_SERVICE_IDENTITY": agent_name,
        "SICC_SERVICE_KEY_ID": public_key_id(keypair.public_key),
        "SICC_SERVICE_PRIVATE_KEY_B64": b64encode(keypair.private_key),
        "SICC_SERVICE_PUBLIC_KEY_B64": b64encode(keypair.public_key),
    }


def prepare_agent_env(agent_name: str, env_path: str | None) -> dict[str, str]:
    agent_env = load_agent_env_file(env_path)
    agent_env["AGENT_NAME"] = agent_name

    if parse_bool(load_dotenv().get("SECURE_MODE", "false")):
        generated_env = build_generated_agent_env(agent_name)
        agent_env.update(generated_env)

    return agent_env


def get_agent_names(running_only=False) -> list[str]:
    cmd = [
        "docker",
        "ps",
        "--filter",
        f"label={get_agent_label()}",
        "--format",
        "{{.Names}}",
    ]
    if not running_only:
        cmd.insert(2, "-a")
    result = subprocess.run(cmd, capture_output=True, text=True)
    return [line.strip() for line in result.stdout.splitlines() if line.strip()]


# commands


def cmd_start(args):
    for name, env_path in parse_start_specs(args.items):
        existing = subprocess.run(
            ["docker", "ps", "-a", "-q", "--filter", f"name=^/{name}$"],
            capture_output=True,
            text=True,
        ).stdout.strip()

        if existing:
            if env_path:
                print(
                    f"Env file ignored for existing container {name}; remove it first to change env.",
                    file=sys.stderr,
                )
            print(f"Resuming: {name}")
            code = run_cmd(["docker", "start", name])
        else:
            print(f"Starting: {name}" + (f" ({env_path})" if env_path else ""))
            agent_env = prepare_agent_env(name, env_path)
            code = run_cmd(
                [
                    "docker",
                    "compose",
                    "-f",
                    COMPOSE_FILE,
                    "-p",
                    COMPOSE_PROJECT,
                    "run",
                    "-d",
                    "--name",
                    name,
                    "agent",
                ],
                env_extra=agent_env,
            )

        if code != 0:
            print(f"Failed to start {name}", file=sys.stderr)
            sys.exit(code)
        print(f"Started: {name}")


def cmd_stop(args):
    names = get_agent_names(running_only=True) if args.all else args.names
    if not names:
        print(
            "No running agents found."
            if args.all
            else "Specify at least one agent name."
        )
        return
    for name in names:
        print(f"Stopping: {name}")
        code = run_cmd(["docker", "stop", name])
        if code != 0:
            print(f"Failed to stop {name}", file=sys.stderr)


def cmd_down(args):
    names = get_agent_names() if args.all else args.names
    if not names:
        print("No agents found." if args.all else "Specify at least one agent name.")
        return
    for name in names:
        print(f"Removing: {name}")
        code = run_cmd(["docker", "rm", "-f", name])
        if code != 0:
            print(f"Failed to remove {name}", file=sys.stderr)


def cmd_logs(args):
    cmd = ["docker", "logs", "--tail", str(args.tail)]
    if args.follow:
        cmd.append("-f")
    cmd.append(args.name)
    process = subprocess.Popen(cmd)
    try:
        process.wait()
    except KeyboardInterrupt:
        process.terminate()
        process.wait()


def cmd_list(args):
    label = get_agent_label()
    print("Running agents:")
    run_cmd(
        [
            "docker",
            "ps",
            "--filter",
            f"label={label}",
            "--format",
            "table {{.Names}}\t{{.Status}}\t{{.ID}}",
        ]
    )

    print("\nStopped agents:")
    run_cmd(
        [
            "docker",
            "ps",
            "-a",
            "--filter",
            f"label={label}",
            "--filter",
            "status=exited",
            "--format",
            "table {{.Names}}\t{{.Status}}\t{{.ID}}",
        ]
    )


# CLI


def main():
    parser = argparse.ArgumentParser(prog="agents", description="Manage SICC agents")
    sub = parser.add_subparsers(dest="command", required=True)

    p = sub.add_parser("start", help="Start one or more agents")
    p.add_argument(
        "items",
        nargs="+",
        metavar="name [env_file]",
        help="Agent names, optionally followed by per-agent env file paths",
    )
    p.set_defaults(func=cmd_start)

    p = sub.add_parser("stop", help="Stop one or more agents (container kept)")
    p.add_argument("names", nargs="*", metavar="name")
    p.add_argument("--all", action="store_true", help="Stop all agents")
    p.set_defaults(func=cmd_stop)

    p = sub.add_parser("down", help="Stop and remove one or more agents")
    p.add_argument("names", nargs="*", metavar="name")
    p.add_argument("--all", action="store_true", help="Down all agents")
    p.set_defaults(func=cmd_down)

    p = sub.add_parser("logs", help="Get logs for an agent")
    p.add_argument("name", metavar="name")
    p.add_argument("-f", "--follow", action="store_true", help="Follow log output")
    p.add_argument("--tail", type=int, default=50, metavar="N")
    p.set_defaults(func=cmd_logs)

    p = sub.add_parser("list", help="List running and stopped agents")
    p.set_defaults(func=cmd_list)

    args = parser.parse_args()

    args.func(args)


if __name__ == "__main__":
    main()
