# refactor-prompt.md
This document outlines a detailed, step-by-step refactoring plan for the **Tracklistify** project, based on the refactor.md document. The goal is to provide comprehensive technical prompts for each part of the refactoring process to ensure clarity and prevent misunderstandings during implementation.

---

## Introduction

The refactoring process is divided into five main phases:

1. **Project Structuring and Cleanup**
2. **Core Refactoring**
3. **Provider and Downloader Improvements**
4. **Testing Infrastructure**
5. **Code Quality Enhancements**

Each phase contains specific steps with detailed prompts to guide the refactoring efforts.

---

## Phase 1: Project Structuring and Cleanup

### Step 1: Consolidate Modules

**Prompt:**

- **Task:** Consolidate duplicate logging functionalities into a single module.
- **Files Involved:**
    - track.py
    - base.py
    - logger.py

- **Action Items:**
    1. Identify all logging implementations across the codebase.
    2. Create or update logger.py to include all necessary logging configurations and utilities.
    3. Remove logging code from `track.py` and `base.py`.
    4. Update these modules to import and use the centralized logging utilities from `utils/logger.py`.
- **Objective:** Ensure consistent logging practices throughout the project by using a centralized logging module.

**Prompt:**

- **Task:** Merge validation functions into a single module.
- **Files Involved:**
    - validation.py
    - validation.py

- **Action Items:**
    1. Review both `validation.py` files to identify overlapping functions.
    2. Decide which functions should be kept and which can be removed or merged.
    3. Consolidate all validation logic into `utils/validation.py`.
    4. Update all references in the codebase to use the consolidated validation functions.
    5. Remove `config/validation.py` if it is no longer needed.
- **Objective:** Eliminate redundancy by centralizing validation logic, improving maintainability.

### Step 2: Standardize Naming Conventions

**Prompt:**

- **Task:** Ensure consistent naming conventions across all modules.
- **Action Items:**
    1. Review all class names to ensure they use PascalCase.
    2. Review all function and method names to ensure they use snake_case.
    3. Refactor any names that do not comply with these conventions.
    4. Update all references to the renamed classes, functions, and methods throughout the codebase.
- **Objective:** Improve code readability and maintainability through consistent naming.

### Step 3: Simplify Imports with `__init__.py`

**Prompt:**

- **Task:** Organize and simplify imports using `__init__.py` files.
- **Action Items:**
    1. For each package directory (e.g., core, utils, providers), update the `__init__.py` file.
    2. Define the `__all__` list in each `__init__.py` to specify the public API of the package.
    3. Import key classes and functions in the `__init__.py` files to facilitate easier imports elsewhere.
    4. Refactor import statements in other modules to use the simplified package imports.
- **Example:**

    ```python
    # In tracklistify/utils/__init__.py
    from .logger import get_logger, setup_logger
    from .validation import validate_url, clean_url

    __all__ = ["get_logger", "setup_logger", "validate_url", "clean_url"]
    ```

- **Objective:** Simplify the import structure, making the codebase more intuitive and easier to navigate.

### Step 4: Remove Dead Code

**Prompt:**

- **Task:** Detect and remove unused or obsolete code.
- **Action Items:**
    1. Use the `vulture` tool to scan the codebase for dead code:

         ```bash
         vulture tracklistify/
         ```

    2. Review the reported unused code to confirm whether it is truly unnecessary.
    3. Remove confirmed dead code from the codebase.
    4. Run the test suite to ensure that the removal of code does not break existing functionality.
- **Objective:** Clean up the codebase, reducing clutter and potential confusion.

---

## Phase 2: Core Refactoring

### Step 1: Refactor Track Processing Engine

**Prompt:**

- **Task:** Enhance the `TrackProcessor` class for better asynchronous handling and error management.
- **Files Involved:**
    - `tracklistify/core/track_processor.py` (assumed location)
- **Action Items:**
    1. Review the `TrackProcessor` class implementation.
    2. Ensure all asynchronous operations use proper `async`/`await` syntax.
    3. Implement async context managers where appropriate.
    4. Add retry mechanisms with exponential backoff for network calls or operations that may fail intermittently.
    5. Integrate standardized exception handling using custom exceptions from the `exceptions` module.
    6. Write unit tests to cover the new asynchronous and error-handling logic.
- **Objective:** Improve the reliability and performance of the track processing engine.

### Step 2: Enhance Provider Interfaces

**Prompt:**

- **Task:** Define a clear protocol or abstract base class for all track identification providers.
- **Files Involved:**
    - base.py
    - `tracklistify/providers/shazam_provider.py`
    - `tracklistify/providers/acrcloud_provider.py`
