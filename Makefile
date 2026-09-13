# Entry points for the scripts in this repo, so tooling that looks for a
# declared command finds one without a package.json.
.PHONY: validate test install

validate:
	./validate.sh

test:
	./hooks/test-hooks.sh

install:
	./install.sh
