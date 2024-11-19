"""
Setup configuration for Tracklistify package.
"""

from setuptools import setup, find_packages

setup(
    name="tracklistify",
    version="0.5.4",
    packages=find_packages(),
    install_requires=[
        "pydub>=0.25.1",
        "pyacrcloud>=1.0.7",
        "yt-dlp>=2023.7.6",
        "requests>=2.31.0",
        "configparser>=5.3.0",
        "python-dotenv>=1.0.0",
        "aiohttp>=3.8.0",
        "shazamio>=0.4.0",
        "librosa==0.10.1",
        "numba==0.58.1",
        "numpy>=1.23.5,<2.0.0",
        "llvmlite==0.41.1",
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
    author="Tracklistify Team",
    description="Automatically identify and catalog tracks from DJ mixes and audio streams",
    long_description=open("README.md").read(),
    long_description_content_type="text/markdown",
    url="https://github.com/yourusername/tracklistify",
    classifiers=[
        "Development Status :: 4 - Beta",
        "Intended Audience :: End Users/Desktop",
        "License :: OSI Approved :: MIT License",
        "Programming Language :: Python :: 3.11",
        "Topic :: Multimedia :: Sound/Audio :: Analysis",
        "Topic :: Multimedia :: Sound/Audio :: Conversion",
    ],
    python_requires=">=3.11",
)
