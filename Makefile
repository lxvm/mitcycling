# MIT Cycling site — common tasks.
#
#   make            build the site into public/ (same as `make build`)
#   make serve      live-reloading local preview at http://localhost:1313/
#   make logo       regenerate assets/logo.svg + assets/favicon.svg from scripts/build_logo.py
#   make results    refresh data/race_results_live.json from the results feed
#   make deploy     build and publish to gh-pages (wraps ./deploy.sh)
#   make clean      remove build output

HUGO      ?= hugo
PYTHON    ?= python3
PORT      ?= 1313
BIND      ?= 127.0.0.1
OUT       ?= public

.PHONY: all build results serve deploy clean logo

all: logo results build

# Plain build, using whatever results data is already in data/.
# --cleanDestinationDir keeps deleted pages from lingering in public/.
build: 
	$(HUGO) --minify --cleanDestinationDir -d $(OUT)

# Badge artwork. The SVGs are committed, so a normal build doesn't need
# fontTools; rerun `make logo` after changing the script or its font.
LOGO_SRC := scripts/build_logo.py scripts/fonts/AlfaSlabOne-Regular.ttf

logo: assets/logo.svg assets/favicon.svg

assets/logo.svg: $(LOGO_SRC)
	$(PYTHON) scripts/build_logo.py -o $@

assets/favicon.svg: $(LOGO_SRC)
	$(PYTHON) scripts/build_logo.py -o $@

results:
	$(PYTHON) scripts/fetch_results.py

serve:
	$(HUGO) server --bind $(BIND) --port $(PORT) --buildDrafts --disableFastRender

deploy:
	./deploy.sh

clean:
	rm -rf $(OUT) resources/_gen .hugo_build.lock
