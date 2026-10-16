"""Version string helpers."""
import os
import subprocess


def get_version():
    """Return version string. Appends git branch when running from a repo checkout."""
    from documix import __version__
    package_dir = os.path.dirname(os.path.abspath(__file__))
    if not os.path.isdir(os.path.join(os.path.dirname(package_dir), '.git')):
        return __version__  # installed package: no git checkout to inspect
    try:
        result = subprocess.run(
            ['git', 'rev-parse', '--abbrev-ref', 'HEAD'],
            capture_output=True, text=True, timeout=5,
            cwd=package_dir
        )
        if result.returncode == 0:
            branch = result.stdout.strip()
            if branch and branch != 'HEAD':
                return f"{__version__}-dev ({branch})"
    except (FileNotFoundError, subprocess.SubprocessError):
        pass
    return __version__
