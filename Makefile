VENV=$(PWD)/dev/venv
PIP_DOWNLOAD_CACHE ?= $(PWD)/.pip_cache
PIP = $(VENV)/bin/pip install --download-cache $(PIP_DOWNLOAD_CACHE) --use-mirrors
PYTHON = $(VENV)/bin/python
SED=sed
PYLINT=pylint
PYLINTRC = $(PWD)/dev/etc/pylintrc

.PHONY: all clean virtualenv build test

all: virtualenv build fixup-pylintrc pylint

virtualenv: $(VENV)

$(VENV):
	python $(PWD)/dev/bin/virtualenv.py $(VENV)

build: virtualenv
	$(PIP) -U -r requirements.txt
	$(PYTHON) setup.py develop

fixup-pylintrc:
	$(SED) -i "s#REPLACE#$(PWD)#" $(PYLINTRC)

pylint: fixup-pylintrc virtualenv
	$(PYLINT) --rcfile=$(PYLINTRC) ldapfs

clean:
	rm -rf $(VENV) build dist *.egg-info
