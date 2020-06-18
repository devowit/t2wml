import setuptools

with open("README.md", "r") as fh:
    long_description = fh.read()
setuptools.setup(
    name="t2wml-api", 
    version="0.0.1",
    description="Programming API for T2WML, a cell-based Language for mapping tables into wikidata records",
    long_description=long_description,
    long_description_content_type="text/markdown",
	author="USC ISI and The Research Software Company",
    url="https://github.com/usc-isi-i2/t2wml/",
    packages=setuptools.find_packages(),
    classifiers=[
        "Programming Language :: Python :: 3"

    ],
    python_requires='>=3.6',
)