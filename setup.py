import setuptools

with open("README.md", "r") as fh:
    long_description = fh.read()

setuptools.setup(
    name="bigbeans-kaylynn234",
    version="1.0.0rc1",
    author="Kaylynn Morgan",
    author_email="mkaylynn7@gmail.com",
    description="A bad database wrapper",
    long_description=long_description,
    long_description_content_type="text/markdown",
    url="https://github.com/kaylynn234/bigbeans",
    packages=setuptools.find_packages(),
    classifiers=[
        "Development Status :: 4 - Beta",
        "Programming Language :: Python :: 3.6",
        "Programming Language :: Python :: 3.7",
        "Programming Language :: Python :: 3.8",
        "License :: OSI Approved :: MIT License",
        "Operating System :: OS Independent",
    ],
    python_requires='>=3.6',
    install_requires=[
        "asyncpg"
    ]
)