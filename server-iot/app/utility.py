from typing import List


def build_function(python_code: str, param_names: List[str]) -> str:
    """
    Build a complete function definition from python_code and parameter names.
    
    The python_code contains only the function body (not the def line).
    This constructs a complete, callable function by wrapping it.
    """
    params = ", ".join(param_names)
    function_def = f"def _sicc_command({params}):\n"
    indented_code = "\n".join(f"\t{line}" for line in python_code.splitlines())
    
    return function_def + indented_code + "\n"

