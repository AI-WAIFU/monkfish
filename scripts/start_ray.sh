#!/bin/bash

# Start Ray with specified parameters
/root/miniconda/bin/conda run --name catfish \
    ray start --address="$1" --resources="$2" --object-store-memory "$3"
