from setuptools import setup, find_packages


setup(
    name="graphify",
    version="0.1.0",
    packages=find_packages(),
    install_requires=[
        "allennlp>=0.9.0",
        "numpy>=1.17.4",
        "spacy>=2.2.3",
        "tqdm>=4.40.2",
        "wordfreq>=2.2.1"
    ],
    tests_require=[
        'pytest',
        'pytest-cov',
        'codecov'
    ]
)