FROM ubuntu:bionic

RUN apt-get update && DEBIAN_FRONTEND=noninteractive apt-get install --no-install-recommends -y \
    ca-certificates \
    python3 \
    python3-setuptools \
    python3-wheel \
    python3-pip

RUN mkdir /highfive
WORKDIR /highfive

COPY setup.py .
COPY highfive/*.py highfive/
COPY highfive/configs/ highfive/configs/
RUN pip3 install .

EXPOSE 80
ENV HIGHFIVE_PORT 80
ENV HIGHFIVE_CONFIG_DIR /highfive/highfive/configs

ENV LC_ALL=C.UTF-8
ENV LANG=C.UTF-8

# Allow logs to show up timely on CloudWatch.
ENV PYTHONUNBUFFERED=1

CMD highfive
