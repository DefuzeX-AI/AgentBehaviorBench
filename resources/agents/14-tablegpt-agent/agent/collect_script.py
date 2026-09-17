import platform
import subprocess
import sys


def get_os_info():
    return {
        "system": platform.system(),
        "node": platform.node(),
        "release": platform.release(),
        "version": platform.version(),
        "machine": platform.machine(),
        "processor": platform.processor(),
    }


def get_python_info():
    return {
        "implementation": platform.python_implementation(),
        "version": platform.python_version(),
        "compiler": platform.python_compiler(),
    }


def get_pip_list():
    result = subprocess.run(
        [sys.executable, "-m", "pip", "list"],
        capture_output=True,
        text=True,
        check=False,
    )
    if result.returncode == 0:
        return result.stdout

    return f"Failed to get pip list: {result.stderr}"


def write_to_log_file(content, filename="env_output.log"):
    with open(filename, "w") as file:
        file.write(content)


def main():
    os_info = get_os_info()
    python_info = get_python_info()
    pip_list = get_pip_list()

    content = "Operating System Information:\n"
    for key, value in os_info.items():
        content += f"{key}: {value}\n"

    content += "\nPython Information:\n"
    for key, value in python_info.items():
        content += f"{key}: {value}\n"

    content += "\nPip List:\n"
    content += pip_list

    # stdout
    print(content)  # noqa: T201

    # file
    write_to_log_file(content)


if __name__ == "__main__":
    main()
