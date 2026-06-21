from setuptools import setup, find_packages

setup(
    name="shell-dep",
    version="1.0.0",
    description="Shell script dependency analyzer - visualizes source/. dependencies as ASCII tree",
    packages=find_packages(),
    python_requires=">=3.7",
    install_requires=[
        "colorama>=0.4.0",
    ],
    entry_points={
        "console_scripts": [
            "shell-dep=shell_dep.cli:main",
        ],
    },
)
