FROM nvidia/cuda:12.1.1-runtime-ubuntu22.04

WORKDIR /workspace

RUN apt-get update && \
    apt-get install -y python3-pip python3-dev && \
    rm -rf /var/lib/apt/lists/*

RUN python3 -m pip install --upgrade pip

RUN apt-get update && \
    apt-get install -y git --no-install-recommends && \
    rm -rf /var/lib/apt/lists/*


RUN git clone --depth 1 https://github.com/EleutherAI/lm-evaluation-harness && \
    cd lm-evaluation-harness && \
    pip install -e .