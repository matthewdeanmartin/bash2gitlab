# -------- Config (override on the CLI: make build IMAGE_NAME=youruser/bash2gitlab) --------
IMAGE_NAME ?= matthewdeanmartin/bash2gitlab
B2G_VERSION ?= 0.9.1           # bash2gitlab version to install in the image
TAG ?= $(B2G_VERSION)          # image tag; default to the same as B2G version
IMG := $(IMAGE_NAME):$(TAG)
LATEST := $(IMAGE_NAME):latest

# If you decide to DROP tini from the Dockerfile, you can still get proper signal handling
# by adding --init to docker run. See the 'run' target below.

# -------- Local build (single-arch) --------
.PHONY: build
build:
	docker build \
	  --build-arg B2G_VERSION=$(B2G_VERSION) \
	  -t $(IMG) \
	  -f Dockerfile .

.PHONY: tag-latest
tag-latest:
	docker tag $(IMG) $(LATEST)

# Convenience run wrapper (mount PWD, keep file ownership)
# On Windows Git Bash/MSYS2, id -u/-g may not exist; remove --user if needed.
.PHONY: run
run:
	docker run --rm -it \
	  --user "$$(id -u 2>/dev/null || echo 0):$$(id -g 2>/dev/null || echo 0)" \
	  -v "$$PWD":/work -w /work \
	  --init \
	  $(IMG) --help

# -------- Docker Hub login --------
.PHONY: login
login:
	# You'll be prompted for your Docker Hub creds; or use DOCKER_CONFIG/creds store.
	docker login

# -------- Publish (single-arch push) --------
.PHONY: push
push: tag-latest
	docker push $(IMG)
	docker push $(LATEST)

# -------- Multi-arch (amd64 + arm64) with buildx --------
.PHONY: buildx-setup
buildx-setup:
	# Create and use a builder if it doesn't exist; bootstrap QEMU emulation if needed
	docker buildx create --use --name b2g-builder >/dev/null 2>&1 || true
	docker buildx inspect --bootstrap >/dev/null

.PHONY: publish-multiarch
publish-multiarch: buildx-setup
	docker buildx build \
	  --platform linux/amd64,linux/arm64 \
	  --build-arg B2G_VERSION=$(B2G_VERSION) \
	  -t $(IMG) -t $(LATEST) \
	  -f Dockerfile \
	  --push .

# -------- Clean local artifacts --------
.PHONY: clean
clean:
	- docker rmi $(IMG) 2>/dev/null || true
	- docker rmi $(LATEST) 2>/dev/null || true
