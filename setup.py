"""
Setup configuration for Tracklistify package.
"""

from setuptools import setup, find_packages

setup(
    name="tracklistify",
    version="0.5.6",
    packages=find_packages(),
    install_requires=[
        "aiohttp>=3.8.0",
        "python-dotenv>=0.19.0",
        "yt-dlp>=2023.11.16",
        "mutagen>=1.45.1",
        "shazamio>=0.4.0.1",
        "pydub>=0.25.1",
    ],
    extras_require={
        "dev": [
            "pytest>=7.4.0",
            "pytest-cov>=4.1.0",
            "pytest-asyncio>=0.21.1",
            "black>=23.7.0",
            "isort>=5.12.0",
            "flake8>=6.1.0",
            "mypy>=1.5.1",
            "pre-commit>=3.3.3",
        ],
    },
    entry_points={
        "console_scripts": [
            "tracklistify=tracklistify.__main__:main",
        ],
    },
    author="Your Name",
    author_email="your.email@example.com",
    description="Audio track identification and tracklist generation tool",
    long_description=open("README.md").read(),
    long_description_content_type="text/markdown",
    url="https://github.com/yourusername/tracklistify",
    classifiers=[
        "Development Status :: 4 - Beta",
        "Intended Audience :: End Users/Desktop",
        "License :: OSI Approved :: MIT License",
        "Programming Language :: Python :: 3.8",
        "Programming Language :: Python :: 3.9",
        "Programming Language :: Python :: 3.10",
        "Programming Language :: Python :: 3.11",
    ],
    python_requires=">=3.8",
)
