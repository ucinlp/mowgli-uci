# mowgli-uci
code related to UCI MOWGLI project


## Getting started

We recommend using the conda python package manager.
To install the necessary dependencies run:
```{bash}
conda install --file requirements.txt
```
You will also need to download the latest ConceptNet Numberbatch embeddings \[[link](https://conceptnet.s3.amazonaws.com/downloads/2019/numberbatch/numberbatch-en-19.08.txt.gz)\]


## Linking Instructions

To obtain link candidates run:
```{bash}
python link.py link \
    --input [INPUT FILE] \
    --output [OUTPUT FILE] \
    --embeddings [PATH TO THE NUMBERBATCH EMBEDDINGS]
```

For further details run:
```{bash}
python link.py link --help
```
