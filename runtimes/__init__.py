from runtimes.base import BaseRuntime
from runtimes.cpp_runtime import CppRuntime
from runtimes.java_runtime import JavaRuntime
from runtimes.python_runtime import PythonRuntime

_RUNTIMES: dict[str, BaseRuntime] = {
    "python": PythonRuntime(),
    "python3": PythonRuntime(),
    "py": PythonRuntime(),
    "cpp": CppRuntime(),
    "c++": CppRuntime(),
    "c": CppRuntime(),
    "java": JavaRuntime(),
}


def get_runtime(language: str) -> BaseRuntime:
    lang = language.lower().strip()
    if lang not in _RUNTIMES:
        raise ValueError(f"Unsupported execution runtime: '{language}'. Supported: python, cpp.")
    return _RUNTIMES[lang]
