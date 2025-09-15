# Contributing to Tracklistify

We love your input! We want to make contributing to Tracklistify as easy and transparent as possible, whether it's:

- Reporting a bug
- Discussing the current state of the code
- Submitting a fix
- Proposing new features
- Becoming a maintainer

## Development Process

We use GitHub to host code, to track issues and feature requests, as well as accept pull requests.

1. Fork the repo and create your branch from `main`
2. Set up your development environment:
   ```bash
   # Clone your fork
   git clone https://github.com/betmoar/tracklistify.git
   cd tracklistify

   # Run the setup script
   ./env-setup.sh --dev
   ```

3. Make your changes:
   - Write your code
   - Add or update tests as needed
   - Update documentation if required

4. Ensure your code meets our standards:
   ```bash
   # Code formatting and linting is handled by pre-commit hooks
   # Run manually if needed:
   black .
   isort .
   flake8
   mypy .

   # Run tests
   pytest
   ```

5. Commit your changes:
   ```bash
   git add .
   git commit -m "Description of changes"
   ```

## Development Environment

- Python 3.11 or higher
- Required system dependencies:
  - ffmpeg
  - git

The `env-setup.sh` script will:
- Create a virtual environment
- Install all dependencies
- Set up pre-commit hooks
- Configure development tools

## Code Style

We use several tools to maintain code quality:
- Black for code formatting
- isort for import sorting
- flake8 for linting
- mypy for type checking

All code must:
- Include type hints
- Have comprehensive docstrings
- Follow PEP 8 guidelines
- Pass all linting and type checks

## Testing

- Write tests for new features
- Update tests for modified code
- Ensure all tests pass before submitting PR
- Maintain or improve code coverage

## Pull Request Process

1. Update the README.md with details of changes if needed
2. Update the CHANGELOG.md under the [Unreleased] section
3. Update documentation if you're changing functionality
4. The PR will be merged once you have the sign-off of a maintainer

## Any contributions you make will be under the MIT Software License

In short, when you submit code changes, your submissions are understood to be under the same [MIT License](http://choosealicense.com/licenses/mit/) that covers the project. Feel free to contact the maintainers if that's a concern.

## Report bugs using GitHub's [issue tracker](https://github.com/betmoar/tracklistify/issues)

We use GitHub issues to track public bugs. Report a bug by [opening a new issue](https://github.com/betmoar/tracklistify/issues/new).

## Write bug reports with detail, background, and sample code

**Great Bug Reports** tend to have:

- A quick summary and/or background
- Steps to reproduce
  - Be specific!
  - Give sample code if you can
- What you expected would happen
- What actually happens
- Notes (possibly including why you think this might be happening, or stuff you tried that didn't work)

## License

By contributing, you agree that your contributions will be licensed under its MIT License.
