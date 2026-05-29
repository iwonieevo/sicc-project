import argparse
import os
import subprocess
import sys

COMPOSE_FILE = "docker-compose.agents.yml"
COMPOSE_PROJECT = "agents"


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


def run_cmd(cmd: list[str], env_extra: dict|None = None) -> int:
    env = os.environ.copy()
    if env_extra:
        env.update(env_extra)
    return subprocess.run(cmd, env=env).returncode


def get_agent_names(running_only=False) -> list[str]:
    cmd = ["docker", "ps", "--filter", f"label={get_agent_label()}",
           "--format", "{{.Names}}"]
    if not running_only:
        cmd.insert(2, "-a")
    result = subprocess.run(cmd, capture_output=True, text=True)
    return [line.strip() for line in result.stdout.splitlines() if line.strip()]


# commands

def cmd_start(args):
    for name in args.names:
        print(f"Starting: {name}")
        code = run_cmd(
            ["docker", "compose", "-f", COMPOSE_FILE, "-p", COMPOSE_PROJECT,
             "run", "-d", "--name", name, "agent"],
            env_extra={"AGENT_NAME": name}
        )
        if code != 0:
            print(f"Failed to start {name}", file=sys.stderr)
            sys.exit(code)
        print(f"Started: {name}")


def cmd_stop(args):
    names = get_agent_names(running_only=True) if args.all else args.names
    if not names:
        print("No running agents found." if args.all else "Specify at least one agent name.")
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
    run_cmd(["docker", "ps",
             "--filter", f"label={label}",
             "--format", "table {{.Names}}\t{{.Status}}\t{{.ID}}"])

    print("\nStopped agents:")
    run_cmd(["docker", "ps", "-a",
             "--filter", f"label={label}",
             "--filter", "status=exited",
             "--format", "table {{.Names}}\t{{.Status}}\t{{.ID}}"])


# CLI

def main():
    parser = argparse.ArgumentParser(prog="agents", description="Manage SICC agents")
    sub = parser.add_subparsers(dest="command", required=True)

    p = sub.add_parser("start", help="Start one or more agents")
    p.add_argument("names", nargs="+", metavar="name")
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