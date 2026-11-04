PYTHON ?= python3
.PHONY: check test validate doctor status tasks sources
check: validate test
validate:
	$(PYTHON) tools/lab.py validate
test:
	$(PYTHON) -m unittest discover -s tests -v
doctor:
	$(PYTHON) tools/lab.py doctor
status:
	$(PYTHON) tools/lab.py status --write
tasks:
	$(PYTHON) tools/lab.py task list
sources:
	$(PYTHON) tools/lab.py sources
