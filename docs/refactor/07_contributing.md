# Contributing Guidelines

<div align="center">

[⬅️ Troubleshooting](06_troubleshooting.md) | [🏠 Home](README.md) | [Checklist ➡️](08_checklist.md)

</div>

---

**Topics:** `#contributing` `#guidelines` `#pr-process` `#standards`

**Related Files:**
- [`CONTRIBUTING.md`](../CONTRIBUTING.md)
- [`CODE_OF_CONDUCT.md`](../CODE_OF_CONDUCT.md)
- [`.github/PULL_REQUEST_TEMPLATE.md`](../.github/PULL_REQUEST_TEMPLATE.md)
- [`.github/ISSUE_TEMPLATE/`](../.github/ISSUE_TEMPLATE/)

---

## Getting Started

1. Fork the repository
2. Create your feature branch (`git checkout -b feature/amazing-feature`)
3. Run all quality checks (`poetry run dev -a`)
4. Commit your changes using commitizen (`poetry run cz commit`)
5. Push to the branch (`git push origin feature/amazing-feature`)
6. Create a Pull Request

## Development Workflow

### 1. Setting Up Your Environment
```bash
# Clone your fork
git clone https://github.com/YOUR_USERNAME/tracklistify.git
cd tracklistify

# Add upstream remote
git remote add upstream https://github.com/betmoar/tracklistify.git

# Install dependencies
poetry install
```

### 2. Making Changes
- Follow the coding style guide
- Add tests for new functionality
- Update documentation as needed
- Keep commits atomic and well-described

### 3. Quality Checks
```bash
# Run all checks
poetry run dev -a

# Run specific checks
poetry run dev -t pylint
poetry run dev -t pytest
```

### 4. Submitting Changes
- Keep pull requests focused on a single feature or fix
- Update the CHANGELOG.md file
- Ensure CI/CD checks pass
- Request review from maintainers

## License

This project is licensed under the MIT License - see the [LICENSE](LICENSE) file for details.
