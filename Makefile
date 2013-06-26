#
# Makefile for ldapfs development
#

# If you're currently in a virtual environment ldapfs will
# install the development environment into that env. If not
# it uses /tmp/ldapfs-dev
VIRTUAL_ENV ?= /tmp/ldapfs-dev
PIP_DOWNLOAD_CACHE ?= $(PWD)/.pip_cache
PIP = $(VIRTUAL_ENV)/bin/pip install --download-cache $(PIP_DOWNLOAD_CACHE) --use-mirrors
PYTHON = $(VIRTUAL_ENV)/bin/python
SED=sed
PYLINT=pylint
PYLINTRC_SRC = $(PWD)/dev/etc/pylintrc
PYLINTRC = $(VIRTUAL_ENV)/bin/pylintrc

.PHONY: all clean virtualenv build test

all: virtualenv build pylint

virtualenv: $(VIRTUAL_ENV)

$(VIRTUAL_ENV):
	virtualenv $(VIRTUAL_ENV)

build: virtualenv
	$(PYTHON) setup.py develop

sdist: virtualenv
	$(PYTHON) setup.py sdist

bdist: virtualenv
	$(PYTHON) setup.py bdist

$(PYLINTRC): $(PYLINTRC_SRC)
	$(SED) "s%##REPLACE##%$(VIRTUAL_ENV)%" "$(PYLINTRC_SRC)" >| "$(PYLINTRC)"

pylint: virtualenv build $(PYLINTRC)
	$(PYLINT) --rcfile="$(PYLINTRC)" ldapfs

clean:
	rm -rf $(VIRTUAL_ENV) build dist *.egg-info log

dist-clean: clean
	rm -rf $(PIP_DOWNLOAD_CACHE)
