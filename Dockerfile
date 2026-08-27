# it's offical so i'm using it + alpine so damn small
FROM python:3.8.3-alpine3.10

# install required packages - requires build-base due to psutil GCC complier requirements
RUN apk add --no-cache build-base python3-dev linux-headers

# copy the codebase
COPY . /worker

# install Python packages
# setuptools<60 + --no-build-isolation: psutil==5.8.0 (2021) fails to compile
# against whatever setuptools pip's build isolation fetches fresh at build
# time (a "cython_sources" AttributeError from setuptools' rewritten
# distutils shim in 60+) - pinning an old setuptools in the main env and
# disabling isolation makes pip use that pinned copy instead.
RUN pip install "setuptools<60" wheel && \
    pip install --no-build-isolation -r /worker/requirements.txt

#set python to be unbuffered
ENV PYTHONUNBUFFERED=1

# run the worker-manger
WORKDIR /worker
CMD [ "python", "/worker/worker.py" ]
