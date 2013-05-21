#
# Simple makefile for ldapfs development
#

# Change this if you want this virtualenv to live alongside
# your other environments
VENV=/tmp/ldapfs-dev
PIP_DOWNLOAD_CACHE ?= $(PWD)/.pip_cache
PIP = $(VENV)/bin/pip install --download-cache $(PIP_DOWNLOAD_CACHE) --use-mirrors
PYTHON = $(VENV)/bin/python
SED=sed
PYLINT=pylint
PYLINTRC_SRC = $(PWD)/dev/etc/pylintrc
PYLINTRC = $(VENV)/bin/pylintrc

.PHONY: all clean virtualenv build test

all: virtualenv build pylint

virtualenv: $(VENV)

$(VENV):
	virtualenv $(VENV)

build: virtualenv
	$(PIP) -U -r requirements.txt
	$(PYTHON) setup.py develop

$(PYLINTRC):
	$(SED) "s%##REPLACE##%$(VENV)%" "$(PYLINTRC_SRC)" >| "$(PYLINTRC)"

pylint: virtualenv $(PYLINTRC)
	$(PYLINT) --rcfile="$(PYLINTRC)" ldapfs

clean:
	rm -rf $(VENV) build dist *.egg-info

dist-clean: clean
	rm -rf $(PIP_DOWNLOAD_CACHE)
