VENV=$(PWD)/dev/venv
PIP_DOWNLOAD_CACHE ?= $(PWD)/.pip_cache
INSTALL = $(VENV)/bin/pip install --download-cache $(PIP_DOWNLOAD_CACHE) --use-mirrors
PYTHON = $(VENV)/bin/python

.PHONY: all clean virtualenv build test

all: virtualenv build

virtualenv: $(VENV)

$(VENV):
	python $(PWD)/dev/bin/virtualenv.py $(VENV)

build: virtualenv
	$(INSTALL) -U -r requirements.txt
	$(PYTHON) setup.py develop

clean:
	rm -rf $(VENV)
