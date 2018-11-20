FROM ubuntu:bionic

RUN apt-get update && apt-get install -y apache2 \
  ca-certificates \
  python

# Set up Highfive
RUN mkdir /highfive
WORKDIR /highfive

COPY setup.py .
COPY highfive/*.py highfive/
COPY highfive/configs/* highfive/configs/
RUN python setup.py install
RUN touch highfive/config
RUN chown -R www-data:www-data .

# Set up Apache
WORKDIR /etc/apache2
COPY deployment/highfive.conf conf-available/highfive.conf
RUN a2enmod cgi
RUN rm conf-enabled/serve-cgi-bin.conf
RUN rm sites-enabled/*
RUN ln -s ../conf-available/highfive.conf conf-enabled

EXPOSE 80
CMD apachectl -D FOREGROUND
