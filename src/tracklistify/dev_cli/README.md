# Tracklistify Development CLI

This repository contains a command-line interface (CLI) for development tools used in the Tracklistify project. The CLI provides various commands to streamline development tasks such as linting, formatting, type checking, and running tests.

## Table of Contents

- [Installation](#installation)
- [Usage](#usage)
- [Configuration](#configuration)
- [Commands](#commands)
    - [ListCommand](#listcommand)
    - [RunCommand](#runcommand)
- [Development](#development)
- [License](#license)
- [Features](#features)
- [Error Handling](#error-handling)
- [Logging](#logging)
- [Adding New Commands](#adding-new-commands)
- [Testing](#testing)
- [Contributing](#contributing)
- [Debugging Commands](#debugging-commands)

## Installation

To install the development CLI, clone the repository and install the required dependencies:

```sh
git clone https://github.com/yourusername/tracklistify.git
cd tracklistify
pip install -r requirements.txt
```

## Usage

To use the CLI, navigate to the `tracklistify/dev_cli` directory and run the CLI commands:

```sh
cd tracklistify/dev_cli
python cli.py <command>
```

## Configuration

The CLI uses a configuration file (`tools.yaml`) to define the available development tools and their settings. The configuration includes the command to execute, a description of the tool, and optional default arguments.

Example configuration in `tools.yaml`:

```yaml
pylint:
    command: pylint
    description: Python code linter
    args: --rcfile=.pylintrc

black:
    command: black
    description: Python code formatter
    args: --line-length=88

mypy:
    command: mypy
    description: Static type checker
    args: --strict

pytest:
    command: pytest
    description: Python test runner
    args: -v
```

### Running Tools

To run a tool, use the `RunCommand` with the tool name and any additional arguments:

```sh
python cli.py run <tool_name> [args...]
```

For example, to run `pylint` with default arguments:

```sh
python cli.py run pylint
```

To run `black` with custom arguments:

```sh
python cli.py run black --line-length=100
```

### Editing Tools

To add or edit tools, modify the `tools.yaml` file. Add a new entry or update an existing one with the desired command, description, and arguments.

Example of adding a new tool:

```yaml
flake8:
    command: flake8
    description: Python code linter
    args: --max-line-length=120
```

## Commands

### ListCommand

The `ListCommand` lists all available development tools defined in the configuration.

```python
class ListCommand(DevCommand):

        def execute(self) -> bool:
                """List all available tools.

                Returns:
                        bool: True if tools were listed successfully
                """
```

### RunCommand

The `RunCommand` executes a specified development tool with optional arguments.

```python
class RunCommand(DevCommand):

        def _run_tool(
                self,
                tool_name: str,
                tool_config: Dict[str, Any],
                args: List[str]
        ) -> bool:
                """Run a specified tool with optional arguments."""
```

## Development

To contribute to the development of the CLI, follow these steps:

1. Fork the repository.
2. Create a new branch for your feature or bugfix.
3. Make your changes and commit them with a descriptive message.
4. Push your changes to your fork.
5. Create a pull request to the main repository.

## License

This project is licensed under the MIT License. See the [LICENSE](../LICENSE) file for details.

## Features

- Modular command structure
- JSON-based tool configuration
- Comprehensive logging with file and console output
- Robust error handling and reporting
- Environment variable support for tools
- Command execution framework supporting both sync and async operations

## Error Handling

The CLI implements comprehensive error handling:

1. **ToolNotFoundError**: When a specified tool is not found in configuration
2. **ToolExecutionError**: When a tool execution fails
3. **ConfigurationError**: When there are issues with tool configuration
4. **General exceptions**: Unexpected errors during execution

All errors are:
- Logged with context and stack traces
- Reported to the user with helpful messages
- Include suggestions for resolution when possible

## Logging

The CLI provides comprehensive logging:

- Console output with color-coded messages
- File logging with rotation
- Debug mode for detailed information
- Structured logging with context

Configure logging with:
```sh
python cli.py --debug --log-dir=/path/to/logs run <tool_name>
```

## Adding New Commands

1. Create a new command class inheriting from `DevCommand`
2. Implement the `execute()` method
3. Register the command in the CLI group

Example:
```python
class NewCommand(DevCommand):
    def execute(self, *args, **kwargs) -> bool:
        # Implementation
        return True
```

## Testing

Run tests with:
```sh
python -m pytest tests/
```

## Contributing

1. Fork the repository
2. Create a feature branch
3. Make your changes
4. Submit a pull request

## Debugging Commands

Here are some useful commands for debugging the dev_cli:

### Code Quality Checks

```bash
# Run pylint with debug output and custom log directory
python tracklistify/dev.py --debug --log-dir logs run pylint tracklistify/dev_cli

# Run black with verbose output
python tracklistify/dev.py --debug run black tracklistify/dev_cli --verbose

# Run mypy with detailed error messages
python tracklistify/dev.py --debug run mypy tracklistify/dev_cli --show-error-codes
```

### Testing

```bash
# Run pytest with debug logging
python tracklistify/dev.py --debug --log-dir logs run pytest tracklistify/tests/

# Run specific test file with verbose output
python tracklistify/dev.py --debug run pytest tracklistify/tests/test_config.py -vv

# Run tests with coverage report
python tracklistify/dev.py run pytest --cov=tracklistify --cov-report=term-missing
```

### Tool Configuration

```bash
# List all available tools with debug output
python tracklistify/dev.py --debug list

# Run a tool with custom environment variables
PYTHONPATH=. python tracklistify/dev.py --debug run pylint --rcfile=custom_pylintrc

# Check tool configuration
python tracklistify/dev.py --debug run pylint --list-msgs
```

### Common Debugging Scenarios

1. Debug configuration loading:
```bash
python tracklistify/dev.py --debug --log-dir logs list
```

2. Debug tool execution with specific arguments:
```bash
python tracklistify/dev.py --debug --log-dir logs run black tracklistify/dev_cli --check
```

3. Debug import issues:
```bash
PYTHONPATH=. python tracklistify/dev.py --debug run pylint --generate-rcfile
```

4. Debug command registration:
```bash
python tracklistify/dev.py --debug help
```

### Log File Analysis

The log files contain detailed information about:
- Tool configuration loading
- Command execution
- Environment variables
- Error messages and stack traces

View the logs:
```bash
# View the latest log file
tail -f logs/dev_cli.log

# Search for specific error messages
grep "ERROR" logs/dev_cli.log

# View configuration loading logs
grep "Loaded configuration" logs/dev_cli.log
