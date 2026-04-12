import shutil
import subprocess
import sys
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[1]


def run(command, check=True):
    print(f"\n>>> {' '.join(command)}")
    result = subprocess.run(command, text=True)
    if check and result.returncode != 0:
        raise SystemExit(result.returncode)
    return result.returncode


def resolve_command(name, extra_candidates=()):
    resolved = shutil.which(name)
    if resolved:
        return resolved

    candidates = list(extra_candidates)
    if sys.platform == "win32":
        user_home = Path.home()
        candidates.extend(
            [
                user_home / "scoop" / "shims" / f"{name}.cmd",
                user_home / "scoop" / "shims" / f"{name}.exe",
                user_home / "scoop" / "shims" / name,
            ]
        )

    for candidate in candidates:
        candidate_path = Path(candidate)
        if candidate_path.exists():
            return str(candidate_path)
    return None


def command_exists(name):
    return resolve_command(name) is not None


def ensure_windows():
    if sys.platform != "win32":
        raise SystemExit("This installer currently supports Windows only.")


def ensure_scoop():
    if not command_exists("scoop"):
        raise SystemExit(
            "Scoop is not installed or not on PATH. Install Scoop first, then rerun this script."
        )


def ensure_bucket(bucket_name):
    scoop_cmd = resolve_command("scoop")
    result = subprocess.run(
        [scoop_cmd, "bucket", "list"],
        capture_output=True,
        text=True,
        check=False,
    )
    if result.returncode != 0:
        raise SystemExit("Failed to query Scoop buckets.")

    if bucket_name.lower() not in result.stdout.lower():
        run([scoop_cmd, "bucket", "add", bucket_name])


def install_if_missing(package_name, commands_to_check):
    scoop_cmd = resolve_command("scoop")
    if all(command_exists(cmd) for cmd in commands_to_check):
        print(f"{package_name}: already available")
        return
    run([scoop_cmd, "install", package_name])


def install_first_available(package_names, commands_to_check):
    if all(command_exists(cmd) for cmd in commands_to_check):
        print(f"{'/'.join(package_names)}: already available")
        return

    last_code = 1
    for package_name in package_names:
        print(f"Trying Java package: {package_name}")
        last_code = run([resolve_command("scoop"), "install", package_name], check=False)
        if last_code == 0 and all(command_exists(cmd) for cmd in commands_to_check):
            return

    raise SystemExit(last_code)


def verify():
    checks = [
        ("python", ["python", "--version"]),
        ("node", ["node", "--version"]),
        ("g++", ["g++", "--version"]),
        ("gcc", ["gcc", "--version"]),
        ("javac", ["javac", "-version"]),
        ("java", ["java", "-version"]),
    ]

    print("\nVerification:")
    for name, command in checks:
        if not command_exists(command[0]):
            print(f"- {name}: missing")
            continue
        print(f"- {name}: found")
        run(command, check=False)


def main():
    print(f"Repository: {REPO_ROOT}")
    ensure_windows()
    ensure_scoop()

    ensure_bucket("java")

    install_if_missing("gcc", ["gcc", "g++"])
    install_first_available(
        ["openjdk", "temurin-jdk", "openjdk17", "temurin17-jdk"],
        ["javac", "java"],
    )

    verify()
    print("\nDone. Open a new terminal or restart the app if newly installed commands are not picked up immediately.")


if __name__ == "__main__":
    main()