- **Action Items:**
    1. Create or update `base.py` to include an abstract base class or protocol with required methods like `identify_track` and `enrich_metadata`.
    2. Ensure that all provider classes inherit from the base class or implement the protocol.
    3. Refactor provider implementations to align with the standardized interface.
    4. Update the provider factory to utilize the new standardized interfaces.
    5. Implement fallback mechanisms: if one provider fails, the system should seamlessly switch to another.
- **Objective:** Standardize provider implementations, making it easier to add or modify providers in the future.

### Step 3: Optimize Configuration Management

**Prompt:**

- **Task:** Centralize and streamline configuration loading, parsing, and validation.
- **Files Involved:**
    - __init__.py
    - `tracklistify/config/config.py` (assumed)
- **Action Items:**
    1. Use a configuration management library like `pydantic` or `dynaconf` to handle configurations.
    2. Ensure configurations can be loaded from environment variables, .env files, or configuration files (e.g., YAML, JSON).
    3. Centralize all configuration definitions in a single module.
    4. Implement validation logic within the configuration classes using built-in validators.
    5. Update all parts of the application to use the centralized configuration.
    6. Consider adding hot-reloading capabilities if configurations may change at runtime.
- **Objective:** Simplify configuration management, making the application more flexible and easier to maintain.

---

## Phase 3: Provider and Downloader Improvements

### Step 1: Improve Provider Factory

**Prompt:**

- **Task:** Enhance the provider factory to support provider chaining and dynamic configuration.
- **Files Involved:**
    - factory.py

- **Action Items:**
    1. Update the provider factory to allow configuring the order of providers based on priority levels.
    2. Modify the factory to enable or disable providers based on configuration settings.
    3. Implement logic to try providers in order until one succeeds or all fail.
    4. Ensure that exceptions from individual providers are handled gracefully without crashing the application.
    5. Update documentation to reflect how the provider factory works with the new enhancements.
- **Objective:** Make the provider system more robust and configurable, improving reliability.

### Step 2: Enhance Metadata Enrichment

**Prompt:**

- **Task:** Optimize metadata enrichment by improving API integrations and implementing caching.
- **Files Involved:**
    - `tracklistify/providers/spotify_provider.py`
    - `tracklistify/utils/cache.py` (if available)
- **Action Items:**
    1. Review current API integration with Spotify and other metadata sources.
    2. Implement caching mechanisms to store recent API responses, reducing redundant API calls.
    3. Ensure compliance with API rate limits and terms of service.
    4. Add validation and sanitization steps for the enriched metadata.
    5. Update unit tests to cover the new caching logic and any changes to metadata processing.
- **Objective:** Provide users with more accurate and detailed metadata while optimizing API usage.

### Step 3: Refine Download Management

**Prompt:**

- **Task:** Simplify downloader implementations and add support for resuming downloads.
- **Files Involved:**
    - youtube.py
    - mixcloud.py
    - spotify.py

- **Action Items:**
    1. Identify common functionalities across downloader modules and extract them into a base class or utility functions.
    2. Implement exception handling to manage network errors, timeouts, and other issues during downloads.
    3. Add functionality to resume interrupted downloads, potentially using content headers or download libraries that support resuming.
    4. Incorporate checksums or hashes to verify download integrity.
    5. Update documentation and test cases accordingly.
- **Objective:** Improve the user experience by making downloads more reliable and efficient.

---

## Phase 4: Testing Infrastructure

### Step 1: Reorganize Test Structure

**Prompt:**

- **Task:** Organize tests into distinct categories for clarity and maintainability.
- **Files Involved:**
    - `tests/unit/`
    - `tests/integration/`
    - `tests/performance/`
- **Action Items:**
    1. Create directories for unit, integration, and performance tests within the tests directory.
    2. Move existing test files into the appropriate directories based on their scope.
    3. Rename test files and functions to be more descriptive (e.g., `test_track_processor.py`).
    4. Ensure that the test discovery mechanism is updated to find tests in the new locations.
- **Objective:** Improve test organization, making it easier for developers to locate and write tests.

### Step 2: Increase Test Coverage

**Prompt:**

- **Task:** Write additional tests to cover untested code paths and scenarios.
- **Action Items:**
    1. Use `pytest-cov` to generate a coverage report:

         ```bash
         pytest --cov=tracklistify tests/
         ```

    2. Identify modules and functions with low coverage.
    3. Write unit tests for uncovered code, focusing on edge cases and error conditions.
    4. Utilize mocking to isolate tests from external dependencies like network calls.
    5. Update the test suite to include these new tests and ensure all tests pass.
