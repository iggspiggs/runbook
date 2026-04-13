"""
setup.py for runbook-sdk.

Use ``pip install -e .`` for local development.
For production releases, prefer ``pyproject.toml`` + ``build``.
"""

from pathlib import Path

from setuptools import find_packages, setup

here = Path(__file__).parent
long_description = (here / "README.md").read_text(encoding="utf-8") if (here / "README.md").exists() else ""

setup(
    name="runbook-sdk",
    version="0.1.0",
    author="Runbook",
    author_email="sdk@runbook.io",
    description="SDK for annotating automation rules for the Runbook registry",
    long_description=long_description,
    long_description_content_type="text/markdown",
    url="https://github.com/runbook-io/runbook-sdk-python",
    project_urls={
        "Documentation": "https://docs.runbook.io/sdk/python",
        "Source": "https://github.com/runbook-io/runbook-sdk-python",
        "Tracker": "https://github.com/runbook-io/runbook-sdk-python/issues",
    },
    packages=find_packages(exclude=["tests*", "examples*"]),
    python_requires=">=3.10",
    install_requires=[
        "pydantic>=2.0",
        "httpx>=0.24",
    ],
    extras_require={
        "dev": [
            "pytest>=7.0",
            "pytest-cov",
            "mypy>=1.0",
            "ruff>=0.1",
        ],
    },
    classifiers=[
        "Development Status :: 3 - Alpha",
        "Intended Audience :: Developers",
        "Topic :: Software Development :: Libraries :: Python Modules",
        "License :: OSI Approved :: MIT License",
        "Programming Language :: Python :: 3",
        "Programming Language :: Python :: 3.10",
        "Programming Language :: Python :: 3.11",
        "Programming Language :: Python :: 3.12",
        "Typing :: Typed",
    ],
    keywords="automation rules registry runbook observability",
    include_package_data=True,
    zip_safe=False,
)
