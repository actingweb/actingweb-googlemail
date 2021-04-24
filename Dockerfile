FROM python:3.7-slim-buster

RUN useradd -ms /bin/bash uwsgi
RUN mkdir /src
WORKDIR /src
COPY Pipfile.lock /src/
COPY Pipfile /src/
RUN apt-get update \
    && apt-get -y install build-essential python python-dev \
    && pip install --upgrade pip && pip install pipenv
COPY . /src
RUN pipenv install --dev --system --ignore-pipfile
EXPOSE 5000
#ENTRYPOINT ["/src/run.sh"]
