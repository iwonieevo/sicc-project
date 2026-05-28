import re
from typing import Any, Dict, List


def sanitize_parameter(value: Any, param_type: str) -> Any:
    """
    Sanitize a parameter value based on its expected type.
    
    Args:
        value: Raw input value
        param_type: Expected type ('text' or 'integer')
    
    Returns:
        Sanitized value appropriate for the type
    """
    if value is None:
        return None
    
    if param_type == "integer":
        try:
            if isinstance(value, str):
                value = value.strip()
            return int(value)
        except (ValueError, TypeError):
            raise ValueError(f"Invalid integer value: {value}")
    
    if param_type == "text":
        if not isinstance(value, str):
            value = str(value)
        value = re.sub(r'[\x00-\x08\x0b\x0c\x0e-\x1f\x7f]', '', value)
        return value
    
    return str(value)


def sanitize_parameters(params: Dict[str, Any], param_definitions: List[Dict]) -> Dict[str, Any]:
    """
    Apply sanitization to all parameters based on their definitions.
    Builds complete parameter dict with defaults, then overrides with provided values.
    
    Args:
        params: Dictionary of parameter name to value (user input)
        param_definitions: List of parameter definition dicts with 'name', 'param_type', 
        'is_required', and 'default_value'
    
    Returns:
        Sanitized parameter dictionary with all parameters (defaults + overrides)
    """
    sanitized = {}
    
    for p in param_definitions:
        name = p["name"]
        param_type = p["param_type"]
        default_value = p.get("default_value")
        
        if name in params and params[name] is not None:
            value = params[name]
        elif default_value is not None:
            value = default_value
        else:
            value = None
        
        try:
            sanitized[name] = sanitize_parameter(value, param_type)
        except ValueError as e:
            raise ValueError(f"Parameter '{name}': {str(e)}")
    
    return sanitized