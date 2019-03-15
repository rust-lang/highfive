FROM ubuntu:bionic

RUN apt-get update && DEBIAN_FRONTEND=noninteractive apt-get install --no-install-recommends -y \
    ca-certificates \
    python \
    python-setuptools \
    python-wheel \
    python-pip

RUN mkdir /highfive
WORKDIR /highfive

COPY setup.py .
COPY highfive/*.py highfive/
COPY highfive/configs/ highfive/configs/
RUN pip install .

EXPOSE 80
ENV HIGHFIVE_PORT 80
ENV HIGHFIVE_CONFIG_DIR /highfive/highfive/configs

CMD highfive
