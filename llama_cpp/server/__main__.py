"""Example FastAPI server for llama.cpp.

To run this example:

```bash
pip install fastapi uvicorn sse-starlette pydantic-settings
export MODEL=../models/7B/...
```

Then run:
```
uvicorn llama_cpp.server.app:app --reload
```

or

```
python3 -m llama_cpp.server
```

Then visit http://localhost:8000/docs to see the interactive API docs.

"""
import os
import argparse
import inspect
from typing import List, Literal, Union

import uvicorn

from llama_cpp.server.app import create_app, Settings

def get_base_type(annotation):
    if getattr(annotation, '__origin__', None) is Literal:
        return type(annotation.__args__[0])
    elif getattr(annotation, '__origin__', None) is Union:
        non_optional_args = [arg for arg in annotation.__args__ if arg is not type(None)]
        if non_optional_args:
            return get_base_type(non_optional_args[0])
    elif getattr(annotation, '__origin__', None) is list or getattr(annotation, '__origin__', None) is List:
        return get_base_type(annotation.__args__[0])
    else:
        return annotation

def contains_list_type(annotation) -> bool:
    origin = getattr(annotation, '__origin__', None)
    
    if origin is list or origin is List:
        return True
    elif origin in (Literal, Union):
        return any(contains_list_type(arg) for arg in annotation.__args__)
    else:
        return False

def parse_bool_arg(arg):
    if isinstance(arg, bytes):
        arg = arg.decode('utf-8')

    true_values = {'1', 'on', 't', 'true', 'y', 'yes'}
    false_values = {'0', 'off', 'f', 'false', 'n', 'no'}

    arg_str = str(arg).lower().strip()
    
    if arg_str in true_values:
        return True
    elif arg_str in false_values:
        return False
    else:
        raise ValueError(f'Invalid boolean argument: {arg}')

if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    for name, field in Settings.model_fields.items():
        description = field.description
        if field.default is not None and description is not None:
            description += f" (default: {field.default})"
        base_type = get_base_type(field.annotation) if field.annotation is not None else str
        list_type = contains_list_type(field.annotation)
        if base_type is not bool:
            parser.add_argument(
                f"--{name}",
                dest=name,
                nargs="*" if list_type else None,
                type=base_type,
                help=description,
            )
        if base_type is bool:
            parser.add_argument(
                f"--{name}",
                dest=name,
                type=parse_bool_arg,
                help=f"{description}",
            )

    # Extract uvicorn.run function arguments to dynamically add them to argparse
    uvicorn_run_signature = inspect.signature(uvicorn.run)
    for param_name, param in uvicorn_run_signature.parameters.items():
        # Skip the "app" argument since it will be provided internally
        if param_name == "app":
            continue

        # Handle special types and defaults
        param_type = param.annotation if param.annotation != inspect.Parameter.empty else str
        param_default = param.default if param.default != inspect.Parameter.empty else None

        # Add argument to argparse
        parser.add_argument(
            f"--uvicorn-{param_name}",
            type=param_type,
            default=param_default,
            help=f"Uvicorn setting for {param_name} (default: {repr(param_default).replace('%', '%%')})"
        )

    args = parser.parse_args()
    settings = Settings(**{k: v for k, v in vars(args).items() if v is not None and not k.startswith("uvicorn_")})
    app = create_app(settings=settings)

    # Separate out uvicorn arguments
    uvicorn_args = {k[8:]: v for k, v in vars(args).items() if k.startswith("uvicorn_") and v is not None}

    # Merge with other environment-based settings if needed
    uvicorn_args['host'] = os.getenv("HOST", uvicorn_args.get('host', "127.0.0.1"))
    uvicorn_args['port'] = int(os.getenv("PORT", uvicorn_args.get('port', 8000)))

    uvicorn.run(app, **uvicorn_args)