- **Objective:** Increase confidence in the codebase by ensuring all logic is tested.

### Step 3: Implement Continuous Integration (CI)

**Prompt:**

- **Task:** Set up automated testing and code quality checks using GitHub Actions.
- **Files Involved:**
    - `.github/workflows/ci.yml`
- **Action Items:**
    1. Create a CI workflow file in `.github/workflows/ci.yml`.
    2. Configure the workflow to trigger on `push` and `pull_request` events.
    3. Define jobs to:
         - Set up the Python environment.
         - Install dependencies.
         - Run linters (ruff, pylint) and formatters (black).
         - Run type checks with mypy.
         - Execute tests with pytest.
         - Generate coverage reports and, optionally, upload them to a service like Codecov.
    4. Ensure that the workflow fails if any step does not pass.
- **Objective:** Automate quality checks to maintain high standards and catch issues early.

---

## Phase 5: Code Quality Enhancements

### Step 1: Static Analysis and Type Checking

**Prompt:**

- **Task:** Introduce type hints throughout the codebase and enforce type checking with mypy.
- **Action Items:**
    1. Add type annotations to all functions, methods, and variables.
    2. Install mypy and add it to the development requirements.
    3. Run mypy to identify type inconsistencies:

         ```bash
         mypy tracklistify/
         ```

    4. Resolve any type errors reported by mypy.
    5. Update the CI workflow to include mypy checks.
- **Objective:** Improve code clarity and prevent type-related bugs.

### Step 2: Code Formatting

**Prompt:**

- **Task:** Enforce consistent code formatting using black.
- **Action Items:**
    1. Install black and add it to the development dependencies.
    2. Run black on the entire codebase:

         ```bash
         black tracklistify/ tests/
         ```

    3. Configure black settings in pyproject.toml if customization is needed.
    4. Set up a pre-commit hook for black in .pre-commit-config.yaml:

         ```yaml
         repos:
         -   repo: https://github.com/psf/black
                 rev: 22.3.0
                 hooks:
                 -   id: black
         ```

    5. Install pre-commit hooks:

         ```bash
         pre-commit install
         ```

    6. Ensure all future commits are checked for formatting compliance.
- **Objective:** Maintain a consistent code style, enhancing readability and collaboration.

### Step 3: Documentation

**Prompt:**

- **Task:** Update and generate comprehensive documentation using Sphinx.
- **Action Items:**
    1. Install Sphinx and initialize documentation in the docs directory:

         ```bash
         sphinx-quickstart docs
         ```

    2. Configure Sphinx to auto-generate documentation from docstrings using extensions like `sphinx.ext.autodoc`.
    3. Update code docstrings to follow a consistent style guide (e.g., Google or NumPy style).
    4. Add code examples and detailed explanations where necessary.
    5. Build the HTML documentation:

         ```bash
         make -C docs html
         ```

    6. Update README.md with links to the generated documentation and instructions on how to build it.
- **Objective:** Provide users and contributors with clear, accessible documentation.

---

## General Best Practices

### Version Control

**Prompt:**

- **Action Items:**
    1. Use Git feature branches for each refactoring task:

         ```bash
         git checkout -b refactor/<task-name>
         ```

    2. Write commit messages following the Conventional Commits specification:

         ```
         feat: description of the new feature
         fix: description of the bug fix
         refactor: description of the refactoring
         ```

    3. Open pull requests for code reviews, ensuring at least one other developer reviews and approves before merging.

### Dependency Management

**Prompt:**

- **Action Items:**
    1. Use poetry to manage dependencies:

         ```bash
         poetry add <package>
         ```

    2. Regularly run `poetry update` to update dependencies.
    3. Check for known security vulnerabilities with tools like `safety`:

         ```bash
         safety check
         ```

    4. Ensure pyproject.toml and `poetry.lock` are up to date and committed to version control.

### Pre-Commit Hooks

**Prompt:**

- **Action Items:**
    1. Update .pre-commit-config.yaml to include desired hooks for linting, formatting, and type checking.
    2. Ensure all developers install pre-commit hooks by running:

         ```bash
         pre-commit install
         ```

    3. Test the hooks locally to confirm they work as expected.

---

## Conclusion

By following this detailed refactoring plan, we can collaboratively improve the Tracklistify project in a structured and efficient manner. Each step is designed to address specific issues identified in the codebase, with clear objectives and action items to guide the process. This approach minimizes the risk of errors or misunderstandings, ensuring a successful refactoring effort.

---

**Note:** As we proceed with the refactoring, it's essential to continuously communicate updates and challenges within the development team to maintain alignment and address any issues promptly.
